"""Subjects — subject-scoped learning data (M1).

Routes: subject CRUD, per-subject knowledge bases (upload → index → query).
Knowledge indexing reuses the LlamaIndex pipeline through the same
``KnowledgeBaseInitializer`` / ``run_initialization_task`` machinery as the
global knowledge center, but bound to ``data/subjects/<id>/knowledge_bases``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from deeptutor.api.routers.auth import require_auth
from deeptutor.api.routers.knowledge import (
    KnowledgeBaseInitializer,
    ProgressTracker,
    _build_unique_task_id,
    get_task_stream_manager,
    run_initialization_task,
)
from deeptutor.api.subject_route import SubjectRoute
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.services.rag.service import RAGService
from deeptutor.subjects import (
    exam_points,
    grading,
    json_store,
    knowledge_points,
    store,
    subject_operations,
    uploads,
    wrong_book,
)
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error

logger = logging.getLogger(__name__)

#: 科目路由专用错误出口：只影响本 router，其他上游 router 的异常机制不变（C02/P1-56）。
router = APIRouter(route_class=SubjectRoute)

#: Extension → knowledge type for ``type=auto`` uploads. The single source of
#: truth lives with the upload preflight (``subjects/uploads.py``); the name is
#: re-exported here because it is part of this router's historical surface.
TYPE_BY_EXTENSION = uploads.TYPE_BY_EXTENSION
ALLOWED_TYPES = uploads.ALLOWED_TYPES


def _require_subject(subject_id: str) -> dict:
    """Resolve one subject in the **current user's** registry (C01/C02).

    The id is validated as a plain slug before anything is resolved: an id that
    cannot be a single path segment is ``invalid_subject_id`` (400) rather than a
    lookup miss, and no "clean-up" or admin fallback is attempted. A well-formed
    but unregistered id raises the named ``subject_not_found`` (404) instead of an
    ``HTTPException`` whose detail echoed the caller's input.
    """
    if not store.is_valid_subject_id(subject_id):
        raise store.InvalidSubjectIdError(subject_id)
    subject = store.get_subject(subject_id)
    if subject is None:
        raise store.SubjectNotFoundError(subject_id)
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
    request: Request,
    subject_id: str,
    description: str = Form(None),
    term: str = Form(None),
    _: None = Depends(require_auth),
):
    """Update only the fields the caller actually submitted (C03).

    ``Form(None)`` alone cannot tell "omitted" from "explicit empty string":
    FastAPI collapses an explicitly submitted empty field to ``None`` as well,
    so ``description or ""`` used to wipe a field the caller never mentioned.
    The raw form is consulted for *presence*, its string value for the new
    value — an explicitly submitted empty string clears the field, an absent
    field keeps its stored value, and a PATCH with neither field returns the
    current subject without writing the registry at all.
    """
    subject = _require_subject(subject_id)
    form = await request.form()

    submitted: dict[str, str] = {}
    for name in ("description", "term"):
        if name not in form:
            continue  # 未提交 -> 保留原值
        raw_value = form.get(name)
        if not isinstance(raw_value, str):
            # A file part is already rejected by FastAPI's own 422; this keeps a
            # future parser change from silently clearing the field instead.
            raise json_store.invalid_input(f"{name} 必须是字符串")
        submitted[name] = raw_value  # 显式空字符串 -> 明确清空

    if not submitted:
        # 空 PATCH：不调用 store.update_subject，也不写 index.json。
        return {"subject": subject}

    updated = store.update_subject(subject_id, **submitted)
    return {"subject": updated}


@router.delete("/{subject_id}")
async def delete_subject(subject_id: str, _: None = Depends(require_auth)):
    """Delete this subject's learning + public trees and only then its registry.

    The synchronous deletion (validation, both trees, registry write) holds an
    exclusive activity lease; it runs off-loop and a busy/failed deletion never
    reports ``deleted``.
    """
    _require_subject(subject_id)
    deleted = await asyncio.to_thread(store.delete_subject, subject_id)
    if not deleted:
        raise store.SubjectNotFoundError(subject_id)
    return {"status": "deleted", "subject_id": subject_id}


@router.get("/{subject_id}/knowledge")
async def list_subject_knowledge(subject_id: str, _: None = Depends(require_auth)):
    """Read-only view of this subject's KBs (C07).

    The count and status are projected from the **current** index source, not
    from a stored ``documents`` counter, and the projection never registers,
    creates or schedules anything: a GET must not have side effects.
    """
    _require_subject(subject_id)
    return {"knowledge": _knowledge_view(subject_id)}


def _confined_kb_dir(subject_id: str, kb_name: str) -> Path:
    """A stored record's KB path, refused before it can leave the subject."""
    base_dir = uploads.kb_base_path(subject_id)
    try:
        segment = json_store.safe_segment(kb_name, what="知识库名称")
    except json_store.InvalidInputError as exc:
        raise json_store.corrupt_error("knowledge.json", "知识库记录中的名称非法") from exc
    return json_store.confined(base_dir, base_dir / segment)


