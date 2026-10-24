"""Pure types and normalization helpers for model discovery.

This module deliberately has no network, filesystem, or catalog IO.  Every
value that reaches an API response or a cache file is normalized here so the
adapter, cache, and router can share one definition of a safe candidate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DISCOVERY_SERVICES: tuple[str, ...] = (
    "llm",
    "embedding",
    "stt",
    "tts",
    "imagegen",
    "videogen",
    "vision",
)
DISCOVERY_SERVICE_SET = frozenset(DISCOVERY_SERVICES)
SEARCH_SERVICE = "search"
MAX_MODEL_ID_LENGTH = 512
MAX_MODEL_NAME_LENGTH = 256
MAX_MODELS = 10_000
MAX_PAGES = 100
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REMOTE_CONCURRENCY = 4
REFRESH_DEADLINE_SECONDS = 30.0

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_HINTS = (
    "authorization",
    "api-key",
    "apikey",
    "api_key",
    "token",
    "secret",
    "password",
    "cookie",
    "credential",
    "x-goog-api-key",
)


class DiscoveryStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class CacheState(str, Enum):
    MISS = "miss"
    FRESH = "fresh"
    STALE = "stale"
    NONE = "none"


class Classification(str, Enum):
    PROVIDER = "provider"
    CURATED = "curated"
    UNKNOWN = "unknown"


class RuntimeCompatibility(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ModelSource(str, Enum):
    REMOTE = "remote"
    PRESET = "preset"


class DiscoveryErrorCode(str, Enum):
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    INCOMPLETE = "INCOMPLETE"
    CACHE_IO = "CACHE_IO"
    CREDENTIAL_REENTRY_REQUIRED = "CREDENTIAL_REENTRY_REQUIRED"
    BAD_REQUEST = "BAD_REQUEST"


class DiscoveryRequestError(ValueError):
    """A caller-facing request problem (HTTP 4xx, never an upstream failure)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: DiscoveryErrorCode | str = DiscoveryErrorCode.BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code.value if isinstance(code, DiscoveryErrorCode) else str(code)


