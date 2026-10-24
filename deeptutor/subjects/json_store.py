"""Strict JSON collection storage with reentrant, cross-process locking (C01).

This is the one storage adapter the subject layer uses. It owns three things:

1. **Strict reads.** A missing file means "empty collection" (``[]`` / the
   caller's default object). A file that exists but is corrupt — bad JSON, the
   wrong top-level type, non-finite numbers, an undecodable file — raises
   :class:`StorageCorruptError`. It never degrades to an empty collection,
   because "we could not read your data" and "you have no data" must not look
   the same to the caller: the first one gets written over.

2. **Atomic writes.** Writes go through :func:`deeptutor.services.file_io.atomic_write_json`
   (same-directory temp file, flush/fsync, atomic replace), so a failed write
   leaves the previous bytes in place.

3. **Locked read-modify-write.** :func:`json_transaction` takes a *directory*
   and yields a transaction. Everything done inside it — the read, the
   modification, and the write — happens while holding both a process-wide
   reentrant thread lock and an OS ``flock`` on that directory, so two threads
   or two processes cannot interleave a read-modify-write and lose an update.

Path confinement
----------------
Validation happens **before** anything is read, opened or created. A path is
only usable if the trusted root itself is not a symlink, no component below it
is a symlink, and the fully resolved path is still under that root — a
``subject_id``-shaped name is not enough, because ``<root>/a`` may itself point
at another subject, another user, or the admin tree. The leaf file is opened
with ``O_NOFOLLOW``, so a JSON file swapped for a symlink after the check is
refused rather than followed. A dangling symlink is an error, not a missing
file.

Locking model
-------------
One lock file per locked directory (``<dir>/.deeptutor.lock``), so the subject
registry and each subject are independent: work on subject A never blocks work
on subject B. The pair (reentrant ``threading.RLock``, ``flock``) is held by a
**cached** :class:`_PathLock` per normalized directory, so nesting reuses the
same lock instance and the same file descriptor: an inner transaction cannot
release the outer one's lock or open a second, conflicting ``flock``.

Reentrancy is tracked with a depth counter keyed by **thread and process**. A
lock inherited across ``fork`` is not a lock the child legitimately holds, so
``after_in_child`` drops the child's inherited descriptors and state and lets it
take a fresh, independent lock; the parent keeps its own.

Platforms without ``fcntl`` are reported as :class:`LockUnsupportedError`
rather than silently running unlocked — a lock that quietly does nothing is
worse than no lock at all, because callers would believe they were protected.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import errno
import json
import math
import os
from pathlib import Path
import stat
import threading
from typing import Any, Callable, Iterator

from deeptutor.services.file_io import atomic_write_json
from deeptutor.subjects.errors import (
    ERROR_SPECS,
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
)

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

#: Name of the per-directory lock file.
LOCK_FILE_NAME = ".deeptutor.lock"

_CORRUPT_MESSAGE = "科目数据文件已损坏，请先修复或移除该文件后重试。"
_IO_MESSAGE = "科目数据文件读写失败，请稍后重试。"
_ESCAPE_MESSAGE = "路径超出允许的科目数据目录，已拒绝访问。"
_SYMLINK_MESSAGE = "路径中存在符号链接，已拒绝访问。"
_UNSUPPORTED_MESSAGE = "当前平台缺少经过验证的文件锁支持，已拒绝并发写入。"


class LockUnsupportedError(StorageIOError):
    """Platform has no verified locking primitive (C01: never run unlocked)."""


class InvalidInputError(SubjectOperationError):
    """A caller-supplied value is unusable (C02 ``invalid_input``, 400).

    Deliberately distinct from :class:`~deeptutor.subjects.errors.StorageCorruptError`:
    a bad argument is the caller's problem and must not be reported as damage
    to the learner's data (nor the other way round).
    """

    def __init__(self, detail: str = "", *, cause: BaseException | None = None) -> None:
        spec = ERROR_SPECS[ErrorCode.INVALID_INPUT]
        self.detail = detail
        super().__init__(
            spec.code,
            spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )


class UpdateCallbackError(TypeError):
    """An update callback returned something that is not a collection/object."""


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
def _corrupt(source: Path | str, detail: str, *, index: int | None = None,
             cause: BaseException | None = None) -> StorageCorruptError:
    """Build a corrupt error whose server-side diagnostics stay relative.

    C02 forbids echoing host paths or record bodies to the client. The public
    projection is always the fixed message; ``path`` is only a file name and
    ``record_index`` only a position, so neither can leak a host path or a
    record's contents.
    """
    error = StorageCorruptError(
        f"{_CORRUPT_MESSAGE}（{detail}）", path=Path(source).name, cause=cause
    )
    error.record_index = index
    return error


def _io(source: Path | str, cause: BaseException | None = None) -> StorageIOError:
    return StorageIOError(_IO_MESSAGE, path=Path(source).name, cause=cause)


def corrupt_error(
    source: Path | str, detail: str, *, index: int | None = None
) -> StorageCorruptError:
    """Build a corrupt-collection error carrying only relative diagnostics.

    Consumers that validate record *shape* (beyond "is a JSON object") use this
    so every corruption path reports the same way: a fixed safe message to the
    client, plus a file name and record index kept server-side.
    """
    return _corrupt(source, detail, index=index)


def invalid_input(detail: str) -> InvalidInputError:
    """Build an ``invalid_input`` error for a bad caller-supplied value."""
    return InvalidInputError(detail)


def make_directory(path: Path, *, parents: bool = True, exist_ok: bool = True) -> None:
    """Create an already-confined directory, reporting OS failures as C02 IO."""
    try:
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)
    except OSError as exc:
        raise _io(path, exc) from exc


# ---------------------------------------------------------------------------
# Path confinement (no symlink escape)
# ---------------------------------------------------------------------------
def ensure_trusted_root(root: Path) -> Path:
    """The anchor itself must be reachable without a symlink.

    A symlinked root cannot be "resolved and trusted": whatever it points at
    today is not the scope the caller asked for, and re-resolving it on every
    call would silently adopt a new target.
    """
    root = Path(root)
    if root.is_symlink():
        raise StorageIOError(_SYMLINK_MESSAGE, path=root.name)
    return root


def confined(root: Path, path: Path) -> Path:
    """Return *path* after proving it stays inside *root* without symlinks.

    Checks the root, every component below it, and the final resolved location.
    Nothing is created or opened here — callers run this *before* touching the
    target, so a rejected path is never read, mkdir'd or locked.
    """
    root = ensure_trusted_root(root)
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise StorageIOError(_ESCAPE_MESSAGE, path=path.name) from None

    resolved_root = root.resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise StorageIOError(_SYMLINK_MESSAGE, path=path.name)

    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise StorageIOError(_ESCAPE_MESSAGE, path=path.name)
    return path


def safe_segment(name: object, *, what: str = "名称") -> str:
    """A single, non-empty path segment (no separators, no traversal)."""
    if not isinstance(name, str):
        raise invalid_input(f"{what}必须是字符串")
    if not name or name != name.strip():
        raise invalid_input(f"{what}不能为空或包含首尾空白")
    if name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise invalid_input(f"{what}不能包含路径分隔符")
    return name


# ---------------------------------------------------------------------------
# Strict decoding
# ---------------------------------------------------------------------------
def _strict_loads(text: str, *, source: Path) -> Any:
    """``json.loads`` with the standard's non-finite extensions turned off."""

    def _reject(name: str) -> Any:
        raise _corrupt(source, f"非标准数字常量 {name}")

    try:
        value = json.loads(text, parse_constant=_reject)
    except StorageCorruptError:
        raise
    except RecursionError as exc:
        raise _corrupt(source, "嵌套过深", cause=exc) from exc
    except ValueError as exc:
        # json.JSONDecodeError and the int-digit conversion limit both land here.
        raise _corrupt(source, "不是合法 JSON", cause=exc) from exc
    try:
        _reject_non_finite(value, source=source)
    except RecursionError as exc:  # pragma: no cover - extreme nesting
        raise _corrupt(source, "嵌套过深", cause=exc) from exc
    return value


