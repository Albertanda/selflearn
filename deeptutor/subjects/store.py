"""Subject-scoped data layer (M1).

Each subject owns its own data tree under ``data/subjects/<id>/``:

    data/subjects/
        index.json              # subject registry (id, name, term, ...)
        <id>/
            knowledge.json      # knowledge-base records for this subject
            materials/<type>/   # uploaded raw files (textbook/ppt/board/...)
            knowledge_bases/    # LlamaIndex KB trees (one per record)

The model configuration stays global; only learner data is subject-scoped.

Storage rules (C01)
-------------------
* Every read goes through :mod:`deeptutor.subjects.json_store`, so a damaged
  ``index.json``/``knowledge.json`` raises instead of looking like an empty
  registry — otherwise the next ``create_subject`` would overwrite it.
* Every read-modify-write runs inside one lock: the registry has its own lock
  and each subject has its own, so creating a subject never races another
  create, and two subjects never block each other.
* Paths are resolved through the **current user's** ``PathService`` and then
  checked against that anchor: the subjects root itself may not be a symlink,
  an id is validated as a whole string, and the resolved path must still sit
  inside this user's subject root. A subject/KB/material symlink pointing at
  another subject, another user or the admin tree is refused **before** it is
  read, created or locked.
* Addressing a subject that is not in the current user's registry is a
  ``subject_not_found`` (404), not an implicit "create it" — writing learner
  data must not bring a subject tree into existence.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import stat
import time
import uuid

from deeptutor.services.path_service import PathService
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import (
    ERROR_SPECS,
    ErrorCode,
    StorageIOError,
    SubjectOperationError,
)

SUBJECTS_ROOT_NAME = "subjects"

#: Subject ids come from :func:`slugify`, which keeps ASCII alphanumerics and
#: CJK ideographs and collapses everything else to ``-``. The pattern accepts
#: CJK because an ASCII-only class rejects every Chinese subject name.
#:
#: It is matched with :func:`re.fullmatch`, not ``^...$``: in Python ``$`` also
#: matches *just before* a trailing newline, so ``"math\\n"`` used to pass
#: validation and produce a directory name with an embedded newline.
_SUBJECT_ID_RE = re.compile(r"[a-z0-9\u4e00-\u9fff][a-z0-9\u4e00-\u9fff-]{0,63}")

_INDEX_NAME = "index.json"
_KNOWLEDGE_NAME = "knowledge.json"
_SUBJECT_SUBDIRS = ("materials", "knowledge_bases")


class InvalidSubjectIdError(SubjectOperationError):
    """An id that is not a plain slug (C02 ``invalid_subject_id``, 400).

    This is *not* storage corruption: nothing on disk is wrong, the caller
    supplied something that cannot be a single path segment. A named domain
    error keeps it out of the generic ``ValueError`` route, which the mapper
    treats as an unknown internal failure.
    """

    def __init__(self, subject_id: object = None, *, cause: BaseException | None = None) -> None:
        spec = ERROR_SPECS[ErrorCode.INVALID_SUBJECT_ID]
        self.subject_id = subject_id
        super().__init__(
            spec.code,
            spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )


class SubjectNotFoundError(SubjectOperationError):
    """The id is well-formed but is not in the current user's registry (404)."""

    def __init__(self, subject_id: object = None, *, cause: BaseException | None = None) -> None:
        spec = ERROR_SPECS[ErrorCode.SUBJECT_NOT_FOUND]
        self.subject_id = subject_id
        super().__init__(
            spec.code,
            spec.message,
            http_status=spec.http_status,
            retryable=spec.retryable,
            cause=cause,
        )


def is_valid_subject_id(subject_id: str) -> bool:
    """Whether *subject_id* is safe to use as a single path segment.

    Validated against the **whole** string: a trailing LF/CRLF/space, a path
    separator, a percent escape or a non-string all fail. Callers must not
    "clean up" an id — an id that is not already a plain slug is rejected.
    """
    if not isinstance(subject_id, str):
        return False
    return _SUBJECT_ID_RE.fullmatch(subject_id) is not None


