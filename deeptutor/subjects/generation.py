"""Shared LLM call for the subject features (M3/M4/M6/M7).

One place that applies the subject generation budget and turns a
budget-truncated generation into a named, diagnosable error.

Why this exists: the subject features generate long artifacts (review guides,
chart reports) with a reasoning model, whose chain-of-thought is billed against
the same ``max_tokens`` budget as the answer. When the budget runs out the
provider returns ``finish_reason="length"`` — sometimes with **no** text, which
used to render as a blank PDF that looked like a success, and sometimes with a
**half-written** artifact, which used to be returned as if it were complete.
Upstream v1.6.10 named the first case; this module covers both.

Ordering matters and is asserted by ``tests/phase1/test_p1_04.py``:
``finish_reason`` is checked **before** any success return.
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.llm.exceptions import (
    LLMEmptyResponseError,
    LLMReasoningBudgetExhausted,
)
from deeptutor.services.llm.types import finish_was_truncated
from deeptutor.subjects import LLM_MAX_TOKENS
from deeptutor.subjects.errors import SubjectOutputTruncated


def validate_subject_response(response: Any, *, max_tokens: int | None = None) -> str:
    """Return the usable, trimmed text of one completion response.

    Pure: it only reads ``response.content`` / ``response.finish_reason`` /
    ``response.usage`` — no retries, no network, no budget changes.

    Raises:
        LLMReasoningBudgetExhausted: ``finish_reason`` is a truncation reason and
            the body is empty (the reasoning-burned-the-budget case). Preserved
            unchanged from the earlier contract.
        SubjectOutputTruncated: ``finish_reason`` is a truncation reason **and**
            the body is non-empty — a half-written artifact must not be treated
            as a finished one.
        LLMEmptyResponseError: not truncated, but the body is blank.
    """
    content = getattr(response, "content", None)
    text = (content or "").strip()
    finish_reason = getattr(response, "finish_reason", None)

    # 1) finish_reason 先判：有正文但被截断同样不能算成功。
    if finish_was_truncated(finish_reason):
        usage = dict(getattr(response, "usage", None) or {})
        diagnostics = {
            "finish_reason": finish_reason,
            "usage": usage,
            "max_tokens": max_tokens,
            "content_chars": len(text),
        }
        if text:
            raise SubjectOutputTruncated(diagnostics=diagnostics)
        raise LLMReasoningBudgetExhausted(
            "模型把输出预算耗尽在推理上，没有产出正文"
            f"（finish_reason={finish_reason}，"
            f"completion_tokens={usage.get('completion_tokens', '?')}，"
            f"max_tokens={max_tokens}）。请提高 max_tokens 或降低推理强度后重试。",
            diagnostics=diagnostics,
        )

    # 2) 非截断但空白：provider 没给出可用正文。
    if not text:
        raise LLMEmptyResponseError(
            "模型返回空内容，请重试。",
            details={"finish_reason": finish_reason, "max_tokens": max_tokens},
        )

    return text


async def complete_subject_text(
    *,
    prompt: str,
    system_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    max_tokens: int | None = None,
) -> str:
    """Run one subject-feature completion and return its trimmed text.

    The public signature and parameter semantics are unchanged; the result
    check is delegated to :func:`validate_subject_response`.

    Raises:
        LLMReasoningBudgetExhausted: the provider stopped at an output cap
            (``finish_reason`` is a truncation reason) without producing text —
            the reasoning-burned-the-budget case, reported as such.
        SubjectOutputTruncated: the provider stopped at an output cap but had
            already produced partial text.
        LLMEmptyResponseError: the provider returned no text for any other
            reason.
    """
    from deeptutor.services.llm.factory import complete_response

    budget = max_tokens or LLM_MAX_TOKENS
    response = await complete_response(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=budget,
    )

    return validate_subject_response(response, max_tokens=budget)


__all__ = ("complete_subject_text", "validate_subject_response")
