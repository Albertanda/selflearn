"""Subject upload preflight, private staging and controlled publication (C07).

One upload batch is handled in four separated phases so that "accepted" never
means "half done":

1. **Preflight** (:func:`plan_batch`) — pure, no filesystem access. Every
   original name is checked (absolute paths, separators, traversal, control
   characters, non-UTF-8) *before* the existing normalizer is allowed to rename
   anything, then the whole batch is classified and checked as a unit: empty
   batches, mixed ``auto`` categories, audio mixed into documents, unsupported
   extensions and normalized (NFC + lowercased extension) duplicates are all
   refused here, before any directory is created.
2. **Staging** (:func:`stage_files`) — streamed, size-limited copy into a
   private staging directory *outside* ``materials/`` and ``raw/`` (the indexer
   walks ``raw`` recursively and would happily index a ``.bak.txt``). Files are
   hashed while they are written; nothing is published yet.
3. **Transcription** (P1-16) — the ASR provider is called with a controlled
   file stream, never a whole-file ``read_bytes()``. A batch is only published
   once *every* file transcribed.
4. **Publication** (:func:`commit_documents` / :func:`commit_transcripts`) —
   inside one KB-scoped critical section: refuse while a worker is alive or a
   task is only queued, refuse when the authoritative materials and the index
   source already disagree, replace both copies, verify the published digest,
   record the source manifest, and reserve the index task. Any ordinary failure
   rolls the *whole* batch back to the previous consistent bytes.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
from typing import Any, Callable, Iterable, Iterator, Sequence
import uuid

from deeptutor.knowledge.naming import validate_knowledge_base_name
from deeptutor.services.asr import transcribe as transcribe_service
from deeptutor.services.rag.kb_paths import resolve_kb_dir
from deeptutor.subjects import json_store, store, subject_operations
from deeptutor.subjects import material_manifest as manifest_mod
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageIOError,
    SubjectStorageError,
    subject_error,
)
from deeptutor.utils.document_validator import DocumentValidator

logger = logging.getLogger(__name__)

#: Audio extensions this endpoint accepts (a *local* whitelist: the global
#: document policy is not widened by the lecture path).
AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".amr", ".wma"}
)

#: Extension → MIME for the ASR multipart part. The wire table itself lives with
#: the ASR service that owns the multipart request; this is the same mapping.
AUDIO_MIME = dict(transcribe_service.MIME_BY_EXTENSION)

#: Suffix of the transcript file kept next to the recording in ``materials``.
TRANSCRIPT_SUFFIX = ".transcript.txt"

#: Extension → knowledge type used by ``type=auto``.
TYPE_BY_EXTENSION = {
    ".pdf": "textbook",
    ".epub": "textbook",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".png": "board",
    ".jpg": "board",
    ".jpeg": "board",
    ".webp": "board",
    ".mp3": "lecture",
    ".m4a": "lecture",
    ".wav": "lecture",
    ".docx": "assignment",
    ".doc": "assignment",
    ".md": "assignment",
    ".txt": "assignment",
}

ALLOWED_TYPES = frozenset(
    {"textbook", "ppt", "board", "lecture", "assignment", "past_exam", "other"}
)

STAGING_DIR_NAME = ".upload-staging"
#: Read/write block for uploaded bytes (bounded memory, streamed end to end).
WORK_CHUNK = 1 << 20
#: Suffix of the same-directory temporary file used for atomic publication. It
#: is deliberately *not* an indexable extension, so a concurrent indexer that
#: walks ``raw`` never collects a partially written file.
PART_SUFFIX = ".p1part"

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Batch preflight (P1-17)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BatchFile:
    """One accepted upload: original name, publish name and wire metadata."""

    upload: Any
    original: str
    name: str
    extension: str
    mime: str | None


@dataclass(frozen=True)
class UploadPlan:
    operation: str  # "index" | "transcribe"
    kb_type: str
    kb_name: str
    files: tuple[BatchFile, ...]

    @property
    def names(self) -> list[str]:
        return [item.name for item in self.files]

    @property
    def audio(self) -> bool:
        return self.operation == "transcribe"


def kb_name_for_type(kb_type: str) -> str:
    """The KB a type uploads into (``<type>-kb``), validated as a KB name."""
    candidate = f"{kb_type}-kb"
    try:
        return validate_knowledge_base_name(candidate)
    except ValueError:
        return f"{kb_type}{store.new_kb_id()[:6]}"


def assert_safe_original_name(name: Any) -> str:
    """Refuse a raw client filename that is not a single safe basename.

    This runs *before* :class:`DocumentValidator`, which silently strips path
    components: ``../../etc/passwd`` must be a rejection, not a quiet rename to
    ``passwd`` that then overwrites a real file.
    """
    if not isinstance(name, str) or not name:
        raise json_store.invalid_input("文件名不能为空")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        raise json_store.invalid_input("文件名包含无法编码的字符") from None
    if not name.strip():
        raise json_store.invalid_input("文件名不能为空")
    if name in (".", ".."):
        raise json_store.invalid_input("文件名不能是 '.' 或 '..'")
    if "/" in name or "\\" in name:
        raise json_store.invalid_input("文件名不能包含路径分隔符")
    if os.path.isabs(name):
        raise json_store.invalid_input("文件名不能是绝对路径")
    if _CONTROL_RE.search(name):
        raise json_store.invalid_input("文件名不能包含控制字符")
    return name


def normalize_name(name: str, *, allowed: Iterable[str]) -> str:
    """Apply the existing normalizer (NFC + lowercased extension) to *name*."""
    try:
        return DocumentValidator.validate_upload_safety(
            name, None, allowed_extensions=set(allowed)
        )
    except ValueError as exc:
        raise json_store.invalid_input("文件类型不受支持或文件名非法") from exc


def audio_mime(extension: str) -> str:
    """MIME for one audio extension; unknown audio is never labelled ``mpeg``."""
    return AUDIO_MIME.get(extension.lower(), "application/octet-stream")


def plan_batch(files: Sequence[Any], *, type: str) -> UploadPlan:
    """Validate one whole batch and decide its single operation.

    Raises :class:`InvalidInputError` (400) for anything that must never reach
    the disk — including the mixed batches the old first-file heuristic used to
    mislabel.
    """
    if not files:
        raise json_store.invalid_input("没有收到文件")

    if type == "auto":
        explicit: str | None = None
    else:
        if type not in ALLOWED_TYPES:
            raise json_store.invalid_input("未知的资料类型")
        explicit = type

    supported = manifest_mod.supported_extensions()
    prepared: list[BatchFile] = []
    for upload in files:
        original = assert_safe_original_name(getattr(upload, "filename", None))
        extension = PurePosixPath(original).suffix.lower()
        if extension in AUDIO_EXTENSIONS:
            name = normalize_name(original, allowed=AUDIO_EXTENSIONS)
            prepared.append(
                BatchFile(upload, original, name, extension, audio_mime(extension))
            )
            continue
        if extension not in supported:
            raise json_store.invalid_input(
                "文件类型不受支持，当前引擎无法索引该格式。"
            )
        name = normalize_name(original, allowed=supported)
        prepared.append(BatchFile(upload, original, name, extension, None))

    # ---- batch-level classification: never route by the first file alone ----
    #: A batch is audio **only** when every file is audio; an explicit ``lecture``
    #: must be all-audio and an explicit document type must contain no audio.
    audio_flags = [item.extension in AUDIO_EXTENSIONS for item in prepared]
    categories = [
        "lecture" if is_audio else TYPE_BY_EXTENSION.get(item.extension, "textbook")
        for item, is_audio in zip(prepared, audio_flags)
    ]
    if explicit is None:
        if len(set(categories)) != 1:
            raise json_store.invalid_input("同一批上传的资料类型不一致，请分开上传。")
        kb_type = categories[0]
    else:
        kb_type = explicit
        if kb_type == "lecture" and not all(audio_flags):
            raise json_store.invalid_input("lecture 类型只接受音频文件。")
        if kb_type != "lecture" and any(audio_flags):
            raise json_store.invalid_input("音频文件只能作为 lecture 上传。")

    # ---- normalized duplicates and derived-name conflicts (whole batch) ----
    seen: dict[str, str] = {}
    for item in prepared:
        if item.name in seen:
            raise json_store.invalid_input("同一批中存在重名文件，请重命名后重试。")
        seen[item.name] = item.original
    if kb_type == "lecture":
        for item in prepared:
            derived = f"{item.name}{TRANSCRIPT_SUFFIX}"
            if derived in seen:
                raise json_store.invalid_input("音频与其转写文件名冲突，请重命名后重试。")

    return UploadPlan(
        operation="transcribe" if kb_type == "lecture" else "index",
        kb_type=kb_type,
        kb_name=kb_name_for_type(kb_type),
        files=tuple(prepared),
    )


# ---------------------------------------------------------------------------
# Paths (never resolved through a linked external pointer)
# ---------------------------------------------------------------------------
def _same_path(left: Path | str, right: Path | str) -> bool:
    return os.path.normpath(str(left)) == os.path.normpath(str(right))


def materials_path(subject_id: str, kb_type: str, *, create: bool = False) -> Path:
    """``materials/<type>`` without the auto-creating store helper (GET-safe)."""
    directory = store.subject_dir(subject_id)
    base = json_store.confined(directory, directory / "materials")
    sub = json_store.confined(
        base, base / json_store.safe_segment(kb_type, what="材料类型")
    )
    if create:
        json_store.make_directory(sub)
    return sub


def kb_base_path(subject_id: str, *, create: bool = False) -> Path:
    """The subject's ``knowledge_bases`` root, confined (created only on write).

    A GET must not bring the directory into existence, so the read paths use
    ``create=False`` and the store helper that always mkdir's is not used.
    """
    directory = store.subject_dir(subject_id)
    base = json_store.confined(directory, directory / "knowledge_bases")
    if create:
        json_store.make_directory(base)
    return base


def kb_paths(
    subject_id: str, kb_name: str, *, create: bool = False
) -> tuple[Path, Path]:
    """``(kb_dir, raw_dir)`` strictly inside the subject's own KB root.

    A KB whose ``kb_config.json`` points at a linked external index is refused
    instead of being written through: the subject upload entry must never turn
    into a writer for a library outside this subject.
    """
    base = kb_base_path(subject_id, create=create)
    kb_dir = json_store.confined(
        base, base / json_store.safe_segment(kb_name, what="知识库名称")
    )
    if not _same_path(resolve_kb_dir(base, kb_name), kb_dir):
        raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
    raw_dir = json_store.confined(kb_dir, kb_dir / "raw")
    if create:
        json_store.make_directory(kb_dir)
        json_store.make_directory(raw_dir)
    return kb_dir, raw_dir


@contextmanager
def staging_root(subject_id: str) -> Iterator[Path]:
    """A private, cleaned-up staging directory inside this subject's tree."""
    directory = store.subject_dir(subject_id)
    root = json_store.confined(directory, directory / STAGING_DIR_NAME)
    json_store.make_directory(root)
    try:
        os.chmod(root, 0o700)
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        logger.debug("Could not tighten staging directory mode", exc_info=True)
    slot = root / uuid.uuid4().hex
    json_store.make_directory(slot)
    try:
        yield slot
    finally:
        shutil.rmtree(slot, ignore_errors=True)


