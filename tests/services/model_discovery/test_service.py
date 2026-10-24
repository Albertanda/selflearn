from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from deeptutor.services.model_discovery.cache import CacheIOError
from deeptutor.services.model_discovery.service import ModelDiscoveryService
from deeptutor.services.model_discovery.types import (
    DiscoveryRequestError,
    DiscoveryStatus,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


def response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def make_catalog() -> dict[str, Any]:
    def profile(profile_id: str, binding: str, base_url: str, key: str, service: str):
        model = {
            "id": f"{service}-model-{profile_id}",
            "name": f"{profile_id} model",
            "model": f"{service}/existing-{profile_id}",
        }
        return {
            "id": profile_id,
            "name": profile_id,
            "binding": binding,
            "base_url": base_url,
            "api_key": key,
            "api_version": "",
            "extra_headers": {},
            "models": [model],
        }

    profiles = {
        "llm": [
            profile("p-llm", "openai", "https://api.openai.com/v1", "sk.llm.with.dots", "llm"),
            profile("p-llm-b", "openai", "https://api.openai.com/v1", "sk.other", "llm"),
            profile("p-codex", "openai_codex", "https://chatgpt.com/backend-api/codex", "", "llm"),
        ],
        "embedding": [
            profile(
                "p-emb",
                "siliconflow",
                "https://api.siliconflow.cn/v1",
                "sk.sf.with.dots",
                "embedding",
            ),
        ],
        "stt": [
            profile(
                "p-stt",
                "aliyun",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                "sk.stt.with.dots",
                "stt",
            ),
            {
                **profile(
                    "p-llm",
                    "aliyun",
                    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    "sk.same-id-stt",
                    "stt",
                ),
                "extra_headers": {"X-Api-Secret": "header-secret.value"},
            },
        ],
        "tts": [],
        "imagegen": [],
        "videogen": [],
        "vision": [
            profile("p-vis", "openai", "https://api.openai.com/v1", "sk.vision", "vision"),
        ],
    }
    services: dict[str, Any] = {}
    for service, items in profiles.items():
        services[service] = {
            "active_profile_id": items[0]["id"] if items else None,
            "active_model_id": items[0]["models"][0]["id"] if items else None,
            "profiles": items,
        }
    services["search"] = {"active_profile_id": None, "profiles": []}
    return {"version": 1, "services": services}


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings" / "model_catalog.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(make_catalog()), encoding="utf-8")
    return path


def service(
    catalog_path: Path,
    tmp_path: Path,
    handler,
    clock: Clock | None = None,
) -> ModelDiscoveryService:
    return ModelDiscoveryService(
        catalog_path=catalog_path,
        cache_root=tmp_path / "runtime" / "cache" / "model-discovery",
        owner="admin-1",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0)
        ),
        now=clock or Clock(),
    )


@pytest.mark.asyncio
async def test_saved_profile_uses_exact_dotted_key_and_catalog_is_unchanged(
    catalog_path: Path, tmp_path: Path
):
    before = catalog_path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk.stt.with.dots"
        return response(
            {
                "output": {
                    "total": 1,
                    "page_no": 1,
                    "page_size": 100,
                    "models": [
                        {"model": "qwen3-asr-flash", "capabilities": ["ASR"]}
                    ],
                }
            }
        )

    svc = service(catalog_path, tmp_path, handler)
    result = await svc.discover(service="stt", profile_id="p-stt", mode="refresh")
    assert result.status is DiscoveryStatus.OK
    assert result.models[0].id == "qwen3-asr-flash"
    assert catalog_path.read_bytes() == before
    files = list((tmp_path / "runtime" / "cache" / "model-discovery").glob("*.json"))
    assert files
    raw = files[0].read_text(encoding="utf-8")
    assert "sk.stt.with.dots" not in raw
    assert "dashscope" not in raw
    assert "api_key" not in raw


