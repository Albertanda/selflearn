"""Subject-scoped knowledge-base references — codec + read-only resolver (P1-20).

Two libraries can carry the *same* disk name in three places at once: subject A,
subject B and the global (admin/user) workspace. A bare ``kb_name`` therefore
cannot identify a library on its own, and C08 fixes the wire identity:

    subject:kb:<subject_id>:<kb_name>

This module owns both halves of that contract:

* :func:`encode_subject_kb_ref` / :func:`decode_subject_kb_ref` — the codec.
  The disk name is never rewritten: the *only* transformation is joining the two
  validated segments, so a Chinese or mixed-case identity round-trips exactly.
* :func:`resolve_kb_ref` — the single resolver every consumer (rag tool,
  ``kb_files``, chat mounting, the agentic pipeline) goes through, so
  "authorized", "exists" and "ready" mean the same thing everywhere.

Deliberate properties:

* **Read-only.** It uses ``uploads.kb_base_path``/``kb_paths(create=False)`` and
  ``json_store`` confinement; ``store.subject_kb_base_dir()`` is never used
  because it ``mkdir``'s. Resolving must not create a KB, a manager, a lock or a
  config migration, and must not hash every document.
* **Server-owned paths.** ``base_dir`` stays inside the resolved resource. It is
  never part of a model schema, a public message or a source metadata block
  (:meth:`ResolvedSubjectKb.public_dict` cannot emit it).
* **Honest readiness.** Ready is derived from the same source/index projection
  S05/S06 already use (:func:`deeptutor.subjects.material_manifest.project_status`)
  — never from a registry flag alone. A missing or unknown status is not ready.
* **No fallback.** A rejected subject reference never degrades into a same-named
  global library, and a bare name is only accepted when a *unique* mounted
  resource matches it. ``mounted_refs=None`` (legacy, no turn scope) and
  ``mounted_refs=[]`` (this turn mounts nothing) are different requests.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from deeptutor.services.rag.kb_paths import resolve_kb_dir
from deeptutor.services.rag.provider_binding import resolve_bound_provider
from deeptutor.subjects import json_store, store, uploads
from deeptutor.subjects import material_manifest as manifest_mod
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error

#: Wire prefix of a subject KB reference.
SUBJECT_KB_PREFIX = "subject:kb:"
#: Existing global (non-subject) wire prefixes; their authorization and audit
#: semantics stay with :mod:`deeptutor.multi_user.knowledge_access`.
ADMIN_KB_PREFIX = "admin:kb:"
USER_KB_PREFIX = "user:kb:"
GLOBAL_KB_PREFIXES = (ADMIN_KB_PREFIX, USER_KB_PREFIX)

#: Path of ``kb_config.json`` inside a KB base directory.
KB_CONFIG_NAME = "kb_config.json"

#: Internal tool arguments that decide *which* library a call reads. The chat
#: pipeline deletes every one of them from a model-supplied argument dict and
#: writes the trusted values itself, so a model cannot redirect retrieval (C08:
#: the gate lives at the execution end, not in the schema).
SCOPE_KWARGS = (
    "kb_base_dir",
    "base_dir",
    "kb_dir",
    "provider",
    "expected_subject_id",
    "mounted_refs",
    "_mounted_refs",
    "subject_id",
    "_subject_id",
    "_kb_scope",
)

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Resolved resource
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ResolvedSubjectKb:
    """One authorized library, ready to hand to a service.

    ``base_dir`` is the server-side KB root (the directory that *contains* the
    KB folders) and never leaves the server. ``status`` is the projected
    source/index state observed while resolving (``""`` when readiness was not
    requested).
    """

    kb_ref: str
    name: str
    base_dir: Path
    subject_id: str | None
    read_only: bool
    provider: str
    status: str = ""

    @property
    def is_subject(self) -> bool:
        """Whether this resource belongs to a subject tree (not global)."""
        return self.subject_id is not None

    @property
    def kb_dir(self) -> Path:
        """The directory holding this KB's index (linked KBs resolve too)."""
        return resolve_kb_dir(self.base_dir, self.name)

    def public_dict(self) -> dict[str, Any]:
        """The safe projection: no host path, no cache directory, no key."""
        return {
            "kb_ref": self.kb_ref,
            "name": self.name,
            "subject_id": self.subject_id,
            "read_only": self.read_only,
            "provider": self.provider,
        }


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------
def is_valid_kb_name(name: object) -> bool:
    """Whether *name* can be one segment of a wire ref and of a path.

    Stricter than :func:`json_store.safe_segment` in exactly the ways the wire
    format requires: no colon (the separator), no control characters, no
    leading/trailing whitespace and no ``.``/``..``. Case, language and inner
    spaces are *not* touched — the stored identity is used verbatim.
    """
    if not isinstance(name, str) or not name:
        return False
    if name != name.strip():
        return False
    if name in (".", ".."):
        return False
    if ":" in name or "/" in name or "\\" in name:
        return False
    if _CONTROL_RE.search(name):
        return False
    return True