def _kb_projection(subject_id: str, kb_name: str, *, record: dict | None) -> dict:
    """The sanitized, read-only status dict for one subject KB."""
    from deeptutor.subjects import material_manifest

    # Read-only on purpose: the global KnowledgeBaseManager constructor creates
    # its directory and rewrites a normalized config, so a GET must not use it.
    manager_status = uploads.read_kb_status(uploads.kb_base_path(subject_id), kb_name)
    kb_dir = _confined_kb_dir(subject_id, kb_name)
    kb_type = (record or {}).get("type")
    materials_dir: Path | None = None
    if kb_type is not None:
        if not isinstance(kb_type, str) or not kb_type:
            raise json_store.corrupt_error("knowledge.json", "知识库记录中的材料类型非法")
        try:
            materials_dir = uploads.materials_path(subject_id, kb_type)
        except json_store.InvalidInputError as exc:
            raise json_store.corrupt_error("knowledge.json", "知识库记录中的材料类型非法") from exc
    busy = uploads.busy_state(kb_dir)
    return material_manifest.project_status(
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


def _knowledge_view(subject_id: str) -> list[dict]:
    out: list[dict] = []
    for record in store.load_knowledge_records(subject_id):
        kb_name = record["kb_name"]
        projection = _kb_projection(subject_id, kb_name, record=record)
        out.append({**record, "documents": projection["documents"], "status": projection})
    return out


@router.post("/{subject_id}/knowledge/upload")
async def upload_subject_knowledge(
    subject_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    type: str = Form("auto"),
    _: None = Depends(require_auth),
):
    """Upload files into this subject's knowledge base (default: textbook).

    The whole batch is validated before anything is created, staged privately,
    and only then published: an audio batch is transcribed and published as
    audio + transcripts, a document batch replaces both ``materials/<type>``
    and the KB's ``raw`` copy and reserves the index task.
    """
    _require_subject(subject_id)
    plan = uploads.plan_batch(files, type=type)
    # Acceptance (staging/transcription) is already a subject activity.  A
    # document batch hands this same lease to the queued index worker; an audio
    # batch releases it when transcription/publish finishes.
    lease = subject_operations.acquire_activity(subject_id, kind="upload")
    if plan.operation == "transcribe":
        return await _await_upload_operation(_upload_audio_batch(subject_id, plan), lease)
    return await _upload_document_batch(
        subject_id, plan, background_tasks, lease=lease
    )


async def _upload_audio_batch(subject_id: str, plan: "uploads.UploadPlan") -> dict:
    """Transcribe a whole audio batch, then publish it (P1-16)."""
    from deeptutor.services.asr import transcribe as asr_mod

    with uploads.staging_root(subject_id) as staging:
        staged = await uploads.stage_files(plan, staging)
        transcripts: list[dict] = []
        for item in staged:
            result = await asr_mod.transcribe(item.path)
            failure = str(result.get("error") or "")
            if failure:
                logger.warning(
                    "ASR failed for one upload (%s): %s",
                    result.get("error_kind") or "provider",
                    failure,
                )
                raise _asr_error(result)
            text = result.get("text", "")
            if not isinstance(text, str):
                raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT) from None
            transcripts.append(
                {
                    "file": item.entry.name,
                    "text": text,
                    "model": str(result.get("model") or ""),
                }
            )
        latch = await asyncio.to_thread(
            subject_operations.acquire_audio_writer, subject_id, timeout=5.0
        )
        try:
            committed = await asyncio.to_thread(
                uploads.commit_transcripts,
                subject_id=subject_id,
                plan=plan,
                staged=staged,
                transcripts=transcripts,
                staging_dir=staging,
            )
        finally:
            latch.release()
    return {
        "operation": "transcribe",
        "type": "lecture",
        "files": committed.names,
        "transcripts": transcripts,
        "message": f"ASR 转写完成（{len(transcripts)} 个文件）",
    }


