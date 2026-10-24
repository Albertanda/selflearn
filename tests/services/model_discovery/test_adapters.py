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


def connection(
    base_url: str,
    *,
    binding: str,
    key: str = "sk.fictitious.with.dots",
    headers: dict[str, str] | None = None,
) -> Connection:
    return Connection.from_mapping(
        {
            "binding": binding,
            "base_url": base_url,
            "api_key": key,
            "extra_headers": headers or {},
        }
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
async def test_aliyun_native_pagination_auth_and_capability_routing():
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(urlsplit(str(request.url)).query)
        requests.append(
            {
                "url": str(request.url),
                "page": int(query["page_no"][0]),
                "size": int(query["page_size"][0]),
                "auth": request.headers.get("authorization"),
            }
        )
        if int(query["page_no"][0]) == 1:
            return json_response(
                {
                    "success": True,
                    "output": {
                        "total": 3,
                        "page_no": 1,
                        "page_size": 100,
                        "models": [
                            {
                                "model": "qwen3-asr-flash",
                                "name": "Qwen3 ASR Flash",
                                "capabilities": ["ASR"],
                                "inference_provider": "aliyun-bailian",
                                "model_info": {"context_window": 8192},
                            },
                            {
                                "model": "paraformer-realtime-v2",
                                "name": "Paraformer Realtime",
                                "capabilities": ["Realtime-ASR"],
                            },
                        ],
                    },
                }
            )
        return json_response(
            {
                "success": True,
                "output": {
                    "total": 3,
                    "page_no": 2,
                    "page_size": 100,
                    "models": [
                        {
                            "model": "qwen3-asr-flash-filetrans",
                            "name": "Filetrans",
                            "capabilities": ["ASR"],
                        },
                        {
                            "model": "qwen-plus",
                            "name": "Qwen Plus",
                            "capabilities": ["TG", "Reasoning"],
                        },
                    ],
                },
            }
        )

    outcome = await fetch_catalog(
        connection(
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            binding="aliyun",
        ),
        "stt",
        "aliyun",
        client_factory=factory(handler),
    )
    assert [model.id for model in outcome.models] == [
        "qwen3-asr-flash",
        "paraformer-realtime-v2",
        "qwen3-asr-flash-filetrans",
    ]
    assert outcome.models[0].runtime_compatibility == "supported"
    assert outcome.models[1].runtime_compatibility == "unsupported"
    assert outcome.models[1].reason_code == "realtime_protocol_unsupported"
    assert outcome.models[2].reason_code == "aliyun_filetrans_protocol_unsupported"
    assert outcome.models[0].context_window == 8192
    assert all("aliyun" in item["url"] for item in requests)
    assert all(item["auth"] == "Bearer sk.fictitious.with.dots" for item in requests)
    assert requests[0]["size"] == 100


@pytest.mark.asyncio
async def test_aliyun_third_party_routing_is_unknown_not_supported():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "output": {
                    "total": 1,
                    "page_no": 1,
                    "page_size": 100,
                    "models": [
                        {
                            "model": "deepseek-v3",
                            "name": "DeepSeek V3",
                            "capabilities": ["TG"],
                            "inference_provider": "siliconflow",
                        }
                    ],
                }
            }
        )

    outcome = await fetch_catalog(
        connection("https://ws.cn-beijing.maas.aliyuncs.com/v1", binding="aliyun"),
        "llm",
        "aliyun",
        client_factory=factory(handler),
    )
    assert outcome.models[0].runtime_compatibility == "unknown"
    assert outcome.models[0].reason_code == "third_party_inference_routing"


@pytest.mark.asyncio
async def test_aliyun_no_progress_pagination_is_incomplete():
    def handler(request: httpx.Request) -> httpx.Response:
        models = [
            {"model": f"qwen-model-{index}", "capabilities": ["TG"]}
            for index in range(100)
        ]
        return json_response(
            {"output": {"total": 200, "page_no": 1, "page_size": 100, "models": models}}
        )

    outcome = await fetch_catalog(
        connection("https://dashscope.aliyuncs.com/v1", binding="aliyun"),
        "llm",
        "aliyun",
        client_factory=factory(handler),
    )
    assert outcome.complete is False
    assert outcome.error is not None
    assert outcome.error.code is DiscoveryErrorCode.INCOMPLETE


