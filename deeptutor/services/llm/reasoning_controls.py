"""Single source of truth for reasoning/thinking capabilities.

The UI, catalog discovery and every provider formatter consume this module.
A model name alone is never enough: a capability is resolved from the provider
identity, the exact call id and the wire protocol that will actually be used.
Unknown proxies therefore stay ``supported=None`` instead of inheriting an
official vendor's levels from a lookalike model id.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# Internal vocabulary.  These are compatibility inputs, not a claim that one
# model exposes all of them.  ``inherit`` / ``provider_default`` are selection
# modes and are deliberately not members of this tuple.
EFFORT_LEVELS: tuple[str, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)
CONTROL_KINDS: tuple[str, ...] = ("effort", "budget", "toggle", "adaptive", "unknown")
SOURCE_KINDS: tuple[str, ...] = ("provider_api", "endpoint_api", "official_docs")

# Internal config sentinel: let the provider choose, and suppress every
# project-side auto default.  It is never serialized to a vendor request.
PROVIDER_DEFAULT_EFFORT = "__provider_default__"
# Compatibility sentinel for an old client that omitted the field.  The
# runtime resolves it before the provider call; it is not a wire value.
INHERIT_EFFORT = "__inherit__"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_CHECKED = "2026-10-24T00:00:00Z"

_OFFICIAL_REASONING_HOSTS: dict[str, tuple[str, ...]] = {
    "deepseek": ("api.deepseek.com",),
    "dashscope": (
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "maas.aliyuncs.com",
    ),
    "anthropic": ("api.anthropic.com",),
    "gemini": ("generativelanguage.googleapis.com",),
    "openai": ("api.openai.com",),
    "azure_openai": ("openai.azure.com", "azure.com"),
    "github_copilot": ("api.githubcopilot.com",),
}

_DEEPSEEK_ALIASES = {
    "minimal": "low",
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
    "max": "max",
    "ultra": "max",
}


@dataclass(frozen=True, slots=True)
class ReasoningSource:
    kind: str
    source_url: str
    checked_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "source_url": self.source_url,
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True, slots=True)
class ReasoningControls:
    supported: bool | None = None
    control: str = "unknown"
    levels: tuple[str, ...] = field(default_factory=tuple)
    can_disable: bool | None = None
    default_level: str | None = None
    aliases: Mapping[str, str] = field(default_factory=dict)
    source: ReasoningSource | None = None
    # Internal only — never returned by ``to_dict``.
    wire: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "supported": self.supported,
            "control": self.control,
            "levels": list(self.levels),
            "can_disable": self.can_disable,
            "default_level": self.default_level,
            "aliases": dict(self.aliases),
        }
        if self.source is not None:
            value["source"] = self.source.to_dict()
        return value

    @classmethod
    def from_mapping(cls, value: Any) -> "ReasoningControls | None":
        if isinstance(value, ReasoningControls):
            return value
        if not isinstance(value, Mapping):
            return None
        supported = value.get("supported")
        if supported not in (True, False, None):
            return None
        control = str(value.get("control") or "unknown").strip().lower()
        if control not in CONTROL_KINDS:
            return None
        raw_levels = value.get("levels")
        if raw_levels is None:
            raw_levels = []
        if not isinstance(raw_levels, (list, tuple)):
            return None
        levels: list[str] = []
        for item in raw_levels:
            token = str(item or "").strip().lower()
            if token not in EFFORT_LEVELS or token in levels:
                return None
            levels.append(token)
        if len(levels) > len(EFFORT_LEVELS):
            return None
        can_disable = value.get("can_disable")
        if can_disable not in (True, False, None):
            return None
        default_level = value.get("default_level")
        if default_level in ("", None):
            default_level = None
        else:
            default_level = str(default_level).strip().lower()
            if default_level not in levels:
                return None
        aliases: dict[str, str] = {}
        raw_aliases = value.get("aliases")
        if raw_aliases is not None:
            if not isinstance(raw_aliases, Mapping):
                return None
            for key, target in raw_aliases.items():
                source = str(key or "").strip().lower()
                resolved = str(target or "").strip().lower()
                if source not in EFFORT_LEVELS or resolved not in levels:
                    return None
                aliases[source] = resolved
        source = _parse_source(value.get("source"))
        if supported is False:
            levels = []
            default_level = None
            aliases = {}
            can_disable = False
        if supported is True and control == "unknown":
            return None
        if supported is True and not levels and control in {"effort", "budget"}:
            return None
        return cls(
            supported=supported,
            control=control,
            levels=tuple(levels),
            can_disable=can_disable,
            default_level=default_level,
            aliases=aliases,
            source=source,
        )

    def native_effort(self, value: str | None) -> tuple[str | None, str | None]:
        """Resolve a compatibility input to a native level.

        Returns ``(effective, mapped_from)``.  ``mapped_from`` is set only when
        an alias changed the requested token.
        """

        token = str(value or "").strip().lower()
        if token in {"", "auto", "provider_default"}:
            return None, None
        if token == "none":
            if self.can_disable is True:
                return "none", None
            return None, token
        if token in self.levels:
            return token, None
        target = self.aliases.get(token)
        if target in self.levels:
            return target, token
        return None, token

    def supports_request(self, value: str | None) -> bool:
        token = str(value or "").strip().lower()
        if token in {"none", "off"}:
            return self.can_disable is True
        effective, _ = self.native_effort(token)
        return effective is not None


def _clean_source_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or _CONTROL_CHARS.search(text):
        return ""
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port in (None, 443 if parsed.scheme == "https" else 80) else f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))


def _clean_checked_at(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_source(value: Any) -> ReasoningSource | None:
    if not isinstance(value, Mapping):
        return None
    kind = str(value.get("kind") or "").strip()
    url = _clean_source_url(value.get("source_url"))
    raw_checked = value.get("checked_at")
    if isinstance(raw_checked, datetime):
        raw_checked = raw_checked.isoformat()
    checked = _clean_checked_at(raw_checked)
    if kind not in SOURCE_KINDS or not url or not checked:
        return None
    return ReasoningSource(kind=kind, source_url=url, checked_at=checked)


def _source(kind: str, url: str, checked: str = _CHECKED) -> ReasoningSource:
    parsed = _parse_source({"kind": kind, "source_url": url, "checked_at": checked})
    if parsed is None:  # pragma: no cover - constants are valid
        raise ValueError("invalid reasoning-controls source")
    return parsed


# ---------------------------------------------------------------------------
# Explicit provider rules
# ---------------------------------------------------------------------------

DEEPSEEK_DOCS = "https://api-docs.deepseek.com/guides/thinking_mode/"
ALIYUN_DEEPSEEK_DOCS = "https://help.aliyun.com/zh/model-studio/deepseek-api"
ALIYUN_QWEN_DOCS = "https://help.aliyun.com/zh/model-studio/qwen-api-via-dashscope"
ALIYUN_THINKING_DOCS = "https://help.aliyun.com/zh/model-studio/deep-thinking"
ANTHROPIC_EFFORT_DOCS = "https://platform.claude.com/docs/en/build-with-claude/effort"
ANTHROPIC_ADAPTIVE_DOCS = "https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking"
GEMINI_THINKING_DOCS = "https://ai.google.dev/gemini-api/docs/generate-content/thinking"
GEMINI_OPENAI_DOCS = "https://ai.google.dev/gemini-api/docs/openai"
OPENAI_REASONING_DOCS = "https://developers.openai.com/api/docs/guides/reasoning"


@dataclass(frozen=True, slots=True)
class _Rule:
    providers: tuple[str, ...]
    match: str  # "exact" | "prefix" | "contains"
    models: tuple[str, ...]
    controls: ReasoningControls

    def matches(self, provider: str, model: str) -> bool:
        if provider not in self.providers:
            return False
        for pattern in self.models:
            if self.match == "exact" and model == pattern:
                return True
            if self.match == "prefix" and model.startswith(pattern):
                return True
            if self.match == "contains" and pattern in model:
                return True
        return False


def _c(
    *,
    control: str,
    levels: tuple[str, ...],
    wire: str,
    can_disable: bool | None,
    default_level: str | None = None,
    aliases: Mapping[str, str] | None = None,
    source: ReasoningSource | None = None,
) -> ReasoningControls:
    return ReasoningControls(
        supported=True,
        control=control,
        levels=levels,
        can_disable=can_disable,
        default_level=default_level,
        aliases=dict(aliases or {}),
        source=source,
        wire=wire,
    )


_S = _source("official_docs", DEEPSEEK_DOCS)
_S_ALI_DEEPSEEK = _source("official_docs", ALIYUN_DEEPSEEK_DOCS)
_S_ALI_QWEN = _source("official_docs", ALIYUN_QWEN_DOCS)
_S_ALI_THINK = _source("official_docs", ALIYUN_THINKING_DOCS)
_S_ANTHROPIC = _source("official_docs", ANTHROPIC_EFFORT_DOCS)
_S_GEMINI = _source("official_docs", GEMINI_THINKING_DOCS)
_S_OPENAI = _source("official_docs", OPENAI_REASONING_DOCS)

_RULES: tuple[_Rule, ...] = (
    # ── DeepSeek official ────────────────────────────────────────────────
    _Rule(
        ("deepseek",),
        "exact",
        ("deepseek-flash", "deepseek-v4-pro"),
        _c(
            control="effort",
            levels=("low", "high", "max"),
            wire="deepseek",
            can_disable=True,
            default_level="high",
            aliases=_DEEPSEEK_ALIASES,
            source=_S,
        ),
    ),
    # ── Aliyun DeepSeek (its own versioned API rules) ────────────────────
    _Rule(
        ("dashscope",),
        "exact",
        (
            "deepseek-v4.1-flash",
            "deepseek-v4-flash-0731",
            "deepseek-v4-pro-0813",
        ),
        _c(
            control="effort",
            levels=("low", "high", "max"),
            wire="dashscope_deepseek_effort",
            can_disable=True,
            default_level="high",
            aliases=_DEEPSEEK_ALIASES,
            source=_S_ALI_DEEPSEEK,
        ),
    ),
    _Rule(
        ("dashscope",),
        "exact",
        ("deepseek-v4-pro",),
        _c(
            control="effort",
            levels=("high", "max"),
            wire="dashscope_deepseek_effort",
            can_disable=True,
            default_level="high",
            aliases={
                "minimal": "high",
                "low": "high",
                "medium": "high",
                "high": "high",
                "xhigh": "max",
                "max": "max",
                "ultra": "max",
            },
            source=_S_ALI_DEEPSEEK,
        ),
    ),
    _Rule(
        ("dashscope",),
        "exact",
        ("deepseek-v4.1-flash-1017",),
        # The exact snapshot's official page only documents thinking; keep the
        # conservative two-level subset rather than inheriting Flash's low.
        _c(
            control="effort",
            levels=("high", "max"),
            wire="dashscope_deepseek_effort",
            can_disable=True,
            default_level="high",
            aliases={
                "minimal": "high",
                "low": "high",
                "medium": "high",
                "high": "high",
                "xhigh": "max",
                "max": "max",
                "ultra": "max",
            },
            source=_S_ALI_THINK,
        ),
    ),
    # ── Aliyun Qwen 3.8: native reasoning_effort; never send budget too ──
    _Rule(
        ("dashscope",),
        "exact",
        ("qwen3.8-2.4t-a95b",),
        _c(
            control="effort",
            levels=("low", "medium", "xhigh"),
            wire="dashscope_qwen_effort",
            can_disable=False,
            default_level="xhigh",
            aliases={"minimal": "low", "high": "xhigh", "max": "xhigh"},
            source=_S_ALI_QWEN,
        ),
    ),
    _Rule(
        ("dashscope",),
        "prefix",
        ("qwen3.8",),
        _c(
            control="effort",
            levels=("low", "medium", "xhigh"),
            wire="dashscope_qwen_effort",
            can_disable=True,
            default_level="xhigh",
            aliases={"minimal": "low", "high": "xhigh", "max": "xhigh"},
            source=_S_ALI_QWEN,
        ),
    ),
    # ── Aliyun Qwen thinking-budget families ─────────────────────────────
    _Rule(
        ("dashscope",),
        "exact",
        ("qwen3.7-max-preview", "qwen3.7-max-2026-05-17"),
        _c(
            control="budget",
            levels=("low", "medium", "high"),
            wire="dashscope_budget",
            can_disable=False,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_ALI_QWEN,
        ),
    ),
    _Rule(
        ("dashscope",),
        "prefix",
        (
            "qwen3.7",
            "qwen3.6",
            "qwen3.5",
            "qwen3",
            "qwen-3",
            "qwq",
            "qwen-plus",
            "qwen-flash",
        ),
        _c(
            control="budget",
            levels=("low", "medium", "high"),
            wire="dashscope_budget",
            can_disable=True,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_ALI_THINK,
        ),
    ),
    # ── Anthropic: adaptive effort is separate from thinking mode ────────
    _Rule(
        ("anthropic",),
        "prefix",
        ("claude-opus-5-5", "claude-haiku-5-5"),
        _c(
            control="effort",
            levels=("low", "medium", "high", "xhigh", "max"),
            wire="anthropic_adaptive",
            can_disable=False,
            default_level="medium",
            aliases={"minimal": "low"},
            source=_S_ANTHROPIC,
        ),
    ),
    _Rule(
        ("anthropic",),
        "prefix",
        (
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-fable-5",
            "claude-mythos-5",
        ),
        _c(
            control="effort",
            levels=("low", "medium", "high", "xhigh", "max"),
            wire="anthropic_adaptive",
            can_disable=False,
            default_level="high",
            aliases={"minimal": "low"},
            source=_S_ANTHROPIC,
        ),
    ),
    _Rule(
        ("anthropic",),
        "prefix",
        (
            "claude-3-7",
            "claude-4",
            "claude-sonnet-4",
            "claude-opus-4",
            "claude-haiku-4",
        ),
        _c(
            control="budget",
            levels=("low", "medium", "high"),
            wire="anthropic_budget",
            can_disable=True,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_ANTHROPIC,
        ),
    ),
    # ── Gemini through the OpenAI-compatible wire ───────────────────────
    _Rule(
        ("gemini",),
        "prefix",
        ("gemini-3.8-flash",),
        _c(
            control="effort",
            levels=("low", "medium", "high"),
            wire="gemini_compat",
            can_disable=False,
            default_level="medium",
            source=_S_GEMINI,
        ),
    ),
    _Rule(
        ("gemini",),
        "prefix",
        ("gemini-3.1-flash-lite-image",),
        _c(
            control="effort",
            levels=("minimal", "high"),
            wire="gemini_compat",
            can_disable=False,
            default_level="minimal",
            source=_S_GEMINI,
        ),
    ),
    _Rule(
        ("gemini",),
        "prefix",
        ("gemini-3",),
        _c(
            control="effort",
            levels=("minimal", "low", "medium", "high"),
            wire="gemini_compat",
            can_disable=False,
            default_level="high",
            aliases={},
            source=_S_GEMINI,
        ),
    ),
    _Rule(
        ("gemini",),
        "exact",
        ("gemini-2.5-pro",),
        _c(
            control="budget",
            levels=("low", "medium", "high"),
            wire="gemini_compat",
            can_disable=False,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_GEMINI,
        ),
    ),
    _Rule(
        ("gemini",),
        "prefix",
        ("gemini-2.5",),
        _c(
            control="budget",
            levels=("none", "low", "medium", "high"),
            wire="gemini_compat",
            can_disable=True,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=GEMINI_OPENAI_DOCS and _source("official_docs", GEMINI_OPENAI_DOCS),
        ),
    ),
    # ── OpenAI-family exact models ───────────────────────────────────────
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "exact",
        ("gpt-5.1-codex-max",),
        _c(
            control="effort",
            levels=("low", "medium", "high", "xhigh"),
            wire="openai",
            can_disable=False,
            aliases={"minimal": "low", "max": "xhigh"},
            source=_S_OPENAI,
        ),
    ),
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "exact",
        ("gpt-5.1", "gpt-5.1-codex"),
        _c(
            control="effort",
            levels=("none", "low", "medium", "high"),
            wire="openai",
            can_disable=True,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_OPENAI,
        ),
    ),
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "exact",
        ("gpt-5.2",),
        _c(
            control="effort",
            levels=("none", "low", "medium", "high", "xhigh"),
            wire="openai",
            can_disable=True,
            aliases={"minimal": "low", "max": "xhigh"},
            source=_S_OPENAI,
        ),
    ),
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "exact",
        ("gpt-5-pro",),
        _c(
            control="effort",
            levels=("high",),
            wire="openai",
            can_disable=False,
            default_level="high",
            aliases={},
            source=_S_OPENAI,
        ),
    ),
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "prefix",
        ("gpt-5",),
        _c(
            control="effort",
            levels=("minimal", "low", "medium", "high"),
            wire="openai",
            can_disable=False,
            aliases={"xhigh": "high", "max": "high"},
            source=_S_OPENAI,
        ),
    ),
    _Rule(
        ("openai", "azure_openai", "github_copilot"),
        "prefix",
        ("o1", "o3", "o4", "codex-mini"),
        _c(
            control="effort",
            levels=("low", "medium", "high"),
            wire="openai",
            can_disable=False,
            aliases={"minimal": "low", "xhigh": "high", "max": "high"},
            source=_S_OPENAI,
        ),
    ),
)


def _provider_identity(provider: str | None) -> str:
    try:
        from deeptutor.services.model_discovery.provider_policy import provider_identity

        return provider_identity(provider, "llm")
    except Exception:
        return str(provider or "").strip().lower().replace("-", "_")


def _model_key(model: str | None) -> str:
    token = str(model or "").strip().lower()
    if token.startswith("models/"):
        token = token[7:]
    return token


def static_controls_for(provider: str | None, model: str | None) -> ReasoningControls | None:
    identity = _provider_identity(provider)
    key = _model_key(model)
    if not identity or not key:
        return None
    for rule in _RULES:
        if rule.matches(identity, key):
            return rule.controls
    return None


def _wire_for_metadata(identity: str, control: str) -> str:
    if identity == "deepseek":
        return "deepseek"
    if identity == "dashscope":
        if control == "budget":
            return "dashscope_budget"
        if control == "toggle":
            return "dashscope_toggle"
        return "dashscope_qwen_effort"
    if identity == "anthropic":
        return "anthropic_adaptive" if control in {"effort", "adaptive"} else "anthropic_budget"
    if identity == "gemini":
        return "gemini_compat"
    if identity in {"openai", "azure_openai", "github_copilot"}:
        return "openai"
    return "unknown"


def _official_reasoning_host(identity: str, base_url: str | None) -> bool:
    """A proxy with a vendor name does not inherit that vendor's policy."""

    if not base_url:
        # Direct callers (and managed providers without a base URL) resolve the
        # static table; catalog/runtime callers always pass their profile URL.
        return True
    try:
        host = (urlsplit(base_url.strip()).hostname or "").lower()
    except ValueError:
        return False
    if not host or "/" in host:
        return False
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in _OFFICIAL_REASONING_HOSTS.get(identity, ())
    )