def _asr_error(result: dict) -> Exception:
    """Map an ASR failure onto the fixed C02 exit; the text stays server-side."""
    kind = str(result.get("error_kind") or "")
    code = {
        "timeout": ErrorCode.PROVIDER_TIMEOUT,
        "invalid_output": ErrorCode.INVALID_MODEL_OUTPUT,
        "unconfigured": ErrorCode.PROVIDER_UNAVAILABLE,
        # A local read failure is storage, not the provider: the client must
        # not be told to "retry the model" when the file could not be read.
        "io": ErrorCode.STORAGE_IO,
    }.get(kind, ErrorCode.PROVIDER_UNAVAILABLE)
    return subject_error(code, cause=RuntimeError(str(result.get("error") or "")))


async def _upload_document_batch(
    subject_id: str,
    plan: "uploads.UploadPlan",
    background_tasks: BackgroundTasks,
    *,
    lease: "subject_operations.ActivityLease | None" = None,
) -> dict:
    """Publish a document batch and queue its index task (P1-17/P1-18/P1-19).

    ``lease`` is acquired before acceptance and handed to the reservation on a
    successful commit.  From that point the background worker owns it until
    :func:`uploads.finalize_reserved_task` observes the real terminal state.
    """
    lease = lease or subject_operations.acquire_activity(subject_id, kind="upload")
    return await _await_upload_operation(
        _upload_document_batch_inner(subject_id, plan, background_tasks, lease=lease), lease)


async def _await_upload_operation(operation, lease: subject_operations.ActivityLease) -> dict:
    """Keep staging and ownership alive through an in-flight thread on cancel.

    A cancelled HTTP request never dispatches its queued background tasks. If
    its commit finishes later, explicitly abort that orphaned reservation before
    releasing the activity lease. Completed source bytes remain authoritative.
    """
    task = asyncio.create_task(operation)

    def cancelled(done: asyncio.Task) -> None:
        async def finish() -> None:
            kb_dir = None
            task_id = None
            try:
                result = done.result()
                task_id = result.get("task_id")
                if task_id:
                    kb_dir = uploads.kb_paths(lease.subject_id, result["kb_name"])[0]
                    reservation = uploads.reservation_for(kb_dir) or {}
                    if reservation.get("task_id") == task_id:
                        await asyncio.to_thread(
                            uploads._abort_reserved_task, kb_dir, task_id, reservation, "request_cancelled")
            except BaseException:
                logger.warning("cancelled upload completion could not be finalized")
            finally:
                if kb_dir is not None and task_id is not None:
                    uploads.clear_reservation(kb_dir, task_id=task_id)
                lease.release()

        asyncio.create_task(finish())

    try:
        result = await asyncio.shield(task)
    except BaseException:
        task.add_done_callback(cancelled)
        raise
    if not lease.detached:
        lease.release()
    return result


