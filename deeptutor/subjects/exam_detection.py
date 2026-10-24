"""Exam-point detection (M4) — find teacher-stressed examinable content
in lecture transcripts (e.g. ASR output).

Pipeline: transcript → LLM detection (signal-based) → **validated** candidates
(level explicit/emphasis, evidence quoted verbatim from the transcript) →
deterministic negative-signal filtering → user confirmation → store.

Why this module was rewritten (C06):

* A legal ``{"points": []}`` ("no signals found") and a *failed* detection used
  to look identical: the parser returned ``[]`` for bad JSON, a missing
  ``points`` key, a wrong ``level`` and merely empty candidates alike, and
  :func:`detect_points` turned every exception into
  ``{"points": [], "error": str(exc)}`` — a 200 response reporting "nothing
  found". Now a legal empty list succeeds and every failure is raised as a
  named C02 error, so the route can never report ``detected=0`` for a broken
  model.
* The evidence must be a **direct quote**: after whitespace normalisation it has
  to occur in the transcript. Rewriting punctuation or words, or a merely
  similar phrase, makes the whole round ``invalid_model_output`` — candidates
  are never silently dropped and never partially saved.
* The deterministic negative-phrase guardrail ("不考/不会考/不用重点看/了解即可")
  runs **after** schema and citation validation, so exclusion can never hide a
  malformed candidate.

The prompt version is bumped to ``v4``: ``v3`` shipped an example whose
``evidence`` was not actually a substring of its own input, which taught the
model to paraphrase quotes. :data:`DETECT_PROMPT_VERSION` always names the
prompt this module really sends, and both are returned to the caller.
"""

from __future__ import annotations

import re

from deeptutor.services.llm.config import get_llm_config
from deeptutor.subjects import model_output
from deeptutor.subjects.errors import SubjectOperationError, map_subject_exception
from deeptutor.subjects.generation import complete_subject_text
from deeptutor.subjects.json_store import invalid_input
from deeptutor.subjects.model_output import ModelOutputError, parse_model_object

DETECT_PROMPT_VERSION = "v4"

DETECT_PROMPT_V4 = """你是一名严谨的课程助教，任务是从大学课堂讲课转写文本中识别【教师明确暗示会考】的内容。

## 识别信号（按强度分级）
- explicit（明示）：教师明确说【今年/本学期】考试会考。信号词如："这是重中之重""期末肯定要考""必考""一定会考""每年都考""考试重点""重点掌握""这里会考""必出""大题必考"等。注意："每年都考/每年都出题"属于明确的考试暗示，可判 explicit；但"去年考过/往年考过"只是历史经验，判 emphasis。
- emphasis（强调）：教师强烈提示重要性但没有直说【今年会考】。信号词如："这个很重要""特别重要""一定要重视""务必掌握""最关键""最容易错""经常考""往年考过""去年考过""基础中的基础""年年都要用到""大家注意""重点""核心""多练几遍"等。

## 输出要求
只输出 JSON（不要任何其他文字）：
{"points": [{"content": "考点内容的完整描述（含具体知识点/公式/结论）", "level": "explicit", "evidence": "原文中的直接引文（教师原话，越短越好，且必须能在转写原文中逐字找到）", "kp": "所属知识点名称（如：一阶线性方程、洛必达法则）"}]}

## 规则
1. 只提取有明确依据的考点，宁缺毋滥；闲聊、过渡句、题外话不要提取。
2. explicit 必须真的有"必考/肯定考/每年都考/重中之重"这类【指向今年考试】的字面信号；只有"重要/注意/重视"而没有考试指向的归为 emphasis；"去年考过/往年考过"归为 emphasis。
3. 教师用强语气强调（"很重要+一定要重视""务必掌握""基础中的基础""几乎年年都要用到"）即使没有"考"字，也要提取为 emphasis——知识点主题本身可以作为考点内容。
4. 教师明确说"不用重点看""不会考""了解即可""看看书就行"的内容，即使前面有"重要"字样，也【不要】提取（负向信号优先）。
5. evidence 必须是原文引文，不得改写、不得增删标点或词语。
6. 同一知识点被多次强调时合并为一条，evidence 取最强的那句。
7. 找不到任何考点时输出 {"points": []}。

## 示例
输入："这个内容很重要，大家一定要重视起来，几乎年年都要用到。"
输出：{"points": [{"content": "常微分方程组的解法（整体重要性）", "level": "emphasis", "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到", "kp": "常微分方程组"}]}

输入："去年期末考试最后一道大题就考的消元法，大家今年注意。"
输出：{"points": [{"content": "消元法解常微分方程组", "level": "emphasis", "evidence": "去年期末考试最后一道大题就考的消元法", "kp": "消元法"}]}

输入："这个不难，不用重点看，大家了解一下就行。"
输出：{"points": []}
"""

