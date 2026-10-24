"""P1-10 行为测试：严格加载与可重入事务锁基础（C01/C02）。

覆盖卡的六个必证场景，每个都有正例与只改一个目标字段/故障点的反例：

* 缺失返回指定默认、坏 JSON/错顶层/拒读各自抛明确错误；
* 文件内 NaN/Infinity/溢出值作为 storage_corrupt 拒绝，不变成合法集合；
* 两个线程、两个子进程各追加 N 条，最终都是 2N 且 id 唯一（真实 flock）；
* 嵌套 transaction 不死锁、内层退出不释放外层、异常后能重新取得锁；
* 不同 subject 的锁互相独立、可并行；
* 不支持锁的平台明确报错，而不是静默无锁。

并发用 ready/GO 文件握手与 ``threading.Event`` 真正制造重叠，用有界等待判定、不用长
sleep；跨进程用子进程退出码判定。另有一个受控坏对照：把锁换成空实现后，同一次
"读-改-写"确实丢更新，证明 2N 断言是承重的而不是陪跑。
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from deeptutor.subjects import json_store
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    map_subject_exception,
)
from deeptutor.subjects.json_store import (
    LOCK_FILE_NAME,
    JsonTransaction,
    LockUnsupportedError,
    confined,
    json_transaction,
    read_list,
    read_object,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 唯一虚构标记：损坏诊断与错误投影都不得回显文件内容或宿主路径。
FAKE_BODY_MARKER = "p1-10-FAKE-BODY-a41f9c2e-DO-NOT-LEAK"


# Coordinator acceptance: exercise inherited Python locks as well as flock.
@pytest.mark.parametrize("owner", ["main", "thread"])
def test_review_fork_reinitializes_thread_locks(tmp_path: Path, owner: str):
    script = r'''
import os, signal, sys, threading, time
from pathlib import Path
from deeptutor.subjects.json_store import JsonTransaction, json_transaction
root = Path(sys.argv[1]); owner = sys.argv[2]
ready = threading.Event(); release = threading.Event()
tx = JsonTransaction(root)
def hold():
    with json_transaction(root):
        ready.set(); assert release.wait(10)
if owner == "main": tx.__enter__()
else:
    holder = threading.Thread(target=hold); holder.start(); assert ready.wait(5)
pid = os.fork()
if pid == 0:
    try:
        with json_transaction(root): (root / "child-entered").touch()
        done = threading.Event()
        def enter_again():
            with json_transaction(root): done.set()
        thread = threading.Thread(target=enter_again, daemon=True); thread.start()
        assert done.wait(2), "child lock retains inherited recursion count"
    except BaseException:
        import traceback; traceback.print_exc(); os._exit(2)
    os._exit(0)
try:
    time.sleep(.2)
    assert not (root / "child-entered").exists(), "child bypassed parent flock"
finally:
    if owner == "main": tx.__exit__(None, None, None)
    else: release.set(); holder.join(5); assert not holder.is_alive()
deadline = time.monotonic() + 4
while time.monotonic() < deadline:
    ended, status = os.waitpid(pid, os.WNOHANG)
    if ended: break
    time.sleep(.01)
else:
    os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
    raise AssertionError("child stranded on inherited thread lock")
assert os.waitstatus_to_exitcode(status) == 0
assert (root / "child-entered").exists()
'''
    env = {**os.environ, "DEEPTUTOR_HOME": str(tmp_path / "home")}
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "locked"), owner],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("reader", ["read_list", "read_object"])
def test_review_fifo_is_rejected_without_blocking(tmp_path: Path, reader: str):
    script = r'''
import os, sys
from pathlib import Path
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import StorageIOError
path = Path(sys.argv[1]); os.mkfifo(path)
try:
    if sys.argv[2] == "read_list": json_store.read_list(path)
    else: json_store.read_object(path, default={})
except StorageIOError: pass
else: raise AssertionError("FIFO accepted as a JSON file")
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "fifo.json"), reader],
        cwd=REPO_ROOT, env={**os.environ, "DEEPTUTOR_HOME": str(tmp_path / "home")},
        capture_output=True, text=True, timeout=3,
    )
    assert result.returncode == 0, result.stderr


def test_review_flock_acquisition_io_error_is_typed_and_closes_fd(tmp_path, monkeypatch):
    actual_open = os.open
    opened = []

    def remember(*args, **kwargs):
        fd = actual_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail(*args):
        raise OSError("fake acquisition failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", remember)
        patch.setattr(json_store.fcntl, "flock", fail)
        with pytest.raises(StorageIOError):
            with json_transaction(tmp_path):
                pass
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])
    with json_transaction(tmp_path):
        pass


@pytest.mark.parametrize("writer", ["list", "object", "tx-list", "tx-object", "lock"])
def test_review_mkdir_io_errors_are_typed(tmp_path, monkeypatch, writer):
    actual_mkdir = Path.mkdir
    target = tmp_path / "existing.json"
    target.write_text("[]" if writer.endswith("list") else "{}")
    before = target.read_bytes()

    def denied(path, *args, **kwargs):
        if path == tmp_path:
            raise PermissionError("fake mkdir denied")
        return actual_mkdir(path, *args, **kwargs)

    if writer.startswith("tx-"):
        with json_transaction(tmp_path) as tx:
            monkeypatch.setattr(Path, "mkdir", denied)
            with pytest.raises(StorageIOError):
                if writer == "tx-list":
                    tx.write_list(target, [])
                else:
                    tx.write_object(target, {})
    else:
        monkeypatch.setattr(Path, "mkdir", denied)
        with pytest.raises(StorageIOError):
            if writer == "list":
                json_store.atomic_write_list(target, [])
            elif writer == "object":
                json_store.atomic_write_object(target, {})
            else:
                with json_transaction(tmp_path):
                    pass
    assert target.read_bytes() == before


def test_review_unlock_interrupt_still_closes_fd(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        tx = JsonTransaction(tmp_path).__enter__()
        fd = tx._lock._handle().fd
        patch.setattr(json_store.fcntl, "flock", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            tx.__exit__(None, None, None)
        with pytest.raises(OSError):
            os.fstat(fd)
    with json_transaction(tmp_path):
        pass


def test_review_nonregular_lock_file_is_refused(tmp_path):
    os.mkfifo(tmp_path / LOCK_FILE_NAME)
    with pytest.raises(StorageIOError):
        with json_transaction(tmp_path):
            pass


@pytest.mark.parametrize("read_fails", [False, True])
def test_review_reader_close_io_does_not_hide_read_error(tmp_path, monkeypatch, read_fails):
    target = tmp_path / "collection.json"
    target.write_text("[]")
    actual_close = os.close

    def close_then_fail(fd):
        actual_close(fd)
        raise OSError("fake close failure")

    def fail_read(*args):
        raise OSError("fake read failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", close_then_fail)
        if read_fails:
            patch.setattr(os, "read", fail_read)
        with pytest.raises(StorageIOError) as error:
            read_list(target)
    assert str(error.value.cause) == ("fake read failure" if read_fails else "fake close failure")


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_raw(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ids(records: list[dict]) -> list[str]:
    return [r["id"] for r in records]


def _wait_for(predicate, timeout: float, interval: float = 0.01) -> bool:
    """有界轮询；返回是否在 timeout 内满足，不用固定长 sleep。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# 缺失默认 / 严格失败
