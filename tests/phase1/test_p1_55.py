"""P1-55 行为测试：严格的单对象模型 JSON 解析（C04/C02）。

正向：纯对象、完整 JSON 代码围栏、单行围栏、已结束推理段之后的正文。

反向（每条都只从合法基准改一个点）：

* 两个连续对象 / 对象后跟正文 -> ``trailing_content``；
* 多个候选对象（围栏里两个）-> ``trailing_content``；
* 截断 JSON -> ``invalid_json``；
* 未闭合围栏 / 未闭合 think -> 各自具名原因；
* 顶层 array / null / scalar / 数字 -> ``not_a_json_object``；
* think 正文里的对象**不能**被当成结果。

另证：字符串内部的花括号、结束标签、代码围栏等合法内容不会被贪婪截断。
失败一律是 C02 ``invalid_model_output``，对外投影不含原始模型文本。

推理标签一律用**显式转义**拼出来（``_LT`` / ``_GT``），不写字面量：这样夹具的字节
不依赖编辑器或任何中间环节对标签的处理。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from deeptutor.subjects.errors import ErrorCode, map_subject_exception, to_http_payload
from deeptutor.subjects.model_output import (
    REASON_DECODER_LIMIT,
    REASON_EMPTY,
    REASON_INVALID_JSON,
    REASON_NON_FINITE_NUMBER,
    REASON_NOT_A_STRING,
    REASON_NOT_AN_OBJECT,
    REASON_TRAILING_AFTER_FENCE,
    REASON_TRAILING_CONTENT,
    REASON_UNCLOSED_FENCE,
    REASON_UNCLOSED_THINK,
    ModelOutputError,
    parse_model_object,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 唯一虚构标记：模型原文不得出现在任何对外投影里。
FAKE_MODEL_TEXT = "p1-55-FAKE-MODEL-TEXT-2a7f4c9e-DO-NOT-LEAK"

# --- 推理标签（显式转义构造） ---------------------------------------------
_LT = "\x3c"
_GT = "\x3e"
OPEN_THINK = _LT + "think" + _GT
CLOSE_THINK = _LT + "/think" + _GT
OPEN_THINKING = _LT + "thinking" + _GT
CLOSE_THINKING = _LT + "/thinking" + _GT
#: DeepSeek 的推理结束标记：推理正文 + 该 token，其后才是答案正文。
END_OF_THINKING = _LT + "\uff5cend\u2581of\u2581thinking\uff5c" + _GT


def _reason(exc: pytest.ExceptionInfo[ModelOutputError]) -> str:
    return exc.value.reason


# ---------------------------------------------------------------------------
# 正向
# ---------------------------------------------------------------------------
def test_plain_object_is_parsed():
    assert parse_model_object('{"verdict": "correct", "feedback": "好"}') == {
        "verdict": "correct",
        "feedback": "好",
    }


def test_surrounding_whitespace_is_tolerated():
    assert parse_model_object('\n\n  {"points": []}\n\n') == {"points": []}


def test_complete_json_fence_is_parsed():
    raw = '```json\n{"points": [{"content": "洛必达法则"}]}\n```'
    assert parse_model_object(raw) == {"points": [{"content": "洛必达法则"}]}


def test_complete_bare_fence_is_parsed():
    raw = '```\n{"verdict": "wrong"}\n```'
    assert parse_model_object(raw) == {"verdict": "wrong"}


def test_single_line_fence_is_parsed():
    assert parse_model_object('```{"a": 1}```') == {"a": 1}


def test_closed_think_block_before_the_body_is_stripped():
    raw = OPEN_THINK + "让我先分析一下题目。" + CLOSE_THINK + '\n{"verdict": "partial", "feedback": "部分正确"}'
    assert parse_model_object(raw) == {"verdict": "partial", "feedback": "部分正确"}


def test_closed_thinking_block_before_the_body_is_stripped():
    raw = OPEN_THINKING + "先看定义。" + CLOSE_THINKING + '\n{"a": 1}'
    assert parse_model_object(raw) == {"a": 1}


def test_multiple_closed_think_blocks_before_the_body_are_stripped():
    raw = (
        OPEN_THINK + "第一段" + CLOSE_THINK
        + OPEN_THINKING + "第二段" + CLOSE_THINKING
        + '\n{"a": 1}'
    )
    assert parse_model_object(raw) == {"a": 1}


def test_orphan_closing_tag_is_stripped():
    assert parse_model_object(CLOSE_THINK + '{"a": 1}') == {"a": 1}


def test_think_block_then_fence_is_parsed():
    raw = OPEN_THINK + "推理" + CLOSE_THINK + '\n```json\n{"points": []}\n```'
    assert parse_model_object(raw) == {"points": []}


def test_deepseek_end_of_thinking_token_terminates_the_reasoning_block():
    """DeepSeek 的结束 token 本身就是"推理已结束"，其后是正文。"""
    raw = "让我先分析一下题目。" + END_OF_THINKING + '\n{"verdict": "partial"}'
    assert parse_model_object(raw) == {"verdict": "partial"}


def test_deepseek_end_token_works_even_when_reasoning_contains_braces():
    raw = (
        "我先试一个 " + '{"trap": true}' + " 但这不是答案"
        + END_OF_THINKING + '{"answer": 42}'
    )
    assert parse_model_object(raw) == {"answer": 42}


def test_deepseek_end_token_after_an_unclosed_think_open_tag():
    raw = OPEN_THINK + "推理还没写完" + END_OF_THINKING + '{"a": 1}'
    assert parse_model_object(raw) == {"a": 1}


# ---------------------------------------------------------------------------
# think 正文与 JSON 分离
# ---------------------------------------------------------------------------
def test_objects_inside_think_are_not_returned():
    raw = OPEN_THINK + '我先试一个 {"trap": true} 但这不是答案' + CLOSE_THINK + '{"answer": 42}'
    result = parse_model_object(raw)

    assert result == {"answer": 42}
    assert "trap" not in result
    assert "我先试一个" not in json.dumps(result, ensure_ascii=False)


def test_reasoning_before_the_end_token_is_not_returned():
    raw = '推理里出现 {"trap": true}' + END_OF_THINKING + '{"answer": 42}'
    assert parse_model_object(raw) == {"answer": 42}


def test_think_only_payload_is_rejected_as_empty():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(OPEN_THINK + "只有思考，没有正文" + CLOSE_THINK)
    assert _reason(excinfo) == REASON_EMPTY


# ---------------------------------------------------------------------------
# 反向：多个候选 / 尾随内容
# ---------------------------------------------------------------------------
def test_two_consecutive_objects_are_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('{"a": 1}{"b": 2}')
    assert _reason(excinfo) == REASON_TRAILING_CONTENT


def test_object_followed_by_prose_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('{"a": 1}\n希望这个答案对你有帮助。')
    assert _reason(excinfo) == REASON_TRAILING_CONTENT


def test_two_objects_inside_a_fence_are_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('```json\n{"a": 1}\n{"b": 2}\n```')
    assert _reason(excinfo) == REASON_TRAILING_CONTENT


def test_content_after_the_closing_fence_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('```json\n{"a": 1}\n```\n额外说明')
    assert _reason(excinfo) == REASON_TRAILING_AFTER_FENCE


def test_prose_before_an_object_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('好的，下面是答案：{"a": 1}')
    assert _reason(excinfo) == REASON_NOT_AN_OBJECT


# ---------------------------------------------------------------------------
# 反向：截断 / 未闭合
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1',
        '{"a": ',
        '{"a": 1, "b": [1, 2',
        "{",
    ],
)
def test_truncated_json_is_rejected(raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_INVALID_JSON


def test_unclosed_fence_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object('```json\n{"a": 1}')
    assert _reason(excinfo) == REASON_UNCLOSED_FENCE


def test_unclosed_think_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(OPEN_THINK + '还没想完 {"a": 1}')
    assert _reason(excinfo) == REASON_UNCLOSED_THINK


def test_unclosed_think_before_a_fence_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(OPEN_THINK + '没闭合\n```json\n{"a": 1}\n```')
    assert _reason(excinfo) == REASON_UNCLOSED_THINK


def test_unclosed_thinking_tag_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(OPEN_THINKING + '没闭合 {"a": 1}')
    assert _reason(excinfo) == REASON_UNCLOSED_THINK


# ---------------------------------------------------------------------------
# 反向：错误顶层类型
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "[1, 2, 3]",
        "[]",
        "null",
        "true",
        "42",
        "3.14",
        '"just a string"',
        "```json\n[{\"a\": 1}]\n```",
        "```json\nnull\n```",
    ],
)
def test_wrong_top_level_type_is_rejected(raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_NOT_AN_OBJECT


@pytest.mark.parametrize("raw", ["", "   ", "\n\n"])
def test_blank_payload_is_rejected(raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_EMPTY


def test_non_string_input_is_rejected():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(b'{"a": 1}')  # type: ignore[arg-type]
    assert _reason(excinfo) == REASON_NOT_A_STRING


# ---------------------------------------------------------------------------
# 合法内容不得被贪婪截断
# ---------------------------------------------------------------------------
def test_braces_inside_strings_are_not_mis_truncated():
    raw = '{"pattern": "}{", "nested": {"x": [1, 2]}, "tail": "}}"}'
    assert parse_model_object(raw) == {
        "pattern": "}{",
        "nested": {"x": [1, 2]},
        "tail": "}}",
    }


def test_end_of_thinking_token_inside_a_json_string_is_left_alone():
    raw = '{"text": "推理标记 ' + END_OF_THINKING + ' 只是字面量"}'
    assert parse_model_object(raw) == {"text": "推理标记 " + END_OF_THINKING + " 只是字面量"}


def test_closing_tag_inside_a_json_string_is_left_alone():
    raw = '{"text": "文中出现 ' + CLOSE_THINK + ' 字面量"}'
    assert parse_model_object(raw) == {"text": "文中出现 " + CLOSE_THINK + " 字面量"}


def test_fence_inside_a_json_string_is_left_alone():
    raw = '{"text": "正文里有 ``` 这样的字面量"}'
    assert parse_model_object(raw) == {"text": "正文里有 ``` 这样的字面量"}


def test_escaped_quotes_and_newlines_are_preserved():
    raw = '{"feedback": "第一行\\n第二行 \\"引用\\""}'
    assert parse_model_object(raw) == {"feedback": '第一行\n第二行 "引用"'}


# ---------------------------------------------------------------------------
# 失败必须是具名的 invalid_model_output，且不泄露模型原文
# ---------------------------------------------------------------------------
def test_failure_is_a_named_invalid_model_output_error():
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object("not json at all")
    error = excinfo.value

    assert error.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert error.http_status == 502
    assert error.retryable is True

    payload = to_http_payload(error)
    assert payload["error"]["code"] == "invalid_model_output"
    assert isinstance(payload["detail"], str)
    # 诊断原因保留在服务端
    assert error.reason == REASON_NOT_AN_OBJECT


def test_error_projection_never_contains_the_raw_model_text():
    raw = '{"a": 1}' + FAKE_MODEL_TEXT
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)

    error = excinfo.value
    for surface in (
        json.dumps(to_http_payload(error), ensure_ascii=False),
        json.dumps(map_subject_exception(error).message, ensure_ascii=False),
        repr(error),
        str(error),
    ):
        assert FAKE_MODEL_TEXT not in surface


def test_raw_text_is_not_stored_on_the_error():
    raw = '{"a": 1} trailing'
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    # 只保留 reason 与（可选的）底层 JSON 解析异常，不挂原始正文
    assert not hasattr(excinfo.value, "raw")
    assert excinfo.value.reason == REASON_TRAILING_CONTENT


def test_multiple_candidates_are_never_silently_resolved():
    """没有"先抠一段后默认成功"的兜底：任何多候选都必须失败。"""
    for raw in (
        '{"verdict": "correct"}\n{"verdict": "wrong"}',
        '```json\n{"verdict": "correct"}\n```\n```json\n{"verdict": "wrong"}\n```',
        '{"verdict": "correct"}{"verdict": "wrong"}',
    ):
        with pytest.raises(ModelOutputError):
            parse_model_object(raw)


# ---------------------------------------------------------------------------
# R3（rework01）：严格数字与具名解码失败
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize(
    "template",
    [
        '{"value": %s}',
        '{"nested": {"value": %s}}',
        '{"items": [1, %s, 2]}',
        '{"nested": {"items": [{"deep": %s}]}}',
    ],
)
def test_nonstandard_numeric_constants_are_rejected(constant: str, template: str):
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(template % constant)
    assert _reason(excinfo) == REASON_NON_FINITE_NUMBER


@pytest.mark.parametrize("number", ["1e400", "-1e400", "1e309"])
@pytest.mark.parametrize(
    "template",
    ['{"value": %s}', '{"nested": {"value": %s}}', '{"items": [%s]}'],
)
def test_numeric_overflow_does_not_become_infinity(number: str, template: str):
    """``float()`` 会把溢出字面量解成 inf 而不报错，必须在解析后按非有限拒绝。"""
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(template % number)
    assert _reason(excinfo) == REASON_NON_FINITE_NUMBER


def test_finite_numeric_values_remain_valid():
    result = parse_model_object(
        '{"value": 1e300, "nested": [3.14, 1, 0.8], "big": 1e-300, "text": "中文"}'
    )
    assert math.isfinite(result["value"])
    assert result["nested"] == [3.14, 1, 0.8]
    assert result["big"] > 0
    assert result["text"] == "中文"


def test_decoder_recursion_limit_is_a_named_model_failure():
    """先证明同一输入合法，再注入 decoder 的 RecursionError。

    不依赖"固定多少层嵌套必然触发限制"——那与解释器/平台相关，不是可移植的用例。
    """
    from unittest.mock import patch

    raw = '{"value": 1}'
    assert parse_model_object(raw) == {"value": 1}

    with patch.object(
        json.JSONDecoder, "raw_decode", side_effect=RecursionError("controlled decoder limit")
    ):
        with pytest.raises(ModelOutputError) as excinfo:
            parse_model_object(raw)
    assert _reason(excinfo) == REASON_DECODER_LIMIT


def test_decoder_integer_limit_is_a_named_model_failure():
    """5000 位整数在默认整数转换上限下抛 ValueError，必须转成具名模型错误。"""
    raw = '{"value":' + "9" * 5000 + "}"
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_INVALID_JSON


def test_parser_does_not_change_interpreter_limits():
    """生产 parser 不得靠改全局限制（或吞错）来"支持"超大输入。"""
    import sys

    before_int = sys.get_int_max_str_digits()
    before_recursion = sys.getrecursionlimit()

    with pytest.raises(ModelOutputError):
        parse_model_object('{"value":' + "9" * 5000 + "}")

    assert sys.get_int_max_str_digits() == before_int
    assert sys.getrecursionlimit() == before_recursion


def test_non_finite_numbers_are_rejected_in_fenced_and_think_wrapped_payloads():
    raw = OPEN_THINK + "thinking" + CLOSE_THINK + '\n```json\n{"v": NaN}\n```'
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_NON_FINITE_NUMBER


# ---------------------------------------------------------------------------
# R4（rework01）：外围包装不得吃掉合法正文
# ---------------------------------------------------------------------------
def test_literal_backticks_in_a_fenced_json_string_are_preserved():
    """合法的 JSON 字符串里可以有字面 ``` —— 结束围栏取最后一个。"""
    value = {"feedback": "示例代码 ```python print('x') ```，保留原样"}
    body = json.dumps(value, ensure_ascii=False)

    assert parse_model_object("```json\n" + body + "\n```") == value
    assert parse_model_object("```" + body + "```") == value
    assert parse_model_object("```\n" + body + "\n```") == value


def test_json_string_with_markdown_and_escapes_survives_every_wrapper():
    value = {
        "feedback": "第一行\n第二行 ```js\nconst a = 1;\n``` 还有 \\\"引号\\\" 与 {花括号}",
        "points": [],
    }
    body = json.dumps(value, ensure_ascii=False)

    for wrapper in (
        body,
        "```json\n" + body + "\n```",
        "```" + body + "```",
        OPEN_THINK + "reasoning" + CLOSE_THINK + "```json\n" + body + "\n```",
    ):
        assert parse_model_object(wrapper) == value


def test_closing_think_tag_must_match_the_opening_tag():
    for opening, closing in (
        (OPEN_THINK, CLOSE_THINKING),
        (OPEN_THINKING, CLOSE_THINK),
        (OPEN_THINKING, CLOSE_THINKING.replace("thinking", "think")),
    ):
        with pytest.raises(ModelOutputError) as excinfo:
            parse_model_object(opening + "reasoning" + closing + '{"answer": 42}')
        assert _reason(excinfo) == REASON_UNCLOSED_THINK


def test_matching_think_tags_still_work():
    assert parse_model_object(OPEN_THINK + "r" + CLOSE_THINK + '{"answer": 42}') == {"answer": 42}
    assert parse_model_object(OPEN_THINKING + "r" + CLOSE_THINKING + '{"answer": 42}') == {
        "answer": 42
    }


def test_valid_closed_think_then_a_fence_is_still_supported():
    """``</think>`` 紧邻 ```json 时，闭标签不能吃掉围栏的第一个反引号。"""
    raw = OPEN_THINK + '{"trap": 1}' + CLOSE_THINK + '```json\n{"answer": 42}\n```'
    assert parse_model_object(raw) == {"answer": 42}


def test_single_backtick_wrapped_object_is_parsed():
    assert parse_model_object('`{"a": 1}`') == {"a": 1}


def test_fenced_json_after_a_closed_think_keeps_its_own_language_tag():
    raw = OPEN_THINK + "r" + CLOSE_THINK + '```json\n{"a": 1}\n```'
    assert parse_model_object(raw) == {"a": 1}


def test_unclosed_fence_after_a_closed_think_is_still_rejected():
    raw = OPEN_THINK + "r" + CLOSE_THINK + '```json\n{"a": 1}'
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_UNCLOSED_FENCE


def test_fence_surrounded_payload_with_trailing_prose_is_still_rejected():
    raw = "```json\n" + json.dumps({"a": 1}) + "\n```\n希望有帮助"
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_TRAILING_AFTER_FENCE


def test_inline_multiline_fence_keeps_the_entire_object():
    value = {"first": "不能丢失", "second": 2}
    raw = "```" + json.dumps(value, ensure_ascii=False, indent=2) + "```"
    assert parse_model_object(raw) == value


def test_first_object_on_fence_opening_line_cannot_be_discarded():
    raw = '```{"discarded": true}\n{"accepted": true}\n```'
    with pytest.raises(ModelOutputError) as excinfo:
        parse_model_object(raw)
    assert _reason(excinfo) == REASON_TRAILING_CONTENT


def test_fence_language_header_is_metadata_not_a_free_form_prefix():
    assert parse_model_object('```python\n{"answer": 42}\n```') == {"answer": 42}
    raw = '```json {"discarded": true}\n{"accepted": true}\n```'
    with pytest.raises(ModelOutputError):
        parse_model_object(raw)
