"""Subject export snapshot + ZIP publication (P1-40/P1-41, C12).

The export is split into a *prepare* half that runs in a worker thread and a
tiny *commit* half that runs only after the live async caller resumes:

* :func:`prepare_export_bundle` takes the exclusive subject activity lease,
  snapshots the authoritative learning tree and trusted completed artifacts
  into a private UUID staging directory, writes/validates ``manifest.json`` and
  produces a complete ZIP.  It never creates a public name.
* :func:`commit_export_bundle` re-checks the current user's subject and moves
  the ZIP to its public ``subjects/<sid>/subject-export-<uuid>.zip`` name with
  one no-overwrite link.  A cancelled request can therefore discard the
  preparation without ever exposing a URL.
* :func:`export_subject_bundle` keeps the synchronous Appendix-A API for
  callers that are not an HTTP route; it simply runs both halves inline.

Only allowlisted groups enter the archive: current registry metadata,
``learning/`` (top-level learning JSON, materials and KB originals/index files)
and ``artifacts/`` (completed report trees, known legacy report files and
completed review packs).  Settings, other subjects/users, old export ZIPs,
``_report_runs``, ``_review_pack``, upload staging, locks and diagnostics are
never enumerated.  Any symlink or non-regular source is refused before it can
be read, not silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any, Iterable
import uuid
import zipfile

from deeptutor.subjects import json_store, store, subject_operations
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    subject_error,
)

SCHEMA_VERSION = 1
EXPORT_MARKER = "subject-export-"
STAGING_DIRNAME = ".export-staging"
MANIFEST_NAME = "manifest.json"
SUBJECT_NAME = "subject.json"

_EXPORT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_REVIEW_PACK_RE = re.compile(r"^review-guide-([a-f0-9]{32})\.(pdf|docx)$")
_LEGACY_REPORT_RE = re.compile(r"^report-\d+\.(md|pdf)$")
_LEGACY_CHART_RE = re.compile(r"^chart_[1-8]\.png$")
_REPORT_ID_RE = re.compile(r"^[a-f0-9]{32}$")

EXCLUSIONS = [
    "chat_history:not_included_no_subject_binding",
    "settings_and_secrets:not_included",
    "other_subjects_and_users:not_included",
    "previous_export_zips:not_included",
    "private_runs_and_staging:not_included",
    "locks_temporaries_and_diagnostics:not_included",
]

#: A crash can leave a private preparation behind; it is never public and is
#: never scanned as input.  This is only used to clean *our own* staging trees.
_TRANSIENT_PARTS = {".upload-staging", ".asr_jobs", "_report_runs", "_review_pack", "__pycache__"}
_TRANSIENT_NAMES = {".deeptutor.lock", ".progress.json", ".DS_Store"}


class SnapshotChanged(RuntimeError):
    """The source set changed while the snapshot was being copied."""


@dataclass
class PreparedExport:
    export_id: str
    staging_root: Path
    zip_path: Path
    public_path: Path
    manifest: dict[str, Any]
    lease: subject_operations.ActivityLease

    def release(self) -> None:
        self.lease.release()


@dataclass(frozen=True)
class _Source:
    zip_path: str
    source: Path | None
    size: int
    sha256: str
    category: str
    payload: bytes | None = None

    def contract(self) -> dict[str, Any]:
        return {
            "path": self.zip_path,
            "size": self.size,
            "sha256": self.sha256,
            "category": self.category,
        }


def _sha256(path: Path) -> tuple[int, str]:
    """Hash one regular, non-symlink file without following links."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise subject_error(ErrorCode.STORAGE_CORRUPT)
            digest = hashlib.sha256()
            size = 0
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
                size += len(block)
    except SubjectOperationError:
        raise
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    return size, digest.hexdigest()


def _assert_tree_safe(root: Path) -> None:
    """Refuse any symlink/special entry anywhere below *root* (deep included)."""
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise subject_error(ErrorCode.STORAGE_IO)
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_walk_error):
            here = Path(dirpath)
            for name in list(dirnames) + list(filenames):
                full = here / name
                info = full.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise subject_error(ErrorCode.STORAGE_IO)
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise subject_error(ErrorCode.STORAGE_IO)
    except SubjectOperationError:
        raise
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc


