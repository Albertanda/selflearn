"""P1-04 行为测试：空正文和截断正文不能成功（C04/C02）。

覆盖卡的四个必证场景，每个都有正例与独立反例：

* ``length`` / ``max_tokens`` / ``max_output_tokens`` 三种 reason 各测空与非空：
  空 -> ``LLMReasoningBudgetExhausted``（保留旧语义），非空 -> ``output_truncated``；
* 非截断但空白 -> ``empty_model_output``（``LLMEmptyResponseError``）；
* ``stop`` + 中文正文正常 trim 返回；
* legacy ``finish_reason=None`` + 正文兼容返回。

另外断言：``finish_reason`` 在成功返回**之前**被检查（半篇正文不得当成功）；
真实 factory 调用参数原样透传（不自动加预算、不自动重试）；诊断只留在服务端。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.services.llm.exceptions import (
    LLMEmptyResponseError,
    LLMReasoningBudgetExhausted,
)
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOutputTruncated,
    map_subject_exception,
    to_http_payload,
)
from deeptutor.subjects.generation import complete_subject_text, validate_subject_response

REPO_ROOT = Path(__file__).resolve().parents[2]

TRUNCATED_REASONS = ("length", "max_tokens", "max_output_tokens")

#: 唯一虚构标记：模型正文/诊断不得出现在对外投影里。
FAKE_MODEL_TEXT = "p1-04-FAKE-MODEL-TEXT-9e2b7d41-DO-NOT-LEAK"

SUBJECT_API_KEY = "sk-p1-04-FAKE-KEY-DO-NOT-LEAK"


def _response(content: str | None, finish_reason: str | None, **extra) -> SimpleNamespace:
    payload = {
        "content": content,
        "finish_reason": finish_reason,
        "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17},
    }
    payload.update(extra)
    return SimpleNamespace(**payload)


# ---------------------------------------------------------------------------
# 正向
# ---------------------------------------------------------------------------
def test_stop_with_chinese_body_returns_trimmed_text():
    response = _response("  \n 复变函数的柯西积分公式 \n ", "stop")
    assert validate_subject_response(response) == "复变函数的柯西积分公式"


def test_legacy_none_finish_reason_with_body_is_accepted():
    response = _response("  legacy 正文  ", None)
    assert validate_subject_response(response) == "legacy 正文"


def test_unknown_but_non_truncating_finish_reason_is_accepted():
    response = _response("正文", "content_filter")
    assert validate_subject_response(response) == "正文"


# ---------------------------------------------------------------------------
# 反向：三种截断 reason x 空 / 非空
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reason", TRUNCATED_REASONS)
def test_empty_truncated_body_keeps_the_reasoning_budget_error(reason: str):
    with pytest.raises(LLMReasoningBudgetExhausted) as excinfo:
        validate_subject_response(_response("", reason), max_tokens=16000)

    error = excinfo.value
    assert error.error_code == "reasoning_budget_exhausted"
    assert error.retryable is True
    # 诊断完整，便于定位
    assert error.diagnostics["finish_reason"] == reason
    assert error.diagnostics["max_tokens"] == 16000
    # 对外投影是具名 502
    projected = map_subject_exception(error)
    assert projected.code is ErrorCode.REASONING_BUDGET_EXHAUSTED
    assert projected.http_status == 502


@pytest.mark.parametrize("reason", TRUNCATED_REASONS)
def test_whitespace_only_truncated_body_is_still_a_failure(reason: str):
    with pytest.raises(LLMReasoningBudgetExhausted):
        validate_subject_response(_response("   \n\t ", reason))


@pytest.mark.parametrize("reason", TRUNCATED_REASONS)
def test_non_empty_truncated_body_raises_output_truncated(reason: str):
    """半篇正文必须失败——这正是原实现 `if text: return text` 的缺陷。"""
    half_written = "# 半篇报告\n\n只写了一半"

    with pytest.raises(SubjectOutputTruncated) as excinfo:
        validate_subject_response(_response(half_written, reason), max_tokens=16000)

    error = excinfo.value
    assert error.code is ErrorCode.OUTPUT_TRUNCATED
    assert error.http_status == 502
    assert error.retryable is True
    assert error.diagnostics["finish_reason"] == reason
    assert error.diagnostics["content_chars"] == len(half_written)
    assert to_http_payload(error)["error"]["code"] == "output_truncated"


def test_finish_reason_is_checked_before_any_success_return():
    """坏对照：把 reason 换成 stop，同样的正文就应当成功返回。"""
    body = "# 完整报告\n\n正文齐全"

    with pytest.raises(SubjectOutputTruncated):
        validate_subject_response(_response(body, "length"))
    assert validate_subject_response(_response(body, "stop")) == body


# ---------------------------------------------------------------------------
# 反向：非截断空白
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("content", ["", "   ", "\n\n\t", None])
def test_non_truncated_blank_body_raises_empty_model_output(content):
    with pytest.raises(LLMEmptyResponseError) as excinfo:
        validate_subject_response(_response(content, "stop"))

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.EMPTY_MODEL_OUTPUT
    assert projected.http_status == 502


def test_empty_body_diagnostics_do_not_leak_into_the_projection():
    with pytest.raises(SubjectOutputTruncated) as excinfo:
        validate_subject_response(
            _response(FAKE_MODEL_TEXT + " 半篇", "length"), max_tokens=1234
        )

    error = excinfo.value
    # 诊断只保存计数与 reason，不保存正文
    assert FAKE_MODEL_TEXT not in str(error.diagnostics)
    assert set(error.diagnostics) == {"finish_reason", "usage", "max_tokens", "content_chars"}
    projected = to_http_payload(error)
    serialized = str(projected)
    assert FAKE_MODEL_TEXT not in serialized
    assert "diagnostics" not in serialized
    assert "1234" not in serialized


# ---------------------------------------------------------------------------
# complete_subject_text：签名、参数透传、真实消费者
# ---------------------------------------------------------------------------
def _run(coro):
    return asyncio.run(coro)


def _call_complete(**overrides):
    kwargs = {
        "prompt": "写一份复习指南",
        "system_prompt": "你是助教",
        "model": "stub-model",
        "api_key": SUBJECT_API_KEY,
        "base_url": "https://stub.invalid/v1",
    }
    kwargs.update(overrides)
    return complete_subject_text(**kwargs)


def test_complete_subject_text_passes_parameters_through_unchanged(monkeypatch):
    calls: list[dict] = []

    async def fake_complete_response(**kwargs):
        calls.append(kwargs)
        return _response("  正文  ", "stop")

    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", fake_complete_response)

    assert _run(_call_complete()) == "正文"

    assert len(calls) == 1
    call = calls[0]
    assert call["prompt"] == "写一份复习指南"
    assert call["system_prompt"] == "你是助教"
    assert call["model"] == "stub-model"
    assert call["api_key"] == SUBJECT_API_KEY
    assert call["base_url"] == "https://stub.invalid/v1"
    # 预算沿用 subject 默认值，既没有被自动提高，也没有重试
    from deeptutor.subjects import LLM_MAX_TOKENS

    assert call["max_tokens"] == LLM_MAX_TOKENS


def test_explicit_budget_is_honoured_and_not_retried(monkeypatch):
    calls: list[dict] = []

    async def fake_complete_response(**kwargs):
        calls.append(kwargs)
        return _response("正文", "stop")

    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", fake_complete_response)

    assert _run(_call_complete(max_tokens=512)) == "正文"
    assert [call["max_tokens"] for call in calls] == [512]


def test_truncated_generation_fails_through_the_real_entry_point(monkeypatch):
    calls: list[dict] = []

    async def fake_complete_response(**kwargs):
        calls.append(kwargs)
        return _response("# 只写了一半", "length")

    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", fake_complete_response)

    with pytest.raises(SubjectOutputTruncated):
        _run(_call_complete())
    # 失败即返回：不自动重试
    assert len(calls) == 1


def test_empty_truncated_generation_keeps_the_s01_contract(monkeypatch):
    """S01 已验收的真实消费者回归：空 + length 仍抛 LLMReasoningBudgetExhausted。"""

    async def fake_complete_response(**_kwargs):
        return _response("", "length")

    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", fake_complete_response)

    with pytest.raises(LLMReasoningBudgetExhausted):
        _run(_call_complete())


def test_blank_generation_raises_empty_response_error(monkeypatch):
    async def fake_complete_response(**_kwargs):
        return _response("   ", "stop")

    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", fake_complete_response)

    with pytest.raises(LLMEmptyResponseError):
        _run(_call_complete())


def test_complete_subject_text_keeps_its_public_signature():
    import inspect

    signature = inspect.signature(complete_subject_text)
    assert list(signature.parameters) == [
        "prompt",
        "system_prompt",
        "model",
        "api_key",
        "base_url",
        "max_tokens",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.parameters["max_tokens"].default is None


def test_validate_subject_response_is_pure():
    """纯函数：同一个 response 反复调用得到同一结果，不修改输入。"""
    response = _response("  正文  ", "stop")
    before = dict(vars(response))

    assert validate_subject_response(response) == "正文"
    assert validate_subject_response(response) == "正文"
    assert vars(response) == before