def encode_subject_kb_ref(subject_id: str, kb_name: str) -> str:
    """``subject:kb:<subject_id>:<kb_name>`` — the only place the wire id is built.

    Both segments are validated with the existing S03 rules (a Chinese subject
    slug stays legal, and the KB's disk name is not modified in any way).
    """
    if not store.is_valid_subject_id(subject_id):
        raise json_store.invalid_input("科目标识非法")
    if not is_valid_kb_name(kb_name):
        raise json_store.invalid_input("知识库名称非法")
    return f"{SUBJECT_KB_PREFIX}{subject_id}:{kb_name}"


def is_subject_kb_ref(kb_ref: object) -> bool:
    return isinstance(kb_ref, str) and kb_ref.startswith(SUBJECT_KB_PREFIX)


def decode_subject_kb_ref(kb_ref: str) -> tuple[str, str] | None:
    """Decode a subject wire ref, or ``None`` when it is not one.

    A value that *is* prefixed but malformed (extra separators, an invalid slug,
    a traversal attempt, a control character) raises ``invalid_input`` instead of
    being coerced: silently repairing a bad identity is how two libraries end up
    being confused for one another.
    """
    if not is_subject_kb_ref(kb_ref):
        return None
    body = kb_ref[len(SUBJECT_KB_PREFIX) :]
    subject_id, separator, kb_name = body.partition(":")
    if not separator or ":" in kb_name:
        raise json_store.invalid_input("知识库引用格式非法")
    if not store.is_valid_subject_id(subject_id) or not is_valid_kb_name(kb_name):
        raise json_store.invalid_input("知识库引用格式非法")
    return subject_id, kb_name


def normalize_kb_ref(kb_ref: object) -> str:
    """The comparison form of a reference (outer whitespace only).

    ``"  subject:kb:a:x "`` and ``"subject:kb:a:x"`` are the same request;
    ``"Subject:KB:a:x"`` is not (case is part of an identity).
    """
    if not isinstance(kb_ref, str):
        raise json_store.invalid_input("知识库引用必须是字符串")
    return kb_ref.strip()


def _ref_name(kb_ref: str) -> str:
    """The *name* segment of any reference form, without resolving it."""
    decoded = decode_subject_kb_ref(kb_ref)
    if decoded is not None:
        return decoded[1]
    for prefix in GLOBAL_KB_PREFIXES:
        if kb_ref.startswith(prefix):
            return kb_ref[len(prefix) :]
    return kb_ref


def _ref_kind(kb_ref: str) -> str:
    if is_subject_kb_ref(kb_ref):
        return "subject"
    for prefix in GLOBAL_KB_PREFIXES:
        if kb_ref.startswith(prefix):
            return "global"
    return "bare"