def _reject_non_finite(value: Any, *, source: Path) -> None:
    """``1e400`` decodes to ``inf`` without raising, so check after decoding."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _corrupt(source, "包含非有限数值")
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite(item, source=source)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_finite(item, source=source)


def _read_text(path: Path) -> str | None:
    """Read ``path`` without following a symlink; ``None`` means "absent".

    ``O_NOFOLLOW`` makes the check atomic: a JSON file swapped for a symlink
    between the confinement check and the open is refused (``ELOOP``) instead of
    read. A *dangling* symlink therefore reports an error rather than looking
    like a missing file.
    """
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise StorageIOError(_SYMLINK_MESSAGE, path=path.name, cause=exc) from exc
        raise _io(path, exc) from exc

    chunks: list[bytes] = []
    failure: BaseException | None = None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _io(path)
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError as exc:
        failure = _io(path, exc)
        raise failure from exc
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if failure is None:
                raise _io(path, exc) from exc

    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _corrupt(path, "不是有效的 UTF-8 文本", cause=exc) from exc


# ---------------------------------------------------------------------------
# Public strict readers (C01)
# ---------------------------------------------------------------------------
def read_list(path: Path) -> list[dict]:
    """Read a top-level array collection.

    ``[]`` when the file does not exist. Raises :class:`StorageCorruptError` for
    a corrupt file, a non-array top level, a non-object record, or non-finite
    numbers, and :class:`StorageIOError` for a read/permission failure or a
    symlinked file — never an empty list, so a damaged file cannot be silently
    overwritten.
    """
    path = Path(path)
    text = _read_text(path)
    if text is None:
        return []
    value = _strict_loads(text, source=path)
    if not isinstance(value, list):
        raise _corrupt(path, "顶层不是数组")
    records: list[dict] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _corrupt(path, "记录不是对象", index=index)
        records.append(item)
    return records


def read_object(path: Path, *, default: dict) -> dict:
    """Read a top-level object document.

    A **fresh deep copy** of *default* when the file does not exist — never the
    caller's object itself, so a mutable default cannot leak between calls.
    An existing file is returned as stored, keeping unknown historical fields.
    """
    path = Path(path)
    text = _read_text(path)
    if text is None:
        return copy.deepcopy(default)
    value = _strict_loads(text, source=path)
    if not isinstance(value, dict):
        raise _corrupt(path, "顶层不是对象")
    return value


# ---------------------------------------------------------------------------
# Unlocked atomic writers
# ---------------------------------------------------------------------------
def _require_records(records: Any) -> list[dict]:
    if not isinstance(records, list):
        raise UpdateCallbackError("集合必须是数组")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise UpdateCallbackError(f"第 {index} 条记录不是对象")
    return records


def _commit(path: Path, payload: Any) -> None:
    """Serialize/replace with the target preserved and IO failures named."""
    try:
        atomic_write_json(path, payload)
    except OSError as exc:
        # The atomic write keeps the previous bytes; report a storage IO failure
        # instead of letting a bare OSError reach the caller.
        raise _io(path, exc) from exc


def atomic_write_list(path: Path, records: list[dict]) -> None:
    """Atomically write a collection **without** taking a lock.

    For callers that already hold the directory's transaction (or that are
    building a brand-new file nobody can race yet). Everyone else should use
    :meth:`JsonTransaction.write_list`, which also covers the read half.
    """
    path = Path(path)
    _require_records(records)
    _commit(path, list(records))


def atomic_write_object(path: Path, payload: dict) -> None:
    """Object counterpart of :func:`atomic_write_list`."""
    path = Path(path)
    if not isinstance(payload, dict):
        raise UpdateCallbackError("对象文档必须是对象")
    _commit(path, dict(payload))


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------
@dataclass
class _LockHandle:
    """Bookkeeping for one thread's hold on a path lock."""

    pid: int = 0
    depth: int = 0
    fd: int | None = None


