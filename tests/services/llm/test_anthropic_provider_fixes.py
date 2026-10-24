"""Regression tests for Anthropic provider support of newer Claude models.

Covers three fixes:
1. A ``base_url`` ending in ``/v1`` must not be doubled by the SDK.
2. ``temperature`` is omitted for effort-based models that reject it.
3. ``cache_control`` breakpoints never exceed the Anthropic limit of 4.
"""

from __future__ import annotations

from typing import Any

import pytest

# Constructing AnthropicProvider imports the optional `anthropic` SDK ([cli]
# extra) — skip cleanly where it isn't installed (e.g. the CI python-tests job).
pytest.importorskip("anthropic")

from deeptutor.services.llm.provider_core.anthropic_provider import AnthropicProvider


def _provider(model: str = "claude-opus-4-8", api_base: str | None = None) -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key", api_base=api_base, default_model=model)


def test_base_url_trailing_v1_is_not_doubled() -> None:
    # The SDK appends its own `/v1/...`; a base_url of `.../v1` would 404.
    provider = _provider(api_base="https://api.anthropic.com/v1")
    assert str(provider._client.base_url).rstrip("/") == "https://api.anthropic.com"


def test_base_url_without_v1_is_preserved() -> None:
    provider = _provider(api_base="https://proxy.example.com/anthropic")
    assert str(provider._client.base_url).rstrip("/") == "https://proxy.example.com/anthropic"


def _kwargs(provider: AnthropicProvider, model: str) -> dict[str, Any]:
    return provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model=model,
        max_tokens=1024,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
    )


def test_temperature_omitted_for_effort_based_models() -> None:
    provider = _provider()
    for model in (
        "claude-opus-4-8",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-7",
        "claude-fable-5",
        "claude-haiku-5-5",
    ):
        assert "temperature" not in _kwargs(provider, model), model


def test_temperature_is_not_sent_to_the_anthropic_messages_sdk() -> None:
    provider = _provider()
    # anthropic 1.5 removed temperature from Messages.create/stream. Passing
    # it makes every non-adaptive Claude request fail before reaching the wire.
    for model in (
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-1",
    ):
        assert "temperature" not in _kwargs(provider, model), model


def _count_cache_control(system: Any, messages: list[dict[str, Any]], tools: list) -> int:
    s, msgs, tls = AnthropicProvider._apply_cache_control(system, messages, tools)
    total = 0
    if isinstance(s, list):
        total += sum("cache_control" in b for b in s)
    for m in msgs:
        c = m.get("content")
        if isinstance(c, list):
            total += sum("cache_control" in b for b in c)
    if tls:
        total += sum("cache_control" in t for t in tls)
    return total


def test_cache_control_never_exceeds_four() -> None:
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    for n_tools in (0, 1, 5, 12, 15, 25, 40):
        tools = [{"name": f"t{i}", "description": "d", "input_schema": {}} for i in range(n_tools)]
        assert _count_cache_control("system prompt", messages, tools) <= 4, n_tools


def _kwargs_with_effort(
    provider: AnthropicProvider,
    model: str,
    effort: str,
    *,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    return provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model=model,
        max_tokens=max_tokens,
        temperature=0.7,
        reasoning_effort=effort,
        tool_choice=None,
    )


def test_effort_based_families_map_real_effort_to_adaptive_thinking() -> None:
    """Opus 4.7+/Opus 5/Sonnet 5/Fable 5 reject enabled+budget_tokens with a
    400 — a configured effort level must become adaptive thinking there."""
    provider = _provider()
    for model in (
        "claude-opus-4-8",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-7",
        "claude-fable-5",
    ):
        kwargs = _kwargs_with_effort(provider, model, "high")
        assert kwargs["thinking"] == {"type": "adaptive"}, model
        assert "temperature" not in kwargs, model
        assert kwargs["max_tokens"] == 8192, model  # no budget headroom inflation


def test_effort_based_families_map_minimal_to_low_without_disabling() -> None:
    provider = _provider()
    kwargs = _kwargs_with_effort(provider, "claude-opus-4-8", "minimal")
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "low"}
    assert "temperature" not in kwargs


def test_older_models_keep_budget_below_the_output_limit() -> None:
    provider = _provider()
    kwargs = _kwargs_with_effort(
        provider, "claude-opus-4-6", "high", max_tokens=8192
    )
    assert kwargs["thinking"]["type"] == "enabled"
    assert 0 < kwargs["thinking"]["budget_tokens"] < 8192
    assert kwargs["max_tokens"] == 8192
    assert "temperature" not in kwargs


def test_older_models_omit_thinking_for_off_sentinels() -> None:
    """An off-sentinel used to fall through to the budget branch, where an
    unrecognised value means "default budget" — so `none` turned thinking ON."""
    provider = _provider()
    for effort in ("none", "minimum"):
        kwargs = _kwargs_with_effort(provider, "claude-opus-4-6", effort)
        assert "thinking" not in kwargs, effort
        assert "temperature" not in kwargs, effort
    # ``minimal`` is a compatibility alias for the native low level, not off.
    minimal = _kwargs_with_effort(provider, "claude-opus-4-6", "minimal")
    assert minimal["thinking"]["type"] == "enabled"


def test_legacy_adaptive_value_is_not_sent_as_an_effort() -> None:
    """``adaptive`` is a protocol mode, not a strength. A legacy stored value
    is left for the user to reset instead of being guessed into a level."""
    provider = _provider()
    kwargs = _kwargs_with_effort(provider, "claude-sonnet-4-5", "adaptive")
    assert "thinking" not in kwargs
    assert "temperature" not in kwargs


def test_off_sentinels_leave_tool_choice_to_the_caller() -> None:
    """Extended thinking forces tool_choice=auto; thinking-off must not."""
    provider = _provider()
    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"function": {"name": "t", "description": "", "parameters": {}}}],
        model="claude-opus-4-6",
        max_tokens=1024,
        temperature=0.7,
        reasoning_effort="none",
        tool_choice="required",
    )
    assert kwargs["tool_choice"] == {"type": "any"}