def _global_resource_id(kb_ref: str) -> str:
    """The *authorized* resource id behind a global reference.

    ``admin:kb:x`` and ``user:kb:x`` are two different resources for an ordinary
    learner (their own library and one assigned to them) that may share a name —
    so a prefix-stripped string is not an identity. Resolving through the
    multi-user seam returns the real resource id, which is what the mounted-set
    comparison must use. The one legitimate alias case is preserved: for an
    administrator both spellings resolve to the same admin library, and then the
    two ids are equal.

    An unresolvable entry keeps its literal spelling as its identity, so it can
    never accidentally match a different resource (and never raises here: this is
    a comparison, not an authorization decision — the resolver still runs on the
    reference the caller actually asked for).
    """
    from deeptutor.multi_user.knowledge_access import resolve_for_rag

    try:
        resource = resolve_for_rag(kb_ref)
    except Exception:
        return kb_ref
    if resource is None:
        return kb_ref
    return str(resource.id)


def _mounted_identity(ref: str) -> tuple[str, str, str]:
    """What a mounted entry denotes, for ambiguity detection.

    A subject reference is identified by its subject *and* name; a global
    reference by the **real resolved resource id** (never by a stripped prefix),
    because a user's own ``x`` and an assigned admin ``x`` are different
    libraries. Two different resources sharing a name must never be guessed
    between; two spellings of one resource are one identity.
    """
    decoded = decode_subject_kb_ref(ref)
    if decoded is not None:
        return ("subject", decoded[0], decoded[1])
    if _ref_kind(ref) == "global":
        return ("global", "", _global_resource_id(ref))
    # A bare mounted entry denotes the global library the historical resolver
    # answers for it (that is how the runtime mounts an explicit learner
    # selection); when it resolves to nothing it stays a bare identity so it
    # cannot alias a different resource.
    resolved = _global_resource_id(ref)
    if resolved != ref:
        return ("global", "", resolved)
    return ("bare", "", _ref_name(ref))


def _unique_mounted_match(ref: str, mounted: Sequence[str]) -> str | None:
    """The one mounted resource a bare *ref* names; ``None`` when none matches.

    Spellings of the *same* resource are not an ambiguity (a bare name plus its
    explicit wire id, or an administrator's alias, denotes one library): the
    explicit wire spelling is preferred so the mounted set keeps a canonical
    identity. Distinct resources sharing a name — a subject library and a global
    one, or ``user:kb:x`` and ``admin:kb:x`` — are an ambiguity, and the caller
    gets ``invalid_input`` rather than a guess.
    """
    name = _ref_name(ref)
    if not is_valid_kb_name(name):
        raise json_store.invalid_input("知识库名称非法")
    matches = [entry for entry in mounted if _ref_name(entry) == name]
    if not matches:
        return None
    identities = {_mounted_identity(entry) for entry in matches}
    if len(identities) > 1:
        raise json_store.invalid_input("知识库名称在本轮挂载中不唯一")
    for entry in matches:
        if _ref_kind(entry) == "global":
            return entry
    return matches[0]


# ---------------------------------------------------------------------------
# Read-only status of a subject KB
# ---------------------------------------------------------------------------
def _kb_config_payload(subject_id: str) -> dict[str, Any]:
    """``kb_config.json`` of one subject, strictly read and never migrated."""
    base = uploads.kb_base_path(subject_id)
    return json_store.read_object(Path(base) / KB_CONFIG_NAME, default={})


def confined_kb_dir(subject_id: str, kb_name: str) -> Path:
    """``<subject>/knowledge_bases/<kb_name>``, refused before it is read.

    The leaf is confirmed to be a real directory inside the subject's own KB
    root: a symlinked (or dangling) ``<kb_name>`` reports a storage error instead
    of being walked into another library, and a ``kb_config`` pointer to an
    external index is refused exactly like
    :func:`deeptutor.subjects.uploads.kb_paths` refuses it for writes.
    """
    base = uploads.kb_base_path(subject_id)
    segment = json_store.safe_segment(kb_name, what="知识库名称")
    kb_dir = json_store.confined(base, base / segment)
    linked = resolve_kb_dir(base, kb_name)
    if os.path.normpath(str(linked)) != os.path.normpath(str(kb_dir)):
        raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
    return kb_dir


#: Recorded manager states that make a library unusable even when an older
#: published index exists: the last attempt failed, so the index cannot be
#: claimed to represent the current sources.
_BLOCKING_MANAGER_STATES = frozenset({"error", "failed"})