@pytest.mark.asyncio
async def test_profile_id_is_scoped_to_the_requested_service(catalog_path: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no network for a non-existent profile")

    svc = service(catalog_path, tmp_path, handler)
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(service="stt", profile_id="p-emb")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mask_without_saved_profile_is_400_and_saved_mask_restores(
    catalog_path: Path, tmp_path: Path
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk.llm.with.dots"
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(
            service="llm",
            connection={"binding": "openai", "base_url": "https://api.openai.com/v1", "api_key": "***"},
        )
    assert exc.value.status_code == 400
    result = await svc.discover(
        service="llm",
        profile_id="p-llm",
        mode="refresh",
        connection={"api_key": "***", "extra_headers": {}},
    )
    assert result.status is DiscoveryStatus.OK


@pytest.mark.asyncio
async def test_origin_or_binding_change_using_saved_credentials_is_409(
    catalog_path: Path, tmp_path: Path
):
    def handler(request: httpx.Request) -> httpx.Response:
        expected = (
            "Bearer sk.llm.with.dots"
            if request.url.path.startswith("/other/")
            else "Bearer sk.brand.new"
        )
        assert request.headers["authorization"] == expected
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(
            service="llm",
            profile_id="p-llm",
            connection={"base_url": "https://proxy.example.test/v1", "api_key": "***"},
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "CREDENTIAL_REENTRY_REQUIRED"
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(
            service="llm",
            profile_id="p-llm",
            connection={"binding": "siliconflow", "api_key": "***"},
        )
    assert exc.value.status_code == 409
    # Binding AND path change together must still count as an identity change.
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(
            service="llm",
            profile_id="p-llm",
            connection={
                "binding": "siliconflow",
                "base_url": "https://proxy.example.test/v1",
                "api_key": "***",
            },
        )
    assert exc.value.status_code == 409
    # Same origin with a changed path is allowed: the credential stays on the
    # same scheme/host/port.
    same_origin = await svc.discover(
        service="llm",
        profile_id="p-llm",
        mode="refresh",
        connection={"base_url": "https://api.openai.com/other/v1", "api_key": "***"},
    )
    assert same_origin.status is DiscoveryStatus.OK
    # An explicitly re-entered key is allowed at a new origin.
    new_key = await svc.discover(
        service="llm",
        profile_id="p-llm",
        mode="refresh",
        connection={"base_url": "https://proxy.example.test/v1", "api_key": "sk.brand.new"},
    )
    assert new_key.status is DiscoveryStatus.OK


@pytest.mark.asyncio
async def test_unsupported_and_managed_profiles_are_explicit(catalog_path: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported providers must not be contacted")

    svc = service(catalog_path, tmp_path, handler)
    unsupported = await svc.discover(
        service="llm",
        connection={"binding": "not_a_registered_provider", "base_url": "https://example.test/v1", "api_key": "sk.x"},
    )
    assert unsupported.status is DiscoveryStatus.UNSUPPORTED
    assert unsupported.error is not None
    assert unsupported.error.code.value == "UNSUPPORTED"
    with pytest.raises(DiscoveryRequestError):
        await svc.discover(service="llm", profile_id="p-codex")
    with pytest.raises(DiscoveryRequestError):
        await svc.discover(
            service="llm",
            connection={
                "binding": "codebuddy",
                "base_url": "https://codebuddy.example.test/v1",
                "api_key": "sk.x",
            },
        )


@pytest.mark.asyncio
async def test_cache_first_uses_cache_and_refresh_calls_upstream(catalog_path: Path, tmp_path: Path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)
    first = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert first.cache.state.value == "fresh"
    second = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert second.cache.state.value == "fresh"
    assert len(calls) == 1
    third = await svc.discover(service="llm", profile_id="p-llm", mode="refresh")
    assert third.cache.state.value == "fresh"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cache_is_isolated_by_key_header_service_profile_and_owner(
    catalog_path: Path, tmp_path: Path
):
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            (request.url.path, request.headers.get("authorization", ""))
        )
        if request.url.path == "/api/v1/models":
            return response(
                {
                    "output": {
                        "total": 1,
                        "page_no": 1,
                        "page_size": 100,
                        "models": [{"model": "qwen3-asr-flash", "capabilities": ["ASR"]}],
                    }
                }
            )
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)
    await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    await svc.discover(service="llm", profile_id="p-llm-b", mode="cache_first")
    await svc.discover(
        service="stt",
        profile_id="p-stt",
        mode="cache_first",
    )
    assert len(calls) == 3
    assert len({item[1] for item in calls}) == 3

    other_owner = ModelDiscoveryService(
        catalog_path=catalog_path,
        cache_root=tmp_path / "runtime" / "cache" / "model-discovery",
        owner="admin-2",
        client_factory=svc.client_factory,
        now=svc.now,
    )
    await other_owner.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_concurrent_same_connection_is_single_flight(catalog_path: Path, tmp_path: Path):
    calls = 0
    lock = asyncio.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        async with lock:
            calls += 1
        await asyncio.sleep(0.05)
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)
    results = await asyncio.gather(
        svc.discover(service="llm", profile_id="p-llm", mode="refresh"),
        svc.discover(service="llm", profile_id="p-llm", mode="refresh"),
    )
    assert calls == 1
    assert [result.status for result in results] == [DiscoveryStatus.OK, DiscoveryStatus.OK]


@pytest.mark.asyncio
async def test_failure_keeps_stale_directory_and_failure_time_does_not_become_fetched_at(
    catalog_path: Path, tmp_path: Path
):
    clock = Clock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response({"data": [{"id": "gpt-4.1"}]})
        return httpx.Response(500, content=b"upstream secret sk-leak")

    svc = service(catalog_path, tmp_path, handler, clock=clock)
    first = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    fetched_at = first.cache.fetched_at
    clock.advance(hours=2)
    failed = await svc.discover(service="llm", profile_id="p-llm", mode="refresh")
    assert failed.status is DiscoveryStatus.ERROR
    assert [model.id for model in failed.models] == ["gpt-4.1"]
    assert failed.cache.state.value == "stale"
    assert failed.cache.fetched_at == fetched_at
    assert failed.error is not None
    assert "sk-leak" not in failed.error.message


@pytest.mark.asyncio
async def test_failure_cooldown_blocks_cache_first_but_refresh_retries(
    catalog_path: Path, tmp_path: Path
):
    clock = Clock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, content=b"unavailable")

    svc = service(catalog_path, tmp_path, handler, clock=clock)
    first = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert first.status is DiscoveryStatus.ERROR
    second = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert second.status is DiscoveryStatus.ERROR
    assert calls == 1
    third = await svc.discover(service="llm", profile_id="p-llm", mode="refresh")
    assert third.status is DiscoveryStatus.ERROR
    assert calls == 2