# ---------------------------------------------------------------------------
def test_missing_file_returns_empty_list(tmp_path: Path):
    assert read_list(tmp_path / "absent.json") == []


def test_missing_object_returns_a_fresh_copy_of_the_default(tmp_path: Path):
    default = {"goals": "", "facts": []}

    first = read_object(tmp_path / "absent.json", default=default)
    first["facts"].append({"text": "mutated"})
    first["goals"] = "changed"

    second = read_object(tmp_path / "absent.json", default=default)
    assert second == {"goals": "", "facts": []}
    assert default == {"goals": "", "facts": []}  # 调用者的 default 未被污染


@pytest.mark.parametrize("text", ["{not json", '{"a": 1', "", "[1, 2"])
def test_corrupt_json_is_an_explicit_error(tmp_path: Path, text: str):
    path = tmp_path / "broken.json"
    _write_raw(path, text)

    with pytest.raises(StorageCorruptError) as excinfo:
        read_list(path)

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.STORAGE_CORRUPT
    assert projected.http_status == 500
    assert projected.retryable is False
    # 投影是固定安全消息：不回显文件内容、路径或宿主目录
    assert FAKE_BODY_MARKER not in projected.message
    assert str(tmp_path) not in projected.message


@pytest.mark.parametrize("payload", [{"a": 1}, "text", 7, None, True])
def test_wrong_top_level_type_for_a_collection_is_corrupt(tmp_path: Path, payload):
    path = tmp_path / "wrong.json"
    _write(path, payload)

    with pytest.raises(StorageCorruptError):
        read_list(path)


