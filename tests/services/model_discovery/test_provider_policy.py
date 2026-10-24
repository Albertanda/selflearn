from __future__ import annotations

import pytest

from deeptutor.services.model_discovery.provider_policy import (
    ADAPTER_ALIYUN,
    ADAPTER_ANTHROPIC,
    ADAPTER_AZURE,
    ADAPTER_GEMINI,
    ADAPTER_MANAGED,
    ADAPTER_OLLAMA,
    ADAPTER_OPENAI,
    ADAPTER_SILICONFLOW,
    PROVIDER_POLICIES,
    adapter_for,
    policy_for,
    policy_matrix,
    provider_identity,
    registry_policy_gaps,
)
from deeptutor.services.provider_registry import PROVIDERS, canonical_provider_name

EXPECTED_ADAPTERS = {
    "custom": ADAPTER_OPENAI,
    "custom_anthropic": ADAPTER_ANTHROPIC,
    "azure_openai": ADAPTER_AZURE,
    "openrouter": ADAPTER_OPENAI,
    "orcarouter": ADAPTER_OPENAI,
    "edenai": ADAPTER_OPENAI,
    "aihubmix": ADAPTER_OPENAI,
    "siliconflow": ADAPTER_SILICONFLOW,
    "novita": ADAPTER_OPENAI,
    "atlascloud": ADAPTER_OPENAI,
    "volcengine": ADAPTER_OPENAI,
    "volcengine_coding_plan": ADAPTER_OPENAI,
    "byteplus": ADAPTER_OPENAI,
    "byteplus_coding_plan": ADAPTER_OPENAI,
    "anthropic": ADAPTER_ANTHROPIC,
    "openai": ADAPTER_OPENAI,
    "openai_codex": ADAPTER_MANAGED,
    "github_copilot": ADAPTER_MANAGED,
    "codebuddy": ADAPTER_MANAGED,
    "deepseek": ADAPTER_OPENAI,
    "gemini": ADAPTER_GEMINI,
    "zhipu": ADAPTER_OPENAI,
    "dashscope": ADAPTER_ALIYUN,
    "moonshot": ADAPTER_OPENAI,
    "minimax": ADAPTER_OPENAI,
    "minimax_anthropic": ADAPTER_ANTHROPIC,
    "mistral": ADAPTER_OPENAI,
    "stepfun": ADAPTER_OPENAI,
    "xiaomi_mimo": ADAPTER_OPENAI,
    "vllm": ADAPTER_OPENAI,
    "ollama": ADAPTER_OLLAMA,
    "lm_studio": ADAPTER_OPENAI,
    "llama_cpp": ADAPTER_OPENAI,
    "lemonade": ADAPTER_OPENAI,
    "ovms": ADAPTER_OPENAI,
    "nvidia_nim": ADAPTER_OPENAI,
    "groq": ADAPTER_OPENAI,
    "qianfan": ADAPTER_OPENAI,
}


def test_every_registered_provider_has_one_explicit_policy():
    names = [spec.name for spec in PROVIDERS]
    assert len(names) == 38
    assert len(set(names)) == 38
    assert registry_policy_gaps() == []
    assert set(PROVIDER_POLICIES) == set(names)
    matrix = policy_matrix()
    assert set(matrix) == set(names)
    for name, adapter in EXPECTED_ADAPTERS.items():
        assert matrix[name]["adapter"] == adapter
        assert matrix[name]["identity"] == name


def test_policy_does_not_merge_transport_family_into_provider_identity():
    for name in ("openai", "custom", "vllm", "lm_studio", "deepseek", "openrouter"):
        assert provider_identity(name, "llm") == name
    assert provider_identity("openai_compatible", "llm") == "custom"
    # Aliyun aliases are real aliases for the one existing LLM identity.
    for alias in ("aliyun", "alibaba", "bailian", "dashscope"):
        assert provider_identity(alias, "llm") == "dashscope"
    # The STT/embedding adapters keep the existing aliyun identity.
    assert provider_identity("dashscope", "stt") == "aliyun"
    assert provider_identity("aliyun", "embedding") == "aliyun"


