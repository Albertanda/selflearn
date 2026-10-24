"""P1-06 行为测试：批改成功一次只记一次、失败不污染学情（C05/C02/C01）。

目标：一次业务提交只写一次权威集合；评级失败/存储失败都不改动学情；新题答对不进入
错题本。

覆盖的必证场景（每类都是合法基准 + 只改一个目标字段/故障点）：

* 新题 correct：不创建 entry、不写（也不新建）``wrong_book.json``，返回
  ``saved=false`` / ``entry=null``；
* 新题 partial/wrong：创建 entry 与首个 attempt 在**一次**事务里完成，只发生一次权威写；
* 已存在的同题（trim 后精确匹配）：无论 correct/partial/wrong 都只 append 一次 attempt，
  掌握度/状态按既有公式重算；partial 仍按 ``correct=false`` 计；
* 精确匹配不扩成相似题：只差一个字符就是另一道题；
* 未涉及的旧记录不被回写派生字段，未知历史字段保留；
* provider/解析/预算/截断故障：真实 HTTP 非 2xx + 对应 C02 code，失败前后
  ``wrong_book.json`` 字节与目录状态完全不变；
* 并发同题 N 次提交：只有一个 entry 且恰好 N 个 attempt —— 并用**有效坏对照**（去掉
  事务锁，其余不变）证明"丢更新"确实会发生，即该断言承重。

HTTP 用例通过真实科目路由客户端发送表单；模型侧用真实 generation 路径上的替身
（``factory.complete_response`` 返回真实 ``TutorResponse``），配置是虚构的
``LLMConfig``。所有写入只发生在 tmp 隔离根。
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time

import pytest

from deeptutor.services.llm.exceptions import LLMProviderTransportError
from deeptutor.subjects import json_store, store, wrong_book
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX

#: 唯一虚构标记：错误投影、响应正文与落盘数据都不得出现它。
FAKE_BODY_MARKER = "p1-06-FAKE-BODY-5bd2e1-DO-NOT-LEAK"

_QUESTION = "求 f(x)=x^2 在 x=1 处的导数"


@pytest.mark.parametrize("existing_file", [False, True])
def test_unencodable_model_feedback_fails_before_any_attempt_is_committed(
    p1_subjects, p1_route_client, p1_providers, p1_llm, monkeypatch, existing_file
):
    subject = p1_subjects["科目A"]
    path = subject.root / "wrong_book.json"
    if existing_file:
        path.write_text("[]")
        before = path.read_bytes()
    else:
        path.unlink(missing_ok=True)
        before = None
    _install_cfg(monkeypatch)
    writes = _count_writes(monkeypatch)
    p1_llm.response = json.dumps({"verdict": "wrong", "feedback": "\ud800"})
    response = _check(p1_route_client, subject.subject_id, question=_QUESTION, student_answer="-2x")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert writes == []
    if before is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == before


def _schema(name: str) -> dict:
    """把 ``plans/phase1/schemas.json`` 的一个 ``$defs`` 条目变成可校验 schema。"""
    doc = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8"))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{name}",
        "$defs": doc["$defs"],
    }


def _install_cfg(monkeypatch: pytest.MonkeyPatch):
    """虚构 LLM 配置写入真实配置缓存（不读真实 settings/密钥）。"""
    import deeptutor.services.llm.config as config_mod

    cfg = config_mod.LLMConfig(
        model="p1-06-fake-model",
        api_key="p1-06-fake-key",
        base_url="http://127.0.0.1:9/v1",
    )
    monkeypatch.setattr(config_mod, "_LLM_CONFIG_CACHE", cfg)
    return cfg


def _count_writes(monkeypatch: pytest.MonkeyPatch, *, delay: float = 0.0) -> list[str]:
    """统计（并可放慢）权威写次数；放进锁内以放大读-改-写窗口。"""

    calls: list[str] = []
    real = json_store.atomic_write_json

    def counting(path, payload):
        calls.append(Path(path).name)
        if delay:
            time.sleep(delay)
        return real(path, payload)

    monkeypatch.setattr(json_store, "atomic_write_json", counting)
    return calls


def _data_digest(root: Path) -> dict[str, str]:
    """目录摘要，**排除** ``.deeptutor.lock``。

    读-改-写必须在同一 subject 锁内进行（C01），因此第一次取锁会在科目目录里留下一个
    空的锁文件；这是锁的正常副作用，不是学情数据写入。本文件断言的是权威集合
    （``wrong_book.json`` 及目录内容）不被污染。
    """
    return {
        name: digest
        for name, digest in helpers.tree_digest(root).items()
        if not name.endswith(json_store.LOCK_FILE_NAME)
    }


def _raw_entries(subject_root: Path) -> list[dict]:
    path = subject_root / "wrong_book.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _bad_control_unlocked():
    """坏对照：同一套读改写，但**没有**任何互斥。"""

    class _UnlockedTransaction:
        def __init__(self, directory):
            self._directory = Path(directory)

        def path(self, name):
            return self._directory / json_store.safe_segment(name)

        def read_list(self, path):
            time.sleep(0.05)  # 放大真实读-改-写窗口，让重叠必然发生
            return json_store.read_list(path)

        def write_list(self, path, records):
            json_store.atomic_write_list(path, records)

        def read_object(self, path, *, default):
            return json_store.read_object(path, default=default)

        def write_object(self, path, payload):
            json_store.atomic_write_object(path, payload)

    @contextmanager
    def _unlocked(lock_dir):
        yield _UnlockedTransaction(lock_dir)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(json_store, "json_transaction", _unlocked)
        _count_writes(patch, delay=0.02)
        yield


def _submit_concurrently(subject_id: str, *, workers: int, question: str) -> None:
    """N 个线程同时提交同一道题（wrong），用 barrier 真正制造重叠。"""
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            wrong_book.submit_graded_attempt(
                subject_id, question=question, correct=False, source="check"
            )
        except BaseException as exc:  # noqa: BLE001 - 收集后重新抛出
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors


def _failed_check(client, subject_id: str, **form):
    """发一次注定失败的批改请求，返回 (C02 code, response|None)。

    P1-56 的路由包装上线后，领域错误会被投影成完整 C02 响应；在此之前
    TestClient 会把同一个领域错误直接抛出。两种情况都要求**相同的 code**，
    因此本文件在阶段末（P1-56 完成后）复跑时断言不变。
    """
    try:
        response = client.post(f"{ROUTE_PREFIX}/{subject_id}/wrong-book/check", data=form)
    except SubjectOperationError as exc:
        return map_subject_exception(exc).code, None
    payload = response.json()
    return ErrorCode(payload["error"]["code"]), response


def _assert_c02(response, code: ErrorCode) -> None:
    from jsonschema import validate

    assert response is not None
    assert response.status_code >= 400
    body = response.json()
    validate(instance=body, schema=_schema("ErrorResponse"))
    assert body["error"]["code"] == code.value
    assert body["detail"] == body["error"]["message"]
    assert FAKE_BODY_MARKER not in response.text


# ---------------------------------------------------------------------------
# 模块级：一次提交 = 一次权威写
# ---------------------------------------------------------------------------
def test_new_correct_writes_nothing_and_creates_no_file(p1_runtime: Path):
    subject = store.create_subject("批改不写科目")
    root = store.subject_dir(subject["id"])
    (root / "wrong_book.json").unlink(missing_ok=True)
    before = _data_digest(root)

    result = wrong_book.submit_graded_attempt(
        subject["id"], question=_QUESTION, correct=True, answer="2x", kp="导数"
    )

    assert result is None
    assert not (root / "wrong_book.json").exists()
    assert _data_digest(root) == before


def test_new_wrong_creates_one_entry_with_one_attempt_in_one_write(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject = store.create_subject("新错题科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    (root / "wrong_book.json").unlink(missing_ok=True)
    writes = _count_writes(monkeypatch)

    entry = wrong_book.submit_graded_attempt(
        subject_id,
        question=f"  {_QUESTION}  ",
        correct=False,
        answer="2x",
        kp="导数",
        source="check",
    )

    assert writes == ["wrong_book.json"]  # 只发生一次权威写
    raw = _raw_entries(root)
    assert len(raw) == 1
    assert raw[0]["id"] == entry["id"]
    assert raw[0]["attempts"] == [
        {"ts": raw[0]["attempts"][0]["ts"], "correct": False, "session_id": ""}
    ]
    assert entry["question"] == _QUESTION  # trim 后存储
    assert entry["answer"] == "2x"
    assert entry["kp"] == "导数"
    assert entry["source"] == "check"
    assert entry["mastery"] == 0.0
    assert entry["status"] == "missed"
    assert entry["archived"] is False
    assert entry["created_at"] == raw[0]["created_at"]
    assert entry["updated_at"] == raw[0]["created_at"]  # 创建即首次尝试


def test_existing_entry_appends_exactly_one_attempt_and_recomputes(p1_runtime: Path):
    subject = store.create_subject("已有错题科目")
    subject_id = subject["id"]
    created = wrong_book.submit_graded_attempt(
        subject_id, question=_QUESTION, correct=False, kp="导数"
    )
    entry_id = created["id"]

    updated = wrong_book.submit_graded_attempt(
        subject_id, question=_QUESTION, correct=True, session_id="s-1"
    )

    assert updated["id"] == entry_id
    assert len(updated["attempts"]) == 2
    assert [a["correct"] for a in updated["attempts"]] == [False, True]
    assert updated["attempts"][1]["session_id"] == "s-1"
    assert updated["mastery"] == wrong_book.mastery_score([False, True])
    assert updated["status"] == wrong_book.classify([False, True])
    assert len(_raw_entries(store.subject_dir(subject_id))) == 1


def test_partial_on_an_existing_entry_counts_as_false(p1_runtime: Path):
    subject = store.create_subject("部分正确科目")
    subject_id = subject["id"]
    # 先制造一次真实的错答（新题答对不入本，所以基准必须从一次 miss 开始）
    seeded = wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)
    wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=True)

    updated = wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)

    assert updated["id"] == seeded["id"]
    assert [a["correct"] for a in updated["attempts"]] == [False, True, False]
    assert updated["mastery"] == wrong_book.mastery_score([False, True, False])
    assert updated["status"] == wrong_book.classify([False, True, False])


def test_trim_exact_match_reuses_the_entry_but_a_near_match_does_not(p1_runtime: Path):
    subject = store.create_subject("精确匹配科目")
    subject_id = subject["id"]
    first = wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)

    trimmed = wrong_book.submit_graded_attempt(
        subject_id, question=f"\t{_QUESTION} \n", correct=False
    )
    near = wrong_book.submit_graded_attempt(
        subject_id, question=_QUESTION + "？", correct=False
    )

    assert trimmed["id"] == first["id"]
    assert len(trimmed["attempts"]) == 2
    assert near["id"] != first["id"]
    assert len(_raw_entries(store.subject_dir(subject_id))) == 2


def test_untouched_legacy_records_keep_their_bytes_and_unknown_fields(p1_runtime: Path):
    """提交只改匹配到的那一条；不把派生读视图回写给所有旧题。"""
    subject = store.create_subject("遗留记录科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    legacy = {
        "id": "legacy01",
        "subject_id": subject_id,
        "question": "旧题：未作答记录",
        "kp": "旧知识点",
        "mastery": 1.0,
        "status": "mastered",
        "attempts": [],
        "archived": False,
        "legacy_note": "必须保留",
    }
    (root / "wrong_book.json").write_text(
        json.dumps([legacy], ensure_ascii=False), encoding="utf-8"
    )

    wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)

    raw = _raw_entries(root)
    preserved = next(r for r in raw if r["id"] == "legacy01")
    assert preserved["legacy_note"] == "必须保留"
    assert preserved["mastery"] == 1.0  # 派生值没有被回写
    assert preserved["status"] == "mastered"
    assert preserved["attempts"] == []
    # 读视图仍然是派生的：旧记录读出来是 0/untracked
    views = {e["id"]: e for e in wrong_book.load(subject_id)}
    assert views["legacy01"]["mastery"] == 0.0
    assert views["legacy01"]["status"] == "untracked"


def test_a_brand_new_wrong_answer_works_when_the_file_is_absent(p1_runtime: Path):
    subject = store.create_subject("无文件科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    (root / "wrong_book.json").unlink(missing_ok=True)

    entry = wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)

    assert entry is not None
    assert len(_raw_entries(root)) == 1


@pytest.mark.parametrize("bad_correct", ["false", 1, 0, None, "true"])
def test_correct_must_be_a_real_bool(p1_runtime: Path, bad_correct):
    subject = store.create_subject("布尔科目")
    subject_id = subject["id"]
    before = _data_digest(store.subject_dir(subject_id))

    with pytest.raises(SubjectOperationError) as excinfo:
        wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=bad_correct)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    assert _data_digest(store.subject_dir(subject_id)) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question", ""),
        ("question", "   "),
        ("question", None),
        ("question", 7),
        ("session_id", 5),
        ("answer", {"a": 1}),
        ("kp", ["导数"]),
        ("source", 3),
    ],
)
def test_caller_parameter_errors_write_nothing(p1_runtime: Path, field: str, value):
    subject = store.create_subject("参数科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    before = _data_digest(root)
    kwargs = {"question": _QUESTION, "correct": False, field: value}
    if field == "question":
        kwargs["question"] = value

    with pytest.raises(SubjectOperationError) as excinfo:
        wrong_book.submit_graded_attempt(subject_id, **kwargs)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    assert _data_digest(root) == before
    assert not (root / "wrong_book.json").exists()


@pytest.mark.parametrize("existing_entry", [True, False])
def test_injected_write_failure_keeps_the_old_bytes(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch, existing_entry: bool
):
    subject = store.create_subject("写失败科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    if existing_entry:
        wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)
    else:
        (root / "wrong_book.json").unlink(missing_ok=True)
    before = _data_digest(root)

    def exploding(path, payload):
        raise StorageIOError("注入的写入失败", path=Path(path).name)

    monkeypatch.setattr(json_store, "atomic_write_json", exploding)

    with pytest.raises(StorageIOError):
        wrong_book.submit_graded_attempt(subject_id, question=_QUESTION, correct=False)

    assert _data_digest(root) == before
    # 没有半条目：要么文件仍不存在，要么仍是原来那一条
    raw = _raw_entries(root)
    assert len(raw) == (1 if existing_entry else 0)


def test_a_mid_commit_failure_leaves_no_half_written_new_entry(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """新题写入失败：旧文件仍在，且不留下"没有 attempt 的条目"。"""
    subject = store.create_subject("半条目科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    original = [{"id": "keep01", "subject_id": subject_id, "question": "旧题", "attempts": []}]
    (root / "wrong_book.json").write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    before_bytes = (root / "wrong_book.json").read_bytes()

    def exploding(path, payload):
        raise StorageIOError("注入失败", path=Path(path).name)

    monkeypatch.setattr(json_store, "atomic_write_json", exploding)

    with pytest.raises(StorageIOError):
        wrong_book.submit_graded_attempt(subject_id, question="新题", correct=False)

    assert (root / "wrong_book.json").read_bytes() == before_bytes
    raw = _raw_entries(root)
    assert [r["id"] for r in raw] == ["keep01"]
    assert all(r.get("attempts") == [] for r in raw)


# ---------------------------------------------------------------------------
# 并发：同题 N 次提交 = 1 个 entry + N 个 attempt（含有效坏对照）
# ---------------------------------------------------------------------------
def test_concurrent_submits_of_one_question_keep_every_attempt(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    subject = store.create_subject("并发科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    (root / "wrong_book.json").unlink(missing_ok=True)
    writes = _count_writes(monkeypatch, delay=0.02)

    _submit_concurrently(subject_id, workers=4, question=_QUESTION)

    raw = _raw_entries(root)
    assert len(raw) == 1
    assert len(raw[0]["attempts"]) == 4
    assert [a["correct"] for a in raw[0]["attempts"]] == [False] * 4
    assert len(writes) == 4  # 每个线程一次提交各写一次，没有额外写


def test_bad_control_without_the_lock_the_same_scenario_loses_updates(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """坏对照：只去掉事务锁，其余不变 —— 4 次提交不会都留下。"""
    subject = store.create_subject("坏对照科目")
    subject_id = subject["id"]
    root = store.subject_dir(subject_id)
    file = root / "wrong_book.json"
    file.unlink(missing_ok=True)

    with _bad_control_unlocked():
        _submit_concurrently(subject_id, workers=4, question=_QUESTION)
    unlocked_raw = _raw_entries(root)

    # 恢复真实锁，重跑同一场景
    file.unlink(missing_ok=True)
    _count_writes(monkeypatch, delay=0.02)
    _submit_concurrently(subject_id, workers=4, question=_QUESTION)
    locked_raw = _raw_entries(root)

    # 坏对照：丢更新（少于 4 个 attempt）——证明上面的并发断言承重
    assert len(unlocked_raw) == 1
    assert len(unlocked_raw[0]["attempts"]) < 4
    # 真实锁：一个 entry、4 个 attempt，一个都不丢
    assert len(locked_raw) == 1
    assert len(locked_raw[0]["attempts"]) == 4


# ---------------------------------------------------------------------------
# HTTP：成功形状、C02 失败形状、失败零污染
# ---------------------------------------------------------------------------
def _check(client, subject_id: str, **form):
    return client.post(f"{ROUTE_PREFIX}/{subject_id}/wrong-book/check", data=form)


def test_http_new_correct_creates_no_file_and_returns_saved_false(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from jsonschema import validate

    subject = p1_subjects["科目A"]
    (subject.root / "wrong_book.json").unlink(missing_ok=True)
    before = _data_digest(subject.root)
    _install_cfg(monkeypatch)
    p1_llm.response = '{"verdict": "correct", "feedback": "思路正确"}'

    response = _check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="2x",
        reference_answer="2x",
        kp="导数",
    )

    assert response.status_code == 200
    body = response.json()
    validate(instance=body, schema=_schema("GradeResponse"))
    assert body == {
        "verdict": "correct",
        "feedback": "思路正确",
        "correct": True,
        "entry": None,
        "saved": False,
    }
    assert not (subject.root / "wrong_book.json").exists()
    assert _data_digest(subject.root) == before


def test_http_new_wrong_saves_one_entry_once(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from jsonschema import validate

    subject = p1_subjects["科目A"]
    (subject.root / "wrong_book.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    writes = _count_writes(monkeypatch)
    p1_llm.response = '{"verdict": "wrong", "feedback": "符号错了"}'

    response = _check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="-2x",
        reference_answer="2x",
    )

    assert response.status_code == 200
    body = response.json()
    validate(instance=body, schema=_schema("GradeResponse"))
    assert body["saved"] is True
    assert body["correct"] is False
    assert body["entry"]["attempts"] == [
        {"ts": body["entry"]["attempts"][0]["ts"], "correct": False, "session_id": ""}
    ]
    assert writes == ["wrong_book.json"]
    assert len(_raw_entries(subject.root)) == 1


def test_http_existing_entry_correct_raises_mastery(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    subject = p1_subjects["科目A"]
    seeded = wrong_book.submit_graded_attempt(
        subject.subject_id, question=_QUESTION, correct=False, source="check"
    )
    _install_cfg(monkeypatch)
    p1_llm.response = '{"verdict": "correct", "feedback": "这次对了"}'

    response = _check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="2x",
        reference_answer="2x",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    assert body["entry"]["id"] == seeded["id"]
    assert [a["correct"] for a in body["entry"]["attempts"]] == [False, True]
    assert body["entry"]["mastery"] == wrong_book.mastery_score([False, True])
    assert body["entry"]["mastery"] > 0.0


@pytest.mark.parametrize("verdict", ["partial", "wrong"])
def test_http_new_partial_or_wrong_maps_to_correct_false_with_one_attempt(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    verdict: str,
):
    subject = p1_subjects["科目B"]
    (subject.root / "wrong_book.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = f'{{"verdict": "{verdict}", "feedback": "反馈"}}'

    response = _check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="乱写",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == verdict
    assert body["correct"] is False
    assert body["saved"] is True
    assert [a["correct"] for a in body["entry"]["attempts"]] == [False]


@pytest.mark.parametrize(
    ("text", "finish_reason", "usage", "expected"),
    [
        ("", "stop", None, ErrorCode.EMPTY_MODEL_OUTPUT),
        ('{"verdict": "cor', "length", {"completion_tokens": 16000}, ErrorCode.OUTPUT_TRUNCATED),
        ("", "length", {"completion_tokens": 16000}, ErrorCode.REASONING_BUDGET_EXHAUSTED),
        ("不是 JSON", "stop", None, ErrorCode.INVALID_MODEL_OUTPUT),
        ('{"feedback": "缺 verdict"}', "stop", None, ErrorCode.INVALID_MODEL_OUTPUT),
    ],
)
def test_http_grading_failures_are_non_2xx_c02_and_change_nothing(
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
    seeded = wrong_book.submit_graded_attempt(
        subject.subject_id, question=_QUESTION, correct=False
    )
    before = _data_digest(subject.root)
    _install_cfg(monkeypatch)
    p1_llm.response = text
    p1_llm.finish_reason = finish_reason
    p1_llm.usage = usage

    code, response = _failed_check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="2x",
        reference_answer="2x",
    )

    assert code is expected
    if response is not None:
        _assert_c02(response, expected)
    assert _data_digest(subject.root) == before
    entry = wrong_book.find_by_question(subject.subject_id, _QUESTION)
    assert entry["id"] == seeded["id"] and len(entry["attempts"]) == 1


def test_http_provider_failure_is_502_and_leaks_neither_message_nor_path(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目A"]
    before = _data_digest(subject.root)
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
        monkeypatch,
        llm=_RaisingLLM(LLMProviderTransportError(f"宿主路径 /home/secret 与标记 {FAKE_BODY_MARKER}")),
    )

    code, response = _failed_check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="2x",
    )

    assert code is ErrorCode.PROVIDER_UNAVAILABLE
    if response is not None:
        _assert_c02(response, ErrorCode.PROVIDER_UNAVAILABLE)
        assert "/home/secret" not in response.text
    assert _data_digest(subject.root) == before


def test_http_blank_input_is_rejected_without_writing(
    p1_subjects, p1_route_client, p1_providers, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目A"]
    (subject.root / "wrong_book.json").unlink(missing_ok=True)
    before = _data_digest(subject.root)
    _install_cfg(monkeypatch)

    response = _check(
        p1_route_client, subject.subject_id, question="   ", student_answer="2x"
    )

    assert response.status_code == 400
    assert _data_digest(subject.root) == before
    assert not (subject.root / "wrong_book.json").exists()


def test_http_response_never_carries_the_student_answer_or_diagnostics(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """错误响应的服务端诊断（长度/摘要）不进入响应；成功响应也只有约定字段。"""
    subject = p1_subjects["科目B"]
    _install_cfg(monkeypatch)
    p1_llm.response = '{"verdict": "partial", "feedback": "第二问漏了"}'

    response = _check(
        p1_route_client,
        subject.subject_id,
        question=_QUESTION,
        student_answer="只写了一半",
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"verdict", "feedback", "correct", "entry", "saved"}
    # 学生作答既不出现在响应里，也不会被当成参考答案/解析写进错题记录。
    assert "只写了一半" not in response.text
    assert body["entry"]["answer"] == ""
    assert body["entry"]["analysis"] == ""


class _RaisingLLM(helpers.FakeLLMClient):
    def __init__(self, error: BaseException) -> None:
        super().__init__("")
        self.error = error

    async def complete_response(self, prompt: str = "", **kwargs):
        self._record(prompt=prompt, **kwargs)
        raise self.error


def test_route_helper_grading_result_shape_is_stable(p1_runtime: Path):
    """``_ai_grade`` 现在返回经过验证的 GradeResult（不再是裸 tuple）。"""
    from deeptutor.api.routers import subjects as subjects_router
    from deeptutor.subjects import grading

    assert asyncio.iscoroutinefunction(subjects_router._ai_grade)
    assert grading.GradeResult.__dataclass_fields__.keys() == {"verdict", "feedback"}
