"""P1-40: the shared subject activity protocol is a real OS lease."""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from starlette.datastructures import UploadFile

from deeptutor.api.routers import subjects as subjects_router
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_store
from deeptutor.subjects import export_bundle, store, subject_operations, uploads
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers


def _subject(admin_root: Path, label: str = "租约科目") -> helpers.SubjectPaths:
    return helpers.make_subject(admin_root, label)


def _code(exc: BaseException) -> str:
    return getattr(exc, "code", None)


def _assert_busy(fn, *args, **kwargs):
    with pytest.raises(SubjectOperationError) as error:
        fn(*args, **kwargs)
    assert error.value.code == ErrorCode.KB_BUSY
    assert error.value.http_status == 409
    assert error.value.retryable is True


def test_missing_fcntl_is_a_typed_failure_without_opening_a_descriptor(p1_runtime, monkeypatch):
    from deeptutor.subjects.errors import SubjectStorageError

    subject = _subject(p1_runtime)
    monkeypatch.setattr(subject_operations, "fcntl", None)
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises(SubjectStorageError):
        subject_operations.acquire_activity(subject.subject_id)
    assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_registration_is_rechecked_after_acquiring_the_os_lock(p1_runtime, monkeypatch):
    subject = _subject(p1_runtime)
    real_key = subject_operations.lease_key
    removed = False

    def racing(sid):
        nonlocal removed
        key = real_key(sid)
        if not removed:
            removed = True
            assert store.delete_subject(sid)
        return key

    monkeypatch.setattr(subject_operations, "lease_key", racing)
    lease = None
    try:
        with pytest.raises(SubjectOperationError) as error:
            lease = subject_operations.acquire_activity(subject.subject_id)
        assert error.value.code == ErrorCode.SUBJECT_NOT_FOUND
        assert not subject.root.exists()
    finally:
        if lease is not None:
            lease.release()


def test_direct_report_store_run_also_blocks_export_and_delete(p1_runtime):
    subject = _subject(p1_runtime)
    run = report_store.create_report_run(subject.subject_id)
    try:
        _assert_busy(export_bundle.prepare_export_bundle, subject.subject_id)
        _assert_busy(store.delete_subject, subject.subject_id)
    finally:
        report_store.fail_report_run(run)


def test_a_lease_for_another_subject_cannot_authorize_report_creation(p1_runtime):
    a, b = _subject(p1_runtime, "租约甲"), _subject(p1_runtime, "租约乙")
    lease = subject_operations.acquire_activity(a.subject_id)
    run = None
    try:
        with pytest.raises(SubjectOperationError):
            run = report_store.create_report_run(b.subject_id, lease=lease)
        assert lease.active
        assert not (b.root / "_report_runs").exists()
    finally:
        if run is not None:
            report_store.fail_report_run(run)
        lease.release()


def test_fork_child_cannot_unlock_the_parent_lease(p1_runtime):
    subject = _subject(p1_runtime)
    lease = subject_operations.acquire_activity(subject.subject_id)
    pid = os.fork()
    if pid == 0:
        try:
            lease.release()
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    contender = None
    try:
        with pytest.raises(SubjectOperationError) as error:
            contender = subject_operations.acquire_activity(subject.subject_id, mode="exclusive")
        assert error.value.code == ErrorCode.KB_BUSY
    finally:
        if contender is not None:
            contender.release()
        lease.release()


def test_lease_file_must_be_regular(p1_runtime):
    from deeptutor.subjects.errors import SubjectStorageError

    subject = _subject(p1_runtime)
    root = subject_operations._lock_root()
    os.mkfifo(root / f"{subject.subject_id}.lock")
    lease = None
    try:
        with pytest.raises(SubjectStorageError):
            lease = subject_operations.acquire_activity(subject.subject_id)
    finally:
        if lease is not None:
            lease.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("audio", [False, True])