def test_managed_entries_are_explicit_and_not_dispatched():
    for name in ("openai_codex", "github_copilot", "codebuddy"):
        policy = policy_for(name)
        assert policy is not None and policy.managed
        assert adapter_for(
            binding=name, service="llm", base_url="https://example.test/v1"
        ) == ADAPTER_MANAGED
    assert policy_for("not_a_registered_provider") is None
    assert adapter_for(
        binding="not_a_registered_provider",
        service="llm",
        base_url="https://example.test/v1",
    ) == "unsupported"


def test_native_hosts_and_gateway_paths_choose_protocol_not_identity():
    assert adapter_for(
        binding="siliconflow",
        service="llm",
        base_url="https://api.siliconflow.cn/v1",
        is_official_siliconflow=lambda value: "siliconflow.cn" in value,
    ) == ADAPTER_SILICONFLOW
    assert adapter_for(
        binding="siliconflow",
        service="llm",
        base_url="https://school.example.test/v1",
        is_official_siliconflow=lambda value: "siliconflow.cn" in value,
    ) == ADAPTER_OPENAI
    assert adapter_for(
        binding="dashscope",
        service="llm",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        is_official_aliyun=lambda value: "dashscope.aliyuncs.com" in value,
    ) == ADAPTER_ALIYUN
    assert adapter_for(
        binding="dashscope",
        service="llm",
        base_url="https://gateway.example.test/v1",
        is_official_aliyun=lambda value: False,
    ) == ADAPTER_OPENAI
    assert adapter_for(
        binding="dashscope",
        service="llm",
        base_url="https://gateway.example.test/v1",
        directory_url="https://gateway.example.test/v1/models",
        is_official_aliyun=lambda value: False,
    ) == ADAPTER_ALIYUN
    assert adapter_for(
        binding="gemini",
        service="llm",
        base_url="https://proxy.example.test/v1beta/openai/",
    ) == ADAPTER_OPENAI
    assert adapter_for(
        binding="gemini",
        service="llm",
        base_url="https://proxy.example.test/v1beta/openai/",
        directory_url="https://proxy.example.test/v1beta/models",
    ) == ADAPTER_GEMINI
    assert adapter_for(
        binding="gemini",
        service="llm",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ) == ADAPTER_GEMINI


def test_registry_alias_does_not_create_a_second_aliyun_entry():
    values = [spec.name for spec in PROVIDERS]
    assert values.count("dashscope") == 1
    assert "aliyun" not in values
    assert canonical_provider_name("aliyun") == "dashscope"
    assert canonical_provider_name("bailian") == "dashscope"
    dashscope = next(spec for spec in PROVIDERS if spec.name == "dashscope")
    assert "阿里云百炼" in dashscope.label


@pytest.mark.asyncio
async def test_every_non_managed_provider_enters_a_bounded_directory_request():
    import json

    import httpx

    from deeptutor.services.model_discovery.adapters import fetch_catalog
    from deeptutor.services.model_discovery.types import Connection, adapter_kind

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("/api/v1/models"):
            payload = {"output": {"total": 1, "models": [{"model": "qwen-plus", "capabilities": ["TG"]}]}}
        elif path.endswith("/api/tags"):
            payload = {"models": [{"name": "llama3.2:latest"}]}
        elif path.endswith("/models") and "generativelanguage" in str(request.url):
            payload = {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}]}
        else:
            payload = {"data": [{"id": "model-a"}]}
        return httpx.Response(200, content=json.dumps(payload).encode())

    def client_factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    base_urls = {
        "anthropic": "https://api.anthropic.com/v1",
        "minimax_anthropic": "https://api.minimax.io/anthropic",
        "azure_openai": "https://resource.openai.azure.com/openai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "siliconflow": "https://api.siliconflow.cn/v1",
        "ollama": "http://localhost:11434/v1",
    }
    for spec in PROVIDERS:
        policy = PROVIDER_POLICIES[spec.name]
        connection = Connection.from_mapping(
            {
                "binding": spec.name,
                "base_url": base_urls.get(spec.name, f"https://{spec.name}.example.test/v1"),
                "api_key": "sk-fictitious",
            }
        )
        adapter = adapter_kind("llm", connection)
        if policy.managed:
            assert adapter == "unsupported"
            continue
        before = len(calls)
        outcome = await fetch_catalog(
            connection, "llm", adapter, client_factory=client_factory
        )
        assert outcome.error is None, spec.name
        assert len(calls) > before, spec.name
