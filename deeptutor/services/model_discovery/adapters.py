"""Bounded directory adapters for Aliyun, SiliconFlow, compatible APIs, Ollama.

Only metadata endpoints are called.  No inference request, model download, or
pull operation is implemented here.  Authentication headers are attached
explicitly and redirects are never followed, so a credential cannot be
forwarded to another host.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import weakref

import httpx

from .compatibility import (
    aliyun_model,
    anthropic_model,
    azure_model,
    gemini_model,
    generic_model,
    presets_for,
    siliconflow_model,
)
from .types import (
    MAX_MODELS,
    MAX_PAGE_BYTES,
    MAX_PAGES,
    MAX_REMOTE_CONCURRENCY,
    MAX_TOTAL_BYTES,
    REFRESH_DEADLINE_SECONDS,
    Connection,
    DiscoveredModel,
    DiscoveryErrorCode,
    DiscoveryUpstreamError,
    append_url_path,
    clean_model_id,
    clean_model_name,
    iso_utc,
    replace_url_path,
    utc_now,
    with_query_params,
)

ClientFactory = Callable[[], httpx.AsyncClient]

# Share one gate across services/owners in an event loop. Weak values avoid
# retaining closed test loops through a semaphore's bound-loop reference.
_REMOTE_GATES = weakref.WeakKeyDictionary()
_DIRECTORY_LOG_CONTEXT = ContextVar("model_directory_logging", default=False)


def _remote_gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    reference = _REMOTE_GATES.get(loop)
    gate = reference() if reference is not None else None
    if gate is None:
        gate = asyncio.Semaphore(MAX_REMOTE_CONCURRENCY)
        _REMOTE_GATES[loop] = weakref.ref(gate)
    return gate


class _DirectoryLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _DIRECTORY_LOG_CONTEXT.get():
            # httpx logs the entire request URL, including query credentials.
            # Restrict this change to directory requests in this async context;
            # unrelated clients keep their normal logging behavior.
            record.msg = "Model directory HTTP transport event."
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


_DIRECTORY_LOG_FILTER = _DirectoryLogFilter()


@contextmanager
def _directory_logging():
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        if _DIRECTORY_LOG_FILTER not in logger.filters:
            logger.addFilter(_DIRECTORY_LOG_FILTER)
    token = _DIRECTORY_LOG_CONTEXT.set(True)
    try:
        yield
    finally:
        _DIRECTORY_LOG_CONTEXT.reset(token)


_SERVICE_SUBTYPE = {
    "llm": "chat",
    "embedding": "embedding",
    "stt": "speech-to-text",
    "imagegen": "text-to-image",
    "videogen": "text-to-video",
}

_PROVIDER_PAGE_SIZE = 100


@dataclass(slots=True)
class FetchOutcome:
    models: list[DiscoveredModel]
    complete: bool = True
    error: DiscoveryUpstreamError | None = None
    remote: bool = True


@dataclass(slots=True)
class _Budget:
    deadline: float
    bytes_total: int = 0
    pages: int = 0

    def check_time(self) -> None:
        if time.monotonic() >= self.deadline:
            raise DiscoveryUpstreamError(
                DiscoveryErrorCode.TIMEOUT,
                "目录查询超过 30 秒总时限。",
                retryable=True,
            )

    def add_page(self, size: int) -> None:
        self.pages += 1
        if size > MAX_PAGE_BYTES:
            raise DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "目录响应超过单页 2 MiB 限制。",
                retryable=False,
            )
        self.bytes_total += size
        if self.bytes_total > MAX_TOTAL_BYTES:
            raise DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "目录响应超过累计 16 MiB 限制。",
                retryable=False,
            )


def _auth_headers(connection: Connection) -> dict[str, str]:
    headers = dict(connection.extra_headers)
    lowered = {name.lower() for name in headers}
    if connection.api_key and not ({"authorization", "api-key", "x-api-key"} & lowered):
        headers["Authorization"] = f"Bearer {connection.api_key}"
    headers.setdefault("Accept", "application/json")
    return headers


def _anthropic_headers(connection: Connection) -> dict[str, str]:
    headers = dict(connection.extra_headers)
    lowered = {name.lower() for name in headers}
    if connection.api_key and "x-api-key" not in lowered and "authorization" not in lowered:
        headers["x-api-key"] = connection.api_key
    if "anthropic-version" not in lowered:
        headers["anthropic-version"] = connection.api_version or "2023-06-01"
    headers.setdefault("Accept", "application/json")
    return headers


def _gemini_headers(connection: Connection) -> dict[str, str]:
    headers = dict(connection.extra_headers)
    lowered = {name.lower() for name in headers}
    if connection.api_key and not ({"x-goog-api-key", "authorization"} & lowered):
        headers["x-goog-api-key"] = connection.api_key
    headers.setdefault("Accept", "application/json")
    return headers


def _azure_headers(connection: Connection) -> dict[str, str]:
    headers = dict(connection.extra_headers)
    lowered = {name.lower() for name in headers}
    if connection.api_key and not ({"api-key", "authorization"} & lowered):
        headers["api-key"] = connection.api_key
    headers.setdefault("Accept", "application/json")
    return headers


def _is_official_aliyun(base_url: str) -> bool:
    from .types import is_aliyun_official_host

    return is_aliyun_official_host(base_url)


def _source_url(url: str) -> str:
    from .metadata import clean_source_url

    return clean_source_url(url)


def _checked_at(now: Callable[[], datetime] | None) -> str:
    return iso_utc(now() if now is not None else utc_now()) or "1970-01-01T00:00:00Z"


def _directory_url(connection: Connection, *, suffix: str = "models") -> str:
    if connection.model_directory_url:
        return connection.model_directory_url
    url = append_url_path(connection.base_url, suffix)
    if connection.api_version:
        url = with_query_params(url, {"api-version": connection.api_version})
    return url


def _compatible_fallback_url(url: str) -> str | None:
    """At most one terminal /v1 toggle, preserving proxy prefix and query."""

    parsed = urlsplit(url)
    path = parsed.path
    if path.endswith("/v1/models"):
        prefix = path[: -len("/v1/models")]
        candidate_path = f"{prefix}/models" if prefix else "/models"
    elif path.endswith("/models"):
        parent = path[: -len("/models")].rstrip("/")
        last = parent.rsplit("/", 1)[-1].lower()
        if last.startswith("v") and last[1:].isdigit():
            return None
        candidate_path = f"{parent}/v1/models" if parent else "/v1/models"
    else:
        return None
    if candidate_path == path:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, candidate_path, parsed.query, ""))


def _gemini_models_url(connection: Connection) -> str:
    if connection.model_directory_url:
        return connection.model_directory_url
    parsed = urlsplit(connection.base_url.strip())
    path = parsed.path.rstrip("/")
    if path.endswith("/openai"):
        path = path[: -len("/openai")] + "/models"
    elif path.endswith("/models"):
        pass
    else:
        path = path + "/models"
    if not path.startswith("/"):
        path = "/" + path
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _azure_models_url(connection: Connection) -> str:
    if connection.model_directory_url:
        return connection.model_directory_url
    parsed = urlsplit(connection.base_url.strip())
    path = parsed.path.rstrip("/")
    lowered = path.lower()
    if "/openai/deployments/" in lowered:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.UNAVAILABLE,
            "旧版 Azure 部署地址只代表一个部署，无法列出基础模型目录。请填写 /openai/v1 端点或明确的目录地址，并继续手工填写部署名。",
            retryable=False,
        )
    if lowered.endswith("/openai/v1") or lowered.endswith("/v1"):
        path = path + "/models"
    elif "/openai/v1/" in lowered and lowered.endswith("/models"):
        pass
    elif lowered.endswith("/models"):
        pass
    else:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.UNAVAILABLE,
            "Azure 资源根地址没有可直接读取的模型目录。请使用 /openai/v1 端点或明确的目录地址；目录中的 offering 不是部署名。",
            retryable=False,
        )
    url = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))
    if connection.api_version:
        url = with_query_params(url, {"api-version": connection.api_version})
    return url


def _status_error(status_code: int, *, directory: bool) -> DiscoveryUpstreamError:
    if status_code in {401}:
        return DiscoveryUpstreamError(
            DiscoveryErrorCode.AUTH_FAILED,
            "供应商拒绝了凭据。请检查 API Key 后重试。",
            retryable=False,
            status_code=status_code,
        )
    if status_code in {403}:
        return DiscoveryUpstreamError(
            DiscoveryErrorCode.FORBIDDEN,
            "凭据没有读取模型目录的权限。",
            retryable=False,
            status_code=status_code,
        )
    if status_code == 429:
        return DiscoveryUpstreamError(
            DiscoveryErrorCode.RATE_LIMITED,
            "供应商限流，请稍后重试。",
            retryable=True,
            status_code=status_code,
        )
    if status_code in {404, 405} and directory:
        return DiscoveryUpstreamError(
            DiscoveryErrorCode.UNAVAILABLE,
            "该地址没有可用的模型目录；请检查 Base URL，阿里云北京地域可能需要业务空间专属域名。",
            retryable=False,
            status_code=status_code,
        )
    if status_code >= 500:
        return DiscoveryUpstreamError(
            DiscoveryErrorCode.UNAVAILABLE,
            "供应商目录服务暂时不可用。",
            retryable=True,
            status_code=status_code,
        )
    return DiscoveryUpstreamError(
        DiscoveryErrorCode.INVALID_RESPONSE,
        "供应商目录请求被拒绝。",
        retryable=False,
        status_code=status_code,
    )


async def _request_json(
    client: httpx.AsyncClient,
    url: str,
    headers: Mapping[str, str],
    budget: _Budget,
    *,
    directory: bool,
) -> Any:
    budget.check_time()
    try:
        with _directory_logging():
            return await _read_response(client, url, headers, budget, directory=directory)
    except httpx.TimeoutException as exc:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.TIMEOUT,
            "目录查询超时，请稍后重试。",
            retryable=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.UNAVAILABLE,
            "无法连接供应商目录服务。",
            retryable=True,
        ) from exc


async def _read_response(client, url, headers, budget, *, directory):
    async with client.stream("GET", url, headers=dict(headers)) as response:
        status_code = response.status_code
        if 300 <= status_code < 400:
            raise DiscoveryUpstreamError(
                DiscoveryErrorCode.INVALID_RESPONSE,
                "目录接口返回了重定向，已停止且不会转发凭据。",
                retryable=False,
                status_code=status_code,
            )
        if status_code != 200:
            # Do not read or surface the upstream body.
            raise _status_error(status_code, directory=directory)
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_PAGE_BYTES:
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INCOMPLETE,
                    "目录响应超过单页 2 MiB 限制。",
                    retryable=False,
                )
            chunks.append(chunk)
        budget.add_page(size)
        raw = b"".join(chunks)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.INVALID_RESPONSE,
            "供应商返回的目录不是有效 JSON。",
            retryable=False,
        ) from exc


def _dedupe(models: list[DiscoveredModel]) -> list[DiscoveredModel]:
    seen: set[str] = set()
    result: list[DiscoveredModel] = []
    for model in models:
        if model.id in seen:
            continue
        seen.add(model.id)
        result.append(model)
    if len(result) > MAX_MODELS:
        return result[:MAX_MODELS]
    return result


async def fetch_aliyun(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = (
        connection.model_directory_url
        or replace_url_path(connection.base_url, "/api/v1/models")
    )
    headers = _auth_headers(connection)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    models: list[DiscoveredModel] = []
    seen: set[str] = set()
    total: int | None = None
    all_ids: set[str] = set()
    page_no = 1
    complete = False
    async with client_factory() as client:
        while True:
            if page_no > MAX_PAGES:
                return FetchOutcome(
                    models=_dedupe(models),
                    complete=False,
                    error=DiscoveryUpstreamError(
                        DiscoveryErrorCode.INCOMPLETE,
                        "目录超过 100 页上限，未缓存为完整目录。",
                        retryable=False,
                    ),
                )
            page_url = with_query_params(
                url, {"page_no": page_no, "page_size": _PROVIDER_PAGE_SIZE}
            )
            payload = await _request_json(client, page_url, headers, budget, directory=True)
            if not isinstance(payload, Mapping):
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INVALID_RESPONSE,
                    "阿里云目录响应结构无效。",
                    retryable=False,
                )
            output = payload.get("output")
            if not isinstance(output, Mapping):
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INVALID_RESPONSE,
                    "阿里云目录响应缺少 output.models。",
                    retryable=False,
                )
            raw_models = output.get("models")
            if not isinstance(raw_models, list):
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INVALID_RESPONSE,
                    "阿里云目录响应缺少 output.models。",
                    retryable=False,
                )
            try:
                total_value = int(output.get("total") or 0)
            except (TypeError, ValueError):
                total_value = 0
            if total_value > 0:
                total = total_value
                if total > MAX_MODELS:
                    return FetchOutcome(
                        models=_dedupe(models),
                        complete=False,
                        error=DiscoveryUpstreamError(
                            DiscoveryErrorCode.INCOMPLETE,
                            "目录超过 10,000 个模型上限。",
                            retryable=False,
                        ),
                    )
            if not raw_models:
                complete = total is None or len(all_ids) >= total
                break
            raw_ids: set[str] = set()
            for raw in raw_models:
                if not isinstance(raw, Mapping):
                    continue
                raw_id = str(raw.get("model") or raw.get("id") or "").strip()
                if raw_id:
                    raw_ids.add(raw_id)
            if raw_ids and raw_ids <= all_ids:
                return FetchOutcome(
                    models=_dedupe(models),
                    complete=False,
                    error=DiscoveryUpstreamError(
                        DiscoveryErrorCode.INCOMPLETE,
                        "目录分页没有前进，未缓存不完整目录。",
                        retryable=False,
                    ),
                )
            all_ids.update(raw_ids)
            for raw in raw_models:
                if not isinstance(raw, Mapping):
                    continue
                annotated = dict(raw)
                annotated["__source_url"] = source_url
                annotated["__checked_at"] = checked_at
                annotated["__official"] = _is_official_aliyun(source_url)
                model = aliyun_model(annotated, service, requested_service=service)
                if model is None:
                    continue
                if model.id in seen:
                    continue
                seen.add(model.id)
                models.append(model)
                if len(models) > MAX_MODELS:
                    return FetchOutcome(
                        models=_dedupe(models)[:MAX_MODELS],
                        complete=False,
                        error=DiscoveryUpstreamError(
                            DiscoveryErrorCode.INCOMPLETE,
                            "目录超过 10,000 个模型上限。",
                            retryable=False,
                        ),
                    )
            if total is not None and len(all_ids) >= total:
                complete = True
                break
            if total is None and len(raw_models) < _PROVIDER_PAGE_SIZE:
                complete = True
                break
            page_no += 1
    if not complete:
        return FetchOutcome(
            models=_dedupe(models),
            complete=False,
            error=DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "供应商目录在达到声明总数前结束，未缓存为完整目录。",
                retryable=False,
            ),
        )
    return FetchOutcome(models=_dedupe(models), complete=True, error=None)


async def fetch_siliconflow(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    presets = presets_for(service, "siliconflow")
    if service in {"tts", "vision"}:
        # The documented API has no exact sub_type for these categories.  Do
        # not invent one and do not turn every unclassified item into TTS or
        # vision; show only the small project-traceable preset set instead.
        return FetchOutcome(
            models=[item.to_discovered() for item in presets],
            complete=True,
            error=None,
            remote=False,
        )
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = connection.model_directory_url or append_url_path(connection.base_url, "models")
    subtype = None if connection.model_directory_url else _SERVICE_SUBTYPE.get(service)
    if subtype:
        url = with_query_params(url, {"sub_type": subtype})
    headers = _auth_headers(connection)
    async with client_factory() as client:
        payload = await _request_json(client, url, headers, budget, directory=True)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    if isinstance(payload, Mapping):
        raw_models = payload.get("data")
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = None
    if not isinstance(raw_models, list):
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.INVALID_RESPONSE,
            "硅基流动目录响应缺少 data[]。",
            retryable=False,
        )
    models: list[DiscoveredModel] = []
    for raw in raw_models:
        if not isinstance(raw, Mapping):
            continue
        annotated = dict(raw)
        annotated["__source_url"] = source_url
        annotated["__checked_at"] = checked_at
        model = siliconflow_model(annotated, service)
        if model is not None:
            models.append(model)
    if len(models) > MAX_MODELS:
        return FetchOutcome(
            models=_dedupe(models)[:MAX_MODELS],
            complete=False,
            error=DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "目录超过 10,000 个模型上限。",
                retryable=False,
            ),
        )
    return FetchOutcome(models=_dedupe(models), complete=True, error=None)


def _ollama_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    base = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))
    return append_url_path(base, "api/tags")


async def fetch_ollama(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = _ollama_url(connection.base_url)
    headers = _auth_headers(connection)
    async with client_factory() as client:
        payload = await _request_json(client, url, headers, budget, directory=True)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("models"), list):
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.INVALID_RESPONSE,
            "Ollama /api/tags 响应缺少 models[]。",
            retryable=False,
        )
    models: list[DiscoveredModel] = []
    for raw in payload["models"]:
        if not isinstance(raw, Mapping):
            continue
        model_id = str(raw.get("name") or raw.get("model") or "").strip()
        try:
            model_id = clean_model_id(model_id)
        except ValueError:
            continue
        from .types import (
            Classification,
            ModelSource,
            RuntimeCompatibility,
        )

        if service in {"llm", "embedding"}:
            compatibility, reason = RuntimeCompatibility.SUPPORTED, None
        elif service == "vision":
            compatibility, reason = RuntimeCompatibility.UNKNOWN, "ollama_capability_not_exposed"
        else:
            compatibility, reason = RuntimeCompatibility.UNSUPPORTED, "ollama_adapter_not_available"
        models.append(
            DiscoveredModel(
                id=model_id,
                name=clean_model_name(raw.get("name"), model_id),
                services=(),
                classification=Classification.UNKNOWN,
                runtime_compatibility=compatibility,
                reason_code=reason,
                source=ModelSource.REMOTE,
            )
        )
    if len(models) > MAX_MODELS:
        return FetchOutcome(
            models=_dedupe(models),
            complete=False,
            error=DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE, "目录超过模型数量上限。", retryable=False
            ),
        )
    return FetchOutcome(models=_dedupe(models), complete=True)


async def fetch_openai_compatible(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = _directory_url(connection)
    headers = _auth_headers(connection)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    async with client_factory() as client:
        try:
            payload = await _request_json(client, url, headers, budget, directory=True)
        except DiscoveryUpstreamError as exc:
            fallback = (
                None
                if connection.model_directory_url
                else _compatible_fallback_url(url)
            )
            if exc.status_code not in {404, 405} or fallback is None:
                raise
            # Exactly one same-origin protocol fallback, sharing the budget.
            payload = await _request_json(
                client, fallback, headers, budget, directory=True
            )
            source_url = _source_url(fallback)
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        raw_models = payload["data"]
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.INVALID_RESPONSE,
            "兼容目录响应缺少 data[] 或裸列表。",
            retryable=False,
        )
    models: list[DiscoveredModel] = []
    for raw in raw_models:
        if not isinstance(raw, Mapping):
            continue
        model = generic_model(
            raw,
            service,
            binding=connection.binding,
            adapter="openai_compatible",
            provider_declared=False,
            base_url=connection.base_url,
            source_url=source_url,
            checked_at=checked_at,
        )
        if model is None:
            continue
        if model.services and service not in model.services:
            continue
        models.append(model)
    if len(models) > MAX_MODELS:
        return FetchOutcome(
            models=_dedupe(models)[:MAX_MODELS],
            complete=False,
            error=DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "目录超过 10,000 个模型上限。",
                retryable=False,
            ),
        )
    if isinstance(payload, Mapping) and (
        payload.get("has_more") is True or payload.get("next_cursor") or payload.get("next_page")
    ):
        # Arbitrary compatible endpoints do not share a cursor protocol.
        # Report partial metadata instead of guessing requests or caching it.
        return FetchOutcome(
            models=_dedupe(models),
            complete=False,
            error=DiscoveryUpstreamError(
                DiscoveryErrorCode.INCOMPLETE,
                "供应商目录仍有后续分页，当前兼容接口无法完整获取。",
                retryable=False,
            ),
        )
    return FetchOutcome(models=_dedupe(models), complete=True)


async def fetch_anthropic(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = connection.model_directory_url or append_url_path(
        connection.base_url, "models"
    )
    headers = _anthropic_headers(connection)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    models: list[DiscoveredModel] = []
    seen: set[str] = set()
    cursor: str | None = None
    async with client_factory() as client:
        for _page in range(MAX_PAGES):
            page_url = with_query_params(url, {"limit": 100, "after_id": cursor})
            payload = await _request_json(
                client, page_url, headers, budget, directory=True
            )
            if not isinstance(payload, Mapping) or not isinstance(
                payload.get("data"), list
            ):
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INVALID_RESPONSE,
                    "Anthropic 目录响应缺少 data[]。",
                    retryable=False,
                )
            for raw in payload["data"]:
                if not isinstance(raw, Mapping):
                    continue
                model = anthropic_model(
                    raw,
                    service,
                    source_url=source_url,
                    checked_at=checked_at,
                )
                if model is not None and model.id not in seen:
                    seen.add(model.id)
                    models.append(model)
            has_more = payload.get("has_more") is True
            last_id = str(payload.get("last_id") or "").strip() or None
            if not has_more:
                return FetchOutcome(models=_dedupe(models), complete=True)
            if not last_id or last_id == cursor:
                return FetchOutcome(
                    models=_dedupe(models),
                    complete=False,
                    error=DiscoveryUpstreamError(
                        DiscoveryErrorCode.INCOMPLETE,
                        "Anthropic 目录游标没有前进，未缓存不完整目录。",
                        retryable=False,
                    ),
                )
            cursor = last_id
    return FetchOutcome(
        models=_dedupe(models),
        complete=False,
        error=DiscoveryUpstreamError(
            DiscoveryErrorCode.INCOMPLETE,
            "Anthropic 目录超过 100 页上限。",
            retryable=False,
        ),
    )


async def fetch_gemini(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = _gemini_models_url(connection)
    headers = _gemini_headers(connection)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    models: list[DiscoveredModel] = []
    seen: set[str] = set()
    token: str | None = None
    async with client_factory() as client:
        for _page in range(MAX_PAGES):
            page_url = with_query_params(
                url, {"pageSize": 100, "pageToken": token}
            )
            payload = await _request_json(
                client, page_url, headers, budget, directory=True
            )
            if not isinstance(payload, Mapping) or not isinstance(
                payload.get("models"), list
            ):
                raise DiscoveryUpstreamError(
                    DiscoveryErrorCode.INVALID_RESPONSE,
                    "Gemini 目录响应缺少 models[]。",
                    retryable=False,
                )
            for raw in payload["models"]:
                if not isinstance(raw, Mapping):
                    continue
                model = gemini_model(
                    raw,
                    service,
                    source_url=source_url,
                    checked_at=checked_at,
                )
                if model is not None and model.id not in seen:
                    seen.add(model.id)
                    models.append(model)
            token = str(payload.get("nextPageToken") or "").strip() or None
            if not token:
                return FetchOutcome(models=_dedupe(models), complete=True)
    return FetchOutcome(
        models=_dedupe(models),
        complete=False,
        error=DiscoveryUpstreamError(
            DiscoveryErrorCode.INCOMPLETE,
            "Gemini 目录超过 100 页上限。",
            retryable=False,
        ),
    )


async def fetch_azure(
    connection: Connection,
    service: str,
    *,
    client_factory: ClientFactory,
    budget: _Budget | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    url = _azure_models_url(connection)
    headers = _azure_headers(connection)
    source_url = _source_url(url)
    checked_at = _checked_at(now)
    async with client_factory() as client:
        payload = await _request_json(client, url, headers, budget, directory=True)
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        raw_models = payload["data"]
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.INVALID_RESPONSE,
            "Azure 模型目录响应缺少 data[]。",
            retryable=False,
        )
    models: list[DiscoveredModel] = []
    for raw in raw_models:
        if not isinstance(raw, Mapping):
            continue
        model = azure_model(
            raw,
            service,
            source_url=source_url,
            checked_at=checked_at,
        )
        if model is not None and (not model.services or service in model.services):
            models.append(model)
    return FetchOutcome(models=_dedupe(models), complete=True)


async def _fetch_catalog(
    connection: Connection,
    service: str,
    adapter: str,
    *,
    client_factory: ClientFactory | None = None,
    now: Callable[[], datetime] | None = None,
) -> FetchOutcome:
    factory = client_factory or (
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0),
            follow_redirects=False,
        )
    )
    budget = _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
    if adapter == "aliyun":
        return await fetch_aliyun(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "siliconflow":
        return await fetch_siliconflow(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "ollama":
        return await fetch_ollama(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "openai_compatible":
        return await fetch_openai_compatible(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "anthropic":
        return await fetch_anthropic(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "gemini":
        return await fetch_gemini(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    if adapter == "azure":
        return await fetch_azure(
            connection, service, client_factory=factory, budget=budget, now=now
        )
    raise DiscoveryUpstreamError(
        DiscoveryErrorCode.UNSUPPORTED,
        "该供应商尚未适配在线模型目录，请继续手工填写模型。",
        retryable=False,
    )


async def fetch_catalog(connection, service, adapter, *, client_factory=None, now=None):
    """Bound queueing, transport and pagination by one cancellable deadline."""
    try:
        async with asyncio.timeout(REFRESH_DEADLINE_SECONDS):
            async with _remote_gate():
                return await _fetch_catalog(
                    connection, service, adapter, client_factory=client_factory, now=now
                )
    except TimeoutError as exc:
        raise DiscoveryUpstreamError(
            DiscoveryErrorCode.TIMEOUT, "目录查询超过总时限，请稍后重试。", retryable=True
        ) from exc


__all__ = [
    "ClientFactory",
    "FetchOutcome",
    "fetch_aliyun",
    "fetch_anthropic",
    "fetch_azure",
    "fetch_catalog",
    "fetch_gemini",
    "fetch_ollama",
    "fetch_openai_compatible",
    "fetch_siliconflow",
]