class _PathLock:
    """A cached reentrant thread lock + ``flock`` pair for one directory.

    One instance lives in :data:`_LOCKS` per normalized directory, so callers
    never re-create the lock (which would let two "holders" exist at once) and
    never re-open the ``flock`` fd while already holding it (which on Linux
    would drop the first lock: ``flock`` on a *different* fd for the same file
    is a separate lock, and closing the original fd releases it).
    """

    def __init__(self, key: str, lock_path: Path) -> None:
        self.key = key
        self.lock_path = lock_path
        self._rlock = threading.RLock()
        self._local = threading.local()

    def _handle(self) -> _LockHandle:
        handle: _LockHandle | None = getattr(self._local, "handle", None)
        pid = os.getpid()
        if handle is None or handle.pid != pid:
            # A handle inherited across fork is not this process's hold.
            handle = _LockHandle(pid=pid)
            self._local.handle = handle
        return handle

    def acquire(self) -> None:
        self._rlock.acquire()
        handle = self._handle()
        try:
            if handle.depth == 0:
                self._open_and_flock(handle)
            handle.depth += 1
        except BaseException:
            self._rlock.release()
            raise

    def _open_and_flock(self, handle: _LockHandle) -> None:
        if fcntl is None:
            raise LockUnsupportedError(_UNSUPPORTED_MESSAGE, path=self.lock_path.name)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            # Never follow a symlink someone planted as the lock file.
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(str(self.lock_path), flags, 0o600)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.EMLINK):
                raise StorageIOError(
                    _SYMLINK_MESSAGE, path=self.lock_path.name, cause=exc
                ) from exc
            raise _io(self.lock_path, exc) from exc
        _register_fd(descriptor)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise _io(self.lock_path)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError as exc:
            _close_quietly(descriptor)
            raise _io(self.lock_path, exc) from exc
        except BaseException:
            _close_quietly(descriptor)
            raise
        handle.fd = descriptor

    def release(self) -> None:
        """Drop one level; the outermost level unlocks and closes the fd.

        The descriptor is closed even when ``LOCK_UN`` fails, and the failure is
        surfaced as a storage IO error — but never at the cost of leaking the
        fd. If the OS keeps refusing ``close``, nothing here pretends the
        descriptor is gone; we simply do not retry, so a recycled fd is never
        closed twice.
        """
        handle = self._handle()
        if handle.depth <= 0:  # pragma: no cover - defensive
            raise RuntimeError("release() without a matching acquire()")
        handle.depth -= 1
        if handle.depth > 0:
            self._rlock.release()
            return

        descriptor, handle.fd = handle.fd, None
        failure: BaseException | None = None
        try:
            if descriptor is not None:
                try:
                    if fcntl is not None:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                except BaseException as exc:
                    failure = exc
                finally:
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        if failure is None:
                            failure = exc
                    finally:
                        _discard_fd(descriptor)
        finally:
            self._rlock.release()
        if failure is not None:
            if isinstance(failure, OSError):
                raise _io(self.lock_path, failure) from failure
            raise failure

    # Test/diagnostic helpers -------------------------------------------------
    def held_depth(self) -> int:
        return self._handle().depth

    def fd_is_open(self) -> bool:
        return self._handle().fd is not None


