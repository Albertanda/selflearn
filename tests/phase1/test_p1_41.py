"""P1-41: export HTTP returns a real, authenticated, downloadable ZIP."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import threading
import time
import zipfile

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from deeptutor.api.routers import outputs
from deeptutor.api.routers import subjects as subjects_router
from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser
from deeptutor.multi_user.paths import scope_for_user
from deeptutor.subjects import export_bundle, store, subject_operations
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers


def _subject(admin_root: Path, label: str = "下载科目") -> helpers.SubjectPaths:
    subject = helpers.make_subject(admin_root, label)
    (subject.root / "materials" / "lecture" / "download.txt").write_text(
        f"{subject.marker}-download", encoding="utf-8"
    )
    return subject


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(subjects_router.router, prefix="/api/v1/subjects")
    app.include_router(outputs.router, prefix="/api/outputs")
    return app


def _user(user_id: str) -> tuple[CurrentUser, object]:
    scope = scope_for_user(user_id, is_admin=False)
    return (
        CurrentUser(id=user_id, username=user_id, role="user", scope=scope),
        set_current_user(
            CurrentUser(id=user_id, username=user_id, role="user", scope=scope)
        ),
    )


def _manifest(payload: bytes) -> dict:
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.testzip() is None
        return json.loads(archive.read("manifest.json").decode("utf-8"))


@pytest.mark.asyncio
async def test_snapshot_cleanup_is_off_loop_and_cancellable_before_publication(p1_runtime, monkeypatch):
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    real_remove = export_bundle.shutil.rmtree

    def removing(path, *args, **kwargs):
        if Path(path).name == "content" or (Path(path) / "content").is_dir():
            entered.set()
            assert release.wait(5)
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(export_bundle.shutil, "rmtree", removing)
    watchdog = threading.Timer(2, release.set)
    watchdog.start()
    try:
        async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
            task = asyncio.create_task(subjects_router.export_subject_data(subject.subject_id, None))
            assert await asyncio.to_thread(entered.wait, 5)
            assert (await client.get("/api/v1/subjects")).status_code == 200
            assert not release.is_set(), "snapshot cleanup blocked the event loop"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
            deadline = time.monotonic() + 5
            while subject_operations.active_lease_kinds(subject.subject_id) and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert not list(subject.outputs.glob("subject-export-*.zip"))
            assert subject_operations.active_lease_kinds(subject.subject_id) == ()
    finally:
        release.set()
        watchdog.cancel()


def test_http_export_url_downloads_the_same_verified_zip(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)

    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/subjects/{subject.subject_id}/export")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["schema_version"] == 1
            assert len(body["export_id"]) == 32
            assert body["url"] == f"/api/outputs/subjects/{subject.subject_id}/{Path(body['path']).name}"
            assert body["path"] == f"subjects/{subject.subject_id}/{Path(body['path']).name}"
            assert body["size"] > 0
            assert str(p1_runtime) not in json.dumps(body)

            download = await client.get(body["url"])
            assert download.status_code == 200
            assert download.content[:2] == b"PK"
            assert len(download.content) == body["size"]
            manifest = _manifest(download.content)
            assert manifest["export_id"] == body["export_id"]

            # The private manifest is not a separate public route; only the ZIP URL exists.
            assert (await client.get(f"/api/outputs/subjects/{subject.subject_id}/manifest.json")).status_code == 404
            assert (await client.get(f"/api/outputs/subjects/{subject.subject_id}/.export-staging/x")).status_code == 404

    asyncio.run(scenario())


def test_export_failure_is_non_2xx_without_a_url(p1_runtime: Path, monkeypatch) -> None:
    subject = _subject(p1_runtime)

    def failing(_subject_id: str):
        from deeptutor.subjects import json_store

        raise SubjectOperationError(
            ErrorCode.STORAGE_IO,
            "本地数据读写失败，请重试。",
            http_status=500,
            retryable=True,
        )

    monkeypatch.setattr(export_bundle, "prepare_export_bundle", failing)

    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/subjects/{subject.subject_id}/export")
            assert response.status_code == 500
            body = response.json()
            assert "url" not in body
            assert body["error"]["code"] == "storage_io"

    asyncio.run(scenario())


def test_compression_never_blocks_another_http_read(p1_runtime: Path, monkeypatch) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    original = export_bundle._zip_content

    def blocking(content, zip_path):
        entered.set()
        assert release.wait(10)
        return original(content, zip_path)

    monkeypatch.setattr(export_bundle, "_zip_content", blocking)

    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            export_task = asyncio.create_task(
                client.get(f"/api/v1/subjects/{subject.subject_id}/export")
            )
            assert await asyncio.to_thread(entered.wait, 10)
            started = time.monotonic()
            read = await client.get("/api/v1/subjects")
            elapsed = time.monotonic() - started
            assert read.status_code == 200
            assert elapsed < 2.0, "event loop was blocked by ZIP compression"
            release.set()
            response = await export_task
            assert response.status_code == 200
            assert response.json()["url"]

    asyncio.run(scenario())


def test_cancelled_export_never_publishes_after_its_thread_ends(
    p1_runtime: Path, monkeypatch
) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    original = export_bundle._zip_content

    def blocking(content, zip_path):
        entered.set()
        assert release.wait(10)
        return original(content, zip_path)

    monkeypatch.setattr(export_bundle, "_zip_content", blocking)

    async def scenario() -> None:
        task = asyncio.create_task(
            subjects_router.export_subject_data(subject.subject_id, None)
        )
        assert await asyncio.to_thread(entered.wait, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        # The worker callback discards the preparation; no public name appears.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not list(subject.outputs.glob("subject-export-*.zip")):
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        assert list(subject.outputs.glob("subject-export-*.zip")) == []
        staging = p1_runtime / "user" / ".export-staging"
        assert not list(staging.glob("*"))
        assert subject_operations.active_lease_kinds(subject.subject_id) == ()

    asyncio.run(scenario())


def test_non_admin_users_with_the_same_subject_id_never_cross_directories(
    p1_runtime: Path,
) -> None:
    users: dict[str, CurrentUser] = {}
    subjects: dict[str, helpers.SubjectPaths] = {}
    tokens = []
    for user_id, marker in (("user-a", "alpha"), ("user-b", "beta")):
        user, token = _user(user_id)
        users[user_id] = user
        tokens.append(token)
        try:
            record = store.create_subject(f"同名{user_id}", term="2026春")
            subject = helpers.SubjectPaths(
                record["id"], p1_runtime, None, None, marker  # type: ignore[arg-type]
            )
        finally:
            reset_current_user(token)
        # Resolve the actual per-user paths with the same user context.
        from deeptutor.subjects.store import current_subject_paths

        _, token2 = _user(user_id)
        try:
            paths = current_subject_paths()
            root = paths.get_workspace_dir() / "subjects" / record["id"]
            out = paths.get_public_outputs_root() / "subjects" / record["id"]
            out.mkdir(parents=True, exist_ok=True)
            (root / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
            (root / "materials" / "lecture" / "who.txt").write_text(marker, encoding="utf-8")
        finally:
            reset_current_user(token2)
        subjects[user_id] = helpers.SubjectPaths(record["id"], p1_runtime, root, out, marker)  # type: ignore[arg-type]

    # Two concurrent export requests, each under its own non-admin context.
    async def run_one(user_id: str) -> tuple[str, bytes]:
        _, token = _user(user_id)
        try:
            payload = await subjects_router.export_subject_data(
                subjects[user_id].subject_id, None
            )
            from deeptutor.api.routers import outputs as outputs_mod

            download = await outputs_mod.read_output(payload["path"], None)
            return user_id, Path(download.path).read_bytes()
        finally:
            reset_current_user(token)

    async def scenario() -> dict[str, bytes]:
        results = await asyncio.gather(run_one("user-a"), run_one("user-b"))
        return dict(results)

    payloads = asyncio.run(scenario())
    from io import BytesIO

    for user_id, marker in (("user-a", "alpha"), ("user-b", "beta")):
        manifest = _manifest(payloads[user_id])
        assert manifest["subject"]["id"] == subjects[user_id].subject_id
        with zipfile.ZipFile(BytesIO(payloads[user_id])) as archive:
            assert archive.read("learning/materials/lecture/who.txt") == marker.encode()
            all_text = b"\n".join(archive.read(name) for name in archive.namelist())
        assert marker.encode() in all_text
        other = "beta" if marker == "alpha" else "alpha"
        assert other.encode() not in all_text

    # B's context cannot read A's relative output URL (same relative shape).
    from deeptutor.api.routers import outputs as outputs_mod

    relative = f"subjects/{subjects['user-a'].subject_id}/subject-export-{'0' * 32}.zip"
    _, token = _user("user-b")
    try:
        with pytest.raises(Exception):
            asyncio.run(outputs_mod.read_output(relative, None))
    finally:
        reset_current_user(token)


def test_unregistered_subject_export_is_404(p1_runtime: Path) -> None:
    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/subjects/not-registered/export")
            assert response.status_code == 404
            assert "url" not in response.json()

    asyncio.run(scenario())