def controls_for(
    provider: str | None,
    model: str | None,
    *,
    metadata: Any = None,
    model_record: Mapping[str, Any] | None = None,
    base_url: str | None = None,
) -> ReasoningControls:
    """Resolve the one safe capability summary for a concrete selection.

    Precedence: explicit catalog metadata (the exact connection's own answer),
    then a narrowly matched official rule.  Unknown providers/models remain
    unknown.  A display name is never consulted.
    """

    identity = _provider_identity(provider)
    key = _model_key(model)
    record = model_record or {}

    # Codex publishes its own per-model levels through its OAuth catalog.
    raw_levels = record.get("codex_supported_reasoning_levels")
    if identity == "openai_codex" and isinstance(raw_levels, (list, tuple)):
        levels: list[str] = []
        for item in raw_levels:
            token = str(item or "").strip().lower()
            if token in EFFORT_LEVELS and token not in levels:
                levels.append(token)
        if levels:
            default = str(record.get("codex_default_reasoning_level") or "").strip().lower()
            return ReasoningControls(
                supported=True,
                control="effort",
                levels=tuple(levels),
                can_disable="none" in levels,
                default_level=default if default in levels else None,
                aliases={},
                source=None,
                wire="codex_responses",
            )

    raw_meta = metadata
    if isinstance(metadata, Mapping) and "reasoning_controls" in metadata:
        raw_meta = metadata.get("reasoning_controls")
    parsed = ReasoningControls.from_mapping(raw_meta)
    # Bundled documentation fallback is a derived cache, not a newer answer
    # from this connection's API. Apply corrected rules without rewriting a
    # user's catalog; explicit provider/endpoint metadata still wins below.
    if (
        parsed is not None
        and parsed.source is not None
        and parsed.source.kind == "official_docs"
        and _official_reasoning_host(identity, base_url)
    ):
        current_rule = static_controls_for(identity, key)
        if current_rule is not None:
            return current_rule
    if parsed is not None and parsed.supported is not None:
        if parsed.supported is False:
            return replace(parsed, wire="none")
        wire = _wire_for_metadata(identity, parsed.control)
        if wire == "unknown":
            # An unavailable proxy may advertise arbitrary JSON; without a
            # protocol we know how to format, do not claim a usable control.
            return ReasoningControls(
                supported=None,
                control="unknown",
                source=parsed.source,
                wire="unknown",
            )
        # Keep official aliases when the per-model answer only narrows levels.
        base = static_controls_for(identity, key)
        aliases = dict(parsed.aliases)
        if not aliases and base is not None:
            aliases = {k: v for k, v in base.aliases.items() if v in parsed.levels}
        default = parsed.default_level
        if default is None and base is not None and base.default_level in parsed.levels:
            default = base.default_level
        return replace(
            parsed,
            aliases=aliases,
            default_level=default,
            wire=wire,
        )

    if _official_reasoning_host(identity, base_url):
        rule = static_controls_for(identity, key)
        if rule is not None:
            return rule
    return ReasoningControls(supported=None, control="unknown", wire="unknown")