async def test_cancelled_upload_commit_keeps_ownership_until_real_completion(
    p1_runtime, monkeypatch, audio
):
    from fastapi import BackgroundTasks

    subject = _subject(p1_runtime)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    target = "commit_transcripts" if audio else "commit_documents"
    real = getattr(uploads, target)

    def blocking(**kwargs):
        entered.set()
        try:
            assert release.wait(5)
            return real(**kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(uploads, target, blocking)
    if audio:
        from deeptutor.services.asr import transcribe as asr

        async def transcription(*args, **kwargs):
            return {"text": "转写正文", "model": "test", "error": ""}

        monkeypatch.setattr(asr, "transcribe", transcription)
    upload = UploadFile(file=BytesIO(b"staged bytes"), filename="record.wav" if audio else "source.txt")
    task = asyncio.create_task(subjects_router.upload_subject_knowledge(
        subject.subject_id, BackgroundTasks(), files=[upload], type="auto"))
    contender = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(SubjectOperationError) as error:
            contender = subject_operations.acquire_activity(subject.subject_id, mode="exclusive")
        assert error.value.code == ErrorCode.KB_BUSY
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        deadline = time.monotonic() + 5
        while subject_operations.active_lease_kinds(subject.subject_id) and time.monotonic() < deadline:
            await asyncio.sleep(.01)
        assert subject_operations.active_lease_kinds(subject.subject_id) == ()
        assert uploads.reservation_for(subject.knowledge_bases / "textbook-kb") is None
    finally:
        if contender:
            contender.release()
        release.set()
        await asyncio.to_thread(finished.wait, 5)


@pytest.mark.asyncio
async def test_cancelled_index_await_does_not_release_a_running_worker(p1_runtime):
    from fastapi import BackgroundTasks

    subject = _subject(p1_runtime)
    upload = UploadFile(file=BytesIO(b"index bytes"), filename="source.txt")
    payload = await subjects_router.upload_subject_knowledge(
        subject.subject_id, BackgroundTasks(), files=[upload], type="auto")
    kb = subject.knowledge_bases / payload["kb_name"]
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def thread_body():
        entered.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()

    async def running():
        await asyncio.to_thread(thread_body)

    task = asyncio.create_task(uploads.run_reserved_index_task(kb, payload["task_id"], running))
    contender = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(SubjectOperationError) as error:
            contender = subject_operations.acquire_activity(subject.subject_id, mode="exclusive")
        assert error.value.code == ErrorCode.KB_BUSY
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        deadline = time.monotonic() + 5
        while uploads.reservation_for(kb) is not None and time.monotonic() < deadline:
            await asyncio.sleep(.01)
        assert uploads.reservation_for(kb) is None
    finally:
        if contender:
            contender.release()
        release.set()
        await asyncio.to_thread(finished.wait, 5)
        uploads.clear_reservation(kb, task_id=payload["task_id"])


def test_exclusive_lease_blocks_shared_from_another_thread(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    exclusive = subject_operations.acquire_activity(
        subject.subject_id, mode=subject_operations.EXCLUSIVE, kind="delete"
    )
    seen: list[BaseException] = []

    def contender() -> None:
        try:
            subject_operations.acquire_activity(subject.subject_id, kind="upload")
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            seen.append(exc)

    thread = threading.Thread(target=contender)
    thread.start()
    thread.join(5)
    assert seen and _code(seen[0]) == ErrorCode.KB_BUSY
    exclusive.release()

    lease = subject_operations.acquire_activity(subject.subject_id, kind="upload")
    lease.release()


def test_shared_lease_blocks_delete_and_export_and_preserves_data(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    marker = (subject.root / "profile.json").read_bytes()
    lease = subject_operations.acquire_activity(subject.subject_id, kind="upload")
    try:
        _assert_busy(store.delete_subject, subject.subject_id)
        assert subject.root.is_dir()
        assert (subject.root / "profile.json").read_bytes() == marker
        _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
    finally:
        lease.release()
    result = export_bundle.export_subject_bundle(subject.subject_id)
    assert result["zip_path"].is_file()


def test_upload_queue_holds_one_lease_until_the_worker_finishes(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _subject(p1_runtime)

    class Recorder:
        def __init__(self) -> None:
            self.tasks = []

        def add_task(self, func, *args, **kwargs):
            self.tasks.append((func, args, kwargs))

    background = Recorder()
    file = UploadFile(file=BytesIO(b"queued upload"), filename="queued.txt")
    payload = asyncio.run(
        subjects_router.upload_subject_knowledge(
            subject.subject_id, background, files=[file], type="auto"
        )
    )
    assert payload["operation"] == "index"
    assert background.tasks, "the route must queue the index worker"
    kb_dir = subject.knowledge_bases / payload["kb_name"]
    reservation = uploads.reservation_for(kb_dir)
    assert reservation is not None and reservation["task_id"] == payload["task_id"]
    assert subject_operations.active_lease_kinds(subject.subject_id) == ("upload",)

    # Accepted + queued: the same lease blocks both destructive operations,
    # including through the real HTTP routes.
    _assert_busy(store.delete_subject, subject.subject_id)
    _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
    from fastapi.testclient import TestClient

    with TestClient(helpers.build_route_app()) as client:
        deleted = client.delete(f"/api/v1/subjects/{subject.subject_id}")
        exported = client.get(f"/api/v1/subjects/{subject.subject_id}/export")
        assert deleted.status_code == 409 and deleted.json()["error"]["code"] == "kb_busy"
        assert exported.status_code == 409 and exported.json()["error"]["code"] == "kb_busy"
        assert subject.root.is_dir()

    entered, release = threading.Event(), threading.Event()
    worker_error: list[BaseException] = []

    async def run_worker() -> None:
        async def run() -> None:
            entered.set()
            await asyncio.to_thread(release.wait, 5)

        try:
            await uploads.run_reserved_index_task(
                kb_dir, payload["task_id"], run
            )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            worker_error.append(exc)

    async def scenario() -> None:
        task = asyncio.create_task(run_worker())
        assert await asyncio.to_thread(entered.wait, 5)
        # Executing worker: still busy, still the same continuous lease.
        _assert_busy(store.delete_subject, subject.subject_id)
        _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
        release.set()
        await task

    asyncio.run(scenario())
    assert not worker_error
    assert uploads.reservation_for(kb_dir) is None
    assert subject_operations.active_lease_kinds(subject.subject_id) == ()
    # The lease really ended with the worker, not with the HTTP response.
    assert export_bundle.export_subject_bundle(subject.subject_id)["zip_path"].is_file()


def test_two_subjects_do_not_block_each_other(p1_runtime: Path) -> None:
    a = _subject(p1_runtime, "互斥甲科")
    b = _subject(p1_runtime, "互斥乙科")
    exclusive_a = subject_operations.acquire_activity(
        a.subject_id, mode=subject_operations.EXCLUSIVE, kind="delete"
    )
    try:
        lease_b = subject_operations.acquire_activity(b.subject_id, kind="upload")
        lease_b.release()
    finally:
        exclusive_a.release()


def test_report_pipeline_holds_a_lease_until_failure_is_finalized(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()

    async def blocking_llm(*_args, **_kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        from deeptutor.services.llm.exceptions import LLMEmptyResponseError

        raise LLMEmptyResponseError("intentional")

    monkeypatch.setattr(report_mod, "_llm", blocking_llm)

    async def scenario() -> None:
        task = asyncio.create_task(
            report_mod.generate_report(
                subject.subject_id, title="忙报告", requirements=""
            )
        )
        assert await asyncio.to_thread(entered.wait, 5)
        _assert_busy(store.delete_subject, subject.subject_id)
        _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
        release.set()
        with pytest.raises(Exception):
            await task

    asyncio.run(scenario())
    assert subject_operations.active_lease_kinds(subject.subject_id) == ()
    assert export_bundle.export_subject_bundle(subject.subject_id)["zip_path"].is_file()


def test_cancelled_report_render_keeps_the_subject_busy_until_the_thread_ends(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _subject(p1_runtime)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    async def fake_llm(*_args, **_kwargs):
        return "# 报告\n\n取消后的渲染线程。\n"

    def blocking_render(*_args, **_kwargs):
        entered.set()
        try:
            assert release.wait(10)
            return False
        finally:
            finished.set()

    monkeypatch.setattr(report_mod, "_llm", fake_llm)
    monkeypatch.setattr(report_mod, "_render_in_owned_context", blocking_render)

    async def scenario() -> None:
        task = asyncio.create_task(
            report_mod.generate_report(
                subject.subject_id, title="取消报告", requirements=""
            )
        )
        assert await asyncio.to_thread(entered.wait, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # The async run is gone (failed metadata, no public URL), but the render
        # thread still holds its own lease: delete/export must stay busy.
        assert report_store.active_report_runs() == ()
        _assert_busy(store.delete_subject, subject.subject_id)
        _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
        release.set()
        assert await asyncio.to_thread(finished.wait, 10)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and subject_operations.active_lease_kinds(
            subject.subject_id
        ):
            await asyncio.sleep(0.02)
        assert subject_operations.active_lease_kinds(subject.subject_id) == ()
        assert not (subject.outputs / "reports").exists()
        assert export_bundle.export_subject_bundle(subject.subject_id)["zip_path"].is_file()
        assert store.delete_subject(subject.subject_id) is True

    asyncio.run(scenario())


def test_review_pack_route_holds_a_lease_until_its_cleanup(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    from deeptutor.services.pdf import review_guide

    async def blocking(*_args, **_kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        raise RuntimeError("intentional")

    # The route maps unexpected exceptions; the important part is the lease and
    # that no public review pack is published.
    monkeypatch.setattr(review_guide, "generate_guide_markdown", blocking)

    async def scenario() -> None:
        task = asyncio.create_task(
            subjects_router.generate_review_pack(subject.subject_id, format="pdf")
        )
        assert await asyncio.to_thread(entered.wait, 5)
        _assert_busy(store.delete_subject, subject.subject_id)
        _assert_busy(export_bundle.export_subject_bundle, subject.subject_id)
        release.set()
        with pytest.raises(Exception):
            await task

    asyncio.run(scenario())
    assert subject_operations.active_lease_kinds(subject.subject_id) == ()
    assert not list(subject.outputs.glob("review-guide-*.pdf"))


PROCESS_HOLDER = r'''
import json, sys
repo, sid, mode = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, repo)
from deeptutor.subjects import subject_operations
try:
    lease = subject_operations.acquire_activity(sid, mode=mode, kind="process-probe")
except Exception as exc:
    print(json.dumps({"ok": False, "code": getattr(exc, "code", None)}), flush=True)
    raise SystemExit(0)
print(json.dumps({"ok": True}), flush=True)
sys.stdin.readline()
lease.release()
'''


def _spawn_holder(subject_id: str, mode: str) -> tuple[subprocess.Popen, dict]:
    repo = str(Path(__file__).resolve().parents[2])
    proc = subprocess.Popen(
        [sys.executable, "-c", PROCESS_HOLDER, repo, subject_id, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    assert line, proc.stderr.read() if proc.stderr else "child produced no output"
    return proc, json.loads(line)


def _stop_holder(proc: subprocess.Popen) -> None:
    assert proc.stdin is not None
    proc.stdin.write("\n")
    proc.stdin.flush()
    proc.wait(timeout=10)


def test_cross_process_shared_and_exclusive_leases_really_conflict(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    # 1) This process holds shared; an independent process cannot take exclusive.
    shared = subject_operations.acquire_activity(subject.subject_id, kind="upload")
    proc, result = _spawn_holder(subject.subject_id, "exclusive")
    assert result == {"ok": False, "code": "kb_busy"}
    proc.wait(timeout=10)
    shared.release()

    # 2) This process holds exclusive; an independent process cannot take shared.
    exclusive = subject_operations.acquire_activity(
        subject.subject_id, mode=subject_operations.EXCLUSIVE, kind="export"
    )
    proc, result = _spawn_holder(subject.subject_id, "shared")
    assert result == {"ok": False, "code": "kb_busy"}
    proc.wait(timeout=10)
    exclusive.release()

    # 3) The process holds exclusive; the parent cannot take shared, and after
    #    the process proves release the parent can.
    proc, result = _spawn_holder(subject.subject_id, "exclusive")
    assert result == {"ok": True}
    _assert_busy(subject_operations.acquire_activity, subject.subject_id, kind="upload")
    _stop_holder(proc)
    lease = subject_operations.acquire_activity(subject.subject_id, kind="upload")
    lease.release()
