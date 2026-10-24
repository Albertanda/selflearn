"""Wrong-question book (M3) — per-subject mistake collection with mastery.

Each entry records a question the learner got wrong (or asked about), its
knowledge point, and an attempt history. Mastery is computed by the same
recency-weighted policy as ``learning.mastery.compute_mastery`` and mapped
to four status levels:

    repeated  反复错  — multiple errors (>=2) or low score after recovery
    missed    错过    — one error, not yet re-verified
    basic     基本掌握 — recovering (0.5 <= score < 0.8)
    mastered  已掌握   — score >= 0.8 (confidence-capped: 2 clean tries)

Storage: ``data/subjects/<id>/wrong_book.json``.
"""

from __future__ import annotations

from pathlib import Path
import time
import uuid

from deeptutor.learning.mastery import compute_mastery
from deeptutor.subjects import json_store, store
from deeptutor.subjects.errors import ERROR_SPECS, ErrorCode, SubjectOperationError

WRONG_BOOK_NAME = "wrong_book.json"


class InvalidCorrectnessError(SubjectOperationError):
    """``correct`` was not a real bool (C02 ``invalid_input``, 400).

    A string ``"false"``, an int ``1`` or ``None`` must never be coerced: the
    attempt history feeds mastery, and ``bool("false") is True`` would silently
    turn a wrong answer into a right one.
    """

    def __init__(self, value: object = None, *, cause: BaseException | None = None) -> None:
        spec = ERROR_SPECS[ErrorCode.INVALID_INPUT]
        self.value = value
        super().__init__(
            spec.code,
            spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )

STATUS_ORDER = ("repeated", "missed", "basic", "mastered", "untracked")
STATUS_LABELS = {
    "repeated": "反复错",
    "missed": "错过",
    "basic": "基本掌握",
    "mastered": "已掌握",
    "untracked": "未标记",
}

#: Mastery is persisted and displayed at this precision. Classification rounds
#: to the SAME precision before comparing against its thresholds, so the number
#: the learner sees and the status beside it can never disagree: the raw
#: recency-weighted score for one miss followed by three hits is
#: ``0.7999999999999999``, which *displays* as 0.8 but failed a ``>= 0.8`` test
#: and was labelled 基本掌握 instead of 已掌握.
MASTERY_PRECISION = 3


def mastery_score(correctness: list[bool]) -> float:
    """Recency-weighted mastery, rounded to the stored/displayed precision."""
    return round(compute_mastery(correctness), MASTERY_PRECISION)


def classify(correctness: list[bool]) -> str:
    """Map an attempt history to one of the four mastery status levels."""
    if not correctness:
        return "untracked"
    score = mastery_score(correctness)
    last = correctness[-1]
    if not last:
        errors = sum(1 for c in correctness if not c)
        return "repeated" if errors >= 2 else "missed"
    if score >= 0.8:
        return "mastered"
    if score >= 0.5:
        return "basic"
    return "repeated"


def _required_text(value: object, what: str) -> str:
    """A caller-supplied required string (blank/non-string -> invalid_input)."""
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    cleaned = value.strip()
    if not cleaned:
        raise json_store.invalid_input(f"{what}不能为空")
    return cleaned


