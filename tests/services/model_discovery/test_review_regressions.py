"""Independent acceptance cases not covered by the worker's happy paths."""

import asyncio
from dataclasses import replace
import json
import logging
from pathlib import Path

import httpx
import pytest

from deeptutor.services.model_discovery import adapters
from deeptutor.services.model_discovery.compatibility import (
    aliyun_runtime_compatibility,
    generic_model,
    generic_services_for_model,
)
from deeptutor.services.model_discovery.service import ModelDiscoveryService
from deeptutor.services.model_discovery.types import (
    Connection,
    DiscoveryErrorCode,
    DiscoveryStatus,
    DiscoveryUpstreamError,
    RuntimeCompatibility,
)


@pytest.mark.asyncio
async def test_masked_json_string_headers_restore_and_do_not_cross_origins(tmp_path):
    def handler(request):
        assert request.headers["X-Custom"] == "fake-custom-credential"
        return payload()

    svc = service(tmp_path, handler)
    svc.catalog_path.write_text(
        json.dumps(
            {
                "services": {
                    "llm": {
                        "profiles": [
                            {
                                "id": "p",
                                "binding": "custom",
                                "base_url": "https://models.invalid/v1",
                                "extra_headers": '{"X-Custom":"fake-custom-credential"}',
                            }
                        ]
                    }
                }
            }
        )
    )
    result = await svc.discover(service="llm", profile_id="p", connection={"extra_headers": "***"})
    assert result.status == DiscoveryStatus.OK
    from deeptutor.services.model_discovery.types import DiscoveryRequestError

    for headers in (None, "***"):
        with pytest.raises(DiscoveryRequestError) as caught:
            await svc.discover(
                service="llm",
                profile_id="p",
                connection={
                    "base_url": "https://other.invalid/v1",
                    "extra_headers": headers,
                },
            )
        assert caught.value.status_code == 409


def connection(**changes):
    return replace(Connection(binding="custom", base_url="https://models.invalid/v1"), **changes)


