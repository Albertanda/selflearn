from __future__ import annotations

import os
from pathlib import Path
import time
import uuid

import pytest

from deeptutor.services.asr import job_store
from deeptutor.subjects.errors import AsrErrorCode, AsrOperationError


def _staged(root: Path, data: bytes = b"RIFFdata") -> Path:
    path = root / f"stage-{uuid.uuid4().hex}.wav"
    path.write_bytes(data)
    return path


def _create(subject, root: Path, *, signature: str = "sig", data: bytes = b"RIFFdata"):
    job_id = uuid.uuid4().hex
    staged = _staged(root, data)
    manifest, created = job_store.create_job(
        subject.subject_id,
        job_id=job_id,
        request_id=str(uuid.uuid4()),
        signature=signature,
        language="zh",
        config_fingerprint="fingerprint",
        files=[
            {
                "staged_path": str(staged),
                "name": "讲 课.wav",
                "size_bytes": len(data),
                "sha256": __import__("hashlib").sha256(data).hexdigest(),
                "content_type": "audio/wav",
            }
        ],
    )
    return manifest, created, job_id


def test_list_missing_root_is_empty_and_read_only(asr_subject):
    root = Path(asr_subject.root) / ".asr_jobs"
    assert not root.exists()
    assert job_store.list_manifests(asr_subject.subject_id) == []
    assert not root.exists()


def test_manifest_revision_and_cleanup(asr_subject, tmp_path):
    manifest, created, job_id = _create(asr_subject, tmp_path)
    assert created is True
    assert manifest["status"] == "queued"
    updated = job_store.update_manifest(
        asr_subject.subject_id,
        job_id,
        lambda current: {**current, "status": "failed", "error": {"code": "x"}},
    )
    assert updated["revision"] == manifest["revision"] + 1
    assert updated["updated_at"]
    directory = job_store.job_dir(asr_subject.subject_id, job_id)
    assert (directory / "input").is_dir()
    assert (directory / "chunks").is_dir()
    job_store.cleanup_media(asr_subject.subject_id, job_id)
    assert not (directory / "input").exists()
    assert not (directory / "chunks").exists()
    assert (directory / "manifest.json").is_file()


def test_create_move_is_idempotent_and_conflict_is_explicit(asr_subject, tmp_path):
    first, created, job_id = _create(asr_subject, tmp_path, signature="same")
    assert created is True
    staged = _staged(tmp_path)
    second, created_again = job_store.create_job(
        asr_subject.subject_id,
        job_id=job_id,
        request_id="r",
        signature="same",
        language="zh",
        config_fingerprint="fingerprint",
        files=[
            {
                "staged_path": str(staged),
                "name": "讲 课.wav",
                "size_bytes": 8,
                "sha256": __import__("hashlib").sha256(b"RIFFdata").hexdigest(),
                "content_type": "audio/wav",
            }
        ],
    )
    assert created_again is False
    assert second["job_id"] == job_id
    with pytest.raises(AsrOperationError) as excinfo:
        job_store.create_job(
            asr_subject.subject_id,
            job_id=job_id,
            request_id="r",
            signature="different",
            language="zh",
            config_fingerprint="fingerprint",
            files=[
                {
                    "staged_path": str(_staged(tmp_path, b"other")),
                    "name": "讲 课.wav",
                    "size_bytes": 5,
                    "sha256": "0" * 64,
                    "content_type": "audio/wav",
                }
            ],
        )
    assert excinfo.value.code == AsrErrorCode.ASR_REQUEST_CONFLICT


def test_worker_claim_is_exclusive_and_release_is_idempotent(asr_subject, tmp_path):
    _manifest, _created, job_id = _create(asr_subject, tmp_path)
    first = job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id)
    assert first is not None
    assert first.active
    assert job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id) is None
    first.release()
    first.release()
    second = job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id)
    assert second is not None
    second.release()


def test_forked_child_release_does_not_unlock_parent(asr_subject, tmp_path):
    _manifest, _created, job_id = _create(asr_subject, tmp_path)
    claim = job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id)
    assert claim is not None
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        try:
            claim.release()
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert status == 0
    # The parent's claim is still held; the child closing its inherited fd must
    # not perform LOCK_UN on the shared open file description.
    assert job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id) is None
    claim.release()
    again = job_store.WorkerClaim.acquire(asr_subject.subject_id, job_id)
    assert again is not None
    again.release()


def test_worker_birth_and_alive_projection(asr_subject):
    birth = job_store.process_birth()
    assert birth["pid"] == os.getpid()
    assert job_store.worker_is_alive({"worker": birth}) is True
    stale = dict(birth)
    stale["start_ticks"] = (birth.get("start_ticks") or 0) + 1
    assert job_store.worker_is_alive({"worker": stale}) is False


def test_invalid_job_id_is_rejected(asr_subject):
    with pytest.raises(Exception) as excinfo:
        job_store.job_dir(asr_subject.subject_id, "../escape", create=False)
    assert getattr(excinfo.value, "http_status", None) == 400
