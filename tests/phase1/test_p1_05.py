"""P1-05 行为测试：批改结果验证（C05/C04/C02）。

目标：只有**完整且合法**的 verdict/feedback 才能产生批改结果；任何解析/校验/供应商
故障都必须作为具名 C02 错误抛出，绝不合成 ``wrong``。

覆盖的必证场景（每类都有正例基准 + 只改一个目标字段/故障点的反例）：

* correct/partial/wrong 三种成功，以及大小写/空白归一化；
* feedback 长度上限（历史 500 字符）与「空字符串是合法字符串」；
* 合法基准上分别缺 verdict / 缺 feedback / feedback 错类型 / verdict 错类型 /
  未知枚举 / 多个 JSON 候选对象 → ``invalid_model_output``；
* 通过**真实 generation 路径**（``factory.complete_response`` 替身返回真实
  ``TutorResponse``）验证 provider 故障、空响应、非空截断、推理预算耗尽都失败，
  且没有任何一条被记成 ``wrong``；
* 参数错误（空题目/空作答/非字符串）是 ``invalid_input``，不是模型故障；
* 真实供应商故障保留 cause，且异常文本不会进入 feedback。

最后一个用例是**有效坏对照**：把旧的宽松解析（贪婪 regex + 任何未知枚举→wrong）
重新实现一遍，证明上面这些"必须失败"的输入在旧行为下确实会变成 ``wrong`` ——
也就是说这些断言是承重的，而不是陪跑。

全部业务调用在 tmp 隔离根内，用 provider 替身，不读真实配置、不写真实数据。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from deeptutor.services.llm.exceptions import (
    LLMProviderTransportError,
    LLMTimeoutError,
)
from deeptutor.subjects import grading
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    map_subject_exception,
)
from deeptutor.subjects.model_output import ModelOutputError
from tests.phase1 import helpers

#: 唯一虚构标记：模型正文/异常文本都不允许出现在对外消息里。
FAKE_BODY_MARKER = "p1-05-FAKE-BODY-7c31ab-DO-NOT-LEAK"

_GOOD_JSON = '{"verdict": "correct", "feedback": "思路正确，注意最后一步的符号。"}'


def _install_cfg(monkeypatch: pytest.MonkeyPatch, *, model: str = "p1-05-fake-model"):
    """把一份虚构 LLM 配置放进真实的配置缓存（不读真实 settings/密钥）。"""
    import deeptutor.services.llm.config as config_mod

    cfg = config_mod.LLMConfig(
        model=model,
        api_key="p1-05-fake-key",
        base_url="http://127.0.0.1:9/v1",
    )
    monkeypatch.setattr(config_mod, "_LLM_CONFIG_CACHE", cfg)
    return cfg


def _run(coro):
    return asyncio.run(coro)


def _grade(question: str = "1+1=?", student_answer: str = "2", reference: str = "2"):
    return _run(grading.grade_answer(question, student_answer, reference))


def _code(exc: BaseException) -> ErrorCode:
    return map_subject_exception(exc).code


class _RaisingLLM(helpers.FakeLLMClient):
    """真实 generation 路径上的供应商故障替身。"""

    def __init__(self, error: BaseException) -> None:
        super().__init__("")
        self.error = error

    async def complete_response(self, prompt: str = "", **kwargs):
        self._record(prompt=prompt, **kwargs)
        raise self.error


# ---------------------------------------------------------------------------
# 解析与校验（纯函数边界）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", ["correct", "partial", "wrong"])
def test_each_verdict_is_accepted_with_its_feedback(p1_runtime: Path, verdict: str):
    result = grading.parse_grade(f'{{"verdict": "{verdict}", "feedback": "反馈内容"}}')

    assert result.verdict == verdict
    assert result.feedback == "反馈内容"
    assert result.correct is (verdict == "correct")


@pytest.mark.parametrize(
    ("raw_verdict", "expected"),
    [
        (" CORRECT ", "correct"),
        ("Partial", "partial"),
        ("\tWrOnG\n", "wrong"),
        ("correct", "correct"),
    ],
)
def test_verdict_is_normalised_by_strip_and_lower(
    p1_runtime: Path, raw_verdict: str, expected: str
):
    import json

    raw = json.dumps({"verdict": raw_verdict, "feedback": "f"})
    result = grading.parse_grade(raw)

    assert result.verdict == expected


def test_feedback_keeps_the_historical_500_char_cap(p1_runtime: Path):
    long_feedback = "甲" * 600

    result = grading.parse_grade(f'{{"verdict": "wrong", "feedback": "{long_feedback}"}}')

    assert len(result.feedback) == grading.FEEDBACK_MAX_CHARS == 500
    assert result.feedback == "甲" * 500


def test_an_empty_feedback_string_is_still_a_string(p1_runtime: Path):
    """C05 只要求 feedback 是字符串，没有约定新的非空限制。"""
    result = grading.parse_grade('{"verdict": "correct", "feedback": ""}')

    assert result.feedback == ""


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "normal\ud800text"])
def test_feedback_must_be_serializable_as_utf8(p1_runtime, value):
    raw = json.dumps({"verdict": "wrong", "feedback": value})
    with pytest.raises(SubjectOperationError) as error:
        grading.parse_grade(raw)
    assert map_subject_exception(error.value).code is ErrorCode.INVALID_MODEL_OUTPUT


def test_paired_surrogate_and_real_unicode_feedback_are_accepted(p1_runtime):
    result = grading.parse_grade('{"verdict":"wrong","feedback":"中文 \\ud83d\\ude42"}')
    assert result.feedback == "中文 🙂"


def test_unknown_model_fields_are_ignored(p1_runtime: Path):
    result = grading.parse_grade(
        '{"verdict": "partial", "feedback": "f", "confidence": 0.4, "extra": {"a": 1}}'
    )

    assert result.verdict == "partial"


@pytest.mark.parametrize(
    "raw",
    [
        '{"feedback": "没有 verdict"}',
        '{"verdict": "correct"}',
    ],
)
def test_a_missing_required_field_is_invalid_model_output(p1_runtime: Path, raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        grading.parse_grade(raw)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "feedback",
    ['{"a": 1}', "5", "null", '["分条反馈"]', "true"],
)
def test_a_non_string_feedback_is_invalid_model_output(p1_runtime: Path, feedback: str):
    with pytest.raises(ModelOutputError) as excinfo:
        grading.parse_grade(f'{{"verdict": "correct", "feedback": {feedback}}}')

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("verdict", ["1", "null", '["correct"]', '{"v": "correct"}', "true"])
def test_a_non_string_verdict_is_not_coerced(p1_runtime: Path, verdict: str):
    with pytest.raises(ModelOutputError) as excinfo:
        grading.parse_grade(f'{{"verdict": {verdict}, "feedback": "f"}}')

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("verdict", ["maybe", "", "  ", "correctish", "对", "correctly"])
def test_an_unknown_verdict_enum_is_invalid_model_output(p1_runtime: Path, verdict: str):
    with pytest.raises(ModelOutputError) as excinfo:
        grading.parse_grade(f'{{"verdict": "{verdict}", "feedback": "f"}}')

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


def test_multiple_json_candidates_are_rejected(p1_runtime: Path):
    raw = '{"verdict": "correct", "feedback": "第一个"} {"verdict": "wrong", "feedback": "第二个"}'

    with pytest.raises(ModelOutputError) as excinfo:
        grading.parse_grade(raw)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"verdict": "correct", "feedback": "截断在中间"\n```',
        '{"verdict": "correct", "feedback": "未闭合',
        "这不是 JSON",
        "",
        "   ",
    ],
)
def test_unusable_bodies_are_rejected(p1_runtime: Path, raw: str):
    with pytest.raises(SubjectOperationError) as excinfo:
        grading.parse_grade(raw)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("raw", ["[]", "null", "3", '"verdict"'])
def test_a_non_object_toplevel_is_rejected(p1_runtime: Path, raw: str):
    with pytest.raises(SubjectOperationError) as excinfo:
        grading.parse_grade(raw)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


def test_a_valid_fenced_and_think_wrapped_object_is_accepted(p1_runtime: Path):
    """合法围栏/思考块包装仍然可用（C04 允许），复用同一解析器。"""
    raw = f"<think>先判断等价变换</think>\n```json\n{_GOOD_JSON}\n```"

    result = grading.parse_grade(raw)

    assert result.verdict == "correct"


def test_rejection_never_echoes_the_model_body(p1_runtime: Path):
    raw = f'{{"verdict": "{FAKE_BODY_MARKER}", "feedback": "f"}}'

    with pytest.raises(SubjectOperationError) as excinfo:
        grading.parse_grade(raw)

    error = map_subject_exception(excinfo.value)
    assert error.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert error.http_status == 502
    assert error.retryable is True
    assert FAKE_BODY_MARKER not in error.message
    assert FAKE_BODY_MARKER not in str(excinfo.value)


# ---------------------------------------------------------------------------
# 真实 generation 路径
# ---------------------------------------------------------------------------
def test_success_goes_through_the_real_generation_path(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = _GOOD_JSON

    result = _grade(question="求导数", student_answer="2x", reference="2x")

    assert result.verdict == "correct"
    assert result.feedback == "思路正确，注意最后一步的符号。"
    # 真实路径：替身装在 factory.complete_response 上，被 generation 真正调用过。
    assert p1_llm.call_count == 1
    prompt = p1_llm.calls[0].payload["prompt"]
    assert "求导数" in prompt
    assert "2x" in prompt
    assert p1_llm.calls[0].payload["system_prompt"] == grading.SYSTEM_PROMPT
    # 预算沿用既有 LLM_MAX_TOKENS，没有被本卡改动。
    from deeptutor.subjects import LLM_MAX_TOKENS

    assert p1_llm.calls[0].payload["max_tokens"] == LLM_MAX_TOKENS


def test_the_prompt_carries_question_student_answer_and_reference(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    prompt = grading.build_prompt("题目正文", "学生作答正文", "参考答案正文")

    assert "题目：题目正文" in prompt
    assert "学生作答：学生作答正文" in prompt
    assert "参考答案：参考答案正文" in prompt


def test_the_reference_line_is_omitted_when_empty(p1_runtime: Path):
    prompt = grading.build_prompt("题目正文", "学生作答正文")

    assert "参考答案" not in prompt
    assert "学生作答：学生作答正文" in prompt


def test_the_model_verdict_is_normalised_through_the_real_path(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = '{"verdict": "  PARTIAL ", "feedback": "部分正确"}'

    result = _grade()

    assert result.verdict == "partial"
    assert result.correct is False


@pytest.mark.parametrize(
    ("text", "finish_reason", "usage", "expected"),
    [
        ("", "stop", None, ErrorCode.EMPTY_MODEL_OUTPUT),
        ("   ", "stop", None, ErrorCode.EMPTY_MODEL_OUTPUT),
        ("", "length", {"completion_tokens": 16000}, ErrorCode.REASONING_BUDGET_EXHAUSTED),
        ("", "max_tokens", None, ErrorCode.REASONING_BUDGET_EXHAUSTED),
        (
            '{"verdict": "cor',
            "length",
            {"completion_tokens": 16000},
            ErrorCode.OUTPUT_TRUNCATED,
        ),
        (
            '{"verdict": "correct", "feedback": "半篇',
            "max_output_tokens",
            None,
            ErrorCode.OUTPUT_TRUNCATED,
        ),
    ],
)
def test_generation_failures_are_typed_and_never_become_wrong(
    p1_runtime: Path,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    finish_reason: str,
    usage,
    expected: ErrorCode,
):
    _install_cfg(monkeypatch)
    p1_llm.response = text
    p1_llm.finish_reason = finish_reason
    p1_llm.usage = usage

    with pytest.raises(SubjectOperationError) as excinfo:
        _grade()

    error = map_subject_exception(excinfo.value)
    assert error.code is expected
    assert error.http_status in (502, 504)
    assert error.retryable is True
    # 关键：没有返回值，因此调用方不可能拿到一个"保守的 wrong"。
    assert p1_llm.call_count == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMProviderTransportError("connect refused"), ErrorCode.PROVIDER_UNAVAILABLE),
        (LLMTimeoutError("timed out"), ErrorCode.PROVIDER_TIMEOUT),
    ],
)
def test_provider_failures_are_typed_and_keep_their_cause(
    p1_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected: ErrorCode,
):
    _install_cfg(monkeypatch)
    raiser = _RaisingLLM(error)
    helpers.install_provider_stubs(monkeypatch, llm=raiser)

    with pytest.raises(SubjectOperationError) as excinfo:
        _grade()

    mapped = map_subject_exception(excinfo.value)
    assert mapped.code is expected
    assert mapped.cause is error
    assert raiser.call_count == 1


def test_an_unexpected_provider_error_is_internal_error_with_the_real_cause(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    original = RuntimeError(f"unexpected {FAKE_BODY_MARKER}")
    helpers.install_provider_stubs(monkeypatch, llm=_RaisingLLM(original))

    with pytest.raises(SubjectOperationError) as excinfo:
        _grade()

    mapped = map_subject_exception(excinfo.value)
    assert mapped.code is ErrorCode.INTERNAL_ERROR
    assert mapped.cause is original
    assert FAKE_BODY_MARKER not in mapped.message
    assert FAKE_BODY_MARKER not in str(excinfo.value)


def test_a_provider_error_text_never_becomes_feedback(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """旧实现把 str(exc) 拼进 feedback；现在故障必须抛出且不带原文。"""
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
        monkeypatch, llm=_RaisingLLM(LLMProviderTransportError(f"泄漏标记 {FAKE_BODY_MARKER}"))
    )

    with pytest.raises(SubjectOperationError):
        _grade()

    # 没有 GradeResult 产生 → 不可能有 feedback 承载异常文本。
    assert not hasattr(grading, "_last_result")


@pytest.mark.parametrize(
    ("question", "student_answer", "reference"),
    [
        ("", "2", ""),
        ("   ", "2", ""),
        (None, "2", ""),
        (5, "2", ""),
        ("1+1=?", "", ""),
        ("1+1=?", "   ", ""),
        ("1+1=?", None, ""),
        ("1+1=?", "2", 7),
    ],
)
def test_caller_parameter_errors_are_invalid_input_and_do_not_call_the_model(
    p1_runtime: Path,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    question,
    student_answer,
    reference,
):
    _install_cfg(monkeypatch)

    with pytest.raises(SubjectOperationError) as excinfo:
        _grade(question=question, student_answer=student_answer, reference=reference)

    assert _code(excinfo.value) is ErrorCode.INVALID_INPUT
    assert p1_llm.call_count == 0


def test_grading_does_not_touch_the_subject_tree(p1_runtime: Path, p1_providers, p1_llm, monkeypatch):
    """grading 模块没有磁盘副作用：判分成功也不写任何学科文件。"""
    from deeptutor.subjects import store

    _install_cfg(monkeypatch)
    subject = store.create_subject("批改科目")
    subject_root = store.subject_dir(subject["id"])
    before = helpers.tree_digest(subject_root)
    p1_llm.response = _GOOD_JSON

    _grade()

    assert helpers.tree_digest(subject_root) == before
    assert not (subject_root / "wrong_book.json").exists()


# ---------------------------------------------------------------------------
# 有效坏对照：证明上面的拒绝断言是承重的
# ---------------------------------------------------------------------------
def _legacy_grade(raw: str) -> str:
    """旧 ``_ai_grade`` 的解析行为（贪婪 regex、未知枚举→wrong、异常→wrong）。"""
    import json
    import re

    text = raw.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return "wrong"
    try:
        data = json.loads(match.group(0))
    except Exception:
        return "wrong"
    verdict = str(data.get("verdict", "wrong")).lower()
    if verdict not in ("correct", "partial", "wrong"):
        verdict = "wrong"
    return verdict


def test_bad_control_the_legacy_parser_turned_every_rejection_into_wrong(p1_runtime: Path):
    """坏对照：旧解析对这些输入**从不报错**，而是伪造一个 verdict。"""
    rejected_inputs = [
        '{"feedback": "缺 verdict"}',                                   # → wrong
        '{"verdict": "correct"}',                                       # → 伪造 correct
        '{"verdict": "correct", "feedback": {"a": 1}}',                 # → 伪造 correct
        '{"verdict": 1, "feedback": "f"}',                              # → wrong
        '{"verdict": "maybe", "feedback": "f"}',                        # → wrong
        '{"verdict": "correct", "feedback": "a"} {"verdict": "wrong", "feedback": "b"}',
        "",                                                             # → wrong
        '{"verdict": "cor',                                             # → wrong
    ]

    legacy_outcomes = [_legacy_grade(raw) for raw in rejected_inputs]

    # 旧行为：没有异常，任何输入都得到一个 verdict；其中 6 条直接变成 wrong
    # （"正确但被截断"会被记成答错），另 2 条伪造出 correct。
    assert all(outcome in ("correct", "partial", "wrong") for outcome in legacy_outcomes)
    assert legacy_outcomes.count("wrong") == 6
    assert legacy_outcomes[1] == "correct" and legacy_outcomes[2] == "correct"

    for raw in rejected_inputs:
        with pytest.raises(SubjectOperationError):
            grading.parse_grade(raw)  # 新行为：拒绝，绝不合成 verdict