@dataclass(frozen=True, slots=True)
class TurnReasoningResolution:
    scoped_effort: str | None
    snapshot: dict[str, Any]


def resolve_turn_reasoning(
    controls: ReasoningControls,
    *,
    model_default: str | None,
    mode: str,
    effort: str | None,
) -> TurnReasoningResolution:
    """Resolve inherit/provider_default/effort into a scoped config value."""

    mode = str(mode or "inherit")
    requested = model_default if mode == "inherit" else effort
    if mode == "provider_default":
        return TurnReasoningResolution(
            scoped_effort=PROVIDER_DEFAULT_EFFORT,
            snapshot={
                "mode": "provider_default",
                "requested": None,
                "effective": "provider_default",
                "source": "provider_default",
                "control": controls.control,
            },
        )
    if mode == "effort":
        effective = validate_override(controls, "effort", effort)
        _native, mapped = controls.native_effort(effort)
        return TurnReasoningResolution(
            scoped_effort=effective,
            snapshot={
                "mode": "effort",
                "requested": str(effort or "").strip().lower(),
                "effective": effective,
                "source": "alias" if mapped else "requested",
                "control": controls.control,
            },
        )
    # inherit
    if not model_default:
        if controls.supported is True and controls.default_level:
            return TurnReasoningResolution(
                scoped_effort=controls.default_level,
                snapshot={
                    "mode": "inherit",
                    "requested": None,
                    "effective": controls.default_level,
                    "source": "control_default",
                    "control": controls.control,
                },
            )
        scoped = None if controls.supported is True else PROVIDER_DEFAULT_EFFORT
        return TurnReasoningResolution(
            scoped_effort=scoped,
            snapshot={
                "mode": "inherit",
                "requested": None,
                "effective": "provider_default" if scoped == PROVIDER_DEFAULT_EFFORT else None,
                "source": "inherit",
                "control": controls.control,
            },
        )
    if controls.supported is not True:
        return TurnReasoningResolution(
            scoped_effort=PROVIDER_DEFAULT_EFFORT,
            snapshot={
                "mode": "inherit",
                "requested": model_default,
                "effective": "provider_default",
                "source": "unsupported_saved_value",
                "control": controls.control,
            },
        )
    if requested_effort_is_off(model_default):
        effective = "none" if controls.can_disable is True else None
        return TurnReasoningResolution(
            scoped_effort=effective or PROVIDER_DEFAULT_EFFORT,
            snapshot={
                "mode": "inherit",
                "requested": model_default,
                "effective": effective or "provider_default",
                "source": "model_default",
                "control": controls.control,
            },
        )
    effective, mapped = controls.native_effort(model_default)
    if effective is None:
        return TurnReasoningResolution(
            scoped_effort=PROVIDER_DEFAULT_EFFORT,
            snapshot={
                "mode": "inherit",
                "requested": model_default,
                "effective": "provider_default",
                "source": "unsupported_saved_value",
                "control": controls.control,
            },
        )
    return TurnReasoningResolution(
        scoped_effort=effective,
        snapshot={
            "mode": "inherit",
            "requested": model_default,
            "effective": effective,
            "source": "alias" if mapped else "model_default",
            "control": controls.control,
        },
    )