_LOCKS: dict[str, _PathLock] = {}
_LOCKS_GUARD = threading.Lock()
#: Every lock descriptor this process has open, so ``fork`` can drop the child's
#: inherited copies — including ones held by threads the child no longer has.
_OPEN_FDS: set[int] = set()


def _register_fd(descriptor: int) -> None:
    with _LOCKS_GUARD:
        _OPEN_FDS.add(descriptor)


def _discard_fd(descriptor: int) -> None:
    with _LOCKS_GUARD:
        _OPEN_FDS.discard(descriptor)


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:  # pragma: no cover - already closed
        pass
    finally:
        _discard_fd(descriptor)


def _after_fork_in_child() -> None:  # pragma: no cover - runs in the child
    """Drop inherited lock state so the child takes its own locks.

    ``fork`` copies both the thread lock and every lock descriptor. Neither is a
    hold the child may use: the reentrancy depth would let it skip ``flock``
    entirely, and calling ``LOCK_UN`` on an inherited descriptor would unlock
    the *parent's* lock (``flock`` lives on the shared open file description).
    Closing the child's copy is safe — the parent's own descriptor keeps the
    lock held.
    """
    global _LOCKS_GUARD
    _LOCKS_GUARD = threading.Lock()
    for descriptor in list(_OPEN_FDS):
        _close_quietly(descriptor)
    _OPEN_FDS.clear()
    for lock in list(_LOCKS.values()):
        # The vanished parent thread may own the copied RLock; even a fork by
        # its owner carries a recursion count that strands other child threads.
        lock._rlock = threading.RLock()  # noqa: SLF001
        lock._local = threading.local()  # noqa: SLF001 - deliberate per-process reset


if hasattr(os, "register_at_fork"):  # pragma: no branch - POSIX
    os.register_at_fork(after_in_child=_after_fork_in_child)


