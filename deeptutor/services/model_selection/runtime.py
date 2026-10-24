"""Runtime helpers for request-scoped model selection."""

from __future__ import annotations

from contextvars import Token
from typing import Any

from deeptutor.services.config.provider_runtime import ResolvedLLMConfig, resolve_llm_runtime_config
from deeptutor.services.llm import config as llm_config_module
from deeptutor.services.llm.config import LLMConfig


def llm_config_from_resolved(resolved: ResolvedLLMConfig) -> LLMConfig:
    """Convert provider-runtime output into the LLM service config shape."""
    return LLMConfig(
        model=resolved.model,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        effective_url=resolved.effective_url,
        binding=resolved.binding,
        provider_name=resolved.provider_name,
        provider_mode=resolved.provider_mode,
        api_version=resolved.api_version,
        extra_headers=resolved.extra_headers,
        reasoning_effort=resolved.reasoning_effort,
        context_window=resolved.context_window,
    )


def resolve_llm_config_for_selection(selection: Any) -> LLMConfig:
    """Resolve the LLM config for a chat/session selection reference."""
    if selection is None:
        return llm_config_module.get_llm_config()
    return llm_config_from_resolved(resolve_llm_runtime_config(llm_selection=selection))


def activate_llm_selection(
    selection: Any,
    *,
    reasoning_effort: str | None = None,
    reasoning_protocol: str | None = None,
    apply_reasoning: bool = False,
) -> tuple[LLMConfig, Token[LLMConfig | None]]:
    """Resolve and install a scoped LLM config for the current async context.

    ``apply_reasoning=True`` writes only this turn's resolved effort onto the
    scoped copy; it never touches ``model_catalog`` or the global cache.
    """

    config = resolve_llm_config_for_selection(selection)
    if apply_reasoning:
        from deeptutor.services.llm.reasoning_controls import apply_reasoning_to_config

        config = apply_reasoning_to_config(
            config,
            reasoning_effort,
            protocol=reasoning_protocol,
        )
    token = llm_config_module.set_scoped_llm_config(config)
    return config, token


def reset_llm_selection(token: Token[LLMConfig | None] | None) -> None:
    if token is not None:
        llm_config_module.reset_scoped_llm_config(token)


__all__ = [
    "activate_llm_selection",
    "llm_config_from_resolved",
    "reset_llm_selection",
    "resolve_llm_config_for_selection",
]