@pytest.mark.asyncio
async def test_empty_directory_has_five_minute_ttl(catalog_path: Path, tmp_path: Path):
    clock = Clock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"data": []})

    svc = service(catalog_path, tmp_path, handler, clock=clock)
    first = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert first.status is DiscoveryStatus.EMPTY
    assert first.complete is True
    second = await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert second.status is DiscoveryStatus.EMPTY
    assert calls == 1
    clock.advance(minutes=5, seconds=1)
    await svc.discover(service="llm", profile_id="p-llm", mode="cache_first")
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_hide_success(catalog_path: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return response({"data": [{"id": "gpt-4.1"}]})

    svc = service(catalog_path, tmp_path, handler)

    def boom(**kwargs):
        raise CacheIOError("disk")

    svc.cache.save_success = boom  # type: ignore[method-assign]
    result = await svc.discover(service="llm", profile_id="p-llm", mode="refresh")
    assert result.status is DiscoveryStatus.OK
    assert [model.id for model in result.models] == ["gpt-4.1"]
    assert result.cache.state.value == "none"
    assert result.error is not None
    assert result.error.code.value == "CACHE_IO"


@pytest.mark.asyncio
async def test_aliyun_failure_offers_traceable_stt_preset(catalog_path: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"unavailable")

    svc = service(catalog_path, tmp_path, handler)
    result = await svc.discover(service="stt", profile_id="p-stt", mode="refresh")
    assert result.status is DiscoveryStatus.ERROR
    assert [model.id for model in result.models] == ["qwen3-asr-flash"]
    assert result.models[0].source.value == "preset"


@pytest.mark.asyncio
async def test_search_is_rejected_before_network(catalog_path: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    svc = service(catalog_path, tmp_path, handler)
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(service="search")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_saved_secret_header_mask_restores_only_for_same_profile(
    catalog_path: Path, tmp_path: Path
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-secret"] == "header-secret.value"
        return response(
            {
                "output": {
                    "total": 1,
                    "page_no": 1,
                    "page_size": 100,
                    "models": [{"model": "qwen3-asr-flash", "capabilities": ["ASR"]}],
                }
            }
        )

    svc = service(catalog_path, tmp_path, handler)
    result = await svc.discover(
        service="stt",
        profile_id="p-llm",
        mode="refresh",
        connection={"extra_headers": {"X-Api-Secret": "***"}},
    )
    assert result.status is DiscoveryStatus.OK
    with pytest.raises(DiscoveryRequestError):
        await svc.discover(
            service="stt",
            profile_id="p-stt",
            connection={"extra_headers": {"X-Api-Secret": "***"}},
        )
