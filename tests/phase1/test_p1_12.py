"""P1-12 行为测试：错题与 attempt 事务、掌握度一致（C01/C05）。

覆盖卡的必证场景，每个都有正例与只改一个目标字段/故障点的反例：

* N 个并发 attempt 全部保存（受锁的完整读改写，不是只保护最后一次 write）；
* ``False+True+True+True`` 得到 0.8 / mastered（三位舍入策略保留）；
* 错误的 ``correct`` 类型被拒绝（``"false"`` 不会变成 ``True``、``1`` 不冒充 ``True``），
  且旧文件字节不变；
* 坏文件不会变空后覆盖；归档/删除只动目标记录，不碰别的题、别的科目；
* 无 attempt 保持 0/untracked；未知历史字段与旧时间保留。

只使用 tmp 隔离根，不触碰真实数据。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from deeptutor.subjects import json_store, store, wrong_book
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)

#: 唯一虚构标记：任何对外投影都不得回显题目正文或宿主路径。
FAKE_QUESTION = "p1-12-FAKE-QUESTION-7c1f4a-DO-NOT-LEAK"


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_review_attempt_session_id_requires_string(p1_runtime, value):
    sid = _subject()
    entry = _entry(sid)
    path = _book_path(sid)
    before = path.read_bytes()
    with pytest.raises(SubjectOperationError) as error:
        wrong_book.record_attempt(sid, entry["id"], correct=True, session_id=value)
    assert error.value.code == ErrorCode.INVALID_INPUT
    assert path.read_bytes() == before


@pytest.mark.parametrize("key", ["kp", "analysis", "created_at", "archived", "subject_id", "status"])
def test_review_wrong_record_null_is_corrupt_not_missing(p1_runtime, key):
    sid = _subject()
    record = _entry(sid)
    assert wrong_book.load(sid)
    record[key] = None
    path = _book_path(sid)
    path.write_text(json.dumps([record]))
    before = path.read_bytes()
    with pytest.raises(StorageCorruptError):
        wrong_book.load(sid)
    with pytest.raises(StorageCorruptError):
        wrong_book.record_attempt(sid, record["id"], correct=True)
    assert path.read_bytes() == before


def _subject(name: str = "错题科目") -> str:
    return store.create_subject(name)["id"]


def _book_path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "wrong_book.json"


def _entry(subject_id: str, **overrides) -> dict:
    kwargs = {"question": "求 lim x->0 sin(x)/x"}
    kwargs.update(overrides)
    return wrong_book.add_entry(subject_id, **kwargs)


# ---------------------------------------------------------------------------
# 正例基准
# ---------------------------------------------------------------------------
def test_add_entry_starts_at_zero_untracked(p1_runtime: Path):
    subject_id = _subject()
    entry = _entry(subject_id)

    assert entry["mastery"] == 0.0
    assert entry["status"] == "untracked"
    assert entry["attempts"] == []
    assert entry["archived"] is False
    assert entry["created_at"] == entry["updated_at"]
    assert wrong_book.load(subject_id) == [entry]
    assert wrong_book.stats(subject_id)["total"] == 1


def test_missing_collection_is_empty_but_corrupt_is_an_error(p1_runtime: Path):
    subject_id = _subject()
    assert wrong_book.load(subject_id) == []

    _book_path(subject_id).write_text("[{", encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        wrong_book.load(subject_id)


def test_mastery_rounding_policy_is_preserved(p1_runtime: Path):
    """False+True+True+True -> 0.8/mastered（0.7999999999999 必须仍判 mastered）。"""
    subject_id = _subject()
    entry = _entry(subject_id)

    wrong_book.record_attempt(subject_id, entry["id"], correct=False)
    for _ in range(3):
        stored = wrong_book.record_attempt(subject_id, entry["id"], correct=True)

    assert stored is not None
    assert stored["mastery"] == 0.8
    assert stored["status"] == "mastered"
    assert [a["correct"] for a in stored["attempts"]] == [False, True, True, True]


def test_archived_entries_keep_their_attempts_and_times(p1_runtime: Path):
    subject_id = _subject()
    entry = _entry(subject_id)
    wrong_book.record_attempt(subject_id, entry["id"], correct=False)

    archived = wrong_book.archive(subject_id, entry["id"])
    assert archived is not None
    assert archived["archived"] is True
    assert len(archived["attempts"]) == 1
    assert archived["created_at"] == entry["created_at"]
    assert archived["mastery"] == 0.0
    assert [e["id"] for e in wrong_book.list_entries(subject_id, archived=False)] == []
    assert wrong_book.stats(subject_id)["total"] == 0


# ---------------------------------------------------------------------------
# 反例：错误的 correct 类型
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["false", "0", "", 0, 1, None, [], {}, 0.0])
def test_non_bool_correct_is_rejected_and_the_file_is_untouched(p1_runtime: Path, bad):
    subject_id = _subject()
    entry = _entry(subject_id)
    wrong_book.record_attempt(subject_id, entry["id"], correct=False)
    before = _book_path(subject_id).read_bytes()

    with pytest.raises(wrong_book.InvalidCorrectnessError) as excinfo:
        wrong_book.record_attempt(subject_id, entry["id"], correct=bad)

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.INVALID_INPUT
    assert projected.http_status == 400
    assert projected.retryable is False
    assert _book_path(subject_id).read_bytes() == before  # 旧字节不变
    assert len(wrong_book.load(subject_id)[0]["attempts"]) == 1


def test_string_false_does_not_become_true(p1_runtime: Path):
    """单独断言：``"false"`` 若被 bool() 强转就会变成"答对"。"""
    subject_id = _subject()
    entry = _entry(subject_id)

    with pytest.raises(wrong_book.InvalidCorrectnessError):
        wrong_book.record_attempt(subject_id, entry["id"], correct="false")

    stored = wrong_book.load(subject_id)[0]
    assert stored["attempts"] == []
    assert stored["mastery"] == 0.0
    assert stored["status"] == "untracked"


# ---------------------------------------------------------------------------
# 反例：坏文件
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "[{",
        '{"not": "an array"}',
        '[{"id": "a", "attempts": [{"correct": "false"}]}]',
        '[{"id": "a", "attempts": "nope"}]',
        '[{"attempts": []}]',
        '[{"id": "a", "archived": "yes"}]',
        '[{"id": "a", "mastery": NaN}]',
    ],
)
def test_a_damaged_file_is_not_replaced_by_an_empty_collection(p1_runtime: Path, text: str):
    subject_id = _subject()
    path = _book_path(subject_id)
    path.write_text(text, encoding="utf-8")

    for action in (
        lambda: wrong_book.load(subject_id),
        lambda: _entry(subject_id),
        lambda: wrong_book.record_attempt(subject_id, "a", correct=True),
        lambda: wrong_book.archive(subject_id, "a"),
        lambda: wrong_book.delete(subject_id, "a"),
    ):
        with pytest.raises(StorageCorruptError):
            action()
        assert path.read_text(encoding="utf-8") == text  # 坏文件始终原样保留


def test_corrupt_diagnostics_stay_relative(p1_runtime: Path):
    subject_id = _subject()
    path = _book_path(subject_id)
    path.write_text('[{"id": "a", "attempts": [{"correct": "false"}]}]', encoding="utf-8")

    with pytest.raises(StorageCorruptError) as excinfo:
        wrong_book.load(subject_id)

    error = excinfo.value
    assert error.path == "wrong_book.json"
    assert error.record_index == 0
    assert str(p1_runtime) not in str(error)
    assert "false" not in str(error)


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------
def test_concurrent_attempts_are_not_lost(p1_runtime: Path):
    subject_id = _subject()
    entry = _entry(subject_id)
    workers = 12
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            wrong_book.record_attempt(
                subject_id, entry["id"], correct=index % 2 == 0, session_id=f"s{index}"
            )
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    stored = wrong_book.load(subject_id)
    assert len(stored) == 1
    assert len(stored[0]["attempts"]) == workers
    assert len({a["session_id"] for a in stored[0]["attempts"]}) == workers
    assert stored[0]["mastery"] == wrong_book.mastery_score(
        [a["correct"] for a in stored[0]["attempts"]]
    )


def test_concurrent_entries_are_not_lost(p1_runtime: Path):
    subject_id = _subject()
    workers = 10
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            _entry(subject_id, question=f"题目 {index}")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    entries = wrong_book.load(subject_id)
    assert len(entries) == workers
    assert len({e["id"] for e in entries}) == workers


def test_lost_attempt_bad_control(p1_runtime: Path):
    """受控坏对照：绕过锁的读改写确实丢 attempt。"""
    import contextlib

    from deeptutor.subjects.json_store import JsonTransaction

    subject_id = _subject()
    entry = _entry(subject_id)
    path = _book_path(subject_id)
    rounds = 15
    both_read = threading.Barrier(2)
    errors: list[BaseException] = []

    @contextlib.contextmanager
    def unlocked():
        yield JsonTransaction(store.subject_dir(subject_id))

    def worker(index: int) -> None:
        try:
            for _ in range(rounds):
                with unlocked() as tx:
                    entries = tx.read_list(path)
                    entries[0].setdefault("attempts", []).append(
                        {"ts": 1, "correct": True, "session_id": f"u{index}"}
                    )
                    both_read.wait(timeout=10)
                    tx.write_list(path, entries)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    stored = json.loads(path.read_text(encoding="utf-8"))
    lost = len(stored[0]["attempts"])
    assert lost < 2 * rounds  # 丢 attempt

    # 对照：同样的工作量走真锁一遍，这一轮一条都不丢
    before = lost
    locked_entry_id = stored[0]["id"]
    for _ in range(2 * rounds):
        wrong_book.record_attempt(subject_id, locked_entry_id, correct=True)
    assert len(wrong_book.load(subject_id)[0]["attempts"]) == before + 2 * rounds


# ---------------------------------------------------------------------------
# 归档 / 删除只动目标记录
# ---------------------------------------------------------------------------
def test_archive_and_delete_leave_other_entries_and_subjects_alone(p1_runtime: Path):
    subject_a = _subject("甲科目")
    subject_b = _subject("乙科目")
    first = _entry(subject_a, question="第一题")
    second = _entry(subject_a, question="第二题")
    other_subject_entry = _entry(subject_b, question="别科题目")
    wrong_book.record_attempt(subject_a, second["id"], correct=True)

    assert wrong_book.archive(subject_a, first["id"]) is not None
    assert wrong_book.delete(subject_a, second["id"]) is True

    remaining_a = wrong_book.load(subject_a)
    assert [e["id"] for e in remaining_a] == [first["id"]]
    assert remaining_a[0]["archived"] is True

    assert [e["id"] for e in wrong_book.load(subject_b)] == [other_subject_entry["id"]]
    assert wrong_book.load(subject_b)[0]["question"] == "别科题目"


def test_archive_and_delete_report_a_missing_target_without_writing(p1_runtime: Path):
    subject_id = _subject()
    _entry(subject_id)
    before = _book_path(subject_id).read_bytes()

    assert wrong_book.archive(subject_id, "no-such-id") is None
    assert wrong_book.delete(subject_id, "no-such-id") is False
    assert wrong_book.record_attempt(subject_id, "no-such-id", correct=True) is None
    assert _book_path(subject_id).read_bytes() == before


# ---------------------------------------------------------------------------
# 未知字段 / 旧数据兼容
# ---------------------------------------------------------------------------
def test_unknown_historical_fields_and_legacy_times_survive(p1_runtime: Path):
    subject_id = _subject()
    path = _book_path(subject_id)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-1",
                    "subject_id": subject_id,
                    "question": FAKE_QUESTION,
                    "attempts": [{"ts": 1700000000.5, "correct": True, "session_id": ""}],
                    "mastery": 1.0,
                    "status": "mastered",
                    "archived": False,
                    "created_at": 1700000000.5,
                    "updated_at": 1700000000.5,
                    "legacy_note": {"keep": ["me"]},
                    "ai_tags": ["calc"],
                }
            ]
        ),
        encoding="utf-8",
    )

    stored = wrong_book.load(subject_id)[0]
    assert stored["legacy_note"] == {"keep": ["me"]}
    assert stored["ai_tags"] == ["calc"]
    assert stored["attempts"][0]["ts"] == 1700000000.5  # 旧时间不被重写

    updated = wrong_book.record_attempt(subject_id, "legacy-1", correct=True)
    assert updated is not None
    assert updated["legacy_note"] == {"keep": ["me"]}
    assert updated["ai_tags"] == ["calc"]
    assert updated["created_at"] == 1700000000.5
    assert updated["attempts"][0]["ts"] == 1700000000.5
    assert isinstance(updated["updated_at"], int)  # 新写时间统一整数秒


def test_reading_a_legacy_entry_without_attempts_is_zero_untracked(p1_runtime: Path):
    subject_id = _subject()
    _book_path(subject_id).write_text(
        json.dumps([{"id": "legacy-2", "question": "旧题"}]), encoding="utf-8"
    )

    stored = wrong_book.load(subject_id)[0]
    assert stored["id"] == "legacy-2"
    assert stored.get("attempts", []) == []
    assert stored.get("mastery", 0.0) == 0.0
    assert stored.get("status", "untracked") == "untracked"

    recomputed = wrong_book.record_attempt(subject_id, "legacy-2", correct=False)
    assert recomputed is not None
    assert len(recomputed["attempts"]) == 1
    assert recomputed["attempts"][0]["correct"] is False
    assert recomputed["mastery"] == 0.0
    assert recomputed["status"] == "missed"


def test_question_exact_match_policy_is_unchanged(p1_runtime: Path):
    subject_id = _subject()
    entry = _entry(subject_id, question="  精确 匹配  ")

    assert wrong_book.find_by_question(subject_id, "精确 匹配") is not None
    assert wrong_book.find_by_question(subject_id, "精确  匹配") is None


# ---------------------------------------------------------------------------
# R1/R3/R4（rework01）
# ---------------------------------------------------------------------------
def _write_raw(subject_id: str, text: str) -> Path:
    path = store.subject_dir(subject_id) / "wrong_book.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_symlinked_collection_is_refused_before_reading(p1_runtime: Path):
    a = _subject("甲错题科目")
    b = _subject("乙错题科目")
    _entry(a, question="alpha")
    _entry(b, question="beta")
    link = _book_path(a)
    victim = _book_path(b)
    link.unlink()
    link.symlink_to(victim)

    reads: list[str] = []
    real_open = os.open

    def spying_open(target: object, flags: int, *args: object, **kwargs: object) -> int:
        try:
            if Path(str(target)).resolve() == victim.resolve():
                reads.append(str(target))
        except OSError:  # pragma: no cover - defensive
            pass
        return real_open(target, flags, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", spying_open)
        with pytest.raises((StorageIOError, SubjectOperationError)):
            wrong_book.load(a)

    assert reads == [], "在拒绝之前读到了别的科目的错题数据"
    assert victim.is_file()


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "x"},                                  # 缺 question
        {"id": "x", "question": 7},
        {"id": "x", "question": ""},
        {"id": "x", "question": "q", "status": 7},
        {"id": "x", "question": "q", "mastery": "high"},
        {"id": "x", "question": "q", "created_at": True},
        {"id": "x", "question": "q", "subject_id": 5},
        {"id": "x", "question": "q", "attempts": [{"correct": 1}]},
    ],
)
def test_corrupt_used_fields_are_rejected_and_not_overwritten(p1_runtime: Path, entry):
    subject_id = _subject("坏字段科目")
    path = _write_raw(subject_id, json.dumps([entry]))
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError):
        wrong_book.load(subject_id)
    with pytest.raises(StorageCorruptError):
        wrong_book.archive(subject_id, "x")
    with pytest.raises(StorageCorruptError):
        wrong_book.record_attempt(subject_id, "x", correct=True)
    assert path.read_bytes() == before


def test_legacy_entry_without_attempts_reads_as_zero_untracked(p1_runtime: Path):
    """存了 mastery=1.0/status=mastered 但没有 attempt：读视图必须是 0/untracked。"""
    subject_id = _subject("无作答科目")
    path = _write_raw(
        subject_id,
        json.dumps(
            [{"id": "legacy", "question": "legacy", "mastery": 1.0,
              "status": "mastered", "created_at": 1.5}]
        ),
    )
    before = path.read_bytes()

    stored = wrong_book.load(subject_id)[0]

    assert stored["mastery"] == 0.0
    assert stored["status"] == "untracked"
    assert path.read_bytes() == before          # 读取不写回
    assert wrong_book.stats(subject_id)["by_status"]["untracked"] == 1


def test_a_legacy_entry_missing_optional_status_does_not_break_consumers(p1_runtime: Path):
    subject_id = _subject("缺状态科目")
    _write_raw(subject_id, json.dumps([{"id": "legacy", "question": "legacy question"}]))

    assert isinstance(wrong_book.context_summary(subject_id), str)
    assert wrong_book.list_entries(subject_id)[0]["status"] == "untracked"
    assert wrong_book.stats(subject_id)["by_status"]["untracked"] == 1
    assert wrong_book.find_by_question(subject_id, "legacy question") is not None


def test_a_present_attempt_history_drives_the_read_view(p1_runtime: Path):
    """有 attempt 时读视图按原公式/精度重算，而不是采信磁盘上的旧值。"""
    subject_id = _subject("重算科目")
    _write_raw(
        subject_id,
        json.dumps(
            [
                {"id": "e", "question": "q", "mastery": 0.1, "status": "repeated",
                 "attempts": [{"ts": 1, "correct": False}, {"ts": 2, "correct": True},
                              {"ts": 3, "correct": True}, {"ts": 4, "correct": True}]}
            ]
        ),
    )

    stored = wrong_book.load(subject_id)[0]

    assert stored["mastery"] == 0.8
    assert stored["status"] == "mastered"


@pytest.mark.parametrize("bad", ["", "   ", 7, None, [1]])
def test_blank_or_non_string_question_is_invalid_input(p1_runtime: Path, bad):
    subject_id = _subject("空题目科目")
    path = _book_path(subject_id)
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(json_store.InvalidInputError) as excinfo:
        wrong_book.add_entry(subject_id, question=bad)

    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT
    after = path.read_bytes() if path.exists() else None
    assert after == before


def test_non_string_optional_fields_are_invalid_input(p1_runtime: Path):
    subject_id = _subject("参数类型科目")

    for kwargs in ({"kp": 7}, {"answer": 7}, {"analysis": []}, {"question_type": 7},
                   {"source": 7}, {"error_type": 7}):
        with pytest.raises(json_store.InvalidInputError):
            wrong_book.add_entry(subject_id, question="合法题目", **kwargs)

    assert wrong_book.load(subject_id) == []


def test_unknown_fields_and_legacy_float_times_survive_the_read_view(p1_runtime: Path):
    subject_id = _subject("未知字段科目")
    path = _write_raw(
        subject_id,
        json.dumps(
            [
                {"id": "legacy", "question": "q", "created_at": 1.5, "updated_at": 2.5,
                 "ai_tags": ["calc"], "legacy_note": {"keep": True},
                 "attempts": [{"ts": 1.5, "correct": True, "session_id": ""}]}
            ]
        ),
    )
    before = path.read_bytes()

    stored = wrong_book.load(subject_id)[0]

    assert stored["ai_tags"] == ["calc"]
    assert stored["legacy_note"] == {"keep": True}
    assert stored["created_at"] == 1.5
    assert stored["attempts"][0]["ts"] == 1.5
    assert path.read_bytes() == before
