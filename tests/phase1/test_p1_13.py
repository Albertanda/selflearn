"""P1-13 行为测试：考点集合事务与整批提交（C01/C06）。

覆盖卡的必证场景，每个都有正例与只改一个目标字段/故障点的反例：

* confirm 与 add 真并发，两个改动都保留（不是只保护最后一次 write）；
* 坏批次一条都不留（整批先校验、再一次权威写）；合法批次只写一次；
* 历史 inferred 可读；JSON 损坏与文件缺失可区分；
* 删除考点不碰别科；未知历史字段保留、不擅自全确认。

只使用 tmp 隔离根，不触碰真实数据，也不触发任何真实模型识别。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from deeptutor.subjects import exam_points, json_store, store
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)


def _subject(name: str = "考点科目") -> str:
    return store.create_subject(name)["id"]


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "exam_points.json"


def _point(subject_id: str, content: str = "洛必达法则", **overrides) -> dict:
    kwargs = {"content": content, "term": "2026春"}
    kwargs.update(overrides)
    return exam_points.add_point(subject_id, **kwargs)


# ---------------------------------------------------------------------------
# 正例基准
# ---------------------------------------------------------------------------
def test_add_point_defaults_to_inferred_and_unconfirmed(p1_runtime: Path):
    subject_id = _subject()
    point = _point(subject_id)

    assert point["level"] == "inferred"
    assert point["confirmed"] is False
    assert point["term"] == "2026春"
    assert point["source"] == "manual"
    assert isinstance(point["created_at"], int)
    assert exam_points.load(subject_id) == [point]


def test_missing_is_empty_but_corrupt_is_an_error(p1_runtime: Path):
    subject_id = _subject()
    assert exam_points.load(subject_id) == []          # missing -> []

    _path(subject_id).write_text("[{", encoding="utf-8")
    with pytest.raises(StorageCorruptError):           # corrupt -> error
        exam_points.load(subject_id)


@pytest.mark.parametrize(
    "text",
    [
        '{"points": []}',
        '[{"id": "a", "level": 3}]',
        '[{"id": "a", "confirmed": "yes"}]',
        '[{"content": "no id"}]',
        '[{"id": "a", "term": ["2026"]}]',
        '[{"id": "a", "mastery": NaN}]',
    ],
)
def test_damaged_or_wrongly_typed_files_are_corrupt(p1_runtime: Path, text: str):
    subject_id = _subject()
    path = _path(subject_id)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(StorageCorruptError):
        exam_points.load(subject_id)
    with pytest.raises(StorageCorruptError):
        _point(subject_id, "新考点")
    assert path.read_text(encoding="utf-8") == text  # 坏文件不被覆盖


def test_diagnostics_stay_relative(p1_runtime: Path):
    subject_id = _subject()
    _path(subject_id).write_text('[{"id": "a", "level": 3}]', encoding="utf-8")

    with pytest.raises(StorageCorruptError) as excinfo:
        exam_points.load(subject_id)

    assert excinfo.value.path == "exam_points.json"
    assert excinfo.value.record_index == 0
    assert str(p1_runtime) not in str(excinfo.value)


def test_historical_inferred_points_are_readable(p1_runtime: Path):
    subject_id = _subject()
    _path(subject_id).write_text(
        json.dumps(
            [
                {
                    "id": "legacy-1",
                    "subject_id": subject_id,
                    "content": "历史推断考点",
                    "level": "inferred",
                    "evidence": "老师提过一句",
                    "kp": "",
                    "term": "2025秋",
                    "source": "lecture_detection",
                    "anchor": "",
                    "confirmed": False,
                    "created_at": 1700000000,
                    "legacy_note": {"keep": ["me"]},
                }
            ]
        ),
        encoding="utf-8",
    )

    stored = exam_points.load(subject_id)[0]
    assert stored["level"] == "inferred"
    assert stored["legacy_note"] == {"keep": ["me"]}

    confirmed = exam_points.set_confirmed(subject_id, "legacy-1", True)
    assert confirmed["confirmed"] is True
    assert confirmed["legacy_note"] == {"keep": ["me"]}   # 未知字段保留
    assert confirmed["created_at"] == 1700000000          # 旧时间不重写


def test_list_points_filters_by_term_and_confirmation(p1_runtime: Path):
    subject_id = _subject()
    spring = _point(subject_id, "春季考点", term="2026春")
    autumn = _point(subject_id, "秋季考点", term="2025秋")
    exam_points.set_confirmed(subject_id, spring["id"], True)

    assert {p["id"] for p in exam_points.list_points(subject_id, term="2026春")} == {spring["id"]}
    assert {p["id"] for p in exam_points.list_points(subject_id, confirmed=True)} == {spring["id"]}
    assert {p["id"] for p in exam_points.list_points(subject_id, confirmed=False)} == {autumn["id"]}


# ---------------------------------------------------------------------------
# 整批提交
# ---------------------------------------------------------------------------
def test_add_many_writes_a_valid_batch_once_and_returns_stored_points(p1_runtime: Path):
    subject_id = _subject()
    batch = [
        {"content": "第一批", "level": "emphasis"},
        {"content": "第二批", "level": "explicit", "evidence": "原话"},
    ]

    stored = exam_points.add_many(subject_id, batch)

    assert [p["content"] for p in stored] == ["第一批", "第二批"]
    assert [p["source"] for p in stored] == ["lecture_detection", "lecture_detection"]
    assert [p["confirmed"] for p in stored] == [False, False]  # 不擅自全确认
    assert [p["level"] for p in stored] == ["emphasis", "explicit"]
    assert exam_points.load(subject_id) == stored


def test_add_many_writes_exactly_once(p1_runtime: Path, monkeypatch: pytest.MonkeyPatch):
    """合法批次只发生一次权威写（不是逐条保存）。"""
    subject_id = _subject()
    from deeptutor.subjects import json_store

    writes: list[list[dict]] = []
    real = json_store.atomic_write_json

    def counting(path, payload):
        writes.append(list(payload))
        return real(path, payload)

    # json_store 的原子写入口；一次写 = 一次调用
    monkeypatch.setattr(json_store, "atomic_write_json", counting)

    exam_points.add_many(subject_id, [{"content": f"点{i}"} for i in range(5)])

    # 只发生一次权威写，且这一次就带上整批 5 条（不是逐条保存）
    assert len(writes) == 1
    assert [p["content"] for p in writes[0]] == [f"点{i}" for i in range(5)]
    assert len(exam_points.load(subject_id)) == 5


@pytest.mark.parametrize(
    "bad_item",
    [
        "not-a-dict",
        42,
        None,
        ["nested"],
        {"content": 5},
        {"content": "ok", "level": 3},
        {"content": "ok", "evidence": ["not", "a", "string"]},
        {"content": "ok", "kp": {"a": 1}},
        {"content": "ok", "term": 2026},
        {"content": "ok", "anchor": 7},
    ],
)
def test_a_bad_batch_leaves_nothing_behind(p1_runtime: Path, bad_item):
    subject_id = _subject()
    before = _path(subject_id)
    assert not before.exists()

    batch = [{"content": "好的一条"}, {"content": "好的另一条"}, bad_item]
    with pytest.raises(exam_points.InvalidExamPointError) as excinfo:
        exam_points.add_many(subject_id, batch)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    # 前半项没有被留下：文件要么不存在，要么仍是原来的空数组
    assert exam_points.load(subject_id) == []


def test_a_bad_batch_does_not_disturb_existing_points(p1_runtime: Path):
    subject_id = _subject()
    existing = _point(subject_id, "已有的点")
    original = _path(subject_id).read_bytes()

    with pytest.raises(exam_points.InvalidExamPointError):
        exam_points.add_many(
            subject_id, [{"content": "新点"}, {"content": "新点2"}, {"content": 5}]
        )

    assert _path(subject_id).read_bytes() == original
    assert [p["id"] for p in exam_points.load(subject_id)] == [existing["id"]]


def test_a_non_list_batch_is_rejected(p1_runtime: Path):
    subject_id = _subject()

    with pytest.raises(exam_points.InvalidExamPointError):
        exam_points.add_many(subject_id, {"content": "not a list"})


# ---------------------------------------------------------------------------
# 并发：confirm 与 add
# ---------------------------------------------------------------------------
def test_concurrent_add_and_confirm_both_survive(p1_runtime: Path):
    subject_id = _subject()
    target = _point(subject_id, "待确认的点")
    workers = 10
    barrier = threading.Barrier(workers + 1)
    errors: list[BaseException] = []

    def adder(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            _point(subject_id, f"并发考点 {index}")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def confirmer() -> None:
        try:
            barrier.wait(timeout=15)
            exam_points.set_confirmed(subject_id, target["id"], True)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=adder, args=(i,)) for i in range(workers)]
    threads.append(threading.Thread(target=confirmer))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    points = exam_points.load(subject_id)
    assert len(points) == workers + 1                       # 一条都没丢
    by_id = {p["id"]: p for p in points}
    assert by_id[target["id"]]["confirmed"] is True        # 确认没有被覆盖
    assert len({p["id"] for p in points}) == workers + 1


def test_lost_update_bad_control(p1_runtime: Path):
    """受控坏对照：绕过锁的读改写会让 confirm 或 add 之一丢失。"""
    import contextlib

    from deeptutor.subjects.json_store import JsonTransaction

    subject_id = _subject()
    target = _point(subject_id, "先有的点")
    path = _path(subject_id)
    both_read = threading.Barrier(2)
    errors: list[BaseException] = []

    @contextlib.contextmanager
    def unlocked():
        yield JsonTransaction(store.subject_dir(subject_id))

    def confirmer() -> None:
        try:
            with unlocked() as tx:
                points = tx.read_list(path)
                for point in points:
                    if point["id"] == target["id"]:
                        point["confirmed"] = True
                snapshot = [dict(p) for p in points]
                both_read.wait(timeout=10)
                tx.write_list(path, snapshot)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def adder() -> None:
        try:
            with unlocked() as tx:
                points = tx.read_list(path)
                # 坏对照追加的记录本身必须是合法形状，否则后续步骤会因
                # 数据损坏而失败，掩盖真正要证明的"更新丢失"。
                points.append(
                    {"id": "new", "content": "坏对照新增", "level": "inferred",
                     "confirmed": False}
                )
                snapshot = [dict(p) for p in points]
                both_read.wait(timeout=10)
                tx.write_list(path, snapshot)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=confirmer), threading.Thread(target=adder)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    final = json.loads(path.read_text(encoding="utf-8"))
    confirmed = any(p.get("confirmed") for p in final)
    added = any(p["id"] == "new" for p in final)
    assert not (confirmed and added)  # 后写者覆盖前写者 —— 更新丢失

    # 对照：同样的两步走真锁顺序执行，两个改动都在
    exam_points.set_confirmed(subject_id, target["id"], True)
    _point(subject_id, "锁后新增")
    final = exam_points.load(subject_id)
    assert any(p["id"] == target["id"] and p["confirmed"] for p in final)
    assert any(p.get("content") == "锁后新增" for p in final)


def test_concurrent_confirm_and_delete_do_not_corrupt_the_file(p1_runtime: Path):
    subject_id = _subject()
    points = [_point(subject_id, f"点{i}") for i in range(6)]
    barrier = threading.Barrier(3)  # 三个 worker：confirm / delete / 别科写入
    errors: list[BaseException] = []

    def confirmer() -> None:
        try:
            barrier.wait(timeout=15)
            for point in points[:3]:
                exam_points.set_confirmed(subject_id, point["id"], True)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def deleter() -> None:
        try:
            barrier.wait(timeout=15)
            for point in points[3:]:
                exam_points.delete(subject_id, point["id"])
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def other_subject() -> None:
        try:
            barrier.wait(timeout=15)
            _point(_subject("别的科目"), "别科考点")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [
        threading.Thread(target=confirmer),
        threading.Thread(target=deleter),
        threading.Thread(target=other_subject),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    remaining = exam_points.load(subject_id)
    assert {p["id"] for p in remaining} == {p["id"] for p in points[:3]}
    assert all(p["confirmed"] is True for p in remaining)


# ---------------------------------------------------------------------------
# 删除与跨科隔离
# ---------------------------------------------------------------------------
def test_delete_touches_only_the_target_point_and_subject(p1_runtime: Path):
    subject_a = _subject("甲考点科目")
    subject_b = _subject("乙考点科目")
    keep = _point(subject_a, "保留的点")
    drop = _point(subject_a, "删除的点")
    other = _point(subject_b, "别科的点")

    assert exam_points.delete(subject_a, drop["id"]) is True

    assert [p["id"] for p in exam_points.load(subject_a)] == [keep["id"]]
    assert [p["id"] for p in exam_points.load(subject_b)] == [other["id"]]
    assert exam_points.delete(subject_a, drop["id"]) is False  # 已删除


def test_delete_and_confirm_report_a_missing_target_without_writing(p1_runtime: Path):
    subject_id = _subject()
    _point(subject_id)
    before = _path(subject_id).read_bytes()

    assert exam_points.delete(subject_id, "no-such-id") is False
    assert exam_points.set_confirmed(subject_id, "no-such-id", True) is None
    assert _path(subject_id).read_bytes() == before


def test_confirm_requires_a_real_bool(p1_runtime: Path):
    subject_id = _subject()
    point = _point(subject_id)
    before = _path(subject_id).read_bytes()

    for bad in ("true", "false", 1, 0, None):
        with pytest.raises(exam_points.InvalidExamPointError):
            exam_points.set_confirmed(subject_id, point["id"], bad)

    assert _path(subject_id).read_bytes() == before


def test_term_summary_only_reports_confirmed_points(p1_runtime: Path):
    subject_id = _subject()
    confirmed = _point(subject_id, "确认的重点", term="2026春")
    _point(subject_id, "未确认的点", term="2026春")
    exam_points.set_confirmed(subject_id, confirmed["id"], True)

    summary = exam_points.term_summary(subject_id, "2026春")
    assert "确认的重点" in summary
    assert "未确认的点" not in summary
    assert exam_points.term_summary(subject_id, "2099春") == ""


# ---------------------------------------------------------------------------
# R1/R3/R4（rework01）
# ---------------------------------------------------------------------------
def _write_raw(subject_id: str, text: str) -> Path:
    path = store.subject_dir(subject_id) / "exam_points.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_symlinked_collection_is_refused_before_reading(p1_runtime: Path):
    a = _subject("甲考点科")
    b = _subject("乙考点科")
    _point(a, "alpha")
    _point(b, "beta")
    link = _path(a)
    victim = _path(b)
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
            exam_points.load(a)

    assert reads == []
    assert victim.is_file()


@pytest.mark.parametrize(
    "point",
    [
        {"id": "x"},                                   # 缺 content
        {"id": "x", "content": 7},
        {"id": "x", "content": "c", "level": 3},
        {"id": "x", "content": "c", "evidence": ["q"]},
        {"id": "x", "content": "c", "kp": {"a": 1}},
        {"id": "x", "content": "c", "term": 2026},
        {"id": "x", "content": "c", "anchor": 7},
        {"id": "x", "content": "c", "confirmed": "yes"},
        {"id": "x", "content": "c", "created_at": True},
    ],
)
def test_corrupt_used_fields_are_rejected_and_not_overwritten(p1_runtime: Path, point):
    subject_id = _subject("坏考点科")
    path = _write_raw(subject_id, json.dumps([point]))
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError):
        exam_points.load(subject_id)
    with pytest.raises(StorageCorruptError):
        exam_points.set_confirmed(subject_id, "x", False)
    assert path.read_bytes() == before


def test_blank_content_is_invalid_input_and_never_persisted(p1_runtime: Path):
    subject_id = _subject("空考点科")
    path = _path(subject_id)
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(json_store.InvalidInputError) as excinfo:
        exam_points.add_point(subject_id, content="   ")
    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT

    # 整批里只要有一条空 content，整批都不写（不是"写了再从返回值过滤"）
    with pytest.raises(json_store.InvalidInputError):
        exam_points.add_many(
            subject_id, [{"content": "good"}, {"content": "   "}]
        )

    after = path.read_bytes() if path.exists() else None
    assert after == before
    assert exam_points.load(subject_id) == []


@pytest.mark.parametrize("bad", [7, None, [], {}])
def test_non_string_content_is_invalid_input(p1_runtime: Path, bad):
    subject_id = _subject("考点类型科")

    with pytest.raises(json_store.InvalidInputError):
        exam_points.add_point(subject_id, content=bad)
    with pytest.raises(json_store.InvalidInputError):
        exam_points.add_many(subject_id, [{"content": bad}])

    assert exam_points.load(subject_id) == []


def test_legacy_points_without_optional_fields_still_render(p1_runtime: Path):
    """缺 kp/level/confirmed 的旧记录在真实 summary 入口可用。"""
    subject_id = _subject("旧考点科")
    _write_raw(
        subject_id,
        json.dumps(
            [{"id": "legacy", "content": "旧考点", "legacy_note": {"keep": True},
              "created_at": 1.5}]
        ),
    )

    stored = exam_points.load(subject_id)[0]
    assert stored["legacy_note"] == {"keep": True}
    assert stored["created_at"] == 1.5

    assert exam_points.set_confirmed(subject_id, "legacy", True)["confirmed"] is True
    assert "旧考点" in exam_points.term_summary(subject_id)


@pytest.mark.parametrize("key", ["evidence", "level", "confirmed", "created_at"])
def test_review_exam_record_null_is_corrupt_not_missing(p1_runtime, key):
    sid = _subject()
    record = exam_points.add_point(sid, content="valid content")
    assert exam_points.load(sid)
    record[key] = None
    path = _path(sid)
    path.write_text(json.dumps([record]))
    before = path.read_bytes()
    with pytest.raises(StorageCorruptError):
        exam_points.load(sid)
    with pytest.raises(StorageCorruptError):
        exam_points.set_confirmed(sid, record["id"], True)
    assert path.read_bytes() == before