class DiscoveryUpstreamError(RuntimeError):
    """A normalized upstream failure that must be represented in the envelope."""

    def __init__(
        self,
        code: DiscoveryErrorCode,
        message: str,
        *,
        retryable: bool = True,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_service(value: Any) -> str:
    service = str(value or "").strip().lower()
    if service == SEARCH_SERVICE:
        raise DiscoveryRequestError(
            "Search is not a model service and has no discovery endpoint.",
            status_code=422,
            code=DiscoveryErrorCode.BAD_REQUEST,
        )
    if service not in DISCOVERY_SERVICE_SET:
        raise DiscoveryRequestError(
            "service must be one of llm, embedding, stt, tts, imagegen, videogen, vision.",
            status_code=422,
            code=DiscoveryErrorCode.BAD_REQUEST,
        )
    return service


def validate_mode(value: Any) -> str:
    mode = str(value or "cache_first").strip().lower()
    if mode not in {"cache_first", "refresh"}:
        raise DiscoveryRequestError(
            "mode must be cache_first or refresh.",
            status_code=422,
            code=DiscoveryErrorCode.BAD_REQUEST,
        )
    return mode


def clean_model_id(value: Any) -> str:
    """Normalize a provider model id without changing its meaningful spelling."""

    if not isinstance(value, str):
        raise ValueError("model id must be a string")
    model_id = value.strip()
    if not model_id:
        raise ValueError("model id is empty")
    if len(model_id) > MAX_MODEL_ID_LENGTH:
        raise ValueError("model id is too long")
    if _CONTROL_CHARS.search(model_id):
        raise ValueError("model id contains control characters")
    return model_id


def clean_model_name(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ValueError("model name must be a string")
    name = _CONTROL_CHARS.sub("", value).strip()
    if not name:
        return fallback
    return name[:MAX_MODEL_NAME_LENGTH]


def coerce_context_window(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


@dataclass(frozen=True, slots=True)
class DiscoveryError:
    code: DiscoveryErrorCode
    message: str
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code.value, "message": self.message, "retryable": self.retryable}


@dataclass(frozen=True, slots=True)
class Connection:
    """The exact connection identity used for one discovery request.

    Secrets are held in memory only.  ``credential_digest`` and the cache code
    never persist these raw values.
    """

    binding: str
    base_url: str
    api_key: str = ""
    api_version: str = ""
    extra_headers: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    model_directory_url: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "Connection":
        if value is None:
            return cls(binding="", base_url="")
        binding = str(value.get("binding") or "").strip()
        base_url = str(value.get("base_url") or "").strip()
        api_key = str(value.get("api_key") or "") if value.get("api_key") is not None else ""
        api_version = (
            str(value.get("api_version") or "").strip()
            if value.get("api_version") is not None
            else ""
        )
        raw_directory_url = value.get("model_directory_url")
        model_directory_url = (
            str(raw_directory_url).strip()
            if raw_directory_url is not None
            else ""
        )
        if model_directory_url:
            validate_directory_url(model_directory_url)
        raw_headers = value.get("extra_headers")
        headers: dict[str, str] = {}
        if isinstance(raw_headers, str):
            text = raw_headers.strip()
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise DiscoveryRequestError("extra_headers is not valid JSON.") from exc
                raw_headers = parsed
        if raw_headers is not None:
            if not isinstance(raw_headers, Mapping):
                raise DiscoveryRequestError("extra_headers must be an object.")
            for key, item_value in raw_headers.items():
                name = str(key).strip()
                if not name or _CONTROL_CHARS.search(name) or ":" in name:
                    raise DiscoveryRequestError("extra_headers contains an invalid name.")
                if isinstance(item_value, (dict, list)) or item_value is None:
                    raise DiscoveryRequestError("extra_headers values must be strings.")
                value_text = str(item_value)
                if "\r" in value_text or "\n" in value_text or "\x00" in value_text:
                    raise DiscoveryRequestError("extra_headers contains an invalid value.")
                headers[name] = value_text
        return cls(
            binding=binding,
            base_url=base_url,
            api_key=api_key,
            api_version=api_version,
            extra_headers=tuple(sorted(headers.items(), key=lambda item: item[0].lower())),
            model_directory_url=model_directory_url,
        )

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.extra_headers)

    @property
    def canonical_binding(self) -> str:
        return canonicalize_binding(self.binding)

    def provider_identity(self, service: str) -> str:
        from .provider_policy import provider_identity

        return provider_identity(self.binding, service)

    def header_digest(self) -> str:
        payload = json.dumps(
            [[name, value] for name, value in self.extra_headers],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def credential_digest(self) -> str:
        payload = json.dumps(
            [self.api_key, [list(item) for item in self.extra_headers]],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def identity(self, *, owner: str, service: str, profile_id: str | None) -> dict[str, Any]:
        """Return the non-secret cache namespace identity."""

        return {
            "owner": owner,
            "service": service,
            "profile_id": profile_id or "",
            "binding": self.provider_identity(service),
            "base_url": canonical_endpoint(self.base_url),
            "directory_url": canonical_endpoint(self.model_directory_url)
            if self.model_directory_url
            else "",
            "api_version": self.api_version,
            "policy_schema_version": 2,
            "credential": self.credential_digest(),
            "headers": self.header_digest(),
        }

    def fingerprint(self, *, owner: str, service: str, profile_id: str | None) -> str:
        raw = json.dumps(
            self.identity(owner=owner, service=service, profile_id=profile_id),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def public_dict(self) -> dict[str, Any]:
        """Only safe fields; used in diagnostics and tests, never with secrets."""

        return {
            "binding": self.canonical_binding,
            "base_url": self.base_url,
            "model_directory_url": self.model_directory_url,
            "api_version": self.api_version,
            "header_names": [name for name, _ in self.extra_headers],
            "has_api_key": bool(self.api_key),
        }


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    id: str
    name: str
    services: tuple[str, ...] = field(default_factory=tuple)
    classification: Classification = Classification.UNKNOWN
    runtime_compatibility: RuntimeCompatibility = RuntimeCompatibility.UNKNOWN
    reason_code: str | None = None
    source: ModelSource = ModelSource.REMOTE
    callability: str = "not_tested"
    context_window: int | None = None
    parameters: Any | None = None
    reasoning_controls: Any | None = None
    resource_name: str | None = None
    deployment_mapping_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        parameters = (
            self.parameters.to_dict()
            if self.parameters is not None and hasattr(self.parameters, "to_dict")
            else None
        )
        reasoning_controls = (
            self.reasoning_controls.to_dict()
            if self.reasoning_controls is not None
            and hasattr(self.reasoning_controls, "to_dict")
            else None
        )
        context_window = None
        if isinstance(parameters, Mapping):
            value = parameters.get("context_window")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                context_window = value
        if context_window is None:
            context_window = self.context_window
        return {
            "id": self.id,
            "name": self.name,
            "services": list(self.services),
            "classification": self.classification.value,
            "runtime_compatibility": self.runtime_compatibility.value,
            "reason_code": self.reason_code,
            "source": self.source.value,
            "callability": "not_tested",
            "metadata_schema_version": 1,
            **({"context_window": context_window} if context_window else {}),
            **({"parameters": parameters} if parameters else {}),
            **(
                {"reasoning_controls": reasoning_controls}
                if reasoning_controls
                else {}
            ),
            **({"resource_name": self.resource_name} if self.resource_name else {}),
            **(
                {"deployment_mapping_required": True}
                if self.deployment_mapping_required
                else {}
            ),
        }


@dataclass(frozen=True, slots=True)
class CacheInfo:
    state: CacheState = CacheState.NONE
    fetched_at: str | None = None
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "fetched_at": self.fetched_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    service: str
    profile_id: str | None
    status: DiscoveryStatus
    models: tuple[DiscoveredModel, ...] = field(default_factory=tuple)
    cache: CacheInfo = field(default_factory=CacheInfo)
    complete: bool = True
    error: DiscoveryError | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "service": self.service,
            "profile_id": self.profile_id,
            "status": self.status.value,
            "models": [model.to_dict() for model in self.models],
            "cache": self.cache.to_dict(),
            "complete": self.complete,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass(frozen=True, slots=True)
class PresetModel:
    """A small, traceable fallback candidate from this project's own registry."""

    id: str
    name: str
    service: str
    runtime_compatibility: RuntimeCompatibility = RuntimeCompatibility.SUPPORTED
    reason_code: str | None = None

    def to_discovered(self) -> DiscoveredModel:
        return DiscoveredModel(
            id=self.id,
            name=self.name,
            services=(self.service,),
            classification=Classification.CURATED,
            runtime_compatibility=self.runtime_compatibility,
            reason_code=self.reason_code,
            source=ModelSource.PRESET,
        )


# ---------------------------------------------------------------------------
# URL and provider identity helpers
# ---------------------------------------------------------------------------

_ALIYUN_DASHSCOPE_SUFFIX = ".dashscope.aliyuncs.com"
_ALIYUN_MAAS_SUFFIX = ".maas.aliyuncs.com"
_SILICONFLOW_SUFFIXES = (".siliconflow.cn", ".siliconflow.com")


def canonicalize_binding(binding: str | None) -> str:
    """Return the provider identity for an LLM connection.

    This is deliberately *not* the transport family: openai/custom/vllm/
    lm_studio keep their own identity so credentials and cache entries cannot
    bleed across providers that merely share a wire protocol.  Aliyun's stable
    LLM identity is ``dashscope``.
    """

    from .provider_policy import provider_identity

    return provider_identity(binding, "llm")


def validate_base_url(value: str, *, required: bool = True) -> str:
    raw = (value or "").strip()
    if not raw:
        if required:
            raise DiscoveryRequestError("base_url is required.", status_code=400)
        return ""
    if any(char in raw for char in ("\r", "\n", "\x00")):
        raise DiscoveryRequestError("base_url contains invalid characters.")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise DiscoveryRequestError("base_url is not a valid URL.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise DiscoveryRequestError("base_url must use http or https.")
    if not parsed.hostname:
        raise DiscoveryRequestError("base_url must include a host.")
    if parsed.username or parsed.password:
        raise DiscoveryRequestError("base_url must not contain userinfo.")
    if parsed.fragment:
        raise DiscoveryRequestError("base_url must not contain a fragment.")
    try:
        parsed.port
    except ValueError as exc:
        raise DiscoveryRequestError("base_url contains an invalid port.") from exc
    return raw


def validate_directory_url(value: str) -> str:
    """Validate an optional complete directory URL (query allowed)."""

    raw = (value or "").strip()
    if not raw:
        return ""
    if any(char in raw for char in ("\r", "\n", "\x00")):
        raise DiscoveryRequestError("model_directory_url contains invalid characters.")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise DiscoveryRequestError("model_directory_url is not a valid URL.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise DiscoveryRequestError("model_directory_url must use http or https.")
    if not parsed.hostname:
        raise DiscoveryRequestError("model_directory_url must include a host.")
    if parsed.username or parsed.password:
        raise DiscoveryRequestError("model_directory_url must not contain userinfo.")
    if parsed.fragment:
        raise DiscoveryRequestError("model_directory_url must not contain a fragment.")
    try:
        parsed.port
    except ValueError as exc:
        raise DiscoveryRequestError("model_directory_url contains an invalid port.") from exc
    return raw


def canonical_endpoint(value: str) -> str:
    """Canonical form for fingerprints, preserving path, query, and version."""

    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def url_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    return f"{scheme}://{netloc}"


def is_aliyun_official_host(value: str) -> bool:
    host = (urlsplit(value.strip()).hostname or "").lower()
    if not host:
        return False
    if host == "dashscope.aliyuncs.com":
        return True
    if host.endswith(".aliyuncs.com"):
        labels = host.split(".")
        if any(
            label == "dashscope" or label.startswith("dashscope-")
            for label in labels[:-2]
        ):
            return True
    if host.endswith(_ALIYUN_MAAS_SUFFIX):
        # Workspace-business-space host: workspace.region.maas.aliyuncs.com.
        return host.count(".") >= 4
    return False


def is_siliconflow_official_host(value: str) -> bool:
    host = (urlsplit(value.strip()).hostname or "").lower()
    return bool(host) and any(host == suffix[1:] or host.endswith(suffix) for suffix in _SILICONFLOW_SUFFIXES)


def adapter_kind(service: str, connection: Connection) -> str:
    """Select the directory adapter by explicit policy, never by host guess."""

    validate_service(service)
    from .provider_policy import ADAPTER_MANAGED, adapter_for

    adapter = adapter_for(
        binding=connection.binding,
        service=service,
        base_url=connection.base_url,
        directory_url=connection.model_directory_url,
        is_official_aliyun=is_aliyun_official_host,
        is_official_siliconflow=is_siliconflow_official_host,
    )
    return "unsupported" if adapter == ADAPTER_MANAGED else adapter


def append_url_path(base_url: str, suffix: str) -> str:
    """Append ``suffix`` to a base URL's path, preserving query parameters."""

    parsed = urlsplit(base_url.strip())
    base_path = parsed.path.rstrip("/")
    suffix_path = "/" + suffix.lstrip("/")
    path = f"{base_path}{suffix_path}" if base_path else suffix_path
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def replace_url_path(base_url: str, path: str) -> str:
    parsed = urlsplit(base_url.strip())
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def with_query_params(url: str, params: Mapping[str, str | int | None]) -> str:
    parsed = urlsplit(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    existing = {key for key, _ in query}
    for key, value in params.items():
        if value is None or key in existing:
            continue
        query.append((key, str(value)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def is_secret_header(name: str) -> bool:
    normalized = name.strip().lower()
    return any(hint in normalized for hint in _SECRET_HINTS)


def redact_headers(headers: Iterable[tuple[str, str]]) -> list[str]:
    return [name for name, _ in headers if not is_secret_header(name)]


def sanitize_upstream_text(value: str, *, limit: int = 200) -> str:
    """Strip control characters and cap an upstream message.

    Callers should generally prefer a fixed project message. This helper only
    exists for safe diagnostic snippets that contain no URL, credential, or
    response body.
    """

    text = _CONTROL_CHARS.sub(" ", str(value or "")).strip()
    return text[:limit]


# ---------------------------------------------------------------------------
# Candidate merge and visibility helpers
# ---------------------------------------------------------------------------


def model_visible(model: Mapping[str, Any] | None) -> bool:
    """Display preference only; missing means visible and is never migrated."""

    if not isinstance(model, Mapping):
        return True
    return model.get("visible_in_picker") is not False


def is_current_llm_default(catalog: Mapping[str, Any], profile_id: str, model_id: str) -> bool:
    service = (
        catalog.get("services", {}).get("llm", {})
        if isinstance(catalog.get("services"), Mapping)
        else {}
    )
    return (
        str(service.get("active_profile_id") or "") == profile_id
        and str(service.get("active_model_id") or "") == model_id
    )


def hide_current_default(
    current_catalog: Mapping[str, Any], proposed_catalog: Mapping[str, Any]
) -> tuple[str, str] | None:
    """Return ``(profile_id, model_id)`` when a PUT would hide the saved default."""

    if not isinstance(proposed_catalog, Mapping):
        return None
    proposed_profile_map: dict[str, Mapping[str, Any]] = {}
    services = proposed_catalog.get("services")
    if not isinstance(services, Mapping):
        return None
    llm = services.get("llm")
    if not isinstance(llm, Mapping):
        return None
    for profile in llm.get("profiles", []) or []:
        if isinstance(profile, Mapping):
            profile_id = str(profile.get("id") or "")
            if profile_id:
                proposed_profile_map[profile_id] = profile

    proposed_profile_id = str(llm.get("active_profile_id") or "")
    proposed_model_id = str(llm.get("active_model_id") or "")
    proposed_default_profile = proposed_profile_map.get(proposed_profile_id)
    if isinstance(proposed_default_profile, Mapping) and proposed_model_id:
        for model in proposed_default_profile.get("models", []) or []:
            if not isinstance(model, Mapping):
                continue
            if str(model.get("id") or "") != proposed_model_id:
                continue
            if model.get("visible_in_picker") is False:
                return proposed_profile_id, proposed_model_id
            break

    current_services = current_catalog.get("services")
    if not isinstance(current_services, Mapping):
        return None
    current_llm = current_services.get("llm")
    if not isinstance(current_llm, Mapping):
        return None
    default_profile = str(current_llm.get("active_profile_id") or "")
    default_model = str(current_llm.get("active_model_id") or "")
    if not default_profile or not default_model:
        return None
    proposed_profile = proposed_profile_map.get(default_profile)
    if not isinstance(proposed_profile, Mapping):
        return None
    for model in proposed_profile.get("models", []) or []:
        if not isinstance(model, Mapping):
            continue
        if str(model.get("id") or "") != default_model:
            continue
        if model.get("visible_in_picker") is False:
            return default_profile, default_model
        break
    return None


def merge_candidates(
    existing_models: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any] | DiscoveredModel],
    selected_ids: Iterable[str],
    *,
    service: str,
    id_factory: Any,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Merge selected candidates into a copy of one profile's models.

    Returns ``(models, added_internal_ids, reused_existing_ids)``. Existing
    models always win: their internal id, alias, parameters, and order are
    untouched. Candidates are de-duplicated by exact provider model string
    within this one profile, not globally.
    """

    validate_service(service)
    current = [dict(item) for item in existing_models if isinstance(item, Mapping)]
    by_value: dict[str, str] = {}
    for model in current:
        value = model.get("model")
        if isinstance(value, str) and value and value not in by_value:
            by_value[value] = str(model.get("id") or "")
    selected = {str(item) for item in selected_ids}
    added: list[str] = []
    reused: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, DiscoveredModel):
            model_id = candidate.id
            name = candidate.name
            services = candidate.services
            compat = candidate.runtime_compatibility
        elif isinstance(candidate, Mapping):
            try:
                model_id = clean_model_id(candidate.get("id"))
            except ValueError:
                continue
            name = clean_model_name(candidate.get("name"), model_id)
            raw_services = candidate.get("services") or []
            services = tuple(
                str(item)
                for item in raw_services
                if isinstance(item, str) and item in DISCOVERY_SERVICE_SET
            )
            raw_compat = str(candidate.get("runtime_compatibility") or "unknown")
            try:
                compat = RuntimeCompatibility(raw_compat)
            except ValueError:
                compat = RuntimeCompatibility.UNKNOWN
        else:
            continue
        if model_id not in selected:
            continue
        if compat is RuntimeCompatibility.UNSUPPORTED:
            continue
        if services and service not in services:
            continue
        if model_id in by_value:
            reused.append(by_value[model_id])
            continue
        internal_id = str(id_factory())
        if not internal_id or internal_id in {item.get("id") for item in current}:
            continue
        model: dict[str, Any] = {"id": internal_id, "name": name, "model": model_id}
        current.append(model)
        by_value[model_id] = internal_id
        added.append(internal_id)
    return current, added, reused


__all__ = [
    "CacheInfo",
    "CacheState",
    "Classification",
    "Connection",
    "DISCOVERY_SERVICES",
    "DISCOVERY_SERVICE_SET",
    "DiscoveryError",
    "DiscoveryErrorCode",
    "DiscoveryRequestError",
    "DiscoveryResult",
    "DiscoveryStatus",
    "DiscoveryUpstreamError",
    "DiscoveredModel",
    "MAX_MODELS",
    "MAX_PAGES",
    "MAX_PAGE_BYTES",
    "MAX_TOTAL_BYTES",
    "ModelSource",
    "PresetModel",
    "RuntimeCompatibility",
    "SEARCH_SERVICE",
    "adapter_kind",
    "append_url_path",
    "canonical_endpoint",
    "canonicalize_binding",
    "clean_model_id",
    "clean_model_name",
    "coerce_context_window",
    "hide_current_default",
    "is_aliyun_official_host",
    "is_current_llm_default",
    "is_secret_header",
    "is_siliconflow_official_host",
    "iso_utc",
    "merge_candidates",
    "model_visible",
    "parse_iso_utc",
    "replace_url_path",
    "sanitize_upstream_text",
    "url_origin",
    "utc_now",
    "validate_base_url",
    "validate_directory_url",
    "validate_mode",
    "validate_service",
    "with_query_params",
]
