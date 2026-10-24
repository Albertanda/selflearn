"""科目业务错误与安全响应投影（C02）。

本模块只做两件事：

1. 定义 C02 表中固定的错误 code、HTTP 状态、retryable 与**固定安全消息**；
2. 把服务端异常投影成对外结构——HTTP 的 ``detail`` + ``error``、WS/tool 共享的
   error 数据。

边界（本阶段刻意不做）：

* 不注册全局 exception handler，不包装任何 APIRoute——那是 P1-56 的工作；
* 不实现存储事务或锁——那是 P1-10/S03 的工作；
* 不把 ``cause`` 的原文投到任何对外结构。``cause`` 只留在服务端，响应永远是
  本模块里的固定消息。

安全性质（由 ``tests/phase1/test_p1_03.py`` 断言）：

* 每个投影都只含 ``code`` / ``message`` / ``retryable``（以及 HTTP 的 ``detail``）；
* 32KiB 的 cause（含伪 key、Authorization、正文、宿主路径）不会出现在任何投影、
  也不会出现在异常的 ``repr``/``str`` 里；
* ``message``/``detail`` 与 Schema 一致：非空且 ≤512 字符。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Mapping

#: Schema：``Error.message`` / ``ErrorResponse.detail`` 的 maxLength。
MAX_MESSAGE_LENGTH = 512

#: 控制字符（含换行/回车）在对外消息里一律压成空格：安全消息必须是单行固定文本。
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class ErrorCode(str, Enum):
    """C02 表中的全部 code。"""

    INVALID_INPUT = "invalid_input"
    INVALID_SUBJECT_ID = "invalid_subject_id"
    SUBJECT_NOT_FOUND = "subject_not_found"
    ENTRY_NOT_FOUND = "entry_not_found"
    KB_NOT_FOUND = "kb_not_found"
    SCOPE_FORBIDDEN = "scope_forbidden"
    KB_NOT_READY = "kb_not_ready"
    KB_BUSY = "kb_busy"
    MATERIAL_OUT_OF_SYNC = "material_out_of_sync"
    STORAGE_CORRUPT = "storage_corrupt"
    STORAGE_IO = "storage_io"
    INTERNAL_ERROR = "internal_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    EMPTY_MODEL_OUTPUT = "empty_model_output"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    OUTPUT_TRUNCATED = "output_truncated"
    REASONING_BUDGET_EXHAUSTED = "reasoning_budget_exhausted"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    SANDBOX_POLICY_UNSUPPORTED = "sandbox_policy_unsupported"
    CHART_FAILED = "chart_failed"
    RENDER_FAILED = "render_failed"
    FEATURE_UNAVAILABLE = "feature_unavailable"



@dataclass(frozen=True)
class ErrorSpec:
    """一个 code 的固定投影。消息是常量，绝不拼接输入。"""

    code: ErrorCode
    http_status: int
    retryable: bool
    message: str


def _spec(code: ErrorCode, http_status: int, retryable: bool, message: str) -> ErrorSpec:
    return ErrorSpec(code=code, http_status=http_status, retryable=retryable, message=message)


ERROR_SPECS: Mapping[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_INPUT: _spec(
        ErrorCode.INVALID_INPUT, 400, False, "请求参数无效，请检查后重试。"
    ),
    ErrorCode.INVALID_SUBJECT_ID: _spec(
        ErrorCode.INVALID_SUBJECT_ID, 400, False, "科目标识无效。"
    ),
    ErrorCode.SUBJECT_NOT_FOUND: _spec(
        ErrorCode.SUBJECT_NOT_FOUND, 404, False, "科目不存在。"
    ),
    ErrorCode.ENTRY_NOT_FOUND: _spec(
        ErrorCode.ENTRY_NOT_FOUND, 404, False, "记录不存在。"
    ),
    ErrorCode.KB_NOT_FOUND: _spec(
        ErrorCode.KB_NOT_FOUND, 404, False, "知识库不存在。"
    ),
    ErrorCode.SCOPE_FORBIDDEN: _spec(
        ErrorCode.SCOPE_FORBIDDEN, 403, False, "没有访问该资源的权限。"
    ),
    ErrorCode.KB_NOT_READY: _spec(
        ErrorCode.KB_NOT_READY, 409, True, "知识库尚未就绪，请稍后重试。"
    ),
    ErrorCode.KB_BUSY: _spec(
        ErrorCode.KB_BUSY, 409, True, "该知识库已有任务进行中，请稍后重试。"
    ),
    ErrorCode.MATERIAL_OUT_OF_SYNC: _spec(
        ErrorCode.MATERIAL_OUT_OF_SYNC, 409, True, "资料与索引源不一致，需要重新建立索引。"
    ),
    ErrorCode.STORAGE_CORRUPT: _spec(
        ErrorCode.STORAGE_CORRUPT, 500, False, "本地数据文件已损坏，未做任何修改。"
    ),
    ErrorCode.STORAGE_IO: _spec(
        ErrorCode.STORAGE_IO, 500, True, "本地数据读写失败，请重试。"
    ),
    ErrorCode.INTERNAL_ERROR: _spec(
        ErrorCode.INTERNAL_ERROR, 500, False, "服务内部错误，请稍后重试。"
    ),
    ErrorCode.PROVIDER_UNAVAILABLE: _spec(
        ErrorCode.PROVIDER_UNAVAILABLE, 502, True, "模型服务暂时不可用，请稍后重试。"
    ),
    ErrorCode.PROVIDER_TIMEOUT: _spec(
        ErrorCode.PROVIDER_TIMEOUT, 504, True, "模型服务响应超时，请重试。"
    ),
    ErrorCode.EMPTY_MODEL_OUTPUT: _spec(
        ErrorCode.EMPTY_MODEL_OUTPUT, 502, True, "模型返回空内容，请重试。"
    ),
    ErrorCode.INVALID_MODEL_OUTPUT: _spec(
        ErrorCode.INVALID_MODEL_OUTPUT, 502, True, "模型返回的结果无法解析，请重试。"
    ),
    ErrorCode.OUTPUT_TRUNCATED: _spec(
        ErrorCode.OUTPUT_TRUNCATED, 502, True, "模型输出被截断，内容不完整，请重试。"
    ),
    ErrorCode.REASONING_BUDGET_EXHAUSTED: _spec(
        ErrorCode.REASONING_BUDGET_EXHAUSTED, 502, True, "模型把输出预算耗尽在推理上，请重试。"
    ),
    ErrorCode.SANDBOX_UNAVAILABLE: _spec(
        ErrorCode.SANDBOX_UNAVAILABLE, 503, False, "隔离执行环境不可用。"
    ),
    ErrorCode.SANDBOX_POLICY_UNSUPPORTED: _spec(
        ErrorCode.SANDBOX_POLICY_UNSUPPORTED, 503, False, "当前部署不支持所需的隔离执行策略。"
    ),
    ErrorCode.CHART_FAILED: _spec(
        ErrorCode.CHART_FAILED, 502, True, "图表生成失败。"
    ),
    ErrorCode.RENDER_FAILED: _spec(
        ErrorCode.RENDER_FAILED, 502, True, "文档渲染失败。"
    ),
    ErrorCode.FEATURE_UNAVAILABLE: _spec(
        ErrorCode.FEATURE_UNAVAILABLE, 501, False, "该功能在当前版本不可用。"
    ),

}


# ---------------------------------------------------------------------------
# ASR-R1 job codes (separate namespace)
# ---------------------------------------------------------------------------
class AsrErrorCode(str, Enum):
    """The fixed ASR-R1 job errors, kept out of the historical C02 table.

    The Phase-1 ``ErrorCode``/``ERROR_SPECS`` pair is frozen and asserted
    exactly by the existing C02 tests.  Adding job-only codes there would make
    those historical assertions fail; the ASR router projects this separate
    table through the same HTTP error envelope shape instead.
    """

    ASR_INPUT_TOO_LARGE = "asr_input_too_large"
    ASR_JOB_NOT_FOUND = "asr_job_not_found"
    ASR_PROTOCOL_UNSUPPORTED = "asr_protocol_unsupported"
    ASR_RESOURCE_LIMIT = "asr_resource_limit"
    ASR_DURATION_LIMIT = "asr_duration_limit"
    ASR_INVALID_AUDIO = "asr_invalid_audio"
    ASR_DEPENDENCY_UNAVAILABLE = "asr_dependency_unavailable"
    ASR_PROVIDER_AUTH = "asr_provider_auth"
    ASR_PROVIDER_BILLING = "asr_provider_billing"
    ASR_PROVIDER_LIMIT = "asr_provider_limit"
    ASR_RATE_LIMITED = "asr_rate_limited"
    ASR_CONFIG_CHANGED = "asr_config_changed"
    ASR_REQUEST_CONFLICT = "asr_request_conflict"
    ASR_INVALID_STATE = "asr_invalid_state"
    ASR_PUBLISH_CONFLICT = "asr_publish_conflict"


@dataclass(frozen=True)
class AsrErrorSpec:
    code: AsrErrorCode
    http_status: int
    retryable: bool
    message: str


def _asr_spec(code: AsrErrorCode, status: int, retryable: bool, message: str) -> AsrErrorSpec:
    return AsrErrorSpec(code=code, http_status=status, retryable=retryable, message=message)


ASR_ERROR_SPECS: Mapping[AsrErrorCode, AsrErrorSpec] = {
    AsrErrorCode.ASR_INPUT_TOO_LARGE: _asr_spec(
        AsrErrorCode.ASR_INPUT_TOO_LARGE, 400, False, "录音文件或本批录音超过允许的大小限制。"
    ),
    AsrErrorCode.ASR_JOB_NOT_FOUND: _asr_spec(
        AsrErrorCode.ASR_JOB_NOT_FOUND, 404, False, "当前科目的转写任务不存在。"
    ),
    AsrErrorCode.ASR_PROTOCOL_UNSUPPORTED: _asr_spec(
        AsrErrorCode.ASR_PROTOCOL_UNSUPPORTED, 400, False, "当前供应商协议暂不支持课堂长录音。"
    ),
    AsrErrorCode.ASR_RESOURCE_LIMIT: _asr_spec(
        AsrErrorCode.ASR_RESOURCE_LIMIT, 400, False, "媒体处理超过本任务资源预算。"
    ),
    AsrErrorCode.ASR_DURATION_LIMIT: _asr_spec(
        AsrErrorCode.ASR_DURATION_LIMIT, 400, False, "录音总时长超过本功能限额。"
    ),
    AsrErrorCode.ASR_INVALID_AUDIO: _asr_spec(
        AsrErrorCode.ASR_INVALID_AUDIO, 400, False, "音频损坏或格式不受支持。"
    ),
    AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE: _asr_spec(
        AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE, 503, False, "缺少经过配置的 ffmpeg/ffprobe 媒体工具。"
    ),
    AsrErrorCode.ASR_PROVIDER_AUTH: _asr_spec(
        AsrErrorCode.ASR_PROVIDER_AUTH, 502, False, "语音识别服务凭据或权限无效。"
    ),
    AsrErrorCode.ASR_PROVIDER_BILLING: _asr_spec(
        AsrErrorCode.ASR_PROVIDER_BILLING, 502, False,
        "语音识别供应商账户余额或计费状态异常，请在供应商平台处理后继续任务。"
    ),
    AsrErrorCode.ASR_PROVIDER_LIMIT: _asr_spec(
        AsrErrorCode.ASR_PROVIDER_LIMIT, 502, False, "语音识别服务仍拒绝细分后的录音片段。"
    ),
    AsrErrorCode.ASR_RATE_LIMITED: _asr_spec(
        AsrErrorCode.ASR_RATE_LIMITED, 429, True, "语音识别服务限流，退避等待已耗尽。"
    ),
    AsrErrorCode.ASR_CONFIG_CHANGED: _asr_spec(
        AsrErrorCode.ASR_CONFIG_CHANGED, 409, False, "恢复任务的模型或策略已变化，不能混用旧检查点。"
    ),
    AsrErrorCode.ASR_REQUEST_CONFLICT: _asr_spec(
        AsrErrorCode.ASR_REQUEST_CONFLICT, 409, False, "同一请求编号对应了不同的录音内容。"
    ),
    AsrErrorCode.ASR_INVALID_STATE: _asr_spec(
        AsrErrorCode.ASR_INVALID_STATE, 409, False, "当前任务状态不允许该操作。"
    ),
    AsrErrorCode.ASR_PUBLISH_CONFLICT: _asr_spec(
        AsrErrorCode.ASR_PUBLISH_CONFLICT, 409, False, "正式转写目标已被后来修改，未覆盖。"
    ),
}


class AsrOperationError(Exception):
    """An ASR job failure with the same safe projection fields as C02."""

    def __init__(
        self,
        code: AsrErrorCode | ErrorCode | str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        if isinstance(code, AsrErrorCode):
            resolved: AsrErrorCode | ErrorCode = code
        elif isinstance(code, ErrorCode):
            resolved = code
        else:
            try:
                resolved = AsrErrorCode(code)
            except ValueError:
                resolved = ErrorCode(code)
        self._spec = ASR_ERROR_SPECS[resolved] if isinstance(resolved, AsrErrorCode) else ERROR_SPECS[resolved]
        super().__init__(self._spec.message)
        self._code = resolved
        self.cause = cause

    @property
    def spec(self) -> AsrErrorSpec | ErrorSpec:
        return self._spec

    @property
    def code(self) -> AsrErrorCode | ErrorCode:
        return self._code

    @property
    def message(self) -> str:
        return self.spec.message

    @property
    def http_status(self) -> int:
        return self.spec.http_status

    @property
    def retryable(self) -> bool:
        return self.spec.retryable

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:  # pragma: no cover
        return f"AsrOperationError(code={self.code.value!r}, http_status={self.http_status})"


def asr_error(code: AsrErrorCode | str, *, cause: BaseException | None = None) -> AsrOperationError:
    return AsrOperationError(code, cause=cause)



def safe_message(text: str, *, fallback: str = "服务内部错误，请稍后重试。") -> str:
    """把文本压成符合 Schema 的单行长度的**格式**工具。

    它只改格式（压平控制字符、截断到 512），**不是**去密手段，也不能把任意输入变成
    安全文案。对外的固定安全消息一律取自 :data:`ERROR_SPECS`；本函数只用于服务端
    自造的诊断文本。
    """
    flattened = _CONTROL_CHARS.sub(" ", str(text)).strip()
    if not flattened:
        return fallback
    return flattened[:MAX_MESSAGE_LENGTH]


def _describe_override(value: Any) -> dict[str, Any]:
    """把被拒绝的调用参数记成不含原文的服务端诊断。

    字符串只留长度与摘要——32KiB 的 cause/消息不需要、也不应该原样挂在异常上。
    """
    if isinstance(value, str):
        return {
            "kind": "str",
            "length": len(value),
            "sha256": hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16],
        }
    if isinstance(value, (bool, int, float)) or value is None:
        return {"kind": type(value).__name__, "value": value}
    return {"kind": type(value).__name__}


class SubjectOperationError(Exception):
    """科目业务错误：对外可安全投影的异常。

    对外字段（``message`` / ``http_status`` / ``retryable``）**永远**取自
    :data:`ERROR_SPECS` 中该 code 的固定规格：

    * 调用方传入的 ``message`` 不会成为对外消息——即使它看起来"安全"；
    * ``http_status`` / ``retryable`` 会被校验，不匹配就归一到表里的值
      （因此 ``http_status=200`` 不会把 504 变成 200，``retryable="false"`` 也不会被
      ``bool()`` 隐式转成 ``True``）；
    * 被拒绝的值只以**摘要**形式记在 ``rejected_overrides`` 里供服务端诊断。

    ``cause`` 同样只在服务端保留，不进入 ``message``/``args``/任何投影。
    """

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        http_status: int,
        retryable: bool,
        cause: BaseException | None = None,
    ) -> None:
        resolved = ErrorCode(code) if not isinstance(code, ErrorCode) else code
        spec = ERROR_SPECS[resolved]

        rejected: dict[str, Any] = {}
        if not isinstance(message, str) or message != spec.message:
            rejected["message"] = _describe_override(message)
        if (not isinstance(http_status, int) or isinstance(http_status, bool)
                or http_status != spec.http_status):
            rejected["http_status"] = _describe_override(http_status)
        if retryable is not spec.retryable:
            rejected["retryable"] = _describe_override(retryable)

        super().__init__(spec.message)
        self._code = resolved
        self.cause = cause
        self.rejected_overrides = rejected

    def __repr__(self) -> str:  # pragma: no cover - 明确不暴露 cause/被拒参数
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"http_status={self.http_status}, retryable={self.retryable})"
        )

    @property
    def spec(self) -> ErrorSpec:
        return ERROR_SPECS[self.code]

    @property
    def code(self) -> ErrorCode:
        return self._code

    @property
    def message(self) -> str:
        return self.spec.message

    @property
    def http_status(self) -> int:
        return self.spec.http_status

    @property
    def retryable(self) -> bool:
        return self.spec.retryable

    def __str__(self) -> str:
        return self.message


class SubjectOutputTruncated(SubjectOperationError):
    """模型输出被输出上限截断（C02 ``output_truncated``）。

    ``diagnostics`` 只留在服务端（finish_reason/token 计数），不进入任何对外投影。
    """

    def __init__(
        self,
        message: str | None = None,
        *,
        cause: BaseException | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        spec = ERROR_SPECS[ErrorCode.OUTPUT_TRUNCATED]
        self.diagnostics = dict(diagnostics or {})
        super().__init__(
            spec.code,
            message or spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )


class SubjectStorageError(Exception):
    """存储层错误基类；``corrupt`` 区分损坏与普通 IO 失败（C02/C01）。"""

    corrupt = False

    def __init__(self, message: str, *, path: Any = None, cause: BaseException | None = None) -> None:
        super().__init__(safe_message(message))
        self.message = safe_message(message)
        self.path = path
        self.cause = cause


class StorageCorruptError(SubjectStorageError):
    """JSON 损坏或顶层类型错误：不返回空集合，也不覆盖坏文件。"""

    corrupt = True


class StorageIOError(SubjectStorageError):
    """读取权限/写入等 IO 失败。"""

    corrupt = False


def subject_error(code: ErrorCode | str, *, cause: BaseException | None = None) -> SubjectOperationError:
    """用 C02 表中的固定投影构造错误（消息/状态/retryable 都来自表）。"""
    resolved = ErrorCode(code) if not isinstance(code, ErrorCode) else code
    spec = ERROR_SPECS[resolved]
    return SubjectOperationError(
        spec.code,
        spec.message,
        http_status=spec.http_status,
        retryable=spec.retryable,
        cause=cause,
    )


def _timeout_types() -> tuple[type[BaseException], ...]:
    """**真实**的超时异常类型（按继承关系，不按类名）。

    ``asyncio.TimeoutError`` 在 3.11+ 就是内建 ``TimeoutError``，去重后保留一份。
    httpx 已随项目安装（ASR 等在用），它的 ``TimeoutException`` 是独立的超时基类，
    因此显式列出——不是为了猜。
    """
    import asyncio

    candidates: list[type[BaseException]] = [TimeoutError, asyncio.TimeoutError]
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx 是既有依赖
        pass
    else:
        candidates.append(httpx.TimeoutException)
    return tuple(dict.fromkeys(candidates))


def map_subject_exception(exc: BaseException) -> SubjectOperationError:
    """把服务端异常映射成 C02 投影；未知异常安全兜底为 ``internal_error``。

    顺序很重要：``LLMReasoningBudgetExhausted`` 是 ``LLMProviderError`` 的子类，
    而 ``LLMEmptyResponseError`` **不是** ``LLMProviderError`` 的子类，两者都必须
    在各自的基类之前判断。

    这里**不猜**：泛型 ``ValueError``/``TypeError``/``KeyError`` 以及类名里带
    "timeout" 的普通异常都不是领域依据，一律按 :data:`ErrorCode.INTERNAL_ERROR`
    处理。调用者若已确认是参数问题，应显式构造 ``INVALID_INPUT``。
    """
    if isinstance(exc, SubjectOperationError):
        return exc

    if isinstance(exc, SubjectStorageError):
        code = ErrorCode.STORAGE_CORRUPT if exc.corrupt else ErrorCode.STORAGE_IO
        return subject_error(code, cause=exc)

    from deeptutor.services.llm.exceptions import (
        LLMConfigError,
        LLMEmptyResponseError,
        LLMError,
        LLMModelNotFoundError,
        LLMParseError,
        LLMProviderTransportError,
        LLMReasoningBudgetExhausted,
        LLMTimeoutError,
    )

    if isinstance(exc, LLMReasoningBudgetExhausted):
        return subject_error(ErrorCode.REASONING_BUDGET_EXHAUSTED, cause=exc)
    if isinstance(exc, LLMEmptyResponseError):
        return subject_error(ErrorCode.EMPTY_MODEL_OUTPUT, cause=exc)
    if isinstance(exc, LLMTimeoutError) or isinstance(exc, _timeout_types()):
        return subject_error(ErrorCode.PROVIDER_TIMEOUT, cause=exc)
    if isinstance(exc, LLMParseError):
        return subject_error(ErrorCode.INVALID_MODEL_OUTPUT, cause=exc)
    if isinstance(exc, LLMProviderTransportError):
        return subject_error(ErrorCode.PROVIDER_UNAVAILABLE, cause=exc)
    if isinstance(exc, (LLMError, LLMConfigError, LLMModelNotFoundError)):
        # 其余 provider 侧故障（限流、鉴权、模型缺失、配置、熔断…）统一按
        # "provider 不可用" 处理：不声称成功，也不落学情/正式产物。
        return subject_error(ErrorCode.PROVIDER_UNAVAILABLE, cause=exc)

    return subject_error(ErrorCode.INTERNAL_ERROR, cause=exc)


def to_error_dict(error: SubjectOperationError) -> dict[str, Any]:
    """WS metadata / ToolResult metadata 共用的 error 数据。

    不改变任何既有事件协议，只提供同构的 ``{code, message, retryable}``。
    """
    return {
        "code": error.code.value,
        "message": error.message,
        "retryable": error.retryable,
    }


def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}


def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
    """WS terminal error / DONE failed 的 metadata 片段。"""
    return to_error_dict(error)


def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
    """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。

    调用者负责用它构造真正的 ToolResult；这里只固定失败语义与 error 数据，
    不返回任何 artifact URL。
    """
    return {"success": False, "metadata": {"error": to_error_dict(error)}}


__all__ = [
    "ERROR_SPECS",
    "ErrorCode",
    "ErrorSpec",
    "MAX_MESSAGE_LENGTH",
    "StorageCorruptError",
    "StorageIOError",
    "SubjectOperationError",
    "SubjectOutputTruncated",
    "SubjectStorageError",
    "map_subject_exception",
    "safe_message",
    "subject_error",
    "to_error_dict",
    "to_http_payload",
    "to_tool_result",
    "to_ws_error_metadata",
]