@pytest.mark.asyncio
async def test_aliyun_404_is_not_reported_as_empty_account():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b'{"message":"not found"}')

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            connection("https://dashscope.aliyuncs.com/v1", binding="aliyun"),
            "stt",
            "aliyun",
            client_factory=factory(handler),
        )
    assert exc.value.code is DiscoveryErrorCode.UNAVAILABLE
    assert "workspace" in exc.value.message.lower() or "业务空间" in exc.value.message


@pytest.mark.asyncio
async def test_siliconflow_exact_subtype_and_reranker_rejection():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(
            {
                "object": "list",
                "data": [
                    {"id": "Qwen/Qwen3-Embedding-8B", "name": "Embedding"},
                    {"id": "BAAI/bge-reranker-v2-m3", "sub_type": "reranker"},
                ],
            }
        )

    outcome = await fetch_catalog(
        connection("https://api.siliconflow.cn/v1", binding="siliconflow"),
        "embedding",
        "siliconflow",
        client_factory=factory(handler),
    )
    assert [model.id for model in outcome.models] == ["Qwen/Qwen3-Embedding-8B"]
    assert parse_qs(urlsplit(str(requests[0].url)).query)["sub_type"] == ["embedding"]


@pytest.mark.asyncio
async def test_siliconflow_tts_and_vision_use_presets_without_network():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("preset-only categories must not call the provider")

    tts = await fetch_catalog(
        connection("https://api.siliconflow.cn/v1", binding="siliconflow"),
        "tts",
        "siliconflow",
        client_factory=factory(handler),
    )
    vision = await fetch_catalog(
        connection("https://api.siliconflow.cn/v1", binding="siliconflow"),
        "vision",
        "siliconflow",
        client_factory=factory(handler),
    )
    assert tts.remote is False
    assert tts.models[0].source == "preset"
    assert tts.models[0].id == "FunAudioLLM/CosyVoice2-0.5B"
    assert vision.models[0].source == "preset"
    assert vision.models[0].runtime_compatibility == "supported"


@pytest.mark.asyncio
async def test_compatible_data_and_bare_list_include_case_and_slashes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk.fictitious.with.dots"
        assert request.headers["x-app"] == "fixture"
        return json_response(
            {
                "data": [
                    {"id": "GPT-4.1/Mini", "name": "GPT Mini"},
                    {"id": "text-embedding-3-small", "name": "Embedding"},
                ]
            }
        )

    outcome = await fetch_catalog(
        connection(
            "https://api.openai.com/v1",
            binding="openai",
            headers={"X-App": "fixture"},
        ),
        "llm",
        "openai_compatible",
        client_factory=factory(handler),
    )
    assert [model.id for model in outcome.models] == ["GPT-4.1/Mini"]
    assert outcome.models[0].runtime_compatibility == "supported"


@pytest.mark.asyncio
async def test_compatible_bare_list_and_api_version_query():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return json_response([{"id": "my-custom-model", "name": "Custom"}])

    conn = Connection.from_mapping(
        {
            "binding": "custom",
            "base_url": "https://proxy.example.test/openai/v1",
            "api_key": "sk.fixture",
            "api_version": "2026-01-01",
        }
    )
    outcome = await fetch_catalog(
        conn, "llm", "openai_compatible", client_factory=factory(handler)
    )
    assert outcome.models[0].classification == "unknown"
    assert outcome.models[0].runtime_compatibility == "unknown"
    assert "api-version=2026-01-01" in seen[0]
    assert seen[0].endswith("/openai/v1/models?api-version=2026-01-01")



@pytest.mark.asyncio
async def test_openai_known_multimodal_family_is_offered_for_vision_and_llm():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3-small"}]})

    llm = await fetch_catalog(
        connection("https://api.openai.com/v1", binding="openai"),
        "llm",
        "openai_compatible",
        client_factory=factory(handler),
    )
    vision = await fetch_catalog(
        connection("https://api.openai.com/v1", binding="openai"),
        "vision",
        "openai_compatible",
        client_factory=factory(handler),
    )
    assert [model.id for model in llm.models] == ["gpt-4o"]
    assert [model.id for model in vision.models] == ["gpt-4o"]
    assert vision.models[0].runtime_compatibility == "supported"