async def _upload_document_batch_inner(
    subject_id: str,
    plan: "uploads.UploadPlan",
    background_tasks: BackgroundTasks,
    *,
    lease: "subject_operations.ActivityLease",
) -> dict:
    kb_dir, _raw_dir = uploads.kb_paths(subject_id, plan.kb_name)
    uploads.assert_kb_not_busy(kb_dir)

    base_dir = uploads.kb_base_path(subject_id)
    task_id = _build_unique_task_id("subject_kb", plan.kb_name)

    def _prepare_kb(new_kb: bool) -> None:
        with json_store.json_transaction(store.subject_dir(subject_id)):
            # Only a brand-new KB gets the initializer's directory structure: its
            # metadata.json + registration are the KB's own creation. An existing
            # KB keeps its metadata (description/created_at/unknown fields) instead
            # of being reset by a re-upload.
            if new_kb:
                initializer.create_directory_structure()
            manager.update_kb_status(
                name=plan.kb_name,
                status="initializing" if new_kb else "rebuilding",
                progress={
                    "stage": "initializing" if new_kb else "reindexing",
                    "message": (
                        "Initializing subject KB..." if new_kb else "Re-indexing subject KB..."
                    ),
                    "percent": 0,
                },
            )

    def _write_record(documents: int) -> None:
        record: dict = {
            "kb_name": plan.kb_name,
            "type": plan.kb_type,
            "documents": documents,
        }
        if store.get_knowledge_record(subject_id, plan.kb_name) is None:
            record["kb_id"] = store.new_kb_id()
            record["created_at"] = (manager.get_kb_entry(plan.kb_name) or {}).get(
                "created_at"
            )
        store.upsert_knowledge_record(subject_id, record)

    def _register_task(new_kb: bool) -> None:
        """Queue the background job — inside the commit's rollback boundary."""
        if new_kb:
            background_tasks.add_task(
                uploads.run_reserved_index_task,
                kb_dir,
                task_id,
                run_initialization_task,
                initializer,
                task_id,
            )
            return
        from deeptutor.api.routers.knowledge import run_reindex_task

        background_tasks.add_task(
            uploads.run_reserved_index_task,
            kb_dir,
            task_id,
            run_reindex_task,
            plan.kb_name,
            str(base_dir),
            task_id,
            "",
        )

    try:
        with uploads.staging_root(subject_id) as staging:
            staged = await uploads.stage_files(plan, staging)
            manager = _kb_manager(subject_id)
            get_task_stream_manager().ensure_task(task_id)
            progress_tracker = ProgressTracker(plan.kb_name, base_dir)
            progress_tracker.task_id = task_id
            initializer = KnowledgeBaseInitializer(
                kb_name=plan.kb_name,
                base_dir=str(base_dir),
                progress_tracker=progress_tracker,
                rag_provider="llamaindex",
            )
            committed = await asyncio.to_thread(
                uploads.commit_documents,
                subject_id=subject_id,
                plan=plan,
                staged=staged,
                staging_dir=staging,
                task_id=task_id,
                hooks=uploads.CommitHooks(
                    prepare_kb=_prepare_kb,
                    write_record=_write_record,
                    register_task=_register_task,
                ),
                lease=lease,
            )
    except BaseException:
        uploads.discard_task_metadata(task_id)
        raise

    # The reservation now owns the lease together with the background worker.
    lease.detach()
    return {
        "operation": "index",
        "message": (
            f"已保存 {len(committed.names)} 个文件到科目知识库 '{plan.kb_name}'，正在建立索引。"
        ),
        "kb_name": plan.kb_name,
        "type": plan.kb_type,
        "files": committed.names,
        "task_id": task_id,
        "documents": committed.documents,
    }


