from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from deeptutor.services.asr import job_store, media
from deeptutor.services.asr.jobs import AsrJobService
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode
from tests.asr.conftest import ROUTE_PREFIX, FakeProvider, upload_files, wav_bytes


def _wait(client, subject_id: str, job_id: str, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{ROUTE_PREFIX}/{subject_id}/asr/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()["job"]
        if job["status"] in ("completed", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_async_job_completes_and_publishes_transcript(
    asr_subject, asr_client, asr_tools, fake_config, fake_provider, monkeypatch
):
    import deeptutor.api.routers.asr as asr_router

    # The route resolved its class at import time, so patch the router symbol
    # (not only the service module).
    monkeypatch.setattr(
        asr_router,
        "AsrJobService",
        lambda subject_id: AsrJobService(
            subject_id,
            config=fake_config,
            provider_factory=lambda config: fake_provider,
            tools=asr_tools,
        ),
    )
    request_id = str(uuid.uuid4())
    response = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(2.0)),
        data={"request_id": request_id, "language": "zh"},
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] in ("queued", "running")
    assert job["result_available"] is False
    finished = _wait(asr_client, asr_subject.subject_id, job["job_id"])
    assert finished["status"] == "completed", finished
    result = asr_client.get(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job['job_id']}/result"
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["operation"] == "transcribe"
    assert payload["files"] == ["lecture.wav"]
    assert payload["transcripts"][0]["file"] == "lecture.wav"
    assert payload["transcripts"][0]["text"] == "转写片段"
    target = Path(asr_subject.materials) / "lecture" / "lecture.wav"
    assert target.is_file()
    transcript = Path(asr_subject.materials) / "lecture" / "lecture.wav.transcript.txt"
    assert transcript.read_text(encoding="utf-8") == "转写片段"
    assert not (Path(asr_subject.knowledge_bases) / "lecture-kb").exists()
    private = Path(asr_subject.root) / ".asr_jobs" / job["job_id"]
    assert (private / "manifest.json").is_file()
    assert (private / "result.json").is_file()
    assert not (private / "input").exists()
    assert not (private / "chunks").exists()


def test_same_request_id_is_idempotent_and_different_content_conflicts(
    asr_subject, asr_tools, fake_config
):
    payload = wav_bytes(1.0)
    request_id = str(uuid.uuid4())
    service = AsrJobService(
        asr_subject.subject_id,
        config=fake_config,
        provider_factory=lambda config: FakeProvider("same"),
        tools=asr_tools,
    )

    async def _create(data: bytes):
        from io import BytesIO

        from starlette.datastructures import UploadFile

        upload = UploadFile(filename="lecture.wav", file=BytesIO(data))
        return await service.create_job([upload], request_id=request_id, language="zh")

    import asyncio

    first, created = asyncio.run(_create(payload))
    assert created is True
    second, created_again = asyncio.run(_create(payload))
    assert created_again is False
    assert second.job_id == first.job_id
    try:
        asyncio.run(_create(payload + b"x"))
    except Exception as exc:
        assert getattr(exc, "code", None) is not None
        assert exc.code.value == "asr_request_conflict"
    else:  # pragma: no cover
        raise AssertionError("different content must conflict")


