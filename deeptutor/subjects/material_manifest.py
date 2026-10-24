"""Index-source manifest and published-index state for subject KBs (C07).

``materials/<type>`` is the **authoritative** material copy; the KB's ``raw/``
directory is the **indexing source**. This module owns the three facts the
subject layer needs to keep those two honest:

1. which regular, indexable files currently make up ``raw`` (streamed sha256,
   symlinks and non-regular entries refused instead of followed);
2. ``<kb_dir>/subject_sources.json`` — the validated ``MaterialManifest``
   record of the source set the last successful upload published;
3. ``<kb_dir>/subject_index_state.json`` — which source fingerprint the
   *published* index was actually built from, so a stale index can never be
   reported as covering newer material.

Everything here is read-only unless a caller explicitly asks for a write, so
the GET routes can project state without creating a manifest, a task or a
directory. A manifest that exists but is malformed is ``storage_corrupt``: it is
never silently replaced by a freshly computed one, because "we could not read
the record" and "there was no record" must not look the same.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Iterable, Sequence

from deeptutor.services.rag.file_routing import FileTypeRouter
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import StorageCorruptError, StorageIOError

#: Internal source manifest, always written at the **KB root** (never in raw/,
#: where the recursive indexer would collect it).
MANIFEST_NAME = "subject_sources.json"
#: Subject-local record of the source set the published index belongs to.
INDEX_STATE_NAME = "subject_index_state.json"

MANIFEST_SCHEMA_VERSION = 1
INDEX_STATE_SCHEMA_VERSION = 1

_HASH_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_SUBJECT_ID_RE = re.compile(r"\A[a-z0-9\u4e00-\u9fff][a-z0-9\u4e00-\u9fff-]{0,63}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_READ_CHUNK = 1 << 20

#: Fixed, bounded status copy. Projections never echo a provider or OS message.
#:
#: ``status`` answers exactly one question — *does the published index cover the
#: material that is on disk right now?* Busy-ness (a live worker thread, an
#: accepted-but-not-started task) is reported through the separate ``busy`` /
#: ``worker_alive`` / ``queued`` / ``task_id`` fields, so "queued" cannot hide a
#: "your new material is not searchable yet" state from a client.
_STATUS_MESSAGES = {
    "ready": "索引已就绪，可检索当前资料。",
    "rebuilding": "资料已更新，正在重建索引。",
    "stale": "资料与索引源不一致，需要重新建立索引。",
    "error": "上一次索引任务失败，请重试。",
    "initializing": "知识库正在初始化。",
    "unknown": "知识库状态未知。",
}

_STATUS_STAGES = {
    "ready": "completed",
    "rebuilding": "reindexing",
    "stale": "stale",
    "error": "error",
    "initializing": "initializing",
    "unknown": "unknown",
}


def supported_extensions() -> set[str]:
    """The extensions the current engine really indexes (read-only probe)."""
    return set(FileTypeRouter.get_supported_extensions())


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_READ_CHUNK), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _walk_error(error: OSError) -> None:
    raise error


def enumerate_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    digest: bool = True,
) -> list[dict]:
    """Enumerate sources with a typed boundary for filesystem failures."""
    try:
        return _enumerate_files(root, extensions=extensions, digest=digest)
    except OSError as exc:
        raise StorageIOError("索引源读取失败。", path=Path(root).name, cause=exc) from exc


def _enumerate_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    digest: bool = True,
) -> list[dict]:
    """Regular files under *root*, recursive, sorted by relative posix path.

    Symlinks (file or directory) and non-regular entries (fifo/socket/device)
    raise :class:`StorageIOError` **before** anything is read: the subject layer
    must not enumerate — let alone index — whatever they point at. A missing
    directory is an empty list; a path that is not a directory is an error.
    """
    root = Path(root)
    if not root.exists():
        return []
    if root.is_symlink():
        raise StorageIOError("索引源目录是符号链接，已拒绝访问。", path=root.name)
    if not root.is_dir():
        raise StorageIOError("索引源路径不是目录。", path=root.name)

    allowed = {ext.lower() for ext in extensions} if extensions is not None else None
    records: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_walk_error):
        here = Path(dirpath)
        dirnames.sort()
        for name in list(dirnames):
            child = here / name
            if child.is_symlink():
                raise StorageIOError("索引源中包含符号链接，已拒绝访问。", path=name)
        for name in sorted(filenames):
            child = here / name
            if child.is_symlink():
                raise StorageIOError("索引源中包含符号链接，已拒绝访问。", path=name)
            info = os.lstat(child)
            if not stat.S_ISREG(info.st_mode):
                raise StorageIOError("索引源中包含非普通文件，已拒绝访问。", path=name)
            relative = _relative(root, child)
            if allowed is not None:
                if PurePosixPath(relative).suffix.lower() not in allowed:
                    continue
            record = {"path": relative, "size": int(info.st_size)}
            if digest:
                record["sha256"] = _sha256_file(child)
            records.append(record)
    records.sort(key=lambda item: item["path"])
    return records


def source_files(raw_dir: Path, *, digest: bool = True) -> list[dict]:
    """The indexable regular files that currently make up a KB's index source."""
    return enumerate_files(raw_dir, extensions=supported_extensions(), digest=digest)


