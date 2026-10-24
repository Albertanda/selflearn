"""Grading (M3) — one *validated* LLM grade per answer check (C05/C04).

Why this module exists: the check flow used to pull the first ``{...}`` out of
the model reply with a greedy regex and turn **every** failure — a transport
error, a truncated answer, an unknown verdict — into ``wrong``. A learner who
answered correctly while the provider was down was recorded as having missed
the question, and the wrong-question book (mastery, status, review lists)
inherited that lie.

The rules implemented here are the C05 ones:

* the reply must be exactly one complete JSON object (C04 parsing, delegated to
  :func:`deeptutor.subjects.model_output.parse_model_object` — no second JSON
  reader, no trailing-comma repair);
* ``verdict`` must be a string and, after ``strip()``/``lower()``, exactly one of
  ``correct`` / ``partial`` / ``wrong``; ``feedback`` must be a string (an empty
  string is a valid string). A missing field, a wrong type or an unknown enum is
  ``invalid_model_output`` — never ``wrong``;
* the feedback keeps its historical 500-character cap and gains no new
  non-empty requirement;
* the config read and the provider call happen inside **one** diagnosable
  boundary, and the real LLM failure keeps its ``cause`` so the P1-56 route
  wrapper can project it to the C02 payload. Nothing here writes a raw
  exception string into the feedback.

This module never touches disk: it returns a validated :class:`GradeResult` and
the caller commits it.
"""

from __future__ import annotations

from dataclasses import dataclass

from deeptutor.services.llm.config import get_llm_config
from deeptutor.subjects.errors import (
    SubjectOperationError,
    map_subject_exception,
)
from deeptutor.subjects.generation import complete_subject_text
from deeptutor.subjects.json_store import invalid_input
from deeptutor.subjects.model_output import ModelOutputError, parse_model_object

#: Bumped when the grading prompt changes so stored/compared behaviour stays
#: identifiable. ``v1`` is the first version that lives in this module.
GRADE_PROMPT_VERSION = "v1"

#: Historical feedback cap (C05 keeps it; no new non-empty rule is added).
FEEDBACK_MAX_CHARS = 500

#: The only accepted verdicts, after ``strip()``/``lower()`` normalisation.
VERDICTS: tuple[str, ...] = ("correct", "partial", "wrong")

SYSTEM_PROMPT = "你是严格的批改助教。"

#: Server-side rejection reasons (never projected to the caller).
REASON_VERDICT_MISSING = "verdict_missing"
REASON_VERDICT_NOT_A_STRING = "verdict_not_a_string"
REASON_VERDICT_UNKNOWN = "verdict_unknown"
REASON_FEEDBACK_MISSING = "feedback_missing"
REASON_FEEDBACK_NOT_A_STRING = "feedback_not_a_string"
REASON_FEEDBACK_INVALID_UNICODE = "feedback_invalid_unicode"


@dataclass(frozen=True)
class GradeResult:
    """A validated grade: exactly the two fields C05 allows, both checked."""

    verdict: str
    feedback: str

    @property
    def correct(self) -> bool:
        """``correct`` is derived from the verdict, never stored separately."""
        return self.verdict == "correct"


def build_prompt(question: str, student_answer: str, reference_answer: str = "") -> str:
    """The grading prompt: question, student answer and (optional) reference.

    The reference line is omitted when empty, exactly as before, so the prompt
    for the common "no reference answer" case is unchanged.
    """
    reference_line = f"参考答案：{reference_answer}\n" if reference_answer else ""
    return (
        "你是一名严谨且鼓励学习者的助教，正在批改一道题。\n\n"
        f"题目：{question}\n"
        + reference_line
        + f"学生作答：{student_answer}\n\n"
        '请只输出 JSON：{"verdict": "correct|partial|wrong", '
        '"feedback": "简短分条反馈（哪里对、哪里错、如何改正）"}'
    )


def _required_text(value: object, what: str) -> str:
    """A caller-supplied required string (blank/non-string -> invalid_input)."""
    if not isinstance(value, str):
        raise invalid_input(f"{what}必须是字符串")
    cleaned = value.strip()
    if not cleaned:
        raise invalid_input(f"{what}不能为空")
    return cleaned


def parse_grade(raw: str) -> GradeResult:
    """Validate one model reply into a :class:`GradeResult` (pure).

    Raises:
        ModelOutputError: the reply is not exactly one complete JSON object
            (delegated to ``parse_model_object``), or the object does not carry
            a legal ``verdict``/``feedback`` pair. The code is C02
            ``invalid_model_output`` and the fixed safe message, never ``wrong``.
    """
    data = parse_model_object(raw)

    if "verdict" not in data:
        raise ModelOutputError(REASON_VERDICT_MISSING)
    verdict = data["verdict"]
    if not isinstance(verdict, str):
        # 1, None, ["correct"] … are not coerced into a verdict.
        raise ModelOutputError(REASON_VERDICT_NOT_A_STRING)
    verdict = verdict.strip().lower()
    if verdict not in VERDICTS:
        raise ModelOutputError(REASON_VERDICT_UNKNOWN)

    if "feedback" not in data:
        raise ModelOutputError(REASON_FEEDBACK_MISSING)
    feedback = data["feedback"]
    if not isinstance(feedback, str):
        raise ModelOutputError(REASON_FEEDBACK_NOT_A_STRING)
    try:
        feedback.encode("utf-8")
    except UnicodeEncodeError as exc:
        # JSON escapes can decode to lone surrogates. Reject before the caller
        # commits an attempt: the HTTP JSON response cannot serialize them.
        raise ModelOutputError(REASON_FEEDBACK_INVALID_UNICODE, cause=exc) from exc

    return GradeResult(verdict=verdict, feedback=feedback[:FEEDBACK_MAX_CHARS])


async def grade_answer(
    question: str,
    student_answer: str,
    reference_answer: str = "",
) -> GradeResult:
    """Grade one answer through the real subject generation path.

    The caller's parameters are validated first (a blank question is a caller
    error, ``invalid_input``, not a model failure), then the config read and the
    completion run together inside one boundary so an LLM/provider problem
    arrives as a typed C02 error that still carries the original ``cause``.

    Raises:
        SubjectOperationError: ``invalid_input`` for bad parameters,
            ``invalid_model_output`` for an unusable reply, or whatever
            :func:`deeptutor.subjects.errors.map_subject_exception` maps the real
            provider/truncation failure to (``output_truncated``,
            ``reasoning_budget_exhausted``, ``empty_model_output``,
            ``provider_unavailable``, ``provider_timeout`` …).
    """
    question = _required_text(question, "题目")
    student_answer = _required_text(student_answer, "学生作答")
    if reference_answer is None:
        reference_answer = ""
    if not isinstance(reference_answer, str):
        raise invalid_input("参考答案必须是字符串")

    prompt = build_prompt(question, student_answer, reference_answer)
    try:
        cfg = get_llm_config()
        raw = await complete_subject_text(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
    except SubjectOperationError:
        # Already a typed, safely projectable error (truncation, empty output,
        # budget exhausted, invalid model output): keep it and its cause as-is.
        raise
    except Exception as exc:  # noqa: BLE001 - real provider/transport failures
        # Keep the true cause server-side; the fixed public message comes from
        # the C02 table in map_subject_exception.
        raise map_subject_exception(exc) from exc

    return parse_grade(raw)


__all__ = (
    "FEEDBACK_MAX_CHARS",
    "GRADE_PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "VERDICTS",
    "GradeResult",
    "build_prompt",
    "grade_answer",
    "parse_grade",
)
