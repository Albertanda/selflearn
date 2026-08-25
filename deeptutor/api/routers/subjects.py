"""Subjects — subject-scoped learning data (M1).

Routes: subject CRUD, per-subject knowledge bases (upload → index → query).
Knowledge indexing reuses the LlamaIndex pipeline through the same
``KnowledgeBaseInitializer`` / ``run_initialization_task`` machinery as the
global knowledge center, but bound to ``data/subjects/<id>/knowledge_bases``.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pathlib import Path
import time

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
from deeptutor.subjects import exam_points, knowledge_points, profile as profile_mod, store, wrong_book

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


# ==================== Wrong-question book (M3) ====================

@router.get("/{subject_id}/wrong-book/stats")
async def wrong_book_stats(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    return {"subject_id": subject_id, **wrong_book.stats(subject_id)}


@router.get("/{subject_id}/wrong-book")
async def list_wrong_book(
    subject_id: str,
    status: str = "",
    include_archived: bool = False,
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    entries = wrong_book.list_entries(
        subject_id, status=status or None, archived=None if include_archived else False
    )
    return {"subject_id": subject_id, "entries": entries}


@router.post("/{subject_id}/wrong-book")
async def add_wrong_entry(
    subject_id: str,
    question: str = Form(...),
    answer: str = Form(""),
    analysis: str = Form(""),
    kp: str = Form(""),
    question_type: str = Form("written"),
    source: str = Form("manual"),
    error_type: str = Form(""),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    if not question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    entry = wrong_book.add_entry(
        subject_id,
        question=question,
        answer=answer,
        analysis=analysis,
        kp=kp,
        question_type=question_type,
        source=source,
        error_type=error_type,
    )
    return {"entry": entry}


@router.post("/{subject_id}/wrong-book/{entry_id}/attempt")
async def record_wrong_attempt(
    subject_id: str,
    entry_id: str,
    correct: bool = Form(...),
    session_id: str = Form(""),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    entry = wrong_book.record_attempt(
        subject_id, entry_id, correct=correct, session_id=session_id
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Wrong-book entry not found")
    return {"entry": entry}


@router.post("/{subject_id}/wrong-book/{entry_id}/archive")
async def archive_wrong_entry(subject_id: str, entry_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    entry = wrong_book.archive(subject_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Wrong-book entry not found")
    return {"entry": entry}


@router.delete("/{subject_id}/wrong-book/{entry_id}")
async def delete_wrong_entry(subject_id: str, entry_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    if not wrong_book.delete(subject_id, entry_id):
        raise HTTPException(status_code=404, detail="Wrong-book entry not found")
    return {"status": "deleted", "entry_id": entry_id}


@router.post("/{subject_id}/wrong-book/check")
async def check_answer(
    subject_id: str,
    question: str = Form(...),
    student_answer: str = Form(...),
    reference_answer: str = Form(""),
    kp: str = Form(""),
    _: None = Depends(require_auth),
):
    """AI-graded answer check: grades the submission, then writes the
    outcome into the wrong-question book (new entry on a miss, attempt
    on a hit of an existing entry)."""
    _require_subject(subject_id)
    if not question.strip() or not student_answer.strip():
        raise HTTPException(status_code=400, detail="question and student_answer are required")

    verdict, feedback = await _ai_grade(question, student_answer, reference_answer)
    is_correct = verdict == "correct"

    entry = wrong_book.find_by_question(subject_id, question)
    if entry is None:
        entry = wrong_book.add_entry(
            subject_id,
            question=question,
            answer=reference_answer,
            kp=kp,
            source="check",
        )
    entry = wrong_book.record_attempt(subject_id, entry["id"], correct=is_correct)

    return {
        "verdict": verdict,
        "feedback": feedback,
        "correct": is_correct,
        "entry": entry,
    }


async def _ai_grade(question: str, student_answer: str, reference_answer: str) -> tuple[str, str]:
    """Grade one answer via the main LLM (verdict: correct / partial / wrong)."""
    from deeptutor.services.llm.config import get_llm_config
    from deeptutor.services.llm.factory import complete

    cfg = get_llm_config()
    prompt = (
        "你是一名严谨且鼓励学习者的助教，正在批改一道题。\n\n"
        f"题目：{question}\n"
        + (f"参考答案：{reference_answer}\n" if reference_answer else "")
        + f"学生作答：{student_answer}\n\n"
        "请只输出 JSON：{\"verdict\": \"correct|partial|wrong\", \"feedback\": \"简短分条反馈（哪里对、哪里错、如何改正）\"}"
    )
    try:
        raw = await complete(
            prompt=prompt,
            system_prompt="你是严格的批改助教。",
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
        import json as _json
        import re as _re

        text = raw.strip()
        m = _re.search(r"\{[\s\S]*\}", text)
        if m:
            data = _json.loads(m.group(0))
            verdict = str(data.get("verdict", "wrong")).lower()
            if verdict not in ("correct", "partial", "wrong"):
                verdict = "wrong"
            return verdict, str(data.get("feedback", ""))[:500]
        return "wrong", text[:300]
    except Exception as exc:  # noqa: BLE001
        return "wrong", f"批改服务不可用：{exc}"


# ==================== Exam points (M4) ====================

@router.get("/{subject_id}/exam-points")
async def list_exam_points(
    subject_id: str,
    term: str = "",
    confirmed_only: bool = False,
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    points = exam_points.list_points(
        subject_id, term=term or None, confirmed=True if confirmed_only else None
    )
    return {"subject_id": subject_id, "points": points}


@router.post("/{subject_id}/exam-points")
async def add_exam_point(
    subject_id: str,
    content: str = Form(...),
    level: str = Form("inferred"),
    evidence: str = Form(""),
    kp: str = Form(""),
    term: str = Form(""),
    source: str = Form("manual"),
    anchor: str = Form(""),
    confirmed: bool = Form(True),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    if not content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    point = exam_points.add_point(
        subject_id,
        content=content,
        level=level,
        evidence=evidence,
        kp=kp,
        term=term,
        source=source,
        anchor=anchor,
        confirmed=confirmed,
    )
    return {"point": point}


@router.post("/{subject_id}/exam-points/detect")
async def detect_exam_points(
    subject_id: str,
    transcript: str = Form(...),
    term: str = Form(""),
    source: str = Form("lecture"),
    auto_confirm: bool = Form(False),
    _: None = Depends(require_auth),
):
    """Run exam-point detection over a lecture transcript (e.g. ASR text).

    Candidates are stored unconfirmed unless ``auto_confirm``; explicit
    points are always stored. Returns the detection record + stored points.
    """
    _require_subject(subject_id)
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="transcript is required")
    from deeptutor.subjects import exam_detection

    result = await exam_detection.detect_points(transcript, term=term, source=source)
    candidates = result["points"]
    stored = []
    for p in candidates:
        confirmed = bool(auto_confirm) or p["level"] == "explicit"
        stored.append(
            exam_points.add_point(
                subject_id,
                content=p["content"],
                level=p["level"],
                evidence=p.get("evidence", ""),
                kp=p.get("kp", ""),
                term=term,
                source=source,
                anchor=p.get("anchor", ""),
                confirmed=confirmed,
            )
        )
    return {
        "version": result["version"],
        "detected": len(candidates),
        "stored": stored,
        "raw": result.get("raw", ""),
    }


@router.post("/{subject_id}/exam-points/{point_id}/confirm")
async def confirm_exam_point(
    subject_id: str, point_id: str, _: None = Depends(require_auth)
):
    _require_subject(subject_id)
    point = exam_points.set_confirmed(subject_id, point_id, True)
    if point is None:
        raise HTTPException(status_code=404, detail="Exam point not found")
    return {"point": point}


@router.delete("/{subject_id}/exam-points/{point_id}")
async def delete_exam_point(subject_id: str, point_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    if not exam_points.delete(subject_id, point_id):
        raise HTTPException(status_code=404, detail="Exam point not found")
    return {"status": "deleted", "point_id": point_id}


# ==================== Knowledge points (M5) ====================

@router.get("/{subject_id}/knowledge-points")
async def list_knowledge_points(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    return {"subject_id": subject_id, "points": knowledge_points.aggregate(subject_id)}


@router.post("/{subject_id}/knowledge-points")
async def add_knowledge_point(
    subject_id: str,
    name: str = Form(...),
    path: str = Form(""),
    source: str = Form("manual"),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    point = knowledge_points.add_point(subject_id, name=name, path=path, source=source)
    return {"point": point}


@router.post("/{subject_id}/knowledge-points/build")
async def build_knowledge_points(subject_id: str, _: None = Depends(require_auth)):
    """Build/link the knowledge map from existing subject data.

    Creates points for every knowledge point named in the wrong book and
    the confirmed exam points, then links both ways. Optionally the LLM
    can enrich with textbook-derived points via ``llm=True`` (future).
    """
    _require_subject(subject_id)
    from deeptutor.subjects import exam_points as ep_mod, wrong_book

    created = []
    # 1. Points from wrong-book kp labels.
    for e in wrong_book.load(subject_id):
        kp = (e.get("kp") or "").strip()
        if not kp:
            continue
        point = knowledge_points.add_point(subject_id, name=kp, source="wrong_book")
        knowledge_points.link_wrong_entry(subject_id, kp, e["id"])
        if point["source"] == "wrong_book":
            created.append(point)
    # 2. Points from confirmed exam points.
    for p in ep_mod.load(subject_id):
        if not p.get("confirmed"):
            continue
        kp = (p.get("kp") or "").strip()
        if not kp:
            continue
        point = knowledge_points.add_point(subject_id, name=kp, source="exam_point")
        knowledge_points.link_exam_point(subject_id, kp, p["id"])
        if point["source"] == "exam_point":
            created.append(point)
    return {
        "created": len(created),
        "points": knowledge_points.aggregate(subject_id),
    }


# ==================== Review pack (M6) ====================

@router.post("/{subject_id}/review-pack")
async def generate_review_pack(
    subject_id: str,
    format: str = Form("pdf"),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a printable review guide from exam points + wrong book.

    Writes the artifact under the public outputs tree and returns a
    download URL served by ``/api/outputs``.
    """
    _require_subject(subject_id)
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.pdf import review_guide

    if format not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="format must be pdf or docx")

    markdown = await review_guide.generate_guide_markdown(subject_id, term=term)
    outputs_root = get_path_service().get_public_outputs_root()
    out_dir = outputs_root / "subjects" / subject_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    ext = "pdf" if format == "pdf" else "docx"
    out_path = out_dir / f"review-guide-{ts}.{ext}"

    ok = (
        review_guide.render_pdf(markdown, out_path)
        if format == "pdf"
        else review_guide.render_docx(markdown, out_path)
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Render failed (is Typst installed?)")
    return {
        "format": format,
        "markdown_tokens": review_guide.estimate_tokens(markdown),
        "url": f"/api/outputs/subjects/{subject_id}/review-guide-{ts}.{ext}",
        "path": str(out_path),
    }


# ==================== Subject profile (M5+) ====================

@router.get("/{subject_id}/profile")
async def get_subject_profile(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    from deeptutor.subjects import profile as profile_mod

    return {"subject_id": subject_id, "profile": profile_mod.load(subject_id)}


@router.post("/{subject_id}/profile")
async def update_subject_profile(
    subject_id: str,
    goals: str = Form(""),
    explanation_style: str = Form("balanced"),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    from deeptutor.subjects import profile as profile_mod

    profile = profile_mod.update(
        subject_id, goals=goals, explanation_style=explanation_style
    )
    return {"subject_id": subject_id, "profile": profile}


# ==================== Report writing (M7) ====================

@router.post("/{subject_id}/report")
async def generate_subject_report(
    subject_id: str,
    title: str = Form(...),
    requirements: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a chart-bearing report and export it as PDF."""
    _require_subject(subject_id)
    if not title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.pdf import report as report_mod

    outputs_root = get_path_service().get_public_outputs_root()
    out_dir = outputs_root / "subjects" / subject_id / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = await report_mod.generate_report(
        subject_id, title=title, requirements=requirements, out_dir=out_dir
    )
    if not result["pdf_ok"]:
        raise HTTPException(status_code=500, detail="Report PDF render failed")
    pdf_name = Path(result["pdf_path"]).name
    return {
        "title": result["title"],
        "markdown_tokens": result["markdown_tokens"],
        "chart_count": result["chart_count"],
        "url": f"/api/outputs/subjects/{subject_id}/reports/{pdf_name}",
        "path": result["pdf_path"],
    }