def fingerprint(records: Sequence[dict]) -> str:
    """Stable digest over ``(path, size, sha256)`` of a source set."""
    payload = [
        [str(item["path"]), int(item["size"]), str(item.get("sha256") or "")]
        for item in sorted(records, key=lambda entry: str(entry["path"]))
    ]
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def shape(records: Sequence[dict]) -> str:
    """Cheap digest over ``(path, size)`` only — used by read-only GETs."""
    payload = [
        [str(item["path"]), int(item["size"])]
        for item in sorted(records, key=lambda entry: str(entry["path"]))
    ]
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _require_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("manifest 路径必须是非空字符串")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # pragma: no cover - defensive
        raise ValueError("manifest 路径必须是合法 UTF-8") from exc
    if _CONTROL_RE.search(value):
        raise ValueError("manifest 路径不能包含控制字符")
    if value.startswith("/") or "\\" in value:
        raise ValueError("manifest 路径必须是相对路径")
    if PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts:
        raise ValueError("manifest 路径不能越出索引源目录")
    if any(part in ("", ".") for part in PurePosixPath(value).parts):
        raise ValueError("manifest 路径必须是规范化的相对路径")
    return value


def build_manifest(*, subject_id: str, kb_name: str, files: Sequence[dict]) -> dict:
    """Assemble and validate a ``MaterialManifest`` payload."""
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "subject_id": subject_id,
        "kb_name": kb_name,
        "files": [
            {"path": str(item["path"]), "size": int(item["size"]), "sha256": str(item["sha256"])}
            for item in files
        ],
    }
    return validate_manifest(manifest, subject_id=subject_id, kb_name=kb_name)


