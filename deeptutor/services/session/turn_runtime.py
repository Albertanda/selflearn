"""
Turn-level runtime manager for unified chat streaming.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
import contextlib
from contextvars import Token
from dataclasses import dataclass, field
import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from anyio import CancelScope

from deeptutor.core.stream import StreamEvent, StreamEventType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from deeptutor.subjects.errors import SubjectOperationError
from deeptutor.services.llm.utils import clean_thinking_tags
from deeptutor.services.path_service import get_path_service
from deeptutor.services.session.artifact_attachments import (
    artifact_attachments,
    fill_preview_text,
)
from deeptutor.services.session.protocol import SessionStoreProtocol

if TYPE_CHECKING:
    from deeptutor.learning.storage import MasteryPathLease
    from deeptutor.services.llm.config import LLMConfig

logger = logging.getLogger(__name__)

MemoryReference = Literal["recent", "profile", "scope", "preferences", "summary"]


# Content call_kinds that make up the persisted answer. The chat agent loop
# streams every round's text as ``content`` with ``agent_loop_round``; the
# finish round (and forced-finish) are the answer, narration rounds are
# filtered back out via their ``call_role`` marker (see _narration_marker_call_id).
_ANSWER_CONTENT_CALL_KINDS = frozenset({"llm_final_response", "agent_loop_round"})
_FINAL_TURN_STATUSES = frozenset({"completed", "failed", "cancelled", "rejected"})


def _should_capture_assistant_content(event: StreamEvent) -> bool:
    if event.type != StreamEventType.CONTENT:
        return False
    metadata = event.metadata or {}
    call_id = metadata.get("call_id")
    if not call_id:
        return True
    return metadata.get("call_kind") in _ANSWER_CONTENT_CALL_KINDS


def _resolve_turn_outcome(
    assistant_events: Sequence[dict[str, Any]],
    done_event: StreamEvent | None,
) -> tuple[str, str]:
    """Resolve the persisted turn status and error from the terminal protocol."""
    done_metadata = (done_event.metadata or {}) if done_event is not None else {}
    status = str(done_metadata.get("status") or "completed")
    if status not in _FINAL_TURN_STATUSES:
        status = "completed"

    error = ""
    for event in reversed(assistant_events):
        metadata = event.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if event.get("type") != StreamEventType.ERROR.value or not metadata.get("turn_terminal"):
            continue
        terminal_status = str(metadata.get("status") or "failed")
        status = terminal_status if terminal_status in _FINAL_TURN_STATUSES else "failed"
        if status == "completed":
            status = "failed"
        error = str(event.get("content") or "")
        break

    return status, error


def _narration_marker_call_id(event: StreamEvent) -> str | None:
    """call_id of a chat-loop round that resolved as narration (a short
    preamble streamed alongside a tool call). Its text belongs to the trace,
    not the persisted answer, so it is excluded when assembling content.

    A round may explicitly keep learner-facing prose surrounding a call via
    ``answer_visible`` (for example DSML or mastery tutoring); that narrow
    exception remains part of the persisted answer.
    """
    metadata = event.metadata or {}
    if (
        metadata.get("trace_kind") == "call_status"
        and metadata.get("call_state") == "complete"
        and metadata.get("call_role") == "narration"
        and metadata.get("answer_visible") is not True
    ):
        call_id = metadata.get("call_id")
        return str(call_id) if call_id else None
    return None


def _assemble_persisted_answer(
    content_segments: Sequence[tuple[str | None, str]],
    narration_call_ids: set[str],
) -> str:
    """Replay visible content bytes, excluding trace-only narration rounds."""
    return clean_thinking_tags(
        "".join(
            text
            for call_id, text in content_segments
            if not (call_id and call_id in narration_call_ids)
        )
    )


def _clip_text(value: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


_TITLE_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ('"', '"'),
    ("'", "'"),
    ("“", "”"),
    ("‘", "’"),
    ("「", "」"),
    ("『", "』"),
    ("`", "`"),
)
_TITLE_PREFIXES: tuple[str, ...] = (
    "Title:",
    "title:",
    "TITLE:",
    "Title-",
    "标题：",
    "标题:",
    "对话标题：",
    "对话标题:",
)
_TITLE_TRAILING_PUNCT = ".。!！?？,，;；、 \t"
_INTERRUPTED_TURN_ERROR = "Turn interrupted by server restart. Please retry your message."


def _sanitize_session_title(raw: str) -> str:
    """Trim the noise LLMs love to add to short titles.

    Strips model reasoning tags, surrounding quotes, leading "Title:" labels,
    trailing punctuation, and Markdown bold/italic markers. Caps length at
    80 characters so a chatty model can't blow past the sidebar layout.
    """
    text = clean_thinking_tags(raw or "").strip()
    if not text:
        return ""
    text = text.splitlines()[0].strip()
    # Iterate until the text stops shrinking — models often nest the
    # noise (e.g. ``**Title:** "Hello"``) so a single pass leaves
    # leftover wrappers.
    for _ in range(8):
        prev = text
        text = text.lstrip("*_#- \t").rstrip("*_ \t")
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                break
        for opener, closer in _TITLE_QUOTE_PAIRS:
            if len(text) >= 2 and text.startswith(opener) and text.endswith(closer):
                text = text[len(opener) : len(text) - len(closer)].strip()
                break
        text = text.rstrip(_TITLE_TRAILING_PUNCT)
        if text == prev:
            break
    return text[:80]


def _extract_memory_references(payload: dict[str, Any]) -> list[MemoryReference]:
    """Return the L3 slot names the client opted in for this turn.

    Any non-empty list triggers ``read_l3_concat`` injection in v2 — the
    individual names are kept for forward-compat with workbench UI hints
    (e.g. "I want preferences in this turn") even though the read tool
    returns the full concat.
    """
    refs = payload.get("memory_references", []) or []
    if not isinstance(refs, list):
        return []
    allowed = {"recent", "profile", "scope", "preferences", "summary"}
    out: list[MemoryReference] = []
    for item in refs:
        if item in allowed and item not in out:
            out.append(item)
    return out


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _mastery_path_id(value: Any) -> str:
    """Normalize the optional session-to-mastery-path association."""
    return str(value or "").strip()


def _llm_selection_dict(value: Any) -> dict[str, str] | None:
    from deeptutor.services.model_selection import LLMSelection

    selection = LLMSelection.from_payload(value)
    return selection.to_dict() if selection else None


# ---------------------------------------------------------------------------
# Subject scope (C08): three-state request → one validated per-turn value
# ---------------------------------------------------------------------------
_TURN_RUNTIME_CONFIG_KEYS = (
    "_persist_user_message",
    "_regenerate",
    "_regenerated_from_message_id",
    "_superseded_turn_id",
    "followup_question_context",
    # Per-turn subagent consult budget (composer stepper). Not part of
    # any capability's public config schema, so it rides as a runtime
    # key — stripped before validation, merged back into the turn config
    # and read by the subagent capability from context.config_overrides.
    "subagent_consult_budget",
    # Subject scope (composer SubjectSelector). Same contract as the
    # budget above: stripped before capability-config validation so it
    # cannot trip ``extra="forbid"``, then merged back into the turn
    # config where _run_turn reads it for the M5 context injection.
    "subject_id",
)


def _validated_public_turn_config(capability: str, config: dict[str, Any]) -> dict[str, Any]:
    from deeptutor.runtime.request_contracts import validate_capability_config

    public = {key: value for key, value in config.items() if key not in _TURN_RUNTIME_CONFIG_KEYS}
    try:
        return validate_capability_config(capability, public)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


#: "the caller did not mention the subject at all" — distinct from every value
#: (including ``None``, which explicitly clears it).
_SUBJECT_ABSENT = object()


def _payload_subject_id(payload: dict[str, Any]) -> str | None:
    """The already-resolved subject of a turn payload — never re-derived.

    ``start_turn`` validates the request and writes the resolved value (a slug or
    ``None``) onto the payload; every later reader — the snapshot, the running
    metadata, the context injection — takes that value verbatim. There is no
    ``or`` fallback here: an explicit ``None`` must not be replaced by whatever
    the session preference happens to be now.
    """
    if not isinstance(payload, dict):  # pragma: no cover - defensive
        return None
    if "subject_id" in payload:
        value = payload.get("subject_id")
    else:
        config = payload.get("config")
        value = config.get("subject_id") if isinstance(config, dict) else None
    return _subject_value(value)


def _snapshot_subject(snapshot: dict[str, Any]) -> Any:
    """The subject recorded in a stored request snapshot.

    A snapshot written before this stage has no scope key at all: that is
    "unrecorded", not "the current preference" (C08), so it regenerates without a
    subject. A recorded ``None``/``""`` is an explicit clear and is kept.
    """
    if not isinstance(snapshot, dict):
        return _SUBJECT_ABSENT
    for key in ("subject_id", "subjectId"):
        if key in snapshot:
            return snapshot.get(key)
    return _SUBJECT_ABSENT


#: Upper bound on the per-turn subject-KB warnings carried in the context and in
#: the persisted DONE metadata (a broken subject cannot flood the turn envelope).
_MAX_KB_WARNINGS = 20


def mount_turn_knowledge_bases(
    explicit_refs: Sequence[Any] | None, subject_id: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    """This turn's KB mount set and the degradations that kept one out (C08).

    The mounted set is the user's explicit references **plus every ready KB of
    the current subject** — stable, deduplicated, server-resolved. Nothing is
    invented: an empty subject or an empty selection mounts nothing (no default
    global library is appended), and a reference that cannot be used is either a
    visible refusal (explicit scope/authorization problem) or a bounded warning
    (a subject library that is simply not ready yet).

    Storage corruption/IO is never downgraded to "the subject has no libraries":
    those errors propagate with their fixed C02 projection.
    """
    from deeptutor.subjects import kb_scope
    from deeptutor.subjects.errors import ErrorCode, SubjectOperationError

    explicit: list[str] = []
    for item in explicit_refs or []:
        ref = str(item or "").strip()
        if ref and ref not in explicit:
            explicit.append(ref)

    candidates = list(explicit)
    if subject_id:
        for name in kb_scope.subject_kb_names(subject_id):
            ref = kb_scope.encode_subject_kb_ref(subject_id, name)
            if ref not in candidates:
                candidates.append(ref)

    mounted: list[str] = []
    warnings: list[dict[str, Any]] = []
    for ref in candidates:
        try:
            resolved = kb_scope.resolve_kb_ref(
                ref,
                expected_subject_id=subject_id,
                mounted_refs=candidates,
                require_ready=True,
            )
        except SubjectOperationError as exc:
            if ref in explicit and exc.code is not ErrorCode.KB_NOT_READY:
                # An explicit reference the learner cannot use is a refusal, not
                # a silent drop: mounting something else instead is exactly the
                # fallback C08 forbids.
                raise
            if len(warnings) < _MAX_KB_WARNINGS:
                warnings.append(
                    {
                        "kb_ref": ref[:200],
                        "status": _kb_status_hint(subject_id, ref, exc),
                        "code": exc.code.value,
                        "message": exc.message,
                    }
                )
            continue
        if resolved.kb_ref not in mounted:
            mounted.append(resolved.kb_ref)
    if warnings:
        logger.warning(
            "subject knowledge bases not mounted: %s",
            [item["kb_ref"] for item in warnings],
        )
    return mounted, warnings


def _kb_status_hint(subject_id: str | None, ref: str, exc: "SubjectOperationError") -> str:
    """The projected status behind a mount warning (never a guessed "ready")."""
    from deeptutor.subjects import kb_scope
    from deeptutor.subjects.errors import SubjectOperationError, SubjectStorageError

    decoded = None
    try:
        decoded = kb_scope.decode_subject_kb_ref(ref)
    except SubjectOperationError:  # pragma: no cover - ref came from our own codec
        decoded = None
    if decoded is None or subject_id is None or decoded[0] != subject_id:
        return "unavailable"
    try:
        return kb_scope.subject_kb_warning_status(decoded[0], decoded[1])
    except SubjectStorageError:  # pragma: no cover - defensive; caller re-raises
        return "unavailable"


def _subject_value(value: Any) -> str | None:
    """Normalize one request value: ``None``/``""`` mean "no subject"."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if not isinstance(value, str):
        from deeptutor.subjects import json_store

        raise json_store.invalid_input("科目标识必须是字符串")
    return value