@pytest.mark.asyncio
async def test_ollama_uses_tags_not_generate_or_pull_and_strips_v1():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return json_response(
            {
                "models": [
                    {"name": "llama3.2:latest", "model": "llama3.2:latest"},
                    {"name": "nomic-embed-text:latest", "model": "nomic-embed-text:latest"},
                ]
            }
        )

    outcome = await fetch_catalog(
        connection("http://127.0.0.1:11434/ollama/v1", binding="ollama", key=""),
        "llm",
        "ollama",
        client_factory=factory(handler),
    )
    assert seen == ["http://127.0.0.1:11434/ollama/api/tags"]
    assert [model.id for model in outcome.models] == [
        "llama3.2:latest",
        "nomic-embed-text:latest",
    ]
    assert outcome.models[0].classification == "unknown"
    assert outcome.models[0].runtime_compatibility == "supported"
    assert outcome.models[0].source == "remote"



@pytest.mark.asyncio
async def test_aliyun_unclassified_model_goes_to_unknown_section():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "output": {
                    "total": 1,
                    "page_no": 1,
                    "page_size": 100,
                    "models": [{"model": "mystery-model-without-capabilities"}],
                }
            }
        )

    outcome = await fetch_catalog(
        connection("https://dashscope-intl.aliyuncs.com/v1", binding="aliyun"),
        "stt",
        "aliyun",
        client_factory=factory(handler),
    )
    assert outcome.models[0].classification == "unknown"
    assert outcome.models[0].runtime_compatibility == "unknown"
    assert outcome.models[0].services == ()
    assert outcome.models[0].reason_code == "category_unconfirmed"

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, DiscoveryErrorCode.AUTH_FAILED),
        (403, DiscoveryErrorCode.FORBIDDEN),
        (429, DiscoveryErrorCode.RATE_LIMITED),
        (500, DiscoveryErrorCode.UNAVAILABLE),
    ],
)
async def test_upstream_status_mapping(status: int, expected: DiscoveryErrorCode):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=b"SECRET upstream body sk-LEAK")

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            connection("https://api.openai.com/v1", binding="openai"),
            "llm",
            "openai_compatible",
            client_factory=factory(handler),
        )
    assert exc.value.code is expected
    assert "SECRET" not in exc.value.message
    assert "sk-LEAK" not in exc.value.message


@pytest.mark.asyncio
async def test_redirect_is_never_followed_and_body_is_not_leaked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://evil.example.test/collect"},
            content=b"sk-redirect-secret",
        )

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            connection("https://api.openai.com/v1", binding="openai"),
            "llm",
            "openai_compatible",
            client_factory=factory(handler),
        )
    assert exc.value.code is DiscoveryErrorCode.INVALID_RESPONSE
    assert "evil" not in exc.value.message
    assert "sk-redirect-secret" not in exc.value.message


@pytest.mark.asyncio
async def test_malformed_json_and_oversize_page_are_bounded_errors():
    def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            connection("https://api.openai.com/v1", binding="openai"),
            "llm",
            "openai_compatible",
            client_factory=factory(bad_json),
        )
    assert exc.value.code is DiscoveryErrorCode.INVALID_RESPONSE

    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))

    with pytest.raises(DiscoveryUpstreamError) as exc:
        await fetch_catalog(
            connection("https://api.openai.com/v1", binding="openai"),
            "llm",
            "openai_compatible",
            client_factory=factory(huge),
        )
    assert exc.value.code is DiscoveryErrorCode.INCOMPLETE


@pytest.mark.asyncio
async def test_generic_model_limit_marks_incomplete():
    payload = {"data": [{"id": f"model-{index}"} for index in range(10001)]}

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(payload)

    outcome = await fetch_catalog(
        connection("https://api.openai.com/v1", binding="openai"),
        "llm",
        "openai_compatible",
        client_factory=factory(handler),
    )
    assert outcome.complete is False
    assert outcome.error is not None
    assert len(outcome.models) == 10000
