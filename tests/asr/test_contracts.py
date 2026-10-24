from __future__ import annotations

from dataclasses import replace
import uuid

import pytest

from deeptutor.services.asr import contracts
from deeptutor.services.voice.config import STTConfig
from deeptutor.subjects.errors import ASR_ERROR_SPECS, AsrErrorCode


def test_request_id_must_be_uuid4_and_job_id_is_hex():
    request_id = str(uuid.uuid4())
    job_id = contracts.request_id_job_id(request_id)
    assert job_id == uuid.UUID(request_id).hex
    assert contracts.valid_job_id(job_id)
    with pytest.raises(ValueError):
        contracts.request_id_job_id(str(uuid.uuid1()))
    with pytest.raises(ValueError):
        contracts.request_id_job_id("not-a-uuid")


def test_config_fingerprint_excludes_api_key_and_header_values():
    base = STTConfig(
        model="m",
        provider_name="custom",
        adapter="openai_compat",
        request_style="multipart",
        auth_style="bearer",
        api_key="key-one",
        base_url="https://user:secret@example.invalid/v1?token=one",
        extra_headers={"X-Secret": "one"},
    )
    rotated = STTConfig(
        model="m",
        provider_name="custom",
        adapter="openai_compat",
        request_style="multipart",
        auth_style="bearer",
        api_key="key-two",
        base_url="https://user:other@example.invalid/v1?token=two",
        extra_headers={"X-Secret": "two"},
    )
    assert contracts.config_fingerprint(base, "zh") == contracts.config_fingerprint(rotated, "zh")
    changed = replace(base, model="other")
    assert contracts.config_fingerprint(base, "zh") != contracts.config_fingerprint(changed, "zh")
    assert contracts.config_fingerprint(base, "en") != contracts.config_fingerprint(base, "zh")


def test_project_job_projects_dead_worker_as_interrupted_without_writing():
    manifest = {
        "job_id": "a" * 32,
        "subject_id": "s",
        "status": "running",
        "phase": "transcribing",
        "revision": 4,
        "created_at": "x",
        "updated_at": "y",
        "files": [{"file_index": 0, "name": "a.wav", "size_bytes": 12}],
        "progress": {"files_total": 1, "chunks_total": 2, "chunks_completed": 1,
                     "audio_total_ms": 2000, "audio_completed_ms": 1000},
        "worker": {"pid": 999999, "start_ticks": 1, "boot_id": "no"},
        "error": None,
    }
    view = contracts.project_job(manifest, worker_alive=False)
    assert view.status == "interrupted"
    assert view.can_retry is True
    assert view.can_cancel is False
    assert manifest["status"] == "running"  # projection is read-only


def test_asr_error_table_and_fixed_messages():
    expected = {
        AsrErrorCode.ASR_INPUT_TOO_LARGE: 400,
        AsrErrorCode.ASR_JOB_NOT_FOUND: 404,
        AsrErrorCode.ASR_PROTOCOL_UNSUPPORTED: 400,
        AsrErrorCode.ASR_RESOURCE_LIMIT: 400,
        AsrErrorCode.ASR_DURATION_LIMIT: 400,
        AsrErrorCode.ASR_INVALID_AUDIO: 400,
        AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE: 503,
        AsrErrorCode.ASR_PROVIDER_AUTH: 502,
        AsrErrorCode.ASR_PROVIDER_BILLING: 502,
        AsrErrorCode.ASR_PROVIDER_LIMIT: 502,
        AsrErrorCode.ASR_RATE_LIMITED: 429,
        AsrErrorCode.ASR_CONFIG_CHANGED: 409,
        AsrErrorCode.ASR_REQUEST_CONFLICT: 409,
        AsrErrorCode.ASR_INVALID_STATE: 409,
        AsrErrorCode.ASR_PUBLISH_CONFLICT: 409,
    }
    for code, status in expected.items():
        spec = ASR_ERROR_SPECS[code]
        assert spec.http_status == status
        assert spec.message
    assert ASR_ERROR_SPECS[AsrErrorCode.ASR_RATE_LIMITED].retryable is True
    assert ASR_ERROR_SPECS[AsrErrorCode.ASR_PROVIDER_AUTH].retryable is False


def test_limits_and_chunk_identity_are_stable():
    assert contracts.MAX_FILES == 16
    assert contracts.MAX_CHUNK_SECONDS == 180
    assert contracts.CHUNK_MAX_SAMPLES == 2_880_000
    assert contracts.chunk_id_for(0, 0, 2_880_000) == "f0-0-2880000"
    assert contracts.chunk_id_for(1, 10, 20) == "f1-10-20"


def test_progress_and_language_validation():
    progress = contracts.progress_defaults(2)
    assert progress["files_total"] == 2
    assert contracts.validate_language(None) == "zh"
    assert contracts.validate_language(" en ") == "en"
    with pytest.raises(ValueError):
        contracts.validate_language("a/b")