@pytest.mark.parametrize("payload", [[], ["x"], 3, None])
def test_wrong_top_level_type_for_an_object_is_corrupt(tmp_path: Path, payload):
    path = tmp_path / "wrong.json"
    _write(path, payload)

    with pytest.raises(StorageCorruptError):
        read_object(path, default={"goals": ""})


def test_non_object_record_is_corrupt_and_reports_its_index(tmp_path: Path):
    path = tmp_path / "collection.json"
    _write(path, [{"id": "ok"}, "not-a-record"])

    with pytest.raises(StorageCorruptError) as excinfo:
        read_list(path)

    error = excinfo.value
    assert error.record_index == 1
    # 诊断只保留相对文件名与序号，不回显记录内容或宿主路径
    assert error.path == "collection.json"
    assert "not-a-record" not in str(error)
    assert str(tmp_path) not in str(error)


def test_unreadable_path_raises_storage_io(tmp_path: Path):
    """把目录当文件读：确定性拒读，映射为 storage_io/retryable。"""
    target = tmp_path / "a_directory.json"
    target.mkdir()

    with pytest.raises(StorageIOError) as excinfo:
        read_list(target)

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.STORAGE_IO
    assert projected.retryable is True


def test_permission_denied_is_storage_io_not_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """权限拒绝必须映射为 storage_io（可重试），而不是 corrupt。

    直接注入 ``PermissionError``：不依赖进程以谁的身份运行，也不需要 skip。
    """
    path = tmp_path / "denied.json"
    _write(path, [{"id": "x"}])

    real_open = os.open

    def deny(target: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(target) == str(path):
            raise PermissionError(13, "Permission denied")
        return real_open(target, flags, *args, **kwargs)

    # 读取现在走 os.open(O_NOFOLLOW)，所以在这一层注入权限失败
    monkeypatch.setattr(os, "open", deny)

    with pytest.raises(StorageIOError) as excinfo:
        read_list(path)

    assert not isinstance(excinfo.value, StorageCorruptError)
    assert map_subject_exception(excinfo.value).code is ErrorCode.STORAGE_IO


def test_a_real_permission_denial_is_storage_io_when_the_os_enforces_it(tmp_path: Path):
    """真实 chmod 000 的补充证据；root 下内核不拦截时如实跳过断言而不是假装通过。"""
    path = tmp_path / "denied.json"
    _write(path, [{"id": "x"}])
    path.chmod(0o000)
    try:
        try:
            path.read_bytes()
        except PermissionError:
            enforced = True
        else:
            enforced = False  # root：内核不拦，本用例不适用
        if enforced:
            with pytest.raises(StorageIOError) as excinfo:
                read_list(path)
            assert not isinstance(excinfo.value, StorageCorruptError)
    finally:
        path.chmod(0o600)


def test_non_utf8_bytes_are_corrupt(tmp_path: Path):
    path = tmp_path / "binary.json"
    path.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(StorageCorruptError):
        read_list(path)


# ---------------------------------------------------------------------------
# 非有限数
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        '[{"mastery": NaN}]',
        '[{"mastery": Infinity}]',
        '[{"mastery": -Infinity}]',
        '[{"nested": {"mastery": NaN}}]',
        '[{"mastery": 1e400}]',
        '[{"mastery": -1e400}]',
        '[{"items": [{"deep": [NaN]}]}]',
    ],
)
def test_non_finite_numbers_in_a_stored_collection_are_corrupt(tmp_path: Path, text: str):
    path = tmp_path / "collection.json"
    _write_raw(path, text)

    with pytest.raises(StorageCorruptError):
        read_list(path)


@pytest.mark.parametrize("text", ['{"value": NaN}', '{"facts": [{"value": Infinity}]}'])
def test_non_finite_numbers_in_a_stored_object_are_corrupt(tmp_path: Path, text: str):
    path = tmp_path / "profile.json"
    _write_raw(path, text)

    with pytest.raises(StorageCorruptError):
        read_object(path, default={})


def test_finite_floats_stay_readable(tmp_path: Path):
    path = tmp_path / "collection.json"
    _write(path, [{"mastery": 0.8, "big": 1e300}])

    assert read_list(path) == [{"mastery": 0.8, "big": 1e300}]


def test_a_corrupt_file_is_never_replaced_by_a_later_write(tmp_path: Path):
    """损坏数据不被覆盖：读取失败必须先于任何写入。"""
    path = tmp_path / "collection.json"
    original = '[{"id": "' + FAKE_BODY_MARKER + '", "broken":'
    _write_raw(path, original)

    with pytest.raises(StorageCorruptError):
        with json_transaction(tmp_path) as tx:
            tx.update_list(path, lambda records: records + [{"id": "new"}])

    assert path.read_text(encoding="utf-8") == original


