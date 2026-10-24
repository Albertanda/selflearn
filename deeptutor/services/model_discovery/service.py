"""Directory discovery orchestration: credentials, cache, limits, and errors."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from deeptutor.services.config.model_catalog import CATALOG_SECRET_MASK

from .adapters import ClientFactory, fetch_catalog
from .cache import CacheEntry, CacheIOError, DiscoveryCache, cache_state_for
from .compatibility import presets_for
from .types import (
    CacheInfo,
    CacheState,
    Connection,
    DiscoveredModel,
    DiscoveryError,
    DiscoveryErrorCode,
    DiscoveryRequestError,
    DiscoveryResult,
    DiscoveryStatus,
    DiscoveryUpstreamError,
    canonical_endpoint,
    iso_utc,
    url_origin,
    utc_now,
    validate_base_url,
    validate_directory_url,
    validate_mode,
    validate_service,
)


def _empty_catalog() -> dict[str, Any]:
    return {"version": 1, "services": {}}


def _read_catalog(path: Path) -> dict[str, Any]:
    """Read the catalog without normalization or any write.

    ``ModelCatalogService.load()`` may add defaults and save them.  Discovery
    must be able to resolve credentials while leaving the catalog byte-for-byte
    unchanged, so this path is intentionally read-only.
    """

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_catalog()
    except UnicodeDecodeError as exc:
        raise DiscoveryRequestError(
            "The saved model catalog is not valid UTF-8.", status_code=500
        ) from exc
    except OSError as exc:
        raise DiscoveryRequestError(
            "Could not read the saved model catalog.", status_code=500
        ) from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryRequestError(
            "The saved model catalog is not valid JSON.", status_code=500
        ) from exc
    return payload if isinstance(payload, dict) else _empty_catalog()


def _services(catalog: Mapping[str, Any]) -> Mapping[str, Any]:
    services = catalog.get("services")
    return services if isinstance(services, Mapping) else {}


def _profiles(catalog: Mapping[str, Any], service: str) -> list[Mapping[str, Any]]:
    service_payload = _services(catalog).get(service)
    if not isinstance(service_payload, Mapping):
        return []
    profiles = service_payload.get("profiles")
    if not isinstance(profiles, list):
        return []
    return [profile for profile in profiles if isinstance(profile, Mapping)]


def _active_profile(catalog: Mapping[str, Any], service: str) -> Mapping[str, Any] | None:
    service_payload = _services(catalog).get(service)
    if not isinstance(service_payload, Mapping):
        return None
    active_id = str(service_payload.get("active_profile_id") or "")
    profiles = _profiles(catalog, service)
    for profile in profiles:
        if str(profile.get("id") or "") == active_id:
            return profile
    return profiles[0] if profiles else None


def _header_dict(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): str(item) for key, item in parsed.items()}
    return {}


def _saved_connection(profile: Mapping[str, Any]) -> Connection:
    return Connection.from_mapping(
        {
            "binding": profile.get("binding") or profile.get("provider") or "",
            "base_url": profile.get("base_url") or "",
            "api_key": profile.get("api_key") or "",
            "api_version": profile.get("api_version") or "",
            "extra_headers": _header_dict(profile.get("extra_headers")),
            "model_directory_url": profile.get("model_directory_url") or "",
        }
    )


def _is_managed(profile: Mapping[str, Any]) -> bool:
    binding = str(profile.get("binding") or "").strip().lower().replace("-", "_")
    return bool(profile.get("managed_by") or profile.get("read_only")) or binding in {
        "codex",
        "openai_codex",
        "codebuddy",
        "codebuddy_code",
        "workbuddy",
    }


class ModelDiscoveryService:
    """One process-wide service instance per owner/cache/catalog path."""

    _instances: dict[tuple[str, str, str], "ModelDiscoveryService"] = {}

    def __init__(
        self,
        *,
        catalog_path: Path,
        cache_root: Path,
        owner: str,
        client_factory: ClientFactory | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.cache = DiscoveryCache(Path(cache_root), now=now)
        self.owner = owner
        self.client_factory = client_factory
        self.now = now
        self._inflight: dict[str, asyncio.Task[DiscoveryResult]] = {}

    @classmethod
    def for_owner(
        cls,
        *,
        catalog_path: Path,
        cache_root: Path,
        owner: str,
        client_factory: ClientFactory | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> "ModelDiscoveryService":
        key = (str(Path(catalog_path).resolve()), str(Path(cache_root).resolve()), owner)
        instance = cls._instances.get(key)
        if instance is None:
            instance = cls(
                catalog_path=catalog_path,
                cache_root=cache_root,
                owner=owner,
                client_factory=client_factory,
                now=now,
            )
            cls._instances[key] = instance
        return instance

    def _resolve(
        self,
        service: str,
        profile_id: str | None,
        connection: Mapping[str, Any] | None,
    ) -> tuple[Connection, str | None, Mapping[str, Any] | None]:
        catalog = _read_catalog(self.catalog_path)
        saved: Mapping[str, Any] | None = None
        if profile_id:
            for profile in _profiles(catalog, service):
                if str(profile.get("id") or "") == profile_id:
                    saved = profile
                    break
            if saved is None:
                raise DiscoveryRequestError(
                    "The selected profile does not exist for this service.",
                    status_code=404,
                )
        elif connection is None:
            saved = _active_profile(catalog, service)
            if saved is None:
                raise DiscoveryRequestError(
                    "No saved profile is configured for this service.",
                    status_code=400,
                )
            profile_id = str(saved.get("id") or "") or None

        if saved is not None and _is_managed(saved):
            raise DiscoveryRequestError(
                "Managed OAuth profiles are configured through their dedicated card, not model discovery.",
                status_code=400,
            )

        if connection is None and saved is not None:
            resolved = _saved_connection(saved)
        else:
            raw = dict(connection or {})
            if saved is not None:
                base = _saved_connection(saved)
                binding = (
                    str(raw.get("binding")) if raw.get("binding") is not None else base.binding
                )
                base_url = (
                    str(raw.get("base_url")) if raw.get("base_url") is not None else base.base_url
                )
                raw_key = raw.get("api_key")
                if raw_key is None or raw_key == CATALOG_SECRET_MASK:
                    api_key = base.api_key
                    restored_key = bool(base.api_key)
                else:
                    api_key = str(raw_key)
                    restored_key = False
                raw_version = raw.get("api_version")
                api_version = base.api_version if raw_version is None else str(raw_version)
                raw_directory_url = raw.get("model_directory_url")
                directory_url = (
                    base.model_directory_url
                    if raw_directory_url is None
                    else str(raw_directory_url).strip()
                )
                raw_headers = raw.get("extra_headers")
                if raw_headers is None or raw_headers == CATALOG_SECRET_MASK:
                    headers = base.headers
                    restored_headers = bool(headers)
                else:
                    if isinstance(raw_headers, str):
                        try:
                            raw_headers = json.loads(raw_headers)
                        except ValueError as exc:
                            raise DiscoveryRequestError(
                                "extra_headers must be a JSON object.", status_code=400
                            ) from exc
                    if not isinstance(raw_headers, Mapping):
                        raise DiscoveryRequestError(
                            "extra_headers must be an object.", status_code=400
                        )
                    headers = {}
                    restored_headers = False
                    for key, value in raw_headers.items():
                        name = str(key)
                        if value == CATALOG_SECRET_MASK:
                            if name not in base.headers:
                                raise DiscoveryRequestError(
                                    "A masked header has no saved value for this profile.",
                                    status_code=400,
                                )
                            headers[name] = base.headers[name]
                            restored_headers = True
                        elif value is None or isinstance(value, (dict, list)):
                            raise DiscoveryRequestError(
                                "extra_headers values must be strings.", status_code=400
                            )
                        else:
                            headers[name] = str(value)
                resolved = Connection.from_mapping(
                    {
                        "binding": binding,
                        "base_url": base_url,
                        "api_key": api_key,
                        "api_version": api_version,
                        "extra_headers": headers,
                        "model_directory_url": directory_url,
                    }
                )
                if restored_key or restored_headers:
                    identity_changed = (
                        resolved.provider_identity(service)
                        != base.provider_identity(service)
                    )
                    if canonical_endpoint(resolved.base_url) != canonical_endpoint(
                        base.base_url
                    ) and url_origin(resolved.base_url) != url_origin(base.base_url):
                        identity_changed = True
                    if (
                        directory_url
                        and directory_url != base.model_directory_url
                        and url_origin(directory_url) != url_origin(base.base_url)
                    ):
                        identity_changed = True
                    if identity_changed:
                        raise DiscoveryRequestError(
                            "The provider identity or URL origin changed. Re-enter credentials before querying.",
                            status_code=409,
                            code=DiscoveryErrorCode.CREDENTIAL_REENTRY_REQUIRED,
                        )
            else:
                raw_key = raw.get("api_key")
                if raw_key == CATALOG_SECRET_MASK:
                    raise DiscoveryRequestError(
                        "A masked API key requires a saved profile.",
                        status_code=400,
                    )
                raw_headers = raw.get("extra_headers")
                if isinstance(raw_headers, Mapping) and any(
                    value == CATALOG_SECRET_MASK for value in raw_headers.values()
                ):
                    raise DiscoveryRequestError(
                        "A masked header requires a saved profile.",
                        status_code=400,
                    )
                resolved = Connection.from_mapping(raw)
            profile_id = profile_id if saved is not None else None

        validate_base_url(resolved.base_url)
        if resolved.model_directory_url:
            validate_directory_url(resolved.model_directory_url)
        if not resolved.binding:
            raise DiscoveryRequestError("A provider binding is required.", status_code=400)
        if resolved.provider_identity(service) in {"openai_codex", "codebuddy"}:
            raise DiscoveryRequestError(
                "Managed OAuth profiles are configured through their dedicated card, not model discovery.",
                status_code=400,
            )
        return resolved, profile_id, saved

    def _cache_info(self, entry: CacheEntry | None) -> CacheInfo:
        if entry is None:
            return CacheInfo(state=CacheState.MISS)
        state = cache_state_for(entry, self.now())
        if state == CacheState.NONE:
            return CacheInfo(state=CacheState.NONE)
        return CacheInfo(
            state=state,
            fetched_at=iso_utc(entry.fetched_at),
            expires_at=iso_utc(entry.expires_at),
        )

    def _preset_models(self, service: str, adapter: str) -> list[DiscoveredModel]:
        return [preset.to_discovered() for preset in presets_for(service, adapter)]

    def _error_result(
        self,
        *,
        service: str,
        profile_id: str | None,
        error: DiscoveryError,
        entry: CacheEntry | None,
        fallback_models: list[DiscoveredModel] | None = None,
    ) -> DiscoveryResult:
        if entry is not None and entry.has_success and entry.in_stale_window(self.now()):
            return DiscoveryResult(
                service=service,
                profile_id=profile_id,
                status=DiscoveryStatus.ERROR,
                models=tuple(entry.models),
                cache=CacheInfo(
                    state=CacheState.STALE,
                    fetched_at=iso_utc(entry.fetched_at),
                    expires_at=iso_utc(entry.expires_at),
                ),
                complete=entry.complete,
                error=error,
            )
        return DiscoveryResult(
            service=service,
            profile_id=profile_id,
            status=DiscoveryStatus.ERROR,
            models=tuple(fallback_models or []),
            cache=self._cache_info(None),
            complete=False,
            error=error,
        )

    async def discover(
        self,
        *,
        service: str,
        profile_id: str | None = None,
        mode: str = "cache_first",
        connection: Mapping[str, Any] | None = None,
    ) -> DiscoveryResult:
        service = validate_service(service)
        mode = validate_mode(mode)
        resolved, profile_id, saved = self._resolve(service, profile_id, connection)
        from .types import adapter_kind

        adapter = adapter_kind(service, resolved)
        if adapter == "unsupported":
            return DiscoveryResult(
                service=service,
                profile_id=profile_id,
                status=DiscoveryStatus.UNSUPPORTED,
                models=(),
                cache=CacheInfo(state=CacheState.NONE),
                complete=False,
                error=DiscoveryError(
                    DiscoveryErrorCode.UNSUPPORTED,
                    "This provider does not have an online model directory adapter in this build. Configure models manually; the saved connection is unchanged.",
                    retryable=False,
                ),
            )

        fingerprint = resolved.fingerprint(owner=self.owner, service=service, profile_id=profile_id)
        entry: CacheEntry | None = None
        try:
            entry = self.cache.load(fingerprint)
        except CacheIOError:
            entry = None

        if mode == "cache_first":
            if entry is not None and entry.fresh(self.now()):
                self.cache.touch(fingerprint)
                return DiscoveryResult(
                    service=service,
                    profile_id=profile_id,
                    status=(
                        DiscoveryStatus.EMPTY if entry.status == "empty" else DiscoveryStatus.OK
                    ),
                    models=tuple(entry.models),
                    cache=self._cache_info(entry),
                    complete=entry.complete,
                )
            if entry is not None and entry.in_failure_cooldown(self.now()):
                error = entry.last_failure or DiscoveryError(
                    DiscoveryErrorCode.UNAVAILABLE,
                    "The last directory query failed; retry is cooling down.",
                    True,
                )
                return self._error_result(
                    service=service,
                    profile_id=profile_id,
                    error=error,
                    entry=entry,
                    fallback_models=self._preset_models(service, adapter),
                )

        task_key = fingerprint
        existing = self._inflight.get(task_key)
        if existing is not None:
            return await asyncio.shield(existing)

        task = asyncio.create_task(
            self._fetch_and_store(
                service=service,
                profile_id=profile_id,
                adapter=adapter,
                connection=resolved,
                fingerprint=fingerprint,
                prior=entry,
            )
        )
        self._inflight[task_key] = task

        def completed(finished):
            if self._inflight.get(task_key) is finished:
                self._inflight.pop(task_key, None)
            if not finished.cancelled():
                finished.exception()

        # Shielded work survives an HTTP waiter disconnect. Only the work's
        # completion releases single-flight, not the first waiter's finally.
        task.add_done_callback(completed)
        return await asyncio.shield(task)

    async def _fetch_and_store(
        self,
        *,
        service: str,
        profile_id: str | None,
        adapter: str,
        connection: Connection,
        fingerprint: str,
        prior: CacheEntry | None,
    ) -> DiscoveryResult:
        try:
            outcome = await fetch_catalog(
                connection,
                service,
                adapter,
                client_factory=self.client_factory,
                now=self.now,
            )
        except DiscoveryUpstreamError as exc:
            error = DiscoveryError(exc.code, exc.message, exc.retryable)
            return self._after_failure(
                service=service,
                profile_id=profile_id,
                adapter=adapter,
                fingerprint=fingerprint,
                error=error,
                prior=prior,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — never let a provider shape crash the API
            error = DiscoveryError(
                DiscoveryErrorCode.INVALID_RESPONSE,
                "The provider directory response could not be processed.",
                False,
            )
            return self._after_failure(
                service=service,
                profile_id=profile_id,
                adapter=adapter,
                fingerprint=fingerprint,
                error=error,
                prior=prior,
            )

        if outcome.error is not None:
            error = DiscoveryError(
                outcome.error.code, outcome.error.message, outcome.error.retryable
            )
            # Keep any safely parsed partial candidates, but never cache a
            # partial directory as complete.
            try:
                self.cache.record_failure(fingerprint=fingerprint, service=service, error=error)
            except CacheIOError:
                pass
            if prior is not None and prior.has_success and prior.in_stale_window(self.now()):
                return self._error_result(
                    service=service,
                    profile_id=profile_id,
                    error=error,
                    entry=prior,
                )
            return DiscoveryResult(
                service=service,
                profile_id=profile_id,
                status=DiscoveryStatus.ERROR,
                models=tuple(outcome.models),
                cache=self._cache_info(None),
                complete=False,
                error=error,
            )

        if not outcome.remote:
            return DiscoveryResult(
                service=service,
                profile_id=profile_id,
                status=(DiscoveryStatus.OK if outcome.models else DiscoveryStatus.EMPTY),
                models=tuple(outcome.models),
                cache=CacheInfo(state=CacheState.NONE),
                complete=True,
            )

        cache_io_error: DiscoveryError | None = None
        saved_entry: CacheEntry | None = None
        if outcome.complete:
            try:
                saved_entry = self.cache.save_success(
                    fingerprint=fingerprint,
                    service=service,
                    models=outcome.models,
                    complete=True,
                    empty=not outcome.models,
                )
            except CacheIOError:
                cache_io_error = DiscoveryError(
                    DiscoveryErrorCode.CACHE_IO,
                    "The directory was fetched, but the server cache could not be written. The result is usable for this request.",
                    retryable=False,
                )
        else:
            error = DiscoveryError(
                DiscoveryErrorCode.INCOMPLETE,
                "The provider directory was too large or pagination did not complete; this partial result was not cached.",
                retryable=False,
            )
            try:
                self.cache.record_failure(fingerprint=fingerprint, service=service, error=error)
            except CacheIOError:
                pass
            return DiscoveryResult(
                service=service,
                profile_id=profile_id,
                status=DiscoveryStatus.ERROR,
                models=tuple(outcome.models),
                cache=CacheInfo(state=CacheState.NONE),
                complete=False,
                error=error,
            )

        return DiscoveryResult(
            service=service,
            profile_id=profile_id,
            status=(
                DiscoveryStatus.EMPTY
                if outcome.complete and not outcome.models
                else DiscoveryStatus.OK
            ),
            models=tuple(outcome.models),
            cache=(
                self._cache_info(saved_entry)
                if cache_io_error is None
                else CacheInfo(state=CacheState.NONE)
            ),
            complete=outcome.complete,
            error=cache_io_error,
        )

    def _after_failure(
        self,
        *,
        service: str,
        profile_id: str | None,
        adapter: str,
        fingerprint: str,
        error: DiscoveryError,
        prior: CacheEntry | None,
    ) -> DiscoveryResult:
        try:
            stored = self.cache.record_failure(
                fingerprint=fingerprint, service=service, error=error
            )
        except CacheIOError:
            stored = prior
        if prior is not None and prior.has_success and prior.in_stale_window(self.now()):
            return self._error_result(
                service=service,
                profile_id=profile_id,
                error=error,
                entry=prior,
            )
        if stored is not None and stored.has_success:
            return self._error_result(
                service=service,
                profile_id=profile_id,
                error=error,
                entry=stored,
            )
        return DiscoveryResult(
            service=service,
            profile_id=profile_id,
            status=DiscoveryStatus.ERROR,
            models=tuple(self._preset_models(service, adapter)),
            cache=self._cache_info(None),
            complete=False,
            error=error,
        )


def get_model_discovery_service() -> ModelDiscoveryService:
    from deeptutor.multi_user.context import get_current_user
    from deeptutor.services.path_service import get_path_service

    user = get_current_user()
    path_service = get_path_service()
    return ModelDiscoveryService.for_owner(
        catalog_path=path_service.get_settings_file("model_catalog"),
        cache_root=path_service.get_user_root() / "cache" / "model-discovery",
        owner=str(user.id),
    )


__all__ = ["ModelDiscoveryService", "get_model_discovery_service"]
