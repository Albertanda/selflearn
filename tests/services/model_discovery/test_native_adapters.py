from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from deeptutor.services.model_discovery.adapters import fetch_catalog
from deeptutor.services.model_discovery.types import (
    Connection,
    DiscoveryErrorCode,
    DiscoveryUpstreamError,
)


def factory(handler):
    def make() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0)
        )

    return make


def json_response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_anthropic_native_pagination_display_name_version_and_metadata():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        query = parse_qs(urlsplit(str(request.url)).query)
        if "after_id" not in query:
            return json_response(
                {
                    "data": [
                        {
                            "id": "claude-sonnet-4-6",
                            "display_name": "Claude Sonnet 4.6",
                            "max_input_tokens": 200000,
                            "max_tokens": 8192,
                            "capabilities": {"image_input": {"supported": True}},
                        }
                    ],
                    "has_more": True,
                    "last_id": "claude-sonnet-4-6",
                }
            )
        return json_response(
            {
                "data": [{"id": "claude-haiku-4-5"}],
                "has_more": False,
                "last_id": "claude-haiku-4-5",
            }
        )

    outcome = await fetch_catalog(
        Connection.from_mapping(
            {
                "binding": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "sk-ant-fictitious",
            }
        ),
        "llm",
        "anthropic",
        client_factory=factory(handler),
    )
    assert [model.id for model in outcome.models] == [
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ]
    first = outcome.models[0]
    assert first.name == "Claude Sonnet 4.6"
    assert first.parameters.values["max_output_tokens"] == 8192
    assert first.parameters.values["max_input_tokens"] == 200000
    assert "context_window" not in first.parameters.values
    assert requests[0].headers["x-api-key"] == "sk-ant-fictitious"
    assert requests[0].headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in requests[0].headers
    assert parse_qs(urlsplit(str(requests[0].url)).query)["limit"] == ["100"]


@pytest.mark.asyncio
async def test_anthropic_cursor_stall_and_old_versions_without_metadata():
    def stall_handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "data": [{"id": "claude-x", "display_name": "Claude X"}],
                "has_more": True,
                "last_id": "same-cursor",
            }
        )

    outcome = await fetch_catalog(
        Connection.from_mapping(
            {
                "binding": "custom_anthropic",
                "base_url": "https://anthropic-proxy.example/v1",
                "api_key": "sk-fictitious",
            }
        ),
        "llm",
        "anthropic",
        client_factory=factory(stall_handler),
    )
    assert outcome.complete is False
    assert outcome.error is not None
    assert outcome.error.code is DiscoveryErrorCode.INCOMPLETE
    assert [model.id for model in outcome.models] == ["claude-x"]

    def old_handler(request: httpx.Request) -> httpx.Response:
        return json_response({"data": [{"id": "claude-old"}], "has_more": False})

    old = await fetch_catalog(
        Connection.from_mapping(
            {
                "binding": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "sk-ant-fictitious",
            }
        ),
        "llm",
        "anthropic",
        client_factory=factory(old_handler),
    )
    assert old.complete is True
    assert old.models[0].parameters is None


@pytest.mark.asyncio
async def test_anthropic_custom_endpoint_404_is_not_rewritten_to_official_host():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    with pytest.raises(DiscoveryUpstreamError):
        await fetch_catalog(
            Connection.from_mapping(
                {
                    "binding": "minimax_anthropic",
                    "base_url": "https://api.minimax.io/anthropic",
                    "api_key": "sk-fictitious",
                }
            ),
            "llm",
            "anthropic",
            client_factory=factory(handler),
        )
    assert calls == ["https://api.minimax.io/anthropic/models?limit=100"]