def controls_for_catalog_selection(
    catalog: Mapping[str, Any] | None,
    selection: Mapping[str, Any] | None,
) -> tuple[ReasoningControls, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    """Resolve the capability for an already-authorised catalog selection."""

    if not isinstance(catalog, Mapping):
        return ReasoningControls(), None, None
    services = catalog.get("services") if isinstance(catalog.get("services"), Mapping) else {}
    service = services.get("llm") if isinstance(services.get("llm"), Mapping) else {}
    selected = selection if isinstance(selection, Mapping) else {}
    profile_id = str(selected.get("profile_id") or service.get("active_profile_id") or "")
    model_id = str(selected.get("model_id") or service.get("active_model_id") or "")
    if not profile_id or not model_id:
        return ReasoningControls(), None, None
    profile = next(
        (
            item
            for item in service.get("profiles", []) or []
            if isinstance(item, Mapping) and str(item.get("id") or "") == profile_id
        ),
        None,
    )
    if profile is None:
        return ReasoningControls(), None, None
    model = next(
        (
            item
            for item in profile.get("models", []) or []
            if isinstance(item, Mapping) and str(item.get("id") or "") == model_id
        ),
        None,
    )
    if model is None:
        return ReasoningControls(), None, profile
    controls = controls_for(
        str(profile.get("binding") or ""),
        str(model.get("model") or ""),
        metadata=model.get("provider_metadata"),
        model_record=model,
        base_url=str(profile.get("base_url") or "") or None,
    )
    return controls, model, profile


def apply_reasoning_to_config(
    config: Any,
    effort: str | None,
    *,
    protocol: str | None = None,
) -> Any:
    """Return a copy of an ``LLMConfig`` with only the scoped effort changed."""

    update: dict[str, Any] = {}
    if effort is not None:
        update["reasoning_effort"] = effort
    if protocol is not None:
        update["reasoning_protocol"] = protocol
    if not update:
        return config
    try:
        return config.model_copy(update)
    except Exception:
        try:
            from dataclasses import replace

            return replace(config, **update)
        except Exception:
            return config


def controls_from_effort_payload(
    raw: Any,
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str = "provider_api",
    provider: str = "deepseek",
    model: str = "",
) -> ReasoningControls | None:
    """Parse DeepSeek's directory ``effort`` object into the shared schema."""

    if not isinstance(raw, Mapping):
        return None
    supported_raw = raw.get("supported_levels")
    if not isinstance(supported_raw, (list, tuple)):
        return None
    levels: list[str] = []
    for item in supported_raw:
        token = str(item or "").strip().lower()
        if token in EFFORT_LEVELS and token not in levels:
            levels.append(token)
    if not levels:
        return None
    default = str(raw.get("default_level") or "").strip().lower() or None
    if default not in levels:
        default = None
    source = _parse_source(
        {"kind": kind, "source_url": source_url, "checked_at": checked_at}
    )
    if source is None:
        return None
    base = static_controls_for(provider, model)
    aliases = (
        {key: value for key, value in base.aliases.items() if value in levels}
        if base is not None
        else {}
    )
    return ReasoningControls(
        supported=True,
        control="effort",
        levels=tuple(levels),
        can_disable=True,
        default_level=default,
        aliases=aliases,
        source=source,
        wire=base.wire if base is not None else "deepseek",
    )


def discoverable_controls(
    provider: str | None,
    model: str | None,
    raw: Mapping[str, Any] | None,
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str,
) -> ReasoningControls | None:
    """Extract only explicit directory fields, never infer from a name."""

    if not isinstance(raw, Mapping):
        raw = {}
    effort = raw.get("effort")
    if isinstance(effort, Mapping):
        parsed = controls_from_effort_payload(
            effort,
            source_url=source_url,
            checked_at=checked_at,
            kind=kind,
            provider=provider or "",
            model=model or "",
        )
        if parsed is not None:
            return parsed
    candidate = raw.get("reasoning_controls")
    if candidate is None and isinstance(raw.get("metadata"), Mapping):
        candidate = raw["metadata"].get("reasoning_controls")
    parsed = ReasoningControls.from_mapping(candidate)
    if parsed is None or parsed.supported is None:
        return None
    if parsed.source is None:
        source = _parse_source(
            {"kind": kind, "source_url": source_url, "checked_at": checked_at}
        )
        if source is not None:
            parsed = replace(parsed, source=source)
    wire = _wire_for_metadata(_provider_identity(provider), parsed.control)
    if parsed.supported is False:
        return replace(parsed, wire="none")
    return replace(parsed, wire=wire) if wire != "unknown" else None


def requested_effort_is_off(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"none", "off"}


def is_provider_default(value: str | None) -> bool:
    return value == PROVIDER_DEFAULT_EFFORT


def normalize_model_default(
    controls: ReasoningControls,
    value: str | None,
    *,
    strict: bool = False,
) -> str | None:
    """Return the native effort for a saved model setting.

    For a per-turn explicit override ``strict=True`` raises on an unsupported
    value.  A legacy saved value is suppressed (returns the provider-default
    sentinel) rather than silently amplified.
    """

    token = str(value or "").strip().lower()
    if not token:
        return None
    if controls.supported is not True:
        if strict:
            raise ValueError("This model does not expose a supported reasoning control.")
        return PROVIDER_DEFAULT_EFFORT
    if requested_effort_is_off(token):
        if controls.can_disable is True:
            return "none"
        if strict:
            raise ValueError("This model cannot disable reasoning.")
        return PROVIDER_DEFAULT_EFFORT
    effective, _mapped = controls.native_effort(token)
    if effective is None:
        if strict:
            raise ValueError(f"Unsupported reasoning level for this model: {token}")
        return PROVIDER_DEFAULT_EFFORT
    return effective


def validate_override(
    controls: ReasoningControls,
    mode: str,
    effort: str | None,
) -> str | None:
    """Validate an already-authorised turn override and return the scoped value."""

    if mode == "inherit":
        return None
    if mode == "provider_default":
        return PROVIDER_DEFAULT_EFFORT
    if mode != "effort":
        raise ValueError("reasoning_override.mode must be inherit, provider_default, or effort.")
    if controls.supported is not True:
        raise ValueError("This model does not expose a supported reasoning control.")
    return normalize_model_default(controls, effort, strict=True)


def budget_tokens_for(level: str, max_tokens: int) -> int:
    """A small, clearly-labelled budget preset that always leaves answer room.

    Anthropic requires ``budget_tokens < max_tokens``.  These are presets, not
    a claim that the vendor enumerates the same three native levels.
    """

    return _distinct_budget_preset(level, max_tokens, (1024, 2048, 3072), minimum=1024)


def dashscope_budget_for(level: str, max_tokens: int) -> int:
    return _distinct_budget_preset(level, max_tokens, (1024, 4096, 8192), minimum=1)


def _distinct_budget_preset(
    level: str, max_tokens: int, targets: tuple[int, int, int], *, minimum: int
) -> int:
    limit = int(max_tokens)
    if limit < minimum + 3:
        raise ValueError("The output token budget is too small for three thinking presets.")
    # Keep answer room when possible; for tiny limits still enforce three
    # distinct, valid budgets rather than making all UI choices identical.
    high = min(targets[2], max(minimum + 2, limit - 512))
    low = max(minimum, min(targets[0], high - 2))
    medium = min(targets[1], high - 1)
    if high < targets[2]:
        medium = min(medium, (low + high) // 2)
    return {"low": low, "medium": medium, "high": high}.get(level, medium)


def openai_compat_reasoning_fields(
    *,
    provider: str | None,
    model: str | None,
    effort: str | None,
    max_tokens: int = 4096,
    protocol: str | None = None,
) -> dict[str, Any]:
    """Build Chat-Completions reasoning fields for one native/off selection.

    Returns top-level keys and an ``extra_body`` mapping. An explicit internal
    ``protocol`` accompanies an already-resolved native value: do not map it
    again with the fallback table. No value is sent when
    the selection is the provider-default sentinel or an unknown capability.
    ``protocol`` is the internal wire resolved with the per-turn capability; it
    keeps directory-provided overrides (e.g. a toggle) on their real wire.
    """

    if effort is None or is_provider_default(effort):
        return {}
    controls = static_controls_for(provider, model)
    wire = protocol or (controls.wire if controls is not None else "unknown")
    if wire == "unknown":
        return {}
    token = str(effort).strip().lower()
    off = requested_effort_is_off(token)
    if protocol is None and controls is not None and controls.supported is True and not off:
        effective, _ = controls.native_effort(token)
        if effective is not None:
            token = effective
    if wire == "deepseek":
        if off:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {
            "reasoning_effort": token,
            "extra_body": {"thinking": {"type": "enabled"}},
        }
    if wire == "dashscope_deepseek_effort":
        if off:
            return {"extra_body": {"enable_thinking": False}}
        return {
            "reasoning_effort": token,
            "extra_body": {"enable_thinking": True},
        }
    if wire == "dashscope_qwen_effort":
        if off:
            return {"extra_body": {"enable_thinking": False}}
        return {
            "reasoning_effort": token,
            "extra_body": {"enable_thinking": True},
        }
    if wire == "dashscope_budget":
        if off:
            return {"extra_body": {"enable_thinking": False}}
        return {
            "extra_body": {
                "enable_thinking": True,
                "thinking_budget": dashscope_budget_for(token, max_tokens),
            }
        }
    if wire == "dashscope_toggle":
        return {"extra_body": {"enable_thinking": not off}}
    if wire == "gemini_compat":
        return {"reasoning_effort": "none" if off else token}
    if wire == "openai":
        if off:
            if protocol is None and controls is not None and controls.can_disable is False:
                return {}
            return {"reasoning_effort": "none"}
        return {"reasoning_effort": token}
    return {}


def responses_reasoning_fields(
    *,
    provider: str | None,
    model: str | None,
    effort: str | None,
    protocol: str | None = None,
) -> dict[str, Any]:
    if effort is None or is_provider_default(effort):
        return {}
    controls = static_controls_for(provider, model)
    wire = protocol or (
        controls.wire
        if controls is not None
        else ("codex_responses" if _provider_identity(provider) == "openai_codex" else "unknown")
    )
    if wire not in {"openai", "codex_responses"}:
        return {}
    token = str(effort).strip().lower()
    if requested_effort_is_off(token):
        if protocol is None and controls is not None and controls.can_disable is False:
            return {}
        return {"reasoning": {"effort": "none"}}
    if protocol is None and controls is not None and controls.supported is True:
        effective, _ = controls.native_effort(token)
        if effective is not None:
            token = effective
    return {"reasoning": {"effort": token}}


def anthropic_reasoning_fields(
    *,
    model: str,
    effort: str | None,
    max_tokens: int,
    protocol: str | None = None,
) -> dict[str, Any]:
    """Return Anthropic ``thinking``/``output_config`` fields.

    A provider-default selection omits both and lets the API decide.  Adaptive
    vs. legacy budget is a protocol distinction, not a user-selectable level.
    """

    controls = static_controls_for("anthropic", model)
    wire = protocol or (controls.wire if controls is not None else "unknown")
    if wire not in {"anthropic_adaptive", "anthropic_budget"}:
        return {}
    if effort is None or is_provider_default(effort):
        return {}
    token = str(effort).strip().lower()
    if requested_effort_is_off(token):
        return {}
    if protocol is None and controls is not None and controls.supported is True:
        effective, _ = controls.native_effort(token)
        if effective is None:
            return {}
        token = effective
    if wire == "anthropic_adaptive":
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": token},
        }
    budget = budget_tokens_for(token, max_tokens)
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


__all__ = [
    "ANTHROPIC_ADAPTIVE_DOCS",
    "ANTHROPIC_EFFORT_DOCS",
    "ALIYUN_DEEPSEEK_DOCS",
    "ALIYUN_QWEN_DOCS",
    "ALIYUN_THINKING_DOCS",
    "CONTROL_KINDS",
    "DEEPSEEK_DOCS",
    "EFFORT_LEVELS",
    "GEMINI_OPENAI_DOCS",
    "GEMINI_THINKING_DOCS",
    "INHERIT_EFFORT",
    "OPENAI_REASONING_DOCS",
    "PROVIDER_DEFAULT_EFFORT",
    "ReasoningControls",
    "ReasoningSource",
    "SOURCE_KINDS",
    "TurnReasoningResolution",
    "anthropic_reasoning_fields",
    "apply_reasoning_to_config",
    "budget_tokens_for",
    "controls_for",
    "controls_for_catalog_selection",
    "controls_from_effort_payload",
    "dashscope_budget_for",
    "discoverable_controls",
    "is_provider_default",
    "normalize_model_default",
    "openai_compat_reasoning_fields",
    "requested_effort_is_off",
    "resolve_turn_reasoning",
    "responses_reasoning_fields",
    "static_controls_for",
    "validate_override",
]