def test_get_is_read_only_and_missing_jobs_do_not_create_a_tree(
    asr_subject, asr_client
):
    root = Path(asr_subject.root)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    response = asr_client.get(f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs")
    assert response.status_code == 200
    assert response.json() == {"jobs": []}
    assert not (root / ".asr_jobs").exists()
    missing = asr_client.get(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{uuid.uuid4().hex}"
    )
    assert missing.status_code == 404
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert after == before


def _plan_for(total: int, count: int):
    async def plan(media_probe, *, file_index=0, tools=None, max_chunk_seconds=180, detect_silence=True):
        step = total // count
        rows = []
        for index in range(count):
            start = index * step
            end = total if index == count - 1 else (index + 1) * step
            rows.append(
                media.PlannedChunk(
                    file_index=file_index,
                    chunk_index=index,
                    start_sample=start,
                    end_sample=end,
                )
            )
        return rows

    return plan


def _normalized_service(subject, tools, config, provider, monkeypatch):
    import deeptutor.services.asr.jobs as jobs_module

    service = AsrJobService(
        subject.subject_id,
        config=config,
        provider_factory=lambda _c: provider,
        tools=tools,
    )
    return service, jobs_module


def test_413_resplits_only_failed_range_and_preserves_other_chunks(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    import asyncio
    from io import BytesIO

    from starlette.datastructures import UploadFile

    from deeptutor.services.asr.provider import AsrProviderError, ProviderResult

    class SplitProvider:
        def __init__(self):
            self.calls = []
            self.failed = False

        async def transcribe_chunk(self, path, *, language="zh"):
            self.calls.append(Path(path).name)
            if not self.failed:
                self.failed = True
                raise AsrProviderError(AsrErrorCode.ASR_PROVIDER_LIMIT, status=413)
            return ProviderResult(text=f"T{len(self.calls)}", model="m", attempts=1)

    import deeptutor.services.asr.jobs as jobs_module

    async def fake_plan(*args, **kwargs):
        return await _plan_for(32000, 2)(*args, **kwargs)

    monkeypatch.setattr(jobs_module.media, "plan_chunks", fake_plan)
    provider = SplitProvider()
    service = AsrJobService(
        asr_subject.subject_id,
        config=fake_config,
        provider_factory=lambda _c: provider,
        tools=asr_tools,
    )

    async def run():
        upload = UploadFile(filename="lecture.wav", file=BytesIO(wav_bytes(2.0)))
        view, _ = await service.create_job([upload], request_id=str(uuid.uuid4()))
        for _ in range(200):
            current = service.get_job(view.job_id)
            if current.status in ("completed", "failed"):
                return current, service.get_result(view.job_id) if current.status == "completed" else None
            await asyncio.sleep(0.05)
        raise AssertionError("timeout")

    final, result = asyncio.run(run())
    assert final.status == "completed", final
    assert result["transcripts"][0]["text"] == "T2\nT3\nT4"
    assert len(provider.calls) == 4  # failed original + two halves + untouched second range


def test_retry_after_seventh_failure_skips_successful_chunks(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    import asyncio
    from io import BytesIO

    from starlette.datastructures import UploadFile

    from deeptutor.services.asr.provider import AsrProviderError, ProviderResult

    class SevenProvider:
        def __init__(self):
            self.calls = []

        async def transcribe_chunk(self, path, *, language="zh"):
            self.calls.append(Path(path).name)
            if len(self.calls) == 7:
                raise AsrProviderError(ErrorCode.PROVIDER_UNAVAILABLE)
            return ProviderResult(text="same sentence", model="m", attempts=1)

    import deeptutor.services.asr.jobs as jobs_module

    async def fake_plan(*args, **kwargs):
        return await _plan_for(32000, 8)(*args, **kwargs)

    monkeypatch.setattr(jobs_module.media, "plan_chunks", fake_plan)
    provider = SevenProvider()
    service = AsrJobService(
        asr_subject.subject_id,
        config=fake_config,
        provider_factory=lambda _c: provider,
        tools=asr_tools,
    )

    async def run():
        upload = UploadFile(filename="lecture.wav", file=BytesIO(wav_bytes(2.0)))
        view, _ = await service.create_job([upload], request_id=str(uuid.uuid4()))
        deadline = time.monotonic() + 20
        failed = None
        while time.monotonic() < deadline:
            current = service.get_job(view.job_id)
            if current.status == "failed":
                failed = current
                break
            await asyncio.sleep(0.05)
        assert failed is not None, "job never failed"
        first_six = list(provider.calls[:6])
        await service.retry_job(view.job_id)
        while time.monotonic() < deadline:
            current = service.get_job(view.job_id)
            if current.status == "completed":
                break
            await asyncio.sleep(0.05)
        assert service.get_job(view.job_id).status == "completed"
        assert provider.calls[:6] == first_six
        assert len(provider.calls) == 9  # 6 success + 1 failed + 2 retried
        result = service.get_result(view.job_id)
        assert result["transcripts"][0]["text"].count("same sentence") == 8

    asyncio.run(run())


def test_out_of_order_completion_merges_by_chunk_index_and_keeps_duplicates(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    import asyncio
    from io import BytesIO

    from starlette.datastructures import UploadFile

    from deeptutor.services.asr.provider import ProviderResult

    class PathProvider:
        async def transcribe_chunk(self, path, *, language="zh"):
            name = Path(path).stem
            # f0-<start>-<end>; return a deterministic label from the range.
            return ProviderResult(text=f"N{name}", model="m", attempts=1)

    import deeptutor.services.asr.jobs as jobs_module

    async def fake_plan(*args, **kwargs):
        return await _plan_for(32000, 3)(*args, **kwargs)

    monkeypatch.setattr(jobs_module.media, "plan_chunks", fake_plan)
    service = AsrJobService(
        asr_subject.subject_id,
        config=fake_config,
        provider_factory=lambda _c: PathProvider(),
        tools=asr_tools,
        transcription_order=lambda chunks: list(reversed(chunks)),
    )

    async def run():
        upload = UploadFile(filename="lecture.wav", file=BytesIO(wav_bytes(2.0)))
        view, _ = await service.create_job([upload], request_id=str(uuid.uuid4()))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = service.get_job(view.job_id)
            if current.status == "completed":
                return service.get_result(view.job_id)
            if current.status in ("failed", "interrupted"):
                raise AssertionError(current)
            await asyncio.sleep(0.05)
        raise AssertionError("timeout")

    result = asyncio.run(run())
    text = result["transcripts"][0]["text"]
    assert text.splitlines()[0].startswith("Nf0-0-")
    assert text.splitlines()[1].startswith("Nf0-10666-")
    assert text.splitlines()[2].startswith("Nf0-21332-")
    assert len(set(text.splitlines())) == 3