@pytest.mark.asyncio
async def test_gemini_native_pagination_resource_name_and_token_semantics():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        query = parse_qs(urlsplit(str(request.url)).query)
        if "pageToken" not in query:
            return json_response(
                {
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "displayName": "Gemini 2.5 Flash",
                            "inputTokenLimit": 1048576,
                            "outputTokenLimit": 65536,
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/embedding-001",
                            "displayName": "Embedding 001",
                            "inputTokenLimit": 2048,
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ],
                    "nextPageToken": "page-2",
                }
            )
        return json_response(
            {
                "models": [
                    {
                        "name": "models/gemini-embedding-2",
                        "supportedGenerationMethods": ["embedContent"],
                    }
                ]
            }
        )

    connection = Connection.from_mapping(
        {
            "binding": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": "gemini.fictitious",
        }
    )
    llm = await fetch_catalog(
        connection, "llm", "gemini", client_factory=factory(handler)
    )
    assert [model.id for model in llm.models] == ["gemini-2.5-flash"]
    model = llm.models[0]
    assert model.resource_name == "models/gemini-2.5-flash"
    assert model.parameters.values["max_input_tokens"] == 1048576
    assert "context_window" not in model.parameters.values
    assert model.parameters.values["max_output_tokens"] == 65536
    assert model.runtime_compatibility == "unknown"
    assert model.reason_code == "gemini_generate_content_category_unverified"
    first_url = urlsplit(str(requests[0].url))
    assert first_url.path == "/v1beta/models"
    assert parse_qs(first_url.query)["pageSize"] == ["100"]
    assert requests[0].headers["x-goog-api-key"] == "gemini.fictitious"
    assert len(requests) == 2
    assert parse_qs(urlsplit(str(requests[1].url)).query)["pageToken"] == ["page-2"]

    requests.clear()
    embedding = await fetch_catalog(
        connection, "embedding", "gemini", client_factory=factory(handler)
    )
    assert [model.id for model in embedding.models] == [
        "embedding-001",
        "gemini-embedding-2",
    ]


@pytest.mark.asyncio
async def test_gemini_custom_proxy_stays_on_proxy_and_uses_explicit_directory():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return json_response(
            {
                "models": [
                    {
                        "name": "models/proxy-gemini",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            }
        )

    proxy = Connection.from_mapping(
        {
            "binding": "gemini",
            "base_url": "https://gemini-proxy.example/v1beta/openai/",
            "api_key": "proxy.fictitious",
        }
    )
    # Without an explicit directory, the custom proxy has no invented native route.
    with pytest.raises(DiscoveryUpstreamError):
        await fetch_catalog(
            proxy,
            "llm",
            "openai_compatible",
            client_factory=factory(lambda request: httpx.Response(404)),
        )

    explicit = Connection.from_mapping(
        {
            "binding": "gemini",
            "base_url": "https://gemini-proxy.example/v1beta/openai/",
            "api_key": "proxy.fictitious",
            "model_directory_url": "https://gemini-proxy.example/custom/models?ver=9",
        }
    )
    outcome = await fetch_catalog(
        explicit, "llm", "gemini", client_factory=factory(handler)
    )
    assert [model.id for model in outcome.models] == ["proxy-gemini"]
    assert str(calls[0].url).startswith("https://gemini-proxy.example/custom/models")
    assert "googleapis.com" not in str(calls[0].url)
    assert calls[0].headers["x-goog-api-key"] == "proxy.fictitious"


@pytest.mark.asyncio
async def test_azure_v1_offering_requires_deployment_mapping_and_keeps_version():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response({"data": [{"id": "gpt-4.1"}, {"id": "text-embedding-3-large"}]})

    outcome = await fetch_catalog(
        Connection.from_mapping(
            {
                "binding": "azure_openai",
                "base_url": "https://resource.openai.azure.com/openai/v1",
                "api_key": "azure.fictitious",
                "api_version": "2025-04-01-preview",
            }
        ),
        "llm",
        "azure",
        client_factory=factory(handler),
    )
    assert [model.id for model in outcome.models] == ["gpt-4.1"]
    model = outcome.models[0]
    assert model.deployment_mapping_required is True
    assert model.runtime_compatibility == "unknown"
    assert model.reason_code == "azure_deployment_mapping_required"
    parsed = urlsplit(str(requests[0].url))
    assert parsed.path == "/openai/v1/models"
    assert parse_qs(parsed.query)["api-version"] == ["2025-04-01-preview"]
    assert requests[0].headers["api-key"] == "azure.fictitious"
    assert "authorization" not in requests[0].headers


@pytest.mark.asyncio
async def test_azure_resource_root_and_legacy_deployment_url_fail_before_request():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return json_response({"data": []})

    for base_url in (
        "https://resource.openai.azure.com",
        "https://resource.openai.azure.com/openai/deployments/my-deploy",
    ):
        with pytest.raises(DiscoveryUpstreamError) as exc:
            await fetch_catalog(
                Connection.from_mapping(
                    {
                        "binding": "azure_openai",
                        "base_url": base_url,
                        "api_key": "azure.fictitious",
                        "api_version": "2024-02-01",
                    }
                ),
                "llm",
                "azure",
                client_factory=factory(handler),
            )
        assert exc.value.code is DiscoveryErrorCode.UNAVAILABLE
        assert "部署" in exc.value.message or "deployment" in exc.value.message.lower()
    assert calls == []
