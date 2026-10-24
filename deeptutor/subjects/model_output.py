"""严格的单对象模型 JSON 解析（C04）。

消费模型输出的唯一边界：**只接受一个完整的 JSON object**，允许它被完整的代码围栏
或已闭合的 think 标签包住。不做任何"先贪婪抠一段、失败就默认成功"的兜底——那是
本阶段要修掉的缺陷根因（批改默认 ``wrong``、考点默认空列表）。

刻意不做的事：

* 不校验批改/考点的字段语义——那是 P1-05 / P1-07 / P1-55 之后各卡的事；
* 不使用正则从正文里"抠"对象：花括号出现在字符串里时正则必然截错，这里用
  ``json.JSONDecoder.raw_decode`` 在**真实起始位置**解析，再要求剩余部分只有空白。

失败一律抛 :class:`ModelOutputError`（C02 ``invalid_model_output``，502/retryable），
并带一个服务端可诊断的 ``reason``；``reason`` 只进服务端，不出现在对外投影里。
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from deeptutor.subjects.errors import ERROR_SPECS, ErrorCode, SubjectOperationError

#: 解析失败的具名原因（服务端诊断用，绝不进入对外 payload）。
REASON_NOT_A_STRING = "not_a_string"
REASON_EMPTY = "empty_output"
REASON_UNCLOSED_THINK = "unclosed_think"
REASON_UNCLOSED_FENCE = "unclosed_fence"
REASON_TRAILING_AFTER_FENCE = "trailing_content_after_fence"
REASON_NOT_AN_OBJECT = "not_a_json_object"
REASON_INVALID_JSON = "invalid_json"
REASON_TRAILING_CONTENT = "trailing_content"
REASON_NON_FINITE_NUMBER = "non_finite_number"
REASON_DECODER_LIMIT = "decoder_limit"

#: ``<think ...>`` / ``<thinking ...>``；只认出现在正文最外层的情况。
#: 与 ``deeptutor/services/llm/utils.clean_thinking_tags`` 同一套标签约定。
#: 尾部的 ``(?:`(?!``))?`` 只吃掉"单独一个反引号"的包装：紧邻三反引号围栏时不吃，
#: 否则 ``</think>```json `` 会被啃掉围栏的第一个字符。
_THINK_OPEN = re.compile(r"`?<\s*(?P<tag>think(?:ing)?)\b[^>]*>(?:`(?!``))?", re.IGNORECASE)
_THINK_CLOSE_ANY = re.compile(
    r"`?<\s*/\s*think(?:ing)?\s*>(?:`(?!``))?", re.IGNORECASE
)


def _think_close_for(tag: str) -> re.Pattern[str]:
    """按**实际开标签名**构造闭标签：``<think>`` 只能由 ``</think>`` 收尾。"""
    return re.compile(
        r"`?<\s*/\s*" + re.escape(tag) + r"\s*>(?:`(?!``))?", re.IGNORECASE
    )


#: DeepSeek 系列在原始输出里用一个特殊 token 结束推理段，且**不一定有起始标签**
#: （形如 ``…推理正文<｜end▁of▁thinking｜>{"verdict": …}``）。它是显式的"推理已结束"
#: 标记，因此按已闭合 think 处理。
_REASONING_END = re.compile(
    r"<\s*[|\uff5c]\s*end\s*[\s_\u2581]*of\s*[\s_\u2581]*thinking\s*[|\uff5c]\s*>",
    re.IGNORECASE,
)

_FENCE = "```"


class ModelOutputError(SubjectOperationError):
    """模型输出不是单个完整 JSON 对象。

    ``reason`` 是服务端诊断字段；``message`` 始终是 C02 的固定安全消息。
    """

    def __init__(self, reason: str, *, cause: BaseException | None = None) -> None:
        spec = ERROR_SPECS[ErrorCode.INVALID_MODEL_OUTPUT]
        self.reason = reason
        super().__init__(
            spec.code,
            spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )


def _strip_think_blocks(text: str) -> str:
    """剥掉正文最前面一到多个**已闭合**的推理块；未闭合或错配直接失败。

    只剥最外层且位于开头的块：推理正文里出现的对象不会被当成结果。
    支持两种"已结束"写法：``<think>…</think>``（含 ``<thinking>``、单个反引号包裹）
    与 DeepSeek 的 ``…<｜end▁of▁thinking｜>`` 结束标记。闭标签必须与开标签同名。
    """
    current = text
    while True:
        stripped = current.lstrip()

        open_match = _THINK_OPEN.match(stripped)
        if open_match is not None:
            tag = open_match.group("tag")
            close = _think_close_for(tag).search(stripped, open_match.end())
            end_token = _REASONING_END.search(stripped, open_match.end())
            if close is not None and (end_token is None or close.start() <= end_token.start()):
                current = stripped[close.end() :]
                continue
            if end_token is not None:
                current = stripped[end_token.end() :]
                continue
            # 同名闭标签缺失：错配（</thinking> 收 <think>）与未闭合都在这里失败
            raise ModelOutputError(REASON_UNCLOSED_THINK)

        # 孤立的结束标签（上游清洗逻辑也会去掉）同样剥掉
        orphan = _THINK_CLOSE_ANY.match(stripped)
        if orphan is not None:
            current = stripped[orphan.end() :]
            continue

        end_token = _REASONING_END.search(stripped)
        if end_token is None:
            return stripped
        if stripped.startswith("{") or stripped.startswith(_FENCE):
            # 正文（对象或围栏）已经开始：此后再出现的标记只可能在 JSON 字符串里，
            # 不能当作推理结束去截断。
            return stripped
        current = stripped[end_token.end() :]


def _strip_code_fence(text: str) -> str:
    """剥掉一个**完整**的三反引号围栏（或单个反引号包装）。

    结束围栏取文本中**最后一个** ``` ，并要求其后只有空白。这样 JSON 字符串里合法的
    字面 ``` （例如 ``{"feedback": "示例 ```python ... ``` 保留原样"}``）不会被误当成
    结束位置。未闭合、或结束围栏之后还有非空内容，都直接失败。
    """
    if text.startswith(_FENCE):
        remainder = text[len(_FENCE) :]
        # A language header is a single identifier, not arbitrary first-line
        # content. In particular, never discard a JSON object before a newline.
        line, newline, body = remainder.partition("\n")
        if newline and re.fullmatch(r"[ \t]*[A-Za-z][A-Za-z0-9_.+-]*[ \t]*\r?", line):
            remainder = body
        close = remainder.rfind(_FENCE)
        if close == -1:
            raise ModelOutputError(REASON_UNCLOSED_FENCE)
        after = remainder[close + len(_FENCE) :]
        if after.strip():
            raise ModelOutputError(REASON_TRAILING_AFTER_FENCE)
        return remainder[:close].strip()

    # 单个反引号包装（`` `{"a": 1}` ``）与三反引号围栏区分对待
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1].strip()
    return text


def _reject_non_finite_constant(name: str) -> Any:
    """``json`` 的 ``parse_constant`` 钩子：``NaN``/``Infinity``/``-Infinity`` 一律拒绝。"""
    raise ModelOutputError(REASON_NON_FINITE_NUMBER)


def _ensure_finite(value: Any) -> None:
    """递归确认没有非有限浮点。

    ``1e400`` 这类字面量会被 ``float()`` 解成 ``inf`` 而**不报错**，因此解析成功之后
    还要检查一遍（含嵌套对象/数组）。
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ModelOutputError(REASON_NON_FINITE_NUMBER)
        return
    if isinstance(value, dict):
        for item in value.values():
            _ensure_finite(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _ensure_finite(item)


def _decode_single_object(text: str) -> dict[str, Any]:
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        raise ModelOutputError(REASON_NOT_AN_OBJECT)
    decoder = json.JSONDecoder(parse_constant=_reject_non_finite_constant)
    try:
        decoded, end = decoder.raw_decode(stripped)
    except ModelOutputError:
        raise
    except json.JSONDecodeError as exc:
        raise ModelOutputError(REASON_INVALID_JSON, cause=exc) from exc
    except RecursionError as exc:
        raise ModelOutputError(REASON_DECODER_LIMIT, cause=exc) from exc
    except ValueError as exc:
        # 例：超过 int 字符串位数上限的整数（默认 4300 位）在 int() 转换时抛 ValueError。
        raise ModelOutputError(REASON_INVALID_JSON, cause=exc) from exc
    if stripped[end:].strip():
        # 两个连续对象、对象后面跟正文等，都属于"不是一个完整对象"
        raise ModelOutputError(REASON_TRAILING_CONTENT)
    if not isinstance(decoded, dict):
        raise ModelOutputError(REASON_NOT_AN_OBJECT)
    try:
        _ensure_finite(decoded)
    except RecursionError as exc:  # pragma: no cover - 极端嵌套
        raise ModelOutputError(REASON_DECODER_LIMIT, cause=exc) from exc
    return decoded


def parse_model_object(raw: str) -> dict[str, Any]:
    """返回 ``raw`` 中**唯一**的 JSON 对象。

    Raises:
        ModelOutputError: 顶层不是对象、JSON 截断/非法、存在两个及以上候选、
            围栏或 think 未闭合、以及围栏/对象之后还有非空内容。
    """
    if not isinstance(raw, str):
        raise ModelOutputError(REASON_NOT_A_STRING)
    text = _strip_think_blocks(raw)
    if not text:
        raise ModelOutputError(REASON_EMPTY)
    text = _strip_code_fence(text)
    if not text.strip():
        raise ModelOutputError(REASON_EMPTY)
    return _decode_single_object(text)


__all__ = [
    "ModelOutputError",
    "REASON_DECODER_LIMIT",
    "REASON_EMPTY",
    "REASON_INVALID_JSON",
    "REASON_NON_FINITE_NUMBER",
    "REASON_NOT_A_STRING",
    "REASON_NOT_AN_OBJECT",
    "REASON_TRAILING_AFTER_FENCE",
    "REASON_TRAILING_CONTENT",
    "REASON_UNCLOSED_FENCE",
    "REASON_UNCLOSED_THINK",
    "parse_model_object",
]