def factory(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def service(tmp_path, handler):
    catalog = tmp_path / "catalog.json"
    catalog.write_text('{"services": {}}')
    return ModelDiscoveryService(
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        owner="review",
        client_factory=factory(handler),
    )


def payload():
    return httpx.Response(200, json={"data": [{"id": "example-model"}]})


@pytest.mark.asyncio
async def test_total_deadline_cancels_slow_directory(monkeypatch):
    monkeypatch.setattr(adapters, "REFRESH_DEADLINE_SECONDS", 0.02)

    async def handler(request):
        await asyncio.sleep(0.1)
        return payload()

    with pytest.raises(DiscoveryUpstreamError) as caught:
        await adapters.fetch_catalog(
            connection(), "llm", "openai_compatible", client_factory=factory(handler)
        )
    assert caught.value.code == DiscoveryErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_distinct_directory_requests_obey_global_concurrency_limit():
    running = peak = 0

    async def handler(request):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return payload()

    await asyncio.gather(
        *[
            adapters.fetch_catalog(
                connection(api_key=str(i)),
                "llm",
                "openai_compatible",
                client_factory=factory(handler),
            )
            for i in range(9)
        ]
    )
    assert 1 <= peak <= 4


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_drop_shared_fetch(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return payload()

    svc = service(tmp_path, handler)
    args = dict(
        service="llm",
        mode="refresh",
        connection={"binding": "custom", "base_url": "https://models.invalid/v1"},
    )
    first = asyncio.create_task(svc.discover(**args))
    await started.wait()
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    second = asyncio.create_task(svc.discover(**args))
    await asyncio.sleep(0.02)
    release.set()
    await second
    assert calls == 1


@pytest.mark.asyncio
async def test_non_directory_cache_root_returns_usable_result_with_io_warning(tmp_path):
    svc = service(tmp_path, lambda r: payload())
    svc.cache.root.write_text("a regular file cannot be a directory")
    result = await svc.discover(
        service="llm", connection={"binding": "custom", "base_url": "https://models.invalid/v1"}
    )
    assert result.status == DiscoveryStatus.OK
    assert result.models[0].id == "example-model"
    assert result.error.code == DiscoveryErrorCode.CACHE_IO


@pytest.mark.asyncio
async def test_non_utf8_cache_is_discarded(tmp_path):
    svc = service(tmp_path, lambda r: payload())
    c = connection()
    fingerprint = c.fingerprint(owner="review", service="llm", profile_id=None)
    svc.cache.root.mkdir()
    (svc.cache.root / (fingerprint + ".json")).write_bytes(b"\xff\xfe")
    result = await svc.discover(
        service="llm", connection={"binding": "custom", "base_url": c.base_url}
    )
    assert result.status == DiscoveryStatus.OK


@pytest.mark.asyncio
async def test_failed_refresh_marks_even_unexpired_directory_stale(tmp_path):
    fail = False

    def handler(request):
        return httpx.Response(503) if fail else payload()

    svc = service(tmp_path, handler)
    args = dict(
        service="llm", connection={"binding": "custom", "base_url": "https://models.invalid/v1"}
    )
    first = await svc.discover(**args)
    fail = True
    failed = await svc.discover(**args, mode="refresh")
    automatic = await svc.discover(**args)
    for result in (failed, automatic):
        assert result.status == DiscoveryStatus.ERROR
        assert result.cache.state.value == "stale"
        assert result.cache.fetched_at == first.cache.fetched_at
        assert result.models == first.models


@pytest.mark.asyncio
async def test_ollama_truncation_is_incomplete(monkeypatch):
    monkeypatch.setattr(adapters, "MAX_MODELS", 3)

    def handler(request):
        return httpx.Response(200, json={"models": [{"name": f"m{i}"} for i in range(4)]})

    result = await adapters.fetch_catalog(
        connection(binding="ollama"), "llm", "ollama", client_factory=factory(handler)
    )
    assert len(result.models) <= 3
    assert not result.complete
    assert result.error.code == DiscoveryErrorCode.INCOMPLETE


@pytest.mark.asyncio
async def test_compatible_response_declaring_more_pages_is_not_cached_as_complete():
    result = await adapters.fetch_catalog(
        connection(),
        "llm",
        "openai_compatible",
        client_factory=factory(
            lambda r: httpx.Response(
                200, json={"data": [{"id": "first-page-only"}], "has_more": True}
            )
        ),
    )
    assert not result.complete
    assert result.error.code == DiscoveryErrorCode.INCOMPLETE


@pytest.mark.asyncio
async def test_ollama_v1_with_query_keeps_proxy_prefix():
    def handler(request):
        assert request.url.path == "/proxy/api/tags"
        assert request.url.params["token"] == "fake-query-secret"
        return httpx.Response(200, json={"models": []})

    await adapters.fetch_catalog(
        connection(
            binding="ollama", base_url="http://localhost:11434/proxy/v1?token=fake-query-secret"
        ),
        "llm",
        "ollama",
        client_factory=factory(handler),
    )


@pytest.mark.asyncio
async def test_overlapping_aliyun_pages_do_not_count_duplicates_as_total():
    def handler(request):
        page = int(request.url.params["page_no"])
        ids = {1: ["a", "b"], 2: ["b", "c"]}.get(page, [])
        return httpx.Response(
            200,
            json={
                "output": {
                    "total": 4,
                    "models": [{"model": i, "capabilities": ["TG"]} for i in ids],
                }
            },
        )

    result = await adapters.fetch_catalog(
        connection(binding="aliyun", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "llm",
        "aliyun",
        client_factory=factory(handler),
    )
    assert not result.complete
    assert result.error.code == DiscoveryErrorCode.INCOMPLETE


@pytest.mark.parametrize(
    "service,model",
    [("stt", "qwen3-asr-flash"), ("vision", "qwen3-vl-plus"), ("embedding", "text-embedding-v3")],
)
def test_third_party_routing_is_not_supported_in_non_llm_categories(service, model):
    status, reason = aliyun_runtime_compatibility(service, model, inference_provider="siliconflow")
    assert status != RuntimeCompatibility.SUPPORTED
    assert reason == "third_party_inference_routing"


@pytest.mark.parametrize("model", ["gpt-4o-audio-preview", "o3-mini", "o1-mini", "o1-preview"])
def test_text_or_audio_models_are_not_presented_as_vision_or_speech_api_models(model):
    assert generic_services_for_model(model, "openai") == ("llm",)


def test_openai_realtime_model_is_not_advertised_as_chat_compatible():
    model = generic_model(
        {"id": "gpt-4o-realtime-preview"},
        "llm",
        binding="openai",
        adapter="openai_compatible",
        provider_declared=False,
    )
    assert model.runtime_compatibility == RuntimeCompatibility.UNSUPPORTED


@pytest.mark.parametrize("model", ["qwen3-asr-flash-filetrans", "qwen3-asr-realtime"])
def test_unsupported_aliyun_protocol_cannot_be_enabled_via_routing_confirmation(model):
    status, _ = aliyun_runtime_compatibility("stt", model, inference_provider="siliconflow")
    assert status == RuntimeCompatibility.UNSUPPORTED


@pytest.mark.asyncio
async def test_http_client_logs_do_not_contain_query_credentials(caplog):
    with caplog.at_level(logging.INFO, logger="httpx"):
        await adapters.fetch_catalog(
            connection(base_url="https://models.invalid/v1?token=fake-query-secret"),
            "llm",
            "openai_compatible",
            client_factory=factory(lambda r: payload()),
        )
    assert "fake-query-secret" not in caplog.text
