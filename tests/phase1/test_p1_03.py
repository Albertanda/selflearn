"""P1-03 行为测试：科目业务错误与安全响应投影（C02）。

覆盖卡的四个必证场景，外加反向断言：

* 实际 ``LLMReasoningBudgetExhausted``（**不是** ``LLMEmptyResponseError`` 子类）
  映射 502/reasoning_budget_exhausted；
* timeout 映射 504；
* 32KiB cause 里的伪 key / Authorization / 正文 / 宿主路径标记不出现在
  HTTP / WS / tool 任一投影，也不出现在 ``repr``/``str``；
* ``detail`` 保持 string、``error`` 字段齐全，并逐个通过冻结 Schema；
* 未知异常安全兜底 ``internal_error``，不伪造成功；
* 负例纪律：先给出合法基准，再只改待测字段。
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from deeptutor.subjects import errors as subject_errors
from deeptutor.subjects.errors import (
    ERROR_SPECS,
    MAX_MESSAGE_LENGTH,
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
    subject_error,
    to_error_dict,
    to_http_payload,
    to_tool_result,
    to_ws_error_metadata,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: C02 表（code → (http, retryable)）。逐个列出，避免用实现反推期望。
C02_TABLE: dict[str, tuple[int, bool]] = {
    "invalid_input": (400, False),
    "invalid_subject_id": (400, False),
    "subject_not_found": (404, False),
    "entry_not_found": (404, False),
    "kb_not_found": (404, False),
    "scope_forbidden": (403, False),
    "kb_not_ready": (409, True),
    "kb_busy": (409, True),
    "material_out_of_sync": (409, True),
    "storage_corrupt": (500, False),
    "storage_io": (500, True),
    "internal_error": (500, False),
    "provider_unavailable": (502, True),
    "provider_timeout": (504, True),
    "empty_model_output": (502, True),
    "invalid_model_output": (502, True),
    "output_truncated": (502, True),
    "reasoning_budget_exhausted": (502, True),
    "sandbox_unavailable": (503, False),
    "sandbox_policy_unsupported": (503, False),
    "chart_failed": (502, True),
    "render_failed": (502, True),
    "feature_unavailable": (501, False),
}

#: 唯一虚构标记：绝不出现在任何对外投影里。
FAKE_API_KEY = "sk-p1-03-FAKE-KEY-3f9a1c7e-DO-NOT-LEAK"
FAKE_AUTHORIZATION = "Bearer p1-03-FAKE-AUTH-8b2d4e6a-DO-NOT-LEAK"
FAKE_PROMPT = "p1-03-FAKE-PROMPT-5c1e9f2b-DO-NOT-LEAK 学生原始作答"
FAKE_HOST_PATH = "/home/albert/selflearn/selflearn/data/user/settings/p1-03-FAKE-PATH-7d3a8c1f"
ALL_MARKERS = (FAKE_API_KEY, FAKE_AUTHORIZATION, FAKE_PROMPT, FAKE_HOST_PATH)


def _schema_validator(name: str) -> jsonschema.Draft202012Validator:
    schemas = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text("utf-8"))
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": schemas["$defs"]}
    )


def _big_cause() -> RuntimeError:
    """32KiB cause，含四类敏感标记；模拟 provider 侧原始异常。"""
    payload = " | ".join(ALL_MARKERS)
    padding = "x" * (32 * 1024 - len(payload))
    return RuntimeError(f"{payload} {padding}")


# ---------------------------------------------------------------------------
# 表与 Schema
# ---------------------------------------------------------------------------
def test_error_table_matches_c02_exactly():
    assert {code.value for code in ERROR_SPECS} == set(C02_TABLE)
    assert {code.value for code in ErrorCode} == set(C02_TABLE)
    for code_value, (status, retryable) in C02_TABLE.items():
        spec = ERROR_SPECS[ErrorCode(code_value)]
        assert spec.http_status == status, code_value
        assert spec.retryable is retryable, code_value
        assert isinstance(spec.message, str) and spec.message
        assert len(spec.message) <= MAX_MESSAGE_LENGTH
        assert "\n" not in spec.message and "\r" not in spec.message


def test_every_code_projects_to_a_schema_valid_error_response():
    validator = _schema_validator("ErrorResponse")
    for code in ErrorCode:
        payload = to_http_payload(subject_error(code))
        validator.validate(payload)
        assert isinstance(payload["detail"], str)
        assert set(payload) == {"detail", "error"}
        assert set(payload["error"]) == {"code", "message", "retryable"}
        assert payload["detail"] == payload["error"]["message"]


# ---------------------------------------------------------------------------
# 实际异常映射
# ---------------------------------------------------------------------------
def test_reasoning_budget_exhausted_is_a_provider_error_and_maps_to_502(p1_runtime):
    from deeptutor.services.llm.exceptions import (
        LLMEmptyResponseError,
        LLMProviderError,
        LLMReasoningBudgetExhausted,
    )

    # 卡的核心事实：它继承 LLMProviderError，而不是 LLMEmptyResponseError。
    assert issubclass(LLMReasoningBudgetExhausted, LLMProviderError)
    assert not issubclass(LLMReasoningBudgetExhausted, LLMEmptyResponseError)

    error = map_subject_exception(LLMReasoningBudgetExhausted("预算耗尽", diagnostics={"x": 1}))
    assert error.code is ErrorCode.REASONING_BUDGET_EXHAUSTED
    assert error.http_status == 502
    assert error.retryable is True
    assert error.cause is not None
    _schema_validator("ErrorResponse").validate(to_http_payload(error))


def test_timeout_maps_to_504(p1_runtime):
    from deeptutor.services.llm.exceptions import LLMTimeoutError

    error = map_subject_exception(LLMTimeoutError("请求超时", provider="stub"))
    assert error.code is ErrorCode.PROVIDER_TIMEOUT
    assert error.http_status == 504
    assert error.retryable is True


def test_named_llm_failures_map_to_their_codes(p1_runtime):
    from deeptutor.services.llm.exceptions import (
        LLMEmptyResponseError,
        LLMParseError,
        LLMProviderError,
        LLMProviderTransportError,
        LLMRateLimitError,
    )

    assert map_subject_exception(LLMEmptyResponseError()).code is ErrorCode.EMPTY_MODEL_OUTPUT
    assert map_subject_exception(LLMParseError()).code is ErrorCode.INVALID_MODEL_OUTPUT
    assert (
        map_subject_exception(LLMProviderTransportError("断流")).code
        is ErrorCode.PROVIDER_UNAVAILABLE
    )
    assert map_subject_exception(LLMRateLimitError()).code is ErrorCode.PROVIDER_UNAVAILABLE
    assert map_subject_exception(LLMProviderError("未知 provider 故障")).code is (
        ErrorCode.PROVIDER_UNAVAILABLE
    )


def test_storage_errors_split_corrupt_from_io():
    corrupt = map_subject_exception(StorageCorruptError("坏 JSON", path="/tmp/x.json"))
    assert corrupt.code is ErrorCode.STORAGE_CORRUPT
    assert corrupt.http_status == 500 and corrupt.retryable is False

    io_error = map_subject_exception(StorageIOError("读失败", path="/tmp/x.json"))
    assert io_error.code is ErrorCode.STORAGE_IO
    assert io_error.http_status == 500 and io_error.retryable is True


def test_unknown_exception_falls_back_to_internal_error_without_claiming_success():
    error = map_subject_exception(RuntimeError("某个没人映射过的故障"))
    assert error.code is ErrorCode.INTERNAL_ERROR
    assert error.http_status == 500 and error.retryable is False
    tool = to_tool_result(error)
    assert tool["success"] is False
    assert "url" not in json.dumps(tool)


def test_existing_subject_operation_error_passes_through_unchanged():
    original = subject_error(ErrorCode.KB_BUSY)
    assert map_subject_exception(original) is original


# ---------------------------------------------------------------------------
# 敏感 cause 不得外泄
# ---------------------------------------------------------------------------
def test_32kib_cause_never_reaches_http_ws_or_tool_projection(p1_runtime):
    from deeptutor.services.llm.exceptions import LLMProviderError

    cause = _big_cause()
    assert len(str(cause)) >= 32 * 1024
    for marker in ALL_MARKERS:
        assert marker in str(cause), "fixture must actually contain the marker"

    error = map_subject_exception(LLMProviderError(str(cause), details={"raw": str(cause)}))

    for name, projection in (
        ("http", to_http_payload(error)),
        ("ws", to_ws_error_metadata(error)),
        ("tool", to_tool_result(error)),
    ):
        serialized = json.dumps(projection, ensure_ascii=False)
        for marker in ALL_MARKERS:
            assert marker not in serialized, f"{name} projection leaked {marker!r}"
        assert len(serialized) < 4096, f"{name} projection is unexpectedly large"

    # 异常自身也不带 cause 原文
    assert subject_errors.MAX_MESSAGE_LENGTH >= len(error.message)
    for surface in (repr(error), str(error), json.dumps(to_error_dict(error), ensure_ascii=False)):
        for marker in ALL_MARKERS:
            assert marker not in surface, f"exception surface leaked {marker!r}"


def test_cause_is_kept_server_side_for_diagnostics(p1_runtime):
    from deeptutor.services.llm.exceptions import LLMProviderError

    cause = LLMProviderError(str(_big_cause()))
    error = map_subject_exception(cause)
    # cause 只在服务端保留：对象上可拿到，但不在对外结构里
    assert error.cause is cause
    assert "cause" not in to_http_payload(error)
    assert "cause" not in to_ws_error_metadata(error)
    assert "cause" not in json.dumps(to_tool_result(error))


# ---------------------------------------------------------------------------
# 合法基准 + 只改一个字段的负例纪律
# ---------------------------------------------------------------------------
def test_valid_base_then_change_only_the_code():
    """先证明基准合法，再只改 code：状态/retryable/message 都跟着表走。"""
    base = subject_error(ErrorCode.INVALID_INPUT)
    base_payload = to_http_payload(base)
    _schema_validator("ErrorResponse").validate(base_payload)
    assert (base.http_status, base.retryable) == (400, False)

    changed = subject_error(ErrorCode.PROVIDER_TIMEOUT)
    changed_payload = to_http_payload(changed)
    _schema_validator("ErrorResponse").validate(changed_payload)
    assert (changed.http_status, changed.retryable) == (504, True)
    # 除目标字段外，结构完全一致
    assert set(changed_payload) == set(base_payload)
    assert set(changed_payload["error"]) == set(base_payload["error"])
    assert changed.message != base.message


def test_long_custom_message_is_discarded_and_the_fixed_message_is_single_line():
    """R1 之后：超长/多行的自造消息不会被"压平后回传"，而是被整条丢弃。

    对外消息永远来自固定表，因此长度与单行性质由表保证；这里同时验证调用者传入的
    换行不会以任何形式出现在投影里。
    """
    long_message = "行1\n行2\r\n" + "很长的消息" * 200
    error = SubjectOperationError(
        ErrorCode.INVALID_MODEL_OUTPUT,
        long_message,
        http_status=502,
        retryable=True,
    )
    assert error.message == ERROR_SPECS[ErrorCode.INVALID_MODEL_OUTPUT].message
    assert len(error.message) <= MAX_MESSAGE_LENGTH
    assert "\n" not in error.message and "\r" not in error.message
    assert "行1" not in json.dumps(to_http_payload(error), ensure_ascii=False)
    _schema_validator("ErrorResponse").validate(to_http_payload(error))


def test_blank_message_falls_back_to_the_fixed_spec_message():
    error = SubjectOperationError(
        ErrorCode.KB_NOT_FOUND, "   \x00  ", http_status=404, retryable=False
    )
    assert error.message == ERROR_SPECS[ErrorCode.KB_NOT_FOUND].message


def test_http_ws_and_tool_share_identical_error_data():
    error = subject_error(ErrorCode.MATERIAL_OUT_OF_SYNC)
    shared = to_error_dict(error)
    assert to_http_payload(error)["error"] == shared
    assert to_ws_error_metadata(error) == shared
    assert to_tool_result(error)["metadata"]["error"] == shared
    # WS/tool 不改变事件协议：只是同一份 error 数据
    assert to_tool_result(error)["success"] is False


def test_string_codes_are_accepted_and_normalised():
    error = subject_error("kb_busy")
    assert error.code is ErrorCode.KB_BUSY
    with pytest.raises(ValueError):
        subject_error("not_a_real_code")


# ---------------------------------------------------------------------------
# R1（rework01）：对外字段只能来自固定表
# ---------------------------------------------------------------------------
def test_valid_base_construction_still_works():
    """基准：用表里的值构造，三个对外字段都原样可用。"""
    spec = ERROR_SPECS[ErrorCode.INVALID_MODEL_OUTPUT]
    error = SubjectOperationError(
        spec.code, spec.message, http_status=spec.http_status, retryable=spec.retryable
    )

    assert error.message == spec.message
    assert error.http_status == spec.http_status
    assert error.retryable is spec.retryable
    assert error.rejected_overrides == {}
    _schema_validator("ErrorResponse").validate(to_http_payload(error))


def test_valid_status_is_compared_by_type_and_value_not_identity():
    spec = ERROR_SPECS[ErrorCode.PROVIDER_TIMEOUT]
    status = int(str(spec.http_status))
    assert status == spec.http_status and status is not spec.http_status
    error = SubjectOperationError(
        spec.code, spec.message, http_status=status, retryable=spec.retryable
    )
    assert error.rejected_overrides == {}
    assert error.http_status == 504


def test_fixed_public_error_fields_cannot_drift_after_construction():
    error = subject_error(ErrorCode.PROVIDER_TIMEOUT)
    for name, value in (
        ("message", FAKE_API_KEY), ("http_status", 200),
        ("retryable", False), ("code", ErrorCode.INVALID_INPUT),
    ):
        try:
            setattr(error, name, value)
        except AttributeError:
            pass
    spec = ERROR_SPECS[ErrorCode.PROVIDER_TIMEOUT]
    assert error.code is spec.code
    assert error.http_status == spec.http_status
    assert error.retryable is spec.retryable
    for projection in (to_http_payload, to_ws_error_metadata, to_tool_result):
        assert FAKE_API_KEY not in json.dumps(projection(error))
    assert to_http_payload(error)["detail"] == spec.message


def test_custom_message_cannot_cross_the_public_boundary():
    """只改 message：任意长度的伪造 Authorization 标记不得进入任何对外投影。"""
    spec = ERROR_SPECS[ErrorCode.INVALID_MODEL_OUTPUT]
    error = SubjectOperationError(
        spec.code,
        FAKE_AUTHORIZATION + "x" * (32 * 1024),
        http_status=spec.http_status,
        retryable=spec.retryable,
    )

    assert error.message == spec.message
    for name, projection in (
        ("http", to_http_payload(error)),
        ("ws", to_ws_error_metadata(error)),
        ("tool", to_tool_result(error)),
    ):
        serialized = json.dumps(projection, ensure_ascii=False)
        assert FAKE_AUTHORIZATION not in serialized, name
        assert "x" * 100 not in serialized, name
    for surface in (repr(error), str(error), json.dumps(to_error_dict(error), ensure_ascii=False)):
        assert FAKE_AUTHORIZATION not in surface


def test_truncated_error_custom_message_is_also_safe():
    from deeptutor.subjects.errors import SubjectOutputTruncated

    error = SubjectOutputTruncated(message=FAKE_AUTHORIZATION)

    assert error.message == ERROR_SPECS[ErrorCode.OUTPUT_TRUNCATED].message
    assert FAKE_AUTHORIZATION not in json.dumps(to_http_payload(error), ensure_ascii=False)


def test_http_status_cannot_override_the_code_table():
    spec = ERROR_SPECS[ErrorCode.PROVIDER_TIMEOUT]
    error = SubjectOperationError(
        spec.code, spec.message, http_status=200, retryable=spec.retryable
    )

    assert error.http_status == 504
    assert error.rejected_overrides["http_status"]["value"] == 200


def test_retryable_is_never_coerced():
    """``"false"`` / ``1`` 都不能被 bool() 隐式转换掩盖错类型。"""
    spec = ERROR_SPECS[ErrorCode.INVALID_INPUT]

    for wrong in ("false", "0", 0, 1, None):
        error = SubjectOperationError(
            spec.code, spec.message, http_status=spec.http_status, retryable=wrong
        )
        assert error.retryable is False, wrong
        assert isinstance(error.retryable, bool)

    retryable_spec = ERROR_SPECS[ErrorCode.KB_BUSY]
    error = SubjectOperationError(
        retryable_spec.code,
        retryable_spec.message,
        http_status=retryable_spec.http_status,
        retryable=False,
    )
    assert error.retryable is True


def test_rejected_overrides_are_recorded_as_digests_not_text():
    """被拒参数只留摘要：服务端可诊断，但不把原文挂到异常上。"""
    spec = ERROR_SPECS[ErrorCode.INTERNAL_ERROR]
    error = SubjectOperationError(
        spec.code, FAKE_API_KEY, http_status=spec.http_status, retryable=spec.retryable
    )

    recorded = error.rejected_overrides["message"]
    assert recorded["kind"] == "str"
    assert recorded["length"] == len(FAKE_API_KEY)
    assert "value" not in recorded
    assert FAKE_API_KEY not in json.dumps(recorded, ensure_ascii=False)
    assert FAKE_API_KEY not in repr(error.rejected_overrides)


def test_safe_message_is_formatting_only_not_a_secret_remover():
    """诚实标注：safe_message 只压平/截断，不承诺去掉秘密。"""
    from deeptutor.subjects.errors import safe_message

    flattened = safe_message("第一行\n" + FAKE_API_KEY)
    assert "\n" not in flattened
    assert FAKE_API_KEY in flattened  # 它不去密——所以对外消息不能用它加工任意输入


def test_all_codes_reject_overrides_and_keep_their_spec():
    """23 个 code 逐个：乱传三个字段后仍等于表里的规格。"""
    validator = _schema_validator("ErrorResponse")
    for code, spec in ERROR_SPECS.items():
        error = SubjectOperationError(
            code, FAKE_PROMPT, http_status=200, retryable="false"
        )
        assert error.message == spec.message
        assert error.http_status == spec.http_status
        assert error.retryable is spec.retryable
        assert set(error.rejected_overrides) == {"message", "http_status", "retryable"}
        validator.validate(to_http_payload(error))


# ---------------------------------------------------------------------------
# R2（rework01）：未知异常不得被猜成用户错误或超时
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc",
    [
        ValueError("internal conversion failed"),
        TypeError("internal signature mismatch"),
        KeyError("internal state missing"),
        RuntimeError("unclassified kernel failure"),
    ],
)
def test_generic_programming_errors_are_internal_not_user_input(exc):
    projected = map_subject_exception(exc)
    assert projected.code is ErrorCode.INTERNAL_ERROR
    assert projected.http_status == 500
    assert projected.retryable is False


def test_a_class_name_does_not_make_an_error_a_provider_timeout():
    class TimeoutConfigurationError(RuntimeError):
        pass

    class TimeoutErrorLike(ValueError):
        pass

    for exc in (TimeoutConfigurationError("config knob missing"), TimeoutErrorLike("bad value")):
        projected = map_subject_exception(exc)
        assert projected.code is ErrorCode.INTERNAL_ERROR, type(exc).__name__
        assert projected.http_status == 500


def test_explicit_invalid_input_stays_400():
    projected = map_subject_exception(subject_error(ErrorCode.INVALID_INPUT))
    assert projected.code is ErrorCode.INVALID_INPUT
    assert projected.http_status == 400
    assert projected.retryable is False


def test_real_timeout_types_still_map_to_504():
    import asyncio

    import httpx

    real_timeouts = [TimeoutError("builtin"), asyncio.TimeoutError("asyncio")]
    if httpx.TimeoutException is not asyncio.TimeoutError:
        real_timeouts.append(httpx.TimeoutException("httpx"))

    for exc in real_timeouts:
        projected = map_subject_exception(exc)
        assert projected.code is ErrorCode.PROVIDER_TIMEOUT, type(exc).__name__
        assert projected.http_status == 504
        assert projected.retryable is True


def test_llm_timeout_error_still_maps_to_504(p1_runtime):
    from deeptutor.services.llm.exceptions import LLMTimeoutError

    projected = map_subject_exception(LLMTimeoutError("provider timed out"))
    assert projected.code is ErrorCode.PROVIDER_TIMEOUT
    assert projected.http_status == 504


def test_known_llm_errors_are_unaffected_by_the_rework(p1_runtime):
    from deeptutor.services.llm.exceptions import (
        LLMEmptyResponseError,
        LLMParseError,
        LLMProviderError,
        LLMReasoningBudgetExhausted,
    )

    assert map_subject_exception(LLMReasoningBudgetExhausted("x")).code is (
        ErrorCode.REASONING_BUDGET_EXHAUSTED
    )
    assert map_subject_exception(LLMEmptyResponseError()).code is ErrorCode.EMPTY_MODEL_OUTPUT
    assert map_subject_exception(LLMParseError()).code is ErrorCode.INVALID_MODEL_OUTPUT
    assert map_subject_exception(LLMProviderError("boom")).code is ErrorCode.PROVIDER_UNAVAILABLE