# ---------------------------------------------------------------------------
# Staging (streamed, size limited, hashed while written)
# ---------------------------------------------------------------------------
@dataclass
class Staged:
    entry: BatchFile
    path: Path
    size: int
    sha256: str


def max_file_size() -> int:
    return int(DocumentValidator.MAX_FILE_SIZE)


async def stage_files(
    plan: UploadPlan, staging_dir: Path, *, size_limit: int | None = None,
    batch_limit: int | None = None,
) -> list[Staged]:
    """Stream every part of the batch into private staging; nothing published.

    Memory stays bounded by :data:`WORK_CHUNK` (never ``upload.read()`` with no
    argument, never ``read_bytes()``), the limit is enforced while writing, and
    the digest computed here is the one later compared against the published
    file.
    """
    limit = max_file_size() if size_limit is None else int(size_limit)
    staged: list[Staged] = []
    batch_size = 0
    for entry in plan.files:
        target = Path(staging_dir) / entry.name
        hasher = hashlib.sha256()
        size = 0
        try:
            with open(target, "wb") as handle:
                while True:
                    chunk = await entry.upload.read(WORK_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    batch_size += len(chunk)
                    if batch_limit is not None and batch_size > batch_limit:
                        from deeptutor.subjects.errors import AsrErrorCode, asr_error

                        raise asr_error(AsrErrorCode.ASR_INPUT_TOO_LARGE)
                    if size > limit:
                        raise json_store.invalid_input("文件超过允许的大小限制。")
                    hasher.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise StorageIOError(
                "上传文件写入临时目录失败。", path=entry.name, cause=exc
            ) from exc
        staged.append(Staged(entry, target, size, hasher.hexdigest()))
    return staged


def _unlink(path: Path) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _digest_of(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(WORK_CHUNK), b""):
            size += len(block)
            hasher.update(block)
    return size, hasher.hexdigest()


def _leaf_state(path: Path, *, what: str) -> str:
    """Classify a leaf without following it: ``absent`` / ``regular`` / error.

    ``os.lstat`` is used (never ``exists()``/``is_file()``, which follow links):
    a symlink — dangling or not — and any non-regular entry (FIFO, socket,
    device) are refused *before* anything is opened, so a planted link cannot
    redirect a write and a FIFO cannot block it.
    """
    path = Path(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise StorageIOError(f"{what}无法访问。", path=path.name, cause=exc) from exc
    if stat.S_ISLNK(info.st_mode):
        raise StorageIOError(f"{what}是符号链接，已拒绝访问。", path=path.name)
    if not stat.S_ISREG(info.st_mode):
        raise StorageIOError(f"{what}不是普通文件。", path=path.name)
    return "regular"


def _prepare_part_leaf(part: Path) -> None:
    """Make a predictable temp leaf safe for **exclusive** creation.

    A symlink or special file there is a hard failure (it is never followed or
    removed). A leftover *regular* temp file from an interrupted run is our own
    namespace, so it is removed and re-created exclusively.
    """
    state = _leaf_state(part, what="临时文件")
    if state == "regular":
        try:
            os.unlink(part)
        except OSError as exc:
            raise StorageIOError("临时文件清理失败。", path=part.name, cause=exc) from exc


def _create_exclusive(part: Path, *, what: str) -> int:
    """Create *part* as a brand-new regular file; return its descriptor."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(str(part), flags, 0o600)
    except OSError as exc:
        raise StorageIOError(f"{what}失败。", path=part.name, cause=exc) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise StorageIOError(f"{what}失败。", path=part.name)
    except BaseException:
        _close_quietly(descriptor)
        _unlink(part)
        raise
    return descriptor


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:  # pragma: no cover - best effort on a failing close
        logger.debug("Could not close temporary descriptor", exc_info=True)


def _write_via_private_temp(
    target: Path, *, what: str, write: Callable[[Any], None]
) -> None:
    """Publish *target* through an exclusively created, un-followable temp leaf.

    Both the final leaf and the temp leaf are checked first (no symlink, no
    non-regular file), the temp file is created with ``O_EXCL|O_NOFOLLOW`` and
    verified to be a regular file, and the replacement is a same-directory
    ``os.replace``. Any failure removes the temp leaf and leaves *target* as it
    was.
    """
    target = Path(target)
    _leaf_state(target, what="目标文件")
    part = target.parent / f".{target.name}{PART_SUFFIX}"
    _prepare_part_leaf(part)
    descriptor = _create_exclusive(part, what=what)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, target)
    except BaseException as exc:
        _unlink(part)
        if isinstance(exc, SubjectStorageError):
            raise
        if isinstance(exc, OSError):
            raise StorageIOError(f"{what}失败。", path=target.name, cause=exc) from exc
        raise


def _atomic_copy(source: Path, target: Path) -> None:
    """Copy *source* next to *target* and replace it atomically."""

    def _write(handle: Any) -> None:
        with open(source, "rb") as origin:
            shutil.copyfileobj(origin, handle, WORK_CHUNK)

    _write_via_private_temp(target, what="资料写入", write=_write)


def _write_text_atomic(target: Path, text: str) -> None:
    """Write transcript text next to *target*, atomically and confined."""
    payload = str(text).encode("utf-8")

    def _write(handle: Any) -> None:
        handle.write(payload)

    _write_via_private_temp(target, what="转写文本写入", write=_write)


class PublishPreconditionError(RuntimeError):
    """The target changed after the job prepared its publication plan."""


class Rollback:
    """Undo actions for one publication; failures are reported, never hidden."""

    def __init__(self) -> None:
        self._actions: list[tuple[str, Callable[[], None]]] = []

    def add(self, label: str, action: Callable[[], None]) -> None:
        self._actions.append((label, action))

    def run(self) -> list[str]:
        failures: list[str] = []
        for label, action in reversed(self._actions):
            try:
                action()
            except Exception:  # noqa: BLE001 - reported, not swallowed
                failures.append(label)
                logger.error("Rollback step failed: %s", label, exc_info=True)
        self._actions.clear()
        return failures


def _reject_unsafe_leaf(target: Path) -> None:
    """Refuse to publish through a symlink or over a non-regular file."""
    _leaf_state(target, what="目标文件")


def publish_pairs(
    pairs: Sequence[tuple[Staged, Path]], *, backup_root: Path, rollback: Rollback
) -> Rollback:
    """Publish staged files, verifying every published digest.

    Each replaced file is first copied into *backup_root* (never moved, so a
    failure leaves the old bytes recoverable) and each new file is compared
    against the staged digest after the atomic replace. Undo actions are added
    to the **caller's** rollback as they go, so a failure in the middle of the
    batch still restores the copies that were already replaced.
    """
    json_store.make_directory(Path(backup_root))
    for index, (staged, target) in enumerate(pairs):
        target = Path(target)
        _reject_unsafe_leaf(target)
        backup: Path | None = None
        if target.exists():
            backup = Path(backup_root) / f"{index:03d}-{target.name}"
            _atomic_copy(target, backup)
        # Register the undo *before* touching the target: the replace can
        # succeed and the verification read still fail, and that failure must
        # put the old bytes back too.
        if backup is None:
            rollback.add(f"remove:{target.name}", lambda t=target: _unlink(t))
        else:
            rollback.add(
                f"restore:{target.name}",
                lambda b=backup, t=target: _atomic_copy(b, t),
            )
        _atomic_copy(staged.path, target)
        size, digest = _digest_of(target)
        if (size, digest) != (staged.size, staged.sha256):
            raise StorageIOError("发布后的文件校验失败。", path=target.name)
    return rollback


def restore_or_fail(rollback: Rollback, exc: BaseException) -> None:
    """Undo a failed publication; an undo failure is an explicit 500."""
    failures = rollback.run()
    if failures:
        raise StorageIOError(
            "资料回滚失败，已禁止建立索引。", path=",".join(failures)
        ) from exc
    if isinstance(exc, OSError) and not isinstance(exc, SubjectStorageError):
        raise StorageIOError("资料写入失败。", cause=exc) from exc
    raise exc


KB_CONFIG_NAME = "kb_config.json"


def read_kb_status(base_dir: Path | str, kb_name: str) -> dict | None:
    """One KB's status straight from ``kb_config.json`` — **no side effects**.

    ``KnowledgeBaseManager`` creates its directory and rewrites a normalized
    config on construction, so a read-only projection must not go through it.
    Missing file/entry means "no status"; an existing file that is not a JSON
    object is corruption rather than a silent default.
    """
    config_path = Path(base_dir) / KB_CONFIG_NAME
    text = json_store._read_text(config_path)
    if text is None:
        return None
    payload = json_store._strict_loads(text, source=config_path)
    if not isinstance(payload, dict):
        raise json_store.corrupt_error(KB_CONFIG_NAME, "顶层不是对象")
    entries = payload.get("knowledge_bases")
    if not isinstance(entries, dict):
        return None
    entry = entries.get(kb_name)
    if not isinstance(entry, dict):
        return None
    coverage, coverage_warning = manifest_mod.public_image_coverage(entry)
    return {
        "status": entry.get("status", "unknown"),
        "progress": entry.get("progress"),
        "updated_at": entry.get("updated_at"),
        # Validated, read-only projection of the last measured image coverage:
        # unmeasured or untrustworthy stored values come back as None instead of
        # being echoed, and the warning is derived from the validated counts.
        "image_coverage": coverage,
        "image_coverage_warning": coverage_warning,
    }


# ---------------------------------------------------------------------------
# Same-KB busy state: live worker *and* accepted-but-not-started reservation
# ---------------------------------------------------------------------------
_RESERVATIONS: dict[str, dict] = {}
_RESERVATIONS_LOCK = threading.Lock()


def worker_key(kb_dir: Path | str) -> str:
    """The controlled identity shared with the indexing stall guard."""
    return str(Path(kb_dir).expanduser().resolve())


def _pipeline_state(key: str) -> dict:
    try:
        from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_mod
    except Exception:  # pragma: no cover - engine import problems are reported
        logger.warning("Index worker registry unavailable", exc_info=True)
        return {"key": key, "alive": False, "registered": False}
    return pipeline_mod.index_worker_state(key)


def task_is_active(task_id: str | None) -> bool:
    """A terminal task status is *not* proof that its thread has exited."""
    if not task_id:
        return False
    try:
        from deeptutor.api.utils.task_id_manager import TaskIDManager
    except Exception:  # pragma: no cover - defensive
        return False
    metadata = TaskIDManager.get_instance().get_task_metadata(task_id) or {}
    return str(metadata.get("status") or "") not in ("completed", "error", "cancelled")


def reserve_index_task(
    kb_dir: Path | str,
    *,
    task_id: str,
    subject_id: str,
    kb_name: str,
    fingerprint: str,
    shape: str,
    documents: int,
    action: str,
    materials_dir: str | None = None,
    lease: subject_operations.ActivityLease | None = None,
) -> dict:
    """Reserve this KB for one index task; raises ``kb_busy`` if already held.

    ``lease`` is the subject activity lease acquired by the upload entry point.
    It is stored in the reservation so the same lease stays held from
    "accepted" through the background worker's real terminal state; the queue
    hand-off never releases it in between.
    """
    key = worker_key(kb_dir)
    reservation = {
        "key": key,
        "task_id": task_id,
        "subject_id": subject_id,
        "kb_name": kb_name,
        "fingerprint": fingerprint,
        "shape": shape,
        "documents": documents,
        "action": action,
        "kb_dir": str(kb_dir),
        "materials_dir": materials_dir,
        "lease": lease,
    }
    with _RESERVATIONS_LOCK:
        current = _RESERVATIONS.get(key)
        if current is not None:
            raise subject_error(ErrorCode.KB_BUSY)
        _RESERVATIONS[key] = reservation
    return reservation


def clear_reservation(kb_dir: Path | str, *, task_id: str | None = None) -> bool:
    key = worker_key(kb_dir)
    with _RESERVATIONS_LOCK:
        current = _RESERVATIONS.get(key)
        if current is None:
            return False
        if task_id is not None and current.get("task_id") != task_id:
            return False
        _RESERVATIONS.pop(key, None)
    lease = current.get("lease")
    if lease is not None:
        lease.release()
    return True


def reservation_for(kb_dir: Path | str) -> dict | None:
    with _RESERVATIONS_LOCK:
        current = _RESERVATIONS.get(worker_key(kb_dir))
        return dict(current) if current is not None else None


def busy_state(kb_dir: Path | str) -> dict:
    """Everything that must block a same-KB upload, in one read-only view."""
    reservation = reservation_for(kb_dir)
    worker = _pipeline_state(worker_key(kb_dir))
    queued = reservation is not None and not bool(worker.get("alive"))
    return {
        "key": worker_key(kb_dir),
        "reserved": reservation is not None,
        "reservation": reservation,
        "worker_alive": bool(worker.get("alive")),
        "worker_registered": bool(worker.get("registered")),
        "queued": queued,
        "busy": reservation is not None or bool(worker.get("alive")),
        "task_id": (reservation or {}).get("task_id"),
    }


def assert_kb_not_busy(kb_dir: Path | str) -> dict:
    state = busy_state(kb_dir)
    if state["busy"]:
        raise subject_error(ErrorCode.KB_BUSY)
    return state


def reset_registry_for_tests() -> None:  # pragma: no cover - test helper
    with _RESERVATIONS_LOCK:
        leases = [
            entry.get("lease") for entry in _RESERVATIONS.values() if entry.get("lease")
        ]
        _RESERVATIONS.clear()
    for lease in leases:
        lease.release()


# ---------------------------------------------------------------------------
# Document commit (P1-18) — one critical section, whole-batch rollback
# ---------------------------------------------------------------------------
@dataclass
class CommitResult:
    operation: str
    kb_type: str
    kb_name: str
    names: list[str] = field(default_factory=list)
    task_id: str | None = None
    documents: int = 0
    new_kb: bool = False


@dataclass
class CommitHooks:
    """Route-supplied side effects that must roll back with the publication.

    ``prepare_kb`` creates/registers the KB record itself (metadata + registry),
    ``write_record`` updates the subject's knowledge record with the new count.
    Both run *inside* the KB critical section so a failure after the files were
    published can still undo the whole batch instead of leaving a half commit.
    """

    prepare_kb: Callable[[bool], None] | None = None
    write_record: Callable[[int], None] | None = None
    register_task: Callable[[bool], None] | None = None


def _backup_or_remove(
    path: Path, *, rollback: Rollback, backup_root: Path, label: str
) -> None:
    """Add an undo action that restores *path*'s current bytes (or removes it)."""
    path = Path(path)
    if path.exists() and path.is_file():
        backup = Path(backup_root) / f"undo-{label}"
        _atomic_copy(path, backup)
        rollback.add(f"restore:{label}", lambda b=backup, t=path: _atomic_copy(b, t))
    else:
        rollback.add(f"remove:{label}", lambda t=path: _unlink(t))


def kb_config_entry(base_dir: Path | str, kb_name: str) -> dict | None:
    """One KB's raw ``kb_config.json`` entry, read strictly and read-only."""
    config_path = Path(base_dir) / KB_CONFIG_NAME
    text = json_store._read_text(config_path)
    if text is None:
        return None
    payload = json_store._strict_loads(text, source=config_path)
    if not isinstance(payload, dict):
        raise json_store.corrupt_error(KB_CONFIG_NAME, "顶层不是对象")
    entries = payload.get("knowledge_bases")
    if not isinstance(entries, dict):
        return None
    entry = entries.get(kb_name)
    return dict(entry) if isinstance(entry, dict) else None


def _write_kb_config(config_path: Path, payload: dict) -> None:
    _leaf_state(config_path, what="知识库配置文件")
    try:
        json_store.atomic_write_object(config_path, payload)
    except SubjectStorageError:
        raise
    except OSError as exc:
        raise StorageIOError("知识库配置写入失败。", path=config_path.name, cause=exc) from exc


def revert_kb_config_entry(
    base_dir: Path | str, kb_name: str, previous: dict | None, *, remove_empty: bool = False
) -> None:
    """Merge our undo under the same subject lock used for registration."""
    with json_store.json_transaction(Path(base_dir).parent):
        _revert_kb_config_entry(base_dir, kb_name, previous, remove_empty=remove_empty)


def _revert_kb_config_entry(
    base_dir: Path | str, kb_name: str, previous: dict | None, *, remove_empty: bool
) -> None:
    """Undo **only our KB's** ``kb_config.json`` entry (re-read, then merge).

    Restoring the whole file from a snapshot would erase a different KB's
    successful registration that landed while this upload was running.
    """
    config_path = Path(base_dir) / KB_CONFIG_NAME
    text = json_store._read_text(config_path)
    if text is None and previous is None:
        return
    payload: dict = {}
    if text is not None:
        loaded = json_store._strict_loads(text, source=config_path)
        if not isinstance(loaded, dict):
            raise json_store.corrupt_error(KB_CONFIG_NAME, "顶层不是对象")
        payload = loaded
    entries = payload.get("knowledge_bases")
    if not isinstance(entries, dict):
        entries = {}
        payload["knowledge_bases"] = entries
    if previous is None:
        entries.pop(kb_name, None)
    else:
        entries[kb_name] = dict(previous)
    if remove_empty and not entries and set(payload) == {"knowledge_bases"}:
        _unlink(config_path)
        return
    _write_kb_config(config_path, payload)


def revert_knowledge_record(subject_id: str, kb_name: str, previous: dict | None) -> None:
    """Undo **only our KB's** record in ``knowledge.json`` (re-read, then merge)."""
    directory = store.subject_dir(subject_id)
    with json_store.json_transaction(directory):
        path = store.subject_data_path(subject_id, "knowledge.json")
        records = json_store.read_list(path)
        remaining = [item for item in records if item.get("kb_name") != kb_name]
        if previous is not None:
            remaining.append(dict(previous))
        json_store.atomic_write_list(path, remaining)


def discard_task_metadata(task_id: str, *, reason: str = "上传未完成，索引任务已取消。") -> None:
    """Close out a task created for an upload that never reached the queue.

    ``_build_unique_task_id`` registers the task as ``running`` before the
    commit; a failed commit must not leave that ghost behind. The terminal
    record is kept as history (only its status changes).
    """
    if not task_id:
        return
    try:
        from deeptutor.api.utils.task_id_manager import TaskIDManager
    except Exception:  # pragma: no cover - defensive
        return
    manager = TaskIDManager.get_instance()
    if manager.get_task_metadata(task_id) is None:
        return
    manager.update_task_status(task_id, "error", error=reason)


def commit_documents(
    *,
    subject_id: str,
    plan: UploadPlan,
    staged: Sequence[Staged],
    staging_dir: Path,
    task_id: str,
    hooks: CommitHooks | None = None,
    lease: subject_operations.ActivityLease | None = None,
) -> CommitResult:
    """Publish a document batch and reserve the index task, or change nothing.

    Everything happens inside the KB directory's transaction: the busy check,
    the source-consistency gate, both replacements, the manifest write and the
    task reservation. Nothing else may publish into this KB in between, so a
    "request accepted but the worker has not started yet" window cannot be
    entered twice.
    """
    hooks = hooks or CommitHooks()
    kb_dir, raw_dir = kb_paths(subject_id, plan.kb_name)
    kb_existed = kb_dir.exists()
    json_store.make_directory(kb_dir)
    json_store.make_directory(raw_dir)
    materials_dir = materials_path(subject_id, plan.kb_type, create=True)
    backup_root = Path(staging_dir) / "backup"
    json_store.make_directory(backup_root)
    result = CommitResult("index", plan.kb_type, plan.kb_name, names=plan.names)

    with json_store.json_transaction(kb_dir):
        assert_kb_not_busy(kb_dir)

        # The KB tree we just created is part of this batch: any failure below
        # must remove it again, not leave an empty registered-looking library.
        rollback = Rollback()
        if not kb_existed:
            rollback.add(
                f"remove-tree:{plan.kb_name}",
                lambda t=kb_dir: shutil.rmtree(t, ignore_errors=True),
            )
        try:
            manifest = manifest_mod.load_manifest(
                kb_dir, subject_id=subject_id, kb_name=plan.kb_name
            )
            raw_now = manifest_mod.source_files(raw_dir)
            materials_now = manifest_mod.enumerate_files(materials_dir)
            if manifest is not None:
                drift = manifest_mod.compare_manifest(manifest["files"], raw_now)
                if not drift["ok"]:
                    raise subject_error(ErrorCode.MATERIAL_OUT_OF_SYNC)
            # materials 是权威副本：索引源里有的文件必须与它逐字节一致，
            # 与 manifest 是否已存在无关（旧库同样只读比较）。
            if not manifest_mod.compare_materials(raw_now, materials_now)["ok"]:
                raise subject_error(ErrorCode.MATERIAL_OUT_OF_SYNC)

            new_kb = manifest is None and not raw_now
            result.new_kb = new_kb
            pairs = [(item, materials_dir / item.entry.name) for item in staged]
            pairs += [(item, raw_dir / item.entry.name) for item in staged]
            publish_pairs(pairs, backup_root=backup_root, rollback=rollback)

            published = manifest_mod.source_files(raw_dir)
            new_manifest = manifest_mod.build_manifest(
                subject_id=subject_id, kb_name=plan.kb_name, files=published
            )
            manifest_file = manifest_mod.manifest_path(kb_dir)
            _backup_or_remove(
                manifest_file,
                rollback=rollback,
                backup_root=backup_root,
                label="subject_sources.json",
            )
            manifest_mod.save_manifest(kb_dir, new_manifest)

            materials_check = manifest_mod.compare_materials(
                published, manifest_mod.enumerate_files(materials_dir)
            )
            if not materials_check["ok"]:
                raise StorageIOError("发布后的资料与索引源不一致。", path=plan.kb_name)

            # Snapshot *our* entry, not the shared file: the undo below merges
            # this KB back out of whatever the file holds at rollback time.
            record_before = store.get_knowledge_record(subject_id, plan.kb_name)
            config_base = kb_paths(subject_id, plan.kb_name)[0].parent
            config_existed = (config_base / KB_CONFIG_NAME).exists()
            config_before = kb_config_entry(config_base, plan.kb_name)

            if hooks.prepare_kb is not None:
                rollback.add(
                    "kb-config-entry",
                    lambda: revert_kb_config_entry(
                        config_base, plan.kb_name, config_before, remove_empty=not config_existed
                    ),
                )
                hooks.prepare_kb(new_kb)

            result.documents = len(published)
            if hooks.write_record is not None:
                rollback.add(
                    "knowledge-record",
                    lambda: revert_knowledge_record(subject_id, plan.kb_name, record_before),
                )
                hooks.write_record(result.documents)

            published_fingerprint = manifest_mod.fingerprint(published)
            reserve_index_task(
                kb_dir,
                task_id=task_id,
                subject_id=subject_id,
                kb_name=plan.kb_name,
                fingerprint=published_fingerprint,
                shape=manifest_mod.shape(published),
                documents=result.documents,
                action="create" if new_kb else "reindex",
                materials_dir=str(materials_dir),
                lease=lease,
            )
            rollback.add(
                "reservation",
                lambda: clear_reservation(kb_dir, task_id=task_id),
            )

            # Queue registration is part of the same boundary: if the caller
            # cannot register the job, the source update and the reservation are
            # rolled back instead of reporting a success that will never run.
            if hooks.register_task is not None:
                hooks.register_task(new_kb)
        except BaseException as exc:
            restore_or_fail(rollback, exc)

        result.task_id = task_id
        return result


def _check_publish_preconditions(
    materials_dir: Path, preconditions: Sequence[dict] | None
) -> None:
    """Verify the caller prepared this publication against the current bytes.

    Runs *inside* the materials transaction, immediately before the first
    rename.  ``allowed_sha256`` may contain the old and (for recovery) the new
    digest, but any other digest is a later third-party modification and is
    never overwritten.
    """
    for row in preconditions or ():
        if not isinstance(row, dict):
            raise PublishPreconditionError("invalid precondition")
        name = row.get("target")
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise PublishPreconditionError("invalid target")
        target = materials_dir / name
        _reject_unsafe_leaf(target)
        state = _leaf_state(target, what="转写发布目标")
        if state == "absent":
            if row.get("allow_absent") is True:
                continue
            raise PublishPreconditionError("target absent")
        size, digest = _digest_of(target)
        allowed = row.get("allowed_sha256")
        if not isinstance(allowed, list) or digest not in [str(item) for item in allowed]:
            raise PublishPreconditionError("target changed")


def commit_transcripts(
    *,
    subject_id: str,
    plan: UploadPlan,
    staged: Sequence[Staged],
    transcripts: Sequence[dict],
    staging_dir: Path,
    preconditions: Sequence[dict] | None = None,
) -> CommitResult:
    """Publish transcribed audio plus its transcript text, or change nothing.

    ``preconditions`` is used by the asynchronous ASR job to refuse overwriting
    a target that changed after the job wrote its publication plan.  The legacy
    synchronous caller omits it and keeps its historical overwrite contract.
    """
    materials_dir = materials_path(subject_id, plan.kb_type, create=True)
    backup_root = Path(staging_dir) / "backup"
    json_store.make_directory(backup_root)
    result = CommitResult("transcribe", plan.kb_type, plan.kb_name, names=plan.names)

    with json_store.json_transaction(materials_dir):
        _check_publish_preconditions(materials_dir, preconditions)
        rollback = Rollback()
        try:
            publish_pairs(
                [(item, materials_dir / item.entry.name) for item in staged],
                backup_root=backup_root,
                rollback=rollback,
            )
            for item, transcript in zip(staged, transcripts):
                target = materials_dir / f"{item.entry.name}{TRANSCRIPT_SUFFIX}"
                _reject_unsafe_leaf(target)
                if target.exists():
                    backup = Path(backup_root) / f"text-{target.name}"
                    _atomic_copy(target, backup)
                    rollback.add(
                        f"restore:{target.name}",
                        lambda b=backup, t=target: _atomic_copy(b, t),
                    )
                else:
                    rollback.add(f"remove:{target.name}", lambda t=target: _unlink(t))
                _write_text_atomic(target, str(transcript.get("text", "")))
        except BaseException as exc:
            restore_or_fail(rollback, exc)
        return result


# ---------------------------------------------------------------------------
# Background task wrapper: only a real terminal state publishes "ready"
# ---------------------------------------------------------------------------
def verify_reserved_sources(kb_dir: Path | str, reservation: dict) -> dict:
    """Do the sources on disk still match what this reservation published?

    Full digests, not the cheap (path, size) shape: a same-size rewrite must
    fail this gate. It runs before the index worker starts *and* before a
    terminal success is published, so neither a drifted queue entry nor a
    drifted completion can be reported as covering the current material.
    """
    kb_dir = Path(kb_dir)
    subject_id = str(reservation.get("subject_id") or "")
    kb_name = str(reservation.get("kb_name") or "")
    expected = str(reservation.get("fingerprint") or "")
    if not subject_id or not kb_name or not expected:
        return {"ok": False, "reason": "reservation_incomplete"}
    try:
        manifest = manifest_mod.load_manifest(
            kb_dir, subject_id=subject_id, kb_name=kb_name
        )
    except SubjectStorageError:
        return {"ok": False, "reason": "manifest_unreadable"}
    if manifest is None:
        return {"ok": False, "reason": "manifest_missing"}
    try:
        raw_now = manifest_mod.source_files(kb_dir / "raw")
    except SubjectStorageError:
        return {"ok": False, "reason": "raw_unreadable"}
    if manifest_mod.fingerprint(raw_now) != expected:
        return {"ok": False, "reason": "source_fingerprint_changed"}
    drift = manifest_mod.compare_manifest(manifest["files"], raw_now)
    if not drift["ok"]:
        return {"ok": False, "reason": "manifest_drift"}
    materials_dir = reservation.get("materials_dir")
    if not materials_dir:
        return {"ok": False, "reason": "materials_unknown"}
    materials_path_obj = Path(str(materials_dir))
    if not materials_path_obj.is_dir():
        return {"ok": False, "reason": "materials_missing"}
    try:
        material_files = manifest_mod.enumerate_files(materials_path_obj)
    except SubjectStorageError:
        return {"ok": False, "reason": "materials_unreadable"}
    if not manifest_mod.compare_materials(raw_now, material_files)["ok"]:
        return {"ok": False, "reason": "materials_drift"}
    return {"ok": True, "reason": "ready"}


def _publish_index_state(
    kb_dir: Path | str,
    task_id: str,
    reservation: dict,
    *,
    ok: bool,
    reason: str,
) -> dict:
    """Write this task's terminal record, preserving the last published one."""
    kb_dir = Path(kb_dir)
    subject_id = str(reservation.get("subject_id") or "")
    kb_name = str(reservation.get("kb_name") or "")
    fingerprint = str(reservation.get("fingerprint") or "")
    state_shape = str(reservation.get("shape") or "")
    documents = int(reservation.get("documents") or 0)
    if not (subject_id and kb_name and fingerprint and state_shape):
        return {"ok": False, "reason": "reservation_incomplete"}
    previous: dict | None = None
    try:
        current = manifest_mod.load_index_state(
            kb_dir, subject_id=subject_id, kb_name=kb_name
        )
    except SubjectStorageError:
        logger.error("Could not read existing index state", exc_info=True)
        return {"ok": False, "reason": "state_read_failed"}
    if isinstance(current, dict):
        if current.get("status") == "ready":
            previous = {
                "fingerprint": current.get("fingerprint"),
                "shape": current.get("shape"),
                "documents": current.get("documents"),
                "task_id": current.get("task_id"),
                "updated_at": current.get("updated_at"),
            }
        else:
            previous = current.get("last_ready")
    state = {
        "schema_version": manifest_mod.INDEX_STATE_SCHEMA_VERSION,
        "subject_id": subject_id,
        "kb_name": kb_name,
        "status": "ready" if ok else "error",
        "fingerprint": fingerprint,
        "shape": state_shape,
        "documents": documents,
        "task_id": task_id,
        "reason": reason,
        "updated_at": manifest_mod.utc_now(),
    }
    if previous is not None:
        state["last_ready"] = previous
    try:
        manifest_mod.save_index_state(kb_dir, state)
    except Exception:  # noqa: BLE001 - state must stay conservative
        logger.error("Could not persist index state", exc_info=True)
        return {"ok": False, "reason": "state_write_failed"}
    return {"ok": ok, "reason": reason}


def _mark_kb_error(subject_id: str, kb_name: str, task_id: str, reason: str) -> None:
    """Make a failure visible on the KB record without leaking diagnostics."""
    try:
        from deeptutor.knowledge.manager import KnowledgeBaseManager

        with json_store.json_transaction(store.subject_dir(subject_id)):
            KnowledgeBaseManager(base_dir=str(store.subject_kb_base_dir(subject_id))).update_kb_status(
                name=kb_name,
                status="error",
                progress={
                    "stage": "error",
                    "message": "索引任务未完成，请重试。",
                    "percent": 0,
                    "task_id": task_id,
                    "reason": reason,
                },
            )
    except Exception:  # pragma: no cover - best effort visibility
        logger.error("Could not mark index state failure", exc_info=True)


def _terminal_task_status(task_id: str) -> str:
    try:
        from deeptutor.api.utils.task_id_manager import TaskIDManager
    except Exception:  # pragma: no cover - defensive
        return ""
    metadata = TaskIDManager.get_instance().get_task_metadata(task_id) or {}
    return str(metadata.get("status") or "")


def _mark_task_failed(task_id: str, reason: str) -> None:
    try:
        from deeptutor.api.utils.task_id_manager import TaskIDManager
    except Exception:  # pragma: no cover - defensive
        return
    manager = TaskIDManager.get_instance()
    if manager.get_task_metadata(task_id) is None:
        return
    manager.update_task_status(
        task_id, "error", error=f"索引任务未完成（{reason}），未发布新的索引版本。"
    )


def finalize_reserved_task(kb_dir: Path | str, task_id: str) -> dict:
    """Record which source fingerprint the finished task actually produced.

    A reservation that is no longer *this* task's is a stale callback: it writes
    nothing at all. Otherwise "ready" additionally requires the sources still to
    match the reserved fingerprint, so a drifted run cannot be published as
    covering the current material.
    """
    reservation = reservation_for(kb_dir) or {}
    if str(reservation.get("task_id") or "") != task_id:
        logger.info("Ignoring finalizer for a stale or foreign reservation")
        return {"ok": False, "reason": "stale_reservation"}

    gate = verify_reserved_sources(kb_dir, reservation)
    terminal = _terminal_task_status(task_id)
    ok = gate["ok"] and terminal == "completed"
    reason = gate["reason"] if not gate["ok"] else (
        "task_failed" if terminal in ("error", "cancelled") else "task_incomplete"
    )
    if ok:
        try:
            manager_value = str(
                (read_kb_status(
                    kb_base_path(str(reservation.get("subject_id"))),
                    str(reservation.get("kb_name")),
                ) or {}).get("status") or ""
            )
            ok = manager_value == "ready"
        except Exception:  # noqa: BLE001 - a failed probe must not claim ready
            logger.warning("Could not confirm terminal index state", exc_info=True)
            ok = False
        reason = "ready" if ok else "kb_not_ready"
    result = _publish_index_state(kb_dir, task_id, reservation, ok=ok, reason=reason)
    if not result["ok"]:
        _mark_task_failed(task_id, str(result.get("reason") or "error"))
        _mark_kb_error(
            str(reservation.get("subject_id") or ""),
            str(reservation.get("kb_name") or ""),
            task_id,
            str(result.get("reason") or "error"),
        )
    clear_reservation(kb_dir, task_id=task_id)
    return result


async def run_reserved_index_task(
    kb_dir: Path | str, task_id: str, run: Callable[..., Any], *args: Any,
) -> None:
    """Cancellation of the awaiter cannot finalize a still-running worker."""
    task = asyncio.create_task(_run_reserved_index_task(kb_dir, task_id, run, *args))

    def consume(done: asyncio.Task) -> None:
        try:
            done.result()
        except BaseException:
            logger.warning("index completion could not be finalized")

    try:
        await asyncio.shield(task)
    except BaseException:
        task.add_done_callback(consume)
        raise


async def _run_reserved_index_task(
    kb_dir: Path | str,
    task_id: str,
    run: Callable[..., Any],
    *args: Any,
) -> None:
    """Run one reserved task, then publish the *real* terminal state.

    ``run`` is the existing background function (``run_initialization_task`` /
    ``run_reindex_task``); those catch their own errors and store raw
    diagnostics in the progress record, so success is decided by the terminal
    task status, the KB's own status *and* a re-check of the reserved source
    version — never by "the call returned".

    The reservation is re-validated **before** the index worker is called: a
    queue entry whose sources changed while it waited is failed safely instead
    of indexing material the caller never accepted.
    """
    reservation = reservation_for(kb_dir) or {}
    if str(reservation.get("task_id") or "") != task_id:
        logger.info("Index task %s is stale or foreign; not starting", task_id)
        return
    try:
        gate = await asyncio.to_thread(verify_reserved_sources, kb_dir, reservation)
    except Exception:
        logger.error("Could not check queued index sources", exc_info=True)
        gate = {"ok": False, "reason": "preflight_failed"}
    if not gate["ok"]:
        logger.warning("Index task %s skipped: %s", task_id, gate["reason"])
        await asyncio.to_thread(_abort_reserved_task, kb_dir, task_id, reservation, gate["reason"])
        return
    try:
        await run(*args)
    except Exception:  # noqa: BLE001 - recorded as a failed run below
        logger.error("Index task %s failed", task_id, exc_info=True)
    finally:
        await asyncio.to_thread(finalize_reserved_task, kb_dir, task_id)


def _abort_reserved_task(
    kb_dir: Path | str, task_id: str, reservation: dict, reason: str
) -> dict:
    """Fail a queued task whose sources no longer match, without indexing."""
    result = _publish_index_state(kb_dir, task_id, reservation, ok=False, reason=reason)
    _mark_task_failed(task_id, reason)
    _mark_kb_error(
        str(reservation.get("subject_id") or ""),
        str(reservation.get("kb_name") or ""),
        task_id,
        reason,
    )
    clear_reservation(kb_dir, task_id=task_id)
    return result


__all__ = [
    "ALLOWED_TYPES",
    "AUDIO_EXTENSIONS",
    "AUDIO_MIME",
    "BatchFile",
    "CommitHooks",
    "CommitResult",
    "Rollback",
    "STAGING_DIR_NAME",
    "TRANSCRIPT_SUFFIX",
    "TYPE_BY_EXTENSION",
    "UploadPlan",
    "assert_kb_not_busy",
    "assert_safe_original_name",
    "audio_mime",
    "busy_state",
    "clear_reservation",
    "commit_documents",
    "commit_transcripts",
    "finalize_reserved_task",
    "kb_name_for_type",
    "kb_paths",
    "materials_path",
    "max_file_size",
    "normalize_name",
    "plan_batch",
    "publish_pairs",
    "read_kb_status",
    "reservation_for",
    "reserve_index_task",
    "reset_registry_for_tests",
    "revert_kb_config_entry",
    "revert_knowledge_record",
    "restore_or_fail",
    "run_reserved_index_task",
    "stage_files",
    "staging_root",
    "task_is_active",
    "verify_reserved_sources",
    "worker_key",
]
