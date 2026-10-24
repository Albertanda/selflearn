"""ASR-R1 durable job service.

The POST route records a job and returns 202 before any probe, ffmpeg or
provider call.  This module owns the worker: probe/plan, checkpointed chunks,
ordered merge, transactional publication and recovery.

Design invariants enforced here (see CONTRACTS D3-D6):

* the worker claim is an OS ``flock``; repeated retry cannot start two workers;
* the main subject lease is shared and held for the worker's whole lifetime;
* the separate audio-writer latch is held only around publication;
* every successful chunk is atomically written before its checkpoint advances;
* merge order is file/chunk order, never completion order;
* completed requires every source range to be successful and every final hash
  to match the prepared publication plan;
* cancellation before publication is real; after publication starts it is 409;
* a dead worker projects as ``interrupted`` on GET and may be explicitly
  retried from its checkpoint.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
import os
from pathlib import Path
import shutil
import threading
from typing import Any, Callable, Mapping, Sequence

from deeptutor.services.asr import job_store, media
from deeptutor.services.asr.contracts import (
    ACTIVE_STATUSES,
    CHUNK_PENDING,
    CHUNK_SAMPLE_RATE,
    CHUNK_SUCCESS,
    MAX_BATCH_BYTES,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_DURATION_MS,
    MAX_WORK_BYTES,
    JobError,
    JobView,
    config_fingerprint,
    progress_defaults,
    project_job,
    request_id_job_id,
    request_signature,
    utc_now,
    validate_language,
)
from deeptutor.services.asr.media import MediaProbe, MediaTools
from deeptutor.services.asr.provider import (
    AsrProviderError,
    OpenAICompatibleProvider,
)
from deeptutor.services.voice.config import STTConfig
from deeptutor.subjects import json_store, store, subject_operations, uploads
from deeptutor.subjects.errors import (
    AsrErrorCode,
    AsrOperationError,
    ErrorCode,
    SubjectOperationError,
    asr_error,
    subject_error,
)

logger = logging.getLogger(__name__)

_TASKS: dict[tuple[str, str, str], asyncio.Task[Any]] = {}
_SHUTTING_DOWN = False
_TASKS_LOCK = threading.Lock()


class _JobCancelled(Exception):
    pass


def _register_task(subject_id: str, job_id: str, task: asyncio.Task[Any], cleanup: Callable[[], None]) -> None:
    key = (str(store.subject_dir(subject_id)), subject_id, job_id)
    with _TASKS_LOCK:
        _TASKS[key] = task

    def _done(_task: asyncio.Task[Any]) -> None:
        cleanup()  # Also runs if shutdown cancels a task before its first step.
        with _TASKS_LOCK:
            if _TASKS.get(key) is task:
                _TASKS.pop(key, None)

    task.add_done_callback(_done)


def active_task_count(subject_id: str | None = None) -> int:
    with _TASKS_LOCK:
        if subject_id is None:
            return len(_TASKS)
        return sum(1 for key in _TASKS if key[1] == subject_id)


async def shutdown_asr() -> int:
    """Cancel this process's ASR workers and leave persisted recovery state.

    No startup scan and no cross-user enumeration are performed.  Each worker
    catches cancellation, persists ``interrupted``/``cancelled`` as appropriate
    and releases its claim/lease/latch before this function returns.
    """
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = True
    with _TASKS_LOCK:
        tasks = list(_TASKS.values())
    for task in tasks:
        task.cancel()
    if tasks:
        # A publication thread may still be committing. Its worker keeps the
        # activity/claim until it has joined, even during shutdown.
        await asyncio.gather(*tasks, return_exceptions=True)
    return len(tasks)


def reset_shutdown_for_tests() -> None:  # pragma: no cover - explicit helper
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = False


def _path_in_job(directory: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    return json_store.confined(directory, directory / relative)


def _job_input_path(directory: Path, manifest: Mapping[str, Any], index: int) -> Path:
    files = manifest.get("files") or []
    row = files[index]
    return _path_in_job(directory, str(row.get("input_path") or ""))


def _normalized_path(directory: Path, manifest: Mapping[str, Any], index: int) -> Path:
    row = manifest["files"][index]
    relative = str(row.get("normalized_path") or "")
    if not relative:
        return json_store.confined(directory / "normalized", directory / "normalized" / f"f{index:04d}.wav")
    return _path_in_job(directory, relative)


def _chunk_path(directory: Path, chunk_id: str) -> Path:
    return json_store.confined(directory / "chunks", directory / "chunks" / f"{chunk_id}.wav")


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _target_state(materials: Path, name: str) -> dict[str, Any]:
    target = json_store.confined(materials, materials / name)
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "size": 0}
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    import stat

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    size, digest = job_store.sha256_file(target)
    return {"exists": True, "sha256": digest, "size": size}


class AsrJobService:
    """One subject's job operations.

    ``config``/``provider_factory`` are injection seams for tests and the
    bounded live smoke.  In normal operation neither is supplied: the active
    STT config is resolved from the current user's catalog and the API key is
    retained only in this process's memory.
    """

    def __init__(
        self,
        subject_id: str,
        *,
        config: STTConfig | None = None,
        provider_factory: Callable[[STTConfig], Any] | None = None,
        tools: MediaTools | None = None,
        transcription_order: Callable[[list[dict[str, Any]]], Sequence[dict[str, Any]]] | None = None,
    ) -> None:
        if not store.is_valid_subject_id(subject_id):
            raise store.InvalidSubjectIdError(subject_id)
        if store.get_subject(subject_id) is None:
            raise store.SubjectNotFoundError(subject_id)
        self.subject_id = subject_id
        self._config_override = config
        self._provider_factory = provider_factory
        self._tools = tools
        self._transcription_order = transcription_order

    # -- config ---------------------------------------------------------------
    def _config(self) -> STTConfig:
        if self._config_override is not None:
            return self._config_override
        try:
            from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config

            return resolve_stt_runtime_config()
        except SubjectOperationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise subject_error(ErrorCode.PROVIDER_UNAVAILABLE, cause=exc) from exc

    def _provider(self, config: STTConfig) -> Any:
        # Validate protocol/capability before a worker is accepted.
        from deeptutor.services.asr.provider import capabilities

        capabilities(config)
        if self._provider_factory is not None:
            return self._provider_factory(config)
        return OpenAICompatibleProvider(config)

    # -- read API -------------------------------------------------------------
    def list_jobs(self, limit: int = 20) -> list[JobView]:
        return [
            job_store.job_view(self.subject_id, manifest)
            for manifest in job_store.list_manifests(self.subject_id, limit=limit)
        ]

    def get_job(self, job_id: str) -> JobView:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
        except job_store.JobNotFound:
            raise asr_error(AsrErrorCode.ASR_JOB_NOT_FOUND) from None
        return job_store.job_view(self.subject_id, manifest)

    def get_result(self, job_id: str) -> dict[str, Any]:
        view = self.get_job(job_id)
        if view.status != "completed":
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        try:
            payload = job_store.read_result(self.subject_id, job_id)
        except job_store.JobNotFound:
            raise asr_error(AsrErrorCode.ASR_JOB_NOT_FOUND) from None
        if not isinstance(payload, dict) or payload.get("job_id") != job_id:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        return payload

    # -- create ---------------------------------------------------------------
    async def create_job(
        self,
        files: Sequence[Any],
        *,
        request_id: str,
        language: str = "zh",
    ) -> tuple[JobView, bool]:
        if not files:
            raise json_store.invalid_input("没有收到文件")
        if len(files) > MAX_FILES:
            raise asr_error(AsrErrorCode.ASR_INPUT_TOO_LARGE)
        try:
            job_id = request_id_job_id(request_id)
        except ValueError as exc:
            raise json_store.invalid_input("request_id 必须是 UUID4") from exc
        try:
            chosen_language = validate_language(language)
        except ValueError as exc:
            raise json_store.invalid_input("语言参数无效") from exc

        config = self._config()
        self._provider(config)  # protocol rejection before 202
        fingerprint = config_fingerprint(config, chosen_language)
        lease = subject_operations.acquire_activity(self.subject_id, kind="asr")
        try:
            plan = uploads.plan_batch(files, type="lecture")
            with uploads.staging_root(self.subject_id) as staging:
                staged = await uploads.stage_files(
                    plan, staging, size_limit=MAX_FILE_BYTES, batch_limit=MAX_BATCH_BYTES
                )
                total = sum(item.size for item in staged)
                if total > MAX_BATCH_BYTES:
                    raise asr_error(AsrErrorCode.ASR_INPUT_TOO_LARGE)
                infos = [
                    {
                        "staged_path": str(item.path),
                        "name": item.entry.name,
                        "size_bytes": item.size,
                        "sha256": item.sha256,
                        "content_type": item.entry.mime or "application/octet-stream",
                    }
                    for item in staged
                ]
                signature = request_signature(
                    [{"name": item["name"], "sha256": item["sha256"]} for item in infos],
                    language=chosen_language,
                    fingerprint=fingerprint,
                )
                manifest, created = job_store.create_job(
                    self.subject_id,
                    job_id=job_id,
                    request_id=request_id,
                    signature=signature,
                    language=chosen_language,
                    config_fingerprint=fingerprint,
                    files=infos,
                )
                if not created:
                    lease.release()
                    return job_store.job_view(self.subject_id, manifest), False
                manifest = job_store.update_manifest(
                    self.subject_id,
                    job_id,
                    lambda current: self._with_model(current, config.model),
                )
                claim = job_store.WorkerClaim.acquire(self.subject_id, job_id)
                if claim is None:
                    raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
                try:
                    manifest = job_store.update_manifest(
                        self.subject_id,
                        job_id,
                        lambda current: self._queued_with_worker(current, claim.birth),
                    )
                    task = asyncio.create_task(
                        self._run_worker(job_id, claim, lease, config)
                    )
                    _register_task(self.subject_id, job_id, task, lambda: (claim.release(), lease.release()))
                except BaseException:
                    claim.release()
                    raise
                return project_job(manifest, worker_alive=True), True
        except BaseException:
            lease.release()
            raise

    @staticmethod
    def _with_model(manifest: dict[str, Any], model: str) -> dict[str, Any]:
        manifest["provider_model"] = str(model)
        return manifest

    @staticmethod
    def _queued_with_worker(manifest: dict[str, Any], birth: dict[str, Any]) -> dict[str, Any]:
        manifest["status"] = "queued"
        manifest["phase"] = "queued"
        manifest["worker"] = dict(birth)
        manifest["cancel_requested"] = False
        return manifest

    # -- cancel / retry -------------------------------------------------------
    async def cancel_job(self, job_id: str) -> tuple[JobView, bool]:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
        except job_store.JobNotFound:
            raise asr_error(AsrErrorCode.ASR_JOB_NOT_FOUND) from None
        status = str(manifest.get("status") or "queued")
        if status == "completed":
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        if status == "cancelled":
            return job_store.job_view(self.subject_id, manifest), False
        if manifest.get("publish_started") or manifest.get("phase") == "publishing":
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)

        claim = job_store.WorkerClaim.acquire(self.subject_id, job_id)
        if claim is not None:
            try:
                # Cancellation owns the claim, so no worker can race cleanup.
                manifest = job_store.read_manifest(self.subject_id, job_id)
                if manifest.get("status") == "completed" or manifest.get("publish_started"):
                    raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
                job_store.cleanup_media(self.subject_id, job_id)
                updated = job_store.update_manifest(
                    self.subject_id, job_id, self._cancelled_manifest,
                )
                return job_store.job_view(self.subject_id, updated), True
            finally:
                claim.release()

        updated = job_store.update_manifest(
            self.subject_id,
            job_id,
            lambda current: self._cancelling_manifest(current),
        )
        return job_store.job_view(self.subject_id, updated), True

    @staticmethod
    def _cancelled_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("publish_started"):
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        manifest["status"] = "cancelled"
        manifest["phase"] = "queued"
        manifest["cancel_requested"] = True
        manifest["error"] = None
        return manifest

    @staticmethod
    def _cancelling_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("status") in ("completed", "cancelled"):
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        if manifest.get("publish_started") or manifest.get("phase") == "publishing":
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        manifest["cancel_requested"] = True
        manifest["status"] = "cancelling"
        return manifest

    async def retry_job(self, job_id: str) -> tuple[JobView, bool]:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
        except job_store.JobNotFound:
            raise asr_error(AsrErrorCode.ASR_JOB_NOT_FOUND) from None
        status = str(manifest.get("status") or "queued")
        projected = project_job(manifest, worker_alive=job_store.worker_is_alive(manifest))
        if status not in ("failed", "interrupted") and projected.status != "interrupted":
            if status in ACTIVE_STATUSES:
                return projected, False
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)

        claim = job_store.WorkerClaim.acquire(self.subject_id, job_id)
        if claim is None:
            # Failure can become visible just before the old worker releases
            # its claim. Do not lose a user's explicit retry in that window.
            deadline = asyncio.get_running_loop().time() + 5
            while claim is None:
                if asyncio.get_running_loop().time() >= deadline:
                    raise subject_error(ErrorCode.KB_BUSY)
                await asyncio.sleep(.05)
                claim = job_store.WorkerClaim.acquire(self.subject_id, job_id)
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
            if manifest.get("status") in ("completed", "cancelled"):
                raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
            config = self._config()
            fingerprint = config_fingerprint(config, str(manifest.get("language") or "zh"))
            if fingerprint != manifest.get("config_fingerprint"):
                raise asr_error(AsrErrorCode.ASR_CONFIG_CHANGED)
            self._provider(config)
            lease = subject_operations.acquire_activity(self.subject_id, kind="asr")
        except BaseException:
            claim.release()
            raise

        def _retry(current: dict[str, Any]) -> dict[str, Any]:
            if current.get("publish_started") or current.get("phase") == "publishing":
                current["status"] = "running"
                current["phase"] = "publishing"
            else:
                current["status"] = "queued"
                current["phase"] = "queued"
            current["cancel_requested"] = False
            current["error"] = None
            current["worker"] = claim.birth
            current["attempts"] = int(current.get("attempts") or 0) + 1
            return current

        try:
            updated = job_store.update_manifest(self.subject_id, job_id, _retry)
            task = asyncio.create_task(self._run_worker(job_id, claim, lease, config))
            _register_task(self.subject_id, job_id, task, lambda: (claim.release(), lease.release()))
        except BaseException:
            claim.release()
            lease.release()
            raise
        return project_job(updated, worker_alive=True), True

    # -- worker ---------------------------------------------------------------
    async def _run_worker(
        self,
        job_id: str,
        claim: job_store.WorkerClaim,
        lease: subject_operations.ActivityLease,
        config: STTConfig,
    ) -> None:
        current_task = asyncio.current_task()
        async def watch_cancel():
            while True:
                await asyncio.sleep(.05)
                state = job_store.read_manifest(self.subject_id, job_id)
                if state.get("cancel_requested") and not state.get("publish_started"):
                    current_task.cancel()
                    return
        watcher = asyncio.create_task(watch_cancel())
        budget_token = media.set_job_budget(job_store.job_dir(self.subject_id, job_id))
        try:
            if _SHUTTING_DOWN:
                raise _JobCancelled()
            manifest = job_store.read_manifest(self.subject_id, job_id)
            if manifest.get("cancel_requested"):
                raise _JobCancelled()
            if manifest.get("publish_started") or manifest.get("phase") == "publishing":
                await self._resume_publish(job_id, config)
                return
            manifest = job_store.update_manifest(
                self.subject_id,
                job_id,
                lambda current: self._running_manifest(current, phase="probing", status="running"),
            )
            await self._probe_and_plan(job_id)
            await self._transcribe(job_id, config)
            await self._publish(job_id, config)
        except _JobCancelled:
            self._mark_cancelled(job_id)
        except asyncio.CancelledError:
            state = job_store.read_manifest(self.subject_id, job_id)
            if state.get("cancel_requested") and not state.get("publish_started"):
                self._mark_cancelled(job_id)
            else:
                self._mark_interrupted(job_id)
            raise
        except (AsrOperationError, SubjectOperationError) as exc:
            self._mark_failed(job_id, exc)
        except Exception as exc:  # noqa: BLE001 - terminal state must be honest
            logger.exception("ASR worker unexpected failure: %s", type(exc).__name__)
            self._mark_failed(job_id, subject_error(ErrorCode.INTERNAL_ERROR, cause=exc))
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            media.reset_job_budget(budget_token)
            claim.release()
            lease.release()

    @staticmethod
    def _running_manifest(
        manifest: dict[str, Any], *, phase: str, status: str = "running"
    ) -> dict[str, Any]:
        if manifest.get("status") in ("completed", "cancelled"):
            raise _JobCancelled()
        manifest["status"] = status
        manifest["phase"] = phase
        manifest["error"] = None
        return manifest

    def _mark_failed(self, job_id: str, exc: AsrOperationError | SubjectOperationError) -> None:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
            if manifest.get("status") in ("completed", "cancelled"):
                return
            code = exc.code
            failed = getattr(exc, "failed_file_index", None)
            failed_chunk = getattr(exc, "failed_chunk_index", None)
            error = JobError.from_code(
                code,
                failed_file_index=failed,
                failed_chunk_index=failed_chunk,
            )

            def _mutate(current: dict[str, Any]) -> dict[str, Any]:
                if current.get("status") in ("completed", "cancelled"):
                    return current
                current["status"] = "failed"
                current["error"] = error.to_dict()
                if current.get("publish_started"):
                    current["phase"] = "publishing"
                return current

            job_store.update_manifest(self.subject_id, job_id, _mutate)
        except Exception as exc2:  # noqa: BLE001
            logger.warning("ASR failure could not be persisted: %s", type(exc2).__name__)

    def _mark_interrupted(self, job_id: str) -> None:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
            if manifest.get("status") in ("completed", "cancelled"):
                return

            def _mutate(current: dict[str, Any]) -> dict[str, Any]:
                if current.get("status") in ("completed", "cancelled"):
                    return current
                current["status"] = "interrupted"
                current["error"] = None
                return current

            job_store.update_manifest(self.subject_id, job_id, _mutate)
        except Exception:  # noqa: BLE001
            logger.warning("ASR interruption could not be persisted")

    def _mark_cancelled(self, job_id: str) -> None:
        try:
            manifest = job_store.read_manifest(self.subject_id, job_id)
            if manifest.get("status") in ("completed", "cancelled"):
                return

            def _mutate(current: dict[str, Any]) -> dict[str, Any]:
                if current.get("status") == "completed":
                    return current
                current["status"] = "cancelled"
                current["phase"] = "queued"
                current["cancel_requested"] = True
                current["error"] = None
                return current

            job_store.cleanup_media(self.subject_id, job_id)
            job_store.update_manifest(self.subject_id, job_id, _mutate)
        except Exception as exc:  # noqa: BLE001
            self._mark_failed(job_id, subject_error(ErrorCode.STORAGE_IO, cause=exc))
            logger.warning("ASR cancellation cleanup/persistence failed")

    def _cancel_requested(self, job_id: str) -> bool:
        manifest = job_store.read_manifest(self.subject_id, job_id)
        return bool(manifest.get("cancel_requested"))

    # -- probe and plan -------------------------------------------------------
    async def _probe_and_plan(self, job_id: str) -> None:
        directory = job_store.job_dir(self.subject_id, job_id)
        manifest = job_store.read_manifest(self.subject_id, job_id)
        tools = self._tools or media.resolve_tools()
        probes: list[MediaProbe] = []
        for index, row in enumerate(manifest.get("files") or []):
            if self._cancel_requested(job_id):
                raise _JobCancelled()
            input_path = _job_input_path(directory, manifest, index)
            size, digest = job_store.sha256_file(input_path)
            if size != int(row.get("size_bytes") or 0) or digest != row.get("sha256"):
                raise subject_error(ErrorCode.STORAGE_CORRUPT)
            probe = await media.probe(input_path, tools=tools)
            if sum(p.duration_ms for p in probes) + probe.duration_ms > MAX_TOTAL_DURATION_MS:
                raise asr_error(AsrErrorCode.ASR_DURATION_LIMIT)
            inputs_bytes = sum(int(item["size_bytes"]) for item in manifest["files"])
            if inputs_bytes + 2 * sum(p.wav_bytes for p in [*probes, probe]) > MAX_WORK_BYTES:
                raise asr_error(AsrErrorCode.ASR_RESOURCE_LIMIT)
            normalized_dir = json_store.confined(directory, directory / "normalized")
            json_store.make_directory(normalized_dir)
            normalized = json_store.confined(normalized_dir, normalized_dir / f"f{index:04d}.wav")
            if normalized.is_file() and row.get("normalized_sha256"):
                if job_store.sha256_file(normalized)[1] != row["normalized_sha256"]:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                frames, rate, channels, width = media.wav_info(normalized)
                if rate != 16_000 or channels != 1 or width != 2:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
            else:
                normalized.unlink(missing_ok=True)  # Uncheckpointed scratch is not reusable.
                frames = await media.normalize_to_wav(input_path, normalized, tools=tools)
            normalized_sha = job_store.sha256_file(normalized)[1]
            normalized_probe = replace(
                probe,
                path=normalized,
                duration_ms=round(frames * 1000 / 16_000),
                total_samples=frames,
                wav_bytes=frames * 2,
            )
            probes.append(normalized_probe)
            manifest = job_store.update_manifest(
                self.subject_id,
                job_id,
                lambda current, i=index, p=normalized_probe, d=normalized_sha, rel=f"normalized/f{index:04d}.wav": self._probe_file(current, i, p, rel, d),
            )
        total_ms = sum(item.duration_ms for item in probes)
        if total_ms > MAX_TOTAL_DURATION_MS:
            raise asr_error(AsrErrorCode.ASR_DURATION_LIMIT)
        if sum(item.size_bytes + 2 * item.wav_bytes for item in probes) > MAX_WORK_BYTES:
            raise asr_error(AsrErrorCode.ASR_RESOURCE_LIMIT)
        manifest = job_store.read_manifest(self.subject_id, job_id)
        if not manifest.get("chunks"):
            planned: list[dict[str, Any]] = []
            for index, probe in enumerate(probes):
                chunks = await media.plan_chunks(
                    probe, file_index=index, tools=tools
                )
                planned.extend(
                    {
                        "chunk_id": item.chunk_id,
                        "file_index": item.file_index,
                        "chunk_index": item.chunk_index,
                        "start_sample": item.start_sample,
                        "end_sample": item.end_sample,
                        "sample_rate": item.sample_rate,
                        "sha256": "",
                        "status": CHUNK_PENDING,
                        "text_path": "",
                        "attempt": 0,
                    }
                    for item in chunks
                )
            job_store.update_manifest(
                self.subject_id,
                job_id,
                lambda current: self._set_chunks(current, planned),
            )
        job_store.update_manifest(
            self.subject_id,
            job_id,
            lambda current: self._running_manifest(current, phase="segmenting"),
        )

    @staticmethod
    def _probe_file(
        manifest: dict[str, Any], index: int, probe: MediaProbe, normalized_path: str, digest: str
    ) -> dict[str, Any]:
        row = manifest["files"][index]
        row["duration_ms"] = probe.duration_ms
        row["input_sample_rate"] = probe.input_sample_rate
        row["channels"] = probe.channels
        row["total_samples"] = probe.total_samples
        row["normalized_path"] = normalized_path
        row["normalized_sha256"] = digest
        progress = manifest.setdefault("progress", progress_defaults(len(manifest["files"])))
        progress["files_total"] = len(manifest["files"])
        progress["audio_total_ms"] = sum(int(item.get("duration_ms") or 0) for item in manifest["files"])
        return manifest

    @staticmethod
    def _set_chunks(manifest: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
        manifest["chunks"] = chunks
        progress = manifest.setdefault("progress", progress_defaults(len(manifest.get("files") or [])))
        progress["chunks_total"] = len(chunks)
        progress["chunks_completed"] = 0
        progress["audio_completed_ms"] = 0
        return manifest

    # -- transcription --------------------------------------------------------
    async def _transcribe(self, job_id: str, config: STTConfig) -> None:
        provider = self._provider(config)
        directory = job_store.job_dir(self.subject_id, job_id)
        while True:
            if self._cancel_requested(job_id):
                raise _JobCancelled()
            current = job_store.read_manifest(self.subject_id, job_id)
            all_rows = [dict(item) for item in (current.get("chunks") or [])]
            if not all_rows:
                raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
            for success in (item for item in all_rows if item.get("status") == CHUNK_SUCCESS):
                text_path = str(success.get("text_path") or "")
                if not text_path or not success.get("text_sha256") or not success.get("sha256"):
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                if job_store.sha256_file(_chunk_path(directory, str(success["chunk_id"])))[1] != success["sha256"]:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                text = job_store.read_chunk_text(directory, text_path)
                if _sha256_bytes(text.encode("utf-8")) != success["text_sha256"]:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
            pending = [item for item in all_rows if item.get("status") != CHUNK_SUCCESS]
            if not pending:
                return
            if self._transcription_order is not None:
                ordered = list(self._transcription_order(all_rows))
            else:
                ordered = sorted(
                    all_rows,
                    key=lambda item: (int(item.get("file_index") or 0), int(item.get("chunk_index") or 0)),
                )
            fresh = next((item for item in ordered if item.get("status") != CHUNK_SUCCESS), None)
            if fresh is None:
                fresh = pending[0]
            chunk_id = str(fresh.get("chunk_id"))
            chunk_path = _chunk_path(directory, chunk_id)
            if not chunk_path.is_file() or not fresh.get("sha256"):
                chunk_path.unlink(missing_ok=True)
                input_path = _normalized_path(directory, current, int(fresh["file_index"]))
                await media.extract_chunk(
                    input_path,
                    chunk_path,
                    int(fresh["start_sample"]),
                    int(fresh["end_sample"]),
                    tools=self._tools or media.resolve_tools(),
                )
                _size, digest = job_store.sha256_file(chunk_path)
                current = job_store.update_manifest(
                    self.subject_id,
                    job_id,
                    lambda m, cid=chunk_id, d=digest: self._chunk_sha(m, cid, d),
                )
            elif fresh.get("sha256"):
                _size, digest = job_store.sha256_file(chunk_path)
                if digest != fresh.get("sha256"):
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
            job_store.update_manifest(
                self.subject_id,
                job_id,
                lambda m: self._running_manifest(m, phase="transcribing"),
            )
            try:
                result = await provider.transcribe_chunk(
                    chunk_path, language=str(current.get("language") or "zh")
                )
            except AsrProviderError as exc:
                if exc.code == AsrErrorCode.ASR_PROVIDER_LIMIT and self._can_split(current, fresh):
                    await self._split_chunk(job_id, current, fresh)
                    continue
                setattr(exc, "failed_file_index", int(fresh["file_index"]))
                setattr(exc, "failed_chunk_index", int(fresh["chunk_index"]))
                raise
            text = getattr(result, "text", "")
            if not isinstance(text, str):
                raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT) from None
            text_path = job_store.write_chunk_text(directory, chunk_id, text)
            job_store.update_manifest(
                self.subject_id,
                job_id,
                lambda m, cid=chunk_id, tp=text_path, d=_sha256_bytes(text.encode("utf-8")): self._chunk_success(m, cid, tp, d),
            )

    @staticmethod
    def _chunk_sha(manifest: dict[str, Any], chunk_id: str, digest: str) -> dict[str, Any]:
        for item in manifest.get("chunks") or []:
            if item.get("chunk_id") == chunk_id:
                item["sha256"] = digest
                return manifest
        raise subject_error(ErrorCode.STORAGE_CORRUPT)

    @staticmethod
    def _chunk_success(manifest: dict[str, Any], chunk_id: str, text_path: str, digest: str) -> dict[str, Any]:
        for item in manifest.get("chunks") or []:
            if item.get("chunk_id") == chunk_id:
                item["status"] = CHUNK_SUCCESS
                item["text_path"] = text_path
                item["text_sha256"] = digest
                item["attempt"] = int(item.get("attempt") or 0) + 1
                break
        else:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        AsrJobService._refresh_progress(manifest)
        return manifest

    @staticmethod
    def _refresh_progress(manifest: dict[str, Any]) -> None:
        chunks = manifest.get("chunks") or []
        progress = manifest.setdefault("progress", progress_defaults(len(manifest.get("files") or [])))
        progress["chunks_total"] = len(chunks)
        progress["chunks_completed"] = sum(1 for item in chunks if item.get("status") == CHUNK_SUCCESS)
        total_ms = 0
        for item in chunks:
            if item.get("status") == CHUNK_SUCCESS:
                samples = max(0, int(item.get("end_sample") or 0) - int(item.get("start_sample") or 0))
                total_ms += round(samples * 1000 / int(item.get("sample_rate") or CHUNK_SAMPLE_RATE))
        progress["audio_completed_ms"] = total_ms

    @staticmethod
    def _can_split(manifest: Mapping[str, Any], chunk: Mapping[str, Any]) -> bool:
        return int(chunk.get("split_depth") or 0) < 1

    async def _split_chunk(
        self, job_id: str, manifest: dict[str, Any], chunk: Mapping[str, Any]
    ) -> None:
        start = int(chunk.get("start_sample") or 0)
        end = int(chunk.get("end_sample") or 0)
        if end - start < 2:
            raise asr_error(AsrErrorCode.ASR_PROVIDER_LIMIT)
        middle = start + (end - start) // 2
        key = f"{start}-{end}"
        file_index = int(chunk.get("file_index") or 0)
        new_rows = [
            {
                "split_depth": 1,
                "chunk_id": f"f{file_index}-{start}-{middle}",
                "file_index": file_index,
                "chunk_index": 0,
                "start_sample": start,
                "end_sample": middle,
                "sample_rate": CHUNK_SAMPLE_RATE,
                "sha256": "",
                "status": CHUNK_PENDING,
                "text_path": "",
                "attempt": 0,
            },
            {
                "split_depth": 1,
                "chunk_id": f"f{file_index}-{middle}-{end}",
                "file_index": file_index,
                "chunk_index": 0,
                "start_sample": middle,
                "end_sample": end,
                "sample_rate": CHUNK_SAMPLE_RATE,
                "sha256": "",
                "status": CHUNK_PENDING,
                "text_path": "",
                "attempt": 0,
            },
        ]

        def _mutate(current: dict[str, Any]) -> dict[str, Any]:
            rows = [
                item
                for item in current.get("chunks") or []
                if item.get("chunk_id") != chunk.get("chunk_id")
            ]
            rows.extend(new_rows)
            rows.sort(key=lambda item: (int(item.get("file_index") or 0), int(item.get("start_sample") or 0)))
            for index, item in enumerate(rows):
                item["chunk_index"] = index
            current["chunks"] = rows
            current.setdefault("resplit_done", []).append(key)
            AsrJobService._refresh_progress(current)
            return current

        job_store.update_manifest(self.subject_id, job_id, _mutate)
        # A stale chunk WAV is no longer referenced; remove it only if it is the
        # exact failed chunk file.
        failed = job_store.job_dir(self.subject_id, job_id) / "chunks" / f"{chunk.get('chunk_id')}.wav"
        try:
            if failed.is_file() and not failed.is_symlink():
                failed.unlink()
        except OSError:
            logger.warning("ASR failed chunk scratch cleanup failed")

    # -- merge / publication --------------------------------------------------
    def _merge_result(self, job_id: str) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any]]:
        directory = job_store.job_dir(self.subject_id, job_id)
        manifest = job_store.read_manifest(self.subject_id, job_id)
        chunks = list(manifest.get("chunks") or [])
        if not chunks or any(item.get("status") != CHUNK_SUCCESS for item in chunks):
            logger.warning(
                "ASR merge incomplete: %s",
                [(item.get("chunk_id"), item.get("status"), bool(item.get("text_path"))) for item in chunks],
            )
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        transcripts: list[dict[str, str]] = []
        for index, row in enumerate(manifest.get("files") or []):
            own = [item for item in chunks if int(item.get("file_index") or 0) == index]
            own.sort(key=lambda item: int(item.get("chunk_index") or 0))
            cursor = 0
            for item in own:
                if int(item["start_sample"]) != cursor or int(item["end_sample"]) <= cursor:
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                cursor = int(item["end_sample"])
            if cursor != int(row.get("total_samples") or 0):
                raise subject_error(ErrorCode.STORAGE_CORRUPT)
            texts: list[str] = []
            for item in own:
                text = job_store.read_chunk_text(directory, str(item.get("text_path") or ""))
                if _sha256_bytes(text.encode("utf-8")) != item.get("text_sha256"):
                    raise subject_error(ErrorCode.STORAGE_CORRUPT)
                if text.strip():
                    texts.append(text.strip())
            transcripts.append(
                {
                    "file": str(row.get("name") or ""),
                    "text": "\n".join(texts),
                    "model": str(manifest.get("provider_model") or ""),
                }
            )
        payload = {
            "operation": "transcribe",
            "job_id": job_id,
            "files": [str(row.get("name") or "") for row in manifest.get("files") or []],
            "transcripts": transcripts,
            "message": f"ASR 转写完成（{len(transcripts)} 个文件）",
        }
        return payload, transcripts, manifest

    async def _publish(self, job_id: str, config: STTConfig) -> None:
        job_store.update_manifest(
            self.subject_id,
            job_id,
            lambda current: self._running_manifest(current, phase="merging"),
        )
        payload, transcripts, manifest = self._merge_result(job_id)
        job_store.write_result(self.subject_id, job_id, payload)
        latch = await self._writer_latch()
        try:
            plan = self._prepare_publish_plan(job_id, manifest, transcripts)
            # The cancel route and this transition both mutate the manifest
            # under the same short lock; whichever wins is authoritative.
            def _start(current: dict[str, Any]) -> dict[str, Any]:
                if current.get("cancel_requested"):
                    raise _JobCancelled()
                if current.get("status") in ("completed", "cancelled"):
                    raise _JobCancelled()
                current["status"] = "running"
                current["phase"] = "publishing"
                current["publish_started"] = True
                current["publish_plan"] = plan
                current["provider_model"] = str(config.model)
                return current

            manifest = job_store.update_manifest(self.subject_id, job_id, _start)
            job_store.write_publish_plan(self.subject_id, job_id, plan)
            await self._commit_joined(job_id, manifest, transcripts, plan)
            if not self._final_hashes_match(plan):
                raise asr_error(AsrErrorCode.ASR_PUBLISH_CONFLICT)
            self._finish_completed(job_id, payload)
        finally:
            latch.release()

    async def _writer_latch(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while True:
            try:
                return subject_operations.acquire_audio_writer(self.subject_id, timeout=0)
            except SubjectOperationError as exc:
                if exc.code != ErrorCode.KB_BUSY or loop.time() >= deadline:
                    raise
                await asyncio.sleep(.05)

    async def _commit_joined(self, *args, **kwargs):
        task = asyncio.create_task(asyncio.to_thread(self._commit_published, *args, **kwargs))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancelling an await cannot stop a filesystem thread. Join it
            # before releasing activity/claim, leaving publishing recoverable.
            await task
            raise

    def _prepare_publish_plan(
        self,
        job_id: str,
        manifest: dict[str, Any],
        transcripts: list[dict[str, str]],
    ) -> dict[str, Any]:
        materials = uploads.materials_path(self.subject_id, "lecture", create=False)
        directory = job_store.job_dir(self.subject_id, job_id)
        rows: list[dict[str, Any]] = []
        for index, file_row in enumerate(manifest.get("files") or []):
            name = str(file_row.get("name") or "")
            audio_target = name
            text_target = f"{name}{uploads.TRANSCRIPT_SUFFIX}"
            old_audio = _target_state(materials, audio_target)
            old_text = _target_state(materials, text_target)
            input_path = _job_input_path(directory, manifest, index)
            _size, audio_sha = job_store.sha256_file(input_path)
            text = transcripts[index]["text"] if index < len(transcripts) else ""
            rows.append(
                {
                    "file_index": index,
                    "name": name,
                    "audio_target": audio_target,
                    "text_target": text_target,
                    "new_audio_sha256": audio_sha,
                    "new_text_sha256": _sha256_bytes(text.encode("utf-8")),
                    "new_text_size": len(text.encode("utf-8")),
                    "old_audio": old_audio,
                    "old_text": old_text,
                }
            )
        return {"schema_version": 1, "job_id": job_id, "files": rows, "created_at": utc_now()}

    def _preconditions(self, plan: Mapping[str, Any], *, recovery: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in plan.get("files") or []:
            old_audio = item.get("old_audio") or {}
            old_text = item.get("old_text") or {}
            audio_allowed = [] if not old_audio.get("exists") else [str(old_audio.get("sha256"))]
            text_allowed = [] if not old_text.get("exists") else [str(old_text.get("sha256"))]
            if recovery:
                audio_allowed.append(str(item.get("new_audio_sha256")))
                text_allowed.append(str(item.get("new_text_sha256")))
            rows.append(
                {
                    "target": item.get("audio_target"),
                    "allowed_sha256": sorted(set(filter(None, audio_allowed))),
                    "allow_absent": not bool(old_audio.get("exists")),
                }
            )
            rows.append(
                {
                    "target": item.get("text_target"),
                    "allowed_sha256": sorted(set(filter(None, text_allowed))),
                    "allow_absent": not bool(old_text.get("exists")),
                }
            )
        return rows

    def _commit_published(
        self,
        job_id: str,
        manifest: dict[str, Any],
        transcripts: list[dict[str, str]],
        plan: Mapping[str, Any],
        *,
        recovery: bool = False,
    ) -> None:
        from deeptutor.subjects.uploads import (
            BatchFile,
            PublishPreconditionError,
            Staged,
            UploadPlan,
        )

        directory = job_store.job_dir(self.subject_id, job_id)
        entries = tuple(
            BatchFile(
                upload=None,
                original=str(row.get("name") or ""),
                name=str(row.get("name") or ""),
                extension=Path(str(row.get("name") or "")).suffix.lower(),
                mime=str(row.get("content_type") or "application/octet-stream"),
            )
            for row in manifest.get("files") or []
        )
        staged = [
            Staged(
                entry=entries[index],
                path=_job_input_path(directory, manifest, index),
                size=int((manifest["files"][index]).get("size_bytes") or 0),
                sha256=str((manifest["files"][index]).get("sha256") or ""),
            )
            for index in range(len(entries))
        ]
        plan_obj = UploadPlan(
            operation="transcribe",
            kb_type="lecture",
            kb_name=uploads.kb_name_for_type("lecture"),
            files=entries,
        )
        staging = directory / "publish-staging"
        json_store.make_directory(staging)
        try:
            uploads.commit_transcripts(
                subject_id=self.subject_id,
                plan=plan_obj,
                staged=staged,
                transcripts=transcripts,
                staging_dir=staging,
                preconditions=self._preconditions(plan, recovery=recovery),
            )
        except PublishPreconditionError as exc:
            raise asr_error(AsrErrorCode.ASR_PUBLISH_CONFLICT, cause=exc) from exc
        finally:
            try:
                shutil.rmtree(staging)
            except OSError:
                pass

    def _final_hashes_match(self, plan: Mapping[str, Any]) -> bool:
        materials = uploads.materials_path(self.subject_id, "lecture", create=False)
        for item in plan.get("files") or []:
            if _target_state(materials, str(item.get("audio_target"))).get("sha256") != item.get("new_audio_sha256"):
                return False
            if _target_state(materials, str(item.get("text_target"))).get("sha256") != item.get("new_text_sha256"):
                return False
        return True

    def _finish_completed(self, job_id: str, payload: dict[str, Any]) -> None:
        if not job_store.read_result(self.subject_id, job_id):
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        job_store.cleanup_media(self.subject_id, job_id)
        job_store.update_manifest(
            self.subject_id,
            job_id,
            lambda current: self._completed_manifest(current, payload),
        )

    @staticmethod
    def _completed_manifest(manifest: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        manifest["status"] = "completed"
        manifest["phase"] = "finished"
        manifest["error"] = None
        manifest["result"] = {
            "files": len(payload.get("files") or []),
            "transcripts": len(payload.get("transcripts") or []),
        }
        AsrJobService._refresh_progress(manifest)
        return manifest

    async def _resume_publish(self, job_id: str, config: STTConfig) -> None:
        manifest = job_store.read_manifest(self.subject_id, job_id)
        plan = manifest.get("publish_plan")
        if not isinstance(plan, Mapping):
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        latch = await self._writer_latch()
        try:
            if self._final_hashes_match(plan):
                self._finish_completed(job_id, job_store.read_result(self.subject_id, job_id))
                return
            payload, transcripts, manifest = self._merge_result(job_id)
            await self._commit_joined(job_id, manifest, transcripts, plan, recovery=True)
            if not self._final_hashes_match(plan):
                raise asr_error(AsrErrorCode.ASR_PUBLISH_CONFLICT)
            self._finish_completed(job_id, payload)
        finally:
            latch.release()

    # -- direct worker for live/offline acceptance ---------------------------
    async def run_job_direct(self, job_id: str) -> None:
        """Run an already-created queued job without the HTTP route (smoke use)."""
        claim = job_store.WorkerClaim.acquire(self.subject_id, job_id)
        if claim is None:
            raise asr_error(AsrErrorCode.ASR_INVALID_STATE)
        lease = subject_operations.acquire_activity(self.subject_id, kind="asr")
        config = self._config()
        self._provider(config)
        await self._run_worker(job_id, claim, lease, config)


__all__ = [
    "AsrJobService",
    "active_task_count",
    "reset_shutdown_for_tests",
    "shutdown_asr",
]
