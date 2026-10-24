from __future__ import annotations

import asyncio
from io import BytesIO
import os
from pathlib import Path
import threading
import time
import uuid

import pytest
from starlette.datastructures import UploadFile

from deeptutor.services.asr import job_store, media
from deeptutor.services.asr.jobs import AsrJobService, reset_shutdown_for_tests, shutdown_asr
from deeptutor.services.asr.provider import ProviderResult
from deeptutor.services.voice.config import STTConfig
from deeptutor.subjects import subject_operations, uploads
from deeptutor.subjects.errors import ErrorCode


class BlockingProvider:
    def __init__(self):
        self.started = asyncio.Event()
        self.calls = 0

    async def transcribe_chunk(self, path, *, language="zh"):
        self.calls += 1
        self.started.set()
        await asyncio.sleep(30)
        return ProviderResult(text="never", model="m", attempts=1)


def _config() -> STTConfig:
    return STTConfig(
        model="fake",
        provider_name="custom",
        adapter="openai_compat",
        request_style="multipart",
        auth_style="bearer",
        api_key="sk-test",
        base_url="http://127.0.0.1:9/v1",
    )


def _upload() -> UploadFile:
    return UploadFile(filename="lecture.wav", file=BytesIO(media.make_silent_wav(Path("/tmp") / f"life-{uuid.uuid4().hex}.wav", 0.2).read_bytes()))


async def _wait_status(service: AsrJobService, job_id: str, wanted: set[str], timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = service.get_job(job_id)
        if view.status in wanted:
            return view
        await asyncio.sleep(0.05)
    raise AssertionError(f"status never became {wanted}")


def test_shutdown_interrupts_owned_worker_and_releases_claim(asr_subject, asr_tools):
    reset_shutdown_for_tests()

    async def run():
        provider = BlockingProvider()
        service = AsrJobService(
            asr_subject.subject_id,
            config=_config(),
            provider_factory=lambda _c: provider,
            tools=asr_tools,
        )
        view, _ = await service.create_job([_upload()], request_id=str(uuid.uuid4()))
        await asyncio.wait_for(provider.started.wait(), 5)
        await shutdown_asr()
        after = service.get_job(view.job_id)
        assert after.status == "interrupted"
        assert after.can_retry is True
        claim = job_store.WorkerClaim.acquire(asr_subject.subject_id, view.job_id)
        assert claim is not None
        claim.release()
        reset_shutdown_for_tests()

    asyncio.run(run())


def test_delete_and_export_are_blocked_by_worker_activity(asr_subject, asr_tools):
    reset_shutdown_for_tests()

    async def run():
        provider = BlockingProvider()
        service = AsrJobService(
            asr_subject.subject_id,
            config=_config(),
            provider_factory=lambda _c: provider,
            tools=asr_tools,
        )
        view, _ = await service.create_job([_upload()], request_id=str(uuid.uuid4()))
        await asyncio.wait_for(provider.started.wait(), 5)
        from deeptutor.subjects import export_bundle, store

        with pytest.raises(Exception) as delete_exc:
            store.delete_subject(asr_subject.subject_id)
        assert delete_exc.value.code == ErrorCode.KB_BUSY
        with pytest.raises(Exception) as export_exc:
            export_bundle.export_subject_bundle(asr_subject.subject_id)
        assert export_exc.value.code == ErrorCode.KB_BUSY
        await shutdown_asr()
        reset_shutdown_for_tests()

    asyncio.run(run())


def test_writer_latch_and_a_second_waiter_conflict(asr_subject):
    latch = subject_operations.acquire_audio_writer(asr_subject.subject_id, timeout=0)
    result = {}

    def second():
        try:
            subject_operations.acquire_audio_writer(asr_subject.subject_id, timeout=0.3)
        except Exception as exc:  # noqa: BLE001
            result["code"] = exc.code
        else:
            result["code"] = None

    thread = threading.Thread(target=second)
    thread.start()
    thread.join(2)
    assert result.get("code") == ErrorCode.KB_BUSY
    latch.release()
    again = subject_operations.acquire_audio_writer(asr_subject.subject_id, timeout=0)
    again.release()


def test_forked_child_cannot_unlock_parent_writer_latch(asr_subject):
    latch = subject_operations.acquire_audio_writer(asr_subject.subject_id, timeout=0)
    pid = os.fork()
    if pid == 0:  # pragma: no cover
        try:
            latch.release()
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert status == 0
    with pytest.raises(Exception) as excinfo:
        subject_operations.acquire_audio_writer(asr_subject.subject_id, timeout=0.1)
    assert excinfo.value.code == ErrorCode.KB_BUSY
    latch.release()