def _is_transient(relative: PurePosixPath) -> bool:
    for part in relative.parts:
        if part in _TRANSIENT_PARTS or part.startswith(".publishing-"):
            return True
    name = relative.name
    return (
        name in _TRANSIENT_NAMES
        or name.lower().endswith((".zip", ".log", ".lock", ".tmp", ".part", ".pyc"))
        or any(part.startswith(".") for part in relative.parts)
        or name.endswith(".p1part")
        or (name.startswith(".review-guide-") and name.endswith(".part"))
        or name.startswith(".tmp")
    )


def _iter_regular_files(root: Path) -> Iterable[tuple[Path, PurePosixPath]]:
    if not root.exists():
        return
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_walk_error):
            here = Path(dirpath)
            dirnames[:] = sorted(
                name for name in dirnames if name not in _TRANSIENT_PARTS
            )
            for name in sorted(filenames):
                full = here / name
                info = full.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise subject_error(ErrorCode.STORAGE_IO)
                if stat.S_ISDIR(info.st_mode):
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise subject_error(ErrorCode.STORAGE_IO)
                relative = PurePosixPath(full.relative_to(root).as_posix())
                if _is_transient(relative):
                    continue
                yield full, relative
    except SubjectOperationError:
        raise
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc


def _walk_error(error: OSError) -> None:
    raise subject_error(ErrorCode.STORAGE_IO, cause=error) from error