@router.get("/{subject_id}/knowledge/{kb_name}/status")
async def subject_kb_status(subject_id: str, kb_name: str, _: None = Depends(require_auth)):
    """Current count/state of one subject KB — read-only, sanitized (P1-19)."""
    _require_subject(subject_id)
    record = store.get_knowledge_record(subject_id, kb_name)
    if uploads.read_kb_status(uploads.kb_base_path(subject_id), kb_name) is None and record is None:
        # Deliberate compatibility (P1-56): this historical plain HTTPException
        # keeps the framework shape ``{"detail": ...}``. The detail is a fixed
        # message rather than the old echo of the caller's kb_name.
        raise HTTPException(status_code=404, detail="知识库不存在。")
    return {"kb_name": kb_name, **_kb_projection(subject_id, kb_name, record=record)}


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

    # The model call happens first and outside every storage lock: whatever the
    # provider does, no learner data has been touched yet.
    result = await _ai_grade(question, student_answer, reference_answer)
    is_correct = result.verdict == "correct"

    # One business commit writes the authoritative collection exactly once. A
    # brand-new correct answer returns None and writes nothing at all; a storage
    # failure keeps the previous bytes and never leaves a half-written entry.
    entry = wrong_book.submit_graded_attempt(
        subject_id,
        question=question,
        correct=is_correct,
        answer=reference_answer,
        kp=kp,
        source="check",
    )

    return {
        "verdict": result.verdict,
        "feedback": result.feedback,
        "correct": is_correct,
        "entry": entry,
        "saved": entry is not None,
    }


