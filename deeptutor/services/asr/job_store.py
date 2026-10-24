"""Private persistent ASR job storage (CONTRACTS D4/D5).

Each job lives below ``<subject>/.asr_jobs/<job_id>/``.  Reads never create the
root, a job directory or a lock file; only a write path may do so.  JSON writes
are atomic and short transactions are used for manifest mutations.  Network and
ffmpeg waits never happen while the JSON lock is held.

The worker claim is a real ``flock`` on ``.worker.lock``.  It is distinct from
the subject-wide activity lease (shared with the rest of the app) and from the
short audio writer latch.  A forked child closes its inherited descriptor
without ``LOCK_UN`` so it cannot unlock the parent's claim.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass, field
import hashlib
import logging
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from deeptutor.services.asr.contracts import (
    CHUNK_FAILED,
    CHUNK_PENDING,
    CHUNK_SUCCESS,
    JOB_SCHEMA_VERSION,
    MAX_BATCH_BYTES,
    MAX_FILE_BYTES,
    MAX_FILES,
    STATUSES,
    JobView,
    progress_defaults,
    project_job,
    utc_now,
    valid_job_id,
)
from deeptutor.subjects import json_store, store
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode, asr_error, subject_error

logger = logging.getLogger(__name__)

JOBS_DIR_NAME = ".asr_jobs"
MANIFEST_NAME = "manifest.json"
RESULT_NAME = "result.json"
PUBLISH_NAME = "publish_plan.json"
INPUT_DIR = "input"
CHUNKS_DIR = "chunks"
TEXT_DIR = "text"
WORKER_LOCK = ".worker.lock"
LOCK_FILE = json_store.LOCK_FILE_NAME


class JobNotFound(Exception):
    """Internal 404 marker; callers project ``asr_job_not_found``."""


def jobs_root(subject_id: str, *, create: bool = False) -> Path:
    directory = store.subject_dir(subject_id)
    root = json_store.confined(directory, directory / JOBS_DIR_NAME)
    if create:
        json_store.make_directory(root)
        try:
            os.chmod(root, 0o700)
        except OSError:  # pragma: no cover - best effort on exotic filesystems
            pass
    return root


def job_dir(subject_id: str, job_id: str, *, create: bool = False) -> Path:
    if not valid_job_id(job_id):
        raise subject_error(ErrorCode.INVALID_INPUT)
    root = jobs_root(subject_id, create=create)
    path = json_store.confined(root, root / job_id)
    if create:
        json_store.make_directory(path, parents=False, exist_ok=False)
        for name in (INPUT_DIR, CHUNKS_DIR, TEXT_DIR, "normalized"):
            json_store.make_directory(json_store.confined(path, path / name))
        try:
            os.chmod(path, 0o700)
        except OSError:  # pragma: no cover
            pass
    return path


def manifest_path(subject_id: str, job_id: str) -> Path:
    directory = job_dir(subject_id, job_id, create=False)
    return json_store.confined(directory, directory / MANIFEST_NAME)


def result_path(subject_id: str, job_id: str) -> Path:
    directory = job_dir(subject_id, job_id, create=False)
    return json_store.confined(directory, directory / RESULT_NAME)


def publish_plan_path(subject_id: str, job_id: str) -> Path:
    directory = job_dir(subject_id, job_id, create=False)
    return json_store.confined(directory, directory / PUBLISH_NAME)


def read_manifest(subject_id: str, job_id: str) -> dict[str, Any]:
    path = manifest_path(subject_id, job_id)
    if not path.is_file() or path.is_symlink():
        raise JobNotFound(job_id)
    payload = json_store.read_object(path, default={})
    if not isinstance(payload, dict) or payload.get("job_id") != job_id:
        raise JobNotFound(job_id)
    return payload


def list_manifests(subject_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Read-only list; a missing jobs root returns ``[]`` without creating it."""
    root = jobs_root(subject_id, create=False)
    if not root.is_dir() or root.is_symlink():
        return []
    rows: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir() or child.is_symlink() or not valid_job_id(child.name):
            continue
        path = json_store.confined(root, child / MANIFEST_NAME)
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json_store.read_object(path, default={})
        except Exception:  # noqa: BLE001 - one corrupt job must not hide the list
            logger.warning("ASR job manifest unreadable; skipped from list")
            continue
        if isinstance(payload, dict) and payload.get("job_id") == child.name:
            rows.append(payload)
    rows.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("job_id"))), reverse=True)
    return rows[: max(0, int(limit))]


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != JOB_SCHEMA_VERSION:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    if not valid_job_id(manifest.get("job_id")):
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    if manifest.get("status") not in STATUSES:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)


