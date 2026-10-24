"""ASR-R1 frozen contracts shared by the job API, worker, media and UI proxy.

This module contains only names, limits, immutable value objects and
serialization helpers.  It never imports a provider client, never reads the
real model catalog and never opens a subject path, so both the API and the
unit-test harness can import it cheaply.

The limits and wire fields mirror ``plans/asr-long-audio/CONTRACTS.md`` D2,
D3, D4 and D6.  Keep additions backwards compatible: the pre-existing
synchronous ASR endpoint is not part of this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from deeptutor.services.voice.config import STTConfig
from deeptutor.subjects.errors import ASR_ERROR_SPECS, ERROR_SPECS, AsrErrorCode, ErrorCode

# ---------------------------------------------------------------------------
# Frozen limits (D2)
# ---------------------------------------------------------------------------
MAX_FILES = 16
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_BATCH_BYTES = 200 * 1024 * 1024
MAX_TOTAL_DURATION_MS = 4 * 60 * 60 * 1000
MAX_WORK_BYTES = 1024 * 1024 * 1024
MAX_CHUNK_SECONDS = 180
CHUNK_SAMPLE_RATE = 16_000
CHUNK_CHANNELS = 1
CHUNK_SAMPLE_WIDTH = 2
CHUNK_MAX_SAMPLES = MAX_CHUNK_SECONDS * CHUNK_SAMPLE_RATE
SILENCE_LOOKBACK_SECONDS = 10
SILENCE_MIN_SECONDS = 0.3
SILENCE_NOISE_DB = -35
SILICONFLOW_MAX_AUDIO_BYTES = 50_000_000
SILICONFLOW_MAX_AUDIO_SECONDS = 3600
UNKNOWN_MAX_CHUNK_BYTES = 8_000_000
UNKNOWN_MAX_CHUNK_SECONDS = 180
PROBE_TIMEOUT_SECONDS = 20
MEDIA_TOTAL_TIMEOUT_SECONDS = 600
PROVIDER_CONNECT_TIMEOUT = 15
PROVIDER_READ_TIMEOUT = 180
PROVIDER_WRITE_TIMEOUT = 60
PROVIDER_TOTAL_TIMEOUT = 240
PROVIDER_MAX_ATTEMPTS = 3
PROVIDER_RETRY_AFTER_CAP = 60
JOB_SCHEMA_VERSION = 1
POLICY_VERSION = "asr-r1-v1"

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
AUDIO_JOB_EXTENSIONS = frozenset(
    {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".oga", ".opus", ".aac", ".amr", ".wma", ".webm"}
)

STATUSES = (
    "queued",
    "running",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
)
PHASES = (
    "queued",
    "probing",
    "segmenting",
    "transcribing",
    "merging",
    "publishing",
    "finished",
)
ACTIVE_STATUSES = frozenset({"queued", "running", "cancelling"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
CHUNK_PENDING = "pending"
CHUNK_SUCCESS = "success"
CHUNK_FAILED = "failed"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def new_request_id() -> str:
    """A fresh UUID4 string (the API compares the UUID value, not formatting)."""
    return str(uuid.uuid4())


def request_id_job_id(request_id: str) -> str:
    """Validate a UUID4 request id and return its 32-char lowercase hex job id."""
    if not isinstance(request_id, str):
        raise ValueError("request_id must be a string")
    try:
        parsed = uuid.UUID(request_id.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError("request_id must be a UUID") from exc
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise ValueError("request_id must be a UUID4")
    return parsed.hex


def valid_job_id(value: object) -> bool:
    if not isinstance(value, str) or not JOB_ID_RE.fullmatch(value):
        return False
    parsed = uuid.UUID(hex=value)
    return parsed.version == 4 and parsed.variant == uuid.RFC_4122


def validate_language(value: object) -> str:
    if value is None or value == "":
        return "zh"
    if not isinstance(value, str):
        raise ValueError("language must be a string")
    text = value.strip()
    if not 1 <= len(text) <= 32 or re.search(r"[\x00-\x1f\x7f/\\]", text):
        raise ValueError("language is invalid")
    return text


def normalized_endpoint(base_url: str) -> str:
    """Credential-free endpoint identity for the config fingerprint.

    Userinfo, query and fragment are deliberately removed: an API key embedded
    in a URL must not become part of a persisted fingerprint.
    """
    raw = (base_url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    # Credential rotation is allowed; other query parameters affect routing.
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not any(s in k.lower() for s in ("key", "token", "secret", "password", "signature", "credential"))]
    return urlunsplit((parsed.scheme.lower(), f"{host}{port}", path, urlencode(sorted(query)), ""))


def config_fingerprint(config: STTConfig, language: str) -> str:
    """Stable, non-secret identity of the provider semantics used by a job.

    API keys and header *values* are excluded.  A retry may use a rotated key
    for the same profile; changing the model, protocol, endpoint or language is
    a different fingerprint and must not be mixed with old checkpoints.
    """
    payload = {
        "policy": POLICY_VERSION,
        "profile_id": config.profile_id,
        "provider": str(config.provider_name or ""),
        "adapter": str(config.adapter or ""),
        "request_style": str(config.request_style or ""),
        "auth_style": str(config.auth_style or ""),
        "model": str(config.model or ""),
        "endpoint": normalized_endpoint(str(config.base_url or "")),
        "api_version": str(config.api_version or ""),
        "header_names": sorted(str(name) for name in (config.extra_headers or {})),
        "language": language,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def endpoint_host(config: STTConfig) -> str:
    raw = str(config.base_url or "")
    try:
        return (urlsplit(raw if "://" in raw else f"https://{raw}").hostname or "").lower()
    except ValueError:
        return ""


def media_chunk_cap(config: STTConfig) -> tuple[int, int]:
    """Conservative ``(bytes, seconds)`` cap for one provider request.

    The SiliconFlow snapshot is 50,000,000 bytes / 3600 s.  The exact MB
    boundary is not documented, so planning uses the lower decimal value and
    never claims a 50,786,002-byte request was rejected.  Every other
    OpenAI-compatible multipart endpoint gets the conservative 8,000,000 B /
    180 s profile.
    """
    from deeptutor.services.voice.config import STT_QWEN_CHAT
    if config.adapter == "qwen_asr" and config.request_style == STT_QWEN_CHAT:
        from deeptutor.services.voice.adapters.qwen_asr import (
            QWEN_MAX_AUDIO_BYTES,
            QWEN_MAX_AUDIO_SECONDS,
        )
        return QWEN_MAX_AUDIO_BYTES, QWEN_MAX_AUDIO_SECONDS
    if endpoint_host(config) in ("api.siliconflow.cn", "api.siliconflow.com"):
        return SILICONFLOW_MAX_AUDIO_BYTES, SILICONFLOW_MAX_AUDIO_SECONDS
    return UNKNOWN_MAX_CHUNK_BYTES, UNKNOWN_MAX_CHUNK_SECONDS


# ---------------------------------------------------------------------------
# Public value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class JobError:
    code: str
    message: str
    retryable: bool
    failed_file_index: int | None = None
    failed_chunk_index: int | None = None

    @classmethod
    def from_code(
        cls,
        code: AsrErrorCode | ErrorCode | str,
        *,
        failed_file_index: int | None = None,
        failed_chunk_index: int | None = None,
    ) -> "JobError":
        if isinstance(code, AsrErrorCode):
            resolved: AsrErrorCode | ErrorCode = code
        elif isinstance(code, ErrorCode):
            resolved = code
        else:
            try:
                resolved = AsrErrorCode(code)
            except ValueError:
                resolved = ErrorCode(code)
        spec = ASR_ERROR_SPECS[resolved] if isinstance(resolved, AsrErrorCode) else ERROR_SPECS[resolved]
        return cls(
            code=spec.code.value,
            message=spec.message,
            retryable=spec.retryable,
            failed_file_index=failed_file_index,
            failed_chunk_index=failed_chunk_index,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.failed_file_index is not None:
            payload["failed_file_index"] = self.failed_file_index
        if self.failed_chunk_index is not None:
            payload["failed_chunk_index"] = self.failed_chunk_index
        return payload


@dataclass(frozen=True)
class JobView:
    job_id: str
    subject_id: str
    status: str
    phase: str
    revision: int
    created_at: str
    updated_at: str
    files: tuple[dict[str, Any], ...]
    progress: dict[str, int]
    error: dict[str, Any] | None
    can_retry: bool
    can_cancel: bool
    result_available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "subject_id": self.subject_id,
            "status": self.status,
            "phase": self.phase,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": [dict(item) for item in self.files],
            "progress": dict(self.progress),
            "error": dict(self.error) if self.error else None,
            "can_retry": self.can_retry,
            "can_cancel": self.can_cancel,
            "result_available": self.result_available,
        }


def progress_defaults(files_total: int = 0) -> dict[str, int]:
    return {
        "files_total": int(files_total),
        "chunks_total": 0,
        "chunks_completed": 0,
        "audio_total_ms": 0,
        "audio_completed_ms": 0,
    }


def project_job(manifest: Mapping[str, Any], *, worker_alive: bool) -> JobView:
    """Project a persisted manifest to the public, read-only JobView.

    A queued/running/cancelling manifest whose worker no longer exists is shown
    as ``interrupted``.  This function never writes the projection back;
    explicit ``retry`` is the only operation that may persist recovery.
    """
    status = str(manifest.get("status") or "queued")
    if status in ACTIVE_STATUSES and not worker_alive:
        status = "interrupted"
    phase = str(manifest.get("phase") or "queued")
    if status == "interrupted" and phase not in ("publishing", "finished"):
        phase = "queued"
    files = tuple(
        {
            "file_index": int(item.get("file_index", index)),
            "name": str(item.get("name") or ""),
            "size_bytes": int(item.get("size_bytes") or 0),
        }
        for index, item in enumerate(manifest.get("files") or [])
        if isinstance(item, Mapping)
    )
    progress = progress_defaults(len(files))
    stored = manifest.get("progress")
    if isinstance(stored, Mapping):
        for key in progress:
            try:
                progress[key] = int(stored.get(key, progress[key]))
            except (TypeError, ValueError):
                pass
    error = manifest.get("error")
    error_dict = None
    if isinstance(error, Mapping):
        try:
            safe = JobError.from_code(str(error.get("code")))
        except ValueError:
            safe = JobError.from_code(ErrorCode.STORAGE_CORRUPT)
        error_dict = safe.to_dict()
        for field in ("failed_file_index", "failed_chunk_index"):
            value = error.get(field)
            if type(value) is int and value >= 0:
                error_dict[field] = value
    return JobView(
        job_id=str(manifest.get("job_id") or ""),
        subject_id=str(manifest.get("subject_id") or ""),
        status=status,
        phase=phase,
        revision=int(manifest.get("revision") or 1),
        created_at=str(manifest.get("created_at") or ""),
        updated_at=str(manifest.get("updated_at") or ""),
        files=files,
        progress=progress,
        error=error_dict,
        can_retry=status in ("failed", "interrupted"),
        can_cancel=status in ("queued", "running") and phase != "publishing",
        result_available=status == "completed",
    )


@dataclass(frozen=True)
class ChunkSpec:
    chunk_id: str
    file_index: int
    chunk_index: int
    start_sample: int
    end_sample: int
    sample_rate: int = CHUNK_SAMPLE_RATE
    sha256: str = ""
    status: str = CHUNK_PENDING
    text_path: str = ""
    attempt: int = 0

    @property
    def samples(self) -> int:
        return max(0, self.end_sample - self.start_sample)

    @property
    def duration_ms(self) -> int:
        return round(self.samples * 1000 / self.sample_rate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_index": self.file_index,
            "chunk_index": self.chunk_index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "sample_rate": self.sample_rate,
            "sha256": self.sha256,
            "status": self.status,
            "text_path": self.text_path,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChunkSpec":
        return cls(
            chunk_id=str(payload.get("chunk_id") or ""),
            file_index=int(payload.get("file_index") or 0),
            chunk_index=int(payload.get("chunk_index") or 0),
            start_sample=int(payload.get("start_sample") or 0),
            end_sample=int(payload.get("end_sample") or 0),
            sample_rate=int(payload.get("sample_rate") or CHUNK_SAMPLE_RATE),
            sha256=str(payload.get("sha256") or ""),
            status=str(payload.get("status") or CHUNK_PENDING),
            text_path=str(payload.get("text_path") or ""),
            attempt=int(payload.get("attempt") or 0),
        )


def chunk_id_for(file_index: int, start_sample: int, end_sample: int) -> str:
    """Stable identity from file number and sample range (not display order)."""
    return f"f{int(file_index)}-{int(start_sample)}-{int(end_sample)}"


def request_signature(files: list[Mapping[str, Any]], *, language: str, fingerprint: str) -> str:
    payload = {
        "files": [
            {"name": str(item.get("name") or ""), "sha256": str(item.get("sha256") or "")}
            for item in files
        ],
        "language": language,
        "config": fingerprint,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ACTIVE_STATUSES",
    "AUDIO_JOB_EXTENSIONS",
    "CHUNK_CHANNELS",
    "CHUNK_MAX_SAMPLES",
    "CHUNK_PENDING",
    "CHUNK_SAMPLE_RATE",
    "CHUNK_SAMPLE_WIDTH",
    "CHUNK_SUCCESS",
    "CHUNK_FAILED",
    "ChunkSpec",
    "JOB_ID_RE",
    "JOB_SCHEMA_VERSION",
    "JobError",
    "JobView",
    "MAX_BATCH_BYTES",
    "MAX_CHUNK_SECONDS",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_DURATION_MS",
    "MAX_WORK_BYTES",
    "MEDIA_TOTAL_TIMEOUT_SECONDS",
    "PHASES",
    "POLICY_VERSION",
    "PROBE_TIMEOUT_SECONDS",
    "PROVIDER_CONNECT_TIMEOUT",
    "PROVIDER_MAX_ATTEMPTS",
    "PROVIDER_READ_TIMEOUT",
    "PROVIDER_RETRY_AFTER_CAP",
    "PROVIDER_TOTAL_TIMEOUT",
    "PROVIDER_WRITE_TIMEOUT",
    "SILENCE_LOOKBACK_SECONDS",
    "SILENCE_MIN_SECONDS",
    "SILENCE_NOISE_DB",
    "SILICONFLOW_MAX_AUDIO_BYTES",
    "SILICONFLOW_MAX_AUDIO_SECONDS",
    "STATUSES",
    "TERMINAL_STATUSES",
    "UNKNOWN_MAX_CHUNK_BYTES",
    "UNKNOWN_MAX_CHUNK_SECONDS",
    "chunk_id_for",
    "config_fingerprint",
    "endpoint_host",
    "media_chunk_cap",
    "new_request_id",
    "normalized_endpoint",
    "progress_defaults",
    "project_job",
    "request_id_job_id",
    "request_signature",
    "utc_now",
    "valid_job_id",
    "validate_language",
]