def _recorded_manager_state(subject_id: str, kb_name: str) -> str:
    recorded = uploads.read_kb_status(uploads.kb_base_path(subject_id), kb_name)
    return str((recorded or {}).get("status") or "").strip().lower()


def subject_kb_warning_status(
    subject_id: str, kb_name: str, *, record: dict[str, Any] | None = None
) -> str:
    """The status a mount warning must report — never a false "ready".

    A recorded ``error``/``failed`` outranks the source/index projection: the
    projection answers "does the published index match the sources", which can
    still be true for a library whose latest run failed. Reporting that as
    ``ready`` would tell the learner their library is fine when the runtime just
    said otherwise.
    """
    recorded = _recorded_manager_state(subject_id, kb_name)
    if recorded in _BLOCKING_MANAGER_STATES:
        return recorded
    return str(subject_kb_status(subject_id, kb_name, record=record).get("status") or "unknown")


def subject_kb_names(subject_id: str) -> list[str]:
    """Every *registered* KB name of one subject, stably ordered.

    Registration means an entry in the subject's ``knowledge.json`` or in its
    ``kb_config.json``. A directory that merely exists inside
    ``knowledge_bases/`` is not a library the learner owns, so it is not listed
    (and cannot be resolved).
    """
    names: set[str] = set()
    for record in store.load_knowledge_records(subject_id):
        name = record.get("kb_name")
        if isinstance(name, str) and is_valid_kb_name(name):
            names.add(name)
    entries = _kb_config_payload(subject_id).get("knowledge_bases")
    if isinstance(entries, dict):
        for name in entries:
            if isinstance(name, str) and is_valid_kb_name(name):
                names.add(name)
    return sorted(names)


def is_subject_kb_registered(subject_id: str, kb_name: str) -> bool:
    """Whether *kb_name* is a registered library of *subject_id*."""
    return _registration(subject_id, kb_name)[0]


def _registration(subject_id: str, kb_name: str) -> tuple[bool, dict[str, Any] | None]:
    """``(registered, knowledge.json record)`` — one read of each source."""
    record = store.get_knowledge_record(subject_id, kb_name)
    if record is not None:
        return True, record
    entries = _kb_config_payload(subject_id).get("knowledge_bases")
    return (isinstance(entries, dict) and kb_name in entries), None


def subject_kb_status(
    subject_id: str, kb_name: str, *, record: dict | None = None
) -> dict[str, Any]:
    """Read-only status projection of one subject KB (S05/S06 semantics).

    Mirrors the sanitized HTTP projection: the same
    :func:`~deeptutor.subjects.material_manifest.project_status` source/index
    logic, the same fixed-copy ``progress`` payload, and no manager
    construction (``KnowledgeBaseManager`` would create the directory and
    rewrite a normalized config). ``record`` may be passed when the caller has
    already read ``knowledge.json`` for this subject.
    """
    base = uploads.kb_base_path(subject_id)
    kb_dir = confined_kb_dir(subject_id, kb_name)
    manager_status = uploads.read_kb_status(base, kb_name)
    if record is None:
        record = store.get_knowledge_record(subject_id, kb_name)
    materials_dir: Path | None = None
    kb_type = (record or {}).get("type")
    if isinstance(kb_type, str) and kb_type:
        materials_dir = uploads.materials_path(subject_id, kb_type)
    busy = uploads.busy_state(kb_dir)
    return manifest_mod.project_status(
        kb_dir=kb_dir,
        raw_dir=kb_dir / "raw",
        materials_dir=materials_dir,
        subject_id=subject_id,
        kb_name=kb_name,
        manager_status=manager_status,
        worker_alive=busy["worker_alive"],
        queued=busy["queued"],
        task_id=busy["task_id"],
    )


