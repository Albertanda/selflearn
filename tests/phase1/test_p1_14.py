"""P1-14 行为测试：知识点与画像剩余存储接入（C01/C10）。

覆盖卡的必证场景，每个都有正例与只改一个目标字段/故障点的反例：

* 并发 add/link 不丢记录（受锁的完整读改写）；
* profile 缺失给独立默认对象、损坏报错、拒读报错 —— 三条各自独立；
* 旧未知字段保留；
* facts 去重与 20 条上限、link 幂等不回归；
* 默认值不跨调用共享可变 dict/list；
* 不调用真实 LLM、不做自动画像抽取。

只使用 tmp 隔离根，不触碰真实数据。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from deeptutor.subjects import json_store, profile, store
from deeptutor.subjects import knowledge_points as kp
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)


def _subject(name: str = "知识点科目") -> str:
    return store.create_subject(name)["id"]


def _kp_path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "knowledge_points.json"


def _profile_path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "profile.json"


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_review_mixed_name_batch_rejects_invalid_element_without_write(p1_runtime, value):
    sid = _subject()
    kp.add_point(sid, name="existing")
    path = _kp_path(sid)
    before = path.read_bytes()
    with pytest.raises(SubjectOperationError) as error:
        kp.add_many(sid, ["valid new name", value])
    assert error.value.code == ErrorCode.INVALID_INPUT
    assert path.read_bytes() == before


@pytest.mark.parametrize("key", ["path", "source", "created_at"])
def test_review_knowledge_record_null_is_corrupt_not_missing(p1_runtime, key):
    sid = _subject()
    record = kp.add_point(sid, name="valid")
    assert kp.load(sid)
    record[key] = None
    path = _kp_path(sid)
    path.write_text(json.dumps([record]))
    before = path.read_bytes()
    with pytest.raises(StorageCorruptError):
        kp.load(sid)
    with pytest.raises(StorageCorruptError):
        kp.add_point(sid, name="other")
    assert path.read_bytes() == before


def test_review_fact_null_timestamp_is_corrupt_not_missing(p1_runtime):
    sid = _subject()
    data = profile.add_fact(sid, "valid fact")
    assert profile.load(sid)
    data["facts"][0]["ts"] = None
    path = _profile_path(sid)
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(StorageCorruptError):
        profile.load(sid)
    with pytest.raises(StorageCorruptError):
        profile.add_fact(sid, "other")
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# 知识点：正例与严格失败
# ---------------------------------------------------------------------------
def test_add_point_defaults_and_unknown_fields(p1_runtime: Path):
    subject_id = _subject()
    point = kp.add_point(subject_id, name="极限", source="manual")

    assert point["name"] == "极限"
    assert point["path"] == "极限"
    assert point["wrong_ids"] == []
    assert point["exam_point_ids"] == []
    assert kp.load(subject_id) == [point]
    assert kp.get_point(subject_id, point["id"]) == point
    assert kp.find_by_name(subject_id, " 极限 ") == point


def test_add_point_is_idempotent_by_name(p1_runtime: Path):
    subject_id = _subject()
    first = kp.add_point(subject_id, name="导数")
    second = kp.add_point(subject_id, name=" 导数 ")

    assert first["id"] == second["id"]
    assert len(kp.load(subject_id)) == 1


def test_add_many_keeps_unknown_fields_and_skips_blanks(p1_runtime: Path):
    subject_id = _subject()
    out = kp.add_many(subject_id, ["极限", "  ", "", "导数"], source="llm")

    assert [p["name"] for p in out] == ["极限", "导数"]
    assert len(kp.load(subject_id)) == 2


def test_missing_is_empty_but_corrupt_is_an_error(p1_runtime: Path):
    subject_id = _subject()
    assert kp.load(subject_id) == []

    _kp_path(subject_id).write_text("[{", encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        kp.load(subject_id)


@pytest.mark.parametrize(
    "text",
    [
        '{"points": []}',
        '[{"id": "a"}]',
        '[{"name": "no id"}]',
        '[{"id": "a", "name": "x", "wrong_ids": "nope"}]',
        '[{"id": "a", "name": "x", "exam_point_ids": {}}]',
        '[{"id": "a", "name": "x", "wrong_ids": [1], "mastery": NaN}]',
    ],
)
def test_damaged_point_files_are_corrupt_and_not_overwritten(p1_runtime: Path, text: str):
    subject_id = _subject()
    path = _kp_path(subject_id)
    path.write_text(text, encoding="utf-8")

    for action in (
        lambda: kp.load(subject_id),
        lambda: kp.add_point(subject_id, name="新点"),
        lambda: kp.link_wrong_entry(subject_id, "x", "w1"),
        lambda: kp.add_many(subject_id, ["新点"]),
    ):
        with pytest.raises(StorageCorruptError):
            action()
        assert path.read_text(encoding="utf-8") == text


def test_unknown_historical_fields_survive_a_link(p1_runtime: Path):
    subject_id = _subject()
    _kp_path(subject_id).write_text(
        json.dumps(
            [
                {
                    "id": "legacy-1",
                    "subject_id": subject_id,
                    "name": "旧知识点",
                    "path": "第一章/旧知识点",
                    "source": "manual",
                    "wrong_ids": [],
                    "exam_point_ids": [],
                    "created_at": 1700000000,
                    "legacy_note": {"keep": ["me"]},
                }
            ]
        ),
        encoding="utf-8",
    )

    linked = kp.link_wrong_entry(subject_id, "旧知识点", "w-1")

    assert linked["wrong_ids"] == ["w-1"]
    assert linked["legacy_note"] == {"keep": ["me"]}
    assert linked["created_at"] == 1700000000
    assert linked["path"] == "第一章/旧知识点"


# ---------------------------------------------------------------------------
# 知识点：link 幂等与并发
# ---------------------------------------------------------------------------
def test_link_is_idempotent_and_scoped_to_the_named_point(p1_runtime: Path):
    subject_id = _subject()
    target = kp.add_point(subject_id, name="积分")
    other = kp.add_point(subject_id, name="微分")

    kp.link_wrong_entry(subject_id, "积分", "w-1")
    kp.link_wrong_entry(subject_id, "积分", "w-1")  # 重复不重加
    kp.link_exam_point(subject_id, "积分", "e-1")
    kp.link_exam_point(subject_id, "积分", "e-1")

    points = {p["id"]: p for p in kp.load(subject_id)}
    assert points[target["id"]]["wrong_ids"] == ["w-1"]
    assert points[target["id"]]["exam_point_ids"] == ["e-1"]
    assert points[other["id"]]["wrong_ids"] == []


def test_link_to_an_unknown_point_returns_none_without_writing(p1_runtime: Path):
    subject_id = _subject()
    kp.add_point(subject_id, name="极限")
    before = _kp_path(subject_id).read_bytes()

    assert kp.link_wrong_entry(subject_id, "不存在", "w-1") is None
    assert kp.link_exam_point(subject_id, "", "e-1") is None
    assert _kp_path(subject_id).read_bytes() == before


def test_concurrent_adds_do_not_lose_points(p1_runtime: Path):
    subject_id = _subject()
    workers = 8
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            kp.add_point(subject_id, name=f"知识点{index}")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    names = sorted(p["name"] for p in kp.load(subject_id))
    assert names == sorted(f"知识点{i}" for i in range(workers))


def test_concurrent_same_name_add_creates_exactly_one_point(p1_runtime: Path):
    subject_id = _subject()
    workers = 8
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=15)
            kp.add_point(subject_id, name="同名知识点")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    assert len(kp.load(subject_id)) == 1  # 不是 8 个重复点


def test_concurrent_links_do_not_lose_ids(p1_runtime: Path):
    subject_id = _subject()
    target = kp.add_point(subject_id, name="级数")
    workers = 10
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            kp.link_wrong_entry(subject_id, "级数", f"w-{index}")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    stored = kp.get_point(subject_id, target["id"])
    assert sorted(stored["wrong_ids"]) == sorted(f"w-{i}" for i in range(workers))


def test_link_lost_update_bad_control(p1_runtime: Path):
    """受控坏对照：绕过锁的两次 link 会丢掉其中一个 id。"""
    import contextlib

    from deeptutor.subjects.json_store import JsonTransaction

    subject_id = _subject()
    target = kp.add_point(subject_id, name="曲线")
    path = _kp_path(subject_id)
    both_read = threading.Barrier(2)
    errors: list[BaseException] = []

    @contextlib.contextmanager
    def unlocked():
        yield JsonTransaction(store.subject_dir(subject_id))

    def worker(tag: str) -> None:
        try:
            with unlocked() as tx:
                points = tx.read_list(path)
                for point in points:
                    point.setdefault("wrong_ids", []).append(tag)
                snapshot = [dict(p) for p in points]
                both_read.wait(timeout=10)
                tx.write_list(path, snapshot)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    lost = json.loads(path.read_text(encoding="utf-8"))[0]["wrong_ids"]
    assert len(lost) == 1  # 后写者覆盖了前写者

    # 对照：走真锁再链一次，两个都在
    kp.link_wrong_entry(subject_id, "曲线", "w0")
    kp.link_wrong_entry(subject_id, "曲线", "w1")
    assert sorted(kp.get_point(subject_id, target["id"])["wrong_ids"]) == ["w0", "w1"]


def test_links_stay_inside_one_subject(p1_runtime: Path):
    subject_a = _subject("甲知识点科目")
    subject_b = _subject("乙知识点科目")
    a_point = kp.add_point(subject_a, name="同名点")
    b_point = kp.add_point(subject_b, name="同名点")

    kp.link_wrong_entry(subject_a, "同名点", "w-a")

    assert kp.get_point(subject_a, a_point["id"])["wrong_ids"] == ["w-a"]
    assert kp.get_point(subject_b, b_point["id"])["wrong_ids"] == []


# ---------------------------------------------------------------------------
# 画像
# ---------------------------------------------------------------------------
def test_profile_defaults_are_fresh_objects_each_call(p1_runtime: Path):
    subject_id = _subject()

    first = profile.load(subject_id)
    first["facts"].append({"text": "leaked", "ts": 1})
    first["goals"] = "changed"

    second = profile.load(subject_id)
    assert second == {"goals": "", "explanation_style": "balanced", "facts": [], "updated_at": 0}
    assert not _profile_path(subject_id).exists()  # 读到默认不等于落盘


def test_profile_defaults_do_not_leak_between_subjects(p1_runtime: Path):
    a = _subject("甲画像科目")
    b = _subject("乙画像科目")

    profile.add_fact(a, "甲的事实")

    assert profile.load(b)["facts"] == []
    assert [f["text"] for f in profile.load(a)["facts"]] == ["甲的事实"]


def test_profile_update_and_facts_round_trip(p1_runtime: Path):
    subject_id = _subject()

    updated = profile.update(subject_id, goals="考上研", explanation_style="theory")
    assert updated["goals"] == "考上研"
    assert updated["explanation_style"] == "theory"
    assert isinstance(updated["updated_at"], int) and updated["updated_at"] > 0

    profile.add_fact(subject_id, "喜欢用例子理解")
    stored = profile.load(subject_id)
    assert [f["text"] for f in stored["facts"]] == ["喜欢用例子理解"]
    assert stored["goals"] == "考上研"


def test_profile_unknown_style_falls_back_but_unknown_fields_survive(p1_runtime: Path):
    subject_id = _subject()
    _profile_path(subject_id).write_text(
        json.dumps(
            {
                "goals": "旧目标",
                "explanation_style": "unknown-style",
                "facts": [],
                "legacy_note": {"keep": ["me"]},
                "theme": "dark",
            }
        ),
        encoding="utf-8",
    )

    loaded = profile.load(subject_id)
    assert loaded["explanation_style"] == "balanced"     # 既有规则
    assert loaded["legacy_note"] == {"keep": ["me"]}     # 未知字段保留
    assert loaded["theme"] == "dark"

    profile.update(subject_id, goals="新目标")
    after = json.loads(_profile_path(subject_id).read_text(encoding="utf-8"))
    assert after["legacy_note"] == {"keep": ["me"]}
    assert after["theme"] == "dark"


# ---------------------------------------------------------------------------
# 画像：三条独立的错误路径
# ---------------------------------------------------------------------------
def test_missing_profile_is_default_not_corrupt(p1_runtime: Path):
    subject_id = _subject()
    assert not _profile_path(subject_id).exists()

    loaded = profile.load(subject_id)

    assert loaded["goals"] == ""
    assert loaded["facts"] == []
    assert profile.add_fact(subject_id, "")["facts"] == []


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        '["not", "an", "object"]',
        '{"facts": "nope"}',
        '{"facts": [{"ts": 1}]}',
        '{"facts": [1, 2]}',
        '{"goals": 5}',
        '{"value": NaN}',
    ],
)
def test_a_damaged_profile_raises_instead_of_falling_back_to_defaults(
    p1_runtime: Path, text: str
):
    """坏 profile 不能退默认后覆盖：必须报错，且旧字节保持。"""
    subject_id = _subject()
    path = _profile_path(subject_id)
    path.write_text(text, encoding="utf-8")

    for action in (
        lambda: profile.load(subject_id),
        lambda: profile.update(subject_id, goals="要覆盖了"),
        lambda: profile.add_fact(subject_id, "新事实"),
    ):
        with pytest.raises(StorageCorruptError):
            action()
        assert path.read_text(encoding="utf-8") == text


def test_an_unreadable_profile_raises_storage_io(p1_runtime: Path):
    subject_id = _subject()
    path = _profile_path(subject_id)
    path.mkdir()  # 目录冒充文件：确定性拒读

    with pytest.raises(StorageIOError) as excinfo:
        profile.load(subject_id)

    assert not isinstance(excinfo.value, StorageCorruptError)
    assert map_subject_exception(excinfo.value).code is ErrorCode.STORAGE_IO


def test_corrupt_profile_diagnostics_stay_relative(p1_runtime: Path):
    subject_id = _subject()
    marker = "p1-14-FAKE-PROFILE-DO-NOT-LEAK"
    _profile_path(subject_id).write_text(f'{{"goals": "{marker}"', encoding="utf-8")

    with pytest.raises(StorageCorruptError) as excinfo:
        profile.load(subject_id)

    error = excinfo.value
    assert error.path == "profile.json"
    assert marker not in str(error)
    assert str(p1_runtime) not in str(error)


# ---------------------------------------------------------------------------
# 画像：facts 策略与并发
# ---------------------------------------------------------------------------
def test_facts_dedupe_and_20_item_cap(p1_runtime: Path):
    subject_id = _subject()

    for index in range(25):
        profile.add_fact(subject_id, f"事实{index}")
    profile.add_fact(subject_id, "事实5")      # 重复不新增、不移动
    profile.add_fact(subject_id, "   事实5   ")  # trim 后同样视为重复

    facts = profile.load(subject_id)["facts"]
    assert len(facts) == 20                          # 上限保持
    assert [f["text"] for f in facts] == [f"事实{i}" for i in range(5, 25)]
    assert len({f["text"] for f in facts}) == 20     # 没有重复


def test_blank_fact_is_ignored_without_writing(p1_runtime: Path):
    subject_id = _subject()
    profile.update(subject_id, goals="目标")
    before = _profile_path(subject_id).read_bytes()

    for blank in ("", "   ", "\n\t"):
        profile.add_fact(subject_id, blank)

    assert _profile_path(subject_id).read_bytes() == before


def test_concurrent_facts_are_not_lost(p1_runtime: Path):
    subject_id = _subject()
    workers = 12
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            profile.add_fact(subject_id, f"并发事实{index}")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    texts = sorted(f["text"] for f in profile.load(subject_id)["facts"])
    assert texts == sorted(f"并发事实{i}" for i in range(workers))


def test_concurrent_profile_updates_do_not_lose_a_change(p1_runtime: Path):
    subject_id = _subject()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def set_goals() -> None:
        try:
            barrier.wait(timeout=15)
            profile.update(subject_id, goals="考研")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def set_style() -> None:
        try:
            barrier.wait(timeout=15)
            profile.update(subject_id, explanation_style="examples")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=set_goals), threading.Thread(target=set_style)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    stored = profile.load(subject_id)
    assert stored["goals"] == "考研"
    assert stored["explanation_style"] == "examples"


def test_facts_lost_update_bad_control(p1_runtime: Path):
    """受控坏对照：绕过锁的 fact 写入会丢掉其中一条。"""
    import contextlib

    from deeptutor.subjects.json_store import JsonTransaction

    subject_id = _subject()
    path = _profile_path(subject_id)
    profile.add_fact(subject_id, "起点")
    both_read = threading.Barrier(2)
    errors: list[BaseException] = []

    @contextlib.contextmanager
    def unlocked():
        yield JsonTransaction(store.subject_dir(subject_id))

    def worker(tag: str) -> None:
        try:
            with unlocked() as tx:
                data = tx.read_object(path, default={})
                facts = list(data.get("facts") or [])
                facts.append({"text": tag, "ts": 1})
                data["facts"] = facts
                both_read.wait(timeout=10)
                tx.write_object(path, data)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"f{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    lost = json.loads(path.read_text(encoding="utf-8"))["facts"]
    assert [f["text"] for f in lost] == ["起点", "f0"] or [f["text"] for f in lost] == [
        "起点",
        "f1",
    ]

    # 对照：走真锁再写两条，都在
    profile.add_fact(subject_id, "f0")
    profile.add_fact(subject_id, "f1")
    texts = [f["text"] for f in profile.load(subject_id)["facts"]]
    assert texts[0] == "起点" and "f0" in texts and "f1" in texts


def test_context_summaries_do_not_call_any_model(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    """本卡不触发 LLM 自动抽取：摘要只读本地存储。"""
    subject_id = _subject()
    kp.add_point(subject_id, name="极限")
    profile.add_fact(subject_id, "喜欢图示")
    profile.update(subject_id, goals="期末复习")

    def explode(*_args: object, **_kwargs: object):
        raise AssertionError("本阶段不得触发任何模型调用")

    import deeptutor.services.llm.factory as factory

    monkeypatch.setattr(factory, "complete_response", explode, raising=False)
    monkeypatch.setattr(factory, "complete", explode, raising=False)

    assert "极限" in kp.context_summary(subject_id)
    assert "喜欢图示" in profile.context_summary(subject_id)


# ---------------------------------------------------------------------------
# R1/R3/R4（rework01）
# ---------------------------------------------------------------------------
def _write_raw(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_a_symlinked_collection_is_refused_before_reading(p1_runtime: Path):
    a = _subject("甲防护科")
    b = _subject("乙防护科")
    kp.add_point(a, name="alpha")
    kp.add_point(b, name="beta")
    link = _kp_path(a)
    victim = _kp_path(b)
    link.unlink()
    link.symlink_to(victim)

    reads: list[str] = []
    real_open = os.open

    def spying_open(target: object, flags: int, *args: object, **kwargs: object) -> int:
        try:
            if Path(str(target)).resolve() == victim.resolve():
                reads.append(str(target))
        except OSError:  # pragma: no cover
            pass
        return real_open(target, flags, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", spying_open)
        with pytest.raises((StorageIOError, SubjectOperationError)):
            kp.load(a)

    assert reads == []
    assert victim.is_file()


def test_a_symlinked_profile_is_refused_before_reading(p1_runtime: Path):
    a = _subject("甲画像科")
    b = _subject("乙画像科")
    profile.update(a, goals="alpha")
    profile.update(b, goals="beta")
    link = _profile_path(a)
    victim = _profile_path(b)
    link.unlink()
    link.symlink_to(victim)

    with pytest.raises((StorageIOError, SubjectOperationError)):
        profile.load(a)

    assert json.loads(victim.read_text(encoding="utf-8"))["goals"] == "beta"


@pytest.mark.parametrize(
    "point",
    [
        {"id": "x"},                                    # 缺 name
        {"id": "x", "name": 7},
        {"id": "x", "name": "n", "wrong_ids": None},    # 显式 null 是损坏
        {"id": "x", "name": "n", "exam_point_ids": None},
        {"id": "x", "name": "n", "wrong_ids": "nope"},
        {"id": "x", "name": "n", "wrong_ids": [1]},
        {"id": "x", "name": "n", "path": 7},
        {"id": "x", "name": "n", "source": []},
        {"id": "x", "name": "n", "created_at": True},
    ],
)
def test_corrupt_point_fields_are_rejected_and_not_overwritten(p1_runtime: Path, point):
    subject_id = _subject("坏知识点科")
    path = _write_raw(_kp_path(subject_id), json.dumps([point]))
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError):
        kp.load(subject_id)
    with pytest.raises(StorageCorruptError):
        kp.link_wrong_entry(subject_id, "n", "w")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "payload",
    [
        '{"facts": null}',
        '{"facts": "nope"}',
        '{"facts": [{"ts": 1}]}',
        '{"facts": [1]}',
        '{"facts": [{"text": "ok", "ts": true}]}',
        '{"goals": 5}',
        '{"explanation_style": []}',
        '{"explanation_style": 3}',
        '{"updated_at": true}',
        '{"updated_at": "soon"}',
    ],
)
def test_corrupt_profile_fields_are_rejected_and_not_overwritten(
    p1_runtime: Path, payload: str
):
    subject_id = _subject("坏画像科")
    path = _write_raw(_profile_path(subject_id), payload)
    before = path.read_bytes()

    for action in (
        lambda: profile.load(subject_id),
        lambda: profile.update(subject_id, goals="新目标"),
        lambda: profile.add_fact(subject_id, "新事实"),
    ):
        with pytest.raises(StorageCorruptError):
            action()
        assert path.read_bytes() == before


def test_a_legacy_profile_without_optional_fields_is_usable(p1_runtime: Path):
    subject_id = _subject("旧画像科")
    path = _write_raw(_profile_path(subject_id), json.dumps({"legacy_note": {"keep": True}}))
    before = path.read_bytes()

    loaded = profile.load(subject_id)

    assert loaded["goals"] == ""
    assert loaded["explanation_style"] == "balanced"
    assert loaded["facts"] == []
    assert loaded["legacy_note"] == {"keep": True}
    assert path.read_bytes() == before                     # 读取不写回
    assert "用户画像" in profile.context_summary(subject_id)


def test_an_unknown_but_string_style_keeps_the_balanced_fallback(p1_runtime: Path):
    subject_id = _subject("未知风格科")
    _write_raw(
        _profile_path(subject_id),
        json.dumps({"goals": "g", "explanation_style": "brand-new-style", "facts": []}),
    )

    assert profile.load(subject_id)["explanation_style"] == "balanced"


@pytest.mark.parametrize("bad", ["   ", "", 7, None, [1]])
def test_blank_or_non_string_point_name_is_invalid_input(p1_runtime: Path, bad):
    subject_id = _subject("空名字科")
    path = _kp_path(subject_id)
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(json_store.InvalidInputError) as excinfo:
        kp.add_point(subject_id, name=bad)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    after = path.read_bytes() if path.exists() else None
    assert after == before


@pytest.mark.parametrize(
    "action",
    [
        lambda sid: profile.update(sid, goals=7),
        lambda sid: profile.update(sid, explanation_style=[]),
        lambda sid: profile.add_fact(sid, 7),
    ],
)
def test_invalid_profile_parameters_are_not_storage_corruption(p1_runtime: Path, action):
    subject_id = _subject("画像参数科")
    path = _profile_path(subject_id)
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(json_store.InvalidInputError) as excinfo:
        action(subject_id)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    after = path.read_bytes() if path.exists() else None
    assert after == before


def test_add_many_never_creates_a_blank_named_point(p1_runtime: Path):
    subject_id = _subject("批量名字科")

    out = kp.add_many(subject_id, ["极限", "   ", "", "导数"], source="llm")

    assert [p["name"] for p in out] == ["极限", "导数"]
    assert all(p["name"].strip() for p in kp.load(subject_id))
