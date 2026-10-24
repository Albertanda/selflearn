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


def conn(**overrides) -> Connection:
    value = {
        "binding": "custom",
        "base_url": "https://school.example.test/school/ai/v1?tenant=alpha",
        "api_key": "school.fictitious.key",
        "extra_headers": {"X-School-App": "demo"},
    }
    value.update(overrides)
    return Connection.from_mapping(value)


@pytest.mark.asyncio
async def test_school_gateway_preserves_proxy_prefix_query_headers_and_model_alias():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(
            {
                "data": [
                    {"id": "school-alias/DeepSeek-V4", "name": "DeepSeek V4"},
                    {"id": "school-alias/Qwen", "name": "Qwen"},
                ]
            }
        )

    outcome = await fetch_catalog(
        conn(), "llm", "openai_compatible", client_factory=factory(handler)
    )
    assert [model.id for model in outcome.models] == [
        "school-alias/DeepSeek-V4",
        "school-alias/Qwen",
    ]
    request = requests[0]
    parsed = urlsplit(str(request.url))
    assert parsed.path == "/school/ai/v1/models"
    assert parse_qs(parsed.query)["tenant"] == ["alpha"]
    assert request.headers["authorization"] == "Bearer school.fictitious.key"
    assert request.headers["x-school-app"] == "demo"
    assert outcome.models[0].runtime_compatibility == "unknown"
    assert outcome.models[0].reason_code == "category_unconfirmed"
    assert outcome.models[0].parameters is None


@pytest.mark.asyncio
async def test_terminal_v1_fallback_is_exactly_one_same_origin_request():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if urlsplit(str(request.url)).path == "/school/ai/v1/models":
            return httpx.Response(404, content=b'{"secret":"do-not-echo"}')
        return json_response({"data": [{"id": "model-a"}]})

    outcome = await fetch_catalog(
        conn(), "llm", "openai_compatible", client_factory=factory(handler)
    )
    assert [model.id for model in outcome.models] == ["model-a"]
    assert len(requests) == 2
    assert urlsplit(requests[1]).path == "/school/ai/models"
    assert parse_qs(urlsplit(requests[1]).query)["tenant"] == ["alpha"]
    assert all(urlsplit(url).hostname == "school.example.test" for url in requests)


@pytest.mark.asyncio
async def test_no_fallback_paths_are_used_for_a_second_404_or_business_version():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            conn(), "llm", "openai_compatible", client_factory=factory(handler)
        )
    assert exc.value.code is DiscoveryErrorCode.UNAVAILABLE
    assert len(calls) == 2
    assert "secret" not in exc.value.message

    calls.clear()
    with pytest.raises(DiscoveryUpstreamError):
        await fetch_catalog(
            conn(base_url="https://school.example.test/school/ai/v2"),
            "llm",
            "openai_compatible",
            client_factory=factory(handler),
        )
    assert calls == ["https://school.example.test/school/ai/v2/models"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, DiscoveryErrorCode.AUTH_FAILED),
        (403, DiscoveryErrorCode.FORBIDDEN),
        (429, DiscoveryErrorCode.RATE_LIMITED),
        (500, DiscoveryErrorCode.UNAVAILABLE),
    ],
)
async def test_non_404_errors_do_not_trigger_path_fallback(status, code):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=b'{"message":"upstream body"}')

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            conn(), "llm", "openai_compatible", client_factory=factory(handler)
        )
    assert exc.value.code is code
    assert len(calls) == 1
    assert "upstream body" not in exc.value.message


@pytest.mark.asyncio
async def test_timeout_tls_html_and_bad_json_are_distinct_and_not_empty_success():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom", request=request)

    def tls_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("certificate verify failed", request=request)

    async def assert_code(handler, code):
        with pytest.raises(DiscoveryUpstreamError) as exc:
            await fetch_catalog(
                conn(), "llm", "openai_compatible", client_factory=factory(handler)
            )
        assert exc.value.code is code

    await assert_code(timeout_handler, DiscoveryErrorCode.TIMEOUT)
    await assert_code(tls_handler, DiscoveryErrorCode.UNAVAILABLE)

    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>gateway login</body></html>",
            headers={"content-type": "text/html"},
        )

    await assert_code(html_handler, DiscoveryErrorCode.INVALID_RESPONSE)

    def bad_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not json")

    await assert_code(bad_json_handler, DiscoveryErrorCode.INVALID_RESPONSE)


@pytest.mark.asyncio
async def test_successful_empty_directory_is_empty_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"data": []})

    outcome = await fetch_catalog(
        conn(), "llm", "openai_compatible", client_factory=factory(handler)
    )
    assert outcome.complete is True
    assert outcome.models == []
    assert outcome.error is None


@pytest.mark.asyncio
async def test_explicit_directory_url_is_used_verbatim_and_never_falls_back():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    directory = "https://catalog.example.test/custom/path/models?version=7"
    with pytest.raises(DiscoveryUpstreamError):
        await fetch_catalog(
            conn(model_directory_url=directory),
            "llm",
            "openai_compatible",
            client_factory=factory(handler),
        )
    assert calls == [directory]


@pytest.mark.asyncio
async def test_redirect_is_not_followed_and_does_not_leak_credentials():
    calls: list[str] = []
    leaked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        leaked.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/models"})

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            conn(), "llm", "openai_compatible", client_factory=factory(handler)
        )
    assert exc.value.code is DiscoveryErrorCode.INVALID_RESPONSE
    assert "Bearer" not in exc.value.message
    assert "school.fictitious.key" not in exc.value.message
    assert len(calls) == 1
    assert all("evil.example" not in url for url in leaked)


def test_directory_url_validation_rejects_userinfo_and_fragment():
    from deeptutor.services.model_discovery.types import DiscoveryRequestError

    for bad in (
        "https://user:pass@catalog.example/models",
        "https://catalog.example/models#frag",
        "ftp://catalog.example/models",
        "not-a-url",
    ):
        with pytest.raises(DiscoveryRequestError):
            conn(model_directory_url=bad)
    assert conn(model_directory_url="http://127.0.0.1:8080/a/models?x=1").model_directory_url


@pytest.mark.asyncio
async def test_405_also_uses_exactly_one_fallback(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if urlsplit(str(request.url)).path == "/school/ai/v1/models":
            return httpx.Response(405)
        return json_response({"data": [{"id": "fallback-model"}]})

    outcome = await fetch_catalog(
        conn(), "llm", "openai_compatible", client_factory=factory(handler)
    )
    assert [model.id for model in outcome.models] == ["fallback-model"]
    assert len(calls) == 2