# ---------------------------------------------------------------------------
# Mounted-turn constraints
# ---------------------------------------------------------------------------
def _mounted_entries(mounted_refs: Iterable[object] | None) -> list[str]:
    """Normalized mounted references (order kept, duplicates dropped)."""
    if mounted_refs is None:
        return []
    if isinstance(mounted_refs, (str, bytes)):
        raise json_store.invalid_input("挂载列表必须是引用数组")
    entries: list[str] = []
    for item in mounted_refs:
        ref = normalize_kb_ref(item)
        if not ref:
            raise json_store.invalid_input("挂载列表包含空引用")
        _ref_kind(ref)  # validates a subject wire ref eagerly
        if ref not in entries:
            entries.append(ref)
    return entries


def _allowed_by_mount(ref: str, mounted: Sequence[str]) -> bool:
    """Whether *ref* denotes a resource this turn actually mounted.

    Compared by **resource identity**: a subject reference by ``(subject, name)``
    and a global one by its authorized resource id, so ``admin:kb:x`` and
    ``user:kb:x`` never stand in for one another, while the spellings an
    administrator legitimately aliases (both resolve to the admin library) still
    match. A bare name is allowed when it names the mounted resource under any
    spelling — the mounted set is the authority, the bare form is just how a
    legacy caller writes it.
    """
    target_name = _ref_name(ref)
    target_kind = _ref_kind(ref)
    target_identity = _mounted_identity(ref) if target_kind == "global" else None
    for entry in mounted:
        if entry == ref:
            return True
        if _ref_name(entry) != target_name:
            continue
        entry_kind = _ref_kind(entry)
        if entry_kind == "global" and target_kind == "global":
            if _global_resource_id(entry) == target_identity[2]:
                return True
            continue
        if target_kind == entry_kind or "bare" in (target_kind, entry_kind):
            return True
    return False


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
def _http_error_to_subject_error(exc: BaseException) -> SubjectOperationError:
    """Project the legacy ``HTTPException`` of the global resolver onto C02."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        code = ErrorCode.SCOPE_FORBIDDEN
    elif status == 404:
        code = ErrorCode.KB_NOT_FOUND
    elif status == 400:
        code = ErrorCode.INVALID_INPUT
    else:  # pragma: no cover - defensive; the global resolver raises 4xx only
        code = ErrorCode.INTERNAL_ERROR
    return subject_error(code, cause=exc)


def _strict_provider(base_dir: Path | str, kb_name: str, kb_dir: Path) -> str:
    """The subject KB's bound provider, read strictly and confined.

    The legacy :func:`~deeptutor.services.rag.provider_binding.resolve_bound_provider`
    swallows a broken ``metadata.json`` and follows a symlinked one, so a
    damaged or linked leaf could silently *select* a different engine (and, for a
    linked file, one outside the subject tree). The subject boundary therefore
    reads both sources itself:

    1. ``kb_config.json`` (authoritative), through the strict reader — broken
       JSON is ``storage_corrupt``, a symlinked config is ``storage_io``;
    2. ``metadata.json`` (legacy fallback) inside the already-confined KB
       directory, again through the strict no-follow reader;
    3. otherwise the default provider.

    ``provider_binding`` itself is read-only in this stage and stays untouched.
    """
    from deeptutor.services.rag.factory import DEFAULT_PROVIDER, normalize_provider_name

    base = Path(base_dir)
    config_path = json_store.confined(base, base / KB_CONFIG_NAME)
    payload = json_store.read_object(config_path, default={})
    entries = payload.get("knowledge_bases")
    if isinstance(entries, dict):
        entry = entries.get(kb_name)
        if isinstance(entry, dict) and entry.get("rag_provider"):
            return normalize_provider_name(entry.get("rag_provider"))

    metadata_path = json_store.confined(kb_dir, kb_dir / "metadata.json")
    metadata = json_store.read_object(metadata_path, default={})
    provider = metadata.get("rag_provider")
    if provider:
        return normalize_provider_name(provider)
    return DEFAULT_PROVIDER


def _resolve_global(
    ref: str, *, require_ready: bool = True, require_write: bool = False
) -> ResolvedSubjectKb:
    """Explicit ``admin:kb:`` / ``user:kb:`` — authorization, audit, readiness.

    The multi-user seam decides *whether* the current user may use the library
    (and audits an assigned one). ``require_ready`` then applies the same
    "a library that is erroring or stale cannot be queried" rule the subject path
    uses: a recorded non-ready status is refused, while a library with no
    recorded status at all (a legacy global KB that predates status tracking)
    keeps working as before.
    """
    from deeptutor.multi_user.knowledge_access import resolve_for_rag

    try:
        resource = resolve_for_rag(ref)
    except SubjectOperationError:
        raise
    except Exception as exc:  # HTTPException(403/404) and nothing else expected
        raise _http_error_to_subject_error(exc) from exc
    if resource is None:
        raise subject_error(ErrorCode.KB_NOT_FOUND)
    base_dir = Path(resource.base_dir)
    status = ""
    if require_ready:
        recorded = uploads.read_kb_status(base_dir, resource.name)
        status = str((recorded or {}).get("status") or "")
        # Distinguish an absent legacy status from an explicitly unknown one:
        # read_kb_status projects both as "unknown".
        config_path = json_store.confined(base_dir, base_dir / KB_CONFIG_NAME)
        entries = json_store.read_object(config_path, default={}).get("knowledge_bases")
        entry = entries.get(resource.name) if isinstance(entries, dict) else None
        if isinstance(entry, dict) and "status" in entry and entry["status"] != "ready":
            raise subject_error(ErrorCode.KB_NOT_READY)
    return ResolvedSubjectKb(
        kb_ref=resource.id,
        name=resource.name,
        base_dir=base_dir,
        subject_id=None,
        read_only=bool(resource.read_only),
        provider=resolve_bound_provider(str(base_dir.resolve()), resource.name),
        status=status,
    )


def _resolve_subject(
    subject_id: str,
    kb_name: str,
    *,
    expected_subject_id: str | None,
    require_ready: bool,
) -> ResolvedSubjectKb:
    """One subject library: scope, existence, authorization, then readiness."""
    if expected_subject_id is None or subject_id != expected_subject_id:
        # Cross-subject access is a scope failure, not a lookup failure. The
        # rejection happens before any path or registry read of the other tree.
        raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
    # ``subject_dir`` validates the slug, confines the path and raises 404 for an
    # id that is not registered *for the current user* — never creating it.
    store.subject_dir(subject_id)
    registered, record = _registration(subject_id, kb_name)
    if not registered:
        raise subject_error(ErrorCode.KB_NOT_FOUND)
    # Confinement of the KB leaf happens before anything is read from it.
    kb_dir = confined_kb_dir(subject_id, kb_name)
    # A registration without a directory is not a library. This is true with or
    # without the readiness check: the S05 "legacy empty library" compatibility
    # branch describes a library whose *sources* are unmeasured, not one whose
    # tree does not exist. Resolving must never create it.
    if not kb_dir.is_dir():
        raise subject_error(ErrorCode.KB_NOT_FOUND)

    base = uploads.kb_base_path(subject_id)
    status = ""
    if require_ready:
        projection = subject_kb_status(subject_id, kb_name, record=record)
        status = str(projection.get("status") or "")
        recorded = _recorded_manager_state(subject_id, kb_name)
        if status != "ready" or recorded in _BLOCKING_MANAGER_STATES:
            # Either the source/index projection says the published index is not
            # current, or the runtime recorded a failed attempt. Both mean "not
            # queryable now"; neither may be reported as ready.
            raise subject_error(ErrorCode.KB_NOT_READY)
    return ResolvedSubjectKb(
        kb_ref=encode_subject_kb_ref(subject_id, kb_name),
        name=kb_name,
        base_dir=Path(base),
        subject_id=subject_id,
        read_only=False,
        provider=_strict_provider(base, kb_name, kb_dir),
        status=status,
    )


def resolve_kb_ref(
    kb_ref: str,
    *,
    expected_subject_id: str | None = None,
    mounted_refs: Iterable[object] | None = None,
    require_ready: bool = True,
) -> ResolvedSubjectKb:
    """Resolve one reference to an authorized, server-owned resource.

    ``kb_ref`` is a subject wire id, an existing global wire id, or a bare name:

    * a **subject** ref must name ``expected_subject_id`` (403 otherwise), exist
      for the current user (404) and — when ``require_ready`` — be ready (409);
    * an **explicit global** ref keeps the original multi-user authorization and
      usage-audit semantics, and is held to the same readiness rule as a subject
      one: a recorded ``error``/``stale``/… status is refused (409) instead of
      being queried anyway;
    * a **bare name** is accepted only when ``mounted_refs`` gives it exactly one
      match (0 → 404, >1 → 400). With ``mounted_refs=None`` the historical
      no-subject global resolver is used unchanged; with an explicit list every
      reference — bare or wire — must be part of that mounted set.

    ``require_ready=False`` skips *only* the readiness check: authorization,
    existence and path confinement still apply.
    """
    ref = normalize_kb_ref(kb_ref)
    mounted = _mounted_entries(mounted_refs)
    scoped = mounted_refs is not None

    if not ref:
        if scoped:
            # An empty reference with a real mounted set is not "the default
            # library": guessing one is exactly the fallback C08 forbids.
            raise subject_error(ErrorCode.INVALID_INPUT)
        return _resolve_global("", require_ready=require_ready)

    decoded = decode_subject_kb_ref(ref)
    if decoded is not None:
        if scoped and not _allowed_by_mount(ref, mounted):
            raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
        return _resolve_subject(
            decoded[0],
            decoded[1],
            expected_subject_id=expected_subject_id,
            require_ready=require_ready,
        )

    if _ref_kind(ref) == "global":
        if scoped and not _allowed_by_mount(ref, mounted):
            raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
        return _resolve_global(ref, require_ready=require_ready)

    # A bare name: only the mounted set of this turn may interpret it.
    if not scoped:
        return _resolve_global(ref, require_ready=require_ready)
    match = _unique_mounted_match(ref, mounted)
    if match is None:
        raise subject_error(ErrorCode.KB_NOT_FOUND)
    if match == ref:
        # The mounted set contains this bare name (and nothing else answers to
        # it): it denotes the legacy global library, so the original resolver
        # handles it. No default alias, no subject guess, no recursion.
        return _resolve_global(ref, require_ready=require_ready)
    return resolve_kb_ref(
        match,
        expected_subject_id=expected_subject_id,
        mounted_refs=mounted,
        require_ready=require_ready,
    )


def resolve_kb_refs(
    refs: Iterable[object],
    *,
    expected_subject_id: str | None = None,
    require_ready: bool = True,
) -> list[ResolvedSubjectKb]:
    """Resolve a mounted set, keeping each reference's own failure visible.

    Unlike the single-reference entry point this does **not** swallow errors —
    callers that need a partial view (chat mounting) resolve one by one and keep
    the failure as a warning.
    """
    mounted = _mounted_entries(refs)
    return [
        resolve_kb_ref(
            ref,
            expected_subject_id=expected_subject_id,
            mounted_refs=mounted,
            require_ready=require_ready,
        )
        for ref in mounted
    ]


def kb_entry(base_dir: Path | str, kb_name: str) -> dict[str, Any]:
    """The raw ``kb_config.json`` entry of a KB, read-only (never migrated)."""
    from deeptutor.services.rag.provider_binding import load_kb_config_entry

    return load_kb_config_entry(base_dir, kb_name)


__all__ = [
    "ADMIN_KB_PREFIX",
    "GLOBAL_KB_PREFIXES",
    "KB_CONFIG_NAME",
    "ResolvedSubjectKb",
    "SCOPE_KWARGS",
    "SUBJECT_KB_PREFIX",
    "USER_KB_PREFIX",
    "decode_subject_kb_ref",
    "encode_subject_kb_ref",
    "confined_kb_dir",
    "is_subject_kb_ref",
    "is_subject_kb_registered",
    "is_valid_kb_name",
    "kb_entry",
    "normalize_kb_ref",
    "resolve_kb_ref",
    "resolve_kb_refs",
    "subject_kb_names",
    "subject_kb_status",
    "subject_kb_warning_status",
]
