"""Independent ASR review: previously uncovered failure and recovery cases."""

import asyncio
from io import BytesIO
from pathlib import Path
import sys
import uuid

import httpx
import pytest
from starlette.datastructures import UploadFile

from deeptutor.services.asr import contracts, job_store, jobs, media, provider
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode
from tests.asr.conftest import FakeProvider, wav_bytes


def test_billing_rejection_is_distinct_and_not_retried(fake_config, tmp_path):
    path = media.make_silent_wav(tmp_path / "chunk.wav", 0.1)
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(402, json={"code": 30001, "message": "Insufficient balance"})

    client = provider.OpenAICompatibleProvider(
        fake_config,
        client_factory=lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(provider.AsrProviderError) as caught:
        asyncio.run(client.transcribe_chunk(path))
    assert caught.value.code.value == "asr_provider_billing"
    assert not caught.value.retryable
    assert len(calls) == 1


def test_endpoint_query_is_not_appended_to_path(fake_config):
    fake_config.base_url = "https://example.test/v1?region=cn"
    assert (
        provider.transcriptions_url(fake_config)
        == "https://example.test/v1/audio/transcriptions?region=cn"
    )
    old = contracts.config_fingerprint(fake_config, "zh")
    fake_config.base_url = "https://example.test/v1?region=us"
    assert contracts.config_fingerprint(fake_config, "zh") != old


def test_provider_checks_actual_chunk_size_before_network(fake_config, tmp_path):
    path = tmp_path / "large.wav"
    path.write_bytes(b"x" * 128)
    client = provider.OpenAICompatibleProvider(fake_config)
    client.capabilities = provider.ProviderCapabilities(100, 180, "multipart")
    with pytest.raises(provider.AsrProviderError) as caught:
        asyncio.run(client.transcribe_chunk(path))
    assert caught.value.code == AsrErrorCode.ASR_PROVIDER_LIMIT


def test_siliconflow_policy_requires_actual_provider_endpoint(fake_config):
    fake_config.provider_name = "siliconflow"
    fake_config.base_url = "https://evil-siliconflow.cn/v1"
    assert contracts.media_chunk_cap(fake_config) == (contracts.UNKNOWN_MAX_CHUNK_BYTES, 180)


def test_413_children_cannot_split_again():
    chunk = {
        "chunk_id": "f0-0-100",
        "file_index": 0,
        "start_sample": 0,
        "end_sample": 100,
        "split_depth": 1,
    }
    assert not jobs.AsrJobService._can_split({}, chunk)


def test_media_log_cap_stops_process_while_running():
    async def run():
        with pytest.raises(media.MediaError) as caught:
            await media._run(
                [
                    sys.executable,
                    "-c",
                    "import sys,time;sys.stdout.write('x'*100000);sys.stdout.flush();time.sleep(5)",
                ],
                timeout=1,
                output_cap=100,
            )
        assert caught.value.reason == "output_budget"

    asyncio.run(run())


def test_ffprobe_restricts_protocols_before_input():
    argv = media._probe_argv(media.MediaTools("ffmpeg", "ffprobe"), Path("/tmp/a.wav"))
    assert argv[argv.index("-protocol_whitelist") + 1] == "file,pipe"


def _service(subject, tools, config, p):
    return jobs.AsrJobService(
        subject.subject_id, config=config, provider_factory=lambda _: p, tools=tools
    )


async def _upload(service):
    return (
        await service.create_job(
            [UploadFile(filename="lecture.wav", file=BytesIO(wav_bytes(0.2)))],
            request_id=str(uuid.uuid4()),
        )
    )[0]


async def _terminal(service, jid):
    async with asyncio.timeout(8):
        while True:
            v = service.get_job(jid)
            if v.status in ("failed", "completed", "cancelled", "interrupted"):
                return v
            await asyncio.sleep(0.02)


def test_cancel_interrupts_inflight_provider(asr_subject, asr_tools, fake_config):
    class Blocking:
        def __init__(self):
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()

        async def transcribe_chunk(self, *args, **kwargs):
            self.started.set()
            try:
                await asyncio.sleep(30)
            finally:
                self.stopped.set()

    async def run():
        p = Blocking()
        s = _service(asr_subject, asr_tools, fake_config, p)
        v = await _upload(s)
        await asyncio.wait_for(p.started.wait(), 5)
        await s.cancel_job(v.job_id)
        await asyncio.wait_for(p.stopped.wait(), 1)
        assert (await _terminal(s, v.job_id)).status == "cancelled"

    asyncio.run(run())


def test_normal_publication_verifies_hashes_before_completed(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    async def run():
        s = _service(asr_subject, asr_tools, fake_config, FakeProvider())
        monkeypatch.setattr(s, "_final_hashes_match", lambda plan: False)
        v = await _upload(s)
        final = await _terminal(s, v.job_id)
        assert final.status == "failed"
        assert final.error["code"] == "asr_publish_conflict"
        assert (job_store.job_dir(s.subject_id, v.job_id) / "input").is_dir()

    asyncio.run(run())


def test_checkpoint_text_tampering_is_rejected_before_resume(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    async def run():
        p = FakeProvider("original")
        s = _service(asr_subject, asr_tools, fake_config, p)

        async def stop_publish(*args):
            raise provider.AsrProviderError(ErrorCode.PROVIDER_UNAVAILABLE)

        original = s._publish
        monkeypatch.setattr(s, "_publish", stop_publish)
        v = await _upload(s)
        assert (await _terminal(s, v.job_id)).status == "failed"
        m = job_store.read_manifest(s.subject_id, v.job_id)
        (job_store.job_dir(s.subject_id, v.job_id) / m["chunks"][0]["text_path"]).write_text(
            "tampered"
        )
        monkeypatch.setattr(s, "_publish", original)
        await s.retry_job(v.job_id)
        final = await _terminal(s, v.job_id)
        assert final.status == "failed" and final.error["code"] == "storage_corrupt"
        assert len(p.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize("crash_state", ["all", "partial", "conflict"])
def test_publishing_crash_recovers_without_retranscription(
    asr_subject, asr_tools, fake_config, monkeypatch, crash_state
):
    async def run():
        p = FakeProvider("saved")
        s = _service(asr_subject, asr_tools, fake_config, p)
        original = s._commit_published

        def crash(jid, manifest, texts, plan, **kwargs):
            if crash_state == "all":
                original(jid, manifest, texts, plan, **kwargs)
            else:
                target = Path(asr_subject.materials) / "lecture"
                target.mkdir(parents=True, exist_ok=True)
                text = target / "lecture.wav.transcript.txt"
                text.write_text("saved" if crash_state == "partial" else "later user edit")
            raise RuntimeError("injected crash after persisted publishing")

        monkeypatch.setattr(s, "_commit_published", crash)
        v = await _upload(s)
        assert (await _terminal(s, v.job_id)).status == "failed"
        monkeypatch.setattr(s, "_commit_published", original)
        await s.retry_job(v.job_id)
        final = await _terminal(s, v.job_id)
        if crash_state == "conflict":
            assert final.status == "failed" and final.error["code"] == "asr_publish_conflict"
            assert (
                Path(asr_subject.materials) / "lecture" / "lecture.wav.transcript.txt"
            ).read_text() == "later user edit"
        else:
            assert final.status == "completed"
        assert len(p.calls) == 1

    asyncio.run(run())


def test_profile_identity_is_frozen_but_key_rotation_is_allowed(fake_config):
    old = contracts.config_fingerprint(fake_config, "zh")
    fake_config.api_key = "rotated-secret"
    assert contracts.config_fingerprint(fake_config, "zh") == old
    fake_config.profile_id = "other-profile"
    assert contracts.config_fingerprint(fake_config, "zh") != old


def test_job_id_requires_uuid4_not_just_hex():
    assert not contracts.valid_job_id("a" * 32)
    assert not contracts.valid_job_id(uuid.uuid1().hex)
    assert contracts.valid_job_id(uuid.uuid4().hex)


def test_upload_batch_limit_is_enforced_before_writing_overflow(tmp_path):
    from deeptutor.subjects import uploads

    first = UploadFile(filename="a.wav", file=BytesIO(b"a" * 6))
    second = UploadFile(filename="b.wav", file=BytesIO(b"b" * 6))
    plan = uploads.plan_batch([first, second], type="lecture")
    with pytest.raises(Exception) as caught:
        asyncio.run(uploads.stage_files(plan, tmp_path, size_limit=100, batch_limit=10))
    assert caught.value.code == AsrErrorCode.ASR_INPUT_TOO_LARGE
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= 10


def test_media_budget_is_cumulative_across_commands(tmp_path):
    async def run():
        token = media.set_job_budget(tmp_path)
        try:
            media._BUDGET.get().remaining = 0.1
            with pytest.raises(media.MediaError) as caught:
                for _ in range(3):
                    await media._run(
                        [sys.executable, "-c", "import time;time.sleep(.06)"], timeout=1
                    )
            assert caught.value.reason == "media_timeout"
        finally:
            media.reset_job_budget(token)

    asyncio.run(run())


def test_interrupted_normalization_rebuilds_partial_scratch(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    async def run():
        original = media.normalize_to_wav
        failed = False

        async def interrupt(source, output, **kwargs):
            nonlocal failed
            if not failed:
                failed = True
                Path(str(output) + ".partial").write_bytes(b"partial-data")
                raise provider.AsrProviderError(ErrorCode.PROVIDER_UNAVAILABLE)
            return await original(source, output, **kwargs)

        monkeypatch.setattr(media, "normalize_to_wav", interrupt)
        p = FakeProvider("valid")
        s = _service(asr_subject, asr_tools, fake_config, p)
        v = await _upload(s)
        assert (await _terminal(s, v.job_id)).status == "failed"
        await s.retry_job(v.job_id)
        assert (await _terminal(s, v.job_id)).status == "completed"
        assert len(p.calls) == 1

    asyncio.run(run())


def test_shutdown_joins_commit_thread_before_unlock(
    asr_subject, asr_tools, fake_config, monkeypatch
):
    import threading

    from deeptutor.subjects import subject_operations

    async def run():
        entered, release = threading.Event(), threading.Event()
        s = _service(asr_subject, asr_tools, fake_config, FakeProvider())
        original = s._commit_published

        def held(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            original(*args, **kwargs)

        monkeypatch.setattr(s, "_commit_published", held)
        jobs.reset_shutdown_for_tests()
        v = await _upload(s)
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        shutdown = asyncio.create_task(jobs.shutdown_asr())
        try:
            await asyncio.sleep(0.05)
            assert not shutdown.done()
            with pytest.raises(Exception) as busy:
                subject_operations.acquire_activity(s.subject_id, mode=subject_operations.EXCLUSIVE)
            assert busy.value.code == ErrorCode.KB_BUSY
        finally:
            release.set()
            await shutdown
            jobs.reset_shutdown_for_tests()
        assert s.get_job(v.job_id).status == "interrupted"
        await s.retry_job(v.job_id)
        assert (await _terminal(s, v.job_id)).status == "completed"

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["normalize", "extract"])
def test_media_failure_removes_owned_partial_output(tmp_path, monkeypatch, operation):
    source = media.make_silent_wav(tmp_path / "input.wav", 0.1)
    output = tmp_path / "output.wav"

    async def failed_run(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"partial bytes")
        raise media.MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="work_budget")

    monkeypatch.setattr(media, "_run", failed_run)
    tools = media.MediaTools("/bin/true", "/bin/true")
    with pytest.raises(media.MediaError):
        if operation == "normalize":
            asyncio.run(media.normalize_to_wav(source, output, tools=tools))
        else:
            asyncio.run(media.extract_chunk(source, output, 0, 1600, tools=tools))
    assert not output.exists()
    assert not output.with_name(output.name + ".partial").exists()


def test_checkpoint_digest_refuses_symlinks(tmp_path):
    target = tmp_path / "file"
    target.write_text("private sentinel")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(Exception):
        job_store.sha256_file(link)
