from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.agentic.client import _ProviderOpenAIAdapter
from deeptutor.services.llm import factory as factory_module
from deeptutor.services.llm.config import LLMConfig, resolve_output_token_budget
from deeptutor.services.llm.exceptions import LLMConfigError
from deeptutor.services.llm.provider_core.base import LLMResponse


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def chat_with_retry(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(dict(kwargs))
        return LLMResponse(content="ok", finish_reason="stop")

    async def chat_stream_with_retry(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(dict(kwargs))
        on_delta = kwargs.get("on_content_delta")
        if on_delta is not None:
            await on_delta("streamed")
        return LLMResponse(content="streamed", finish_reason="stop")


def config(**overrides: Any) -> LLMConfig:
    values = {
        "model": "deepseek-flash",
        "api_key": "sk-fictitious",
        "base_url": "https://api.deepseek.com",
        "binding": "deepseek",
        "provider_name": "deepseek",
        "max_tokens": 8192,
        "max_output_tokens": 393216,
    }
    values.update(overrides)
    return LLMConfig(**values)


@pytest.mark.asyncio
async def test_factory_complete_and_stream_send_selected_and_explicit_budgets(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(factory_module, "get_runtime_provider", lambda _config: fake)
    monkeypatch.setattr(factory_module, "get_llm_config", config)

    await factory_module.complete("hello")
    assert fake.calls[-1]["max_tokens"] == 8192

    await factory_module.complete("hello", max_tokens=512)
    assert fake.calls[-1]["max_tokens"] == 512

    await factory_module.complete("hello", max_tokens=999999)
    assert fake.calls[-1]["max_tokens"] == 393216

    chunks = [chunk async for chunk in factory_module.stream("hello")]
    assert chunks
    assert fake.calls[-1]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_legacy_factory_config_sends_4096(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(factory_module, "get_runtime_provider", lambda _config: fake)
    legacy = config(max_tokens=4096, max_output_tokens=None)
    monkeypatch.setattr(factory_module, "get_llm_config", lambda: legacy)
    await factory_module.complete("hello")
    assert fake.calls[-1]["max_tokens"] == 4096


def test_output_budget_priority_and_cap():
    assert (
        resolve_output_token_budget(explicit=512, configured=8192, provider_max=393216)
        == 512
    )
    assert (
        resolve_output_token_budget(explicit=None, configured=8192, provider_max=393216)
        == 8192
    )
    assert (
        resolve_output_token_budget(explicit=None, configured=None, provider_max=None)
        == 4096
    )
    assert (
        resolve_output_token_budget(explicit=999999, configured=8192, provider_max=32768)
        == 32768
    )
    assert (
        resolve_output_token_budget(explicit=512, configured=8192, provider_max=256)
        == 256
    )


def test_core_agentic_completion_kwargs_apply_budget_and_cap():
    pipeline = object.__new__(AgenticChatPipeline)
    pipeline.llm_config = SimpleNamespace(max_tokens=8192)
    pipeline._max_output_tokens = 32768
    pipeline._chat_temperature = 0.2
    pipeline.model = "deepseek-flash"
    pipeline.binding = "deepseek"
    pipeline.reasoning_effort = None
    assert pipeline._completion_kwargs(8000)["max_tokens"] == 8000
    assert pipeline._completion_kwargs(999999)["max_tokens"] == 32768


@pytest.mark.asyncio
async def test_core_agentic_adapter_forwards_budget_to_provider():
    class CapturingProvider:
        def __init__(self) -> None:
            self.max_tokens = None

        async def chat_stream(self, **kwargs: Any) -> LLMResponse:
            self.max_tokens = kwargs["max_tokens"]
            on_delta = kwargs.get("on_content_delta")
            if on_delta is not None:
                await on_delta("x")
            return LLMResponse(content="x", finish_reason="stop")

    provider = CapturingProvider()
    adapter = _ProviderOpenAIAdapter(provider)
    stream = await adapter.chat.completions.create(
        messages=[{"role": "user", "content": "hi"}],
        model="deepseek-flash",
        max_tokens=2048,
        stream=True,
    )
    async for _chunk in stream:
        pass
    assert provider.max_tokens == 2048


@pytest.mark.asyncio
async def test_long_history_with_large_output_budget_is_refused_after_snipping():
    pipeline = object.__new__(AgenticChatPipeline)
    pipeline.llm_config = SimpleNamespace(context_window=32768, max_tokens=8192)
    pipeline.model = "deepseek-flash"
    pipeline._max_output_tokens = 16384
    pipeline._respond_max_tokens = 16000
    pipeline._exploring_max_tokens = 1600
    pipeline._last_prompt_blocks = []

    async def no_progress(*_args, **_kwargs):
        return None

    stream = SimpleNamespace(progress=no_progress)
    pipeline._tool_result_snip_marker = lambda: "[snipped]"
    pipeline._estimate_messages_tokens = lambda messages: sum(
        len(str(item.get("content") or "")) // 4 for item in messages
    )
    pipeline._t = lambda key: key
    messages = [
        {"role": "user", "content": "x" * 100000},
        {"role": "tool", "content": "y" * 100000},
    ]
    with pytest.raises(LLMConfigError):
        await pipeline._guard_context_window(messages, stream)