#: The prompt actually sent for :data:`DETECT_PROMPT_VERSION`. The returned
#: ``version`` is always looked up from this table, so a caller can never be
#: told "v4" while an older prompt was used.
DETECT_PROMPT = DETECT_PROMPT_V4

_PROMPTS_BY_VERSION: dict[str, str] = {DETECT_PROMPT_VERSION: DETECT_PROMPT}

#: Detection levels the model may emit (C06). ``inferred`` is a *storage*
#: compatibility level for historical manual rows and is never produced here.
DETECT_LEVELS: tuple[str, ...] = ("explicit", "emphasis")

#: Deterministic negative-signal guardrail (C06). This is a literal-text
#: guardrail, not a semantic classifier.
NEGATIVE_PHRASES: tuple[str, ...] = (
    "不会考",
    "不用重点看",
    "不考",
    "了解即可",
    "看看书就行",
)

WARNING_NEGATIVE_EVIDENCE = "negative_evidence_excluded"

#: Server-side rejection reasons (never projected to the caller).
REASON_POINTS_MISSING = "points_missing"
REASON_POINTS_NOT_A_LIST = "points_not_a_list"
REASON_CANDIDATE_NOT_AN_OBJECT = "candidate_not_an_object"
REASON_CONTENT_MISSING = "content_missing"
REASON_CONTENT_NOT_A_STRING = "content_not_a_string"
REASON_CONTENT_BLANK = "content_blank"
REASON_EVIDENCE_MISSING = "evidence_missing"
REASON_EVIDENCE_NOT_A_STRING = "evidence_not_a_string"
REASON_EVIDENCE_BLANK = "evidence_blank"
REASON_KP_MISSING = "kp_missing"
REASON_KP_NOT_A_STRING = "kp_not_a_string"
REASON_LEVEL_MISSING = "level_missing"
REASON_LEVEL_NOT_A_STRING = "level_not_a_string"
REASON_LEVEL_UNKNOWN = "level_unknown"
REASON_EVIDENCE_NOT_IN_TRANSCRIPT = "evidence_not_in_transcript"
REASON_RAW_INVALID_UNICODE = "raw_invalid_unicode"