def _safe_metadata(value: Any) -> Any:
    """Remove private config recursively without dropping benign 'key' words."""
    private = {"key", "api_key", "secret", "token", "password", "passwd", "credential",
               "credentials", "authorization", "owner", "owner_id", "owner_pid", "owner_birth",
               "diagnostic", "diagnostics", "private", "staging_dir", "public_dir", "base_url"}
    if isinstance(value, list):
        return [_safe_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    safe = {}
    for key, item in value.items():
        low = str(key).lower().replace("-", "_")
        if low in private or low.endswith(("_api_key", "_password", "_secret", "_token")):
            continue
        if isinstance(item, str) and ("path" in low or "root" in low or low == "host"):
            if Path(item).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", item):
                continue
        safe[key] = _safe_metadata(item)
    return safe


def _subject_record(subject_id: str) -> dict[str, Any]:
    """The registry record projected to safe, non-private metadata."""
    record = store.get_subject(subject_id)
    if record is None:
        raise subject_error(ErrorCode.SUBJECT_NOT_FOUND)
    safe = _safe_metadata(record)
    safe.setdefault("description", "")
    safe.setdefault("term", "")
    safe.setdefault("created_at", 0)
    safe["id"] = subject_id
    return safe


def _verify_artifact_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise subject_error(ErrorCode.STORAGE_CORRUPT)


def _verify_review_pack(path: Path) -> None:
    """A completed review pack must really parse, not merely have a suffix."""
    _verify_artifact_file(path)
    try:
        if path.suffix == ".pdf":
            from deeptutor.services.pdf.report import _verify_report_pdf

            _verify_report_pdf(path)
        else:
            from docx import Document

            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("missing OOXML parts")
            if not Document(str(path)).paragraphs:
                raise ValueError("empty DOCX")
    except SubjectOperationError as exc:
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc
    except Exception as exc:  # noqa: BLE001 - invalid artifact is corruption
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc


def _report_artifacts(public_dir: Path) -> list[tuple[Path, str]]:
    """Completed report files only; unknown/failed trees are not artifacts."""
    from deeptutor.services.pdf import report_store

    reports = public_dir / "reports"
    if not reports.exists():
        return []
    if reports.is_symlink() or not reports.is_dir():
        raise subject_error(ErrorCode.STORAGE_IO)
    out: list[tuple[Path, str]] = []
    for entry in sorted(reports.iterdir(), key=lambda item: item.name):
        if entry.is_symlink():
            raise subject_error(ErrorCode.STORAGE_IO)
        if entry.is_dir() and _REPORT_ID_RE.fullmatch(entry.name):
            manifest = report_store.read_published_manifest(public_dir.name, entry.name)
            if manifest is None or manifest.status != report_store.STATUS_COMPLETED:
                continue
            for file_entry in manifest.files:
                source = entry / file_entry.path
                _verify_artifact_file(source)
                size, digest = _sha256(source)
                if size != file_entry.size or digest != file_entry.sha256:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                out.append((source, f"artifacts/reports/{entry.name}/{file_entry.path}"))
            continue
        if entry.is_file() and (
            _LEGACY_REPORT_RE.fullmatch(entry.name)
            or _LEGACY_CHART_RE.fullmatch(entry.name)
        ):
            _verify_artifact_file(entry)
            out.append((entry, f"artifacts/reports/{entry.name}"))
    return out


def _review_pack_artifacts(public_dir: Path) -> list[tuple[Path, str]]:
    if not public_dir.exists():
        return []
    out: list[tuple[Path, str]] = []
    for entry in sorted(public_dir.iterdir(), key=lambda item: item.name):
        if entry.is_symlink():
            raise subject_error(ErrorCode.STORAGE_IO)
        if entry.is_file() and _REVIEW_PACK_RE.fullmatch(entry.name):
            _verify_review_pack(entry)
            out.append((entry, f"artifacts/{entry.name}"))
    return out


def _collect(subject_id: str, paths: Any) -> tuple[dict[str, Any], list[_Source]]:
    """Enumerate the authoritative snapshot (no files are copied here)."""
    subject_dir = store.subject_dir(subject_id)
    public_root = paths.get_public_outputs_root()
    public_dir = json_store.confined(public_root, public_root / "subjects" / subject_dir.name)
    _assert_tree_safe(subject_dir)
    _assert_tree_safe(public_dir)

    record = _subject_record(subject_id)
    sources: list[_Source] = []
    seen: set[str] = set()

    def add(source: Path, arcname: str, category: str, *, metadata: bool = False) -> None:
        if arcname in seen:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        seen.add(arcname)
        _verify_artifact_file(source)
        if metadata:
            projected = _safe_metadata(json_store.read_object(source, default={}))
            payload = json.dumps(projected, ensure_ascii=False, sort_keys=True).encode("utf-8")
            sources.append(_Source(arcname, source, len(payload), hashlib.sha256(payload).hexdigest(), category, payload))
        else:
            size, digest = _sha256(source)
            sources.append(_Source(arcname, source, size, digest, category))

    # Learning JSON is *not* excluded by a blanket .json rule: these files are
    # the authoritative learner state.
    for child in sorted(subject_dir.iterdir(), key=lambda item: item.name):
        if child.name.startswith(".") or child.is_symlink():
            continue
        if child.is_file() and child.name in {
            "knowledge.json", "wrong_book.json", "exam_points.json", "knowledge_points.json", "profile.json"
        }:
            add(child, f"learning/{child.name}", "learning")
    for child, relative in _iter_regular_files(subject_dir / "materials"):
        add(child, f"learning/materials/{relative.as_posix()}", "learning")
    kb_root = subject_dir / "knowledge_bases"
    ready: dict[str, bool] = {}
    for child, relative in _iter_regular_files(kb_root):
        parts = relative.parts
        metadata = len(parts) == 1 or (len(parts) == 2 and parts[-1] in {"kb_config.json", "metadata.json"})
        if len(parts) > 1:
            kb = kb_root / parts[0]
            if parts[0] not in ready:
                ready[parts[0]] = _kb_index_ready(subject_id, kb)
            # Always retain raw originals; partial/unknown index bytes and
            # their internal state are never labelled a completed snapshot.
            if parts[1] != "raw" and not metadata and not ready[parts[0]]:
                continue
        if metadata and child.suffix != ".json":
            continue
        add(child, f"learning/knowledge_bases/{relative.as_posix()}", "learning", metadata=metadata)

    for source, arcname in _report_artifacts(public_dir):
        add(source, arcname, "artifact")
    for source, arcname in _review_pack_artifacts(public_dir):
        add(source, arcname, "artifact")

    # Subject.json is generated, so its bytes are represented by the registry
    # projection and its hash is computed from the file written into staging.
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    sources.insert(
        0,
        _Source(
            SUBJECT_NAME,
            None,
            len(payload),
            hashlib.sha256(payload).hexdigest(),
            "subject_metadata",
        ),
    )
    return record, sources


def _kb_index_ready(subject_id: str, kb: Path) -> bool:
    from deeptutor.subjects import material_manifest, uploads

    status = uploads.read_kb_status(kb.parent, kb.name)
    local = [json_store.read_object(kb / name, default={}) for name in ("kb_config.json", "metadata.json")]
    statuses = [item.get("status") for item in local if item.get("status")]
    if status:
        statuses.append(status.get("status"))
    if not statuses or any(item != "ready" for item in statuses):
        return False
    state = material_manifest.load_index_state(kb, subject_id=subject_id, kb_name=kb.name)
    if state is not None:
        projection = material_manifest.project_status(
            kb_dir=kb, raw_dir=kb / "raw", materials_dir=None, subject_id=subject_id,
            kb_name=kb.name, manager_status=status or {"status": "ready"}, verify_hashes=True)
        return projection["status"] == "ready"
    return True  # Legacy ready evidence; no new ready marker is fabricated.


def _snapshot_stable(before: list[_Source], after: list[_Source]) -> bool:
    def key(source: _Source) -> tuple[str, int, str, str]:
        return (source.zip_path, source.size, source.sha256, source.category)

    return [key(item) for item in before if item.source is not None] == [
        key(item) for item in after if item.source is not None
    ]


def _write_manifest(content: Path, record: dict[str, Any], sources: list[_Source], export_id: str) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "export_id": export_id,
        "subject": record,
        "files": [source.contract() for source in sources],
        "exclusions": list(EXCLUSIONS),
    }
    json_store.atomic_write_object(content / MANIFEST_NAME, manifest)
    return manifest