def _same_raw_subject(left: Any, right: Any) -> bool:
    """Whether two explicit carriers are the *same* raw request.

    Only the value itself decides: no normalisation, no truthiness, and a
    non-string never equals a string. (``None`` and ``None`` are the same
    explicit clear; ``None`` and ``""`` are not.)
    """
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    return left is right or left == right


def _requested_subject(payload: dict[str, Any], raw_config: dict[str, Any]) -> Any:
    """The explicit request state: a value, ``None`` (clear) or "absent".

    Both carrier positions are accepted (top-level for SDK/direct callers,
    ``config`` for the composer) and compared **as given**: when both are present
    they must be the same request, otherwise the turn is rejected as
    ``invalid_input`` instead of one silently winning.
    """
    from deeptutor.subjects import json_store

    top = payload.get("subject_id") if "subject_id" in payload else _SUBJECT_ABSENT
    nested = raw_config.get("subject_id") if "subject_id" in raw_config else _SUBJECT_ABSENT
    if top is not _SUBJECT_ABSENT and nested is not _SUBJECT_ABSENT:
        # Compared **as given**: ``null`` vs ``""`` and ``""`` vs ``"   "`` are
        # different requests, not two spellings of "clear". Normalising first
        # would hide exactly the conflict this check exists to surface.
        if not (_same_raw_subject(top, nested)):
            raise json_store.invalid_input("科目参数在两个位置不一致")
        chosen = top
    else:
        chosen = top if top is not _SUBJECT_ABSENT else nested
    if chosen is _SUBJECT_ABSENT:
        return _SUBJECT_ABSENT
    return _subject_value(chosen)


def resolve_subject_scope(requested: Any, stored: Any, *, validate: bool = True) -> str | None:
    """Turn the three-state request plus the session preference into one value.

    Omitted keeps the session's stored subject (including its ``None``), an
    explicit ``None``/``""`` clears it, and a non-empty value must be a valid
    subject slug that exists for the **current user**. A stored preference that is
    no longer valid is not silently repaired either — it fails with
    ``subject_not_found`` so the learner sees why the turn was refused (C08).
    """
    if requested is not _SUBJECT_ABSENT:
        value = _subject_value(requested)
    else:
        value = _subject_value(stored)
    if value is None or not validate:
        return value
    from deeptutor.subjects import json_store, store
    from deeptutor.subjects.errors import ErrorCode, subject_error

    if not store.is_valid_subject_id(value):
        raise json_store.invalid_input("科目标识非法")
    if store.get_subject(value) is None:
        raise subject_error(ErrorCode.SUBJECT_NOT_FOUND)
    return value


def _request_snapshot_metadata(
    *,
    payload: dict[str, Any],
    content: str,
    capability: str,
    config: dict[str, Any],
    attachments: list[dict[str, Any]],
    notebook_references: list[Any],
    history_references: list[Any],
    question_notebook_references: list[Any],
    book_references: list[Any],
    persona: str,
    memory_references: Sequence[str],
    llm_selection: dict[str, str] | None,
) -> dict[str, Any]:
    """Persist the front-end context chips with the user message.

    ``subject_id`` belongs to the snapshot (C08): it is the value this turn was
    validated with, and "no subject" is stored as an explicit ``None`` rather
    than dropped, so a retry can tell it apart from a turn whose scope was simply
    never recorded.
    """
    snapshot: dict[str, Any] = {
        "content": content,
        "capability": capability,
        "enabledTools": _string_list(payload.get("tools")),
        "knowledgeBases": _string_list(payload.get("knowledge_bases")),
        "language": str(payload.get("language", "en") or "en"),
        "subject_id": _payload_subject_id(payload),
    }
    if attachments:
        snapshot["attachments"] = attachments
    if config:
        snapshot["config"] = dict(config)
    if notebook_references:
        snapshot["notebookReferences"] = notebook_references
    if history_references:
        snapshot["historyReferences"] = history_references
    if question_notebook_references:
        snapshot["questionNotebookReferences"] = question_notebook_references
    if book_references:
        snapshot["bookReferences"] = book_references
    mastery_path_id = _mastery_path_id(payload.get("mastery_path_id"))
    if mastery_path_id:
        snapshot["masteryPathId"] = mastery_path_id
    if persona:
        snapshot["persona"] = persona
    if memory_references:
        snapshot["memoryReferences"] = memory_references
    if llm_selection:
        snapshot["llmSelection"] = llm_selection
    reasoning_override = payload.get("reasoning_override")
    if isinstance(reasoning_override, dict):
        snapshot["reasoningOverride"] = dict(reasoning_override)
    reasoning_snapshot = payload.get("_reasoning_snapshot")
    if isinstance(reasoning_snapshot, dict):
        snapshot["reasoning"] = dict(reasoning_snapshot)
    return {"request_snapshot": snapshot}


def _format_question_bank_entry(entry: dict[str, Any]) -> str:
    """Render a single Question Bank entry as a structured Markdown block."""
    lines: list[str] = []
    title = str(entry.get("session_title", "") or "Untitled session")
    difficulty = str(entry.get("difficulty", "") or "").strip()
    qtype = str(entry.get("question_type", "") or "").strip()
    is_correct = bool(entry.get("is_correct"))

    badges: list[str] = []
    if qtype:
        badges.append(qtype)
    if difficulty:
        badges.append(difficulty)
    badges.append("correct" if is_correct else "incorrect")
    badge_text = " · ".join(badges)

    lines.append(f"### Question (from {title}) [{badge_text}]")
    lines.append(_clip_text(str(entry.get("question", "") or ""), limit=2000))

    options = entry.get("options") or {}
    if isinstance(options, dict) and options:
        lines.append("")
        lines.append("**Options:**")
        for key in sorted(options.keys()):
            lines.append(f"- {key}. {options[key]}")

    user_answer = str(entry.get("user_answer", "") or "").strip()
    correct_answer = str(entry.get("correct_answer", "") or "").strip()
    if user_answer:
        lines.append("")
        lines.append(f"**User's Answer:** {_clip_text(user_answer, limit=1000)}")
    if correct_answer:
        lines.append(f"**Reference Answer:** {_clip_text(correct_answer, limit=1500)}")

    explanation = str(entry.get("explanation", "") or "").strip()
    if explanation:
        lines.append("")
        lines.append("**Explanation:**")
        lines.append(_clip_text(explanation, limit=2000))

    return "\n".join(lines)


async def _count_branch_user_turns(
    store: SessionStoreProtocol,
    session_id: str,
    leaf_message_id: int | None,
) -> int:
    """Count user messages on the active branch's ancestor chain.

    Used by the chat source inventory to assign ``first_seen_turn`` for
    *fresh* sources (= current turn = past_user_turns + 1). When
    ``leaf_message_id`` is ``None`` (legacy linear append) all messages
    in the session are counted; otherwise we walk the
    ``parent_message_id`` chain so sibling branches don't inflate the
    count. Kept tiny and protocol-only (``get_messages``) so it stays
    compatible with every store backend.
    """
    all_msgs = await store.get_messages(session_id)
    if leaf_message_id is None:
        return sum(1 for m in all_msgs if m.get("role") == "user")
    by_id: dict[int, dict[str, Any]] = {}
    for m in all_msgs:
        mid = m.get("id")
        if mid is not None:
            by_id[int(mid)] = m
    count = 0
    current: int | None = int(leaf_message_id)
    safety = 10_000
    while current is not None and safety > 0:
        m = by_id.get(int(current))
        if m is None:
            break
        if m.get("role") == "user":
            count += 1
        parent = m.get("parent_message_id")
        current = int(parent) if parent is not None else None
        safety -= 1
    return count


async def _build_question_bank_context(
    store: SessionStoreProtocol,
    entry_ids: list[Any],
) -> str:
    """Fetch the requested Question Bank entries and render them as context."""
    get_entry = getattr(store, "get_notebook_entry", None)
    if not callable(get_entry):
        return ""

    seen: set[int] = set()
    blocks: list[str] = []
    for raw in entry_ids:
        try:
            entry_id = int(raw)
        except (TypeError, ValueError):
            continue
        if entry_id in seen:
            continue
        seen.add(entry_id)
        try:
            entry = await get_entry(entry_id)
        except Exception:
            entry = None
        if not entry:
            continue
        blocks.append(_format_question_bank_entry(entry))
    return "\n\n---\n\n".join(blocks)


def _normalize_filename_list(raw: dict[str, Any]) -> list[str]:
    """Coalesce legacy single-filename and modern multi-filename inputs.

    Returns the cleaned list (possibly empty). Empty / whitespace-only
    entries are dropped, and the singular ``user_answer_image_filename``
    is honoured as a fallback so older clients still surface their
    filename in the system prompt.
    """
    candidates: list[Any] = []
    plural = raw.get("user_answer_image_filenames")
    if isinstance(plural, list):
        candidates.extend(plural)
    elif isinstance(plural, str):
        candidates.append(plural)
    legacy = raw.get("user_answer_image_filename")
    if isinstance(legacy, str) and legacy.strip():
        candidates.append(legacy)
    cleaned: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name:
            cleaned.append(name)
    return cleaned