def test_a_failed_write_keeps_the_previous_bytes(tmp_path: Path):
    path = tmp_path / "collection.json"
    _write(path, [{"id": "original"}])
    original = path.read_bytes()

    with json_transaction(tmp_path) as tx:
        with pytest.raises(ValueError):
            tx.write_list(path, [{"mastery": float("nan")}])

    assert path.read_bytes() == original


# ---------------------------------------------------------------------------
# 锁：同一目录、重入、嵌套、异常
# ---------------------------------------------------------------------------
def test_same_directory_spelling_maps_to_one_lock(tmp_path: Path):
    (tmp_path / "sub").mkdir(exist_ok=True)

    direct = json_store._lock_for(tmp_path)
    dot = json_store._lock_for(tmp_path / ".")
    nested = json_store._lock_for(tmp_path / "sub" / "..")

    assert direct is dot is nested


def test_the_lock_instance_is_cached_and_the_fd_is_not_reopened_while_nested(tmp_path: Path):
    with json_transaction(tmp_path) as outer:
        lock = outer._lock
        assert lock.fd_is_open() is True
        fd = lock._handle().fd
        with json_transaction(tmp_path) as inner:
            assert inner._lock is lock          # 同一个锁实例
            assert lock._handle().fd == fd      # 嵌套没有重新打开 flock FD
            assert lock.held_depth() == 2
            assert json_store.lock_is_held(tmp_path) is True
        assert lock.held_depth() == 1           # 内层退出不释放外层
        assert lock.fd_is_open() is True
    assert lock.fd_is_open() is False


def test_nested_transactions_do_not_deadlock_and_only_the_outer_releases(tmp_path: Path):
    completed = []

    with json_transaction(tmp_path):
        with json_transaction(tmp_path):
            with json_transaction(tmp_path):
                completed.append("inner")
        completed.append("middle")
    completed.append("outer")

    assert completed == ["inner", "middle", "outer"]
    assert json_store.lock_is_held(tmp_path) is False


def test_an_exception_releases_the_lock_and_it_can_be_taken_again(tmp_path: Path):
    with pytest.raises(RuntimeError, match="boom"):
        with json_transaction(tmp_path):
            raise RuntimeError("boom")

    assert json_store.lock_is_held(tmp_path) is False

    with json_transaction(tmp_path):
        pass
    assert json_store.lock_is_held(tmp_path) is False


def test_a_second_thread_cannot_enter_while_the_first_holds_the_lock(tmp_path: Path):
    """确定性互斥证明：B 在 A 持有期间被挡住，A 释放后立刻进入。"""
    holding = threading.Event()
    may_release = threading.Event()
    entered = threading.Event()

    def holder() -> None:
        with json_transaction(tmp_path):
            holding.set()
            assert may_release.wait(timeout=10)

    def waiter() -> None:
        assert holding.wait(timeout=10)
        with json_transaction(tmp_path):
            entered.set()

    first = threading.Thread(target=holder)
    second = threading.Thread(target=waiter)
    first.start()
    second.start()
    try:
        assert holding.wait(timeout=10)
        # 反例：A 还没释放，B 不能进入
        assert entered.wait(timeout=0.3) is False
        may_release.set()
        assert entered.wait(timeout=10) is True
    finally:
        may_release.set()
        first.join(timeout=10)
        second.join(timeout=10)

    assert not first.is_alive() and not second.is_alive()


def test_an_inner_transaction_does_not_unblock_an_outer_waiting_thread(tmp_path: Path):
    """外层持有时，内层进出不能让第三个调用者拿到锁。"""
    holding = threading.Event()
    inner_done = threading.Event()
    may_release = threading.Event()
    entered = threading.Event()

    def holder() -> None:
        with json_transaction(tmp_path):
            with json_transaction(tmp_path):
                pass
            holding.set()
            inner_done.set()
            assert may_release.wait(timeout=10)

    def waiter() -> None:
        assert inner_done.wait(timeout=10)
        with json_transaction(tmp_path):
            entered.set()

    first = threading.Thread(target=holder)
    second = threading.Thread(target=waiter)
    first.start()
    second.start()
    try:
        assert inner_done.wait(timeout=10)
        assert holding.is_set()
        assert entered.wait(timeout=0.3) is False
        may_release.set()
        assert entered.wait(timeout=10) is True
    finally:
        may_release.set()
        first.join(timeout=10)
        second.join(timeout=10)


