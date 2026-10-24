"""OpenAI-compatible reasoning parameter formatting.

The capability table lives in :mod:`reasoning_controls`; this module only
preserves the historical helper API and forwards one resolved selection to the
central OpenAI-compatible formatter.
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.llm.reasoning_controls import (
    is_provider_default,
    openai_compat_reasoning_fields,
)

_PROVIDER_DEFAULT_OFF_PATTERNS: dict[str, tuple[str, ...]] = {
    "gemini": ("gemini-2.5", "gemini-3"),
}
_MINIMAL_NOT_OFF_PATTERNS: dict[str, tuple[str, ...]] = {
    "gemini": ("gemini-3", "gemini-2.5-pro"),
}


def _matches(model_name: str, patterns: tuple[str, ...]) -> bool:
    model_lower = model_name.lower()
    return any(pattern.lower() in model_lower for pattern in patterns)


def default_reasoning_effort_for(provider: str | None, model: str | None) -> str | None:
    """Return the legacy implicit effort for callers outside the central path.

    Kept for compatibility with ``cloud_provider``/``executors``.  The central
    policy remains authoritative for every capability shown in the UI.
    """

    provider_name = (provider or "").strip().lower()
    off_patterns = _PROVIDER_DEFAULT_OFF_PATTERNS.get(provider_name)
    if off_patterns and _matches(model or "", off_patterns):
        if _matches(model or "", _MINIMAL_NOT_OFF_PATTERNS.get(provider_name, ())):
            return "minimal"
        return "none"
    return None


def build_openai_compatible_reasoning_kwargs(
    *,
    spec: Any,
    binding: str | None,
    model: str | None,
    reasoning_effort: str | None,
    max_tokens: int = 4096,
    protocol: str | None = None,
) -> dict[str, Any]:
    """Return Chat-Completions reasoning kwargs for one provider call.

    The provider-default sentinel suppresses both top-level and legacy auto
    defaults.  A genuine ``None`` retains the old fallback for callers that do
    not go through the per-turn runtime.
    """

    provider_name = str(getattr(spec, "name", None) or binding or "").strip().lower()
    effort = reasoning_effort
    if effort is not None and is_provider_default(effort):
        return {}
    if effort is None:
        effort = default_reasoning_effort_for(provider_name, model)
    fields = openai_compat_reasoning_fields(
        provider=provider_name,
        model=model,
        effort=effort,
        max_tokens=max_tokens,
        protocol=protocol,
    )
    kwargs: dict[str, Any] = {}
    if "reasoning_effort" in fields:
        kwargs["reasoning_effort"] = fields["reasoning_effort"]
    if fields.get("extra_body"):
        kwargs["extra_body"] = dict(fields["extra_body"])
    return kwargs


__all__ = [
    "build_openai_compatible_reasoning_kwargs",
    "default_reasoning_effort_for",
]