def validate_manifest(payload: Any, *, subject_id: str, kb_name: str) -> dict:
    """Validate a manifest against the frozen schema and the current identity.

    Anything that is not exactly the documented shape — unknown keys, an
    out-of-range version, a ``size`` that is really a ``bool``, a path that
    escapes ``raw``, a duplicate entry, a foreign ``subject_id``/``kb_name`` —
    is a corrupt record (500), never a value to "fix up".
    """
    def corrupt(detail: str) -> StorageCorruptError:
        return json_store.corrupt_error(MANIFEST_NAME, detail)

    if not isinstance(payload, dict):
        raise corrupt("资料清单顶层必须是对象")
    if set(payload) != {"schema_version", "subject_id", "kb_name", "files"}:
        raise corrupt("资料清单字段与 Schema 不一致")
    version = payload.get("schema_version")
    if isinstance(version, bool) or version != MANIFEST_SCHEMA_VERSION:
        raise corrupt("资料清单版本不受支持")
    owner = payload.get("subject_id")
    if not isinstance(owner, str) or not _SUBJECT_ID_RE.match(owner or ""):
        raise corrupt("资料清单 subject_id 非法")
    if owner != subject_id:
        raise corrupt("资料清单不属于当前科目")
    if payload.get("kb_name") != kb_name:
        raise corrupt("资料清单不属于当前知识库")
    files = payload.get("files")
    if not isinstance(files, list):
        raise corrupt("资料清单 files 必须是数组")

    seen: set[str] = set()
    normalized: list[dict] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise json_store.corrupt_error(MANIFEST_NAME, "资料清单条目字段非法", index=index)
        try:
            path = _require_path(item.get("path"))
        except ValueError as exc:
            raise json_store.corrupt_error(MANIFEST_NAME, str(exc), index=index) from None
        if path in seen:
            raise json_store.corrupt_error(MANIFEST_NAME, "资料清单存在重复路径", index=index)
        seen.add(path)
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise json_store.corrupt_error(MANIFEST_NAME, "资料清单 size 非法", index=index)
        digest = item.get("sha256")
        if not isinstance(digest, str) or not _HASH_RE.match(digest):
            raise json_store.corrupt_error(MANIFEST_NAME, "资料清单 sha256 非法", index=index)
        normalized.append({"path": path, "size": size, "sha256": digest})
    normalized.sort(key=lambda item: item["path"])
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "subject_id": owner,
        "kb_name": kb_name,
        "files": normalized,
    }


def manifest_path(kb_dir: Path) -> Path:
    return Path(kb_dir) / MANIFEST_NAME


def index_state_path(kb_dir: Path) -> Path:
    return Path(kb_dir) / INDEX_STATE_NAME


def _read_object(path: Path, *, what: str) -> dict | None:
    """Read one JSON object strictly; ``None`` means **really absent**.

    The S03 reader is reused instead of a new loose one: it opens with
    ``O_NOFOLLOW`` (a symlink — dangling or not — is an error, never "missing"),
    refuses non-regular files without blocking on them, and rejects undecodable
    bytes. Anything that exists but is not a JSON object (``null``, an array, a
    scalar, broken JSON) is corruption: it must never be mistaken for "no
    record", because the caller would then create a fresh one over it.
    """
    path = Path(path)
    text = json_store._read_text(path)
    if text is None:
        return None
    payload = json_store._strict_loads(text, source=path)
    if not isinstance(payload, dict):
        raise json_store.corrupt_error(what, "顶层不是对象")
    return payload


def load_manifest(kb_dir: Path, *, subject_id: str, kb_name: str) -> dict | None:
    """Read the KB's manifest; ``None`` only when the file does not exist."""
    payload = _read_object(manifest_path(kb_dir), what=MANIFEST_NAME)
    if payload is None:
        return None
    return validate_manifest(payload, subject_id=subject_id, kb_name=kb_name)


def save_manifest(kb_dir: Path, manifest: dict) -> None:
    """Atomically publish a manifest at the KB root (outside ``raw/``)."""
    path = manifest_path(kb_dir)
    json_store.make_directory(Path(kb_dir))
    json_store.atomic_write_object(path, manifest)