def test_different_directories_do_not_block_each_other(tmp_path: Path):
    a = tmp_path / "subject-a"
    b = tmp_path / "subject-b"
    a.mkdir()
    b.mkdir()

    with json_transaction(a):
        assert json_store.lock_is_held(b) is False
        with json_transaction(b):
            assert json_store.lock_is_held(b) is True
        assert json_store.lock_is_held(a) is True


def test_two_threads_work_on_different_subjects_concurrently(tmp_path: Path):
    """不同 subject 真并行：A 持锁时 B 仍能完成一整次读改写。"""
    a = tmp_path / "subject-a"
    b = tmp_path / "subject-b"
    a.mkdir()
    b.mkdir()
    a_holding = threading.Event()
    may_release = threading.Event()
    b_done = threading.Event()

    def hold_a() -> None:
        with json_transaction(a) as tx:
            tx.write_list(a / "x.json", [{"id": "a"}])
            a_holding.set()
            assert may_release.wait(timeout=10)

    def use_b() -> None:
        assert a_holding.wait(timeout=10)
        with json_transaction(b) as tx:
            tx.write_list(b / "x.json", [{"id": "b"}])
            assert tx.read_list(b / "x.json") == [{"id": "b"}]
        b_done.set()

    first = threading.Thread(target=hold_a)
    second = threading.Thread(target=use_b)
    first.start()
    second.start()
    try:
        assert a_holding.wait(timeout=10)
        assert b_done.wait(timeout=10) is True  # 没有被 A 阻塞
    finally:
        may_release.set()
        first.join(timeout=10)
        second.join(timeout=10)


def test_unsupported_platform_reports_an_error_instead_of_running_unlocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(json_store, "fcntl", None)
    json_store._reset_locks_for_tests()

    with pytest.raises(LockUnsupportedError) as excinfo:
        with json_transaction(tmp_path):
            pass

    assert "锁" in str(excinfo.value)
    assert json_store.lock_is_held(tmp_path) is False  # 没有留下半持有状态


# ---------------------------------------------------------------------------
# 路径约束
# ---------------------------------------------------------------------------
def test_confined_rejects_a_path_outside_the_root(tmp_path: Path):
    root = tmp_path / "subject"
    root.mkdir()

    with pytest.raises(StorageIOError):
        confined(root, tmp_path / "elsewhere.json")


def test_confined_rejects_a_symlinked_component(tmp_path: Path):
    root = tmp_path / "subject"
    outside = tmp_path / "admin"
    root.mkdir()
    outside.mkdir()
    (root / "link.json").symlink_to(outside / "index.json")

    with pytest.raises(StorageIOError):
        confined(root, root / "link.json")


def test_transaction_refuses_a_path_that_escapes_through_a_symlink(tmp_path: Path):
    root = tmp_path / "subject"
    outside = tmp_path / "admin"
    root.mkdir()
    outside.mkdir()
    victim = outside / "index.json"
    _write(victim, [{"id": "admin-record"}])
    (root / "index.json").symlink_to(victim)

    with json_transaction(root) as tx:
        with pytest.raises(StorageIOError):
            tx.read_list(root / "index.json")
        with pytest.raises(StorageIOError):
            tx.write_list(root / "index.json", [{"id": "attacker"}])

    assert json.loads(victim.read_text(encoding="utf-8")) == [{"id": "admin-record"}]


def test_a_symlinked_lock_file_is_refused(tmp_path: Path):
    json_store._reset_locks_for_tests()
    decoy = tmp_path / "decoy.lock"
    decoy.write_text("", encoding="utf-8")
    (tmp_path / LOCK_FILE_NAME).symlink_to(decoy)

    try:
        with pytest.raises(StorageIOError):
            with json_transaction(tmp_path):
                pass
    finally:
        json_store._reset_locks_for_tests()


def test_transaction_writes_stay_inside_the_lock_directory(tmp_path: Path):
    root = tmp_path / "subject"
    root.mkdir()

    with json_transaction(root) as tx:
        tx.write_list(tx.path("ok.json"), [{"id": "1"}])
        assert (root / "ok.json").is_file()
        with pytest.raises(StorageIOError):
            tx.write_list(tmp_path / "escape.json", [{"id": "2"}])

    assert not (tmp_path / "escape.json").exists()


# ---------------------------------------------------------------------------
# 线程并发：受锁的完整读改写
# ---------------------------------------------------------------------------
def _append_rounds(target: Path, *, prefix: str, rounds: int) -> None:
    path = target / "collection.json"
    for index in range(rounds):
        with json_transaction(target) as tx:
            records = tx.read_list(path)
            records.append({"id": f"{prefix}-{index}"})
            tx.write_list(path, records)


