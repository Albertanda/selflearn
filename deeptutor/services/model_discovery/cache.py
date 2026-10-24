"""Persistent, bounded, non-secret model-directory cache.

Layout: ``<user_root>/cache/model-discovery/<sha256>.json``.  The file name is
the connection fingerprint; the file contains only that irreversible digest,
sanitized candidates, status, timestamps, and (for source-backed parameters)
the sanitized display URL/checked-at pair.  API keys, header values, request
query strings, and upstream error bodies are never written.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from deeptutor.services.llm.reasoning_controls import ReasoningControls

from .metadata import ModelParameters
from .types import (
    CacheState,
    Classification,
    DiscoveredModel,
    DiscoveryError,
    DiscoveryErrorCode,
    ModelSource,
    RuntimeCompatibility,
    iso_utc,
    parse_iso_utc,
    utc_now,
)

CACHE_SCHEMA_VERSION = 5
MAX_CACHE_ENTRIES = 128
FRESH_SUCCESS_TTL = timedelta(hours=1)
EMPTY_SUCCESS_TTL = timedelta(minutes=5)
FAILURE_COOLDOWN = timedelta(seconds=60)
STALE_RETENTION = timedelta(days=7)


class CacheIOError(RuntimeError):
    pass


@dataclass(slots=True)
class CacheEntry:
    fingerprint: str
    service: str
    status: str
    models: list[DiscoveredModel]
    complete: bool
    fetched_at: datetime | None
    expires_at: datetime | None
    last_used_at: datetime
    last_failure_at: datetime | None = None
    last_failure: DiscoveryError | None = None

    @property
    def has_success(self) -> bool:
        return self.status in {"ok", "empty"} and self.fetched_at is not None

    def fresh(self, now: datetime) -> bool:
        return (
            self.has_success
            and self.complete
            and self.expires_at is not None
            and now < self.expires_at
            and (self.last_failure_at is None or self.last_failure_at < self.fetched_at)
        )

    def in_stale_window(self, now: datetime) -> bool:
        return (
            self.has_success
            and self.fetched_at is not None
            and now - self.fetched_at <= STALE_RETENTION
        )

    def in_failure_cooldown(self, now: datetime) -> bool:
        return self.last_failure_at is not None and now - self.last_failure_at < FAILURE_COOLDOWN


def _dt(value: Any) -> datetime | None:
    return parse_iso_utc(value)


def _entry_from_dict(fingerprint: str, payload: Mapping[str, Any]) -> CacheEntry | None:
    if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    if str(payload.get("connection_fingerprint") or "") != fingerprint:
        return None
    service = str(payload.get("service") or "")
    status = str(payload.get("status") or "")
    if service not in {"llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"}:
        return None
    if status not in {"ok", "empty", "failure"}:
        return None
    models: list[DiscoveredModel] = []
    raw_models = payload.get("models")
    if raw_models is not None and not isinstance(raw_models, list):
        return None
    for item in raw_models or []:
        if not isinstance(item, Mapping):
            return None
        try:
            model_id = str(item.get("id") or "")
            if not model_id or len(model_id) > 512:
                return None
            services = tuple(
                str(value) for value in (item.get("services") or []) if isinstance(value, str)
            )
            classification = Classification(str(item.get("classification") or "unknown"))
            compatibility = RuntimeCompatibility(
                str(item.get("runtime_compatibility") or "unknown")
            )
            source = ModelSource(str(item.get("source") or "remote"))
            context_window = item.get("context_window")
            if context_window is not None and not (
                isinstance(context_window, int) and context_window > 0
            ):
                context_window = None
            parameters = ModelParameters.from_mapping(item.get("parameters"))
            if parameters is not None and parameters.context_window:
                context_window = parameters.context_window
            reasoning_controls = ReasoningControls.from_mapping(
                item.get("reasoning_controls")
            )
            models.append(
                DiscoveredModel(
                    id=model_id,
                    name=str(item.get("name") or model_id)[:256],
                    services=services,
                    classification=classification,
                    runtime_compatibility=compatibility,
                    reason_code=item.get("reason_code")
                    if isinstance(item.get("reason_code"), str)
                    else None,
                    source=source,
                    context_window=context_window,
                    parameters=parameters,
                    reasoning_controls=reasoning_controls,
                    resource_name=item.get("resource_name")
                    if isinstance(item.get("resource_name"), str)
                    else None,
                    deployment_mapping_required=item.get("deployment_mapping_required")
                    is True,
                )
            )
        except (ValueError, TypeError):
            return None
    failure_payload = payload.get("last_failure")
    failure: DiscoveryError | None = None
    if isinstance(failure_payload, Mapping):
        try:
            failure = DiscoveryError(
                code=DiscoveryErrorCode(str(failure_payload.get("code") or "UNAVAILABLE")),
                message=str(failure_payload.get("message") or "目录刷新失败。")[:300],
                retryable=bool(failure_payload.get("retryable")),
            )
        except ValueError:
            failure = DiscoveryError(DiscoveryErrorCode.UNAVAILABLE, "目录刷新失败。", True)
    last_used = _dt(payload.get("last_used_at")) or utc_now()
    return CacheEntry(
        fingerprint=fingerprint,
        service=service,
        status=status,
        models=models,
        complete=bool(payload.get("complete")),
        fetched_at=_dt(payload.get("fetched_at")),
        expires_at=_dt(payload.get("expires_at")),
        last_used_at=last_used,
        last_failure_at=_dt(payload.get("last_failure_at")),
        last_failure=failure,
    )


class DiscoveryCache:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] = utc_now,
        max_entries: int = MAX_CACHE_ENTRIES,
    ) -> None:
        self.root = Path(root)
        self.now = now
        self.max_entries = max(1, max_entries)

    def _path(self, fingerprint: str) -> Path:
        return self.root / f"{fingerprint}.json"

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
        except OSError as exc:
            raise CacheIOError("cannot prepare model discovery cache") from exc

    def load(self, fingerprint: str) -> CacheEntry | None:
        path = self._path(fingerprint)
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CacheIOError("cannot read model discovery cache") from exc
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Corrupt cache is ignored and will be replaced by a fresh fetch.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        if not isinstance(payload, Mapping):
            return None
        return _entry_from_dict(fingerprint, payload)

    def _write(self, entry: CacheEntry) -> None:
        self._ensure_root()
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "connection_fingerprint": entry.fingerprint,
            "service": entry.service,
            "status": entry.status,
            "complete": entry.complete,
            "fetched_at": iso_utc(entry.fetched_at),
            "expires_at": iso_utc(entry.expires_at),
            "last_used_at": iso_utc(entry.last_used_at),
            "last_failure_at": iso_utc(entry.last_failure_at),
            "last_failure": (
                entry.last_failure.to_dict() if entry.last_failure is not None else None
            ),
            "models": [model.to_dict() for model in entry.models],
        }
        data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        fd: int | None = None
        temp_name: str | None = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".md-cache-", suffix=".tmp", dir=self.root)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                fd = None
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._path(entry.fingerprint))
            temp_name = None
        except OSError as exc:
            raise CacheIOError("cannot write model discovery cache") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
        self._prune()

    def _prune(self) -> None:
        try:
            candidates: list[tuple[float, Path]] = []
            for path in self.root.glob("*.json"):
                try:
                    st = path.stat()
                except OSError:
                    continue
                candidates.append((st.st_mtime, path))
        except OSError:
            return
        if len(candidates) <= self.max_entries:
            return
        candidates.sort(key=lambda item: item[0])
        for _, path in candidates[: len(candidates) - self.max_entries]:
            try:
                path.unlink()
            except OSError:
                pass

    def save_success(
        self,
        *,
        fingerprint: str,
        service: str,
        models: list[DiscoveredModel],
        complete: bool,
        empty: bool,
    ) -> CacheEntry:
        now = self.now()
        ttl = EMPTY_SUCCESS_TTL if empty else FRESH_SUCCESS_TTL
        entry = CacheEntry(
            fingerprint=fingerprint,
            service=service,
            status="empty" if empty else "ok",
            models=list(models),
            complete=complete,
            fetched_at=now,
            expires_at=now + ttl,
            last_used_at=now,
        )
        self._write(entry)
        return entry

    def record_failure(
        self,
        *,
        fingerprint: str,
        service: str,
        error: DiscoveryError,
    ) -> CacheEntry:
        now = self.now()
        existing = self.load(fingerprint)
        if existing is not None and existing.has_success:
            existing.last_failure_at = now
            existing.last_failure = error
            existing.last_used_at = now
            self._write(existing)
            return existing
        entry = CacheEntry(
            fingerprint=fingerprint,
            service=service,
            status="failure",
            models=[],
            complete=False,
            fetched_at=None,
            expires_at=None,
            last_used_at=now,
            last_failure_at=now,
            last_failure=error,
        )
        self._write(entry)
        return entry

    def touch(self, fingerprint: str) -> None:
        path = self._path(fingerprint)
        try:
            os.utime(path, None)
        except OSError:
            pass
        # Last used is tracked by mtime for LRU pruning; no content rewrite
        # is needed on a read.


def cache_state_for(entry: CacheEntry | None, now: datetime) -> CacheState:
    if entry is None:
        return CacheState.MISS
    if entry.fresh(now):
        return CacheState.FRESH
    if entry.has_success:
        return CacheState.STALE
    return CacheState.NONE


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "CacheEntry",
    "CacheIOError",
    "DiscoveryCache",
    "EMPTY_SUCCESS_TTL",
    "FAILURE_COOLDOWN",
    "FRESH_SUCCESS_TTL",
    "MAX_CACHE_ENTRIES",
    "STALE_RETENTION",
    "cache_state_for",
]
