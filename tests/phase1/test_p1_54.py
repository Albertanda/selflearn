"""P1-54: delete both trees, never fake success, and respect activity."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import time

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from deeptutor.api.routers import subjects as subjects_router
from deeptutor.services.pdf import report_store
from deeptutor.subjects import export_bundle, json_store, store, subject_operations
from deeptutor.subjects.errors import ErrorCode, StorageIOError, SubjectOperationError
from tests.phase1 import helpers


def _subject(admin_root: Path, label: str = "删除科目") -> helpers.SubjectPaths:
    subject = helpers.make_subject(admin_root, label)
    # Add bytes in both trees so deletion is visible, not just an empty shell.
    (subject.root / "materials" / "lecture" / "delete-me.txt").write_text(
        "delete me", encoding="utf-8"
    )
    import pymupdf

    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "delete")
        document.save(str(subject.outputs / f"review-guide-{'b' * 32}.pdf"))
    return subject


def _snapshot(root: Path) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        out[str(here.relative_to(root))] = ("dir", stat.S_IMODE(here.lstat().st_mode))
        for name in list(dirnames) + list(filenames):
            full = here / name
            info = full.lstat()
            rel = str(full.relative_to(root))
            if stat.S_ISLNK(info.st_mode):
                out[rel] = ("link", os.readlink(full))
            elif stat.S_ISDIR(info.st_mode):
                out[rel] = ("dir", stat.S_IMODE(info.st_mode))
            else:
                out[rel] = (
                    "file",
                    stat.S_IMODE(info.st_mode),
                    info.st_size,
                    hashlib.sha256(full.read_bytes()).hexdigest(),
                )
    return out


def _assert_busy(exc: SubjectOperationError) -> None:
    assert exc.code == ErrorCode.KB_BUSY
    assert exc.http_status == 409 and exc.retryable is True


def test_short_learning_write_participates_in_subject_exclusion(p1_runtime, monkeypatch):
    from deeptutor.subjects import wrong_book

    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    real_enter = json_store.JsonTransaction.__enter__
    errors = []

    def enter(tx):
        if tx.lock_dir == subject.root and threading.current_thread().name == "short-writer":
            entered.set()
            assert release.wait(5)
        return real_enter(tx)

    def writing():
        try:
            wrong_book.add_entry(subject.subject_id, question="并发学习记录")
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(json_store.JsonTransaction, "__enter__", enter)
    thread = threading.Thread(target=writing, name="short-writer")
    thread.start()
    contender = None
    try:
        assert entered.wait(5)
        with pytest.raises(SubjectOperationError) as error:
            contender = subject_operations.acquire_activity(subject.subject_id, mode="exclusive")
        _assert_busy(error.value)
    finally:
        if contender:
            contender.release()
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors


def test_late_learning_writer_cannot_resurrect_a_deleted_subject(p1_runtime, monkeypatch):
    from deeptutor.subjects import wrong_book

    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    real_dir = store.subject_dir
    errors = []
    delayed = False

    def directory(sid):
        nonlocal delayed
        path = real_dir(sid)
        if threading.current_thread().name == "late-writer" and not delayed:
            delayed = True
            entered.set()
            assert release.wait(5)
        return path

    def writing():
        try:
            wrong_book.add_entry(subject.subject_id, question="迟到学习记录")
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(store, "subject_dir", directory)
    thread = threading.Thread(target=writing, name="late-writer")
    thread.start()
    try:
        assert entered.wait(5)
        assert store.delete_subject(subject.subject_id)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not subject.root.exists(), "late JSON writer recreated the deleted tree"
    assert errors and errors[0].code == ErrorCode.SUBJECT_NOT_FOUND


def test_successful_delete_removes_only_this_subjects_two_trees(p1_runtime: Path) -> None:
    a = _subject(p1_runtime, "甲删除科")
    b = _subject(p1_runtime, "乙保留科")
    before_b_learning = _snapshot(b.root)
    before_b_outputs = _snapshot(b.outputs)
    learning, public = a.root, a.outputs

    assert store.delete_subject(a.subject_id) is True
    assert not learning.exists() and not public.exists()
    assert store.get_subject(a.subject_id) is None
    assert _snapshot(b.root) == before_b_learning
    assert _snapshot(b.outputs) == before_b_outputs
    assert store.get_subject(b.subject_id) is not None


def test_http_delete_is_real_and_subsequent_reads_are_404(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    with TestClient(helpers.build_route_app()) as client:
        response = client.delete(f"/api/v1/subjects/{subject.subject_id}")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "deleted"
        assert not subject.root.exists() and not subject.outputs.exists()
        assert client.get(f"/api/v1/subjects/{subject.subject_id}/knowledge").status_code == 404


def test_busy_report_blocks_delete_with_409_and_no_fake_deleted(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    lease = subject_operations.acquire_activity(subject.subject_id, kind="report")
    try:
        with pytest.raises(SubjectOperationError) as error:
            store.delete_subject(subject.subject_id)
        _assert_busy(error.value)
        assert subject.root.exists()
        assert store.get_subject(subject.subject_id) is not None
        # HTTP sees the same fixed C02 projection.
        with TestClient(helpers.build_route_app()) as client:
            response = client.delete(f"/api/v1/subjects/{subject.subject_id}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "kb_busy"
            assert response.json()["error"]["retryable"] is True
            assert "deleted" not in response.text
    finally:
        lease.release()
    assert store.delete_subject(subject.subject_id) is True


def test_concurrent_export_and_delete_never_overlap(p1_runtime: Path, monkeypatch) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    original = export_bundle._zip_content

    def blocking(content, zip_path):
        entered.set()
        assert release.wait(10)
        return original(content, zip_path)

    monkeypatch.setattr(export_bundle, "_zip_content", blocking)

    async def scenario() -> None:
        export_task = asyncio.create_task(
            subjects_router.export_subject_data(subject.subject_id, None)
        )
        assert await asyncio.to_thread(entered.wait, 10)
        with pytest.raises(SubjectOperationError) as error:
            await asyncio.to_thread(store.delete_subject, subject.subject_id)
        _assert_busy(error.value)
        assert subject.root.exists() and subject.outputs.exists()
        release.set()
        result = await export_task
        assert Path(subject.outputs / Path(result["path"]).name).is_file()
        # Export is done; delete's exclusive lease is available and removes both.
        assert await asyncio.to_thread(store.delete_subject, subject.subject_id) is True
        assert not subject.root.exists() and not subject.outputs.exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("which", ["learning", "public"])
def test_rmtree_failure_keeps_registry_and_can_be_retried(
    p1_runtime: Path, monkeypatch, which: str
) -> None:
    subject = _subject(p1_runtime)
    target = subject.root if which == "learning" else subject.outputs
    real_rmtree = store.shutil.rmtree
    failed = {"once": False}

    def failing(path, *args, **kwargs):
        if Path(path) == target and not failed["once"]:
            failed["once"] = True
            raise OSError("injected rmtree failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(store.shutil, "rmtree", failing)
    with pytest.raises(StorageIOError) as error:
        store.delete_subject(subject.subject_id)
    from deeptutor.subjects.errors import map_subject_exception

    mapped = map_subject_exception(error.value)
    assert mapped.code == ErrorCode.STORAGE_IO
    assert mapped.http_status == 500
    assert store.get_subject(subject.subject_id) is not None
    # The other tree is never removed when the first validation/removal failed.
    if which == "learning":
        assert subject.root.exists() and subject.outputs.exists()
    else:
        assert not subject.root.exists() and subject.outputs.exists()

    monkeypatch.setattr(store.shutil, "rmtree", real_rmtree)
    assert store.delete_subject(subject.subject_id) is True
    assert not subject.root.exists() and not subject.outputs.exists()
    assert store.get_subject(subject.subject_id) is None


def test_registry_write_failure_keeps_registration_and_fails_loudly(
    p1_runtime: Path, monkeypatch
) -> None:
    subject = _subject(p1_runtime)
    real = json_store.atomic_write_json
    failed = {"once": False}

    def failing(path, data):
        if Path(path).name == "index.json" and not failed["once"]:
            failed["once"] = True
            raise OSError("injected registry write failure")
        return real(path, data)

    monkeypatch.setattr(json_store, "atomic_write_json", failing)
    with pytest.raises(StorageIOError) as error:
        store.delete_subject(subject.subject_id)
    from deeptutor.subjects.errors import map_subject_exception

    assert map_subject_exception(error.value).code == ErrorCode.STORAGE_IO
    assert store.get_subject(subject.subject_id) is not None
    # The cleanup already happened; the failure is reported honestly, and a
    # retry (with the fault gone) can finish the registry step.
    assert not subject.root.exists() and not subject.outputs.exists()
    monkeypatch.setattr(json_store, "atomic_write_json", real)
    assert store.delete_subject(subject.subject_id) is True
    assert store.get_subject(subject.subject_id) is None


def test_deep_symlink_anywhere_is_refused_before_any_deletion(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    victim = p1_runtime / "victim-keep.txt"
    victim.write_text("keep", encoding="utf-8")
    deep = subject.outputs / "reports" / "nested"
    deep.mkdir(parents=True, exist_ok=True)
    (deep / "dangling").symlink_to(p1_runtime / "does-not-exist")
    before_learning = _snapshot(subject.root)
    before_public = _snapshot(subject.outputs)

    with pytest.raises(StorageIOError) as error:
        store.delete_subject(subject.subject_id)
    from deeptutor.subjects.errors import map_subject_exception

    assert map_subject_exception(error.value).code == ErrorCode.STORAGE_IO
    assert victim.read_text(encoding="utf-8") == "keep"
    assert _snapshot(subject.root) == before_learning
    assert _snapshot(subject.outputs) == before_public
    assert store.get_subject(subject.subject_id) is not None


def test_unregistered_delete_is_false_and_touches_nothing(p1_runtime: Path) -> None:
    assert store.delete_subject("never-registered") is False
    assert store.get_subject("never-registered") is None


def test_old_session_after_delete_gets_subject_not_found_without_a_provider_call(
    p1_runtime: Path, monkeypatch
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.api.routers import unified_ws
    from deeptutor.services.session import get_turn_runtime_manager

    subject = _subject(p1_runtime)
    runtime = get_turn_runtime_manager()
    session = asyncio.run(runtime.store.create_session())
    session_id = session["id"]
    asyncio.run(
        runtime.store.add_message(
            session_id,
            role="user",
            content="旧问题",
            capability="chat",
            metadata={
                "request_snapshot": {
                    "content": "旧问题",
                    "capability": "chat",
                    "subject_id": subject.subject_id,
                }
            },
        )
    )

    import deeptutor.services.llm.factory as factory

    def explode(*_args, **_kwargs):
        raise AssertionError("a deleted subject must never reach a provider")

    monkeypatch.setattr(factory, "complete_response", explode, raising=False)
    monkeypatch.setattr(factory, "complete", explode, raising=False)
    assert store.delete_subject(subject.subject_id) is True

    app = FastAPI()
    app.include_router(unified_ws.router, prefix="/api/v1")
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "regenerate", "session_id": session_id})
            event = None
            for _ in range(20):
                payload = websocket.receive_json()
                if payload.get("type") == "error":
                    event = payload
                    break
            assert event is not None
            assert event["metadata"]["error"]["code"] == "subject_not_found"
            assert event["metadata"]["status"] == "rejected"
            assert str(p1_runtime) not in json.dumps(event, ensure_ascii=False)
            websocket.send_json({"type": "ping"})
            pong = None
            for _ in range(10):
                payload = websocket.receive_json()
                if payload.get("type") == "pong":
                    pong = payload
                    break
            assert pong is not None