async def _ai_grade(
    question: str, student_answer: str, reference_answer: str
) -> grading.GradeResult:
    """Grade one answer via the main LLM (verdict: correct / partial / wrong).

    Thin wiring over :mod:`deeptutor.subjects.grading`: the reply is validated
    there, and every failure propagates as a typed C02 error (projected by the
    subject route wrapper) instead of being flattened into ``wrong``.
    """
    return await grading.grade_answer(question, student_answer, reference_answer)


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

    The whole round is validated first and then saved in **one** transaction:
    duplicates of an earlier detection are reused instead of appended, so two
    runs over the same transcript do not grow the collection. Candidates are
    stored unconfirmed unless ``auto_confirm``; validated ``explicit`` points are
    confirmed. A model failure is never reported as ``detected=0``.
    """
    _require_subject(subject_id)
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="transcript is required")
    from deeptutor.subjects import exam_detection

    result = await exam_detection.detect_points(transcript, term=term, source=source)
    stored = exam_points.upsert_detected(
        subject_id,
        result["points"],
        term=term,
        source=source,
        auto_confirm=auto_confirm,
    )
    return {
        "version": result["version"],
        "detected": len(stored),
        "stored": stored,
        "raw": result["raw"],
        "warnings": result["warnings"],
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
    # One idempotent short transaction creates missing points and rewrites the
    # derived links against the *current* wrong book + confirmed exam points.
    result = knowledge_points.build_from_sources(subject_id)
    return {"created": result["created"], "points": result["points"]}


# ==================== Review pack (M6) ====================

def _verify_review_pack_pdf(path: Path) -> None:
    """Require PDF bytes: PyMuPDF also opens images renamed with a .pdf suffix."""
    from deeptutor.services.pdf.report import _verify_report_pdf

    _verify_report_pdf(path)


def _verify_review_pack_docx(path: Path) -> None:
    """DOCX must be a readable OOXML package with real document content."""
    import zipfile

    try:
        from docx import Document

        if not zipfile.is_zipfile(path):
            raise ValueError("not a zip")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise ValueError("missing OOXML parts")
        document = Document(str(path))
        if not document.paragraphs:
            raise ValueError("empty document")
    except Exception as exc:  # noqa: BLE001 - broken package is a render failure
        raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc


def _render_review_pack_private(
    subject_id: str,
    markdown: str,
    extension: str,
    token: str,
    expected_workspace: str,
) -> Path:
    """Render + verify in a worker thread, still inside the caller's user scope.

    ``asyncio.to_thread`` copies the request context, so the thread re-resolves
    the current PathService and refuses to write if it is not the same workspace
    the async caller used (never the administrator root).  Only private staging
    is touched; publication happens after the await returns.
    """
    from deeptutor.services.pdf import review_guide

    paths = store.current_subject_paths()
    if str(paths.workspace_root) != expected_workspace:
        raise subject_error(ErrorCode.INTERNAL_ERROR)
    subject_dir = store.subject_dir(subject_id)
    staging_root = json_store.confined(subject_dir, subject_dir / "_review_pack")
    json_store.make_directory(staging_root)
    staging = json_store.confined(staging_root, staging_root / f"{token}.{extension}")
    try:
        try:
            ok = (
                review_guide.render_pdf(markdown, staging)
                if extension == "pdf"
                else review_guide.render_docx(markdown, staging)
            )
        except SubjectOperationError:
            raise
        except Exception as exc:  # noqa: BLE001 - renderer failure is C02 render_failed
            raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc
        if not ok:
            raise subject_error(ErrorCode.RENDER_FAILED)
        from deeptutor.services.pdf.report_store import MAX_PUBLISHED_FILE_BYTES

        if staging.is_symlink() or not staging.is_file() or not (
            0 < staging.stat().st_size <= MAX_PUBLISHED_FILE_BYTES
        ):
            raise subject_error(ErrorCode.RENDER_FAILED)
        if extension == "pdf":
            _verify_review_pack_pdf(staging)
        else:
            _verify_review_pack_docx(staging)
        return staging
    except BaseException:
        staging.unlink(missing_ok=True)
        staging.with_suffix(".typ").unlink(missing_ok=True)
        raise


def _prepare_review_pack_copy(
    subject_id: str, markdown: str, extension: str, token: str, expected_workspace: str
) -> Path:
    """Render and copy off-loop; only return an owned, unpublished part file."""
    import os
    import shutil

    paths = store.current_subject_paths()
    final_name = f"review-guide-{token}.{extension}"
    staging = _render_review_pack_private(
        subject_id, markdown, extension, token, expected_workspace
    )
    try:
        subject_dir = store.subject_dir(subject_id)
        public_root = paths.get_public_outputs_root()
        # Validate every component before mkdir/open, including in-root aliases.
        public_dir = json_store.confined(public_root, public_root / "subjects" / subject_dir.name)
        json_store.make_directory(public_dir)
        final_path = json_store.confined(public_root, public_dir / final_name)
        if final_path.exists() or final_path.is_symlink():
            raise subject_error(ErrorCode.STORAGE_IO)
        temporary = json_store.confined(public_root, public_dir / f".{final_name}.part")
        owned = False
        try:
            # Exclusive creation never follows or deletes a preexisting part.
            with temporary.open("xb") as target:
                owned = True
                with staging.open("rb") as source:
                    shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            return temporary
        except BaseException:
            if owned:
                temporary.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    finally:
        staging.unlink(missing_ok=True)
        staging.with_suffix(".typ").unlink(missing_ok=True)


def _prepare_review_pack_copy_leased(
    subject_id: str, markdown: str, extension: str, token: str, expected_workspace: str
) -> Path:
    """Hold a subject lease for the whole off-loop render+copy.

    The request's own lease is released when a cancelled request unwinds; this
    inner lease stays with the thread until it has cleaned up its private part,
    so a concurrent delete still sees the subject as active.
    """
    with subject_operations.acquire_activity(subject_id, kind="review-pack-copy"):
        return _prepare_review_pack_copy(
            subject_id, markdown, extension, token, expected_workspace
        )


async def _publish_review_pack(subject_id: str, markdown: str, extension: str) -> tuple[str, str]:
    """Offload all large IO; commit only after a live request resumes.

    Shielding retains ownership of the thread's result after cancellation. Its
    completion callback removes only its own unpublished part; no worker thread
    can publish a final name. The event-loop commit is one no-overwrite link.
    """
    import os
    import uuid

    paths = store.current_subject_paths()
    expected_workspace = str(paths.workspace_root)
    token = uuid.uuid4().hex
    final_name = f"review-guide-{token}.{extension}"
    prepared = asyncio.create_task(asyncio.to_thread(
        _prepare_review_pack_copy_leased,
        subject_id,
        markdown,
        extension,
        token,
        expected_workspace,
    ))

    def discard(done: asyncio.Task) -> None:
        try:
            done.result().unlink(missing_ok=True)
        except BaseException:
            # Retrieve worker errors without replacing the caller's cancellation.
            pass

    try:
        temporary = await asyncio.shield(prepared)
    except BaseException:
        prepared.add_done_callback(discard)
        raise
    try:
        subject_dir = store.subject_dir(subject_id)
        public_root = paths.get_public_outputs_root()
        json_store.confined(public_root, temporary)
        final_path = json_store.confined(public_root, temporary.parent / final_name)
        os.link(temporary, final_path, follow_symlinks=False)
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    finally:
        temporary.unlink(missing_ok=True)
    relative = f"subjects/{subject_dir.name}/{final_name}"
    return final_name, relative


@router.post("/{subject_id}/review-pack")
async def generate_review_pack(
    subject_id: str,
    format: str = Form("pdf"),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a printable review guide from exam points + wrong book.

    The Markdown is only rendered after the shared S02 generation gate returned
    a complete body; PDF/DOCX is verified in private staging before the atomic
    public publish.  A failure is a named C02 error with no URL.
    """
    _require_subject(subject_id)
    from deeptutor.services.pdf import review_guide

    if format not in ("pdf", "docx"):
        raise subject_error(ErrorCode.INVALID_INPUT)
    lease = subject_operations.acquire_activity(subject_id, kind="review-pack")
    try:
        markdown = await review_guide.generate_guide_markdown(subject_id, term=term)
        if not markdown.strip():
            raise subject_error(ErrorCode.EMPTY_MODEL_OUTPUT)
        markdown_tokens = review_guide.estimate_tokens(markdown)
        name, relative = await _publish_review_pack(subject_id, markdown, format)
    finally:
        lease.release()
    return {
        "format": format,
        "markdown_tokens": markdown_tokens,
        "url": f"/api/outputs/subjects/{subject_id}/{name}",
        "path": relative,
        "status": "completed",
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
    ode_rhs: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a chart-bearing report and publish it as one completed run.

    The route only calls the shared pipeline and projects the official
    ``ReportResponse`` fields; it never creates an output directory, writes a
    compatibility Markdown or guesses a URL from seconds.
    """
    _require_subject(subject_id)
    if not title.strip():
        raise subject_error(ErrorCode.INVALID_INPUT)
    from deeptutor.services.pdf import report as report_mod

    result = await report_mod.generate_report(
        subject_id,
        title=title,
        requirements=requirements,
        ode_rhs=ode_rhs,
    )
    return {
        "title": result["title"],
        "report_id": result["report_id"],
        "status": result["status"],
        "markdown_tokens": result["markdown_tokens"],
        "chart_count": result["chart_count"],
        "url": result["url"],
        "path": result["path"],
        "verification_status": result["verification_status"],
    }


# ==================== Backup export (M8) ====================

@router.get("/{subject_id}/export")
async def export_subject_data(subject_id: str, _: None = Depends(require_auth)):
    """Snapshot the current subject into a verified ZIP and return its URL.

    The heavy snapshot/compression runs in a worker thread and only prepares a
    private file; this live request commits the public name after the await.
    If the request is cancelled, the preparation is discarded when its thread
    finishes: no public ZIP and no URL from this attempt survive.
    """
    _require_subject(subject_id)
    from deeptutor.subjects import export_bundle

    prepared_task = asyncio.create_task(
        asyncio.to_thread(export_bundle.prepare_export_bundle, subject_id)
    )

    def discard(done: asyncio.Task) -> None:
        try:
            export_bundle.discard_export_bundle(done.result())
        except BaseException:
            # Retrieve worker errors without replacing the caller's cancellation.
            pass

    try:
        prepared = await asyncio.shield(prepared_task)
    except BaseException:
        prepared_task.add_done_callback(discard)
        raise

    result = export_bundle.commit_export_bundle(prepared)
    name = result["zip_path"].name
    relative = f"subjects/{subject_id}/{name}"
    return {
        "url": f"/api/outputs/{relative}",
        "path": relative,
        "size": result["size"],
        "export_id": result["export_id"],
        "schema_version": export_bundle.SCHEMA_VERSION,
    }