def _extract_followup_question_context(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("followup_question_context", None)
    if not isinstance(raw, dict):
        return None

    question = str(raw.get("question", "") or "").strip()
    question_id = str(raw.get("question_id", "") or "").strip()
    if not question:
        return None

    options = raw.get("options")
    normalized_options: dict[str, str] | None = None
    if isinstance(options, dict):
        normalized_options = {
            str(key).strip().upper()[:1]: str(value or "").strip()
            for key, value in options.items()
            if str(value or "").strip()
        }

    return {
        "parent_quiz_session_id": str(raw.get("parent_quiz_session_id", "") or "").strip(),
        "question_id": question_id,
        "question": question,
        "question_type": str(raw.get("question_type", "") or "").strip(),
        "options": normalized_options,
        "correct_answer": str(raw.get("correct_answer", "") or "").strip(),
        "explanation": str(raw.get("explanation", "") or "").strip(),
        "difficulty": str(raw.get("difficulty", "") or "").strip(),
        "concentration": str(raw.get("concentration", "") or "").strip(),
        "knowledge_context": _clip_text(str(raw.get("knowledge_context", "") or "").strip()),
        "user_answer": str(raw.get("user_answer", "") or "").strip(),
        "is_correct": raw.get("is_correct"),
        # Filenames of the learner's image answers, when any were attached.
        # The bytes are sent as regular WS attachments on the first
        # follow-up turn — we just record the filenames here so the system
        # prompt can tell the LLM *what* those attached images actually
        # are. Accept both the legacy single ``user_answer_image_filename``
        # string and the new ``user_answer_image_filenames`` list.
        "user_answer_image_filenames": _normalize_filename_list(raw),
        # Most recent AI-judge output the learner saw, if they ran the
        # judge. Forwarded so the follow-up tutor can build on the same
        # assessment rather than starting fresh.
        "ai_judgment": _clip_text(str(raw.get("ai_judgment", "") or "").strip()),
    }


def _extract_persist_user_message(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return True
    raw = config.pop("_persist_user_message", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"false", "0", "no"}
    return bool(raw)


def _extract_regenerate_flag(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    raw = config.pop("_regenerate", False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes"}
    return bool(raw)


def _format_followup_question_context(context: dict[str, Any], language: str = "en") -> str:
    options = context.get("options") or {}
    option_lines = []
    if isinstance(options, dict) and options:
        for key, value in options.items():
            if value:
                option_lines.append(f"{key}. {value}")
    correctness = context.get("is_correct")
    correctness_text = (
        "correct" if correctness is True else "incorrect" if correctness is False else "unknown"
    )

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在处理一道测验题的后续追问。",
            "下面是本题上下文，请在后续回答中优先围绕这道题进行解释、纠错、延展和追问。",
            "如果用户提出超出本题的内容，也可以正常回答，但要保持和本题的连续性。",
            "",
            "[Question Follow-up Context]",
            f"Question ID: {context.get('question_id') or '(none)'}",
            f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
            f"Question type: {context.get('question_type') or '(none)'}",
            f"Difficulty: {context.get('difficulty') or '(none)'}",
            f"Concentration: {context.get('concentration') or '(none)'}",
            "",
            "Question:",
            context.get("question") or "(none)",
        ]
        if option_lines:
            lines.extend(["", "Options:", *option_lines])
        lines.extend(
            [
                "",
                f"User answer: {context.get('user_answer') or '(not provided)'}",
                f"User result: {correctness_text}",
                f"Reference answer: {context.get('correct_answer') or '(none)'}",
                "",
                "Explanation:",
                context.get("explanation") or "(none)",
            ]
        )
        image_filenames = context.get("user_answer_image_filenames") or []
        if isinstance(image_filenames, list) and image_filenames:
            filename_text = "、".join(image_filenames)
            count_text = f"{len(image_filenames)} 张" if len(image_filenames) > 1 else "一张"
            lines.extend(
                [
                    "",
                    "学习者作答附图：",
                    f"该作答共附了{count_text}图片（文件名：{filename_text}），"
                    f"随首条追问消息一起发送，是用户提交的作答内容的一部分，不是无关上下文。"
                    f"请结合图片中的文字/公式/草图进行解读，并将其视为对上面 “User answer” 文本的补充。",
                ]
            )
        ai_judgment = context.get("ai_judgment")
        if ai_judgment:
            lines.extend(
                [
                    "",
                    "AI 评判（之前已对学习者作答给出的评判，请基于此继续，不要重复完整重写）：",
                    ai_judgment,
                ]
            )
        if context.get("knowledge_context"):
            lines.extend(
                [
                    "",
                    "Knowledge context:",
                    context["knowledge_context"],
                ]
            )
        return "\n".join(lines).strip()

    lines = [
        "You are handling follow-up questions about a single quiz item.",
        "Use the question context below as the primary grounding for future turns in this session.",
        "If the user asks something broader, you may answer normally, but maintain continuity with this quiz item.",
        "",
        "[Question Follow-up Context]",
        f"Question ID: {context.get('question_id') or '(none)'}",
        f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
        f"Question type: {context.get('question_type') or '(none)'}",
        f"Difficulty: {context.get('difficulty') or '(none)'}",
        f"Concentration: {context.get('concentration') or '(none)'}",
        "",
        "Question:",
        context.get("question") or "(none)",
    ]
    if option_lines:
        lines.extend(["", "Options:", *option_lines])
    lines.extend(
        [
            "",
            f"User answer: {context.get('user_answer') or '(not provided)'}",
            f"User result: {correctness_text}",
            f"Reference answer: {context.get('correct_answer') or '(none)'}",
            "",
            "Explanation:",
            context.get("explanation") or "(none)",
        ]
    )
    image_filenames = context.get("user_answer_image_filenames") or []
    if isinstance(image_filenames, list) and image_filenames:
        joined = ", ".join(image_filenames)
        plural = "images were" if len(image_filenames) > 1 else "image was"
        plural_noun = (
            "Learner answer images" if len(image_filenames) > 1 else "Learner answer image"
        )
        lines.extend(
            [
                "",
                f"{plural_noun}:",
                f"{len(image_filenames)} {plural} attached to the first follow-up message "
                f"(filenames: {joined}). They are part of the learner's answer — read their "
                "text/formulas/sketches and treat them as a supplement to the typed `User answer` "
                "above, not unrelated context.",
            ]
        )
    ai_judgment = context.get("ai_judgment")
    if ai_judgment:
        lines.extend(
            [
                "",
                "Prior AI judgment (already shown to the learner — build on it instead of restating it in full):",
                ai_judgment,
            ]
        )
    if context.get("knowledge_context"):
        lines.extend(
            [
                "",
                "Knowledge context:",
                context["knowledge_context"],
            ]
        )
    return "\n".join(lines).strip()


@dataclass
class _LiveSubscriber:
    queue: asyncio.Queue[dict[str, Any]]


@dataclass
class _TurnExecution:
    turn_id: str
    session_id: str
    capability: str
    payload: dict[str, Any]
    task: asyncio.Task[None] | None = None
    # True while the turn is parked inside ``ask_user`` waiting for a learner
    # reply. Such a turn holds its resources (notably a mastery path lease)
    # but is doing no work, so another turn may take over from it.
    awaiting_user_reply: bool = False
    subscribers: list[_LiveSubscriber] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    next_seq: int = 1
    flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    events_persisted: bool = False
    persisted_events: list[dict[str, Any]] = field(default_factory=list)
    events_flushed: bool = False


class TurnRuntimeManager:
    """Run one turn in the background and multiplex persisted/live events."""

    def __init__(self, store: SessionStoreProtocol | None = None) -> None:
        from deeptutor.services.session import get_session_store

        self.store = store or get_session_store()
        self._lock = asyncio.Lock()
        self._executions: dict[str, _TurnExecution] = {}
        # Per-turn reply queues used by tools that pause the agentic
        # loop (e.g. ``ask_user``). Queue is created in ``_run_turn``
        # before the orchestrator is invoked and cleaned up in the
        # ``finally`` block, so callers of ``submit_user_reply`` see
        # ``False`` for any turn that is no longer awaiting input.
        # Each entry is a dict of shape:
        #   {"text": str, "answers": list[{"questionId": str, "text": str}] | None}
        # ``text`` is always present (flat fallback for legacy callers);
        # ``answers`` carries the structured per-question replies when the
        # frontend sends the v2 ``ask_user`` shape.
        self._reply_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}

    async def has_live_execution(self, turn_id: str) -> bool:
        """Public check for whether this process still owns the turn's runner.

        Lets transport callers (e.g. the unified WS router) avoid reaching into
        ``_lock`` / ``_executions`` directly.
        """
        return await self._has_live_execution(turn_id)

    async def _has_live_execution(self, turn_id: str) -> bool:
        """Whether this process still owns the turn's in-memory runner."""
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is None:
                return False
            # Some tests and pause/resubscribe paths create an execution
            # placeholder without a task. Treat its presence as live so we do
            # not falsely fail a turn that is still owned by this process.
            return execution.task is None or not execution.task.done()

    async def _fail_orphan_running_turn(self, turn: dict[str, Any] | None) -> dict[str, Any] | None:
        """Finalize a persisted running turn that has no local execution.

        Running turns are process-local: after a server/container restart the
        database row may still say ``running`` while the task and subscriber
        queues are gone. The runtime owns that liveness check, not the store,
        so recovery stays backend-agnostic.
        """
        if turn is None or str(turn.get("status") or "") != "running":
            return turn
        turn_id = str(turn.get("id") or turn.get("turn_id") or "").strip()
        if not turn_id or await self._has_live_execution(turn_id):
            return turn
        await self.store.update_turn_status(turn_id, "failed", _INTERRUPTED_TURN_ERROR)
        return await self.store.get_turn(turn_id)

    async def _recover_orphan_running_turns_for_session(self, session_id: str) -> None:
        """Clear stale active turns before creating a fresh turn."""
        for turn in await self.store.list_active_turns(session_id):
            await self._fail_orphan_running_turn(turn)

    async def _is_awaiting_user_reply(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
            return execution is not None and execution.awaiting_user_reply

    async def _release_superseded_lease(self, path_id: str, lease: MasteryPathLease) -> None:
        """Free ``lease`` when its turn can no longer be working on the path.

        Two cases release it. A turn that is no longer ``running`` (finished,
        or orphaned by a restart) is simply gone. A turn parked inside
        ``ask_user`` is alive but idle — it holds the lease for as long as the
        learner takes to answer, which may be forever. Since the posed question
        is persisted on the path itself, the arriving turn resumes exactly
        where the parked one stopped, so handing the path over loses nothing;
        the parked turn is cancelled rather than left to mutate a path it no
        longer owns. Only a turn that is actively generating keeps the lease.
        """
        from deeptutor.learning.storage import LearningStore

        leased_turn = await self._fail_orphan_running_turn(await self.store.get_turn(lease.turn_id))
        alive = leased_turn is not None and str(leased_turn.get("status") or "") == "running"
        if alive:
            if not await self._is_awaiting_user_reply(lease.turn_id):
                # Genuinely busy — leave the lease, and let the store report
                # the conflict to the caller.
                return
            await self.cancel_turn(lease.turn_id)
        # Scoped to the superseded turn id, so a lease already re-taken by
        # someone else survives.
        await asyncio.to_thread(
            LearningStore().release_path_lease,
            path_id,
            turn_id=lease.turn_id,
        )

    async def _acquire_mastery_path_lease(
        self,
        *,
        path_id: str,
        session_id: str,
        turn_id: str,
        owns_path: bool,
    ) -> None:
        """Bind a session to its path and take over from any superseded turn."""
        from deeptutor.learning.storage import LearningStore, PathLeaseConflictError

        learning_store = LearningStore()
        await asyncio.to_thread(
            learning_store.bind_session,
            path_id,
            session_id,
            owns_path=owns_path,
        )
        lease = await asyncio.to_thread(learning_store.get_path_lease, path_id)
        if lease is not None and lease.turn_id != turn_id and lease.session_id != "__path_api__":
            await self._release_superseded_lease(path_id, lease)
        try:
            await asyncio.to_thread(
                learning_store.acquire_path_lease,
                path_id,
                session_id,
                turn_id,
            )
        except PathLeaseConflictError as exc:
            raise RuntimeError(
                "mastery_path_busy: "
                f"path {path_id!r} is already active in session {exc.lease.session_id!r}"
            ) from exc

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        capability = str(payload.get("capability") or "chat")
        # Formal per-turn reasoning contract: shape first (no session/turn row
        # yet), then authorise the model below before resolving a level.
        from deeptutor.runtime.request_contracts import validate_reasoning_override

        reasoning_override_explicit = "reasoning_override" in payload
        try:
            reasoning_override = validate_reasoning_override(
                payload.get("reasoning_override")
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        payload = {**payload, "reasoning_override": reasoning_override}
        if not payload.get("language"):
            from deeptutor.services.settings.interface_settings import (
                get_response_language,
            )

            payload = {**payload, "language": get_response_language(default="en")}
        raw_config = dict(payload.get("config", {}) or {})
        runtime_only_keys = _TURN_RUNTIME_CONFIG_KEYS
        runtime_only_config = {
            key: raw_config.pop(key) for key in runtime_only_keys if key in raw_config
        }
        # Subject scope (C08) is parsed here, before any session is created, any
        # turn row exists or any preference is written: a conflicting or
        # malformed request must not leave a half-created turn behind.
        requested_subject = _requested_subject(payload, runtime_only_config)
        validated_public_config = _validated_public_turn_config(capability, raw_config)
        payload = {
            **payload,
            "capability": capability,
            "config": {**validated_public_config, **runtime_only_config},
        }
        session = await self.store.ensure_session(payload.get("session_id"))
        preferences = session.get("preferences") or {}
        # Resolve the three states (omitted / explicit clear / explicit value)
        # against this session's stored scope and prove the subject exists for
        # the current user. ``None`` is a real resolved value, not "missing".
        subject_id = resolve_subject_scope(requested_subject, (preferences or {}).get("subject_id"))
        # Resolve this turn's knowledge-base mount set now, before a turn row
        # exists: an explicit reference the learner may not use (unknown,
        # foreign subject, ambiguous bare name) must be refused, not silently
        # replaced by a same-named library. Libraries that are merely not ready
        # yet are reported as bounded warnings instead (see the helper).
        mounted_knowledge_bases, subject_kb_warnings = mount_turn_knowledge_bases(
            payload.get("knowledge_bases"), subject_id
        )
        payload = {
            **payload,
            "subject_id": subject_id,
            "config": {**(payload.get("config") or {}), "subject_id": subject_id},
            # The mount result is part of the validated request; ``_run_turn``
            # consumes it verbatim instead of re-deriving a second set.
            "_mounted_knowledge_bases": mounted_knowledge_bases,
            "_subject_kb_warnings": subject_kb_warnings,
        }
        # A mastery path has a longer lifetime than any one conversation.
        # Persist the explicit association on the session, and restore it on
        # later turns whose frontend payload omits the field.
        mastery_path_explicit = "mastery_path_id" in payload
        configured_mastery_path_id = _mastery_path_id(
            payload.get("mastery_path_id")
            if mastery_path_explicit
            else preferences.get("mastery_path_id")
        )
        mastery_binding = None
        if capability == "mastery_path":
            from deeptutor.learning.identity import resolve_mastery_path_binding

            mastery_binding = resolve_mastery_path_binding(
                configured_path_id=configured_mastery_path_id,
                book_references=payload.get("book_references", []),
                session_id=session["id"],
            )
            mastery_path_id = mastery_binding.path_id
        else:
            mastery_path_id = configured_mastery_path_id
        payload = {**payload, "mastery_path_id": mastery_path_id}
        # Persona is a session-level preference (mirrors llm_selection): an
        # explicit ``persona`` key in the payload — including an empty string,
        # which means "Default" / no persona — wins and is persisted below; an
        # absent key falls back to the session's stored preference so the
        # active persona survives reloads and follows the session.
        persona_explicit = "persona" in payload
        persona_pref = str(
            (payload.get("persona") if persona_explicit else preferences.get("persona")) or ""
        ).strip()
        payload = {**payload, "persona": persona_pref}
        raw_llm_selection = payload.get("llm_selection")
        if raw_llm_selection is None:
            raw_llm_selection = preferences.get("llm_selection")
        try:
            llm_selection = _llm_selection_dict(raw_llm_selection)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if llm_selection:
            try:
                from deeptutor.multi_user.model_access import apply_allowed_llm_selection

                llm_selection = apply_allowed_llm_selection(llm_selection) or {}
            except PermissionError as exc:
                raise RuntimeError(str(exc)) from exc
        else:
            # Non-admin users MUST end up with a concrete llm_selection so we
            # never silently fall through to the global LLM client (which is
            # configured from admin runtime settings). Admin keeps the existing behavior
            # (None llm_selection → default config from admin scope).
            from deeptutor.multi_user.context import get_current_user
            from deeptutor.multi_user.model_access import (
                has_capability_access,
                redacted_model_access,
            )

            current_user = get_current_user()
            if not current_user.is_admin:
                # Single gate, shared with the frontend lock and any HTTP
                # surface: no usable LLM grant → a clear terminal error here
                # instead of a silent fall-through to the global client.
                if not has_capability_access("llm"):
                    raise RuntimeError(
                        "No LLM model is assigned to your account. Please contact an administrator."
                    )
                # Pin the first granted-and-available model as the selection.
                assigned_llms = [
                    item
                    for item in redacted_model_access(current_user.id).get("llm", [])
                    if item.get("available")
                ]
                llm_selection = {
                    "profile_id": assigned_llms[0].get("profile_id"),
                    "model_id": assigned_llms[0].get("model_id"),
                }
        from deeptutor.multi_user.personal_models import merge_personal_llm_profiles
        from deeptutor.services.config import get_model_catalog_service
        from deeptutor.services.model_selection import (
            LLMSelection,
            apply_llm_selection_to_catalog,
        )

        # Personal (owner-bound) profiles live in the user's own catalog, so
        # every resolution below uses the same merged view the runtime does.
        selection_catalog = merge_personal_llm_profiles(get_model_catalog_service().load())
        if llm_selection:
            try:
                apply_llm_selection_to_catalog(
                    selection_catalog,
                    LLMSelection.from_payload(llm_selection),
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc

        # Authorise the model first, then resolve its capability and validate
        # the requested strength.  No shared catalog/default is written.
        from deeptutor.services.llm.reasoning_controls import (
            controls_for_catalog_selection,
            resolve_turn_reasoning,
        )

        reasoning_controls, reasoning_model, reasoning_profile = (
            controls_for_catalog_selection(selection_catalog, llm_selection)
        )
        model_default_effort = (
            str((reasoning_model or {}).get("reasoning_effort") or "").strip() or None
        )
        try:
            reasoning_resolution = resolve_turn_reasoning(
                reasoning_controls,
                model_default=model_default_effort,
                mode=str(reasoning_override.get("mode") or "inherit"),
                effort=reasoning_override.get("effort"),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        resolved_profile_id = (
            (llm_selection or {}).get("profile_id")
            or (reasoning_profile or {}).get("id")
            or ""
        )
        resolved_model_id = (
            (llm_selection or {}).get("model_id")
            or (reasoning_model or {}).get("id")
            or ""
        )
        payload = {
            **payload,
            "_reasoning_effective": reasoning_resolution.scoped_effort,
            "_reasoning_protocol": (
                reasoning_controls.wire
                if reasoning_controls.supported is True
                and reasoning_resolution.scoped_effort is not None
                and not str(reasoning_resolution.scoped_effort).startswith("__")
                else "none"
            ),
            "_reasoning_snapshot": {
                **reasoning_resolution.snapshot,
                "profile_id": resolved_profile_id,
                "model_id": resolved_model_id,
            },
        }
        reasoning_preference_key = (
            f"{resolved_profile_id}:{resolved_model_id}"
            if resolved_profile_id and resolved_model_id
            else ""
        )
        # If the caller didn't pin a per-turn tool list (e.g. non-web
        # channels or the new web UI which sources tools from
        # /settings/tools), back-fill from the user's saved toggleable-tool
        # preference so the chat pipeline sees the same set the user picked
        # in Settings. Callers that explicitly pass ``tools`` (including
        # an empty list) keep their value untouched.
        if payload.get("tools") is None:
            try:
                from deeptutor.api.routers.settings import get_enabled_optional_tools

                payload = {**payload, "tools": list(get_enabled_optional_tools())}
            except Exception:
                payload = {**payload, "tools": []}
        # Admin-imposed per-user tool whitelist (grant v2). Sits after the
        # back-fill so explicit caller lists and settings defaults pass the
        # same gate; this is the single enforcement point for every
        # capability's turn.
        from deeptutor.multi_user.tool_access import allowed_optional_tools

        allowed_tools = allowed_optional_tools()
        if allowed_tools is not None:
            payload = {
                **payload,
                "tools": [t for t in (payload.get("tools") or []) if t in allowed_tools],
            }
        payload = {**payload, "llm_selection": llm_selection}
        await self._recover_orphan_running_turns_for_session(session["id"])
        preference_update: dict[str, Any] = {
            "capability": capability,
            "tools": list(payload.get("tools") or []),
            "knowledge_bases": list(payload.get("knowledge_bases") or []),
            "language": str(payload.get("language") or "en"),
            # The resolved scope is persisted as-is, including an explicit
            # ``None``: clearing the subject on one turn must survive the next
            # payload that omits the field (C08), and a later turn must never
            # inherit a scope this turn did not use.
            "subject_id": subject_id,
        }
        if llm_selection:
            preference_update["llm_selection"] = llm_selection
        if persona_explicit:
            # Persist explicit set AND explicit clear ("" = back to Default).
            preference_update["persona"] = persona_pref
        if mastery_path_explicit or mastery_binding is not None:
            # Mastery turns persist their fully resolved path so a later turn
            # cannot silently fall back to a different aggregate.
            preference_update["mastery_path_id"] = mastery_path_id
        if reasoning_override_explicit and reasoning_preference_key:
            existing_reasoning_prefs = (
                preferences.get("reasoning_preferences")
                if isinstance(preferences.get("reasoning_preferences"), dict)
                else {}
            )
            preference_update["reasoning_preferences"] = {
                **existing_reasoning_prefs,
                reasoning_preference_key: reasoning_override,
            }
        await self.store.update_session_preferences(session["id"], preference_update)
        turn = await self.store.create_turn(session["id"], capability=capability)
        execution = _TurnExecution(
            turn_id=turn["id"],
            session_id=session["id"],
            capability=capability,
            payload=dict(payload),
        )
        # Publish an ownership marker before trying to recover another path
        # lease. Two start_turn calls can otherwise interleave after the first
        # turn row is created but before its task is registered, causing the
        # second caller to misclassify that healthy turn as a restart orphan.
        async with self._lock:
            self._executions[turn["id"]] = execution
        mastery_lease_acquired = False
        if mastery_binding is not None:
            try:
                await self._acquire_mastery_path_lease(
                    path_id=mastery_binding.path_id,
                    session_id=session["id"],
                    turn_id=turn["id"],
                    owns_path=mastery_binding.owned_by_session,
                )
                mastery_lease_acquired = True
            except Exception as exc:
                async with self._lock:
                    self._executions.pop(turn["id"], None)
                with contextlib.suppress(Exception):
                    await self.store.update_turn_status(turn["id"], "rejected", str(exc))
                raise
            persisted_turn = await self.store.get_turn(turn["id"])
            if persisted_turn is None or persisted_turn.get("status") != "running":
                # An administrative reset/delete can cancel the placeholder
                # while lease acquisition is in flight. Never launch a task
                # after that cancellation has already become durable.
                from deeptutor.learning.storage import LearningStore

                async with self._lock:
                    self._executions.pop(turn["id"], None)
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        LearningStore().release_path_lease,
                        mastery_binding.path_id,
                        turn_id=turn["id"],
                    )
                raise RuntimeError("Mastery turn was cancelled while starting")
        session_metadata: dict[str, Any] = {
            "session_id": session["id"],
            "turn_id": turn["id"],
        }
        regenerated_from = runtime_only_config.get("_regenerated_from_message_id")
        if regenerated_from is not None:
            session_metadata["regenerated_from_message_id"] = regenerated_from
        superseded_turn_id = runtime_only_config.get("_superseded_turn_id")
        if superseded_turn_id:
            session_metadata["superseded_turn_id"] = str(superseded_turn_id)
        if runtime_only_config.get("_regenerate"):
            session_metadata["regenerate"] = True
        try:
            await self._publish_live_event(
                execution,
                StreamEvent(
                    type=StreamEventType.SESSION,
                    source="turn_runtime",
                    metadata=session_metadata,
                ),
            )
            async with self._lock:
                execution.task = asyncio.create_task(self._run_turn(execution))
        except Exception as exc:
            async with self._lock:
                self._executions.pop(turn["id"], None)
            if mastery_binding is not None and mastery_lease_acquired:
                from deeptutor.learning.storage import LearningStore

                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        LearningStore().release_path_lease,
                        mastery_binding.path_id,
                        turn_id=turn["id"],
                    )
            with contextlib.suppress(Exception):
                await self.store.update_turn_status(turn["id"], "failed", str(exc))
            raise
        return session, turn

    async def regenerate_last_turn(
        self,
        session_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Re-run the prior user message in ``session_id``.

        Deletes the trailing assistant message (if any), then dispatches a new
        turn with ``_persist_user_message=False`` and ``_regenerate=True`` so
        the runtime knows not to duplicate the user row or refresh long-term
        memory a second time. The original user message stays in place.

        The regenerated turn reuses the **original request's** subject scope
        (C08): the snapshot's value — including an explicit ``None`` — wins over
        the session's current preference, and a scope that no longer exists is
        refused *before* the assistant message, the preferences or a new turn row
        are touched. A legacy snapshot with no recorded scope regenerates as a
        turn without a subject rather than guessing the current one.
        """
        session_id = str(session_id or "").strip()
        if not session_id:
            raise RuntimeError("nothing_to_regenerate")

        session = await self.store.get_session(session_id)
        if session is None:
            raise RuntimeError("nothing_to_regenerate")

        active = await self.store.get_active_turn(session_id)
        if active is not None:
            raise RuntimeError("regenerate_busy")

        last_user = await self.store.get_last_message(session_id, role="user")
        if last_user is None:
            raise RuntimeError("nothing_to_regenerate")

        preferences = session.get("preferences") or {}
        overrides = overrides or {}
        metadata = last_user.get("metadata") or {}
        snapshot: dict[str, Any] = {}
        if isinstance(metadata, dict):
            candidate = metadata.get("request_snapshot") or metadata.get("requestSnapshot")
            if isinstance(candidate, dict):
                snapshot = candidate

        # The original request is the authority for *both* halves of the scope:
        # the subject and the libraries the learner had explicitly attached. The
        # current session preference is never borrowed — that is how a retried
        # turn silently changes which library answered it (C08).
        regenerate_subject = resolve_subject_scope(_snapshot_subject(snapshot), None)
        if overrides.get("knowledge_bases") is not None:
            knowledge_bases = list(overrides.get("knowledge_bases") or [])
        elif "knowledgeBases" in snapshot:
            knowledge_bases = _string_list(snapshot.get("knowledgeBases"))
        elif "knowledge_bases" in snapshot:
            knowledge_bases = _string_list(snapshot.get("knowledge_bases"))
        else:
            # No recorded list at all (a message from before snapshots existed):
            # there is nothing to replay, so the session's stored selection is
            # the only source — exactly how ``capability``/``tools`` behave for
            # such a message. A snapshot that *does* record the list always wins.
            knowledge_bases = _string_list(preferences.get("knowledge_bases"))

        # Validate the original scope **and the replayed mounts** before anything
        # is removed or rewritten: a deleted subject, or a library that was
        # deleted/revoked/not ready since, must surface as a visible refusal —
        # not as a turn replayed against another library, and not after the
        # previous assistant message is already gone. This also applies to the
        # effective legacy selection when no original list was recorded.
        mount_turn_knowledge_bases(knowledge_bases, regenerate_subject)
        capability = str(
            overrides.get("capability")
            or last_user.get("capability")
            or preferences.get("capability")
            or "chat"
        )
        _validated_public_turn_config(capability, dict(overrides.get("config") or {}))

        last_message = await self.store.get_last_message(session_id)
        previous_turn_id: str | None = None
        if last_message is not None and last_message.get("role") == "assistant":
            for event in last_message.get("events") or []:
                turn_id = str((event or {}).get("turn_id") or "")
                if turn_id:
                    previous_turn_id = turn_id
                    break
            await self.store.delete_message(last_message["id"])

        tools = list(
            overrides.get("tools")
            if overrides.get("tools") is not None
            else preferences.get("tools") or []
        )
        language = str(overrides.get("language") or preferences.get("language") or "en")

        config: dict[str, Any] = dict(overrides.get("config") or {})
        # The server's resolved scope is the only one this turn may carry: a
        # stale ``config.subject_id`` from the client would otherwise conflict
        # with the snapshot value validated above.
        config.pop("subject_id", None)
        config.update(
            {
                "_persist_user_message": False,
                "_regenerate": True,
                "_regenerated_from_message_id": int(last_user["id"]),
                "subject_id": regenerate_subject,
            }
        )
        if previous_turn_id:
            config["_superseded_turn_id"] = previous_turn_id
        llm_selection = (
            overrides.get("llm_selection")
            if overrides.get("llm_selection") is not None
            else snapshot.get("llmSelection") or preferences.get("llm_selection")
        )
        mastery_path_id = _mastery_path_id(
            overrides.get("mastery_path_id")
            if "mastery_path_id" in overrides
            else snapshot.get("masteryPathId") or preferences.get("mastery_path_id")
        )

        payload: dict[str, Any] = {
            "session_id": session_id,
            "capability": capability,
            "content": str(last_user.get("content", "") or ""),
            "tools": tools,
            "knowledge_bases": knowledge_bases,
            "language": language,
            "subject_id": regenerate_subject,
            "attachments": list(last_user.get("attachments") or []),
            "notebook_references": list(
                overrides.get("notebook_references")
                if overrides.get("notebook_references") is not None
                else preferences.get("notebook_references") or []
            ),
            "history_references": list(
                overrides.get("history_references")
                if overrides.get("history_references") is not None
                else preferences.get("history_references") or []
            ),
            "book_references": list(
                overrides.get("book_references")
                if overrides.get("book_references") is not None
                else snapshot.get("bookReferences") or []
            ),
            "mastery_path_id": mastery_path_id,
            "config": config,
        }
        if "reasoning_override" in overrides:
            payload["reasoning_override"] = overrides.get("reasoning_override")
        elif isinstance(snapshot.get("reasoningOverride"), dict):
            payload["reasoning_override"] = snapshot.get("reasoningOverride")
        if llm_selection:
            payload["llm_selection"] = llm_selection
        return await self.start_turn(payload)

    async def cancel_turn(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
        if execution is None or execution.task is None or execution.task.done():
            turn = await self.store.get_turn(turn_id)
            if turn is None or turn.get("status") != "running":
                return False
            await self.store.update_turn_status(turn_id, "cancelled", "Turn cancelled")
            return True
        if not execution.task.cancelling():
            execution.task.cancel()
        # A second cancel request must not interrupt the first cleanup, and
        # cancelling the transport waiter must not cancel the turn a second time.
        with CancelScope(shield=True):
            try:
                await asyncio.shield(execution.task)
            except asyncio.CancelledError:
                if not execution.task.done():
                    raise
            turn = await self.store.get_turn(turn_id)
            if turn is not None and turn.get("status") == "running":
                # A task cancelled before its first instruction never enters
                # _run_turn's exception/finally blocks.
                await self.store.update_turn_status(turn_id, "cancelled", "Turn cancelled")
                if not any(event.get("type") == "done" for event in execution.events):
                    await self._publish_live_event(
                        execution,
                        StreamEvent(
                            type=StreamEventType.DONE,
                            source=execution.capability,
                            metadata={"status": "cancelled"},
                        ),
                    )
                await self._flush_buffered_events(execution)
            if execution.task.done():
                await self._release_execution(execution)
        return True

    async def submit_user_reply(
        self,
        turn_id: str,
        text: str | None = None,
        *,
        answers: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Deliver a user reply to a turn that's paused on ``ask_user``.

        Returns ``True`` if the turn was waiting and the reply was
        accepted; ``False`` if no waiter is registered (turn finished,
        was cancelled, or the model never asked).

        Accepts either ``text`` (single free-form reply, legacy single-
        question shape) or ``answers`` (list of ``{questionId, text}``
        pairs, v2 multi-question shape). Both may be passed; the
        consumer prefers structured ``answers`` when present and falls
        back to ``text`` for the legacy case. The payload is enqueued —
        the pipeline's ``await waiter()`` call unblocks on the next
        event-loop tick and substitutes the reply into the matching
        ``role=tool`` message.
        """
        queue = self._reply_queues.get(turn_id)
        if queue is None:
            return False
        payload: dict[str, Any] = {"text": text or "", "answers": answers}
        await queue.put(payload)
        return True

    async def subscribe_turn(
        self,
        turn_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        backlog = await self.store.get_turn_events(turn_id, after_seq=after_seq)
        last_seq = after_seq
        # Track whether we ever yielded a terminal event (DONE) — if the live
        # queue ends WITHOUT one (e.g. a transient send-side stall on
        # ``safe_send`` swallowed it), we synthesise one before returning so
        # the frontend's ``isStreaming`` state clears immediately rather than
        # waiting on the 45s heartbeat-timeout + reconnect catchup path.
        done_yielded = False

        def _track(item: dict[str, Any]) -> dict[str, Any]:
            nonlocal done_yielded
            if str(item.get("type") or "") == "done":
                done_yielded = True
            return item

        for item in backlog:
            last_seq = max(last_seq, int(item.get("seq") or 0))
            yield _track(item)

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        subscriber = _LiveSubscriber(queue=queue)
        execution: _TurnExecution | None = None
        live_backlog: list[dict[str, Any]] = []
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is not None:
                execution.subscribers.append(subscriber)
                live_backlog = [
                    item for item in execution.events if int(item.get("seq") or 0) > last_seq
                ]

        for item in live_backlog:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            yield _track(item)

        catchup = []
        if execution is None:
            catchup = await self.store.get_turn_events(turn_id, after_seq=last_seq)
        for item in catchup:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            yield _track(item)

        turn = await self.store.get_turn(turn_id)
        if execution is None:
            turn = await self._fail_orphan_running_turn(turn)
            if turn is None or turn.get("status") != "running":
                # Turn already finished and we didn't see a DONE in any of the
                # persisted history above — synthesise one so the caller can
                # still close out its streaming state cleanly.
                if not done_yielded:
                    if turn is not None and str(turn.get("status") or "") == "failed":
                        error_event = self._synthesize_error_event(turn_id, turn)
                        if error_event is not None:
                            yield error_event
                    yield self._synthesize_done_event(turn_id, turn)
                return
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                seq = int(item.get("seq") or 0)
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield _track(item)
        finally:
            async with self._lock:
                execution = self._executions.get(turn_id)
                if execution is not None:
                    execution.subscribers = [
                        sub for sub in execution.subscribers if sub is not subscriber
                    ]
            # Safety net: if we drained the live queue (None sentinel arrived)
            # without ever yielding a DONE, the turn is over server-side but
            # the frontend wouldn't know. Read the persisted turn status one
            # more time and synthesise a terminal DONE only for genuinely
            # terminal turns so ``isStreaming`` clears without waiting on
            # the heartbeat-reconnect fallback. A running turn may be paused
            # on ``ask_user`` or may have had this subscription replaced; in
            # that case a synthetic DONE would falsely mark the turn
            # completed while the backend is still awaiting input.
            if not done_yielded:
                final_turn = await self.store.get_turn(turn_id)
                final_status = str((final_turn or {}).get("status") or "").strip()
                if final_turn is None or final_status in {"failed", "cancelled", "completed"}:
                    yield self._synthesize_done_event(turn_id, final_turn)

    @staticmethod
    def _synthesize_done_event(turn_id: str, turn: dict[str, Any] | None) -> dict[str, Any]:
        """Build a DONE event payload from the persisted turn status.

        Used as a recovery path when ``subscribe_turn`` finishes without
        ever observing a live or persisted DONE event for a turn that has
        nonetheless terminated server-side. Mirrors the shape of the
        events the runtime would normally publish so the frontend doesn't
        need a special code path to consume it.
        """
        status = "completed"
        error: str | None = None
        if turn is not None:
            raw_status = str(turn.get("status") or "").strip()
            if raw_status in {"failed", "cancelled", "completed"}:
                status = raw_status
            error_text = str(turn.get("error") or "").strip()
            if error_text:
                error = error_text
        metadata: dict[str, Any] = {"status": status, "synthesized": True}
        if error:
            metadata["error"] = error
        return {
            "type": "done",
            "source": "turn_runtime",
            "stage": "",
            "content": "",
            "metadata": metadata,
            "session_id": "",
            "turn_id": turn_id,
            "seq": 0,
        }

    @staticmethod
    def _synthesize_error_event(turn_id: str, turn: dict[str, Any] | None) -> dict[str, Any] | None:
        """Build a terminal ERROR event from a failed persisted turn."""
        error = str((turn or {}).get("error") or "").strip()
        if not error:
            return None
        return {
            "type": "error",
            "source": "turn_runtime",
            "stage": "",
            "content": error,
            "metadata": {"status": "failed", "synthesized": True},
            "session_id": str((turn or {}).get("session_id") or ""),
            "turn_id": turn_id,
            "seq": 0,
        }

    async def subscribe_session(
        self,
        session_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        active_turn = await self.store.get_active_turn(session_id)
        if active_turn is None:
            return
        async for item in self.subscribe_turn(active_turn["id"], after_seq=after_seq):
            yield item

    async def _run_turn(self, execution: _TurnExecution) -> None:
        payload = execution.payload
        session_id = execution.session_id
        capability_name = execution.capability
        turn_id = execution.turn_id
        attachments = []
        attachment_records = []
        assistant_events: list[dict[str, Any]] = []
        assistant_content = ""
        # Per-round content segments + narration call_ids: a chat-loop round's
        # text is captured live but a round that resolves as narration is
        # dropped from the persisted answer (mirrors the frontend bubble).
        content_segments: list[tuple[str | None, str]] = []
        narration_call_ids: set[str] = set()

        def _persisted_answer() -> str:
            # clean_thinking_tags is a second line of defence: providers that
            # inline <think> in the content channel are split at streaming
            # time by the agent loop, but anything that slips through must
            # never be persisted as the user-facing answer.
            return _assemble_persisted_answer(content_segments, narration_call_ids)

        # Files the model generated this turn (exec/code_execution artifacts),
        # persisted as assistant-message attachments so the UI shows openable
        # cards. Deduped by URL across the turn's SOURCES events.
        generated_attachments: list[dict[str, Any]] = []
        seen_artifact_urls: set[str] = set()
        stream_done_sent = False
        assistant_message_id: str | None = None
        llm_scope_token: Token[LLMConfig | None] | None = None
        reset_active_llm_selection: Callable[[Token[LLMConfig | None] | None], None] | None = None
        # One queue per turn for ``ask_user`` style pause-resume.
        # Created here (BEFORE the orchestrator runs) so the pipeline can
        # await on the awaitable we publish into ``context.metadata``.
        # Cleaned up unconditionally in the outer ``finally``.
        reply_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._reply_queues[turn_id] = reply_queue

        async def _wait_for_user_reply() -> dict[str, Any] | None:
            # Publish the pause so a turn that wants the same mastery path can
            # tell "busy generating" apart from "parked, learner walked away".
            execution.awaiting_user_reply = True
            try:
                return await reply_queue.get()
            finally:
                execution.awaiting_user_reply = False

        try:
            from deeptutor.agents.notebook import NotebookAnalysisAgent
            from deeptutor.core.context import Attachment, UnifiedContext
            from deeptutor.runtime.orchestrator import ChatOrchestrator
            from deeptutor.services.memory import get_memory_store
            from deeptutor.services.model_selection.runtime import (
                activate_llm_selection,
            )
            from deeptutor.services.model_selection.runtime import (
                reset_llm_selection as reset_active_llm_selection,
            )
            from deeptutor.services.notebook import get_notebook_manager
            from deeptutor.services.session.context_builder import ContextBuilder
            from deeptutor.services.skill import get_skill_service

            request_config = dict(payload.get("config", {}) or {})
            followup_question_context = _extract_followup_question_context(request_config)
            persist_user_message = _extract_persist_user_message(request_config)
            is_regenerate = _extract_regenerate_flag(request_config)
            request_config.pop("_regenerated_from_message_id", None)
            request_config.pop("_superseded_turn_id", None)
            raw_user_content = str(payload.get("content", "") or "")
            # Edit-branching tip: when the FE includes ``parent_message_id``
            # (even as ``null``), the new user message attaches at that
            # exact parent — creating a sibling of any existing children
            # and forcing LLM context to come from that parent's ancestor
            # chain only. When the key is absent (legacy callers), the
            # store auto-appends to the latest message in the session.
            branch_parent_explicit = "parent_message_id" in payload
            branch_parent_raw = payload.get("parent_message_id")
            branch_parent_id: int | None
            if branch_parent_explicit:
                try:
                    branch_parent_id = (
                        int(branch_parent_raw) if branch_parent_raw is not None else None
                    )
                except (TypeError, ValueError):
                    branch_parent_id = None
                    branch_parent_explicit = False
            else:
                branch_parent_id = None
            # The subject scope of this turn was resolved and validated once in
            # ``start_turn`` and written onto the payload. Reading it here is a
            # verbatim lookup (``None`` included): re-deriving it from the
            # payload/config with ``or`` would silently re-introduce the
            # preference the turn was validated against — or drop a clear.
            subject_id = _payload_subject_id(payload)
            notebook_references = payload.get("notebook_references", []) or []
            history_references = payload.get("history_references", []) or []
            question_notebook_references = payload.get("question_notebook_references", []) or []
            book_references = payload.get("book_references", []) or []
            memory_references = _extract_memory_references(payload)
            notebook_context = ""
            history_context = ""
            question_bank_context = ""
            book_context = ""

            import base64 as _b64
            import uuid as _uuid

            from deeptutor.services.storage import get_attachment_store

            for item in payload.get("attachments", []):
                record = {
                    "type": item.get("type", "file"),
                    "url": item.get("url", ""),
                    "base64": item.get("base64", ""),
                    "filename": item.get("filename", ""),
                    "mime_type": item.get("mime_type", ""),
                    "id": item.get("id", "") or _uuid.uuid4().hex[:12],
                }
                attachment_records.append(record)

            # Persist original bytes to the attachment store before extraction
            # so the frontend preview drawer can fetch the file later. The
            # extractor will clear base64 on documents to keep DB rows lean,
            # but the URL we record here outlives that pruning. Upload errors
            # are non-fatal — extraction still runs from the in-memory base64.
            attachment_store = get_attachment_store()
            for record in attachment_records:
                if record.get("url"):
                    continue  # already hosted (e.g. legacy URL)
                b64 = record.get("base64") or ""
                if not b64:
                    continue
                try:
                    raw_bytes = _b64.b64decode(b64, validate=False)
                except Exception as exc:
                    logger.warning(
                        "skipping attachment upload for %r: invalid base64 (%s)",
                        record.get("filename"),
                        exc,
                    )
                    continue
                try:
                    record["url"] = await attachment_store.put(
                        session_id=session_id,
                        attachment_id=record["id"],
                        filename=record.get("filename", "") or "file",
                        data=raw_bytes,
                        mime_type=record.get("mime_type", "") or "",
                    )
                except Exception as exc:
                    logger.warning(
                        "attachment store rejected %r: %s",
                        record.get("filename"),
                        exc,
                    )

            from deeptutor.utils.document_extractor import extract_documents_from_records

            document_texts, attachment_records = extract_documents_from_records(attachment_records)
            attachments = [
                Attachment(
                    type=r.get("type", "file"),
                    url=r.get("url", ""),
                    base64=r.get("base64", ""),
                    filename=r.get("filename", ""),
                    mime_type=r.get("mime_type", ""),
                    id=r.get("id", ""),
                    extracted_text=r.get("extracted_text", ""),
                )
                for r in attachment_records
            ]
            # DB persistence copy: drop base64 unconditionally now that the
            # original bytes live in the attachment store. Image attachments
            # used to keep base64 here (which bloated message rows); the URL
            # is now the stable source for previews.
            persisted_attachment_records = [
                {
                    **{k: v for k, v in r.items() if k != "base64"},
                    "base64": "",
                }
                for r in attachment_records
            ]

            if followup_question_context:
                existing_messages = await self.store.get_messages_for_context(
                    session_id, leaf_message_id=branch_parent_id
                )
                if not existing_messages:
                    await self.store.add_message(
                        session_id=session_id,
                        role="system",
                        content=_format_followup_question_context(
                            followup_question_context,
                            language=str(payload.get("language", "en") or "en"),
                        ),
                        capability=capability_name or "chat",
                    )

            llm_config, llm_scope_token = activate_llm_selection(
                payload.get("llm_selection"),
                reasoning_effort=payload.get("_reasoning_effective"),
                reasoning_protocol=payload.get("_reasoning_protocol"),
                apply_reasoning="_reasoning_effective" in payload,
            )
            _history_ratio = 0.35
            try:
                from deeptutor.services.settings.token_budget import (
                    get_token_budget_settings,
                )

                _budget = get_token_budget_settings()
                _history_ratio = (
                    float(_budget.get("context_ratio", 0.7))
                    if not _budget.get("enabled", True)
                    else 0.35
                )
            except Exception:
                pass
            builder = ContextBuilder(self.store, history_budget_ratio=_history_ratio)

            async def _emit_context_event(event: StreamEvent) -> None:
                if event.source in {"context", "context_builder"}:
                    return
                await self._publish_live_event(execution, event)

            history_result = await builder.build(
                session_id=session_id,
                llm_config=llm_config,
                language=payload.get("language", "en"),
                on_event=_emit_context_event,
                leaf_message_id=branch_parent_id,
            )
            memory_store = get_memory_store()
            memory_context = memory_store.read_l3_concat() if memory_references else ""

            # Persona: at most one behaviour preset per turn, eagerly
            # injected (a persona must shape the voice from the first
            # token). Resolution: the user's own workspace first; non-admin
            # users fall back to admin-authored presets (personas carry no
            # privileged workflow, so no grant gate applies).
            from deeptutor.multi_user.context import get_current_user
            from deeptutor.multi_user.paths import get_admin_path_service
            from deeptutor.multi_user.skill_access import assigned_skill_ids
            from deeptutor.services.persona import PersonaService, get_persona_service
            from deeptutor.services.skill.service import SkillService, render_skills_manifest

            current_user = get_current_user()
            requested_persona = str(payload.get("persona") or "").strip()
            persona_context = ""
            if requested_persona:
                persona_context = get_persona_service().load_for_context(requested_persona)
                if not persona_context and not current_user.is_admin:
                    persona_context = PersonaService(
                        root=get_admin_path_service().get_workspace_dir() / "personas"
                    ).load_for_context(requested_persona)
            active_persona = requested_persona if persona_context else ""

            # Skills: never user-selected per turn. The model sees a
            # one-line manifest of every skill visible to this user (own +
            # builtin, plus admin-assigned for non-admin users) and pulls
            # full content on demand via ``read_skill``. ``always`` skills
            # are the exception — their bodies are injected eagerly.
            user_skill_service = get_skill_service()
            skill_entries = user_skill_service.summary_entries()
            always_blocks = [user_skill_service.load_always_for_context()]
            if not current_user.is_admin:
                assigned_service = SkillService(
                    root=get_admin_path_service().get_workspace_dir() / "skills",
                    builtin_root=None,
                )
                allowed_skills = assigned_skill_ids(current_user.id)
                assigned_entries = [
                    e for e in assigned_service.summary_entries() if e.name in allowed_skills
                ]
                skill_entries = skill_entries + assigned_entries
                always_blocks.append(
                    assigned_service.load_for_context(
                        [e.name for e in assigned_entries if e.always and e.available]
                    )
                )
            skills_manifest = "\n\n".join(
                part for part in (*always_blocks, render_skills_manifest(skill_entries)) if part
            )

            # Chat capability uses the lightweight manifest + read_source
            # affordance (no upstream LLM call, no wholesale-dump into the
            # user message). All other capabilities keep the legacy concat
            # path because their internal pipelines consume the named blocks
            # (``[Notebook Context]`` etc.) directly.
            is_chat_capability = (capability_name or "") in {"", "chat"}

            source_manifest_text = ""
            source_index: dict[str, str] = {}

            if is_chat_capability:
                from deeptutor.services.session.source_inventory import (
                    build_inventory,
                    render_manifest,
                )

                resolved_notebook_records = (
                    get_notebook_manager().get_records_by_references(notebook_references)
                    if notebook_references
                    else []
                )
                # Current turn ordinal = (#user messages on this branch's
                # ancestor chain) + 1. ``_count_branch_user_turns`` walks
                # the same lineage the inventory builder uses, so we agree
                # on what "turn N" means for the historical labels.
                current_turn_ordinal = (
                    await _count_branch_user_turns(self.store, session_id, branch_parent_id) + 1
                )
                inventory = await build_inventory(
                    self.store,
                    session_id=session_id,
                    leaf_message_id=branch_parent_id,
                    current_turn_ordinal=current_turn_ordinal,
                    fresh_attachment_records=attachment_records,
                    fresh_notebook_records=resolved_notebook_records,
                    fresh_book_context_text=book_context,
                    fresh_book_references=book_references,
                    fresh_history_session_ids=history_references,
                    fresh_question_entry_ids=question_notebook_references,
                    language=str(payload.get("language", "en") or "en"),
                )
                source_manifest_text, source_index = render_manifest(inventory)
                effective_user_message = raw_user_content
            else:
                if notebook_references:
                    referenced_records = get_notebook_manager().get_records_by_references(
                        notebook_references
                    )
                    if referenced_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        notebook_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=referenced_records,
                            emit=_emit_context_event,
                        )

                if history_references:
                    from deeptutor.services.session.source_inventory import (
                        serialize_referenced_transcript,
                    )

                    history_records: list[dict[str, Any]] = []
                    for session_ref in history_references:
                        history_session_id = str(session_ref or "").strip()
                        if not history_session_id:
                            continue

                        history_session = await self.store.get_session(history_session_id)
                        if not history_session:
                            continue

                        history_messages = await self.store.get_messages_for_context(
                            history_session_id
                        )
                        transcript = serialize_referenced_transcript(
                            history_session,
                            history_messages,
                            language=str(payload.get("language", "en") or "en"),
                        )
                        if not transcript:
                            continue

                        history_summary = str(
                            history_session.get("compressed_summary", "") or ""
                        ).strip()
                        if not history_summary:
                            history_summary = _clip_text(
                                " ".join(
                                    str(message.get("content", "") or "").strip()
                                    for message in history_messages[-4:]
                                    if str(message.get("content", "") or "").strip()
                                ),
                                limit=400,
                            )
                        if not history_summary:
                            history_summary = f"{len(history_messages)} messages"

                        history_records.append(
                            {
                                "id": history_session_id,
                                "notebook_id": "__history__",
                                "notebook_name": "History",
                                "title": str(
                                    history_session.get("title", "") or "Untitled session"
                                ),
                                "summary": history_summary,
                                "output": transcript,
                                "metadata": {
                                    "session_id": history_session_id,
                                    "source": "history",
                                },
                            }
                        )

                    if history_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        history_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=history_records,
                            emit=_emit_context_event,
                        )
                        if not history_context.strip():
                            MAX_FALLBACK_CHARS = 8000
                            parts: list[str] = []
                            total = 0
                            for record in history_records:
                                output = record.get("output")
                                if not output:
                                    continue
                                part = f"## Session: {record.get('title', 'Untitled')}\n{output}"
                                if total + len(part) > MAX_FALLBACK_CHARS:
                                    remaining = MAX_FALLBACK_CHARS - total
                                    if remaining > 100:
                                        parts.append(part[:remaining] + "\n...(truncated)")
                                    break
                                parts.append(part)
                                total += len(part)
                            history_context = "\n\n".join(parts)

                if question_notebook_references:
                    question_bank_context = await _build_question_bank_context(
                        self.store, question_notebook_references
                    )

                effective_user_message = raw_user_content
                context_parts: list[str] = []
                if document_texts:
                    context_parts.append("[Attached Documents]\n" + "\n\n".join(document_texts))
                if book_context:
                    context_parts.append(f"[Book Context]\n{book_context}")
                if notebook_context:
                    context_parts.append(f"[Notebook Context]\n{notebook_context}")
                if history_context:
                    context_parts.append(f"[History Context]\n{history_context}")
                if question_bank_context:
                    context_parts.append(f"[Question Bank Context]\n{question_bank_context}")
                if context_parts:
                    context_parts.append(f"[User Question]\n{raw_user_content}")
                    effective_user_message = "\n\n".join(context_parts)

            conversation_history = list(history_result.conversation_history)
            conversation_context_text = history_result.context_text

            # M5: subject-scoped turns inject the lightweight context layer
            # (knowledge index + exam points + wrong book + profile).
            subject_context_tokens = 0
            subject_term = ""
            if subject_id:
                from deeptutor.subjects import store as subject_store

                subject_record = subject_store.get_subject(subject_id)
                subject_term = str((subject_record or {}).get("term") or "").strip()
                try:
                    from deeptutor.services.pdf.review_guide import estimate_tokens
                    from deeptutor.subjects import (
                        exam_points,
                        knowledge_points,
                        wrong_book,
                    )
                    from deeptutor.subjects import (
                        profile as subject_profile,
                    )

                    # The exam-point summary is term-filtered on purpose: with a
                    # term configured it only carries this term's confirmed
                    # points. Without one the historical "this term" title would
                    # be a lie, so the block is omitted (and the omission is
                    # stated) instead of falling back to the whole-subject list.
                    exam_block = (
                        exam_points.term_summary(subject_id, term=subject_term)
                        if subject_term
                        else ""
                    )
                    _blocks = [
                        knowledge_points.context_summary(subject_id),
                        exam_block,
                        wrong_book.context_summary(subject_id),
                        subject_profile.context_summary(subject_id),
                    ]
                    if not subject_term:
                        _blocks.append("（未设置学期：本轮不注入考点摘要。）")
                    _block = "\n\n".join(b for b in _blocks if b)
                    if _block:
                        subject_context_tokens = estimate_tokens(_block)
                        logger.warning(
                            "subject context injected: %d chars, ~%d tokens",
                            len(_block),
                            subject_context_tokens,
                        )
                        conversation_history.insert(0, {"role": "system", "content": _block})
                except Exception:
                    logger.warning("subject context injection failed", exc_info=True)

            # SQLite returns integer rowids; PocketBase returns its string
            # record ids. Both are opaque to this layer — they only flow into
            # ``parent_message_id`` chaining and the DONE reconcile metadata.
            new_user_message_id: int | str | None = None
            if persist_user_message:
                # Pass parent explicitly only when the FE pinned it (covers
                # both branched edits with a positive id and root edits
                # with explicit null). Otherwise let the store auto-append.
                parent_kwargs: dict[str, Any] = (
                    {"parent_message_id": branch_parent_id} if branch_parent_explicit else {}
                )
                new_user_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="user",
                    content=raw_user_content,
                    capability=capability_name,
                    attachments=persisted_attachment_records,
                    metadata=_request_snapshot_metadata(
                        payload=payload,
                        content=raw_user_content,
                        capability=capability_name,
                        config=request_config,
                        attachments=persisted_attachment_records,
                        notebook_references=notebook_references,
                        history_references=history_references,
                        question_notebook_references=question_notebook_references,
                        book_references=book_references,
                        persona=active_persona,
                        memory_references=memory_references,
                        llm_selection=payload.get("llm_selection"),
                    ),
                    **parent_kwargs,
                )

            # The KB mount set of this turn: the learner's explicit references
            # plus the current subject's ready libraries, resolved server-side.
            # ``start_turn`` already resolved and validated it for this request;
            # recomputing is only the fallback for a payload that did not pass
            # through it (never silently an empty set).
            if "_mounted_knowledge_bases" in payload:
                mounted_knowledge_bases = list(payload.get("_mounted_knowledge_bases") or [])
                subject_kb_warnings = list(payload.get("_subject_kb_warnings") or [])
            else:  # pragma: no cover - defensive; every turn goes through start_turn
                mounted_knowledge_bases, subject_kb_warnings = mount_turn_knowledge_bases(
                    payload.get("knowledge_bases"), subject_id
                )
            if subject_kb_warnings:
                logger.warning(
                    "subject knowledge base warnings for turn %s: %s",
                    turn_id,
                    [item["kb_ref"] for item in subject_kb_warnings],
                )

            context = UnifiedContext(
                session_id=session_id,
                user_message=effective_user_message,
                conversation_history=conversation_history,
                enabled_tools=payload.get("tools"),
                active_capability=payload.get("capability"),
                knowledge_bases=mounted_knowledge_bases,
                attachments=attachments,
                config_overrides=request_config,
                language=payload.get("language", "en"),
                memory_context=memory_context,
                persona_context=persona_context,
                skills_manifest=skills_manifest,
                source_manifest=source_manifest_text,
                metadata={
                    "conversation_summary": history_result.conversation_summary,
                    "conversation_context_text": conversation_context_text,
                    "history_token_count": history_result.token_count,
                    "history_budget": history_result.budget,
                    "turn_id": turn_id,
                    "question_followup_context": followup_question_context or {},
                    "notebook_references": notebook_references,
                    "history_references": history_references,
                    "question_notebook_references": question_notebook_references,
                    "book_references": book_references,
                    "mastery_path_id": _mastery_path_id(payload.get("mastery_path_id")),
                    "mastery_path_lease_managed": capability_name == "mastery_path",
                    "book_context": book_context,
                    "book_context_warnings": [],
                    "subject_id": subject_id,
                    "subject_term": subject_term,
                    "subject_context_tokens": subject_context_tokens,
                    # Subject libraries that were registered but could not be
                    # mounted this turn (not ready / unavailable). Carried in the
                    # context *and* in the persisted DONE metadata so the
                    # degradation stays verifiable after the turn.
                    "subject_kb_warnings": subject_kb_warnings,
                    "knowledge_bases_mounted": list(mounted_knowledge_bases),
                    "memory_references": memory_references,
                    "question_bank_context": question_bank_context,
                    "memory_context": memory_context,
                    "active_persona": active_persona,
                    "llm_selection": payload.get("llm_selection") or {},
                    "llm_model": str(getattr(llm_config, "model", "") or ""),
                    "llm_provider": str(getattr(llm_config, "provider_name", "") or ""),
                    # Per-turn full-text payload for read_source. Empty when
                    # the manifest is empty (non-chat capabilities, or chat
                    # turns with no attached sources). Consumed by the chat
                    # pipeline's tool kwargs injector.
                    "source_index": source_index,
                    # Pause-resume hook: the agentic chat pipeline awaits
                    # this callable when ``ask_user`` (or any other
                    # ``pause_for_user``-emitting tool) pauses the loop.
                    # The callable resolves when the frontend POSTs a
                    # reply via the ``submit_user_reply`` WS message.
                    "wait_for_user_reply": _wait_for_user_reply,
                },
            )

            orch = ChatOrchestrator()
            pending_done_event: StreamEvent | None = None
            async for event in orch.handle(context):
                if event.type == StreamEventType.SESSION:
                    continue
                if event.type == StreamEventType.DONE:
                    pending_done_event = event
                    continue
                payload_event = await self._publish_live_event(execution, event)
                if payload_event.get("type") not in {"done", "session"}:
                    assistant_events.append(payload_event)
                if _should_capture_assistant_content(event):
                    call_id = (event.metadata or {}).get("call_id")
                    content_segments.append((str(call_id) if call_id else None, event.content))
                narration_call_id = _narration_marker_call_id(event)
                if narration_call_id:
                    narration_call_ids.add(narration_call_id)
                for attachment in artifact_attachments(event):
                    if attachment["url"] not in seen_artifact_urls:
                        seen_artifact_urls.add(attachment["url"])
                        generated_attachments.append(attachment)

            # A mastery turn may have changed which path it is on
            # (``mastery_switch`` / ``mastery_leave``). The conversation's
            # stored preference already followed it; tell the open client too,
            # so what it shows as "currently mastering" is not the path the
            # turn merely started on.
            await self._publish_mastery_path_change(
                execution,
                capability_name=capability_name,
                started_on=_mastery_path_id(payload.get("mastery_path_id")),
                ended_on=str(context.metadata.get("mastery_path_id") or ""),
            )

            # Office binaries the browser cannot render need their text pulled
            # out now, while the files are still on disk, or their preview card
            # opens empty. Skipped on the cancelled path below: that one is
            # already unwinding and must not start new blocking work.
            await fill_preview_text(generated_attachments)

            # The persisted answer is the captured content minus any narration
            # rounds (their text stayed in the trace, never the answer).
            assistant_content = _persisted_answer()

            # Assistant continues the same branch as the user message it
            # answers. If we just persisted a new user row we chain off
            # that; if we did not (regenerate path) and the caller pinned a
            # parent, we use it; otherwise we let the store auto-append
            # (legacy behavior).
            if new_user_message_id is not None:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                    parent_message_id=new_user_message_id,
                )
            elif branch_parent_explicit:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                    parent_message_id=branch_parent_id,
                )
            else:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                )
            turn_status, turn_error = _resolve_turn_outcome(
                assistant_events,
                pending_done_event,
            )
            await self.store.update_turn_status(turn_id, turn_status, turn_error)
            if pending_done_event is None:
                pending_done_event = StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": turn_status},
                )
            else:
                pending_done_event.metadata = {
                    **pending_done_event.metadata,
                    "status": turn_status,
                }
            # Attach the persisted row ids so the frontend can reconcile its
            # optimistic (negative) message ids with a targeted in-place swap
            # instead of refetching and re-rendering the whole session.
            persisted_ids = {
                key: value
                for key, value in (
                    ("user_message_id", new_user_message_id),
                    ("assistant_message_id", assistant_message_id),
                )
                if value
            }
            if persisted_ids:
                pending_done_event.metadata = {**pending_done_event.metadata, **persisted_ids}
            if subject_kb_warnings:
                # Terminal envelope carries the bounded subject-KB degradation so
                # a client (and a later reviewer) sees *why* a library was not
                # mounted instead of assuming the subject was empty.
                pending_done_event.metadata = {
                    **pending_done_event.metadata,
                    "subject_kb_warnings": subject_kb_warnings,
                }
            await self._publish_live_event(execution, pending_done_event)
            stream_done_sent = True
            # DONE is part of the same persisted replay log as all preceding
            # events. Reconnects therefore observe the real terminal envelope
            # (including message ids), not a lossy synthesized substitute.
            await self._flush_buffered_events(execution)
            if not is_regenerate and turn_status == "completed":
                # Title generation is post-turn metadata. Keep it after DONE
                # so the composer and duration clock stop as soon as the
                # assistant answer is saved; the frontend keeps this socket
                # open briefly so the later ``session_meta`` title update can
                # still arrive.
                try:
                    await self._maybe_generate_session_title(
                        execution=execution,
                        session_id=session_id,
                        ui_language=str(payload.get("language", "en") or "en"),
                    )
                except Exception:
                    logger.debug("Failed to generate session title", exc_info=True)
            # Flush once every terminal/post-turn event (DONE, and the title
            # ``session_meta`` above) has been published, not before: a
            # client that reconnects after this task's ``finally`` pops
            # ``execution`` from ``_executions`` falls back entirely to this
            # persisted backlog, and ``subscribe_turn`` synthesises an
            # id-less DONE when it finds none there -- permanently orphaning
            # the just-persisted assistant reply from that client's
            # reconcile path (it can still see the message after a full
            # session reload, since the row itself is fine; only the
            # targeted in-place swap is unreachable).
            await self._flush_buffered_events(execution)
        except asyncio.CancelledError:
            with CancelScope(shield=True):
                if not stream_done_sent:
                    with contextlib.suppress(Exception):
                        await self.store.update_turn_status(turn_id, "cancelled", "Turn cancelled")
                    await self._publish_live_event(
                        execution,
                        StreamEvent(
                            type=StreamEventType.ERROR,
                            source=capability_name,
                            content="Turn cancelled",
                            metadata={"turn_terminal": True, "status": "cancelled"},
                        ),
                    )
                    await self._publish_live_event(
                        execution,
                        StreamEvent(
                            type=StreamEventType.DONE,
                            source=capability_name,
                            metadata={"status": "cancelled"},
                        ),
                    )
                with contextlib.suppress(Exception):
                    await self._flush_buffered_events(execution)
                # Best-effort: persist what the turn already produced (streamed
                # answer text, trace events, generated files) so cancelling a
                # turn does not erase visible work — files the model created are
                # on disk either way and must stay reachable. Shielded because
                # we are already unwinding a cancellation. Every step is
                # suppressed separately so the status update below always runs —
                # a turn left "running" gets mislabelled as a restart orphan.
                partial_content = _persisted_answer()
                if assistant_message_id is None and (
                    partial_content or generated_attachments or assistant_events
                ):
                    with contextlib.suppress(Exception):
                        await asyncio.shield(
                            self.store.add_message(
                                session_id=session_id,
                                role="assistant",
                                content=partial_content,
                                capability=capability_name,
                                events=assistant_events,
                                attachments=generated_attachments or None,
                            )
                        )
            raise
        except Exception as exc:
            if stream_done_sent:
                logger.error(
                    "Post-stream persistence for turn %s failed: %s",
                    turn_id,
                    exc,
                    exc_info=True,
                )
                # Suppress each step separately: a flush failure must not
                # also skip the status update, or the turn stays "running"
                # forever and gets mislabelled as a server-restart orphan.
                with contextlib.suppress(Exception):
                    await self._flush_buffered_events(execution)
                with contextlib.suppress(Exception):
                    await self.store.update_turn_status(turn_id, "failed", str(exc))
            else:
                logger.error("Turn %s failed: %s", turn_id, exc, exc_info=True)
                # A subject-layer failure (a scope or storage problem discovered
                # once the turn was already running) goes through the fixed C01
                # projection: the client sees the canonical message plus
                # ``code``/``retryable``, never the raw exception text. Every
                # other failure keeps the historical shape unchanged.
                from deeptutor.subjects.errors import (
                    SubjectOperationError,
                    SubjectStorageError,
                    map_subject_exception,
                    to_ws_error_metadata,
                )

                failure_content = str(exc)
                failure_metadata: dict[str, Any] = {
                    "turn_terminal": True,
                    "status": "failed",
                }
                if isinstance(exc, (SubjectOperationError, SubjectStorageError)):
                    mapped = map_subject_exception(exc)
                    failure_content = mapped.message
                    failure_metadata["error"] = to_ws_error_metadata(mapped)
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.ERROR,
                        source=capability_name,
                        content=failure_content,
                        metadata=failure_metadata,
                    ),
                )
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.DONE,
                        source=capability_name,
                        metadata={"status": "failed"},
                    ),
                )
                with contextlib.suppress(Exception):
                    await self._flush_buffered_events(execution)
                await self.store.update_turn_status(turn_id, "failed", str(exc))
        finally:
            # AnyIO level cancellation (for example a closing WS cancel scope)
            # must not interrupt persistence/lease release at every await.
            with CancelScope(shield=True):
                if llm_scope_token is not None and reset_active_llm_selection is not None:
                    reset_active_llm_selection(llm_scope_token)
                await self._release_execution(execution)

    async def _release_execution(self, execution: _TurnExecution) -> None:
        self._reply_queues.pop(execution.turn_id, None)
        if execution.capability == "mastery_path":
            from deeptutor.learning.storage import LearningStore

            with contextlib.suppress(Exception):
                await asyncio.shield(
                    asyncio.to_thread(LearningStore().release_leases_for_turn, execution.turn_id)
                )
        async with self._lock:
            current = self._executions.get(execution.turn_id)
            if current is execution:
                for subscriber in current.subscribers:
                    with contextlib.suppress(asyncio.QueueFull):
                        subscriber.queue.put_nowait(None)
                self._executions.pop(execution.turn_id, None)
        from deeptutor.runtime.memory_reclaim import schedule_memory_reclaim

        schedule_memory_reclaim()

    async def _publish_mastery_path_change(
        self,
        execution: _TurnExecution,
        *,
        capability_name: str,
        started_on: str,
        ended_on: str,
    ) -> None:
        """Announce a path the turn moved onto, so the client stops lying."""
        if capability_name != "mastery_path" or not ended_on or ended_on == started_on:
            return
        await self._publish_live_event(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION_META,
                source="turn_runtime",
                metadata={"mastery_path_id": ended_on},
            ),
        )

    async def _publish_live_event(
        self,
        execution: _TurnExecution,
        event: StreamEvent,
    ) -> dict[str, Any]:
        if event.type == StreamEventType.DONE and not event.metadata.get("status"):
            event.metadata = {**event.metadata, "status": "completed"}
        event.session_id = execution.session_id
        event.turn_id = execution.turn_id
        payload = event.to_dict()
        async with self._lock:
            current = self._executions.get(execution.turn_id, execution)
            seq = int(payload.get("seq") or 0)
            if seq <= 0:
                seq = current.next_seq
                current.next_seq += 1
                if current is not execution:
                    execution.next_seq = max(execution.next_seq, current.next_seq)
            else:
                current.next_seq = max(current.next_seq, seq + 1)
                execution.next_seq = max(execution.next_seq, seq + 1)
            payload["seq"] = seq
            current.events.append(payload)
            if current is not execution:
                execution.events.append(payload)
            subscribers = list(current.subscribers)
        for subscriber in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                subscriber.queue.put_nowait(payload)
        return payload

    async def _maybe_generate_session_title(
        self,
        *,
        execution: _TurnExecution,
        session_id: str,
        ui_language: str,
    ) -> None:
        """Generate a short LLM-written title for a freshly-named session.

        Runs only when the session still carries the ``New conversation``
        sentinel — once a user manually renames the chat (or this method
        has already filled in a title), it short-circuits. Uses the LLM
        scope already active on the calling task, which is the user's
        currently selected model.
        """
        if not session_id:
            return
        session = await self.store.get_session(session_id)
        if not session:
            return
        current_title = str(session.get("title") or "").strip()
        if current_title and current_title != "New conversation":
            return

        messages = await self.store.get_messages(session_id)
        first_user = ""
        first_assistant = ""
        for m in messages:
            role = str(m.get("role") or "")
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            if role == "user" and not first_user:
                first_user = content
            elif role == "assistant" and not first_assistant:
                first_assistant = content
            if first_user and first_assistant:
                break
        if not first_user or not first_assistant:
            return

        title = ""
        try:
            from deeptutor.services.llm import stream as llm_stream

            zh = str(ui_language or "").lower().startswith("zh")
            if zh:
                sys_prompt = (
                    "你需要为一段对话生成一个简洁的标题。"
                    "直接输出标题文本，不要引号、不要 Markdown 格式、"
                    '不要末尾标点、不要 "标题：" 这类前缀。'
                    "标题控制在 4-10 个汉字以内。"
                )
                user_prompt = (
                    "请基于以下对话生成标题：\n\n"
                    f"[用户]\n{_clip_text(first_user, 800)}\n\n"
                    f"[助手]\n{_clip_text(first_assistant, 1500)}"
                )
            else:
                sys_prompt = (
                    "You generate a concise, descriptive title for a "
                    "conversation. Output only the title as plain text "
                    "— no quotes, no markdown, no trailing punctuation, "
                    'no "Title:" prefix. Keep it 4-8 words.'
                )
                user_prompt = (
                    "Generate a title for this conversation:\n\n"
                    f"[User]\n{_clip_text(first_user, 800)}\n\n"
                    f"[Assistant]\n{_clip_text(first_assistant, 1500)}"
                )

            async def _collect_title() -> str:
                buf: list[str] = []
                async for c in llm_stream(
                    prompt=user_prompt,
                    system_prompt=sys_prompt,
                    temperature=0.3,
                    max_tokens=80,
                ):
                    buf.append(c)
                return "".join(buf)

            raw_title = await asyncio.wait_for(_collect_title(), timeout=20.0)
            title = _sanitize_session_title(raw_title)
        except asyncio.TimeoutError:
            logger.debug("Title LLM call timed out — falling back")
        except Exception:
            logger.debug("Title LLM call failed", exc_info=True)

        if not title:
            # Fallback: truncate the first user message so the sidebar
            # doesn't sit on "New conversation" indefinitely when the
            # title model errors out.
            title = first_user[:50] + ("..." if len(first_user) > 50 else "")

        if not title:
            return

        try:
            await self.store.update_session_title(session_id, title)
        except Exception:
            logger.debug("update_session_title failed", exc_info=True)
            return

        await self._publish_live_event(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION_META,
                source="turn_runtime",
                stage="title",
                content=title,
                metadata={"title": title, "session_id": session_id},
            ),
        )

    async def _flush_buffered_events(self, execution: _TurnExecution) -> None:
        """Persist buffered turn events after the live stream has already drained."""
        async with execution.flush_lock:
            await self._flush_buffered_events_once(execution)

    async def _flush_buffered_events_once(self, execution: _TurnExecution) -> None:
        """One serialized persistence attempt for :meth:`_flush_buffered_events`."""
        if execution.events_flushed:
            return
        if execution.events_persisted:
            await self._mirror_events_to_workspace(execution, execution.persisted_events)
            execution.events_flushed = True
            return
        async with self._lock:
            events = list(execution.events)

        # Prefer the store's batch append (single transaction) when available:
        # per-event commits fsync once per event, which on slow storage (NAS
        # spinning disks) stretches this flush — and the visible spinner — to
        # minutes for a long turn.
        append_batch = getattr(self.store, "append_turn_events", None)
        if callable(append_batch):
            try:
                persisted_batch = await append_batch(execution.turn_id, events)
            except ValueError as exc:
                # A turn can disappear when the session is deleted while the
                # turn task is draining post-stream persistence.
                if "Turn not found:" not in str(exc):
                    raise
                logger.warning(
                    "Skip persisting %d buffered event(s) for missing turn %s",
                    len(events),
                    execution.turn_id,
                )
                execution.persisted_events = []
                execution.events_persisted = True
                execution.events_flushed = True
                return
            execution.persisted_events = list(persisted_batch)
            execution.events_persisted = True
            await self._mirror_events_to_workspace(execution, persisted_batch)
            execution.events_flushed = True
            return

        persisted_events = list(execution.persisted_events)
        try:
            for index, payload in enumerate(events[len(persisted_events) :], len(persisted_events)):
                try:
                    persisted = await self.store.append_turn_event(execution.turn_id, payload)
                except ValueError as exc:
                    # A turn can disappear when the session is deleted while the turn
                    # task is draining post-stream persistence. Avoid cascading
                    # failures. The turn will not come back, so drop the whole
                    # remaining batch with one summary line instead of logging once
                    # per buffered event.
                    if "Turn not found:" not in str(exc):
                        raise
                    logger.warning(
                        "Skip persisting %d buffered event(s) for missing turn %s (first: %s)",
                        len(events) - index,
                        execution.turn_id,
                        payload.get("type", ""),
                    )
                    break
                persisted_events.append(persisted)
        except Exception:
            # Cache a committed prefix so retries continue after it instead of
            # duplicating already persisted events on non-batching backends.
            execution.persisted_events = persisted_events
            raise
        execution.persisted_events = persisted_events
        execution.events_persisted = True
        await self._mirror_events_to_workspace(execution, persisted_events)
        execution.events_flushed = True

    async def _mirror_events_to_workspace(
        self, execution: _TurnExecution, payloads: list[dict[str, Any]]
    ) -> None:
        """Mirror turn events to the task-local ``events.jsonl`` under ``data/user/workspace``.

        One open/write for the whole batch, off the event loop: the previous
        per-event ``open()+append`` ran synchronously on the loop thread and
        stretched turn finalisation (and every other connection) on slow
        storage. ``to_thread`` copies contextvars, so the per-user path scope
        resolves the same as on the loop.
        """
        if not payloads:
            return
        await asyncio.to_thread(self._mirror_events_to_workspace_sync, execution, payloads)

    @staticmethod
    def _mirror_events_to_workspace_sync(
        execution: _TurnExecution, payloads: list[dict[str, Any]]
    ) -> None:
        try:
            path_service = get_path_service()
            task_dir = path_service.get_task_workspace(execution.capability, execution.turn_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            event_file = task_dir / "events.jsonl"
            lines = "".join(
                json.dumps(payload, ensure_ascii=False, default=str) + "\n" for payload in payloads
            )
            with open(event_file, "a", encoding="utf-8") as f:
                f.write(lines)
        except Exception:
            logger.debug("Failed to mirror turn events to workspace", exc_info=True)


import threading

_runtime_lock = threading.Lock()
_runtime_instances: dict[str, TurnRuntimeManager] = {}


def get_turn_runtime_manager() -> TurnRuntimeManager:
    from deeptutor.services.session import get_session_store

    store = get_session_store()
    key = str(getattr(store, "db_path", id(store)))
    with _runtime_lock:
        if key not in _runtime_instances:
            _runtime_instances[key] = TurnRuntimeManager(store=store)
        return _runtime_instances[key]


__all__ = ["TurnRuntimeManager", "get_turn_runtime_manager"]
