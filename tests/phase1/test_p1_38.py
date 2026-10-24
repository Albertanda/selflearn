"""P1-38 行为测试：同步渲染 offload、线程用户上下文与取消不发布。

全部用**真实** asyncio/HTTP 请求验证，不 mock ``asyncio.to_thread``：

* 一个 Typst 编译被 Event 锁住时，第二个独立只读 HTTP 请求仍在释放前完成；
* worker thread 仍解析到发起请求的用户（非管理员）与同一 workspace，输出落在该
  用户目录；两个用户不串；
* 渲染器异常映射为 C02 ``render_failed``（不泄露原始异常文本）；
* 取消等待中的渲染后，即使线程稍后完成也没有正式目录/URL，报告 run 被收尾为
  failed 且 active 登记释放。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from types import SimpleNamespace

import httpx
import pytest

from deeptutor.api.routers import subjects as subjects_router
from deeptutor.multi_user.context import (
    get_current_user_or_none,
    reset_current_user,
    set_current_user,
    user_from_token_payload,
)
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_store, review_guide
from deeptutor.subjects import store
from tests.phase1 import helpers

ROUTE = helpers.ROUTE_PREFIX


def _pdf_bytes() -> bytes:
    from io import BytesIO

    import pymupdf

    buffer = BytesIO()
    document = pymupdf.open()
    document.new_page()
    document.save(buffer, garbage=3)
    document.close()
    return buffer.getvalue()


def _public_root() -> Path:
    return store.current_subject_paths().get_public_outputs_root()


@pytest.mark.asyncio
async def test_blocked_compile_does_not_block_a_second_http_request(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    entered = threading.Event()
    release = threading.Event()
    real_render = review_guide.render_pdf

    def blocking(markdown: str, path: Path, typst_bin: Path | None = None) -> bool:
        entered.set()
        if not release.wait(10):
            raise AssertionError("render was never released")
        return real_render(markdown, path, typst_bin)

    monkeypatch.setattr(review_guide, "render_pdf", blocking)
    transport = httpx.ASGITransport(app=helpers.build_route_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"})
        )
        assert await asyncio.to_thread(entered.wait, 5), "compile never started"
        # The compile is still blocked: this read-only request must finish now.
        listing = await asyncio.wait_for(client.get(ROUTE), timeout=2)
        assert listing.status_code == 200
        assert release.is_set() is False
        release.set()
        response = await asyncio.wait_for(task, timeout=15)

    assert response.status_code == 200, response.text
    assert (_public_root() / response.json()["path"]).is_file()


@pytest.mark.asyncio
async def test_report_route_keeps_responding_while_pdf_compile_is_blocked(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    entered = threading.Event()
    release = threading.Event()

    async def fake_llm(prompt: str, system: str) -> str:
        return "# 课程报告\n\n编译期间的正文。\n"

    def blocking(markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
        entered.set()
        if not release.wait(10):
            raise AssertionError("render was never released")
        Path(out_path).write_bytes(_pdf_bytes())
        return True

    monkeypatch.setattr(report_mod, "_llm", fake_llm)
    monkeypatch.setattr(report_mod, "_render_report_pdf", blocking)
    transport = httpx.ASGITransport(app=helpers.build_route_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(
                f"{ROUTE}/{subject.subject_id}/report",
                data={"title": "编译测试", "requirements": "要求"},
            )
        )
        assert await asyncio.to_thread(entered.wait, 5)
        listing = await asyncio.wait_for(client.get(f"{ROUTE}/{subject.subject_id}/profile"), timeout=2)
        assert listing.status_code == 200
        release.set()
        response = await asyncio.wait_for(task, timeout=15)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_render_thread_sees_the_non_admin_user_and_workspace(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = user_from_token_payload(
        SimpleNamespace(user_id="alice", username="alice", role="user")
    )
    token = set_current_user(user)
    try:
        created = store.create_subject("alice-report")
        subject_id = created["id"]
        expected_workspace = str(store.current_subject_paths().workspace_root)
        admin_workspace = str(p1_runtime)
        seen: dict[str, str | None] = {}
        real_render = review_guide.render_pdf

        def recording(markdown: str, path: Path, typst_bin: Path | None = None) -> bool:
            seen["user"] = get_current_user_or_none().id if get_current_user_or_none() else None
            seen["workspace"] = str(store.current_subject_paths().workspace_root)
            return real_render(markdown, path, typst_bin)

        monkeypatch.setattr(review_guide, "render_pdf", recording)
        name, relative = asyncio.run(
            subjects_router._publish_review_pack(subject_id, "# 指南\n\n正文。\n", "pdf")
        )
    finally:
        reset_current_user(token)

    assert seen["user"] == "alice"
    assert seen["workspace"] == expected_workspace
    assert seen["workspace"] != admin_workspace
    assert relative.startswith(f"subjects/{subject_id}/")
    assert name.startswith("review-guide-")


def test_render_exception_maps_to_render_failed_on_http(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    marker = "p1-38-RENDER-SECRET-91af"

    def exploding(markdown: str, path: Path, typst_bin: Path | None = None):
        raise RuntimeError(marker)

    monkeypatch.setattr(review_guide, "render_docx", exploding)
    response = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "docx"}
    )

    assert response.status_code == 502, response.text
    body = response.json()
    assert body["error"]["code"] == "render_failed"
    assert marker not in response.text
    assert "url" not in body


def test_report_render_exception_maps_to_render_failed_on_http(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    marker = "p1-38-REPORT-SECRET-5b2d"

    async def fake_llm(prompt: str, system: str) -> str:
        return "# 报告\n\n正文。\n"

    def exploding(markdown: str, chart_names, out_path: Path, typst_bin: Path):
        raise RuntimeError(marker)

    monkeypatch.setattr(report_mod, "_llm", fake_llm)
    monkeypatch.setattr(report_mod, "_render_report_pdf", exploding)
    response = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/report", data={"title": "报告"}
    )

    assert response.status_code == 502, response.text
    body = response.json()
    assert body["error"]["code"] == "render_failed"
    assert marker not in response.text
    assert "url" not in body


@pytest.mark.asyncio
async def test_cancelled_report_never_publishes_after_the_thread_finishes(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    async def fake_llm(prompt: str, system: str) -> str:
        return "# 报告\n\n取消测试。\n"

    def blocking(markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
        entered.set()
        try:
            if not release.wait(10):
                raise AssertionError("render was never released")
            Path(out_path).write_bytes(_pdf_bytes())
            return True
        finally:
            finished.set()

    monkeypatch.setattr(report_mod, "_llm", fake_llm)
    monkeypatch.setattr(report_mod, "_render_report_pdf", blocking)
    task = asyncio.create_task(
        report_mod.generate_report(
            subject.subject_id, title="取消测试", requirements="要求"
        )
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(finished.wait, 5)  # 等待线程真正结束

    reports_dir = _public_root() / "subjects" / subject.subject_id / "reports"
    assert not reports_dir.exists() or not any(
        path.is_dir() for path in reports_dir.iterdir()
    )
    assert report_store.active_report_runs() == ()
    runs = [path for path in (subject.root / "_report_runs").iterdir() if path.is_dir()]
    assert len(runs) == 1
    import json

    metadata = json.loads((runs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["files"] == []


@pytest.mark.asyncio
async def test_cancelled_review_pack_never_publishes(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking(markdown: str, path: Path, typst_bin: Path | None = None) -> bool:
        entered.set()
        try:
            if not release.wait(10):
                raise AssertionError("render was never released")
            Path(path).write_bytes(_pdf_bytes())
            return True
        finally:
            finished.set()

    monkeypatch.setattr(review_guide, "render_pdf", blocking)
    public_dir = _public_root() / "subjects" / subject.subject_id
    task = asyncio.create_task(
        subjects_router._publish_review_pack(subject.subject_id, "# 指南\n\n正文。\n", "pdf")
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(finished.wait, 5)

    leftovers = (
        [path.name for path in public_dir.iterdir() if "review-guide" in path.name]
        if public_dir.is_dir()
        else []
    )
    assert leftovers == []


@pytest.mark.parametrize("inside", [False, True])
def test_review_pack_rejects_parent_symlink_before_creating_subject_dir(
    p1_subjects, tmp_path, monkeypatch, inside
) -> None:
    from deeptutor.subjects.errors import SubjectOperationError, SubjectStorageError

    subject = p1_subjects["科目A"]
    root = _public_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "other-scope" if inside else tmp_path / "outside"
    target.mkdir()
    if (root / "subjects").exists():
        (root / "subjects").rename(root / "preserved-subjects")
    (root / "subjects").symlink_to(target, target_is_directory=True)

    def rendering(markdown, path, typst_bin=None):
        path.write_bytes(_pdf_bytes())
        return True

    monkeypatch.setattr(review_guide, "render_pdf", rendering)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        asyncio.run(subjects_router._publish_review_pack(subject.subject_id, "# 指南", "pdf"))
    assert list(target.iterdir()) == []


def test_review_pack_never_overwrites_a_preexisting_part_symlink(
    p1_subjects, tmp_path, monkeypatch
) -> None:
    import uuid

    from deeptutor.subjects.errors import SubjectOperationError, SubjectStorageError

    subject = p1_subjects["科目A"]
    token = "c" * 32
    monkeypatch.setattr(uuid, "uuid4", lambda: SimpleNamespace(hex=token))
    public = _public_root() / "subjects" / subject.subject_id
    public.mkdir(parents=True, exist_ok=True)
    victim = tmp_path / "keep.pdf"
    victim.write_bytes(b"keep me")
    part = public / f".review-guide-{token}.pdf.part"
    part.symlink_to(victim)

    def rendering(markdown, path, typst_bin=None):
        path.write_bytes(_pdf_bytes())
        return True

    monkeypatch.setattr(review_guide, "render_pdf", rendering)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        asyncio.run(subjects_router._publish_review_pack(subject.subject_id, "# 指南", "pdf"))
    assert victim.read_bytes() == b"keep me"
    assert part.is_symlink()
    assert not (public / f"review-guide-{token}.pdf").exists()


@pytest.mark.asyncio
async def test_review_pack_copy_does_not_block_http_and_cancellation_never_commits(
    p1_subjects, monkeypatch
) -> None:
    import shutil

    subject = p1_subjects["科目A"]
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    cleaned = threading.Event()
    real_copy, real_copyobj = shutil.copyfile, shutil.copyfileobj
    real_unlink = Path.unlink

    def unlinking(path, *args, **kwargs):
        result = real_unlink(path, *args, **kwargs)
        if path.name.startswith(".review-guide-") and path.name.endswith(".part"):
            cleaned.set()
        return result

    def blocking(operation):
        def copying(*args, **kwargs):
            entered.set()
            try:
                assert release.wait(5)
                return operation(*args, **kwargs)
            finally:
                finished.set()
        return copying

    monkeypatch.setattr(shutil, "copyfile", blocking(real_copy))
    monkeypatch.setattr(shutil, "copyfileobj", blocking(real_copyobj))
    monkeypatch.setattr(Path, "unlink", unlinking)
    monkeypatch.setattr(review_guide, "render_pdf",
                        lambda markdown, path, typst_bin=None: bool(path.write_bytes(_pdf_bytes())))
    watchdog = threading.Timer(2, release.set)
    watchdog.start()
    transport = httpx.ASGITransport(app=helpers.build_route_app())
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task = asyncio.create_task(subjects_router._publish_review_pack(
                subject.subject_id, "# 指南", "pdf"))
            assert await asyncio.to_thread(entered.wait, 5)
            response = await asyncio.wait_for(client.get(ROUTE), timeout=1)
            assert response.status_code == 200
            assert not release.is_set(), "public copy blocked the event loop"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
            assert await asyncio.to_thread(finished.wait, 5)
            assert await asyncio.to_thread(cleaned.wait, 5)
    finally:
        release.set()
        watchdog.cancel()
    public = _public_root() / "subjects" / subject.subject_id
    assert not list(public.glob("*review-guide*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_report_publication_copy_keeps_loop_responsive_and_cancel_never_commits(
    p1_subjects, monkeypatch, cancel
) -> None:
    entered, release = threading.Event(), threading.Event()
    finished, cleaned = threading.Event(), threading.Event()
    subject = p1_subjects["科目A"]
    original_copy = report_store._copy_and_hash

    def copying(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5)
            return original_copy(*args, **kwargs)
        finally:
            finished.set()

    async def writer(*args):
        return "# 报告\n\n发布复制测试。\n"

    monkeypatch.setattr(report_mod, "_llm", writer)
    monkeypatch.setattr(report_mod, "_render_report_pdf",
                        lambda md, names, path, binary: bool(path.write_bytes(_pdf_bytes())))
    monkeypatch.setattr(report_store, "_copy_and_hash", copying)
    import shutil
    real_rmtree = shutil.rmtree

    def removing(path, *args, **kwargs):
        result = real_rmtree(path, *args, **kwargs)
        if Path(path).name.startswith(".publishing-"):
            cleaned.set()
        return result

    monkeypatch.setattr(shutil, "rmtree", removing)
    watchdog = threading.Timer(2, release.set)
    watchdog.start()
    transport = httpx.ASGITransport(app=helpers.build_route_app())
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task = asyncio.create_task(report_mod.generate_report(
                subject.subject_id, title="发布测试", requirements="要求"))
            assert await asyncio.to_thread(entered.wait, 5)
            response = await asyncio.wait_for(client.get(ROUTE), timeout=1)
            assert response.status_code == 200
            assert not release.is_set(), "report publication copy blocked the event loop"
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                release.set()
                assert await asyncio.to_thread(cleaned.wait, 5)
                assert not list((_public_root() / "subjects" / subject.subject_id / "reports").glob("*/report.pdf"))
                assert report_store.active_report_runs() == ()
            else:
                release.set()
                result = await task
                assert result["status"] == "completed"
                assert (_public_root() / result["path"]).is_file()
            assert await asyncio.to_thread(finished.wait, 5)
    finally:
        release.set()
        watchdog.cancel()
