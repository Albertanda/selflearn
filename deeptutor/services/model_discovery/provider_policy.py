"""Explicit directory policy for every registered LLM provider.

Provider identity, inference backend, and directory protocol are separate
decisions.  This table names the directory protocol for each registry entry;
it never rewrites the provider's identity to the transport family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deeptutor.services.provider_registry import PROVIDERS, canonical_provider_name

POLICY_SCHEMA_VERSION = 1

ADAPTER_OPENAI = "openai_compatible"
ADAPTER_ANTHROPIC = "anthropic"
ADAPTER_GEMINI = "gemini"
ADAPTER_AZURE = "azure"
ADAPTER_ALIYUN = "aliyun"
ADAPTER_SILICONFLOW = "siliconflow"
ADAPTER_OLLAMA = "ollama"
ADAPTER_MANAGED = "managed"


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    name: str
    adapter: str
    # Optional structured-normalizer key (only where the endpoint's JSON shape
    # has been verified independently of the generic parser).
    structured: str | None = None
    managed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_schema_version": POLICY_SCHEMA_VERSION,
            "identity": self.name,
            "adapter": self.adapter,
            "structured": self.structured,
            "managed": self.managed,
        }


def _p(name: str, adapter: str = ADAPTER_OPENAI, *, structured: str | None = None) -> ProviderPolicy:
    return ProviderPolicy(name=name, adapter=adapter, structured=structured)


PROVIDER_POLICIES: dict[str, ProviderPolicy] = {
    "custom": _p("custom"),
    "custom_anthropic": _p("custom_anthropic", ADAPTER_ANTHROPIC),
    "azure_openai": _p("azure_openai", ADAPTER_AZURE),
    "openrouter": _p("openrouter", structured="openrouter"),
    "orcarouter": _p("orcarouter"),
    "edenai": _p("edenai"),
    "aihubmix": _p("aihubmix"),
    "siliconflow": _p("siliconflow", ADAPTER_SILICONFLOW),
    "novita": _p("novita"),
    "atlascloud": _p("atlascloud"),
    "volcengine": _p("volcengine"),
    "volcengine_coding_plan": _p("volcengine_coding_plan"),
    "byteplus": _p("byteplus"),
    "byteplus_coding_plan": _p("byteplus_coding_plan"),
    "anthropic": _p("anthropic", ADAPTER_ANTHROPIC),
    "openai": _p("openai"),
    "openai_codex": ProviderPolicy("openai_codex", ADAPTER_MANAGED, managed=True),
    "github_copilot": ProviderPolicy("github_copilot", ADAPTER_MANAGED, managed=True),
    "codebuddy": ProviderPolicy("codebuddy", ADAPTER_MANAGED, managed=True),
    "deepseek": _p("deepseek", structured="deepseek"),
    "gemini": _p("gemini", ADAPTER_GEMINI),
    "zhipu": _p("zhipu"),
    "dashscope": _p("dashscope", ADAPTER_ALIYUN),
    "moonshot": _p("moonshot"),
    "minimax": _p("minimax"),
    "minimax_anthropic": _p("minimax_anthropic", ADAPTER_ANTHROPIC),
    "mistral": _p("mistral", structured="mistral"),
    "stepfun": _p("stepfun"),
    "xiaomi_mimo": _p("xiaomi_mimo"),
    "vllm": _p("vllm"),
    "ollama": _p("ollama", ADAPTER_OLLAMA),
    "lm_studio": _p("lm_studio"),
    "llama_cpp": _p("llama_cpp"),
    "lemonade": _p("lemonade"),
    "ovms": _p("ovms"),
    "nvidia_nim": _p("nvidia_nim"),
    "groq": _p("groq", structured="groq"),
    "qianfan": _p("qianfan"),
}

# True provider aliases.  Transport-family spellings map to the custom
# OpenAI-compatible identity, not to every compatible provider.
ALIASES: dict[str, str] = {
    "openai_compatible": "custom",
    "openai_compat": "custom",
    "openai-compatible": "custom",
    "custom_openai": "custom",
    "anthropic_compatible": "custom_anthropic",
    "anthropic-compatible": "custom_anthropic",
    "azure": "azure_openai",
    "azure-openai": "azure_openai",
    "azureopenai": "azure_openai",
    "google": "gemini",
    "google_genai": "gemini",
    "claude": "anthropic",
    "aliyun": "dashscope",
    "alibaba": "dashscope",
    "bailian": "dashscope",
    "dashscope-intl": "dashscope",
    "silicon_flow": "siliconflow",
    "lmstudio": "lm_studio",
    "lm-studio": "lm_studio",
    "openai-codex": "openai_codex",
    "github-copilot": "github_copilot",
    "codebuddy_code": "codebuddy",
    "workbuddy": "codebuddy",
    "volcenginecodingplan": "volcengine_coding_plan",
    "bytepluscodingplan": "byteplus_coding_plan",
    "atlas": "atlascloud",
    "atlas_cloud": "atlascloud",
    "eden_ai": "edenai",
    "novita_ai": "novita",
    "orca_router": "orcarouter",
    "orca-router": "orcarouter",
}

ALIYUN_FAMILY = frozenset({"dashscope", "aliyun", "alibaba", "bailian", "dashscope-intl"})


def normalized_key(binding: str | None) -> str:
    return (binding or "").strip().lower().replace("-", "_")


def provider_identity(binding: str | None, service: str = "llm") -> str:
    """Return the real provider identity used for credentials and cache keys.

    The Aliyun family keeps the project's stable ``dashscope`` LLM identity;
    its non-LLM voice/embedding adapters keep the existing ``aliyun`` name.
    Other providers are never collapsed into the compatible transport family.
    """

    key = normalized_key(binding)
    if not key:
        return ""
    canonical = canonical_provider_name(binding) or key
    canonical = ALIASES.get(canonical, canonical)
    canonical = ALIASES.get(normalized_key(canonical), canonical)
    if canonical == "dashscope":
        return "dashscope" if service == "llm" else "aliyun"
    if canonical in PROVIDER_POLICIES:
        return canonical
    if key in ALIYUN_FAMILY:
        return "dashscope" if service == "llm" else "aliyun"
    return canonical


def policy_for(binding: str | None, service: str = "llm") -> ProviderPolicy | None:
    identity = provider_identity(binding, service)
    if identity == "aliyun":
        return PROVIDER_POLICIES["dashscope"]
    return PROVIDER_POLICIES.get(identity)


def is_managed(binding: str | None) -> bool:
    policy = policy_for(binding)
    return bool(policy and policy.managed)


def adapter_for(
    *,
    binding: str | None,
    service: str,
    base_url: str,
    directory_url: str = "",
    is_official_aliyun: Any = None,
    is_official_siliconflow: Any = None,
) -> str:
    """Resolve the directory protocol without changing the inference backend."""

    policy = policy_for(binding, service)
    if policy is None:
        return "unsupported"
    if policy.managed:
        return ADAPTER_MANAGED
    if policy.adapter == ADAPTER_ALIYUN:
        official = bool(is_official_aliyun(base_url)) if callable(is_official_aliyun) else False
        if official or directory_url:
            return ADAPTER_ALIYUN
        # A non-official compatible proxy may still implement /models.
        return ADAPTER_OPENAI
    if policy.adapter == ADAPTER_SILICONFLOW:
        official = bool(is_official_siliconflow(base_url)) if callable(is_official_siliconflow) else False
        return ADAPTER_SILICONFLOW if official else ADAPTER_OPENAI
    if policy.adapter == ADAPTER_GEMINI:
        # An explicit directory URL keeps the Gemini parser even on a proxy;
        # without one, only the recognised Google host may use the native map.
        host = (base_url or "").strip().lower()
        official = any(
            marker in host
            for marker in (
                "generativelanguage.googleapis.com",
                "aiplatform.googleapis.com",
            )
        )
        return ADAPTER_GEMINI if (official or directory_url) else ADAPTER_OPENAI
    if policy.adapter == ADAPTER_ANTHROPIC:
        return ADAPTER_ANTHROPIC
    if policy.adapter == ADAPTER_AZURE:
        return ADAPTER_AZURE
    if policy.adapter == ADAPTER_OLLAMA:
        return ADAPTER_OLLAMA
    return ADAPTER_OPENAI


def policy_matrix() -> dict[str, dict[str, Any]]:
    return {name: policy.to_dict() for name, policy in PROVIDER_POLICIES.items()}


def registry_policy_gaps() -> list[str]:
    registry_names = {spec.name for spec in PROVIDERS}
    return sorted(registry_names.symmetric_difference(PROVIDER_POLICIES))


__all__ = [
    "ADAPTER_ALIYUN",
    "ADAPTER_ANTHROPIC",
    "ADAPTER_AZURE",
    "ADAPTER_GEMINI",
    "ADAPTER_MANAGED",
    "ADAPTER_OLLAMA",
    "ADAPTER_OPENAI",
    "ADAPTER_SILICONFLOW",
    "ALIASES",
    "POLICY_SCHEMA_VERSION",
    "PROVIDER_POLICIES",
    "ProviderPolicy",
    "adapter_for",
    "is_managed",
    "normalized_key",
    "policy_for",
    "policy_matrix",
    "provider_identity",
    "registry_policy_gaps",
]
