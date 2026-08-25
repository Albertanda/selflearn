"""Subject-scoped data layer (M1).

Each subject owns its own data tree under ``data/subjects/<id>/``:

    data/subjects/
        index.json              # subject registry (id, name, term, ...)
        <id>/
            knowledge.json      # knowledge-base records for this subject
            materials/<type>/   # uploaded raw files (textbook/ppt/board/...)
            knowledge_bases/    # LlamaIndex KB trees (one per record)

The model configuration stays global; only learner data is subject-scoped.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
import uuid

from deeptutor.services.path_service import get_path_service

SUBJECTS_ROOT_NAME = "subjects"
_SUBJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def subjects_root() -> Path:
    """Root of the subject tree (``data/subjects``)."""
    root = get_path_service().get_workspace_dir() / SUBJECTS_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def subject_dir(subject_id: str) -> Path:
    """The data directory for one subject."""
    return subjects_root() / subject_id


def _index_path() -> Path:
    return subjects_root() / "index.json"


def load_subjects() -> list[dict]:
    """Load the subject registry (``[]`` when missing)."""
    path = _index_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_subjects(subjects: list[dict]) -> None:
    _index_path().write_text(
        json.dumps(subjects, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def slugify(name: str) -> str:
    """Stable id from a Chinese/English subject name."""
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", name.strip().lower()).strip("-")
    if not raw:
        raw = "subject"
    if len(raw) > 40:
        raw = raw[:40].rstrip("-")
    return raw


def _unique_subject_id(name: str) -> str:
    base = slugify(name)
    existing = {s["id"] for s in load_subjects()}
    candidate = base
    n = 1
    while candidate in existing:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def create_subject(name: str, description: str = "", term: str = "") -> dict:
    """Create a subject and its data directory."""
    subjects = load_subjects()
    subject_id = _unique_subject_id(name)
    record = {
        "id": subject_id,
        "name": name.strip(),
        "description": description.strip(),
        "term": term.strip(),
        "created_at": int(time.time()),
    }
    subjects.append(record)
    _save_subjects(subjects)
    d = subject_dir(subject_id)
    (d / "materials").mkdir(parents=True, exist_ok=True)
    (d / "knowledge_bases").mkdir(parents=True, exist_ok=True)
    _save_knowledge_records(subject_id, [])
    return record


def get_subject(subject_id: str) -> dict | None:
    return next((s for s in load_subjects() if s["id"] == subject_id), None)


def update_subject(subject_id: str, **fields: str) -> dict | None:
    subjects = load_subjects()
    for s in subjects:
        if s["id"] == subject_id:
            for key in ("name", "description", "term"):
                if fields.get(key) is not None:
                    s[key] = fields[key].strip()
            _save_subjects(subjects)
            return s
    return None


def delete_subject(subject_id: str) -> bool:
    subjects = load_subjects()
    kept = [s for s in subjects if s["id"] != subject_id]
    if len(kept) == len(subjects):
        return False
    _save_subjects(kept)
    import shutil

    d = subject_dir(subject_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return True


def _knowledge_path(subject_id: str) -> Path:
    return subject_dir(subject_id) / "knowledge.json"


def load_knowledge_records(subject_id: str) -> list[dict]:
    path = _knowledge_path(subject_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_knowledge_records(subject_id: str, records: list[dict]) -> None:
    path = _knowledge_path(subject_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def get_knowledge_record(subject_id: str, kb_name: str) -> dict | None:
    return next(
        (r for r in load_knowledge_records(subject_id) if r["kb_name"] == kb_name), None
    )


def upsert_knowledge_record(subject_id: str, record: dict) -> None:
    records = load_knowledge_records(subject_id)
    records = [r for r in records if r["kb_name"] != record["kb_name"]]
    records.append(record)
    _save_knowledge_records(subject_id, records)


def subject_kb_base_dir(subject_id: str) -> Path:
    """LlamaIndex base dir for a subject's knowledge bases."""
    d = subject_dir(subject_id) / "knowledge_bases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def materials_dir(subject_id: str, kb_type: str) -> Path:
    d = subject_dir(subject_id) / "materials" / kb_type
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_kb_id() -> str:
    return uuid.uuid4().hex[:12]