def _copy_sources(
    content: Path,
    sources: list[_Source],
    record: dict[str, Any],
) -> None:
    for source in sources:
        target = json_store.confined(content, content / source.zip_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.source is None or source.payload is not None:
            data = source.payload if source.payload is not None else json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
            with target.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            continue
        try:
            src_fd = os.open(source.source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(src_fd, "rb") as src, target.open("xb") as dst:
                if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                    raise subject_error(ErrorCode.STORAGE_IO)
                digest = hashlib.sha256()
                size = 0
                for block in iter(lambda: src.read(1 << 20), b""):
                    dst.write(block)
                    digest.update(block)
                    size += len(block)
                dst.flush()
                os.fsync(dst.fileno())
        except OSError as exc:
            raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        if size != source.size or digest.hexdigest() != source.sha256:
            raise SnapshotChanged("source changed while copying")


def _zip_content(content: Path, zip_path: Path) -> None:
    files = sorted(
        (path for path in content.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(content).as_posix(),
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(content).as_posix())


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    with archive.open(name) as handle:
        return handle.read()


def _verify_zip(zip_path: Path, manifest: dict[str, Any]) -> None:
    """Independent re-read: names, CRC, every size/hash, and complete coverage."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("CRC failure")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate entries")
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or "\\" in name:
                    raise ValueError("unsafe entry")
            stored_manifest = json.loads(_read_zip_member(archive, MANIFEST_NAME).decode("utf-8"))
            if stored_manifest != manifest:
                raise ValueError("manifest mismatch")
            expected = {entry["path"]: entry for entry in manifest["files"]}
            if set(names) - {MANIFEST_NAME} != set(expected) or MANIFEST_NAME in expected:
                raise ValueError("coverage mismatch")
            for path, entry in expected.items():
                if archive.getinfo(path).file_size != entry["size"]:
                    raise ValueError("file size mismatch")
                digest = hashlib.sha256()
                size = 0
                with archive.open(path) as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        size += len(block)
                        if size > entry["size"]:
                            raise ValueError("file size overflow")
                        digest.update(block)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("file hash mismatch")
    except SubjectOperationError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable archive is corruption
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc


def prepare_export_bundle(subject_id: str) -> PreparedExport:
    """Build a private, verified ZIP while holding the exclusive subject lease."""
    if not isinstance(subject_id, str) or not store.is_valid_subject_id(subject_id):
        raise store.InvalidSubjectIdError(subject_id)
    lease = subject_operations.acquire_activity(
        subject_id, mode=subject_operations.EXCLUSIVE, kind="export"
    )
    staging_root: Path | None = None
    owned = False
    try:
        # Re-check registration only after the exclusive gate is held: a delete
        # that won the race must not leave an unknown subject being exported.
        if store.get_subject(subject_id) is None:
            raise subject_error(ErrorCode.SUBJECT_NOT_FOUND)
        paths = store.current_subject_paths()
        root = paths.get_public_outputs_root()
        json_store.ensure_trusted_root(root)
        export_id = uuid.uuid4().hex
        stage_parent = json_store.confined(root, root / STAGING_DIRNAME)
        if stage_parent.is_symlink():
            raise subject_error(ErrorCode.STORAGE_IO)
        json_store.make_directory(stage_parent)
        try:
            os.chmod(stage_parent, 0o700)
        except OSError:  # pragma: no cover - exotic filesystem
            pass
        staging_root = json_store.confined(stage_parent, stage_parent / export_id)
        json_store.make_directory(staging_root, exist_ok=False)
        owned = True
        content = json_store.confined(staging_root, staging_root / "content")
        json_store.make_directory(content)
        zip_path = json_store.confined(staging_root, staging_root / f"subject-export-{export_id}.zip")

        subject_dir = store.subject_dir(subject_id)
        public_dir = json_store.confined(
            root, root / "subjects" / subject_dir.name
        )
        last_change: SnapshotChanged | None = None
        for attempt in range(2):
            if attempt:
                for child in list(staging_root.iterdir()):
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
                json_store.make_directory(content)
            try:
                with json_store.json_transaction(subject_dir):
                    record, sources = _collect(subject_id, paths)
                    _copy_sources(content, sources, record)
                after_record, after_sources = _collect(subject_id, paths)
                if after_record != record or not _snapshot_stable(sources, after_sources):
                    raise SnapshotChanged("source set changed during snapshot")
                manifest = _write_manifest(content, record, sources, export_id)
                _zip_content(content, zip_path)
                _verify_zip(zip_path, manifest)
                # Snapshot cleanup can remove millions of files. Finish it in
                # this worker before the live request commits the single ZIP;
                # the event-loop commit then cleans only its one private link.
                shutil.rmtree(content)
                public_path = json_store.confined(
                    public_dir,
                    public_dir / f"subject-export-{export_id}.zip",
                )
                return PreparedExport(
                    export_id=export_id,
                    staging_root=staging_root,
                    zip_path=zip_path,
                    public_path=public_path,
                    manifest=manifest,
                    lease=lease,
                )
            except SnapshotChanged as exc:
                last_change = exc
                continue
        raise subject_error(ErrorCode.STORAGE_IO, cause=last_change)
    except BaseException:
        if owned and staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        lease.release()
        raise


def _require_prepared(prepared: PreparedExport) -> None:
    """Validate ownership before any cleanup, release, mkdir or publication."""
    sid = prepared.manifest.get("subject", {}).get("id")
    subject_operations.require_activity(prepared.lease, sid, mode=subject_operations.EXCLUSIVE)
    root = store.current_subject_paths().get_public_outputs_root()
    if not _EXPORT_ID_RE.fullmatch(prepared.export_id):
        raise json_store.invalid_input("导出标识无效")
    staging = root / STAGING_DIRNAME / prepared.export_id
    name = f"subject-export-{prepared.export_id}.zip"
    if (prepared.staging_root != staging or prepared.zip_path != staging / name
            or prepared.public_path != root / "subjects" / sid / name):
        raise json_store.invalid_input("导出准备不属于当前用户和科目")
    json_store.confined(root, staging)


def discard_export_bundle(prepared: PreparedExport) -> None:
    """Remove only this preparation's private tree and release its lease."""
    _require_prepared(prepared)
    try:
        root = prepared.staging_root
        if root.exists() and root.is_dir() and not root.is_symlink():
            shutil.rmtree(root, ignore_errors=True)
    finally:
        prepared.release()


def commit_export_bundle(prepared: PreparedExport) -> dict[str, Any]:
    """Publish one prepared ZIP after the live caller resumes; never overwrite."""
    _require_prepared(prepared)
    published = False
    try:
        if not prepared.lease.active:
            raise subject_error(ErrorCode.STORAGE_IO)
        if store.get_subject(prepared.manifest["subject"]["id"]) is None:
            raise subject_error(ErrorCode.SUBJECT_NOT_FOUND)
        paths = store.current_subject_paths()
        public_root = paths.get_public_outputs_root()
        json_store.confined(public_root, prepared.zip_path)
        public_dir = prepared.public_path.parent
        json_store.confined(public_root, public_dir)
        json_store.make_directory(public_dir)
        if prepared.public_path.exists() or prepared.public_path.is_symlink():
            raise subject_error(ErrorCode.STORAGE_IO)
        try:
            os.link(prepared.zip_path, prepared.public_path, follow_symlinks=False)
            published = True
        except OSError as exc:
            raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        size = prepared.public_path.stat().st_size
        return {
            "export_id": prepared.export_id,
            "schema_version": SCHEMA_VERSION,
            "zip_path": prepared.public_path,
            "manifest": prepared.manifest,
            "size": size,
        }
    except BaseException:
        if published:
            try:
                prepared.public_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(prepared.staging_root, ignore_errors=True)
        prepared.release()


def export_subject_bundle(subject_id: str) -> dict[str, Any]:
    """Synchronous Appendix-A helper: prepare + commit in one call."""
    prepared = prepare_export_bundle(subject_id)
    return commit_export_bundle(prepared)


__all__ = [
    "EXCLUSIONS",
    "PreparedExport",
    "SCHEMA_VERSION",
    "commit_export_bundle",
    "discard_export_bundle",
    "export_subject_bundle",
    "prepare_export_bundle",
]