def _lock_for(lock_dir: Path) -> _PathLock:
    """The cached lock for *lock_dir*, normalized so equivalent paths collide.

    The lock directory is validated **before** anything is created in it: a
    symlinked directory would otherwise get a fresh ``.deeptutor.lock`` in
    whatever it points at.
    """
    lock_dir = Path(lock_dir)
    ensure_trusted_root(lock_dir)
    if lock_dir.exists() and not lock_dir.is_dir():
        raise _io(lock_dir)
    make_directory(lock_dir)
    key = str(lock_dir.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _PathLock(key, Path(key) / LOCK_FILE_NAME)
            _LOCKS[key] = lock
        return lock


def _reset_locks_for_tests() -> None:
    """Drop cached locks (tests only; a held lock must never be dropped)."""
    with _LOCKS_GUARD:
        _LOCKS.clear()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class JsonTransaction:
    """A locked read-modify-write scope over one directory.

    Reentrant: entering the same directory's transaction again from the same
    thread reuses the same lock, and the inner exit does not release the outer
    hold. All paths used here must stay inside :attr:`lock_dir`.
    """

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = Path(lock_dir)
        self._lock: _PathLock | None = None
        self._resolved = ""

    def __enter__(self) -> "JsonTransaction":
        lock = _lock_for(self.lock_dir)
        lock.acquire()
        self._lock = lock
        # Remember the directory the lock was validated for, so later checks
        # cannot silently adopt a target the path was swapped to.
        self._resolved = lock.key
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        lock, self._lock = self._lock, None
        if lock is None:
            return False
        try:
            lock.release()
        except BaseException:
            if exc_type is None:
                raise
            # An error in the body is the meaningful one; a cleanup failure must
            # not replace it.
        return False

    # -- paths ----------------------------------------------------------------
    def _current_root(self) -> Path:
        root = Path(self.lock_dir)
        ensure_trusted_root(root)
        if self._resolved and str(root.resolve()) != self._resolved:
            raise StorageIOError(_ESCAPE_MESSAGE, path=root.name)
        return root

    def path(self, name: str) -> Path:
        """A confined path for *name* inside this transaction's directory."""
        root = self._current_root()
        return confined(root, root / safe_segment(name))

    # -- reads ----------------------------------------------------------------
    def read_list(self, path: Path) -> list[dict]:
        return read_list(confined(self._current_root(), Path(path)))

    def read_object(self, path: Path, *, default: dict) -> dict:
        return read_object(confined(self._current_root(), Path(path)), default=default)

    # -- writes ---------------------------------------------------------------
    def write_list(self, path: Path, records: list[dict]) -> None:
        path = confined(self._current_root(), Path(path))
        _require_records(records)
        _commit(path, list(records))

    def write_object(self, path: Path, payload: dict) -> None:
        path = confined(self._current_root(), Path(path))
        if not isinstance(payload, dict):
            raise UpdateCallbackError("对象文档必须是对象")
        _commit(path, dict(payload))

    # -- read-modify-write ----------------------------------------------------
    def update_list(
        self, path: Path, mutate: Callable[[list[dict]], list[dict] | None]
    ) -> list[dict]:
        """Read, mutate, write — all inside the hold.

        *mutate* may edit the list in place and return ``None``, or return a
        replacement list. The result is validated **before** anything is
        written: a callback returning the wrong shape fails without touching the
        existing collection.
        """
        records = self.read_list(path)
        replacement = mutate(records)
        if replacement is not None:
            if not isinstance(replacement, list):
                raise UpdateCallbackError("回调必须返回数组或 None")
            records = replacement
        _require_records(records)
        self.write_list(path, records)
        return records

    def update_object(
        self, path: Path, *, default: dict, mutate: Callable[[dict], dict | None]
    ) -> dict:
        """Object counterpart of :meth:`update_list`."""
        payload = self.read_object(path, default=default)
        replacement = mutate(payload)
        if replacement is not None:
            if not isinstance(replacement, dict):
                raise UpdateCallbackError("回调必须返回对象或 None")
            payload = replacement
        self.write_object(path, payload)
        return payload


@contextmanager
def json_transaction(lock_dir: Path) -> Iterator[JsonTransaction]:
    """Hold *lock_dir*'s process + OS lock for the duration of the block."""
    with JsonTransaction(Path(lock_dir)) as transaction:
        yield transaction


def transaction_depth(lock_dir: Path) -> int:
    """How many times the current thread holds *lock_dir* (diagnostics/tests)."""
    lock_dir = Path(lock_dir)
    try:
        key = str(lock_dir.resolve())
    except OSError:  # pragma: no cover - unreadable path
        return 0
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
    return 0 if lock is None else lock.held_depth()


def lock_is_held(lock_dir: Path) -> bool:
    """Whether the current thread holds *lock_dir* (diagnostics/tests)."""
    return transaction_depth(lock_dir) > 0


__all__ = (
    "InvalidInputError",
    "JsonTransaction",
    "LOCK_FILE_NAME",
    "LockUnsupportedError",
    "UpdateCallbackError",
    "atomic_write_list",
    "atomic_write_object",
    "confined",
    "corrupt_error",
    "ensure_trusted_root",
    "invalid_input",
    "json_transaction",
    "lock_is_held",
    "make_directory",
    "read_list",
    "read_object",
    "safe_segment",
    "transaction_depth",
)
