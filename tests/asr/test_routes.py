from __future__ import annotations

from pathlib import Path
import time
import uuid

import pytest

from deeptutor.services.asr import media
from deeptutor.services.asr.jobs import AsrJobService
from deeptutor.services.asr.provider import AsrProviderError
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode
from tests.asr.conftest import ROUTE_PREFIX, FakeProvider, upload_files, wav_bytes


def _install(monkeypatch, config, provider, tools):
    import deeptutor.api.routers.asr as asr_router

    monkeypatch.setattr(
        asr_router,
        "AsrJobService",
        lambda subject_id: AsrJobService(
            subject_id,
            config=config,
            provider_factory=lambda _config: provider,
            tools=tools,
        ),
    )


def _wait(client, subject_id: str, job_id: str, *, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{ROUTE_PREFIX}/{subject_id}/asr/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()["job"]
        if job["status"] in ("completed", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_post_returns_202_before_slow_provider_and_result_is_separate(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch
):
    provider = FakeProvider("slow text", delay=1.2)
    _install(monkeypatch, fake_config, provider, asr_tools)
    start = time.monotonic()
    response = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(0.5)),
        data={"request_id": str(uuid.uuid4())},
    )
    elapsed = time.monotonic() - start
    assert response.status_code == 202, response.text
    assert elapsed < 1.0, f"POST waited for provider: {elapsed:.2f}s"
    job = response.json()["job"]
    assert job["status"] in ("queued", "running")
    early = asr_client.get(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job['job_id']}/result"
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "asr_invalid_state"
    finished = _wait(asr_client, asr_subject.subject_id, job["job_id"], timeout=20)
    assert finished["status"] == "completed", finished
    assert len(provider.calls) == 1


def test_same_request_same_bytes_is_202_same_job_and_different_bytes_409(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch
):
    _install(monkeypatch, fake_config, FakeProvider("x"), asr_tools)
    request_id = str(uuid.uuid4())
    payload = wav_bytes(0.4)
    first = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(payload),
        data={"request_id": request_id},
    )
    assert first.status_code == 202
    second = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(payload),
        data={"request_id": request_id},
    )
    assert second.status_code == 202
    assert second.json()["job"]["job_id"] == first.json()["job"]["job_id"]
    conflict = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(payload + b"x"),
        data={"request_id": request_id},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "asr_request_conflict"


def test_invalid_ids_are_400_and_foreign_subject_is_404(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch, asr_runtime
):
    _install(monkeypatch, fake_config, FakeProvider("x"), asr_tools)
    bad = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(0.2)),
        data={"request_id": "not-a-uuid"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_input"
    missing = asr_client.get(f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{'g' * 32}")
    assert missing.status_code == 400
    foreign = asr_client.get(f"{ROUTE_PREFIX}/{'z' * 16}/asr/jobs")
    assert foreign.status_code == 404


def test_retry_after_failure_only_reprocesses_pending_chunk(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch
):
    from deeptutor.services.asr.provider import ProviderResult

    class Flaky:
        def __init__(self):
            self.calls = []

        async def transcribe_chunk(self, path, *, language="zh"):
            self.calls.append(str(path))
            if len(self.calls) == 1:
                raise AsrProviderError(ErrorCode.PROVIDER_UNAVAILABLE, reason="test")
            return ProviderResult(text="retry ok", model="fake-asr-model", attempts=1)

    provider = Flaky()
    _install(monkeypatch, fake_config, provider, asr_tools)
    created = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(0.3)),
        data={"request_id": str(uuid.uuid4())},
    )
    assert created.status_code == 202
    job_id = created.json()["job"]["job_id"]
    failed = _wait(asr_client, asr_subject.subject_id, job_id)
    assert failed["status"] == "failed"
    assert failed["can_retry"] is True
    retry = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job_id}/retry"
    )
    assert retry.status_code == 202
    completed = _wait(asr_client, asr_subject.subject_id, job_id)
    assert completed["status"] == "completed", completed
    assert len(provider.calls) == 2


def test_cancel_stops_before_publication_and_duplicate_cancel_is_200(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch
):
    provider = FakeProvider("cancel me", delay=0.8)
    _install(monkeypatch, fake_config, provider, asr_tools)
    created = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(0.3)),
        data={"request_id": str(uuid.uuid4())},
    )
    assert created.status_code == 202
    job_id = created.json()["job"]["job_id"]
    cancel = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job_id}/cancel"
    )
    assert cancel.status_code == 202, cancel.text
    finished = _wait(asr_client, asr_subject.subject_id, job_id)
    assert finished["status"] == "cancelled", finished
    duplicate = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job_id}/cancel"
    )
    assert duplicate.status_code == 200
    assert not (Path(asr_subject.materials) / "lecture" / "lecture.wav").exists()


def test_completed_job_get_does_not_mutate_tree_and_cross_subject_is_404(
    asr_subject, asr_client, asr_tools, fake_config, monkeypatch, asr_runtime
):
    from tests.phase1 import helpers

    other = helpers.make_subject(asr_runtime, "ASR科目B")
    _install(monkeypatch, fake_config, FakeProvider("done"), asr_tools)
    created = asr_client.post(
        f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs",
        files=upload_files(wav_bytes(0.3)),
        data={"request_id": str(uuid.uuid4())},
    )
    job_id = created.json()["job"]["job_id"]
    assert _wait(asr_client, asr_subject.subject_id, job_id)["status"] == "completed"

    def tree_digest(root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        return result

    before = tree_digest(Path(asr_subject.root))
    one = asr_client.get(f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs/{job_id}")
    two = asr_client.get(f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs")
    assert one.status_code == 200 and two.status_code == 200
    assert tree_digest(Path(asr_subject.root)) == before
    foreign = asr_client.get(f"{ROUTE_PREFIX}/{other.subject_id}/asr/jobs/{job_id}")
    assert foreign.status_code == 404


@pytest.mark.parametrize("limit", [0, 51, -1])
def test_list_limit_is_bounded(asr_subject, asr_client, limit):
    response = asr_client.get(f"{ROUTE_PREFIX}/{asr_subject.subject_id}/asr/jobs?limit={limit}")
    assert response.status_code == 422