def _optional_text(value: object, what: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    return value.strip()


def _path(subject_id: str) -> Path:
    """The collection file, confined before anything opens it."""
    return store.subject_data_path(subject_id, WRONG_BOOK_NAME)


#: Fields every stored entry must carry, and the type each one has.
_REQUIRED_TEXT = (("id", "错题记录缺少合法 id"), ("question", "错题记录缺少题目"))
_OPTIONAL_TEXT = ("kp", "answer", "analysis", "question_type", "source", "error_type", "status")
_OPTIONAL_NUMBER = ("mastery", "created_at", "updated_at")


def _validate(entries: list[dict], source: Path) -> list[dict]:
    """Check the fields this module reads; never coerce, never skip silently.

    Required: ``id`` and ``question``. Optional fields keep a definite default
    on read (``status`` -> ``untracked``, ``archived`` -> ``False``), while an
    explicitly wrong type is corruption rather than something to "fix up".
    Unknown historical fields are kept as they are (C01).
    """
    for index, entry in enumerate(entries):
        for key, detail in _REQUIRED_TEXT:
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise json_store.corrupt_error(source.name, detail, index=index)
        subject_id = entry.get("subject_id")
        if "subject_id" in entry and not isinstance(subject_id, str):
            raise json_store.corrupt_error(
                source.name, "subject_id 不是字符串", index=index
            )
        for key in _OPTIONAL_TEXT:
            value = entry.get(key)
            if key in entry and not isinstance(value, str):
                raise json_store.corrupt_error(
                    source.name, f"{key} 不是字符串", index=index
                )
        for key in _OPTIONAL_NUMBER:
            value = entry.get(key)
            if key in entry and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise json_store.corrupt_error(
                    source.name, f"{key} 不是数值", index=index
                )
        attempts = entry.get("attempts", [])
        if not isinstance(attempts, list):
            raise json_store.corrupt_error(source.name, "attempts 不是数组", index=index)
        for attempt in attempts:
            if not isinstance(attempt, dict) or not isinstance(attempt.get("correct"), bool):
                raise json_store.corrupt_error(
                    source.name, "attempt.correct 不是布尔值", index=index
                )
        archived = entry.get("archived")
        if "archived" in entry and not isinstance(archived, bool):
            raise json_store.corrupt_error(source.name, "archived 不是布尔值", index=index)
    return entries


def _project(entry: dict) -> dict:
    """The read view of one entry.

    Mastery and status are always **derived from the attempt history**, never
    taken from the stored values: a legacy row carrying ``mastery: 1.0`` /
    ``status: "mastered"`` with no attempts reads as 0.0 / untracked. The
    projection is a copy — reading never rewrites the file.
    """
    view = dict(entry)
    correctness = [attempt["correct"] for attempt in entry.get("attempts", [])]
    view["mastery"] = mastery_score(correctness)
    view["status"] = classify(correctness)
    view.setdefault("archived", False)
    view.setdefault("attempts", [])
    return view


def load(subject_id: str) -> list[dict]:
    """Load the collection as read views; ``[]`` only when the file is absent."""
    path = _path(subject_id)
    return [_project(entry) for entry in _validate(json_store.read_list(path), path)]


def _save(subject_id: str, entries: list[dict]) -> None:
    """Atomically write the collection (the caller already holds the lock)."""
    path = _path(subject_id)
    json_store.atomic_write_list(path, entries)


def _recompute(entry: dict) -> dict:
    """Refresh mastery score + status from the attempt history.

    ``correct`` is taken as-is: :func:`_validate`/``record_attempt`` already
    guarantee it is a real bool, so nothing here can coerce ``"false"``.
    """
    correctness = [attempt["correct"] for attempt in entry.get("attempts", [])]
    # One rounding step shared with ``classify`` — see MASTERY_PRECISION.
    entry["mastery"] = mastery_score(correctness)
    entry["status"] = classify(correctness)
    return entry


def _new_entry(
    subject_id: str,
    *,
    question: str,
    answer: str = "",
    analysis: str = "",
    kp: str = "",
    question_type: str = "written",
    source: str = "manual",
    error_type: str = "",
    now: int | None = None,
) -> dict:
    """Validate the payload and build one stored entry (no I/O).

    Shared by :func:`add_entry` and :func:`submit_graded_attempt` so a graded
    miss and a manually added question can never drift into two shapes.
    """
    question = _required_text(question, "题目")
    stamp = int(time.time()) if now is None else now
    return {
        "id": uuid.uuid4().hex[:12],
        "subject_id": subject_id,
        "kp": _optional_text(kp, "知识点"),
        "question": question,
        "answer": _optional_text(answer, "答案"),
        "analysis": _optional_text(analysis, "解析"),
        "question_type": _optional_text(question_type, "题型") or "written",
        "source": _optional_text(source, "来源") or "manual",
        "error_type": _optional_text(error_type, "错误类型"),
        "attempts": [],
        "mastery": 0.0,
        "status": "untracked",
        "archived": False,
        "created_at": stamp,
        "updated_at": stamp,
    }


def add_entry(
    subject_id: str,
    *,
    question: str,
    answer: str = "",
    analysis: str = "",
    kp: str = "",
    question_type: str = "written",
    source: str = "manual",
    error_type: str = "",
) -> dict:
    """Add a wrong/asked question. Returns the stored entry.

    Required text is validated first: a blank question is a caller error
    (``invalid_input``), not a row worth persisting.
    """
    entry = _new_entry(
        subject_id,
        question=question,
        answer=answer,
        analysis=analysis,
        kp=kp,
        question_type=question_type,
        source=source,
        error_type=error_type,
    )
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)
        entries.append(entry)
        tx.write_list(path, entries)
    return entry


def _append_attempt(entry: dict, *, correct: bool, session_id: str, now: int) -> None:
    """Append one attempt and refresh mastery/status/updated_at in place."""
    entry.setdefault("attempts", []).append(
        {"ts": now, "correct": correct, "session_id": session_id or ""}
    )
    _recompute(entry)
    entry["updated_at"] = now


def record_attempt(
    subject_id: str, entry_id: str, *, correct: bool, session_id: str = ""
) -> dict | None:
    """Record one answer outcome and recompute mastery/status under the lock."""
    if not isinstance(correct, bool):
        # Rejected before any read or write: the stored history stays valid.
        raise InvalidCorrectnessError(correct)
    if not isinstance(entry_id, str) or not entry_id:
        raise json_store.invalid_input("错题 id 必须是非空字符串")
    if not isinstance(session_id, str):
        raise json_store.invalid_input("session_id 必须是字符串")

    now = int(time.time())
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)
        for entry in entries:
            if entry["id"] != entry_id:
                continue
            _append_attempt(entry, correct=correct, session_id=session_id, now=now)
            tx.write_list(path, entries)
            return _project(entry)
        return None