def _validate_ready_record(value: Any, *, corrupt) -> dict | None:
    """The optional ``last_ready`` snapshot of the last *published* version."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise corrupt("索引状态的 last_ready 非法")
    digest = value.get("fingerprint")
    if not isinstance(digest, str) or not _HASH_RE.match(digest):
        raise corrupt("索引状态的 last_ready fingerprint 非法")
    documents = value.get("documents")
    if isinstance(documents, bool) or not isinstance(documents, int) or documents < 0:
        raise corrupt("索引状态的 last_ready documents 非法")
    record = {
        "fingerprint": digest,
        "documents": documents,
        "task_id": value.get("task_id") if isinstance(value.get("task_id"), str) else None,
        "updated_at": value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
    }
    if value.get("shape") is not None and isinstance(value.get("shape"), str):
        record["shape"] = value["shape"]
    return record


def validate_index_state(payload: Any, *, subject_id: str, kb_name: str) -> dict:
    """Validate the subject-local published-index record."""
    def corrupt(detail: str) -> StorageCorruptError:
        return json_store.corrupt_error(INDEX_STATE_NAME, detail)

    if not isinstance(payload, dict):
        raise corrupt("索引状态必须是对象")
    version = payload.get("schema_version")
    if isinstance(version, bool) or version != INDEX_STATE_SCHEMA_VERSION:
        raise corrupt("索引状态版本不受支持")
    if payload.get("subject_id") != subject_id or payload.get("kb_name") != kb_name:
        raise corrupt("索引状态不属于当前科目或知识库")
    status_value = payload.get("status")
    if status_value not in ("ready", "error"):
        raise corrupt("索引状态取值非法")
    digest = payload.get("fingerprint")
    if not isinstance(digest, str) or not _HASH_RE.match(digest):
        raise corrupt("索引状态 fingerprint 非法")
    cheap = payload.get("shape")
    if not isinstance(cheap, str) or not _HASH_RE.match(cheap):
        raise corrupt("索引状态 shape 非法")
    documents = payload.get("documents")
    if isinstance(documents, bool) or not isinstance(documents, int) or documents < 0:
        raise corrupt("索引状态 documents 非法")
    task_id = payload.get("task_id")
    if task_id is not None and not isinstance(task_id, str):
        raise corrupt("索引状态 task_id 非法")
    state = dict(payload)
    state["last_ready"] = _validate_ready_record(payload.get("last_ready"), corrupt=corrupt)
    return state


def load_index_state(kb_dir: Path, *, subject_id: str, kb_name: str) -> dict | None:
    payload = _read_object(index_state_path(kb_dir), what=INDEX_STATE_NAME)
    if payload is None:
        return None
    return validate_index_state(payload, subject_id=subject_id, kb_name=kb_name)


def save_index_state(kb_dir: Path, state: dict) -> None:
    json_store.make_directory(Path(kb_dir))
    json_store.atomic_write_object(index_state_path(kb_dir), state)


def _by_path(records: Sequence[dict]) -> dict[str, dict]:
    return {str(item["path"]): item for item in records}


def compare_manifest(
    manifest_files: Sequence[dict], actual_files: Sequence[dict], *, verify_hashes: bool = True
) -> dict:
    """Diff a recorded source set against what is on disk right now."""
    recorded = _by_path(manifest_files)
    actual = _by_path(actual_files)
    missing = sorted(set(recorded) - set(actual))
    extra = sorted(set(actual) - set(recorded))
    changed: list[str] = []
    for path in sorted(set(recorded) & set(actual)):
        left, right = recorded[path], actual[path]
        if int(left["size"]) != int(right["size"]):
            changed.append(path)
            continue
        if verify_hashes and right.get("sha256") and left["sha256"] != right["sha256"]:
            changed.append(path)
    return {
        "ok": not (missing or extra or changed),
        "missing": missing,
        "extra": extra,
        "changed": changed,
    }


def _indexable_material_records(material_files: Sequence[dict]) -> list[dict]:
    """Materials entries that could legitimately be an index source.

    Hidden paths (lock files, editor leftovers) and non-indexable extensions
    (the original lecture recording, `*.bak`, images the router cannot parse)
    are not documents and must not be counted or compared as if they were.
    """
    supported = supported_extensions()
    records: list[dict] = []
    for item in material_files:
        path = str(item["path"])
        if path.startswith(".") or "/." in path:
            continue
        if PurePosixPath(path).suffix.lower() not in supported:
            continue
        records.append(item)
    return records


def compare_materials(
    raw_files: Sequence[dict],
    material_files: Sequence[dict],
    *,
    verify_hashes: bool = True,
    compare_extra: bool = True,
) -> dict:
    """Compare the index source with the authoritative materials **both ways**.

    Every index source file must exist in ``materials`` with the same bytes, and
    an indexable material that is missing from ``raw`` is a mismatch too: the
    authoritative copy silently carrying a document the index never saw is
    exactly the "materials 多余但报告 in_sync" failure. Non-indexable and hidden
    material files are outside this comparison (they are not documents).
    """
    # Hidden auxiliary material may be ignored as an *extra*, but a hidden
    # file already present in raw is a real source and still needs its copy.
    authoritative = _by_path(material_files)
    source = _by_path(raw_files)
    missing = sorted(path for path in source if path not in authoritative)
    extra_candidates = _by_path(_indexable_material_records(material_files))
    extra = sorted(path for path in extra_candidates if path not in source) if compare_extra else []
    changed: list[str] = []
    for path, item in source.items():
        counterpart = authoritative.get(path)
        if counterpart is None:
            continue
        if int(counterpart["size"]) != int(item["size"]):
            changed.append(path)
            continue
        if verify_hashes and item.get("sha256") and counterpart.get("sha256"):
            if counterpart["sha256"] != item["sha256"]:
                changed.append(path)
    return {
        "ok": not (missing or extra or changed),
        "missing_in_materials": missing,
        "extra_in_materials": extra,
        "changed_in_materials": sorted(changed),
    }


#: The five C09 coverage fields, in schema order.
IMAGE_COVERAGE_FIELDS = (
    "text_sources",
    "images_seen",
    "images_indexed",
    "images_skipped",
    "skip_reasons",
)

#: The only reasons the public coverage may carry.
PUBLIC_SKIP_REASONS = (
    "parser_no_assets",
    "vision_unavailable",
    "vision_failed",
    "budget",
    "unsupported_image",
)

#: Fixed public copy for a run that did not cover every image. It is derived
#: from the counts (never read back from storage) and is deliberately identical
#: to ``document_loader.IMAGE_COVERAGE_WARNING``; a permanent test keeps the two
#: copies in step.
IMAGE_COVERAGE_WARNING = (
    "本次索引未覆盖文档中的全部图片：部分图片因视觉模型不可用、识别失败、"
    "格式不支持或超出预算被跳过，另有部分文档未能提取到可核实的图片。"
    "这些图片的内容不会出现在检索结果中。"
)


def sanitize_image_coverage(value: Any) -> dict[str, Any] | None:
    """The five-field coverage object, or ``None`` when it is not trustworthy.

    Strict on purpose: booleans, negative or non-integer counts, unknown skip
    reasons, a missing/extra field and a ``seen != indexed + skipped``
    inconsistency all mean "not a valid measurement" — the caller then reports
    *unverified* rather than a fabricated/partial coverage.
    """
    if not isinstance(value, dict) or set(value) != set(IMAGE_COVERAGE_FIELDS):
        return None
    counts: dict[str, Any] = {}
    for name in IMAGE_COVERAGE_FIELDS[:-1]:
        raw = value.get(name)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            return None
        counts[name] = raw
    if counts["images_seen"] != counts["images_indexed"] + counts["images_skipped"]:
        return None
    reasons = value.get("skip_reasons")
    if not isinstance(reasons, dict):
        return None
    clean_reasons: dict[str, int] = {}
    for reason, raw in reasons.items():
        if reason not in PUBLIC_SKIP_REASONS:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            return None
        clean_reasons[reason] = raw
    if sum(count for reason, count in clean_reasons.items() if reason != "parser_no_assets") != counts["images_skipped"]:
        return None
    counts["skip_reasons"] = clean_reasons
    return {name: counts[name] for name in IMAGE_COVERAGE_FIELDS}


def image_coverage_warning(coverage: dict[str, Any] | None) -> str | None:
    """The fixed warning for a coverage that skipped something, else ``None``."""
    if coverage is None:
        return None
    skipped = coverage.get("images_skipped") or 0
    unverified = (coverage.get("skip_reasons") or {}).get("parser_no_assets", 0)
    return IMAGE_COVERAGE_WARNING if (skipped or unverified) else None


def public_image_coverage(manager_status: dict | None) -> tuple[dict | None, str | None]:
    """The safe ``(coverage, warning)`` pair stored for one KB.

    Reads the stable entry field first and falls back to the entry's progress
    snapshot, then re-validates whatever it found: a stored value that does not
    match the contract is reported as *unmeasured*, never echoed, and the
    warning is always derived from the validated counts.
    """
    status = manager_status if isinstance(manager_status, dict) else {}
    coverage = sanitize_image_coverage(status.get("image_coverage"))
    if coverage is None:
        progress = status.get("progress")
        if isinstance(progress, dict):
            coverage = sanitize_image_coverage(progress.get("image_coverage"))
    if coverage is None:
        return None, None
    return coverage, image_coverage_warning(coverage)


def _bounded_progress(status: str, *, percent: int, stage: str) -> dict:
    return {"stage": stage, "message": _STATUS_MESSAGES[status], "percent": percent}


_PUBLIC_REASONS = frozenset({
    "ready", "error", "unknown", "task_failed", "task_incomplete", "kb_not_ready",
    "reservation_incomplete", "manifest_unreadable", "manifest_missing",
    "raw_unreadable", "source_fingerprint_changed", "manifest_drift",
    "materials_unknown", "materials_missing", "materials_unreadable", "materials_drift",
    "state_write_failed", "state_read_failed", "preflight_failed",
})


def _public_reason(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and value in _PUBLIC_REASONS else "unknown"


def project_status(
    *,
    kb_dir: Path,
    raw_dir: Path,
    materials_dir: Path | None,
    subject_id: str,
    kb_name: str,
    manager_status: dict | None,
    worker_alive: bool = False,
    queued: bool = False,
    task_id: str | None = None,
    verify_hashes: bool = False,
) -> dict:
    """Read-only projection of one subject KB's count, source and index state.

    Never writes, never schedules, never consults the auto-registering
    ``list_knowledge_bases``. The returned dict keeps the historical
    ``{status, progress, updated_at}`` shape (plus ``documents``/``task_id``/
    counters) and the ``progress`` payload is rebuilt from fixed copy — the
    global background tasks store raw diagnostics in ``progress``, and those
    must not reach a client.
    """
    raw_files = source_files(raw_dir, digest=verify_hashes)
    documents = len(raw_files)
    manifest = load_manifest(kb_dir, subject_id=subject_id, kb_name=kb_name)
    index_state = load_index_state(kb_dir, subject_id=subject_id, kb_name=kb_name)
    manager_status = manager_status or {}

    if manifest is None:
        # Legacy library: no recorded source identity to compare against. The
        # first successful upload is what establishes a manifest; a GET never
        # writes one.
        manifest_diff: dict = {"ok": True, "legacy": True}
        expected_fingerprint = fingerprint(raw_files) if verify_hashes else None
    else:
        manifest_diff = compare_manifest(
            manifest["files"], raw_files, verify_hashes=verify_hashes
        )
        expected_fingerprint = fingerprint(manifest["files"])

    # materials is the authoritative copy. A *missing* directory while the KB
    # claims sources is a mismatch, not "nothing to compare".
    if materials_dir is None:
        material_diff = (
            {"ok": False, "unverifiable": True}
            if (manifest is not None or raw_files)
            else {"ok": True, "unverifiable": True}
        )
    elif not Path(materials_dir).is_dir():
        material_diff = (
            {"ok": False, "missing_in_materials": sorted(str(i["path"]) for i in raw_files)}
            if (manifest is not None or raw_files)
            else {"ok": True}
        )
    else:
        material_diff = compare_materials(
            raw_files,
            enumerate_files(materials_dir, digest=verify_hashes),
            verify_hashes=verify_hashes,
        )

    in_sync = bool(manifest_diff.get("ok", False)) and bool(material_diff.get("ok", False))
    manager_value = str(manager_status.get("status") or "").lower() or "unknown"
    stored = str((index_state or {}).get("status") or "")
    state_fingerprint = str((index_state or {}).get("fingerprint") or "")
    last_ready = (index_state or {}).get("last_ready") or None
    published = index_state if stored == "ready" else last_ready
    published_matches = bool(
        published and expected_fingerprint and published.get("fingerprint") == expected_fingerprint
    )

    pending = bool(queued or worker_alive)
    manager_error = manager_value in ("error", "failed")
    if not in_sync:
        status = "stale"
    elif stored == "ready" and published_matches:
        # Content identity, not (path, size): a same-size rewrite must not stay
        # "ready" for the new bytes.
        status = "ready"
    elif pending:
        # A task is running or accepted: the index cannot be current yet.
        status = "rebuilding" if (documents or index_state or stored) else "initializing"
    elif stored == "error" or manager_error:
        status = "error"
    elif published is not None:
        # A published index exists but belongs to an older source set.
        status = "stale"
    elif index_state is None and manifest is None and manager_value in ("ready", "completed"):
        # A legacy library whose published index was ready before this stage:
        # there is no recorded source change to contradict it.
        status = "ready"
    elif documents or manager_value in ("ready", "completed", "initializing", "processing"):
        status = "rebuilding"
    else:
        status = "initializing"

    percent = {"ready": 100, "error": 0}.get(status, 0)
    stage = _STATUS_STAGES[status]

    coverage, coverage_warning = public_image_coverage(manager_status)
    projection: dict[str, Any] = {
        "status": status,
        "progress": _bounded_progress(status, percent=percent, stage=stage),
        "updated_at": manager_status.get("updated_at"),
        "documents": documents,
        "materials_in_sync": in_sync,
        "busy": pending,
        "worker_alive": bool(worker_alive),
        "queued": bool(queued),
        # The measured image coverage of the run that produced this state, and
        # the fixed degradation warning. Not measured = None, never zeros.
        "image_coverage": coverage,
        "image_coverage_warning": coverage_warning,
    }
    if task_id:
        projection["task_id"] = task_id
    if index_state is not None:
        projection["indexed_documents"] = int(index_state.get("documents", 0))
        projection["index_sources"] = "ready" if status == "ready" else "stale"
    else:
        projection["index_sources"] = "unknown"
    # The current index version and the newest attempt are separate facts: a
    # failed task must be visible without erasing the last published version.
    projection["published_source"] = (
        {
            "documents": int(published.get("documents", 0)),
            "task_id": published.get("task_id"),
            "updated_at": published.get("updated_at"),
            "matches_current": published_matches,
        }
        if published is not None
        else None
    )
    projection["last_attempt"] = (
        {
            "status": stored or None,
            "task_id": (index_state or {}).get("task_id"),
            "reason": _public_reason((index_state or {}).get("reason")),
            "updated_at": (index_state or {}).get("updated_at"),
            "matches_current": bool(state_fingerprint and state_fingerprint == expected_fingerprint),
        }
        if index_state is not None
        else None
    )
    if not manifest_diff.get("ok", True):
        projection["source_drift"] = {
            "missing": manifest_diff.get("missing", []),
            "extra": manifest_diff.get("extra", []),
            "changed": manifest_diff.get("changed", []),
        }
    if not material_diff.get("ok", True):
        projection["materials_drift"] = {
            "missing": material_diff.get("missing_in_materials", []),
            "extra": material_diff.get("extra_in_materials", []),
            "changed": material_diff.get("changed_in_materials", []),
            "unverifiable": bool(material_diff.get("unverifiable", False)),
        }
    if expected_fingerprint is not None:
        projection["current_fingerprint"] = expected_fingerprint
    return projection


def documents_count(raw_dir: Path) -> int:
    """How many indexable regular source files ``raw`` currently holds."""
    return len(source_files(raw_dir, digest=False))


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "INDEX_STATE_NAME",
    "INDEX_STATE_SCHEMA_VERSION",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA_VERSION",
    "build_manifest",
    "compare_manifest",
    "compare_materials",
    "documents_count",
    "enumerate_files",
    "fingerprint",
    "index_state_path",
    "load_index_state",
    "load_manifest",
    "manifest_path",
    "project_status",
    "save_index_state",
    "save_manifest",
    "shape",
    "source_files",
    "supported_extensions",
    "utc_now",
    "validate_index_state",
    "validate_manifest",
]