def current_subject_paths() -> PathService:
    """The **current user's** ``PathService``, resolved strictly (C01).

    :func:`deeptutor.services.path_service.get_path_service` wraps this in a
    ``try/except`` that falls back to the default (admin) instance. That is the
    right thing for best-effort display paths and exactly the wrong thing for
    learner data: if the current scope cannot be resolved, subject storage must
    fail loudly rather than quietly read or write the administrator's tree.

    Every subject/output helper in this module resolves through here.
    """
    from deeptutor.multi_user.paths import get_current_path_service

    service = get_current_path_service()
    if service is None:  # pragma: no cover - defensive
        raise StorageIOError("无法解析当前用户的科目数据根，已拒绝访问。")
    return service


def _required_text(value: object, what: str) -> str:
    """A caller-supplied required string (blank/non-string -> invalid_input)."""
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    cleaned = value.strip()
    if not cleaned:
        raise json_store.invalid_input(f"{what}不能为空")
    return cleaned


def _optional_text(value: object, what: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    return value.strip()


def subjects_root() -> Path:
    """Root of the current user's subject tree (``.../workspace/subjects``).

    Validated **before** it is created: if ``subjects`` is a symlink, whatever
    it points at is not this user's registry, so the call fails instead of
    reading or writing the target.
    """
    workspace = current_subject_paths().get_workspace_dir()
    json_store.ensure_trusted_root(workspace)
    root = workspace / SUBJECTS_ROOT_NAME
    if root.is_symlink():
        raise StorageIOError(
            "科目根目录是符号链接，已拒绝访问。", path=SUBJECTS_ROOT_NAME
        )
    if root.exists() and not root.is_dir():
        raise StorageIOError("科目根路径不是目录。", path=SUBJECTS_ROOT_NAME)
    json_store.make_directory(root)
    # Re-check after creating: the same path must still be a real directory
    # inside this user's workspace, not a target that appeared in between.
    json_store.confined(workspace, root)
    if root.is_symlink():  # pragma: no cover - defensive
        raise StorageIOError("科目根目录是符号链接，已拒绝访问。", path=SUBJECTS_ROOT_NAME)
    return root


def _subject_dir_unchecked(subject_id: str) -> Path:
    """The subject's directory without requiring a registry entry.

    Only the create/delete flows may use this: creating prepares a tree that is
    not registered *yet*, and deleting must still find the tree after the entry
    is gone.
    """
    if not is_valid_subject_id(subject_id):
        raise InvalidSubjectIdError(subject_id)
    root = subjects_root()
    return json_store.confined(root, root / subject_id)


def subject_dir(subject_id: str) -> Path:
    """The data directory for one subject in the current user's registry.

    Raises an explicit error for an id that is not a plain slug, for a path
    that resolves outside this user's subject root, and for a well-formed id
    that is simply not registered (404) — writing learner data must never bring
    a subject tree into existence.
    """
    path = _subject_dir_unchecked(subject_id)
    if not _is_registered(subject_id):
        raise SubjectNotFoundError(subject_id)
    return path


def subject_data_path(subject_id: str, name: str) -> Path:
    """A confined data file for *subject_id* (validation before any read).

    This is the single entry point the collection modules use for their JSON
    files, so a symlinked ``wrong_book.json`` is refused before it is opened
    rather than after the other subject's bytes have been read.
    """
    directory = subject_dir(subject_id)
    return json_store.confined(directory, directory / json_store.safe_segment(name))


@contextmanager
def subject_transaction(subject_id: str, *, directory: Path):
    """Learning writes take activity before JSON locks and recheck identity."""
    from deeptutor.subjects import subject_operations

    with subject_operations.acquire_activity(subject_id, kind="learning-write"):
        current = subject_dir(subject_id)
        if current != directory:
            raise json_store.invalid_input("学习记录目录不属于当前科目")
        with json_store.json_transaction(current) as tx:
            yield tx


def _index_path() -> Path:
    root = subjects_root()
    return json_store.confined(root, root / _INDEX_NAME)


def _knowledge_path(subject_id: str, *, require_registered: bool = True) -> Path:
    directory = (
        subject_dir(subject_id) if require_registered else _subject_dir_unchecked(subject_id)
    )
    return json_store.confined(directory, directory / _KNOWLEDGE_NAME)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def _validate_registry(records: list[dict], source: Path) -> list[dict]:
    """Check the registry fields this module actually uses.

    Required: a valid slug ``id`` and a non-empty ``name``. Optional fields
    keep a definite default (``description``/``term`` -> ``""``) and unknown
    keys are preserved. A record is never skipped: a bad entry makes the whole
    registry corrupt, so no creation can proceed on top of it.
    """
    for index, record in enumerate(records):
        subject_id = record.get("id")
        if not is_valid_subject_id(subject_id):
            raise json_store.corrupt_error(
                source.name, "注册项 id 不是合法 slug", index=index
            )
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise json_store.corrupt_error(source.name, "注册项缺少合法名称", index=index)
        for key in ("description", "term"):
            value = record.get(key)
            if key in record and not isinstance(value, str):
                raise json_store.corrupt_error(
                    source.name, f"注册项 {key} 不是字符串", index=index
                )
        created = record.get("created_at")
        if "created_at" in record and (
            isinstance(created, bool) or not isinstance(created, (int, float))
        ):
            raise json_store.corrupt_error(
                source.name, "注册项 created_at 不是数值", index=index
            )
    seen: set[str] = set()
    for index, record in enumerate(records):
        if record["id"] in seen:
            raise json_store.corrupt_error(source.name, "注册项 id 重复", index=index)
        seen.add(record["id"])
    return records


def load_subjects() -> list[dict]:
    """Load the subject registry (``[]`` only when the file is missing)."""
    path = _index_path()
    return _validate_registry(json_store.read_list(path), path)


def _is_registered(subject_id: str) -> bool:
    return any(record.get("id") == subject_id for record in load_subjects())


def _save_subjects(subjects: list[dict]) -> None:
    """Write the registry atomically (used by callers that already hold its lock)."""
    path = _index_path()
    json_store.atomic_write_list(path, subjects)


def slugify(name: str) -> str:
    """Stable id from a Chinese/English subject name."""
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", name.strip().lower()).strip("-")
    if not raw:
        raw = "subject"
    if len(raw) > 40:
        raw = raw[:40].rstrip("-")
    return raw


def _path_taken(root: Path, candidate: str) -> bool:
    """Whether *candidate* already exists on disk (including a dangling link)."""
    path = root / candidate
    return path.exists() or path.is_symlink()


def _unique_subject_id(name: str, existing: list[dict], root: Path) -> str:
    """A free id for *name*, avoiding the registry **and** existing paths.

    An id whose directory already exists is not a free id: that tree is not
    ours, so it is never adopted, overwritten or cleaned.
    """
    taken = {record.get("id") for record in existing}
    base = slugify(name)
    candidate = base
    n = 1
    while candidate in taken or _path_taken(root, candidate):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _initialize_subject_tree(subject_id: str) -> None:
    """Create the subject directory tree and an empty knowledge registry.

    Runs while the registry lock is held and before the registry entry exists,
    so it uses the unchecked path helper — the tree is being created for this
    call and belongs to this call until the entry is committed.
    """
    directory = _subject_dir_unchecked(subject_id)
    for name in _SUBJECT_SUBDIRS:
        sub = json_store.confined(directory, directory / name)
        json_store.make_directory(sub)
    _save_knowledge_records(subject_id, [], require_registered=False)


def _discard_new_tree(directory: Path) -> None:
    """Remove a tree this call just created (never a pre-existing one)."""
    try:
        shutil.rmtree(directory, ignore_errors=True)
    except OSError:  # pragma: no cover - best effort
        pass


def create_subject(name: str, description: str = "", term: str = "") -> dict:
    """Create a subject and its data directory.

    Ordering is deliberate: the id is chosen, the whole tree is **prepared**,
    and only then is the single registry write committed. A preparation failure
    therefore never publishes a registry entry — no "publish, then try to write
    it back" rollback.

    An id whose path already exists is skipped rather than reused, so an
    unregistered orphan tree is neither adopted nor overwritten.
    """
    cleaned_name = _required_text(name, "科目名称")
    cleaned_description = _optional_text(description, "科目描述")
    cleaned_term = _optional_text(term, "学期")

    root = subjects_root()
    with json_store.json_transaction(root) as tx:
        index = tx.path(_INDEX_NAME)
        subjects = _validate_registry(tx.read_list(index), index)
        subject_id = _unique_subject_id(cleaned_name, subjects, root)

        destination = json_store.confined(root, root / subject_id)
        created = False
        try:
            json_store.make_directory(destination, parents=False, exist_ok=False)
            created = True
            _initialize_subject_tree(subject_id)
        except BaseException:
            if created:
                _discard_new_tree(destination)
            raise

        record = {
            "id": subject_id,
            "name": cleaned_name,
            "description": cleaned_description,
            "term": cleaned_term,
            "created_at": int(time.time()),
        }
        try:
            subjects.append(record)
            tx.write_list(index, subjects)
        except BaseException:
            if created:
                _discard_new_tree(destination)
            raise
        return record


def get_subject(subject_id: str) -> dict | None:
    """The registry record for *subject_id*, or ``None`` when unregistered."""
    return next((s for s in load_subjects() if s.get("id") == subject_id), None)


def update_subject(subject_id: str, **fields: str) -> dict | None:
    """Update name/description/term under the registry lock."""
    root = subjects_root()
    with json_store.json_transaction(root) as tx:
        index = tx.path(_INDEX_NAME)
        subjects = _validate_registry(tx.read_list(index), index)
        for subject in subjects:
            if subject.get("id") != subject_id:
                continue
            for key in ("name", "description", "term"):
                value = fields.get(key)
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise json_store.invalid_input(f"{key} 必须是字符串")
                subject[key] = _required_text(value, "科目名称") if key == "name" else value.strip()
            tx.write_list(index, subjects)
            return subject
        return None


def _public_subject_dir_unchecked(subject_id: str) -> Path:
    """The subject's public-output directory, validated against the user root."""
    outputs = current_subject_paths().get_public_outputs_root()
    json_store.ensure_trusted_root(outputs)
    return json_store.confined(outputs, outputs / "subjects" / subject_id)


def _assert_deletable_tree(path: Path, anchor: Path) -> None:
    """Every level must be a real directory/file; no symlink or special node."""
    if path.is_symlink():
        raise StorageIOError("待删除路径是符号链接，已拒绝删除。", path=path.name)
    json_store.confined(anchor, path)
    if not path.exists():
        return
    if not path.is_dir():
        raise StorageIOError("待删除路径不是目录。", path=path.name)
    try:
        def fail_walk(error: OSError) -> None:
            raise error

        for dirpath, dirnames, filenames in os.walk(path, followlinks=False, onerror=fail_walk):
            here = Path(dirpath)
            for name in list(dirnames) + list(filenames):
                full = here / name
                info = full.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise StorageIOError(
                        "待删除树中存在符号链接，已拒绝删除。", path=full.name
                    )
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise StorageIOError(
                        "待删除树中存在非普通文件，已拒绝删除。", path=full.name
                    )
    except StorageIOError:
        raise
    except OSError as exc:
        raise StorageIOError("检查待删除树失败。", cause=exc) from exc


def _remove_tree_strict(path: Path) -> None:
    """Delete exactly one validated tree; every OS error propagates (no ignore)."""
    if path.is_symlink():
        raise StorageIOError("待删除路径是符号链接，已拒绝删除。", path=path.name)
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise StorageIOError("删除科目数据失败。", cause=exc) from exc
    if path.exists() or path.is_symlink():
        raise StorageIOError("删除后路径仍然存在。", path=path.name)


def delete_subject(subject_id: str) -> bool:
    """Delete the current user's learning + public trees, then the registry.

    The exclusive activity lease covers validation, both removals and the
    registry write, so an upload/index/report/review/export cannot be running
    while its subject disappears. Any symlink anywhere in either tree is
    refused *before* the first byte is removed. A partial cleanup is reported
    honestly (``storage_io``) while the registry entry is retained, making a
    later retry possible; this is deliberately not presented as a multi-tree
    crash transaction.
    """
    if not isinstance(subject_id, str) or not is_valid_subject_id(subject_id):
        raise InvalidSubjectIdError(subject_id)
    if get_subject(subject_id) is None:
        return False

    from deeptutor.subjects import subject_operations

    lease = subject_operations.acquire_activity(
        subject_id, mode=subject_operations.EXCLUSIVE, kind="delete"
    )
    try:
        # The mutex is held now: this is the authoritative registration check.
        if get_subject(subject_id) is None:
            return False
        root = subjects_root()
        directory = _subject_dir_unchecked(subject_id)
        public = _public_subject_dir_unchecked(subject_id)
        # Validate both trees *before* deleting either one.
        _assert_deletable_tree(directory, root)
        _assert_deletable_tree(public, current_subject_paths().get_public_outputs_root())
        _remove_tree_strict(directory)
        _remove_tree_strict(public)

        with json_store.json_transaction(root) as tx:
            index = tx.path(_INDEX_NAME)
            subjects = _validate_registry(tx.read_list(index), index)
            if not any(record.get("id") == subject_id for record in subjects):
                return False
            kept = [record for record in subjects if record.get("id") != subject_id]
            tx.write_list(index, kept)
        return True
    finally:
        lease.release()


# ---------------------------------------------------------------------------
# Knowledge-base records
# ---------------------------------------------------------------------------
def _validate_knowledge_records(records: list[dict], source: Path) -> list[dict]:
    """Every record we index by must carry a non-empty string ``kb_name``."""
    for index, record in enumerate(records):
        kb_name = record.get("kb_name")
        if not isinstance(kb_name, str) or not kb_name.strip():
            raise json_store.corrupt_error(
                source.name, "知识库记录缺少合法的 kb_name", index=index
            )
    return records


def load_knowledge_records(subject_id: str) -> list[dict]:
    path = _knowledge_path(subject_id)
    return _validate_knowledge_records(json_store.read_list(path), path)


def _save_knowledge_records(
    subject_id: str, records: list[dict], *, require_registered: bool = True
) -> None:
    path = _knowledge_path(subject_id, require_registered=require_registered)
    json_store.atomic_write_list(path, records)


def get_knowledge_record(subject_id: str, kb_name: str) -> dict | None:
    return next(
        (r for r in load_knowledge_records(subject_id) if r["kb_name"] == kb_name), None
    )


def upsert_knowledge_record(subject_id: str, record: dict) -> None:
    """Insert or update one KB record under the subject lock.

    An update **merges** into the matching record, so fields the caller did not
    supply (including unknown historical ones) survive; only the supplied keys
    are overwritten. Other records are left as they are.
    """
    if not isinstance(record, dict):
        raise json_store.invalid_input("知识库记录必须是对象")
    kb_name = record.get("kb_name")
    if not isinstance(kb_name, str) or not kb_name.strip():
        raise json_store.invalid_input("知识库记录缺少合法的 kb_name")

    directory = subject_dir(subject_id)
    with subject_transaction(subject_id, directory=directory) as tx:
        path = tx.path(_KNOWLEDGE_NAME)
        records = _validate_knowledge_records(tx.read_list(path), path)
        merged: list[dict] = []
        updated = False
        for existing in records:
            if existing["kb_name"] != kb_name:
                merged.append(existing)
                continue
            if updated:
                continue  # collapse duplicates into the first match
            combined = dict(existing)
            combined.update(record)
            merged.append(combined)
            updated = True
        if not updated:
            merged.append(dict(record))
        tx.write_list(path, merged)


def subject_kb_base_dir(subject_id: str) -> Path:
    """LlamaIndex base dir for a subject's knowledge bases.

    The directory is confined **before** it is created: a ``knowledge_bases``
    symlink pointing outside the subject is refused rather than mkdir'd
    through.
    """
    directory = subject_dir(subject_id)
    sub = json_store.confined(directory, directory / "knowledge_bases")
    json_store.make_directory(sub)
    return sub


def materials_dir(subject_id: str, kb_type: str) -> Path:
    """``materials/<type>`` for one subject; *kb_type* must be one segment."""
    segment = json_store.safe_segment(kb_type, what="材料类型")
    directory = subject_dir(subject_id)
    base = json_store.confined(directory, directory / "materials")
    sub = json_store.confined(base, base / segment)
    json_store.make_directory(sub)
    return sub


def new_kb_id() -> str:
    return uuid.uuid4().hex[:12]
