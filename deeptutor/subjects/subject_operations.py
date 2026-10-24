"""Cross-thread/cross-process activity leases for one registered subject (P1-40).

Every long-running subject operation that can mutate learner data or publish an
artifact takes a *shared* activity lease: uploads (from acceptance through the
index worker), report runs (from ``create_report_run`` through publication or
failure), review-pack generation and its off-loop render/copy, and exports.
Deleting a subject takes an *exclusive* lease.  Export takes the same exclusive
lease while it snapshots and publishes its ZIP.  Consequently a delete/export
conflicts with every active writer, and a delete conflicts with an export, for
the whole lifetime of the operation -- not just while a process-local flag is
set.

The lock is an OS ``flock`` on ``<workspace>/.subject-operations/<sid>.lock``.
It deliberately lives **outside** the subject tree: deleting the subject must
not delete (and recreate) the lock that proves the delete itself is exclusive.
``flock`` is held on an open file description, so two threads in one process
using separate ``open`` calls conflict just like two processes do.  There is no
blocking wait on the event loop: every acquisition is non-blocking and reports
the existing C02 ``kb_busy`` (409, retryable) on conflict.

This module additionally keeps a tiny process-local diagnostic registry, but it
is never the source of truth for mutual exclusion; a platform without a working
``fcntl`` fails closed instead of silently running unlocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import errno
import os
from pathlib import Path
import stat
import threading
import time

from deeptutor.subjects import json_store, store
from deeptutor.subjects.errors import ErrorCode, StorageIOError, subject_error

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

SHARED = "shared"
EXCLUSIVE = "exclusive"
MODES = frozenset({SHARED, EXCLUSIVE})
LOCK_DIR_NAME = ".subject-operations"

_DIAGNOSTIC_LOCK = threading.Lock()
_ACTIVE: dict[str, list["ActivityLease"]] = {}


class ActivityLeaseError(StorageIOError):
    """The OS lease could not be established for a non-busy reason."""


@dataclass
class ActivityLease:
    """One held OS lease.  ``release`` is idempotent and safe from any thread."""

    key: str
    subject_id: str
    mode: str
    kind: str
    path: Path
    fd: int
    _released: bool = field(default=False, repr=False)
    _detached: bool = field(default=False, repr=False)
    _guard: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _owner_pid: int = field(default_factory=os.getpid, repr=False)

    @property
    def active(self) -> bool:
        if self._owner_pid != os.getpid():
            return False
        with self._guard:
            return not self._released

    @property
    def detached(self) -> bool:
        with self._guard:
            return self._detached

    def detach(self) -> "ActivityLease":
        """Hand ownership to a long-lived holder (e.g. a queued worker).

        The lease stays active; only its new owner releases it.  The route that
        handed it off must not release it in a ``finally`` block.
        """
        with self._guard:
            self._detached = True
        return self

    def release(self) -> None:
        """Drop the flock and close the descriptor exactly once.

        The descriptor is closed from whichever thread finishes last.  That is
        what lets a cancelled request hand ownership to the still-running
        render/copy thread instead of pretending the subject became idle.
        """
        inherited = self._owner_pid != os.getpid()
        if inherited:
            # A fork inherited the open file description and possibly a held
            # Python mutex. Close the child's descriptor without LOCK_UN:
            # unlocking that shared description would unlock the parent too.
            self._guard = threading.Lock()
        with self._guard:
            if self._released:
                return
            self._released = True
            fd = self.fd
        try:
            if not inherited and fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:  # pragma: no cover - closing releases it anyway
                    pass
        finally:
            try:
                os.close(fd)
            finally:
                with _DIAGNOSTIC_LOCK:
                    holders = _ACTIVE.get(self.key)
                    if holders is not None:
                        _ACTIVE[self.key] = [
                            lease for lease in holders if lease is not self
                        ]
                        if not _ACTIVE[self.key]:
                            _ACTIVE.pop(self.key, None)

    def __enter__(self) -> "ActivityLease":
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self.detached:
            self.release()

    def __del__(self) -> None:  # pragma: no cover - best-effort leak guard
        try:
            if not self.detached:
                self.release()
        except Exception:
            pass


def _lock_root() -> Path:
    """The private lease directory for the **current** user, outside subjects."""
    workspace = store.current_subject_paths().get_workspace_dir()
    json_store.ensure_trusted_root(workspace)
    root = json_store.confined(workspace, workspace / LOCK_DIR_NAME)
    if root.is_symlink():
        raise ActivityLeaseError("活动租约目录是符号链接，已拒绝访问。")
    json_store.make_directory(root, parents=False)
    try:
        os.chmod(root, 0o700)
    except OSError:  # pragma: no cover - exotic filesystem
        pass
    return json_store.confined(workspace, root)


def lease_key(subject_id: str) -> str:
    """Strict workspace + registered-subject identity (never just a caller id)."""
    if not isinstance(subject_id, str) or not store.is_valid_subject_id(subject_id):
        raise store.InvalidSubjectIdError(subject_id)
    if store.get_subject(subject_id) is None:
        raise store.SubjectNotFoundError(subject_id)
    return f"{store.current_subject_paths().workspace_root}|{subject_id}"


def acquire_activity(
    subject_id: str, *, mode: str = SHARED, kind: str = "activity"
) -> ActivityLease:
    """Try to acquire one shared/exclusive subject lease without blocking.

    Raises the historical C02 ``kb_busy`` (409, retryable) when another
    thread/process holds a conflicting lease.  Missing OS locking support is a
    hard storage error, never a silently unlocked success.
    """
    if mode not in MODES:
        raise ValueError(f"unknown activity mode: {mode!r}")
    if not isinstance(kind, str) or not kind:
        kind = "activity"
    key = lease_key(subject_id)
    if fcntl is None:
        raise ActivityLeaseError("当前平台缺少经过验证的文件锁支持，已拒绝并发写入。")
    root = _lock_root()
    path = json_store.confined(root, root / f"{subject_id}.lock")
    if path.is_symlink():
        raise ActivityLeaseError("活动租约文件是符号链接，已拒绝访问。")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ActivityLeaseError("无法建立活动租约。", cause=exc) from exc

    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ActivityLeaseError("活动租约文件不是常规文件，已拒绝访问。")
        operation = fcntl.LOCK_EX if mode == EXCLUSIVE else fcntl.LOCK_SH
        fcntl.flock(fd, operation | fcntl.LOCK_NB)
        # A deletion may have completed between the first identity read and
        # lock acquisition. Never authorize a late writer to resurrect its tree.
        if store.get_subject(subject_id) is None:
            raise store.SubjectNotFoundError(subject_id)
    except BlockingIOError as exc:
        os.close(fd)
        raise subject_error(ErrorCode.KB_BUSY, cause=exc) from exc
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            raise subject_error(ErrorCode.KB_BUSY, cause=exc) from exc
        raise ActivityLeaseError("无法建立活动租约。", cause=exc) from exc
    except BaseException:
        os.close(fd)
        raise

    lease = ActivityLease(
        key=key, subject_id=subject_id, mode=mode, kind=kind, path=path, fd=fd
    )
    with _DIAGNOSTIC_LOCK:
        _ACTIVE.setdefault(key, []).append(lease)
    return lease


def require_activity(lease: ActivityLease, subject_id: str, *, mode: str | None = None) -> None:
    """Validate a passed server lease without releasing somebody else's lease."""
    key = lease_key(subject_id)
    with _DIAGNOSTIC_LOCK:
        owned = any(item is lease for item in _ACTIVE.get(key, ()))
    if not owned or not lease.active or lease.key != key or (mode and lease.mode != mode):
        raise json_store.invalid_input("活动租约不属于当前用户和科目")