def write_manifest(subject_id: str, job_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    _validate_manifest(manifest)
    path = manifest_path(subject_id, job_id)
    json_store.atomic_write_object(path, manifest)
    return manifest


def update_manifest(
    subject_id: str,
    job_id: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Short locked read-modify-write, incrementing revision exactly once."""
    directory = job_dir(subject_id, job_id, create=False)
    with json_store.json_transaction(directory) as tx:
        path = tx.path(MANIFEST_NAME)
        current = tx.read_object(path, default={})
        if not isinstance(current, dict) or current.get("job_id") != job_id:
            raise JobNotFound(job_id)
        replacement = mutate(copy.deepcopy(current))
        payload = replacement if isinstance(replacement, dict) else current
        _validate_manifest(payload)
        payload["revision"] = int(current.get("revision") or 1) + 1
        payload["updated_at"] = utc_now()
        tx.write_object(path, payload)
        return payload


@contextmanager
def _open_regular(path: Path):
    fd = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        handle = os.fdopen(fd, "rb")
        fd = None
        with handle:
            yield handle
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    finally:
        if fd is not None:
            os.close(fd)


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with _open_regular(path) as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _replace_into_job(source: Path, target: Path) -> None:
    """Move a private staged file into the job tree without following links."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise subject_error(ErrorCode.STORAGE_IO)
    os.replace(source, target)


def create_job(
    subject_id: str,
    *,
    job_id: str,
    request_id: str,
    signature: str,
    language: str,
    config_fingerprint: str,
    files: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Create exactly one job directory, or return the matching existing one.

    ``files`` items must carry ``staged_path``, ``name``, ``size_bytes``,
    ``sha256`` and ``content_type``.  The caller has already validated names
    and limits.  The jobs-root lock serializes concurrent same-request posts.
    """
    if not valid_job_id(job_id):
        raise subject_error(ErrorCode.INVALID_INPUT)
    if not files or len(files) > MAX_FILES:
        raise asr_error(AsrErrorCode.ASR_INPUT_TOO_LARGE)
    total = sum(int(item.get("size_bytes") or 0) for item in files)
    if total > MAX_BATCH_BYTES or any(int(item.get("size_bytes") or 0) > MAX_FILE_BYTES for item in files):
        raise asr_error(AsrErrorCode.ASR_INPUT_TOO_LARGE)
    jobs_root(subject_id, create=True)
    with json_store.json_transaction(jobs_root(subject_id, create=False)):
        existing_dir = job_dir(subject_id, job_id, create=False)
        if existing_dir.exists():
            existing = read_manifest(subject_id, job_id)
            if existing.get("request_signature") == signature:
                return existing, False
            raise asr_error(AsrErrorCode.ASR_REQUEST_CONFLICT)
        directory = job_dir(subject_id, job_id, create=True)
        try:
            manifest_files: list[dict[str, Any]] = []
            for index, item in enumerate(files):
                staged = Path(str(item["staged_path"]))
                suffix = Path(str(item.get("name") or "")).suffix.lower()
                leaf = f"f{index:04d}{suffix}" if suffix else f"f{index:04d}.bin"
                target = json_store.confined(directory, directory / INPUT_DIR / leaf)
                _replace_into_job(staged, target)
                manifest_files.append(
                    {
                        "file_index": index,
                        "name": str(item["name"]),
                        "size_bytes": int(item["size_bytes"]),
                        "sha256": str(item["sha256"]),
                        "content_type": str(item.get("content_type") or "application/octet-stream"),
                        "input_path": f"{INPUT_DIR}/{leaf}",
                        "duration_ms": 0,
                        "input_sample_rate": 0,
                        "channels": 0,
                        "total_samples": 0,
                    }
                )
            now = utc_now()
            manifest = {
                "schema_version": JOB_SCHEMA_VERSION,
                "job_id": job_id,
                "subject_id": subject_id,
                "request_id": request_id,
                "request_signature": signature,
                "language": language,
                "config_fingerprint": config_fingerprint,
                "status": "queued",
                "phase": "queued",
                "revision": 1,
                "created_at": now,
                "updated_at": now,
                "attempts": 0,
                "worker": None,
                "cancel_requested": False,
                "publish_started": False,
                "publish_plan": None,
                "files": manifest_files,
                "chunks": [],
                "progress": progress_defaults(len(manifest_files)),
                "error": None,
                "result": None,
            }
            write_manifest(subject_id, job_id, manifest)
            return manifest, True
        except BaseException:
            try:
                shutil.rmtree(directory, ignore_errors=True)
            finally:
                raise


def job_view(subject_id: str, manifest: Mapping[str, Any]) -> JobView:
    return project_job(manifest, worker_alive=worker_is_alive(manifest))


# ---------------------------------------------------------------------------
# Worker claim and birth identity
# ---------------------------------------------------------------------------
def _read_boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        return ""


def process_birth(pid: int | None = None) -> dict[str, Any]:
    use_pid = int(pid if pid is not None else os.getpid())
    start_ticks: int | None = None
    try:
        raw = Path(f"/proc/{use_pid}/stat").read_text(encoding="ascii")
        close = raw.rfind(")")
        fields = raw[close + 1 :].split()
        # Field 22 (1-based) is starttime; after comm/state the list starts at 3.
        start_ticks = int(fields[19])
    except (OSError, IndexError, ValueError):
        start_ticks = None
    return {"pid": use_pid, "start_ticks": start_ticks, "boot_id": _read_boot_id()}


def worker_is_alive(manifest: Mapping[str, Any]) -> bool:
    worker = manifest.get("worker")
    if not isinstance(worker, Mapping):
        return False
    try:
        pid = int(worker.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    current = process_birth(pid)
    if worker.get("boot_id") and current.get("boot_id") and worker.get("boot_id") != current.get("boot_id"):
        return False
    recorded = worker.get("start_ticks")
    if recorded is not None and current.get("start_ticks") != recorded:
        return False
    return True


@dataclass
class WorkerClaim:
    """One real OS claim for a job; release is fork-safe and idempotent."""

    subject_id: str
    job_id: str
    path: Path
    fd: int
    owner_pid: int
    birth: dict[str, Any]
    _released: bool = field(default=False, repr=False)

    @classmethod
    def acquire(cls, subject_id: str, job_id: str) -> "WorkerClaim | None":
        directory = job_dir(subject_id, job_id, create=False)
        path = json_store.confined(directory, directory / WORKER_LOCK)
        if path.is_symlink():
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        flags |= os.O_NONBLOCK
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise subject_error(ErrorCode.STORAGE_CORRUPT)
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        except OSError as exc:
            os.close(fd)
            raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        except BaseException:
            os.close(fd)
            raise
        return cls(
            subject_id=subject_id,
            job_id=job_id,
            path=path,
            fd=fd,
            owner_pid=os.getpid(),
            birth=process_birth(),
        )

    @property
    def active(self) -> bool:
        return not self._released and self.owner_pid == os.getpid()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        inherited = self.owner_pid != os.getpid()
        try:
            if not inherited:
                try:
                    import fcntl

                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                os.close(self.fd)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Chunk/result persistence
# ---------------------------------------------------------------------------
def write_chunk_text(job_directory: Path, chunk_id: str, text: str) -> str:
    """Atomically write one chunk text and return its job-relative path."""
    leaf = f"{chunk_id}.txt"
    text_dir = json_store.confined(job_directory, job_directory / TEXT_DIR)
    json_store.make_directory(text_dir)
    target = json_store.confined(text_dir, text_dir / leaf)
    if target.is_symlink():
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    fd, temp_name = tempfile.mkstemp(prefix=".text-", dir=str(text_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(str(text))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return f"{TEXT_DIR}/{leaf}"


def read_chunk_text(job_directory: Path, relative: str) -> str:
    root = json_store.confined(job_directory, job_directory / TEXT_DIR)
    relative_path = Path(relative)
    if relative_path.is_absolute() or len(relative_path.parts) != 2 or relative_path.parts[0] != TEXT_DIR:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    target = json_store.confined(root, root / relative_path.name)
    if not target.is_file() or target.is_symlink():
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    try:
        with _open_regular(target) as handle:
            return handle.read().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc


def write_result(subject_id: str, job_id: str, payload: dict[str, Any]) -> None:
    path = result_path(subject_id, job_id)
    json_store.atomic_write_object(path, payload)


def read_result(subject_id: str, job_id: str) -> dict[str, Any]:
    path = result_path(subject_id, job_id)
    if not path.is_file() or path.is_symlink():
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    payload = json_store.read_object(path, default={})
    if not isinstance(payload, dict):
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    return payload


def write_publish_plan(subject_id: str, job_id: str, payload: dict[str, Any]) -> None:
    json_store.atomic_write_object(publish_plan_path(subject_id, job_id), payload)


def read_publish_plan(subject_id: str, job_id: str) -> dict[str, Any] | None:
    path = publish_plan_path(subject_id, job_id)
    if not path.is_file() or path.is_symlink():
        return None
    payload = json_store.read_object(path, default={})
    return payload if isinstance(payload, dict) else None


def cleanup_media(subject_id: str, job_id: str, *, drop_text: bool = True) -> None:
    """Delete only this job's private input/chunk (and optionally text) copies."""
    directory = job_dir(subject_id, job_id, create=False)
    names = [INPUT_DIR, CHUNKS_DIR, "normalized"] + ([TEXT_DIR] if drop_text else [])
    for name in names:
        target = json_store.confined(directory, directory / name)
        if target.is_symlink():
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        if target.exists():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.is_file() and not target.is_symlink():
                target.unlink()
            else:
                raise subject_error(ErrorCode.STORAGE_CORRUPT)


def result_is_private_path(value: object) -> bool:
    text = str(value or "")
    return text.startswith("/") or ".." in Path(text).parts or "\\" in text


__all__ = [
    "CHUNK_FAILED",
    "CHUNK_PENDING",
    "CHUNK_SUCCESS",
    "JobNotFound",
    "WorkerClaim",
    "cleanup_media",
    "create_job",
    "job_dir",
    "job_view",
    "jobs_root",
    "list_manifests",
    "manifest_path",
    "process_birth",
    "read_chunk_text",
    "read_manifest",
    "read_publish_plan",
    "read_result",
    "result_path",
    "sha256_file",
    "update_manifest",
    "worker_is_alive",
    "write_chunk_text",
    "write_manifest",
    "write_publish_plan",
    "write_result",
]
