"""Subjects — subject-scoped learning data (M1).

Routes: subject CRUD, per-subject knowledge bases (upload → index → query).
Knowledge indexing reuses the LlamaIndex pipeline through the same
``KnowledgeBaseInitializer`` / ``run_initialization_task`` machinery as the
global knowledge center, but bound to ``data/subjects/<id>/knowledge_bases``.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pathlib import Path

from deeptutor.api.routers.auth import require_auth
from deeptutor.api.routers.knowledge import (
    KnowledgeBaseInitializer,
    ProgressTracker,
    _build_unique_task_id,
    _save_uploaded_files_off_loop,
    get_task_stream_manager,
    run_initialization_task,
)
from deeptutor.knowledge.naming import validate_knowledge_base_name
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.services.rag.service import RAGService
from deeptutor.subjects import store

router = APIRouter()

#: Extension → knowledge type. Uploads without an explicit ``type`` are
#: routed by extension; everything else defaults to ``textbook``.
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

ALLOWED_TYPES = {"textbook", "ppt", "board", "lecture", "assignment", "past_exam", "other"}


def _require_subject(subject_id: str) -> dict:
    subject = store.get_subject(subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"Subject '{subject_id}' not found")
    return subject


def _kb_manager(subject_id: str) -> KnowledgeBaseManager:
    return KnowledgeBaseManager(base_dir=str(store.subject_kb_base_dir(subject_id)))


@router.get("")
async def list_subjects(_: None = Depends(require_auth)):
    return {"subjects": store.load_subjects()}


@router.post("")
async def create_subject(
    name: str = Form(...),
    description: str = Form(""),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Subject name is required")
    record = store.create_subject(name, description, term)
    return {"subject": record}


@router.patch("/{subject_id}")
async def patch_subject(
    subject_id: str,
    description: str = Form(None),
    term: str = Form(None),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    updated = store.update_subject(subject_id, description=description or "", term=term or "")
    return {"subject": updated}


@router.delete("/{subject_id}")
async def delete_subject(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    store.delete_subject(subject_id)
    return {"status": "deleted", "subject_id": subject_id}


@router.get("/{subject_id}/knowledge")
async def list_subject_knowledge(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    manager = _kb_manager(subject_id)
    out = []
    for record in store.load_knowledge_records(subject_id):
        status = manager.get_kb_status(record["kb_name"]) or {}
        out.append({**record, "status": status})
    return {"knowledge": out}


@router.post("/{subject_id}/knowledge/upload")
async def upload_subject_knowledge(
    subject_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    type: str = Form("auto"),
    _: None = Depends(require_auth),
):
    """Upload files into this subject's knowledge base (default: textbook)."""
    _require_subject(subject_id)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if type == "auto":
        # Route by extension; default to textbook.
        first = files[0].filename or ""
        ext = Path(first).suffix.lower()
        kb_type = TYPE_BY_EXTENSION.get(ext, "textbook")
    else:
        if type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown type '{type}'")
        kb_type = type

    kb_name = f"{kb_type}-kb"
    try:
        kb_name = validate_knowledge_base_name(kb_name)
    except ValueError:
        kb_name = f"{kb_type}{store.new_kb_id()[:6]}"

    base_dir = store.subject_kb_base_dir(subject_id)
    manager = _kb_manager(subject_id)

    # Save raw files into the subject's materials tree (authoritative copy).
    materials = store.materials_dir(subject_id, kb_type)
    saved, _ = await _save_uploaded_files_off_loop(
        files, materials, allowed_extensions=None, rel_paths=None
    )

    import shutil
    from pathlib import Path as _Path

    kb_raw_dir = _Path(base_dir) / kb_name / "raw"
    kb_raw_dir.mkdir(parents=True, exist_ok=True)
    for name in saved:
        src_file = _Path(materials) / name
        dst = kb_raw_dir / name
        if src_file.exists() and not dst.exists():
            shutil.copy2(src_file, dst)

    if kb_name not in manager.list_knowledge_bases():
        manager.update_kb_status(
            name=kb_name,
            status="initializing",
            progress={"stage": "initializing", "message": "Initializing subject KB...", "percent": 0},
        )
        task_id = _build_unique_task_id("subject_kb", kb_name)
        get_task_stream_manager().ensure_task(task_id)
        progress_tracker = ProgressTracker(kb_name, base_dir)
        progress_tracker.task_id = task_id
        initializer = KnowledgeBaseInitializer(
            kb_name=kb_name,
            base_dir=str(base_dir),
            progress_tracker=progress_tracker,
            rag_provider="llamaindex",
        )
        initializer.create_directory_structure()
        if kb_name not in manager.list_knowledge_bases():
            initializer._register_to_config()


        record = {
            "kb_name": kb_name,
            "kb_id": store.new_kb_id(),
            "type": kb_type,
            "documents": 0,
            "created_at": manager.config.get("knowledge_bases", {})
            .get(kb_name, {})
            .get("created_at"),
        }
        store.upsert_knowledge_record(subject_id, record)
        background_tasks.add_task(run_initialization_task, initializer, task_id)
    else:
        task_id = _build_unique_task_id("subject_kb_add", kb_name)
        get_task_stream_manager().ensure_task(task_id)
        from deeptutor.api.routers.knowledge import run_reindex_task

        # Reset a stale error state so the reindex writes fresh progress.
        current = manager.get_kb_status(kb_name) or {}
        if current.get("status") in ("error", "failed", "initializing"):
            manager.update_kb_status(
                name=kb_name,
                status="initializing",
                progress={"stage": "reindexing", "message": "Re-indexing subject KB...", "percent": 0},
            )
        # Simplest robust path: rebuild the KB with the new file set.
        background_tasks.add_task(
            run_reindex_task, kb_name, str(base_dir), task_id, ""
        )

    return {
        "message": f"Uploaded {len(saved)} file(s) to subject KB '{kb_name}' (type={kb_type})",
        "kb_name": kb_name,
        "type": kb_type,
        "files": saved,
        "task_id": task_id,
    }


@router.get("/{subject_id}/knowledge/{kb_name}/status")
async def subject_kb_status(subject_id: str, kb_name: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    manager = _kb_manager(subject_id)
    status = manager.get_kb_status(kb_name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"KB '{kb_name}' not found")
    return {"kb_name": kb_name, **status}


@router.post("/{subject_id}/knowledge/{kb_name}/query")
async def subject_kb_query(
    subject_id: str,
    kb_name: str,
    query: str = Form(...),
    _: None = Depends(require_auth),
):
    """Retrieve from this subject's KB (RAG search) — the M2 acceptance probe."""
    _require_subject(subject_id)
    manager = _kb_manager(subject_id)
    if kb_name not in manager.list_knowledge_bases():
        raise HTTPException(status_code=404, detail=f"KB '{kb_name}' not found")
    status = manager.get_kb_status(kb_name) or {}
    if status.get("status") not in ("ready",):
        raise HTTPException(
            status_code=409,
            detail=f"KB '{kb_name}' is not ready (status={status.get('status', 'unknown')})",
        )
    rag = RAGService(kb_base_dir=str(store.subject_kb_base_dir(subject_id)))
    result = await rag.search(query=query, kb_name=kb_name)
    return {"query": query, "kb_name": kb_name, "result": result}
