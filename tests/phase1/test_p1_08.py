"""P1-08 行为测试：考点检测一次保存、显式失败、重复检测不重复加点（C06/C02/C01）。

目标：整轮先验证、再在同一 subject 锁里写一次；模型故障不变成 ``detected=0`` 的成功；
重复检测复用既有条目。

覆盖的必证场景：

* 确认策略：``explicit`` 自动确认、``emphasis`` 默认未确认、``auto_confirm=true`` 全确认；
  已确认条目不会被后续 emphasis 检测撤销，``explicit`` 可以把未确认条目提升为确认；
* term：省略/空串采用 ``subject.term``，显式非空采用调用值，且两个学期互不合并；
* 去重：同一批内重复、与既有集合重复（空白归一化后相同）都只保存一条并复用旧
  id/created_at/未知字段；跨科、跨学期不合并；不用相似度；
* 合法零考点：成功且不写文件；只有复用的整轮也不写文件；发生变更的整轮只写一次；
* 整批验证：坏的后半项、坏 level（``inferred`` 这种 manual 兼容等级不得被接受）、
  提交故障都不留部分落盘；
* HTTP：成功响应满足 DetectionResponse schema（``detected == len(stored)``、
  warnings 形状），失败为非 2xx + C02 code，且失败前后文件字节不变。

最后一个用例是**有效坏对照**：旧路由的"逐点 add_point 循环"在遇到坏项之前已经把前半段
存盘，证明"整批不留半截"的断言承重。

不联网、不写真实数据；模型侧全部用真实 generation 路径上的替身。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.llm.exceptions import LLMProviderTransportError
from deeptutor.subjects import exam_points, json_store, store
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX

FAKE_BODY_MARKER = "p1-08-FAKE-BODY-4c17de-DO-NOT-LEAK"

TRANSCRIPT = (
    "今天我们讲洛必达法则。这个内容很重要，大家一定要重视起来，几乎年年都要用到。\n"
    "去年期末考试最后一道大题就考的消元法，大家今年注意。\n"
    "泰勒展开的余项不用重点看，大家了解一下就行。"
)

POINT_A = {
    "content": "洛必达法则（整体重要性）",
    "level": "emphasis",
    "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到",
    "kp": "洛必达法则",
}
POINT_B = {
    "content": "消元法解方程组",
    "level": "explicit",
    "evidence": "去年期末考试最后一道大题就考的消元法",
    "kp": "消元法",
}
POINT_NEGATIVE = {
    "content": "泰勒展开余项",
    "level": "emphasis",
    "evidence": "泰勒展开的余项不用重点看",
    "kp": "泰勒展开",
}


def _schema(name: str) -> dict:
    doc = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8"))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{name}",
        "$defs": doc["$defs"],
    }


def _install_cfg(monkeypatch: pytest.MonkeyPatch):
    import deeptutor.services.llm.config as config_mod

    cfg = config_mod.LLMConfig(
        model="p1-08-fake-model",
        api_key="p1-08-fake-key",
        base_url="http://127.0.0.1:9/v1",
    )
    monkeypatch.setattr(config_mod, "_LLM_CONFIG_CACHE", cfg)
    return cfg


def _subject(name: str = "考点检测科目", term: str = "2026春") -> str:
    return store.create_subject(name, term=term)["id"]


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "exam_points.json"


def _bytes(subject_id: str) -> bytes | None:
    path = _path(subject_id)
    return path.read_bytes() if path.exists() else None


def _raw(subject_id: str) -> list[dict]:
    return json.loads(_path(subject_id).read_text(encoding="utf-8"))


def _count_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = json_store.atomic_write_json

    def counting(path, payload):
        calls.append(Path(path).name)
        return real(path, payload)

    monkeypatch.setattr(json_store, "atomic_write_json", counting)
    return calls


def _points_json(*points: dict) -> str:
    return json.dumps({"points": list(points)}, ensure_ascii=False)


def _detect(client, subject_id: str, transcript: str = TRANSCRIPT, **form):
    return client.post(
        f"{ROUTE_PREFIX}/{subject_id}/exam-points/detect",
        data={"transcript": transcript, **form},
    )


def _failed_detect(client, subject_id: str, **form):
    """发一次注定失败的检测请求，返回 (C02 code, response|None)。

    P1-56 的路由包装上线后领域错误被投影成完整 C02 响应；在此之前它由
    TestClient 直接抛出。两种情况的 code 必须一致，因此本文件在阶段末复跑时断言不变。
    """
    try:
        response = _detect(client, subject_id, **form)
    except SubjectOperationError as exc:
        return map_subject_exception(exc).code, None
    payload = response.json()
    return ErrorCode(payload["error"]["code"]), response


# ---------------------------------------------------------------------------
# 确认策略
# ---------------------------------------------------------------------------
def test_explicit_is_confirmed_and_emphasis_is_not(p1_runtime: Path):
    subject_id = _subject()

    stored = exam_points.upsert_detected(subject_id, [POINT_B, POINT_A])

    by_content = {p["content"]: p for p in stored}
    assert by_content[POINT_B["content"]]["confirmed"] is True
    assert by_content[POINT_A["content"]]["confirmed"] is False
    # 落盘的也是同一份判定
    raw = {p["content"]: p for p in _raw(subject_id)}
    assert raw[POINT_B["content"]]["confirmed"] is True
    assert raw[POINT_A["content"]]["confirmed"] is False


def test_auto_confirm_confirms_emphasis_too(p1_runtime: Path):
    subject_id = _subject()

    stored = exam_points.upsert_detected(subject_id, [POINT_A, POINT_B], auto_confirm=True)

    assert [p["confirmed"] for p in stored] == [True, True]


def test_a_later_emphasis_detection_never_revokes_a_confirmation(p1_runtime: Path):
    subject_id = _subject()
    first = exam_points.upsert_detected(subject_id, [POINT_A], auto_confirm=True)
    assert first[0]["confirmed"] is True

    again = exam_points.upsert_detected(subject_id, [POINT_A], auto_confirm=False)

    assert again[0]["id"] == first[0]["id"]
    assert again[0]["confirmed"] is True
    assert len(_raw(subject_id)) == 1


def test_explicit_promotes_an_unconfirmed_duplicate(p1_runtime: Path):
    subject_id = _subject()
    first = exam_points.upsert_detected(subject_id, [POINT_A])
    assert first[0]["confirmed"] is False

    promoted = exam_points.upsert_detected(subject_id, [{**POINT_A, "level": "explicit"}])

    assert promoted[0]["id"] == first[0]["id"]
    assert promoted[0]["confirmed"] is True
    assert len(_raw(subject_id)) == 1
    # 复用旧记录：既有 level 不被重写（确认可以提升，等级不追溯改写）
    assert _raw(subject_id)[0]["level"] == "emphasis"


# ---------------------------------------------------------------------------
# term 策略与隔离
# ---------------------------------------------------------------------------
def test_an_omitted_term_uses_the_subject_term(p1_runtime: Path):
    subject_id = _subject(term="2026春")

    stored = exam_points.upsert_detected(subject_id, [POINT_A], term="")
    stored_blank = exam_points.upsert_detected(subject_id, [POINT_B], term="   ")

    assert stored[0]["term"] == "2026春"
    assert stored_blank[0]["term"] == "2026春"


def test_an_explicit_term_is_used_and_kept_separate(p1_runtime: Path):
    subject_id = _subject(term="2026春")

    spring = exam_points.upsert_detected(subject_id, [POINT_A], term="2026春")
    autumn = exam_points.upsert_detected(subject_id, [POINT_A], term="2025秋")

    assert spring[0]["term"] == "2026春"
    assert autumn[0]["term"] == "2025秋"
    assert autumn[0]["id"] != spring[0]["id"]
    assert len(_raw(subject_id)) == 2


def test_the_same_point_in_another_subject_is_not_merged(p1_runtime: Path):
    subject_a = _subject("考点科目A")
    subject_b = _subject("考点科目B")

    stored_a = exam_points.upsert_detected(subject_a, [POINT_A])
    stored_b = exam_points.upsert_detected(subject_b, [POINT_A])

    assert stored_a[0]["id"] != stored_b[0]["id"]
    assert len(_raw(subject_a)) == 1
    assert len(_raw(subject_b)) == 1
    assert all(p["subject_id"] == subject_a for p in _raw(subject_a))


def test_similar_but_not_identical_content_is_a_separate_point(p1_runtime: Path):
    subject_id = _subject()

    exam_points.upsert_detected(subject_id, [POINT_A])
    exam_points.upsert_detected(
        subject_id, [{**POINT_A, "content": POINT_A["content"] + "（补充）"}]
    )

    assert len(_raw(subject_id)) == 2


# ---------------------------------------------------------------------------
# 去重与"不重复加点"
# ---------------------------------------------------------------------------
def test_a_second_identical_round_reuses_entries_and_writes_nothing(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_id = _subject()
    first = exam_points.upsert_detected(subject_id, [POINT_A, POINT_B])
    before = _bytes(subject_id)
    writes = _count_writes(monkeypatch)

    second = exam_points.upsert_detected(subject_id, [POINT_A, POINT_B])

    assert [p["id"] for p in second] == [p["id"] for p in first]
    assert writes == []  # 完全无变化的一轮不写
    assert _bytes(subject_id) == before
    assert len(_raw(subject_id)) == 2


def test_duplicates_inside_one_batch_are_saved_once(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    subject_id = _subject()
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(subject_id, [POINT_A, POINT_A, POINT_B])

    assert [p["content"] for p in stored] == [POINT_A["content"], POINT_B["content"]]
    assert len(_raw(subject_id)) == 2
    assert writes == ["exam_points.json"]


def test_whitespace_differences_do_not_create_a_duplicate(p1_runtime: Path):
    subject_id = _subject()
    exam_points.upsert_detected(subject_id, [POINT_A])

    stored = exam_points.upsert_detected(
        subject_id,
        [{**POINT_A, "evidence": "这个内容很重要，大家一定要重视起来， 几乎年年都要用到"}],
    )

    assert len(stored) == 1
    assert len(_raw(subject_id)) == 1


def test_the_same_content_with_different_evidence_is_a_separate_point(p1_runtime: Path):
    subject_id = _subject()

    exam_points.upsert_detected(subject_id, [POINT_A])
    exam_points.upsert_detected(
        subject_id, [{**POINT_A, "evidence": "去年期末考试最后一道大题就考的消元法"}]
    )

    assert len(_raw(subject_id)) == 2


def test_reuse_preserves_the_old_id_created_at_and_unknown_fields(p1_runtime: Path):
    subject_id = _subject()
    legacy = {
        "id": "legacy-point-1",
        "subject_id": subject_id,
        "content": POINT_A["content"],
        "level": "emphasis",
        "evidence": POINT_A["evidence"],
        "kp": "旧知识点",
        "term": "2026春",
        "confirmed": False,
        "created_at": 1791000000,
        "legacy_note": "必须保留",
    }
    _path(subject_id).write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")

    stored = exam_points.upsert_detected(subject_id, [POINT_A])

    assert stored[0]["id"] == "legacy-point-1"
    assert stored[0]["created_at"] == 1791000000
    assert stored[0]["legacy_note"] == "必须保留"
    assert stored[0]["kp"] == "旧知识点"
    raw = _raw(subject_id)
    assert len(raw) == 1
    assert raw[0]["legacy_note"] == "必须保留"


def test_untouched_records_are_not_rewritten(p1_runtime: Path):
    subject_id = _subject()
    legacy = {
        "id": "other-1",
        "subject_id": subject_id,
        "content": "另一条历史考点",
        "level": "inferred",
        "evidence": "",
        "kp": "",
        "term": "2025秋",
        "confirmed": True,
        "created_at": 1790000000,
        "unknown": {"a": 1},
    }
    _path(subject_id).write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")

    exam_points.upsert_detected(subject_id, [POINT_A])

    raw = _raw(subject_id)
    assert raw[0] == legacy  # 未被涉及的记录逐字段不变
    assert len(raw) == 2


# ---------------------------------------------------------------------------
# 空轮 / 写次数 / 失败不留半截
# ---------------------------------------------------------------------------
def test_a_legal_empty_round_succeeds_and_writes_nothing(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_id = _subject()
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(subject_id, [])

    assert stored == []
    assert writes == []
    assert _bytes(subject_id) is None


def test_a_whole_round_is_committed_exactly_once(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    subject_id = _subject()
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(subject_id, [POINT_A, POINT_B, {**POINT_NEGATIVE}])

    assert len(stored) == 3
    assert writes == ["exam_points.json"]
    assert len(_raw(subject_id)) == 3


@pytest.mark.parametrize(
    "bad_item",
    [
        "not-a-dict",
        42,
        None,
        ["nested"],
        {"content": 5, "level": "explicit"},
        {"content": "ok"},  # 缺 level：检测候选必须有严格 level
        {"content": "ok", "level": "inferred"},  # manual 兼容等级不得被接受
        {"content": "ok", "level": "maybe"},
        {"content": "ok", "level": 3},
        {"content": "  ", "level": "explicit"},
        {"content": "ok", "level": "explicit", "evidence": ["x"]},
        {"content": "ok", "level": "explicit", "evidence": "原文", "kp": {"a": 1}},
        {"content": "ok", "level": "explicit", "evidence": "原文", "anchor": 7},
    ],
)
def test_a_bad_later_item_leaves_nothing_behind(p1_runtime: Path, bad_item):
    subject_id = _subject()
    existing = exam_points.add_point(subject_id, content="已有考点", term="2026春")
    before = _bytes(subject_id)

    with pytest.raises(exam_points.InvalidExamPointError) as excinfo:
        exam_points.upsert_detected(subject_id, [POINT_A, POINT_B, bad_item])

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    assert _bytes(subject_id) == before
    assert [p["id"] for p in _raw(subject_id)] == [existing["id"]]


def test_a_commit_failure_keeps_the_previous_file(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    subject_id = _subject()
    existing = exam_points.add_point(subject_id, content="已有考点", term="2026春")
    before = _bytes(subject_id)

    def exploding(path, payload):
        raise StorageIOError("注入的写入失败", path=Path(path).name)

    monkeypatch.setattr(json_store, "atomic_write_json", exploding)

    with pytest.raises(StorageIOError):
        exam_points.upsert_detected(subject_id, [POINT_A, POINT_B])

    assert _bytes(subject_id) == before
    assert [p["id"] for p in _raw(subject_id)] == [existing["id"]]


@pytest.mark.parametrize(
    ("kwargs", "value"),
    [
        ("points", {"content": "x"}),
        ("points", "not-a-list"),
        ("source", 5),
        ("term", 5),
        ("auto_confirm", "yes"),
        ("auto_confirm", 1),
    ],
)
def test_bad_batch_options_are_invalid_input(p1_runtime: Path, kwargs: str, value):
    subject_id = _subject()
    call = {
        "points": [POINT_A],
        "term": "2026春",
        "source": "lecture",
        "auto_confirm": False,
    }
    call[kwargs] = value

    with pytest.raises(exam_points.InvalidExamPointError) as excinfo:
        exam_points.upsert_detected(subject_id, **call)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    assert _bytes(subject_id) is None


@pytest.mark.parametrize("term", ["", "2026春"])
def test_an_unregistered_subject_is_not_found(p1_runtime: Path, term: str):
    with pytest.raises(SubjectOperationError) as excinfo:
        exam_points.upsert_detected("未注册科目", [POINT_A], term=term)

    assert map_subject_exception(excinfo.value).code is ErrorCode.SUBJECT_NOT_FOUND


# ---------------------------------------------------------------------------
# HTTP：成功形状、失败形状、字节不变
# ---------------------------------------------------------------------------
def test_http_detect_returns_a_schema_valid_round_for_a_new_subject(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from jsonschema import validate

    subject = p1_subjects["科目A"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    writes = _count_writes(monkeypatch)
    p1_llm.response = _points_json(POINT_A, POINT_B)

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 200
    body = response.json()
    validate(instance=body, schema=_schema("DetectionResponse"))
    assert body["version"] == "v4"
    assert body["detected"] == len(body["stored"]) == 2
    assert body["warnings"] == []
    assert body["raw"] == _points_json(POINT_A, POINT_B)
    assert [p["confirmed"] for p in body["stored"]] == [False, True]
    # 未提供 term 时必须**精确**采用 fixture 的 subject.term（不是 subject_id，
    # 也不是"两者之一"）；返回的身份必须就是被请求的科目（R5/R3）。
    assert [p["term"] for p in body["stored"]] == ["2026春", "2026春"]
    assert {p["subject_id"] for p in body["stored"]} == {subject.subject_id}
    assert writes == ["exam_points.json"]


def test_http_detect_twice_does_not_grow_the_collection(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    subject = p1_subjects["科目A"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A, POINT_B)

    first = _detect(p1_route_client, subject.subject_id).json()
    before = (subject.root / "exam_points.json").read_bytes()
    second = _detect(p1_route_client, subject.subject_id).json()

    assert second["detected"] == 2
    assert [p["id"] for p in second["stored"]] == [p["id"] for p in first["stored"]]
    assert (subject.root / "exam_points.json").read_bytes() == before


def test_http_detect_uses_the_subject_term_by_default(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    subject = p1_subjects["科目B"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A)

    default_term = _detect(p1_route_client, subject.subject_id).json()
    explicit_term = _detect(p1_route_client, subject.subject_id, term="2025秋").json()

    assert default_term["stored"][0]["term"] == "2026春"
    assert explicit_term["stored"][0]["term"] == "2025秋"
    assert explicit_term["stored"][0]["id"] != default_term["stored"][0]["id"]


def test_http_detect_excludes_negative_evidence_and_reports_the_count(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from jsonschema import validate

    subject = p1_subjects["科目A"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A, POINT_NEGATIVE)

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 200
    body = response.json()
    validate(instance=body, schema=_schema("DetectionResponse"))
    assert [p["content"] for p in body["stored"]] == [POINT_A["content"]]
    assert body["detected"] == 1
    assert body["warnings"] == [
        {
            "code": "negative_evidence_excluded",
            "message": body["warnings"][0]["message"],
            "count": 1,
        }
    ]
    validate(instance=body["warnings"][0], schema=_schema("Warning"))
    assert len(_raw(subject.subject_id)) == 1


def test_http_detect_empty_round_is_a_success_and_writes_nothing(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from jsonschema import validate

    subject = p1_subjects["科目B"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = '{"points": []}'

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 200
    body = response.json()
    validate(instance=body, schema=_schema("DetectionResponse"))
    assert body["detected"] == 0
    assert body["stored"] == []
    assert not (subject.root / "exam_points.json").exists()


@pytest.mark.parametrize(
    ("text", "finish_reason", "usage", "expected"),
    [
        ("不是 JSON", "stop", None, ErrorCode.INVALID_MODEL_OUTPUT),
        ("{}", "stop", None, ErrorCode.INVALID_MODEL_OUTPUT),
        (
            _points_json({**POINT_A, "level": "inferred"}),
            "stop",
            None,
            ErrorCode.INVALID_MODEL_OUTPUT,
        ),
        (
            _points_json({**POINT_A, "evidence": "原文里没有这句"}),
            "stop",
            None,
            ErrorCode.INVALID_MODEL_OUTPUT,
        ),
        ("", "stop", None, ErrorCode.EMPTY_MODEL_OUTPUT),
        ('{"points": [', "length", {"completion_tokens": 16000}, ErrorCode.OUTPUT_TRUNCATED),
        ("", "length", {"completion_tokens": 16000}, ErrorCode.REASONING_BUDGET_EXHAUSTED),
    ],
)
def test_http_detect_failures_are_non_2xx_and_keep_the_old_bytes(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    finish_reason: str,
    usage,
    expected: ErrorCode,
):
    subject = p1_subjects["科目A"]
    seeded = exam_points.add_point(subject.subject_id, content="已有考点", term="2026春")
    before = (subject.root / "exam_points.json").read_bytes()
    _install_cfg(monkeypatch)
    p1_llm.response = text
    p1_llm.finish_reason = finish_reason
    p1_llm.usage = usage

    code, response = _failed_detect(p1_route_client, subject.subject_id)

    assert code is expected
    if response is not None:
        from jsonschema import validate

        assert response.status_code >= 400
        body = response.json()
        validate(instance=body, schema=_schema("ErrorResponse"))
        assert body["error"]["code"] == expected.value
        assert FAKE_BODY_MARKER not in response.text
    assert (subject.root / "exam_points.json").read_bytes() == before
    assert [p["id"] for p in _raw(subject.subject_id)] == [seeded["id"]]


def test_http_detect_provider_failure_is_502_without_writing(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目B"]
    subject.root.joinpath("exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)

    class _RaisingLLM(helpers.FakeLLMClient):
        async def complete_response(self, prompt: str = "", **kwargs):
            self._record(prompt=prompt, **kwargs)
            raise LLMProviderTransportError(f"连接失败 {FAKE_BODY_MARKER}")

    helpers.install_provider_stubs(monkeypatch, llm=_RaisingLLM(""))

    code, response = _failed_detect(p1_route_client, subject.subject_id)

    assert code is ErrorCode.PROVIDER_UNAVAILABLE
    if response is not None:
        assert response.status_code == 502
        assert FAKE_BODY_MARKER not in response.text
    assert not (subject.root / "exam_points.json").exists()


def test_http_detect_blank_transcript_is_rejected_without_calling_the_model(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目A"]
    _install_cfg(monkeypatch)

    response = _detect(p1_route_client, subject.subject_id, transcript="   ")

    assert response.status_code == 400
    assert p1_llm.call_count == 0


def test_http_unknown_subject_is_not_found(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    """合法但未注册的 slug：精确 404 + subject_not_found，不调模型、不建树。"""
    from jsonschema import validate

    _install_cfg(monkeypatch)
    subjects_root = helpers.learning_root(p1_subjects["_admin_root"])
    before_dirs = sorted(p.name for p in subjects_root.iterdir() if p.is_dir())

    response = _detect(p1_route_client, "不存在的科目")

    assert response.status_code == 404
    body = response.json()
    validate(instance=body, schema=_schema("ErrorResponse"))
    assert body["error"]["code"] == ErrorCode.SUBJECT_NOT_FOUND.value
    assert p1_llm.call_count == 0
    assert sorted(p.name for p in subjects_root.iterdir() if p.is_dir()) == before_dirs


# ---------------------------------------------------------------------------
# 有效坏对照：旧的逐点保存会留下前半段
# ---------------------------------------------------------------------------
def test_bad_control_the_old_per_point_loop_left_the_earlier_points(p1_runtime: Path):
    subject_id = _subject()
    batch = [POINT_A, POINT_B, {"content": "   ", "level": "emphasis", "evidence": "这个内容很重要"}]

    # 旧行为：路由里逐点 add_point，坏项之前的点已经落盘
    with pytest.raises(SubjectOperationError):
        for item in batch:
            exam_points.add_point(
                subject_id,
                content=item["content"],
                level=item.get("level", "inferred"),
                evidence=item.get("evidence", ""),
                kp=item.get("kp", ""),
                term="2026春",
            )
    assert len(_raw(subject_id)) == 2  # 前半段留下了（这正是要被修掉的行为）
    assert [p["content"] for p in _raw(subject_id)] == [POINT_A["content"], POINT_B["content"]]

    # 新行为：整批先验证，一条都不留
    other = _subject("整批科目")
    with pytest.raises(exam_points.InvalidExamPointError):
        exam_points.upsert_detected(other, batch, term="2026春")
    assert _bytes(other) is None


# ---------------------------------------------------------------------------
# R1（rework01）：内部批量入口的候选必须字段齐全、level 精确
# ---------------------------------------------------------------------------
def _malformed_candidates() -> list[tuple[str, dict]]:
    """坏候选：每条都是合法基准只改一个字段/缺一个字段。"""
    bad = {**POINT_A, "content": "另一个考点"}
    missing_evidence = {k: v for k, v in bad.items() if k != "evidence"}
    missing_kp = {k: v for k, v in bad.items() if k != "kp"}
    return [
        ("missing_evidence", missing_evidence),
        ("evidence_empty", {**bad, "evidence": ""}),
        ("evidence_blank", {**bad, "evidence": "   "}),
        ("missing_kp", missing_kp),
        ("kp_null", {**bad, "kp": None}),
        ("kp_object", {**bad, "kp": {"name": "极限"}}),
        ("kp_number", {**bad, "kp": 7}),
        ("level_padded", {**bad, "level": " Explicit "}),
        ("level_upper", {**bad, "level": "EXPLICIT"}),
        ("level_newline", {**bad, "level": "emphasis\n"}),
        ("missing_level", {k: v for k, v in bad.items() if k != "level"}),
        ("missing_content", {k: v for k, v in bad.items() if k != "content"}),
    ]


@pytest.mark.parametrize(("case", "bad"), _malformed_candidates(), ids=lambda v: str(v)[:24])
def test_r1_a_malformed_batch_candidate_is_invalid_input_and_writes_nothing(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch, case: str, bad: dict
):
    subject_id = _subject()
    seed = exam_points.add_point(
        subject_id, content="已有考点", level="inferred", evidence="", term="2025秋"
    )
    before = _bytes(subject_id)
    writes = _count_writes(monkeypatch)

    with pytest.raises(exam_points.InvalidExamPointError) as excinfo:
        exam_points.upsert_detected(subject_id, [POINT_A, bad], term="2026春")

    # 内部调用参数非法是 400 invalid_input，不能借 storage_corrupt 拒绝调用参数
    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    assert writes == []  # 不是"helper 没被调用"，而是真的一次写都没发生
    assert _bytes(subject_id) == before
    assert [p["id"] for p in _raw(subject_id)] == [seed["id"]]


def test_r1_a_valid_batch_with_an_empty_kp_is_accepted(p1_runtime: Path, monkeypatch):
    """合法正例：kp 允许空字符串，两个精确枚举都可用。"""
    subject_id = _subject()
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(
        subject_id,
        [{**POINT_A, "kp": ""}, POINT_B],
        term="2026春",
    )

    assert [p["level"] for p in stored] == ["emphasis", "explicit"]
    assert stored[0]["kp"] == ""
    assert writes == ["exam_points.json"]


@pytest.mark.parametrize("level", ["EXPLICIT", " explicit ", "emphasis\n"])
def test_r1_http_invalid_level_is_502_and_keeps_the_file(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    level: str,
):
    subject = p1_subjects["科目A"]
    path = subject.root / "exam_points.json"
    path.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json({**POINT_A, "level": level})

    code, response = _failed_detect(p1_route_client, subject.subject_id)

    assert code is ErrorCode.INVALID_MODEL_OUTPUT
    if response is not None:
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "invalid_model_output"
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# R2（rework01）：同批重复的确认依据不能被顺序丢掉
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "levels", [("emphasis", "explicit"), ("explicit", "emphasis"), ("emphasis", "emphasis")]
)
def test_r2_same_batch_confirmation_is_order_independent(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch, levels: tuple[str, str]
):
    subject_id = _subject()
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(
        subject_id, [{**POINT_A, "level": level} for level in levels], term="2026春"
    )

    expected_confirmed = "explicit" in levels
    assert len(stored) == 1
    assert stored[0]["confirmed"] is expected_confirmed
    disk = _raw(subject_id)
    assert len(disk) == 1
    assert disk[0]["confirmed"] is expected_confirmed
    # 返回视图与磁盘一致；本轮是**新建**条目，因此恰好一次写
    # （"无变化的一轮零写"由下面复用已确认条目的用例覆盖）
    assert stored[0]["id"] == disk[0]["id"]
    assert stored[0]["confirmed"] == disk[0]["confirmed"]
    assert writes == ["exam_points.json"]


@pytest.mark.parametrize(
    "levels", [("emphasis", "explicit"), ("explicit", "emphasis")]
)
def test_r2_same_batch_explicit_promotes_a_reused_legacy_entry(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch, levels: tuple[str, str]
):
    subject_id = _subject()
    legacy = exam_points.add_point(
        subject_id,
        content=POINT_A["content"],
        level="emphasis",
        evidence=POINT_A["evidence"],
        term="2026春",
        confirmed=False,
    )
    legacy["unknown"] = {"keep": 1}
    _path(subject_id).write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(
        subject_id, [{**POINT_A, "level": level} for level in levels], term="2026春"
    )

    assert len(stored) == 1
    assert stored[0]["confirmed"] is True
    disk = _raw(subject_id)
    assert disk[0]["id"] == legacy["id"]
    assert disk[0]["created_at"] == legacy["created_at"]
    assert disk[0]["unknown"] == {"keep": 1}
    assert disk[0]["confirmed"] is True
    assert stored[0] == {**disk[0]}
    assert writes == ["exam_points.json"]


def test_r2_a_reused_confirmed_entry_is_not_revoked_and_writes_nothing(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_id = _subject()
    first = exam_points.upsert_detected(subject_id, [{**POINT_A, "level": "explicit"}])
    assert first[0]["confirmed"] is True
    writes = _count_writes(monkeypatch)

    again = exam_points.upsert_detected(subject_id, [POINT_A], term="2026春")

    assert again[0]["confirmed"] is True
    assert again[0]["id"] == first[0]["id"]
    assert writes == []  # 无变化的一轮零写
    assert len(_raw(subject_id)) == 1


def test_r2_http_duplicate_confirmation_does_not_drop_explicit(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    subject = p1_subjects["科目A"]
    (subject.root / "exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A, {**POINT_A, "level": "explicit"})

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 200
    body = response.json()
    assert body["detected"] == len(body["stored"]) == 1
    assert body["stored"][0]["confirmed"] is True
    assert _raw(subject.subject_id)[0]["confirmed"] is True


def test_r2_a_failed_commit_keeps_the_previous_bytes(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_id = _subject()
    legacy = exam_points.add_point(
        subject_id, content=POINT_A["content"], evidence=POINT_A["evidence"], term="2026春"
    )
    before = _bytes(subject_id)

    def exploding(path, payload):
        raise StorageIOError("注入的写入失败", path=Path(path).name)

    monkeypatch.setattr(json_store, "atomic_write_json", exploding)

    with pytest.raises(StorageIOError):
        exam_points.upsert_detected(
            subject_id, [POINT_A, {**POINT_A, "level": "explicit"}], term="2026春"
        )

    assert _bytes(subject_id) == before
    assert _raw(subject_id)[0]["confirmed"] is False
    assert [p["id"] for p in _raw(subject_id)] == [legacy["id"]]


# ---------------------------------------------------------------------------
# R3（rework01）：复用旧考点的身份与 level 元数据校验
# ---------------------------------------------------------------------------
def _legacy_base(subject_id: str) -> dict:
    return exam_points.add_point(
        subject_id,
        content=POINT_A["content"],
        level="emphasis",
        evidence=POINT_A["evidence"],
        kp=POINT_A["kp"],
        term="2026春",
        confirmed=False,
    )


def test_r3_a_legal_legacy_record_is_reused_over_http(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    """先证明合法基准：可复用、返回身份正确、文件不变。"""
    subject = p1_subjects["科目A"]
    base = _legacy_base(subject.subject_id)
    subject.root.joinpath("exam_points.json").write_text(
        json.dumps([base], ensure_ascii=False), encoding="utf-8"
    )
    before = (subject.root / "exam_points.json").read_bytes()
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A)

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 200
    body = response.json()
    assert body["detected"] == 1
    assert body["stored"][0]["id"] == base["id"]
    assert body["stored"][0]["subject_id"] == subject.subject_id
    assert (subject.root / "exam_points.json").read_bytes() == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject_id", None),
        ("subject_id", 7),
        ("subject_id", "bad/id"),
        ("subject_id", "另一个科目"),
        ("level", "unexpected"),
        ("level", None),
        ("level", "Inferred"),
    ],
)
def test_r3_bad_reused_metadata_is_storage_corrupt_and_publishes_nothing(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value,
):
    subject = p1_subjects["科目A"]
    path = subject.root / "exam_points.json"
    base = _legacy_base(subject.subject_id)
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A)

    # 合法对照先过（证明坏值之后的行为差异确实来自目标字段）
    path.write_text(json.dumps([base], ensure_ascii=False), encoding="utf-8")
    control = _detect(p1_route_client, subject.subject_id)
    assert control.status_code == 200

    path.write_text(json.dumps([{**base, field: value}], ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()

    response = _detect(p1_route_client, subject.subject_id)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert path.read_bytes() == before  # 坏文件不被覆盖
    assert len(_raw(subject.subject_id)) == 1


def test_r3_a_corrupt_reuse_after_a_new_candidate_publishes_no_prefix(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """本轮前半是合法新候选、后半要复用坏记录：整轮都不得落盘。"""
    subject = p1_subjects["科目A"]
    path = subject.root / "exam_points.json"
    base = _legacy_base(subject.subject_id)
    path.write_text(
        json.dumps([{**base, "subject_id": None}], ensure_ascii=False), encoding="utf-8"
    )
    before = path.read_bytes()
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json({**POINT_A, "content": "全新的合法考点"}, POINT_A)

    response = _detect(p1_route_client, subject.subject_id)

    assert path.read_bytes() == before
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert len(_raw(subject.subject_id)) == 1


def test_r3_a_bad_reuse_leaves_the_other_subject_untouched(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    alpha = p1_subjects["科目A"]
    beta = p1_subjects["科目B"]
    beta_point = exam_points.add_point(
        beta.subject_id, content="乙科自己的考点", evidence="乙科原文", term="2026春"
    )
    beta_before = (beta.root / "exam_points.json").read_bytes()
    base = _legacy_base(alpha.subject_id)
    alpha.root.joinpath("exam_points.json").write_text(
        json.dumps([{**base, "subject_id": beta.subject_id}], ensure_ascii=False),
        encoding="utf-8",
    )
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(POINT_A)

    response = _detect(p1_route_client, alpha.subject_id)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert (beta.root / "exam_points.json").read_bytes() == beta_before
    assert [p["id"] for p in _raw(beta.subject_id)] == [beta_point["id"]]


def test_r3_legacy_records_without_identity_or_level_still_read(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """缺 subject_id/level 键的历史记录仍可读：可复用、视图补默认、磁盘不写回。"""
    subject_id = _subject()
    legacy = {
        "id": "legacy-no-meta",
        "content": POINT_A["content"],
        "evidence": POINT_A["evidence"],
        "kp": POINT_A["kp"],
        "term": "2026春",
        "confirmed": True,
        "created_at": 1790000000,
        "legacy_note": {"keep": True},
    }
    _path(subject_id).write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")
    before = _bytes(subject_id)
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(subject_id, [POINT_A], term="2026春")

    assert writes == []  # 只复用旧记录，因此零写
    assert _bytes(subject_id) == before
    assert stored[0]["id"] == "legacy-no-meta"
    assert stored[0]["subject_id"] == subject_id  # 视图补当前科目
    assert stored[0]["level"] == "inferred"  # 缺 level 键的视图默认
    assert stored[0]["legacy_note"] == {"keep": True}
    assert stored[0]["confirmed"] is True
    raw = _raw(subject_id)[0]
    assert "subject_id" not in raw and "level" not in raw  # 磁盘原样保留
    # 历史 inferred 记录正常可读
    historical = exam_points.add_point(
        subject_id, content="历史推断点", level="inferred", evidence="", term="2026春"
    )
    assert historical["level"] == "inferred"
    assert exam_points.load(subject_id)[-1]["level"] == "inferred"


def test_r3_the_reused_view_defaults_a_missing_subject_id_to_the_requested_subject(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_id = _subject()
    record = _legacy_base(subject_id)
    record.pop("subject_id")
    _path(subject_id).write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")
    before = _bytes(subject_id)
    writes = _count_writes(monkeypatch)

    stored = exam_points.upsert_detected(subject_id, [POINT_A], term="2026春")

    assert writes == []
    assert stored[0]["id"] == record["id"]
    assert stored[0]["subject_id"] == subject_id  # 只读视图补当前科目
    assert _bytes(subject_id) == before  # 磁盘上的记录没有被改写
    assert "subject_id" not in _raw(subject_id)[0]