def _after_fork_child() -> None:
    global _DIAGNOSTIC_LOCK, _ACTIVE
    leases = [lease for group in _ACTIVE.values() for lease in group]
    _DIAGNOSTIC_LOCK = threading.Lock()
    _ACTIVE = {}
    for lease in leases:
        lease.release()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


def active_lease_kinds(subject_id: str) -> tuple[str, ...]:
    """Diagnostic only: kinds this *process* currently holds (not a mutex)."""
    if not isinstance(subject_id, str):
        return ()
    try:
        key = lease_key(subject_id)
    except Exception:
        return ()
    with _DIAGNOSTIC_LOCK:
        return tuple(sorted(lease.kind for lease in _ACTIVE.get(key, ())))


def reset_for_tests() -> None:  # pragma: no cover - explicit test helper
    """Release diagnostic leases retained by a failed test (never used in prod)."""
    with _DIAGNOSTIC_LOCK:
        leases = [lease for holders in _ACTIVE.values() for lease in holders]
        _ACTIVE.clear()
    for lease in leases:
        lease.release()


# ---------------------------------------------------------------------------
# Cross-process audio writer latch (ASR-R1)
# ---------------------------------------------------------------------------
AUDIO_LOCK_SUFFIX = ".audio.lock"


@dataclass
class AudioWriterLatch:
    """A short, subject-wide exclusive latch for publishing audio + transcript.

    It is intentionally a *separate* file from the subject activity lease: all
    normal activity is shared, while the old synchronous audio endpoint and the
    new ASR job both take this exclusive latch only around the publication
    step.  It is never held across provider/media work.
    """

    subject_id: str
    path: Path
    fd: int
    owner_pid: int = field(default_factory=os.getpid, repr=False)
    _released: bool = field(default=False, repr=False)
    _guard: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def active(self) -> bool:
        return self.owner_pid == os.getpid() and not self._released

    def release(self) -> None:
        inherited = self.owner_pid != os.getpid()
        if inherited:
            self._guard = threading.Lock()
        with self._guard:
            if self._released:
                return
            self._released = True
        try:
            if not inherited and fcntl is not None:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                except OSError:  # pragma: no cover - closing releases it anyway
                    pass
        finally:
            try:
                os.close(self.fd)
            except OSError:  # pragma: no cover
                pass

    def __enter__(self) -> "AudioWriterLatch":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def acquire_audio_writer(subject_id: str, *, timeout: float = 5.0) -> AudioWriterLatch:
    """Acquire the per-subject audio publication latch, or raise ``kb_busy``.

    Acquisition is a bounded non-blocking flock loop.  It never runs on the
    FastAPI event loop directly; callers use ``asyncio.to_thread`` when the
    wait could be non-zero.  A missing OS lock implementation fails closed.
    """
    if fcntl is None:
        raise ActivityLeaseError("当前平台缺少经过验证的文件锁支持，已拒绝并发写入。")
    if not isinstance(subject_id, str) or not store.is_valid_subject_id(subject_id):
        raise store.InvalidSubjectIdError(subject_id)
    if store.get_subject(subject_id) is None:
        raise store.SubjectNotFoundError(subject_id)
    workspace = store.current_subject_paths().get_workspace_dir()
    json_store.ensure_trusted_root(workspace)
    root = json_store.confined(workspace, workspace / LOCK_DIR_NAME)
    if root.is_symlink():
        raise ActivityLeaseError("活动租约目录是符号链接，已拒绝访问。")
    json_store.make_directory(root, parents=False)
    path = json_store.confined(root, root / f"{subject_id}{AUDIO_LOCK_SUFFIX}")
    if path.is_symlink():
        raise ActivityLeaseError("音频写入门闩是符号链接，已拒绝访问。")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ActivityLeaseError("无法建立音频写入门闩。", cause=exc) from exc
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ActivityLeaseError("音频写入门闩不是常规文件，已拒绝访问。")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return AudioWriterLatch(subject_id=subject_id, path=path, fd=fd)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise subject_error(ErrorCode.KB_BUSY) from None
            time.sleep(0.05)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise subject_error(ErrorCode.KB_BUSY, cause=exc) from exc
            raise ActivityLeaseError("无法建立音频写入门闩。", cause=exc) from exc
        except BaseException:
            os.close(fd)
            raise


__all__ = [
    "ActivityLease",
    "ActivityLeaseError",
    "AudioWriterLatch",
    "EXCLUSIVE",
    "LOCK_DIR_NAME",
    "SHARED",
    "acquire_activity",
    "acquire_audio_writer",
    "active_lease_kinds",
    "lease_key",
    "reset_for_tests",
]
