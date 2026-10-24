"""P1-07 行为测试：考点 JSON 与直接引用证据（C06/C04/C02）。

目标：合法的「零考点」与检测失败必须分开；整轮候选的 evidence 必须是转写原文的直接
引用（只允许空白归一化）。

覆盖的必证场景：

* ``{"points": []}`` 是合法成功（真的是"没发现"），返回空列表 + 无警告；
* 缺 points、顶层/项/字段类型错误、坏 JSON、多候选 JSON、未知 level 全部失败
  （``invalid_model_output``），不返回"空成功"；
* evidence 不在原文（改写标点/词语/语义近似）→ **整轮**失败，不是部分成功；
* 中文空白差异（转写里有换行/多余空格）仍然算直接引用；
* 负向证据按确定性短语排除并给出 warnings 计数 —— 但排除之前先验证 schema 与引用：
  非法候选不能靠"负向过滤"蒙过去；
* provider / 预算耗尽 / 非空截断通过真实 generation 路径上抛，不变成 ``points=[]``；
* prompt 示例里的每条 evidence 都能在它自己的输入中逐字找到，且返回的 version 与实际
  发送的 prompt 一致（未知版本是调用参数错误）。

最后一个用例是**有效坏对照**：把旧的宽松解析重新实现一遍，证明这些坏输入在旧行为下
确实会变成"空成功"，即失败断言承重。

不联网、不用真实模型/密钥，全部在 tmp 隔离根内。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re

import pytest

from deeptutor.services.llm.exceptions import LLMProviderTransportError
from deeptutor.subjects import exam_detection as ed
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    map_subject_exception,
)
from deeptutor.subjects.model_output import ModelOutputError
from tests.phase1 import helpers

FAKE_BODY_MARKER = "p1-07-FAKE-BODY-9ab3f7-DO-NOT-LEAK"

TRANSCRIPT = (
    "今天我们讲洛必达法则。这个内容很重要，大家一定要重视起来，几乎年年都要用到。\n"
    "另外，泰勒展开的余项不用重点看，大家了解一下就行。\n"
    "去年期末考试最后一道大题就考的消元法，大家今年注意。"
)


def _install_cfg(monkeypatch: pytest.MonkeyPatch):
    import deeptutor.services.llm.config as config_mod

    cfg = config_mod.LLMConfig(
        model="p1-07-fake-model",
        api_key="p1-07-fake-key",
        base_url="http://127.0.0.1:9/v1",
    )
    monkeypatch.setattr(config_mod, "_LLM_CONFIG_CACHE", cfg)
    return cfg


def _points_json(*points: dict) -> str:
    return json.dumps({"points": list(points)}, ensure_ascii=False)


def _detect(transcript: str = TRANSCRIPT, **kwargs):
    return asyncio.run(ed.detect_points(transcript, **kwargs))


@pytest.mark.parametrize("position", ["top_level", "candidate_extra"])
def test_invalid_unicode_in_returned_raw_fails_before_http_publication(
    p1_runtime, p1_subjects, p1_route_client, p1_providers, p1_llm, monkeypatch, position
):
    from deeptutor.subjects import store

    _install_cfg(monkeypatch)
    point = {"content": "c", "level": "explicit", "evidence": "这个内容很重要", "kp": "k"}
    data = {"points": [point]}
    target = data if position == "top_level" else point
    target["extra"] = "合法🙂"
    valid_body = json.dumps(data, ensure_ascii=False)
    p1_llm.response = valid_body
    assert _detect()["raw"] == valid_body

    sid = next(iter(p1_subjects.values())).subject_id
    book = store.subject_dir(sid) / "exam_points.json"
    book.write_text("[]", encoding="utf-8")
    before = book.read_bytes()
    # The fields consumed by the detector remain valid. Only the ignored raw
    # text changes, and the previous implementation committed before HTTP500.
    p1_llm.response = valid_body.replace("合法🙂", "\ud800")
    response = p1_route_client.post(
        f"{helpers.ROUTE_PREFIX}/{sid}/exam-points/detect", data={"transcript": TRANSCRIPT}
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert book.read_bytes() == before


class _RaisingLLM(helpers.FakeLLMClient):
    def __init__(self, error: BaseException) -> None:
        super().__init__("")
        self.error = error

    async def complete_response(self, prompt: str = "", **kwargs):
        self._record(prompt=prompt, **kwargs)
        raise self.error


def _code(exc: BaseException) -> ErrorCode:
    return map_subject_exception(exc).code


@pytest.mark.parametrize("field", ["content", "evidence", "kp"])
def test_detection_strings_must_be_serializable_as_utf8(p1_runtime, field):
    candidate = {"content": "洛必达法则", "evidence": "这个内容很重要", "kp": "极限", "level": "emphasis"}
    assert ed.parse_points(_points_json(candidate), TRANSCRIPT)[0]
    candidate[field] = "\ud800"
    with pytest.raises(ModelOutputError) as error:
        ed.parse_points(_points_json(candidate), TRANSCRIPT)
    assert error.value.reason == f"{field}_invalid_unicode"


def test_real_unicode_in_detection_content_and_kp_remains_legal(p1_runtime):
    candidate = {"content": "中文 🙂", "evidence": "这个内容很重要", "kp": "极限 🙂", "level": "emphasis"}
    points, excluded = ed.parse_points(_points_json(candidate), TRANSCRIPT)
    assert points == [candidate]
    assert excluded == 0


# ---------------------------------------------------------------------------
# 合法基准：零考点 vs 检测失败
# ---------------------------------------------------------------------------
def test_an_empty_points_list_is_a_legal_success(p1_runtime: Path):
    points, excluded = ed.parse_points('{"points": []}', TRANSCRIPT)

    assert points == []
    assert excluded == 0


def test_a_valid_candidate_is_parsed_with_its_quote(p1_runtime: Path):
    raw = _points_json(
        {
            "content": "洛必达法则（整体重要性）",
            "level": "emphasis",
            "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到",
            "kp": "洛必达法则",
        }
    )

    points, excluded = ed.parse_points(raw, TRANSCRIPT)

    assert excluded == 0
    assert points == [
        {
            "content": "洛必达法则（整体重要性）",
            "level": "emphasis",
            "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到",
            "kp": "洛必达法则",
        }
    ]


def test_detect_points_returns_the_four_documented_keys(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(
        {
            "content": "消元法解方程组",
            "level": "explicit",
            "evidence": "去年期末考试最后一道大题就考的消元法",
            "kp": "消元法",
        }
    )

    result = _detect(term="2026春", source="lecture")

    assert set(result) == {"version", "points", "raw", "warnings"}
    assert result["version"] == ed.DETECT_PROMPT_VERSION
    assert result["warnings"] == []
    assert result["points"] == [
        {
            "content": "消元法解方程组",
            "level": "explicit",
            "evidence": "去年期末考试最后一道大题就考的消元法",
            "kp": "消元法",
            "term": "2026春",
            "source": "lecture",
            "anchor": "",
        }
    ]
    assert p1_llm.call_count == 1


def test_an_empty_detection_round_is_a_success_not_a_failure(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = '{"points": []}'

    result = _detect()

    assert result["points"] == []
    assert result["warnings"] == []
    assert result["raw"] == '{"points": []}'


# ---------------------------------------------------------------------------
# 失败：坏 JSON / 缺 points / 字段类型 / level
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        '{"points": []',
        "不是 JSON",
        "",
        "   ",
        '```json\n{"points": []}\n```\n多余内容',
        '{"points": []} {"points": []}',
    ],
)
def test_unusable_bodies_fail_instead_of_reporting_no_points(p1_runtime: Path, raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(raw, TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("raw", ["[]", "null", "3", '"points"'])
def test_a_non_object_toplevel_fails(p1_runtime: Path, raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(raw, TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("raw", ["{}", '{"candidates": []}', '{"point": []}'])
def test_a_missing_points_key_fails(p1_runtime: Path, raw: str):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(raw, TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("points", ['"x"', "{}", "5", "null", "true"])
def test_points_must_be_an_array(p1_runtime: Path, points: str):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(f'{{"points": {points}}}', TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("item", ['"x"', "5", "null", "[]", "true"])
def test_each_candidate_must_be_an_object(p1_runtime: Path, item: str):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(f'{{"points": [{item}]}}', TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "candidate",
    [
        {"level": "emphasis", "evidence": "这个内容很重要", "kp": "k"},  # 缺 content
        {"content": 5, "level": "emphasis", "evidence": "这个内容很重要", "kp": "k"},
        {"content": "  ", "level": "emphasis", "evidence": "这个内容很重要", "kp": "k"},
        {"content": "c", "level": "emphasis", "kp": "k"},  # 缺 evidence
        {"content": "c", "level": "emphasis", "evidence": {"a": 1}, "kp": "k"},
        {"content": "c", "level": "emphasis", "evidence": "   ", "kp": "k"},
        {"content": "c", "level": "emphasis", "evidence": "这个内容很重要"},  # 缺 kp
        {"content": "c", "level": "emphasis", "evidence": "这个内容很重要", "kp": 7},
        {"content": "c", "evidence": "这个内容很重要", "kp": "k"},  # 缺 level
        {"content": "c", "level": 3, "evidence": "这个内容很重要", "kp": "k"},
        {"content": "c", "level": None, "evidence": "这个内容很重要", "kp": "k"},
    ],
)
def test_a_malformed_candidate_field_fails_the_round(p1_runtime: Path, candidate: dict):
    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "level",
    [
        "inferred",  # 只是历史 manual 存储的兼容等级，检测不得产出它
        "maybe",
        "explicitly",
        "强调",
        "",
        "EXPLICIT",  # 精确枚举：不做 strip/lower 修错
        " Explicit ",
        "EMPHASIS",
        "emphasis\n",
        "explicit\t",
    ],
)
def test_a_level_outside_explicit_emphasis_fails(p1_runtime: Path, level: str):
    candidate = {
        "content": "c",
        "level": level,
        "evidence": "这个内容很重要",
        "kp": "k",
    }

    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT
    assert ed.DETECT_LEVELS == ("explicit", "emphasis")


@pytest.mark.parametrize("level", ["explicit", "emphasis"])
def test_only_the_exact_level_strings_are_accepted(p1_runtime: Path, level: str):
    """C06 的两个枚举值必须**原样**出现：不做大小写/空白归一化。"""
    candidate = {
        "content": "c",
        "level": level,
        "evidence": "这个内容很重要",
        "kp": "k",
    }

    points, _ = ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert points[0]["level"] == level


def test_a_candidate_with_an_empty_kp_is_still_legal(p1_runtime: Path):
    """kp 必须存在且为字符串，但空字符串是合法值（ExamCandidate 无 minLength）。"""
    candidate = {
        "content": "c",
        "level": "emphasis",
        "evidence": "这个内容很重要",
        "kp": "",
    }

    points, _ = ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert points[0]["kp"] == ""


def test_unknown_candidate_fields_are_ignored(p1_runtime: Path):
    candidate = {
        "content": "c",
        "level": "explicit",
        "evidence": "这个内容很重要",
        "kp": "k",
        "confidence": 0.9,
        "anchor": "00:12:30",
    }

    points, _ = ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert set(points[0]) == {"content", "level", "evidence", "kp"}


# ---------------------------------------------------------------------------
# 直接引用
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "evidence",
    [
        "这个内容很重要，大家一定要重视起来，几乎年年都要用到",  # 合法基准
        "这个内容很重要,大家一定要重视起来,几乎年年都要用到",  # 半角标点
        "这个内容很重要。大家一定要重视起来。几乎年年都要用到。",  # 改标点
        "这个内容很重要，大家一定要重视，几乎年年都要用到",  # 改词
        "教师强调了洛必达法则的重要性",  # 语义近似
        "洛必达法则很重要",  # 概括
        "这个内容非常重要",  # 近义词
    ],
)
def test_only_a_verbatim_quote_is_accepted(p1_runtime: Path, evidence: str):
    candidate = {"content": "c", "level": "emphasis", "evidence": evidence, "kp": "k"}
    legal = evidence == "这个内容很重要，大家一定要重视起来，几乎年年都要用到"

    if legal:
        points, _ = ed.parse_points(_points_json(candidate), TRANSCRIPT)
        assert points[0]["evidence"] == evidence
    else:
        with pytest.raises(ModelOutputError) as excinfo:
            ed.parse_points(_points_json(candidate), TRANSCRIPT)
        assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "evidence",
    [
        "这个内容很重要，大家一定要重视起来，几乎年年都要用到",
        "今天 我们 讲 洛必达法则",
        "去年期末考试最后一道大题就考的消元法",
    ],
)
def test_chinese_whitespace_differences_still_count_as_a_quote(
    p1_runtime: Path, evidence: str
):
    transcript = "今天\n我们 讲 洛必达法则。这个内容很重要，大家一定要重视起来，几乎年年都要用到。\n去年期末考试最后一道大题就考的消元法，大家今年注意。"
    candidate = {"content": "c", "level": "emphasis", "evidence": evidence, "kp": "k"}

    points, _ = ed.parse_points(_points_json(candidate), transcript)

    assert points[0]["evidence"] == evidence


def test_a_later_illegal_candidate_fails_the_whole_round(p1_runtime: Path):
    """不是部分成功：后段非法候选让整轮失败。"""
    raw = _points_json(
        {
            "content": "合法候选",
            "level": "emphasis",
            "evidence": "这个内容很重要",
            "kp": "k",
        },
        {
            "content": "坏候选",
            "level": "emphasis",
            "evidence": "这句原文里没有",
            "kp": "k",
        },
    )

    with pytest.raises(ModelOutputError) as excinfo:
        ed.parse_points(raw, TRANSCRIPT)

    assert _code(excinfo.value) is ErrorCode.INVALID_MODEL_OUTPUT


def test_a_non_quote_candidate_after_valid_ones_also_fails(p1_runtime: Path):
    raw = _points_json(
        {"content": "a", "level": "explicit", "evidence": "这个内容很重要", "kp": "k"},
        {"content": "b", "level": "emphasis", "evidence": "消元法的矩阵形式", "kp": "k"},
    )

    with pytest.raises(ModelOutputError):
        ed.parse_points(raw, TRANSCRIPT)


# ---------------------------------------------------------------------------
# 负向信号：确定性排除 + 计数，且不掩盖非法候选
# ---------------------------------------------------------------------------
def test_a_negative_phrase_candidate_is_excluded_with_a_warning(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(
        {
            "content": "泰勒展开余项",
            "level": "emphasis",
            "evidence": "泰勒展开的余项不用重点看",
            "kp": "泰勒展开",
        },
        {
            "content": "洛必达法则",
            "level": "emphasis",
            "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到",
            "kp": "洛必达法则",
        },
    )

    result = _detect()

    assert [p["content"] for p in result["points"]] == ["洛必达法则"]
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert warning["code"] == ed.WARNING_NEGATIVE_EVIDENCE
    assert warning["count"] == 1
    assert isinstance(warning["message"], str) and warning["message"]


@pytest.mark.parametrize(
    ("evidence", "phrase"),
    [
        ("这题不会考", "不会考"),
        ("泰勒展开的余项不用重点看", "不用重点看"),
        ("这一章不考", "不考"),
        ("大家了解即可", "了解即可"),
        ("这部分看看书就行", "看看书就行"),
    ],
)
def test_each_negative_phrase_excludes_its_candidate(p1_runtime: Path, evidence: str, phrase: str):
    transcript = f"课堂原文：{evidence}。"
    candidate = {"content": "c", "level": "emphasis", "evidence": evidence, "kp": "k"}

    points, excluded = ed.parse_points(_points_json(candidate), transcript)

    assert phrase in ed.NEGATIVE_PHRASES
    assert points == []
    assert excluded == 1


def test_multiple_negative_candidates_are_counted(p1_runtime: Path):
    transcript = "这句不考。那句也不用重点看。第三句了解即可。"
    raw = _points_json(
        {"content": "a", "level": "emphasis", "evidence": "这句不考", "kp": "k"},
        {"content": "b", "level": "emphasis", "evidence": "那句也不用重点看", "kp": "k"},
        {"content": "c", "level": "emphasis", "evidence": "第三句了解即可", "kp": "k"},
    )

    points, excluded = ed.parse_points(raw, transcript)

    assert points == []
    assert excluded == 3


def test_negative_filtering_does_not_hide_an_illegal_candidate(p1_runtime: Path):
    """被负向短语命中的候选，其 schema 与引用也必须先通过。"""
    # 1) level 非法 + 负向短语
    bad_level = _points_json(
        {"content": "a", "level": "inferred", "evidence": "这句不考", "kp": "k"}
    )
    with pytest.raises(ModelOutputError):
        ed.parse_points(bad_level, "这句不考。")

    # 2) 引用不在原文 + 负向短语
    bad_quote = _points_json(
        {"content": "a", "level": "emphasis", "evidence": "原文里没有这句不考", "kp": "k"}
    )
    with pytest.raises(ModelOutputError):
        ed.parse_points(bad_quote, "这句不考。")

    # 3) 缺 content + 负向短语
    missing = _points_json({"level": "emphasis", "evidence": "这句不考", "kp": "k"})
    with pytest.raises(ModelOutputError):
        ed.parse_points(missing, "这句不考。")


def test_no_negative_warning_when_nothing_was_excluded(p1_runtime: Path):
    raw = _points_json(
        {"content": "a", "level": "emphasis", "evidence": "这个内容很重要", "kp": "k"}
    )

    _, excluded = ed.parse_points(raw, TRANSCRIPT)

    assert excluded == 0


# ---------------------------------------------------------------------------
# 真实 generation 路径上的故障
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "finish_reason", "usage", "expected"),
    [
        ("", "stop", None, ErrorCode.EMPTY_MODEL_OUTPUT),
        ("", "length", {"completion_tokens": 16000}, ErrorCode.REASONING_BUDGET_EXHAUSTED),
        ('{"points": [', "length", {"completion_tokens": 16000}, ErrorCode.OUTPUT_TRUNCATED),
    ],
)
def test_generation_failures_propagate_instead_of_an_empty_success(
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
        _detect()

    assert _code(excinfo.value) is expected


def test_a_provider_failure_is_not_a_zero_point_success(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
        monkeypatch, llm=_RaisingLLM(LLMProviderTransportError(f"连接失败 {FAKE_BODY_MARKER}"))
    )

    with pytest.raises(SubjectOperationError) as excinfo:
        _detect()

    error = map_subject_exception(excinfo.value)
    assert error.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert error.cause is not None
    assert FAKE_BODY_MARKER not in error.message


def test_a_rejected_round_never_returns_raw_diagnostics(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    """旧实现把 str(exc) 塞进 error 字段；现在既没有 error 字段也没有原文。"""
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
        monkeypatch, llm=_RaisingLLM(RuntimeError(f"内部细节 {FAKE_BODY_MARKER}"))
    )

    with pytest.raises(SubjectOperationError) as excinfo:
        _detect()

    mapped = map_subject_exception(excinfo.value)
    assert mapped.code is ErrorCode.INTERNAL_ERROR
    assert FAKE_BODY_MARKER not in str(excinfo.value)
    assert FAKE_BODY_MARKER not in mapped.message


def test_the_prompt_actually_sent_matches_the_returned_version(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = '{"points": []}'

    result = _detect()

    sent = p1_llm.calls[0].payload["prompt"]
    assert result["version"] == ed.DETECT_PROMPT_VERSION == "v4"
    assert sent.startswith(ed.prompt_for_version(result["version"]))
    assert TRANSCRIPT in sent


@pytest.mark.parametrize("version", ["v1", "v2", "v3", "v5", ""])
def test_an_unimplemented_prompt_version_is_a_caller_error(p1_runtime: Path, version: str):
    with pytest.raises(SubjectOperationError) as excinfo:
        _detect(prompt_version=version)

    assert _code(excinfo.value) is ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("transcript", ["", "   ", None, 5])
def test_a_blank_transcript_is_a_caller_error_and_does_not_call_the_model(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch, transcript
):
    _install_cfg(monkeypatch)

    with pytest.raises(SubjectOperationError) as excinfo:
        _detect(transcript=transcript)

    assert _code(excinfo.value) is ErrorCode.INVALID_INPUT
    assert p1_llm.call_count == 0


def test_the_model_body_is_returned_without_reasoning_blocks(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    body = _points_json(
        {"content": "c", "level": "explicit", "evidence": "这个内容很重要", "kp": "k"}
    )
    p1_llm.response = f"<think>先看看有没有考试信号</think>\n{body}"

    result = _detect()

    assert result["raw"] == body
    assert "think" not in result["raw"]
    assert result["points"][0]["level"] == "explicit"


# ---------------------------------------------------------------------------
# prompt 示例本身必须逐字可引用
# ---------------------------------------------------------------------------
def test_every_prompt_example_quote_appears_verbatim_in_its_own_input(p1_runtime: Path):
    pairs = re.findall(r'输入："([^"]*)"\n输出：(\{.*\})', ed.DETECT_PROMPT)
    assert len(pairs) == 3  # 三个示例都在

    quoted = 0
    for source, output in pairs:
        data = json.loads(output)
        for candidate in data["points"]:
            assert (
                ed.normalize_whitespace(candidate["evidence"])
                in ed.normalize_whitespace(source)
            ), candidate["evidence"]
            quoted += 1
    assert quoted == 2  # 两个示例含考点，第三个是合法的空列表


def test_the_old_example_quote_really_was_not_verbatim(p1_runtime: Path):
    """坏对照：v3 示例里那句引文在它自己的输入里找不到（所以必须改）。"""
    legacy_evidence = "去年期末考试，最后一道大题就是考的消元法"
    legacy_input = "去年期末考试最后一道大题就考的消元法，大家今年注意。"

    assert ed.normalize_whitespace(legacy_evidence) not in ed.normalize_whitespace(legacy_input)
    # 修正后的示例引文是逐字可找到的
    fixed = "去年期末考试最后一道大题就考的消元法"
    assert ed.normalize_whitespace(fixed) in ed.normalize_whitespace(legacy_input)


# ---------------------------------------------------------------------------
# 有效坏对照：旧宽松解析会把这些坏输入变成"空成功"
# ---------------------------------------------------------------------------
def _legacy_parse_points(raw: str) -> list[dict]:
    """旧 ``_parse_points`` 的容错行为（贪婪抓取、跳过坏项、level 兜底）。"""
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", match.group(0))
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        return []
    out = []
    for item in points:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        level = str(item.get("level") or "emphasis").lower()
        if level not in ("explicit", "emphasis", "inferred"):
            level = "emphasis"
        out.append({"content": content, "level": level})
    return out


def test_bad_control_the_legacy_parser_reported_no_points_for_every_failure(p1_runtime: Path):
    broken_rounds = [
        '{"points": [',
        "不是 JSON",
        "{}",
        '{"points": {}}',
        '{"points": [{"level": "inferred", "evidence": "这个内容很重要", "kp": "k"}]}',
        '{"points": [{"content": "c", "level": "emphasis", "evidence": "原文里没有", "kp": "k"}]}',
    ]

    legacy = [_legacy_parse_points(raw) for raw in broken_rounds]
    # 旧行为：结构坏的五种输入都变成"没发现考点"的空成功……
    assert legacy[:5] == [[] for _ in range(5)]
    # ……而引用根本不在原文的候选被直接接受（quote 从未被验证）。
    assert legacy[5] == [{"content": "c", "level": "emphasis"}]

    for raw in broken_rounds:
        with pytest.raises(SubjectOperationError):
            ed.parse_points(raw, TRANSCRIPT)  # 新行为：具名失败
