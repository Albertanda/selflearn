"""Normalized, source-backed model parameters.

The directory endpoints expose a small, provider-specific vocabulary.  This
module maps only explicitly understood fields into a stable whitelist; it never
copies arbitrary upstream JSON, never picks the first matching integer
recursively, and never turns a missing limit into "unlimited".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from deeptutor.services.llm.reasoning_controls import ReasoningControls

from .types import iso_utc

METADATA_SCHEMA_VERSION = 1
MAX_SUPPORTED_DIMENSIONS = 128
MAX_JSON_SAFE_INTEGER = 9_007_199_254_740_991

PARAMETER_KEYS: tuple[str, ...] = (
    "context_window",
    "max_input_tokens",
    "max_output_tokens",
    "max_reasoning_tokens",
    "default_dimensions",
    "supported_dimensions",
    "supports_dimensions_parameter",
    "input_modalities",
    "output_modalities",
)
_INTEGER_KEYS = frozenset(
    {
        "context_window",
        "max_input_tokens",
        "max_output_tokens",
        "max_reasoning_tokens",
        "default_dimensions",
    }
)
_MODALITY_KEYS = frozenset({"input_modalities", "output_modalities"})
_MODALITIES = frozenset({"text", "image", "audio", "video"})
_PROVENANCE_KINDS = frozenset({"provider_api", "endpoint_api", "official_docs"})
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ParameterProvenance:
    kind: str
    source_url: str
    checked_at: str
    json_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "kind": self.kind,
            "source_url": self.source_url,
            "checked_at": self.checked_at,
        }
        if self.json_path:
            value["json_path"] = self.json_path
        return value


@dataclass(frozen=True, slots=True)
class ModelParameters:
    values: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, ParameterProvenance] = field(default_factory=dict)

    @property
    def context_window(self) -> int | None:
        return _positive_int(self.values.get("context_window"))

    def to_dict(self) -> dict[str, Any]:
        cleaned = _clean_values(self.values)
        provenance = {
            key: item.to_dict()
            for key, item in self.provenance.items()
            if key in cleaned and isinstance(item, ParameterProvenance)
        }
        values = {key: value for key, value in cleaned.items() if key in provenance}
        if values and provenance:
            values["provenance"] = provenance
        return values

    @classmethod
    def from_mapping(cls, value: Any) -> "ModelParameters | None":
        if not isinstance(value, Mapping):
            return None
        cleaned = _clean_values(value)
        raw_provenance = value.get("provenance")
        provenance: dict[str, ParameterProvenance] = {}
        if isinstance(raw_provenance, Mapping):
            for key, item in raw_provenance.items():
                if key not in cleaned or not isinstance(item, Mapping):
                    continue
                kind = str(item.get("kind") or "")
                source_url = clean_source_url(str(item.get("source_url") or ""))
                checked_at = _clean_checked_at(item.get("checked_at"))
                json_path = _clean_path(item.get("json_path"))
                if kind in _PROVENANCE_KINDS and source_url and checked_at:
                    provenance[key] = ParameterProvenance(
                        kind=kind,
                        source_url=source_url,
                        checked_at=checked_at,
                        json_path=json_path,
                    )
        # Every returned field must carry a valid provenance entry.
        values = {key: value for key, value in cleaned.items() if key in provenance}
        if not values:
            return None
        return cls(values=values, provenance=provenance)

    def fill_missing(self, other: "ModelParameters | None") -> "ModelParameters":
        """Supplement missing fields without ever widening a primary limit."""

        if other is None:
            return self
        values = dict(other.values)
        provenance = dict(other.provenance)
        values.update(self.values)
        provenance.update(self.provenance)
        return ModelParameters(values=values, provenance=provenance)

    def merged(self, other: "ModelParameters | None") -> "ModelParameters":
        if other is None:
            return self
        values = dict(self.values)
        provenance = dict(self.provenance)
        for key, value in other.values.items():
            values[key] = value
            source = other.provenance.get(key)
            if source is not None:
                provenance[key] = source
        return ModelParameters(values=values, provenance=provenance)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        return None
    if parsed <= 0 or parsed > MAX_JSON_SAFE_INTEGER:
        return None
    return parsed


def _clean_modalities(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip().lower()
        if token in _MODALITIES and token not in result:
            result.append(token)
    return result


def _clean_values(raw: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in _INTEGER_KEYS:
        parsed = _positive_int(raw.get(key))
        if parsed is not None:
            result[key] = parsed
    raw_dimensions = raw.get("supported_dimensions")
    if isinstance(raw_dimensions, (list, tuple)):
        dimensions: list[int] = []
        for item in raw_dimensions:
            parsed = _positive_int(item)
            if parsed is not None and parsed not in dimensions:
                dimensions.append(parsed)
        if dimensions:
            result["supported_dimensions"] = dimensions[:MAX_SUPPORTED_DIMENSIONS]
    supports = raw.get("supports_dimensions_parameter")
    if isinstance(supports, bool):
        result["supports_dimensions_parameter"] = supports
    for key in _MODALITY_KEYS:
        modalities = _clean_modalities(raw.get(key))
        if modalities:
            result[key] = modalities
    return result


def clean_source_url(value: str) -> str:
    """Strip userinfo/query/fragment; the URL is display-only."""

    text = (value or "").strip()
    if not text or _CONTROL.search(text):
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
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


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
    return iso_utc(parsed) or ""


def _clean_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub("", value).strip()
    return text[:200] or None


def provenance(
    *,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
    json_path: str | None = None,
) -> ParameterProvenance | None:
    if kind not in _PROVENANCE_KINDS:
        return None
    url = clean_source_url(source_url)
    timestamp = iso_utc(checked_at) if isinstance(checked_at, datetime) else _clean_checked_at(checked_at)
    if not url or not timestamp:
        return None
    return ParameterProvenance(
        kind=kind,
        source_url=url,
        checked_at=timestamp,
        json_path=_clean_path(json_path),
    )


def build_parameters(
    values: Mapping[str, Any],
    *,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
    json_paths: Mapping[str, str] | None = None,
) -> ModelParameters | None:
    cleaned = _clean_values(values)
    if not cleaned:
        return None
    paths = json_paths or {}
    source: dict[str, ParameterProvenance] = {}
    for key in cleaned:
        item = provenance(
            kind=kind,
            source_url=source_url,
            checked_at=checked_at,
            json_path=paths.get(key),
        )
        if item is not None:
            source[key] = item
    if not source:
        return None
    return ModelParameters(values=cleaned, provenance=source)


# ---------------------------------------------------------------------------
# Provider-specific extraction
# ---------------------------------------------------------------------------


def aliyun_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str = "provider_api",
) -> ModelParameters | None:
    model_info = raw.get("model_info")
    if not isinstance(model_info, Mapping):
        return None
    values = {
        "context_window": model_info.get("context_window"),
        "max_input_tokens": model_info.get("max_input_tokens"),
        "max_output_tokens": model_info.get("max_output_tokens"),
        "max_reasoning_tokens": model_info.get("max_reasoning_tokens"),
    }
    return build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={key: f"output.models[].model_info.{key}" for key in values},
    )


def deepseek_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str = "provider_api",
) -> ModelParameters | None:
    values = {
        "context_window": raw.get("context_window"),
        "max_output_tokens": raw.get("max_output_tokens"),
        "input_modalities": raw.get("input_modalities"),
        "output_modalities": raw.get("output_modalities"),
    }
    return build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "context_window": "data[].context_window",
            "max_output_tokens": "data[].max_output_tokens",
            "input_modalities": "data[].input_modalities",
            "output_modalities": "data[].output_modalities",
        },
    )


def generic_parameters(
    raw: Mapping[str, Any],
    *,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
) -> ModelParameters | None:
    """Only top-level, explicitly named fields on an arbitrary endpoint."""

    values = {
        "context_window": raw.get("context_window")
        or raw.get("context_length")
        or raw.get("max_context_length"),
        "max_input_tokens": raw.get("max_input_tokens"),
        "max_output_tokens": raw.get("max_output_tokens")
        or raw.get("max_completion_tokens"),
        "max_reasoning_tokens": raw.get("max_reasoning_tokens"),
        "input_modalities": raw.get("input_modalities"),
        "output_modalities": raw.get("output_modalities"),
    }
    parameters = build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "context_window": "data[].context_window|context_length|max_context_length",
            "max_input_tokens": "data[].max_input_tokens",
            "max_output_tokens": "data[].max_output_tokens|max_completion_tokens",
            "max_reasoning_tokens": "data[].max_reasoning_tokens",
            "input_modalities": "data[].input_modalities",
            "output_modalities": "data[].output_modalities",
        },
    )
    return embedding_parameters(
        raw,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        fallback=parameters,
    )


def openrouter_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
) -> ModelParameters | None:
    context = raw.get("context_length")
    top_provider = raw.get("top_provider")
    endpoint_context = (
        top_provider.get("context_length") if isinstance(top_provider, Mapping) else None
    )
    max_output = (
        top_provider.get("max_completion_tokens")
        if isinstance(top_provider, Mapping)
        else None
    )
    # Endpoint-scoped limits win when they are smaller than the model-level
    # value; never widen a gateway's declared limit to the upstream model's.
    if _positive_int(endpoint_context) and _positive_int(context):
        context = min(int(endpoint_context), int(context))
    architecture = raw.get("architecture")
    values = {
        "context_window": context,
        "max_output_tokens": max_output,
        "input_modalities": architecture.get("input_modalities")
        if isinstance(architecture, Mapping)
        else None,
        "output_modalities": architecture.get("output_modalities")
        if isinstance(architecture, Mapping)
        else None,
    }
    return build_parameters(
        values,
        kind="provider_api",
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "context_window": "data[].context_length",
            "max_output_tokens": "data[].top_provider.max_completion_tokens",
            "input_modalities": "data[].architecture.input_modalities",
            "output_modalities": "data[].architecture.output_modalities",
        },
    )


def groq_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
) -> ModelParameters | None:
    values = {
        "context_window": raw.get("context_window"),
        "max_output_tokens": raw.get("max_completion_tokens"),
    }
    return build_parameters(
        values,
        kind="provider_api",
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "context_window": "data[].context_window",
            "max_output_tokens": "data[].max_completion_tokens",
        },
    )


def mistral_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
) -> ModelParameters | None:
    values = {
        "context_window": raw.get("max_context_length") or raw.get("context_window"),
        "max_output_tokens": raw.get("max_output_tokens"),
    }
    return build_parameters(
        values,
        kind="provider_api",
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "context_window": "data[].max_context_length",
            "max_output_tokens": "data[].max_output_tokens",
        },
    )


def anthropic_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str = "provider_api",
) -> ModelParameters | None:
    values = {
        "max_input_tokens": raw.get("max_input_tokens"),
        "max_output_tokens": raw.get("max_tokens"),
    }
    capabilities = raw.get("capabilities")
    if isinstance(capabilities, Mapping):
        image = capabilities.get("image_input")
        if isinstance(image, Mapping) and image.get("supported") is True:
            values["input_modalities"] = ["text", "image"]
        elif isinstance(image, Mapping) and image.get("supported") is False:
            values["input_modalities"] = ["text"]
    return build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "max_input_tokens": "data[].max_input_tokens",
            "max_output_tokens": "data[].max_tokens",
            "input_modalities": "data[].capabilities.image_input.supported",
        },
    )


def gemini_parameters(
    raw: Mapping[str, Any],
    *,
    source_url: str,
    checked_at: datetime | str,
    kind: str = "provider_api",
) -> ModelParameters | None:
    values = {
        "max_input_tokens": raw.get("inputTokenLimit"),
        "max_output_tokens": raw.get("outputTokenLimit"),
    }
    return build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "max_input_tokens": "models[].inputTokenLimit",
            "max_output_tokens": "models[].outputTokenLimit",
        },
    )


_DIMENSION_KEYS = ("dimensions", "supported_dimensions", "embedding_dimensions")
_DEFAULT_DIMENSION_KEYS = ("default_dimensions", "default_dimension", "dimension")


def embedding_parameters(
    raw: Mapping[str, Any],
    *,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
    fallback: ModelParameters | None = None,
) -> ModelParameters | None:
    default = None
    default_key = "default_dimensions"
    for key in _DEFAULT_DIMENSION_KEYS:
        default = _positive_int(raw.get(key))
        if default is not None:
            default_key = key
            break
    choices: list[int] = []
    choices_key = "supported_dimensions"
    for key in _DIMENSION_KEYS:
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            choices_key = key
            for item in value:
                parsed = _positive_int(item)
                if parsed is not None and parsed not in choices:
                    choices.append(parsed)
    supports = raw.get("supports_dimensions_parameter")
    values = {
        "default_dimensions": default,
        "supported_dimensions": choices,
        "supports_dimensions_parameter": supports if isinstance(supports, bool) else None,
    }
    direct = build_parameters(
        values,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        json_paths={
            "default_dimensions": f"data[].{default_key}",
            "supported_dimensions": f"data[].{choices_key}",
            "supports_dimensions_parameter": "data[].supports_dimensions_parameter",
        },
    )
    return fallback.merged(direct) if fallback is not None else direct


# ---------------------------------------------------------------------------
# Official documentation supplements (small explicit table, no crawler)
# ---------------------------------------------------------------------------

OFFICIAL_PARAMETERS_PATH = Path(__file__).with_name("official_parameters.json")


def load_official_parameters(path: Path | None = None) -> dict[str, Any]:
    target = path or OFFICIAL_PARAMETERS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"schema_version": 1, "entries": []}
    return payload if isinstance(payload, dict) else {"schema_version": 1, "entries": []}


def _match_alias(model_id: str, entry: Mapping[str, Any]) -> bool:
    target = model_id.strip().lower()
    models = entry.get("models")
    if isinstance(models, list):
        return any(isinstance(item, str) and item.strip().lower() == target for item in models)
    aliases = entry.get("aliases")
    return isinstance(aliases, list) and any(
        isinstance(item, str) and item.strip().lower() == target for item in aliases
    )


def official_parameters_for(
    *,
    provider: str,
    model_id: str,
    region: str = "",
    mode: str = "",
    path: Path | None = None,
) -> ModelParameters | None:
    payload = load_official_parameters(path)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("provider") or "").strip().lower() != provider.strip().lower():
            continue
        if not _match_alias(model_id, entry):
            continue
        regions = entry.get("regions")
        if isinstance(regions, list) and regions and region not in regions and "any" not in regions:
            continue
        modes = entry.get("modes")
        if isinstance(modes, list) and modes and mode not in modes and "any" not in modes:
            # An unknown current mode may only use a conservative "any" entry.
            continue
        fields = entry.get("parameters")
        if not isinstance(fields, Mapping):
            continue
        checked = _clean_checked_at(entry.get("checked_at"))
        source = clean_source_url(str(entry.get("source_url") or ""))
        if not checked or not source:
            continue
        return build_parameters(
            fields,
            kind="official_docs",
            source_url=source,
            checked_at=checked,
            json_paths=entry.get("json_paths") if isinstance(entry.get("json_paths"), Mapping) else None,
        )
    return None


# ---------------------------------------------------------------------------
# Catalog (draft) merge helpers
# ---------------------------------------------------------------------------


def validate_catalog_model_metadata(model: Mapping[str, Any]) -> None:
    """Reject invalid capability/provenance fields before a catalog save."""

    raw_metadata = model.get("provider_metadata")
    if raw_metadata is not None:
        if not isinstance(raw_metadata, Mapping) or raw_metadata.get("schema_version") != 1:
            raise ValueError("provider_metadata.schema_version must be 1")
        raw_controls = raw_metadata.get("reasoning_controls")
        if raw_controls is not None:
            controls = ReasoningControls.from_mapping(raw_controls)
            if controls is None or controls.supported is None:
                raise ValueError("invalid provider_metadata.reasoning_controls")
            if controls.source is None:
                raise ValueError("reasoning_controls requires a source")
            raw_source = raw_controls.get("source") if isinstance(raw_controls, Mapping) else None
            if not isinstance(raw_source, Mapping):
                raise ValueError("reasoning_controls requires a source")
            raw_url = str(raw_source.get("source_url") or "")
            if raw_url != clean_source_url(raw_url):
                raise ValueError(
                    "reasoning_controls source_url must not contain userinfo, query, or fragment"
                )
        raw_parameters = raw_metadata.get("parameters")
        if raw_parameters is None:
            if raw_controls is None:
                raise ValueError("provider_metadata.parameters must be an object")
            raw_parameters = {}
        if not isinstance(raw_parameters, Mapping):
            raise ValueError("provider_metadata.parameters must be an object")
        for key in raw_parameters:
            if key not in PARAMETER_KEYS and key != "provenance":
                raise ValueError(f"unknown provider parameter: {key}")
        for key in _INTEGER_KEYS:
            value = raw_parameters.get(key)
            if value is not None and _positive_int(value) is None:
                raise ValueError(f"invalid positive integer parameter: {key}")
        raw_dimensions = raw_parameters.get("supported_dimensions")
        if raw_dimensions is not None and not isinstance(raw_dimensions, list):
            raise ValueError("supported_dimensions must be an array")
        if isinstance(raw_dimensions, list):
            for item in raw_dimensions:
                if _positive_int(item) is None:
                    raise ValueError("supported_dimensions must contain positive integers")
            if len({_positive_int(item) for item in raw_dimensions}) != len(raw_dimensions):
                raise ValueError("supported_dimensions must not contain duplicates")
            if len(raw_dimensions) > MAX_SUPPORTED_DIMENSIONS:
                raise ValueError("supported_dimensions is too long")
        supports = raw_parameters.get("supports_dimensions_parameter")
        if supports is not None and not isinstance(supports, bool):
            raise ValueError("supports_dimensions_parameter must be a boolean")
        for key in _MODALITY_KEYS:
            values = raw_parameters.get(key)
            if values is None:
                continue
            if not isinstance(values, list) or any(
                not isinstance(item, str) or item.lower() not in _MODALITIES
                for item in values
            ):
                raise ValueError(f"invalid modality list: {key}")
        parameter_fields = {
            key for key in raw_parameters if key in PARAMETER_KEYS and raw_parameters.get(key) is not None
        }
        provenance = raw_parameters.get("provenance")
        if parameter_fields or provenance is not None:
            if not isinstance(provenance, Mapping):
                raise ValueError("provenance must be an object")
            for key, item in provenance.items():
                if key not in PARAMETER_KEYS or not isinstance(item, Mapping):
                    raise ValueError("invalid provenance entry")
                if str(item.get("kind") or "") not in _PROVENANCE_KINDS:
                    raise ValueError("invalid provenance kind")
                raw_url = str(item.get("source_url") or "")
                cleaned_url = clean_source_url(raw_url)
                if not cleaned_url:
                    raise ValueError("invalid provenance source_url")
                if cleaned_url != raw_url:
                    raise ValueError("provenance source_url must not contain userinfo, query, or fragment")
                if not _clean_checked_at(item.get("checked_at")):
                    raise ValueError("invalid provenance checked_at")
            missing = sorted(parameter_fields - set(provenance))
            if missing:
                raise ValueError(f"missing provenance for: {', '.join(missing)}")
    for field_name in ("context_window", "max_tokens", "max_input_tokens", "dimension"):
        value = model.get(field_name)
        if value in (None, ""):
            continue
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError(f"invalid {field_name}")
        if _positive_int(value) is None:
            raise ValueError(f"invalid {field_name}")
    supported_dimensions = model.get("supported_dimensions")
    if supported_dimensions not in (None, ""):
        if isinstance(supported_dimensions, str):
            parts = [item.strip() for item in supported_dimensions.split(",") if item.strip()]
        elif isinstance(supported_dimensions, list):
            parts = supported_dimensions
        else:
            raise ValueError("invalid supported_dimensions")
        if len(parts) > MAX_SUPPORTED_DIMENSIONS:
            raise ValueError("supported_dimensions is too long")
        for item in parts:
            if _positive_int(item) is None:
                raise ValueError("invalid supported_dimensions")
    overrides = model.get("parameter_overrides")
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise ValueError("parameter_overrides must be an object")
        for key, value in overrides.items():
            if key not in {"context_window", "max_tokens", "dimension", "send_dimensions"}:
                raise ValueError("unknown parameter_overrides key")
            if not isinstance(value, bool):
                raise ValueError("parameter_overrides values must be booleans")


def model_override_flags(model: Mapping[str, Any]) -> dict[str, bool]:
    raw = model.get("parameter_overrides")
    flags = raw if isinstance(raw, Mapping) else {}
    result: dict[str, bool] = {}
    for key in ("context_window", "max_tokens", "dimension", "send_dimensions"):
        result[key] = flags.get(key) is True
    # Legacy entries have no flags. A non-empty existing value is treated as a
    # manual choice so a later refresh can never silently replace it.
    if not raw:
        if _positive_int(model.get("context_window")) is not None:
            result["context_window"] = True
        if _positive_int(model.get("max_tokens")) is not None:
            result["max_tokens"] = True
        if _positive_int(model.get("dimension")) is not None:
            result["dimension"] = True
        if "send_dimensions" in model:
            result["send_dimensions"] = True
    return result


def initial_catalog_parameters(
    service: str,
    parameters: ModelParameters | None,
    reasoning_controls: ReasoningControls | None = None,
) -> dict[str, Any]:
    """Values a newly imported catalog model receives (draft only)."""

    values = dict(parameters.values) if parameters is not None else {}
    controls = reasoning_controls if service == "llm" else None
    if parameters is None and controls is None:
        return {}
    if service == "llm":
        updates: dict[str, Any] = {}
        context = values.get("context_window")
        if context:
            updates["context_window"] = str(context)
            updates["context_window_source"] = "official"
            updates["context_window_detected_at"] = (
                _newest_checked_at(parameters) if parameters is not None else None
            )
        max_output = values.get("max_output_tokens")
        if max_output:
            updates["max_tokens"] = str(max_output)
        elif values.get("max_input_tokens"):
            # Input-only metadata is displayed as such, never as total context.
            updates["max_input_tokens"] = str(values["max_input_tokens"])
        metadata: dict[str, Any] = {
            "schema_version": METADATA_SCHEMA_VERSION,
            "parameters": parameters.to_dict() if parameters is not None else {},
        }
        if controls is not None:
            metadata["reasoning_controls"] = controls.to_dict()
        updates["provider_metadata"] = metadata
        updates["parameter_overrides"] = {
            "context_window": False,
            "max_tokens": False,
        }
        return updates
    if service == "embedding":
        updates = {}
        default = values.get("default_dimensions")
        choices = values.get("supported_dimensions")
        if default:
            updates["dimension"] = str(default)
        if choices:
            updates["supported_dimensions"] = ",".join(str(item) for item in choices)
        supports = values.get("supports_dimensions_parameter")
        if supports is True:
            updates["send_dimensions"] = True
        elif supports is False:
            updates["send_dimensions"] = False
        updates["provider_metadata"] = {
            "schema_version": METADATA_SCHEMA_VERSION,
            "parameters": parameters.to_dict() if parameters is not None else {},
        }
        updates["parameter_overrides"] = {
            "dimension": False,
            "send_dimensions": False,
        }
        return updates
    return {}


def _newest_checked_at(parameters: ModelParameters) -> str | None:
    values = [
        item.checked_at
        for item in parameters.provenance.values()
        if isinstance(item, ParameterProvenance) and item.checked_at
    ]
    return max(values) if values else None


def parameter_update_preview(
    existing: Mapping[str, Any],
    parameters: ModelParameters | None,
    *,
    service: str,
    restore_auto: Iterable[str] = (),
    reasoning_controls: ReasoningControls | None = None,
) -> dict[str, Any]:
    """Preview values and metadata independently; only the UI's Apply persists."""
    flags = model_override_flags(existing)
    if (parameters is None and reasoning_controls is None) or service not in {"llm", "embedding"}:
        return {"changes": [], "updates": {}, "overrides": flags}
    restore = set(restore_auto)
    values = dict(parameters.values) if parameters is not None else {}
    changes: list[dict[str, Any]] = []
    updates: dict[str, Any] = {}
    next_flags = dict(flags)
    fields = (("context_window", "context_window"), ("max_tokens", "max_output_tokens")) if service == "llm" else (("dimension", "default_dimensions"),)
    for field_name, parameter in fields:
        desired = values.get(parameter)
        if not desired or (flags[field_name] and field_name not in restore):
            continue
        current = _positive_int(existing.get(field_name))
        if current != desired:
            changes.append({"field": field_name, "from": current, "to": desired})
            updates[field_name] = str(desired)
        if field_name in restore:
            next_flags[field_name] = False
        if field_name == "context_window":
            updates["context_window_source"] = "official"
            updates["context_window_detected_at"] = (
                _newest_checked_at(parameters) if parameters is not None else None
            )
    if service == "llm" and values.get("max_input_tokens"):
        updates["max_input_tokens"] = str(values["max_input_tokens"])
    if service == "embedding":
        if values.get("supported_dimensions"):
            updates["supported_dimensions"] = ",".join(str(item) for item in values["supported_dimensions"])
        supports = values.get("supports_dimensions_parameter")
        if isinstance(supports, bool) and (not flags["send_dimensions"] or "send_dimensions" in restore):
            updates["send_dimensions"] = supports
            if "send_dimensions" in restore:
                next_flags["send_dimensions"] = False
    metadata: dict[str, Any] = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "parameters": parameters.to_dict() if parameters is not None else {},
    }
    if service == "llm" and reasoning_controls is not None:
        metadata["reasoning_controls"] = reasoning_controls.to_dict()
    updates["provider_metadata"] = metadata
    updates["parameter_overrides"] = next_flags
    updates = {key: value for key, value in updates.items() if existing.get(key) != value}
    return {"changes": changes, "updates": updates, "overrides": flags}


__all__ = [
    "MAX_JSON_SAFE_INTEGER",
    "MAX_SUPPORTED_DIMENSIONS",
    "METADATA_SCHEMA_VERSION",
    "ModelParameters",
    "OFFICIAL_PARAMETERS_PATH",
    "PARAMETER_KEYS",
    "ParameterProvenance",
    "ReasoningControls",
    "aliyun_parameters",
    "anthropic_parameters",
    "build_parameters",
    "clean_source_url",
    "deepseek_parameters",
    "embedding_parameters",
    "gemini_parameters",
    "generic_parameters",
    "groq_parameters",
    "initial_catalog_parameters",
    "load_official_parameters",
    "mistral_parameters",
    "model_override_flags",
    "official_parameters_for",
    "openrouter_parameters",
    "parameter_update_preview",
    "provenance",
    "validate_catalog_model_metadata",
]