_WHITESPACE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Whitespace-only normalisation used by the quote and dedupe comparisons.

    Every run of whitespace is removed, so a quote may differ from the
    transcript only in spacing/line breaks. Punctuation, characters and word
    order must still match exactly — no semantic similarity is accepted.
    """
    return _WHITESPACE.sub("", text)


def prompt_for_version(version: str) -> str:
    """The prompt for *version*; an unknown version is a caller error."""
    try:
        return _PROMPTS_BY_VERSION[version]
    except KeyError:
        raise invalid_input(f"未知的检测提示词版本：{version}") from None


def _model_body(raw: str) -> str:
    """The model's body without its reasoning block.

    Reuses the stripper that ``parse_model_object`` already validated (the parse
    succeeded, so the block is closed); ``raw`` must never carry the model's
    chain of thought to the client (C06).
    """
    stripped = model_output._strip_think_blocks(raw)  # reuse the vetted stripper
    body = stripped.strip()
    try:
        body.encode("utf-8")
    except UnicodeEncodeError as exc:
        # Even ignored model fields remain in the returned raw body. Validate
        # that response before the route can publish any exam points.
        raise ModelOutputError(REASON_RAW_INVALID_UNICODE, cause=exc) from exc
    return body


def _candidate(raw: object, transcript: str) -> dict:
    """Validate one candidate: schema first, then the direct-quote requirement."""
    if not isinstance(raw, dict):
        raise ModelOutputError(REASON_CANDIDATE_NOT_AN_OBJECT)

    if "content" not in raw:
        raise ModelOutputError(REASON_CONTENT_MISSING)
    if not isinstance(raw["content"], str):
        raise ModelOutputError(REASON_CONTENT_NOT_A_STRING)
    content = raw["content"].strip()
    if not content:
        raise ModelOutputError(REASON_CONTENT_BLANK)

    if "evidence" not in raw:
        raise ModelOutputError(REASON_EVIDENCE_MISSING)
    if not isinstance(raw["evidence"], str):
        raise ModelOutputError(REASON_EVIDENCE_NOT_A_STRING)
    evidence = raw["evidence"].strip()
    if not evidence:
        raise ModelOutputError(REASON_EVIDENCE_BLANK)

    if "kp" not in raw:
        raise ModelOutputError(REASON_KP_MISSING)
    if not isinstance(raw["kp"], str):
        raise ModelOutputError(REASON_KP_NOT_A_STRING)
    kp = raw["kp"].strip()

    if "level" not in raw:
        raise ModelOutputError(REASON_LEVEL_MISSING)
    level = raw["level"]
    if not isinstance(level, str):
        raise ModelOutputError(REASON_LEVEL_NOT_A_STRING)
    # C06 的枚举是**精确**的：'EXPLICIT'、' Explicit '、'emphasis\n' 都不是
    # explicit/emphasis。这里不做 strip/lower 修错，否则等于用"归一化"把非法
    # level 变成合法考点写进集合（这正是本轮 R1 要挡的行为）。
    if level not in DETECT_LEVELS:
        raise ModelOutputError(REASON_LEVEL_UNKNOWN)

    # JSON decoding accepts escaped lone surrogates; neither our UTF-8 files
    # nor HTTP responses can encode them. This is invalid model output rather
    # than a later serialization/storage failure after validation succeeds.
    for field, value in (("content", content), ("evidence", evidence), ("kp", kp)):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ModelOutputError(f"{field}_invalid_unicode", cause=exc) from exc

    if normalize_whitespace(evidence) not in normalize_whitespace(transcript):
        # Not a direct quote: the whole round fails (C06) instead of dropping
        # this candidate and reporting the rest as a success.
        raise ModelOutputError(REASON_EVIDENCE_NOT_IN_TRANSCRIPT)

    return {"content": content, "level": level, "evidence": evidence, "kp": kp}


def parse_points(raw: str, transcript: str) -> tuple[list[dict], int]:
    """Validate one model reply into candidates plus the excluded count.

    Returns:
        ``(points, excluded)`` where *excluded* counts candidates that passed
        schema **and** citation validation but were removed by the deterministic
        negative-phrase guardrail.

    Raises:
        ModelOutputError: the reply is not exactly one complete JSON object, the
            top level has no ``points`` array, a candidate is not an object, a
            required field is missing/has the wrong type/is blank, the level is
            not exactly ``explicit``/``emphasis``, or an evidence quote is not
            present in the transcript.
    """
    data = parse_model_object(raw)
    if "points" not in data:
        raise ModelOutputError(REASON_POINTS_MISSING)
    candidates = data["points"]
    if not isinstance(candidates, list):
        raise ModelOutputError(REASON_POINTS_NOT_A_LIST)

    points: list[dict] = []
    excluded = 0
    for item in candidates:
        # Schema and citation are checked before the negative-signal filter:
        # exclusion must never mask an illegal candidate.
        point = _candidate(item, transcript)
        if any(phrase in normalize_whitespace(point["evidence"]) for phrase in NEGATIVE_PHRASES):
            excluded += 1
            continue
        points.append(point)
    return points, excluded


async def detect_points(
    transcript: str,
    *,
    term: str = "",
    source: str = "lecture",
    language: str = "zh",
    prompt_version: str = DETECT_PROMPT_VERSION,
) -> dict:
    """Run detection and return ``{version, points, raw, warnings}``.

    ``points`` are validated, unconfirmed candidates (the caller decides the
    confirmation policy and commits them in one batch). Failures — provider,
    truncation, budget exhausted, unusable body, non-quote evidence — propagate
    as typed C02 errors; an empty list always means "the model really found
    nothing".
    """
    if not isinstance(transcript, str):
        raise invalid_input("课堂转写必须是字符串")
    if not transcript.strip():
        raise invalid_input("课堂转写不能为空")
    if not isinstance(term, str):
        raise invalid_input("学期必须是字符串")
    if not isinstance(source, str):
        raise invalid_input("来源必须是字符串")

    prompt = prompt_for_version(prompt_version)
    try:
        cfg = get_llm_config()
        raw = await complete_subject_text(
            prompt=prompt + "\n\n## 课堂转写文本\n" + transcript,
            system_prompt=(
                "你是课堂考点提取助手，只输出 JSON。"
                if language.startswith("zh")
                else "You extract exam points from lectures. JSON only."
            ),
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
    except SubjectOperationError:
        # Already projectable (truncation / empty / budget / parse): keep it.
        raise
    except Exception as exc:  # noqa: BLE001 - real provider/transport failures
        raise map_subject_exception(exc) from exc

    points, excluded = parse_points(raw, transcript)
    for point in points:
        point["term"] = term
        point["source"] = source
        point["anchor"] = ""

    warnings: list[dict] = []
    if excluded:
        warnings.append(
            {
                "code": WARNING_NEGATIVE_EVIDENCE,
                "message": f"已按负向信号排除 {excluded} 条候选（不考/不会考/不用重点看/了解即可等）。",
                "count": excluded,
            }
        )

    return {
        "version": prompt_version,
        "points": points,
        "raw": _model_body(raw),
        "warnings": warnings,
    }


__all__ = (
    "DETECT_LEVELS",
    "DETECT_PROMPT",
    "DETECT_PROMPT_V4",
    "DETECT_PROMPT_VERSION",
    "NEGATIVE_PHRASES",
    "WARNING_NEGATIVE_EVIDENCE",
    "detect_points",
    "normalize_whitespace",
    "parse_points",
    "prompt_for_version",
)