def test_two_threads_appending_do_not_lose_updates(tmp_path: Path):
    rounds = 25
    started = threading.Barrier(2)  # 两个线程真正重叠后才开始
    errors: list[BaseException] = []

    def worker(prefix: str) -> None:
        try:
            started.wait(timeout=10)
            _append_rounds(tmp_path, prefix=prefix, rounds=rounds)
        except BaseException as exc:  # pragma: no cover - 失败时上报
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    records = read_list(tmp_path / "collection.json")
    assert len(records) == 2 * rounds
    assert len(set(_ids(records))) == 2 * rounds


@contextmanager
def _unlocked_transaction(lock_dir: Path):
    """坏对照专用：形状与 json_transaction 相同，但不取任何锁。"""
    yield JsonTransaction(lock_dir)


def test_lost_update_bad_control(tmp_path: Path):
    """受控坏对照：把锁换成空实现，同样的读改写确实丢更新。

    这条证明上面的 2N 断言是承重的——锁若不起作用，结果必然小于 2N。
    """
    rounds = 25
    path = tmp_path / "collection.json"
    _write(path, [])
    both_read = threading.Barrier(2)  # 强制两个线程读到同一份旧状态后再写
    errors: list[BaseException] = []

    def worker(prefix: str) -> None:
        try:
            for index in range(rounds):
                with _unlocked_transaction(tmp_path) as tx:
                    records = tx.read_list(path)
                    records.append({"id": f"{prefix}-{index}"})
                    both_read.wait(timeout=10)
                    tx.write_list(path, records)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"u{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    final = read_list(path)
    assert len(final) < 2 * rounds  # 丢更新


# ---------------------------------------------------------------------------
# 跨进程：真实 flock
# ---------------------------------------------------------------------------
_CHILD_SCRIPT = r'''
import os, sys, time
from pathlib import Path

repo, target, mode, tag, start_flag, home = sys.argv[1:7]
sys.path.insert(0, repo)
os.chdir(repo)
os.environ["DEEPTUTOR_HOME"] = home

from deeptutor.subjects.json_store import json_transaction

target = Path(target)
path = target / "collection.json"
(target / ("ready-" + tag)).write_text("ready", encoding="utf-8")

deadline = time.monotonic() + 30
while not Path(start_flag).exists():
    if time.monotonic() > deadline:
        raise SystemExit("timed out waiting for the start flag")
    time.sleep(0.01)

if mode == "enter":
    with json_transaction(target):
        (target / ("acquired-" + tag)).write_text("yes", encoding="utf-8")
    raise SystemExit(0)

for index in range(int(mode)):
    with json_transaction(target) as tx:
        records = tx.read_list(path)
        records.append({"id": "proc-" + tag + "-" + str(index)})
        tx.write_list(path, records)
raise SystemExit(0)
'''