def submit_graded_attempt(
    subject_id: str,
    *,
    question: str,
    correct: bool,
    answer: str = "",
    kp: str = "",
    source: str = "check",
    session_id: str = "",
) -> dict | None:
    """Commit one *graded* answer in a single subject transaction (C05).

    One business commit writes the authoritative collection **once**:

    * an existing entry (exact match on the trimmed question) gets exactly one
      appended attempt and a recomputed mastery/status — regardless of whether
      the verdict was correct, partial or wrong (partial arrives as
      ``correct=False``);
    * a brand-new question answered correctly is *not* a mistake: nothing is
      created, ``wrong_book.json`` is not written (and not created), and
      ``None`` is returned;
    * a brand-new partial/wrong question is created **and** given its first
      attempt inside the same transaction, so no half-written entry can exist.

    Unknown fields on untouched legacy records are preserved: the raw array is
    read, only the matched/created record is modified, and the projection that
    readers see is never written back.

    Returns:
        The stored read view, or ``None`` when a new correct answer was not
        saved.

    Raises:
        InvalidCorrectnessError: ``correct`` was not a real bool.
        InvalidInputError: the question was blank or a parameter had the wrong
            type — raised before anything is read or written.
    """
    if not isinstance(correct, bool):
        raise InvalidCorrectnessError(correct)
    question = _required_text(question, "题目")
    if not isinstance(session_id, str):
        raise json_store.invalid_input("session_id 必须是字符串")
    # Validate the remaining caller parameters up front, so a malformed call
    # cannot behave differently depending on whether the entry already exists.
    answer = _optional_text(answer, "答案")
    kp = _optional_text(kp, "知识点")
    source = _optional_text(source, "来源") or "check"

    now = int(time.time())
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)

        for entry in entries:
            if entry.get("question", "").strip() != question:
                continue
            _append_attempt(entry, correct=correct, session_id=session_id, now=now)
            tx.write_list(path, entries)
            return _project(entry)

        if correct:
            # A new question answered correctly never enters the wrong book:
            # return before writing, so the file keeps its old bytes (or stays
            # absent).
            return None

        entry = _new_entry(
            subject_id, question=question, answer=answer, kp=kp, source=source, now=now
        )
        _append_attempt(entry, correct=False, session_id=session_id, now=now)
        entries.append(entry)
        tx.write_list(path, entries)
        return _project(entry)


def find_by_question(subject_id: str, question: str) -> dict | None:
    """Exact-match lookup (used by the check flow to reuse an entry)."""
    q = question.strip()
    return next((e for e in load(subject_id) if e.get("question", "").strip() == q), None)


def list_entries(
    subject_id: str, *, status: str | None = None, archived: bool | None = None
) -> list[dict]:
    entries = load(subject_id)
    if status:
        entries = [e for e in entries if e.get("status", "untracked") == status]
    if archived is not None:
        entries = [e for e in entries if bool(e.get("archived", False)) is archived]
    return sorted(entries, key=lambda e: e.get("updated_at", 0), reverse=True)


def stats(subject_id: str) -> dict:
    counts = {s: 0 for s in STATUS_ORDER}
    total = 0
    for e in load(subject_id):
        if e.get("archived"):
            continue
        counts[e.get("status", "untracked")] = counts.get(e.get("status", "untracked"), 0) + 1
        total += 1
    return {"total": total, "by_status": counts}


def archive(subject_id: str, entry_id: str) -> dict | None:
    now = int(time.time())
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)
        for entry in entries:
            if entry["id"] != entry_id:
                continue
            entry["archived"] = True
            entry["updated_at"] = now
            tx.write_list(path, entries)
            return _project(entry)
        return None


def delete(subject_id: str, entry_id: str) -> bool:
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)
        kept = [e for e in entries if e["id"] != entry_id]
        if len(kept) == len(entries):
            return False
        tx.write_list(path, kept)
        return True


def context_summary(subject_id: str, limit: int = 5) -> str:
    """Lightweight injection block for chat turns (no full answers).

    Used by the chat pipeline when a session is subject-scoped: gives the
    model the recent mistake list without dumping whole transcripts.
    """
    entries = [e for e in load(subject_id) if not e.get("archived")]
    if not entries:
        return ""
    active = [
        e for e in entries if e.get("status", "untracked") in ("repeated", "missed", "basic")
    ]
    active.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
    lines = ["【该科目的错题集摘要】"]
    counts = {s: 0 for s in ("repeated", "missed", "basic", "mastered")}
    for e in entries:
        counts[e.get("status", "untracked")] = counts.get(e.get("status", "untracked"), 0) + 1
    lines.append(
        f"错题统计：反复错 {counts['repeated']} 道、错过 {counts['missed']} 道、"
        f"基本掌握 {counts['basic']} 道、已掌握 {counts['mastered']} 道。"
    )
    if active:
        lines.append("最近未掌握错题（讲解时请针对性回顾，不要直接念答案）：")
        for e in active[:limit]:
            status = STATUS_LABELS.get(e.get("status", "untracked"), "未标记")
            kp = e.get("kp") or "未标注知识点"
            q = str(e.get("question", ""))[:80]
            lines.append(f"- [{status}][{kp}] {q}")
    return "\n".join(lines)