def _spawn_children(
    work: Path, specs: list[tuple[str, str]]
) -> tuple[list[subprocess.Popen], Path, Path]:
    """启动子进程并等它们全部 ready；**不**放行（由调用方决定何时放行）。"""
    target = work / "shared"
    target.mkdir(parents=True, exist_ok=True)
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    start_flag = target / "GO"

    env = dict(os.environ)
    env["DEEPTUTOR_HOME"] = str(home)

    procs: list[subprocess.Popen] = []
    for index, (mode, tag) in enumerate(specs):
        unique = f"{tag}-{index}"
        procs.append(
            subprocess.Popen(
                [sys.executable, "-c", _CHILD_SCRIPT, str(REPO_ROOT), str(target),
                 mode, unique, str(start_flag), str(home)],
                cwd=str(REPO_ROOT), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        )

    ready = _wait_for(
        lambda: len(list(target.glob("ready-*"))) >= len(specs), timeout=30
    )
    if not ready:  # pragma: no cover - 子进程未能启动
        for proc in procs:
            proc.kill()
        raise AssertionError("children never signalled ready")
    return procs, target, start_flag


def _finish(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
            raise
    assert [p.returncode for p in procs] == [0] * len(procs), [
        (p.returncode, p.stderr.read()[-800:]) for p in procs
    ]


def test_two_processes_appending_do_not_lose_updates(tmp_path: Path):
    rounds = 20
    procs, target, start = _spawn_children(
        tmp_path, [(str(rounds), "p0"), (str(rounds), "p1")]
    )
    start.write_text("go", encoding="utf-8")
    _finish(procs)

    records = read_list(target / "collection.json")
    assert len(records) == 2 * rounds
    assert len(set(_ids(records))) == 2 * rounds


def test_flock_actually_blocks_a_second_process(tmp_path: Path):
    """父进程持锁期间，子进程的 flock 必须阻塞到父进程释放为止。"""
    work = tmp_path / "work"
    work.mkdir()

    with json_transaction(work / "shared"):
        procs, target, start = _spawn_children(work, [("enter", "blocked")])
        acquired = target / "acquired-blocked-0"
        try:
            start.write_text("go", encoding="utf-8")
            # 反例：父进程仍持锁，子进程的 flock 必须进不来
            assert _wait_for(acquired.exists, timeout=0.6) is False
        finally:
            pass
    # 释放后子进程立刻能取得锁
    assert _wait_for(acquired.exists, timeout=30) is True
    _finish(procs)


# ---------------------------------------------------------------------------
# R1（rework01）：路径防护必须在读取/建目录/开锁之前
# ---------------------------------------------------------------------------
def test_a_dangling_symlink_is_an_error_not_a_missing_file(tmp_path: Path):
    """坏链不等于"文件不存在"：必须报错，不能返回空集合。"""
    path = tmp_path / "collection.json"
    path.symlink_to(tmp_path / "does-not-exist.json")

    with pytest.raises(StorageIOError):
        read_list(path)
    with pytest.raises(StorageIOError):
        read_object(path, default={})


def test_a_symlinked_leaf_is_refused_by_the_low_level_readers(tmp_path: Path):
    victim = tmp_path / "victim.json"
    _write(victim, [{"id": "victim"}])
    link = tmp_path / "link.json"
    link.symlink_to(victim)

    with pytest.raises(StorageIOError):
        read_list(link)
    with pytest.raises(StorageIOError):
        read_object(link, default={})


def test_a_symlinked_root_is_refused(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link-root"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(StorageIOError):
        confined(link, link / "x.json")
    with pytest.raises(StorageIOError):
        with json_transaction(link):
            pass
    assert not (real / LOCK_FILE_NAME).exists()  # 没有在外部目录建锁


def test_transaction_does_not_trust_a_symlinked_lock_root(tmp_path: Path):
    victim = tmp_path / "outside-lock"
    victim.mkdir()
    link = tmp_path / "lock-link"
    link.symlink_to(victim, target_is_directory=True)

    with pytest.raises(StorageIOError):
        with json_transaction(link):
            pass

    assert list(victim.iterdir()) == []  # 外部目录既没有锁也没有数据


def test_a_swapped_root_is_detected_before_the_next_use(tmp_path: Path):
    """事务根规范化后必须保持同一路径，不能中途采用新目标。"""
    real = tmp_path / "subject"
    real.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    with json_transaction(real) as tx:
        tx.write_list(tx.path("a.json"), [{"id": "1"}])
        real.rename(tmp_path / "moved")
        real.symlink_to(other, target_is_directory=True)
        with pytest.raises(StorageIOError):
            tx.write_list(real / "b.json", [{"id": "2"}])

    assert list(other.iterdir()) == []


# ---------------------------------------------------------------------------
# R5（rework01）：写入形状、错误分类与资源释放
# ---------------------------------------------------------------------------
def test_write_list_rejects_non_object_records(tmp_path: Path):
    path = tmp_path / "rows.json"
    _write(path, [{"id": "ok"}])
    before = path.read_bytes()

    with json_transaction(tmp_path) as tx:
        with pytest.raises(json_store.UpdateCallbackError):
            tx.write_list(path, ["not-an-object"])
        with pytest.raises(json_store.UpdateCallbackError):
            tx.write_list(path, {"not": "a list"})

    assert path.read_bytes() == before


def test_write_object_rejects_a_non_object_payload(tmp_path: Path):
    path = tmp_path / "doc.json"
    _write(path, {"id": "ok"})
    before = path.read_bytes()

    with json_transaction(tmp_path) as tx:
        with pytest.raises(json_store.UpdateCallbackError):
            tx.write_object(path, ["nope"])

    assert path.read_bytes() == before


def test_bad_update_callback_result_cannot_corrupt_an_existing_collection(tmp_path: Path):
    path = tmp_path / "rows.json"
    _write(path, [{"id": "ok"}])
    before = path.read_bytes()

    with json_transaction(tmp_path) as tx:
        with pytest.raises(json_store.UpdateCallbackError):
            tx.update_list(path, lambda rows: {"oops": 1})
        with pytest.raises(json_store.UpdateCallbackError):
            tx.update_list(path, lambda rows: rows + ["not-a-record"])

    assert path.read_bytes() == before


def test_bad_update_callback_result_cannot_corrupt_an_existing_object(tmp_path: Path):
    path = tmp_path / "doc.json"
    _write(path, {"goals": "keep"})
    before = path.read_bytes()

    with json_transaction(tmp_path) as tx:
        with pytest.raises(json_store.UpdateCallbackError):
            tx.update_object(path, default={}, mutate=lambda payload: ["nope"])

    assert path.read_bytes() == before


def test_write_os_error_is_a_storage_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """底层 atomic_write_json 的 OSError 不能原样逃逸。"""
    with json_transaction(tmp_path) as tx:
        def explode(*_args: object, **_kwargs: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(json_store, "atomic_write_json", explode)

        with pytest.raises(StorageIOError) as excinfo:
            tx.write_list(tmp_path / "rows.json", [])

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.STORAGE_IO
    assert projected.retryable is True


def test_unlock_failure_still_closes_the_descriptor(tmp_path: Path):
    """LOCK_UN 失败也必须关掉 fd，并且错误照常上报。"""
    original_flock = json_store.fcntl.flock
    descriptor: int | None = None

    def failing_unlock(fd: int, operation: int) -> None:
        if operation == json_store.fcntl.LOCK_UN:
            raise OSError(5, "controlled unlock failure")
        return original_flock(fd, operation)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(json_store.fcntl, "flock", failing_unlock)
        with pytest.raises(StorageIOError):
            with json_transaction(tmp_path) as tx:
                descriptor = tx._lock._handle().fd

    assert descriptor is not None
    with pytest.raises(OSError):
        os.fstat(descriptor)  # 已关闭，不再是有效 fd
    # 而且没有把锁留在半持有状态
    assert json_store.lock_is_held(tmp_path) is False
    with json_transaction(tmp_path):
        pass


def test_a_body_error_is_not_replaced_by_a_cleanup_error(tmp_path: Path):
    """body 的异常才是有效错误；清理失败不能把它顶掉。"""
    original_flock = json_store.fcntl.flock

    def failing_unlock(fd: int, operation: int) -> None:
        if operation == json_store.fcntl.LOCK_UN:
            raise OSError(5, "controlled unlock failure")
        return original_flock(fd, operation)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(json_store.fcntl, "flock", failing_unlock)
        with pytest.raises(RuntimeError, match="body failure"):
            with json_transaction(tmp_path):
                raise RuntimeError("body failure")

    assert json_store.lock_is_held(tmp_path) is False


_FORK_SCRIPT = r'''
import os, signal, sys, time
from pathlib import Path

repo, work, marker = sys.argv[1:4]
sys.path.insert(0, repo)
os.chdir(repo)

from deeptutor.subjects.json_store import json_transaction

work = Path(work)
marker = Path(marker)
result = {"acquired_while_parent_held": None, "child_exit": None}

with json_transaction(work):
    child = os.fork()
    if child == 0:
        with json_transaction(work):
            marker.write_text("acquired", encoding="utf-8")
        os._exit(0)

    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.01)
    result["acquired_while_parent_held"] = marker.exists()

deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    pid, status = os.waitpid(child, os.WNOHANG)
    if pid:
        result["child_exit"] = os.waitstatus_to_exitcode(status)
        break
    time.sleep(0.01)
else:
    os.kill(child, signal.SIGKILL)
    os.waitpid(child, 0)
    result["child_exit"] = "stranded"

import json as _json
print(_json.dumps(result))
'''


def test_a_forked_child_cannot_inherit_the_parents_lock(tmp_path: Path):
    """fork 继承的重入计数/FD 不是子进程的合法持有。

    在独立 tmp 子进程里真的 fork：父进程持锁期间子进程必须进不来，父进程释放后
    子进程才能进入，且父进程的持锁状态不受影响。
    """
    work = tmp_path / "work"
    work.mkdir()
    marker = tmp_path / "child-acquired"
    env = dict(os.environ)
    env["DEEPTUTOR_HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)

    proc = subprocess.run(
        [sys.executable, "-c", _FORK_SCRIPT, str(REPO_ROOT), str(work), str(marker)],
        capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT), env=env,
    )

    assert proc.returncode == 0, proc.stderr[-1500:]
    payload = json.loads([ln for ln in proc.stdout.splitlines() if ln.strip()][-1])
    assert payload["acquired_while_parent_held"] is False, "fork 子进程在父进程持锁期间进入了"
    assert payload["child_exit"] == 0
    assert marker.is_file(), "父进程释放后子进程仍未能进入"
