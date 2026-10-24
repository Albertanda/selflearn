"""Pure provider/category/runtime compatibility rules for model discovery.

A provider's directory is not a statement that this project can run every
model.  These helpers keep that distinction explicit: category membership is
derived only from provider evidence (or a small, traceable mapping), while
``runtime_compatibility`` answers a different question about adapters that
actually exist in this checkout.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit

from deeptutor.services.llm.reasoning_controls import (
    controls_for,
    discoverable_controls,
)

from .metadata import (
    aliyun_parameters,
    anthropic_parameters,
    deepseek_parameters,
    embedding_parameters,
    gemini_parameters,
    generic_parameters,
    groq_parameters,
    mistral_parameters,
    official_parameters_for,
    openrouter_parameters,
)
from .types import (
    Classification,
    DiscoveredModel,
    ModelSource,
    PresetModel,
    RuntimeCompatibility,
    clean_model_id,
    clean_model_name,
    coerce_context_window,
)

ALIYUN_CAPABILITY_SERVICES: dict[str, tuple[str, ...]] = {
    "TG": ("llm",),
    "Reasoning": ("llm",),
    "TR": ("embedding",),
    "ME": ("embedding",),
    "VU": ("vision",),
    "ASR": ("stt",),
    "TTS": ("tts",),
    "IG": ("imagegen",),
    "VG": ("videogen",),
}

ALIYUN_REALTIME_CAPABILITIES = frozenset(
    {
        "Realtime-Omni",
        "Realtime-Text-to-Speech",
        "Realtime-ASR",
        "Realtime-Audio-Translate",
        "Realtime-Chatting",
    }
)

SILICONFLOW_SUBTYPE_SERVICES: dict[str, str] = {
    "chat": "llm",
    "embedding": "embedding",
    "speech-to-text": "stt",
    "text-to-image": "imagegen",
    "text-to-video": "videogen",
    "image-to-image": "imagegen",
}

# Small, traceable presets.  Each is the provider's default model already used
# by this project (or a documented SF vision model); source=preset, never a
# claim that the account directory returned it.
SILICONFLOW_PRESETS: dict[str, tuple[PresetModel, ...]] = {
    "tts": (
        PresetModel(
            id="FunAudioLLM/CosyVoice2-0.5B",
            name="CosyVoice2 0.5B",
            service="tts",
            runtime_compatibility=RuntimeCompatibility.SUPPORTED,
        ),
    ),
    "vision": (
        PresetModel(
            id="Qwen/Qwen2.5-VL-72B-Instruct",
            name="Qwen2.5-VL 72B Instruct",
            service="vision",
            runtime_compatibility=RuntimeCompatibility.SUPPORTED,
        ),
    ),
}

ALIYUN_PRESETS: dict[str, tuple[PresetModel, ...]] = {
    "stt": (
        PresetModel(
            id="qwen3-asr-flash",
            name="千问 ASR Flash",
            service="stt",
            runtime_compatibility=RuntimeCompatibility.SUPPORTED,
        ),
    ),
}


def _normalized_tokens(values: Iterable[Any] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            token = value.strip()
        elif isinstance(value, Mapping):
            token = str(value.get("name") or value.get("code") or "").strip()
        else:
            token = str(value or "").strip()
        if token and token not in result:
            result.append(token)
    return result


def _modality_services(metadata: Mapping[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(metadata, Mapping):
        return ()
    request = {str(item).lower() for item in _normalized_tokens(metadata.get("request_modality"))}
    response = {str(item).lower() for item in _normalized_tokens(metadata.get("response_modality"))}
    services: list[str] = []
    if "audio" in request and "text" in response:
        services.append("stt")
    if "text" in request and "audio" in response:
        services.append("tts")
    if "text" in request and "image" in response:
        services.append("imagegen")
    if "text" in request and "video" in response:
        services.append("videogen")
    if "text" in request and "text" in response:
        services.append("llm")
    if "image" in request and "text" in response and "llm" not in services:
        services.append("llm")
    return tuple(dict.fromkeys(services))


def aliyun_services(
    capabilities: Iterable[Any] | None,
    inference_metadata: Mapping[str, Any] | None = None,
    *,
    model_id: str = "",
) -> tuple[str, ...]:
    tokens = _normalized_tokens(capabilities)
    services: list[str] = []
    for token in tokens:
        mapped = ALIYUN_CAPABILITY_SERVICES.get(token)
        if mapped:
            services.extend(mapped)
        elif token in ALIYUN_REALTIME_CAPABILITIES:
            # Realtime entries belong to a category for explanation, but their
            # protocol is never marked supported below.
            if "ASR" in token:
                services.append("stt")
            elif "Text-to-Speech" in token:
                services.append("tts")
            elif token in {"Realtime-Omni", "Realtime-Chatting"}:
                services.append("llm")
    if not services:
        services.extend(_modality_services(inference_metadata))
    lowered = model_id.lower()
    if "asr" in lowered or "paraformer" in lowered or "fun-asr" in lowered:
        services.append("stt")
    if "tts" in lowered or "cosyvoice" in lowered:
        services.append("tts")
    if "embedding" in lowered:
        services.append("embedding")
    if any(token in lowered for token in ("qwen-vl", "qwen2.5-vl", "qwen3-vl")):
        services.append("vision")
    return tuple(dict.fromkeys(item for item in services if item))


def _aliyun_protocol_compatibility(
    service: str,
    model_id: str,
    *,
    capabilities: Iterable[Any] | None = None,
) -> tuple[RuntimeCompatibility, str | None]:
    caps = set(_normalized_tokens(capabilities))
    lowered = model_id.lower()
    realtime = bool(caps & ALIYUN_REALTIME_CAPABILITIES) or "realtime" in lowered

    if service == "stt":
        if model_id == "qwen3-asr-flash":
            return RuntimeCompatibility.SUPPORTED, None
        if "filetrans" in lowered:
            return (
                RuntimeCompatibility.UNSUPPORTED,
                "aliyun_filetrans_protocol_unsupported",
            )
        if "fun-asr" in lowered or "funasr" in lowered:
            return (
                RuntimeCompatibility.UNSUPPORTED,
                "aliyun_fun_asr_protocol_unsupported",
            )
        if realtime:
            return RuntimeCompatibility.UNSUPPORTED, "realtime_protocol_unsupported"
        return (
            RuntimeCompatibility.UNSUPPORTED,
            "aliyun_stt_adapter_not_implemented",
        )
    if service == "tts":
        if realtime:
            return RuntimeCompatibility.UNSUPPORTED, "realtime_protocol_unsupported"
        return RuntimeCompatibility.UNSUPPORTED, "aliyun_tts_adapter_not_implemented"
    if service == "imagegen":
        return RuntimeCompatibility.UNSUPPORTED, "aliyun_imagegen_adapter_not_implemented"
    if service == "videogen":
        return RuntimeCompatibility.UNSUPPORTED, "aliyun_videogen_adapter_not_implemented"
    if service == "vision":
        if any(token in lowered for token in ("qwen-vl", "qwen2.5-vl", "qwen3-vl")):
            return RuntimeCompatibility.SUPPORTED, None
        if realtime:
            return RuntimeCompatibility.UNSUPPORTED, "realtime_protocol_unsupported"
        return RuntimeCompatibility.UNKNOWN, "aliyun_vision_model_unverified"
    if service == "embedding":
        if lowered.startswith(("text-embedding-v", "multimodal-embedding-v")):
            return RuntimeCompatibility.SUPPORTED, None
        return RuntimeCompatibility.UNKNOWN, "aliyun_embedding_model_unverified"
    if service == "llm":
        if realtime:
            return RuntimeCompatibility.UNSUPPORTED, "realtime_protocol_unsupported"
        return RuntimeCompatibility.SUPPORTED, None
    return RuntimeCompatibility.UNKNOWN, "unsupported_service"


def aliyun_runtime_compatibility(
    service: str,
    model_id: str,
    *,
    capabilities: Iterable[Any] | None = None,
    inference_provider: str = "",
) -> tuple[RuntimeCompatibility, str | None]:
    compatibility, reason = _aliyun_protocol_compatibility(
        service, model_id, capabilities=capabilities
    )
    provider = (inference_provider or "").strip().lower()
    if (
        compatibility != RuntimeCompatibility.UNSUPPORTED
        and provider
        and provider
        not in {
            "aliyun-bailian",
            "alibaba-cloud-modelstudio",
            "aliyun",
            "bailian",
            "dashscope",
        }
    ):
        return RuntimeCompatibility.UNKNOWN, "third_party_inference_routing"
    return compatibility, reason


def aliyun_model(
    raw: Mapping[str, Any],
    service: str,
    *,
    requested_service: str,
) -> DiscoveredModel | None:
    model_id = str(raw.get("model") or raw.get("id") or "").strip()
    try:
        model_id = clean_model_id(model_id)
    except ValueError:
        return None
    name = clean_model_name(raw.get("name"), model_id)
    capabilities = _normalized_tokens(raw.get("capabilities"))
    services = aliyun_services(
        capabilities,
        raw.get("inference_metadata")
        if isinstance(raw.get("inference_metadata"), Mapping)
        else None,
        model_id=model_id,
    )
    if services and requested_service not in services:
        return None
    if not services:
        return DiscoveredModel(
            id=model_id,
            name=name,
            services=(),
            classification=Classification.UNKNOWN,
            runtime_compatibility=RuntimeCompatibility.UNKNOWN,
            reason_code="category_unconfirmed",
            source=ModelSource.REMOTE,
        )
    compatibility, reason = aliyun_runtime_compatibility(
        requested_service,
        model_id,
        capabilities=capabilities,
        inference_provider=str(raw.get("inference_provider") or ""),
    )
    model_info = raw.get("model_info")
    context_window = (
        coerce_context_window(model_info.get("context_window"))
        if isinstance(model_info, Mapping)
        else None
    )
    parameters = aliyun_parameters(
        raw,
        source_url=str(raw.get("__source_url") or ""),
        checked_at=raw.get("__checked_at") or "1970-01-01T00:00:00Z",
        kind="provider_api" if raw.get("__official") else "endpoint_api",
    )
    if raw.get("__official"):
        documented = official_parameters_for(
            provider="dashscope",
            model_id=model_id,
        )
        parameters = parameters.fill_missing(documented) if parameters else documented
    reasoning_controls = _discovery_reasoning_controls(
        raw,
        identity="dashscope",
        model_id=model_id,
        kind="provider_api" if raw.get("__official") else "endpoint_api",
        source_url=str(raw.get("__source_url") or ""),
        checked_at=raw.get("__checked_at") or "1970-01-01T00:00:00Z",
        allow_static=bool(raw.get("__official")),
    )
    return DiscoveredModel(
        id=model_id,
        name=name,
        services=services,
        classification=Classification.PROVIDER,
        runtime_compatibility=compatibility,
        reason_code=reason,
        source=ModelSource.REMOTE,
        context_window=context_window,
        parameters=parameters,
        reasoning_controls=reasoning_controls,
    )


def siliconflow_model(
    raw: Mapping[str, Any],
    service: str,
) -> DiscoveredModel | None:
    model_id = str(raw.get("id") or raw.get("model") or "").strip()
    try:
        model_id = clean_model_id(model_id)
    except ValueError:
        return None
    name = clean_model_name(raw.get("name"), model_id)
    if "rerank" in model_id.lower():
        return None
    declared_subtype = str(raw.get("sub_type") or raw.get("subtype") or "").strip().lower()
    declared_type = str(raw.get("type") or "").strip().lower()
    services: list[str] = []
    mapped = SILICONFLOW_SUBTYPE_SERVICES.get(declared_subtype)
    if mapped:
        services.append(mapped)
    if not services and declared_subtype and declared_subtype not in SILICONFLOW_SUBTYPE_SERVICES:
        # An explicit, unrecognised provider subtype is evidence that this item
        # is not necessarily in the requested category (e.g. a reranker).
        return None
    if not services:
        # The account endpoint may omit type/sub_type.  Filtered requests still
        # carry a provider-side guarantee for the five documented sub_types;
        # the adapter annotates that as request evidence below.
        for token, candidate_service in SILICONFLOW_SUBTYPE_SERVICES.items():
            if token and token in model_id.lower():
                services.append(candidate_service)
    if not services and declared_type in {"text", "image", "audio", "video"}:
        services.extend(_guess_siliconflow_services(model_id, service))
    if service not in services:
        if not services:
            services.append(service) if _is_siliconflow_filter_trusted(service) else None
        if service not in services:
            return None
    compatibility, reason = siliconflow_runtime_compatibility(service, model_id)
    parameters = (
        generic_parameters(
            raw,
            kind="provider_api" if is_official_provider_host("siliconflow", str(raw.get("__source_url") or "")) else "endpoint_api",
            source_url=str(raw.get("__source_url") or ""),
            checked_at=raw.get("__checked_at") or "1970-01-01T00:00:00Z",
        )
    )
    reasoning_controls = _discovery_reasoning_controls(
        raw,
        identity="siliconflow",
        model_id=model_id,
        kind="provider_api"
        if is_official_provider_host("siliconflow", str(raw.get("__source_url") or ""))
        else "endpoint_api",
        source_url=str(raw.get("__source_url") or ""),
        checked_at=raw.get("__checked_at") or "1970-01-01T00:00:00Z",
        allow_static=False,
    )
    return DiscoveredModel(
        id=model_id,
        name=name,
        services=tuple(dict.fromkeys(services)),
        classification=Classification.PROVIDER,
        runtime_compatibility=compatibility,
        reason_code=reason,
        source=ModelSource.REMOTE,
        parameters=parameters,
        reasoning_controls=reasoning_controls,
    )


def _is_siliconflow_filter_trusted(service: str) -> bool:
    # These categories are requested with a documented exact sub_type, so an
    # item returned by that filtered request has provider evidence.
    return service in {"llm", "embedding", "stt", "imagegen", "videogen"}


def _guess_siliconflow_services(model_id: str, requested: str) -> list[str]:
    lowered = model_id.lower()
    if "rerank" in lowered:
        return []
    if requested in {"tts", "vision"}:
        # There is no exact documented filter for these; do not claim a
        # category from an id alone.
        return []
    return [requested]


def siliconflow_runtime_compatibility(
    service: str, model_id: str
) -> tuple[RuntimeCompatibility, str | None]:
    if service in {"llm", "embedding", "stt", "imagegen"}:
        return RuntimeCompatibility.SUPPORTED, None
    if service == "tts":
        if model_id.startswith("FunAudioLLM/CosyVoice"):
            return RuntimeCompatibility.SUPPORTED, None
        return RuntimeCompatibility.UNSUPPORTED, "siliconflow_tts_model_unverified"
    if service == "vision":
        if any(token in model_id.lower() for token in ("qwen-vl", "qwen2.5-vl", "qwen3-vl")):
            return RuntimeCompatibility.SUPPORTED, None
        return RuntimeCompatibility.UNKNOWN, "siliconflow_vision_capability_not_exposed"
    if service == "videogen":
        return RuntimeCompatibility.UNSUPPORTED, "video_adapter_not_available"
    return RuntimeCompatibility.UNKNOWN, "unsupported_service"


_OPENAI_EMBEDDING = re.compile(r"^(text-embedding|embedding-)", re.I)
_OPENAI_STT = re.compile(r"(whisper|gpt-4o.*transcribe|gpt-4o-mini-transcribe)", re.I)
_OPENAI_TTS = re.compile(r"(^tts-|gpt-4o.*tts)", re.I)
_OPENAI_IMAGE = re.compile(r"^(dall-e|gpt-image)", re.I)
_OPENAI_VIDEO = re.compile(r"^sora", re.I)
_OPENAI_LLM = re.compile(r"^(gpt-|o1|o3|o4|chatgpt)", re.I)


def generic_services_for_model(model_id: str, binding: str) -> tuple[str, ...]:
    """Return only categories with provider-specific evidence.

    The OpenAI binding has a small, well-known model family map.  A custom
    OpenAI-compatible endpoint has no such evidence, so it stays unknown.
    """

    canonical = binding.strip().lower().replace("-", "_")
    if canonical not in {"openai", "azure_openai", "openai_compatible"}:
        return ()
    if _OPENAI_EMBEDDING.search(model_id):
        return ("embedding",)
    if _OPENAI_STT.search(model_id):
        return ("stt",)
    if _OPENAI_TTS.search(model_id):
        return ("tts",)
    if _OPENAI_IMAGE.search(model_id):
        return ("imagegen",)
    if _OPENAI_VIDEO.search(model_id):
        return ("videogen",)
    # Audio chat uses /chat/completions, not /audio/speech, and it has no
    # image input. Older small reasoning variants are text-only as well.
    # https://developers.openai.com/api/docs/models/gpt-4o-audio-preview
    # https://developers.openai.com/api/docs/models/o3-mini
    if "audio" in model_id.lower() or "realtime" in model_id.lower():
        return ("llm",)
    if re.match(r"^(o3-mini|o1-mini|o1-preview)(?:-|$)", model_id, re.I):
        return ("llm",)
    if _OPENAI_LLM.search(model_id):
        # A small source-backed multimodal family map.  The OpenAI /models
        # endpoint carries no capability field, so only these known families
        # are additionally offered for the vision service.
        if re.match(r"^(gpt-4o|gpt-4\.1|gpt-5|o[134])", model_id, re.I):
            return ("llm", "vision")
        return ("llm",)
    return ()


def generic_runtime_compatibility(
    service: str,
    services: tuple[str, ...],
    *,
    binding: str,
    adapter: str,
    model_id: str = "",
) -> tuple[RuntimeCompatibility, str | None]:
    if (
        binding.lower().replace("-", "_") in {"openai", "azure_openai", "openai_compatible"}
        and "realtime" in model_id.lower()
    ):
        return RuntimeCompatibility.UNSUPPORTED, "realtime_protocol_unsupported"
    if service not in services:
        return RuntimeCompatibility.UNKNOWN, "category_unconfirmed"
    if adapter == "ollama":
        if service in {"llm", "embedding"}:
            return RuntimeCompatibility.SUPPORTED, None
        if service == "vision":
            return RuntimeCompatibility.UNKNOWN, "ollama_capability_not_exposed"
        return RuntimeCompatibility.UNSUPPORTED, "ollama_adapter_not_available"
    if service == "videogen":
        return RuntimeCompatibility.UNSUPPORTED, "video_adapter_not_available"
    if service == "stt":
        return RuntimeCompatibility.SUPPORTED, None
    if service in {"llm", "embedding", "tts", "imagegen", "vision"}:
        return RuntimeCompatibility.SUPPORTED, None
    return RuntimeCompatibility.UNKNOWN, "unsupported_service"


_OFFICIAL_HOSTS = {
    "openai": ("api.openai.com",),
    "deepseek": ("api.deepseek.com",),
    "openrouter": ("openrouter.ai",),
    "mistral": ("api.mistral.ai",),
    "groq": ("api.groq.com",),
    "siliconflow": ("api.siliconflow.cn", "api.siliconflow.com"),
    "anthropic": ("api.anthropic.com",),
    "gemini": ("generativelanguage.googleapis.com",),
    "zhipu": ("open.bigmodel.cn",),
    "moonshot": ("api.moonshot.cn",),
    "minimax": ("api.minimax.io", "api.minimaxi.com"),
    "stepfun": ("api.stepfun.com",),
    "xiaomi_mimo": ("api.xiaomimimo.com",),
    "nvidia_nim": ("integrate.api.nvidia.com",),
    "qianfan": ("qianfan.baidubce.com",),
    "volcengine": ("ark.cn-beijing.volces.com",),
    "byteplus": ("ark.ap-southeast.bytepluses.com",),
    "aihubmix": ("aihubmix.com",),
    "atlascloud": ("api.atlascloud.ai",),
    "novita": ("api.novita.ai",),
    "orcarouter": ("api.orcarouter.ai",),
    "edenai": ("api.edenai.run",),
}


def is_official_provider_host(binding: str, base_url: str) -> bool:
    """Only a known host makes the endpoint's fields provider_api evidence."""

    from .provider_policy import provider_identity

    identity = provider_identity(binding, "llm")
    host = (urlsplit(base_url.strip()).hostname or "").lower()
    if not host or "/" in host:
        return False
    for suffix in _OFFICIAL_HOSTS.get(identity, ()):
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def _discovery_reasoning_controls(
    raw: Mapping[str, Any],
    *,
    identity: str,
    model_id: str,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
    allow_static: bool,
):
    explicit = discoverable_controls(
        identity,
        model_id,
        raw,
        source_url=source_url,
        checked_at=checked_at,
        kind=kind,
    )
    if explicit is not None:
        return explicit
    return controls_for(identity, model_id) if allow_static else None


def _structured_parameters(
    raw: Mapping[str, Any],
    *,
    identity: str,
    kind: str,
    source_url: str,
    checked_at: datetime | str,
):
    if identity == "deepseek":
        return deepseek_parameters(raw, source_url=source_url, checked_at=checked_at, kind=kind)
    if identity == "openrouter":
        value = openrouter_parameters(raw, source_url=source_url, checked_at=checked_at)
        return value
    if identity == "mistral":
        return mistral_parameters(raw, source_url=source_url, checked_at=checked_at)
    if identity == "groq":
        return groq_parameters(raw, source_url=source_url, checked_at=checked_at)
    return generic_parameters(
        raw,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
    )


def generic_model(
    raw: Mapping[str, Any],
    service: str,
    *,
    binding: str,
    adapter: str,
    provider_declared: bool,
    base_url: str = "",
    source_url: str = "",
    checked_at: datetime | str = "1970-01-01T00:00:00Z",
) -> DiscoveredModel | None:
    model_id = str(raw.get("id") or raw.get("model") or raw.get("name") or "").strip()
    try:
        model_id = clean_model_id(model_id)
    except ValueError:
        return None
    name = clean_model_name(raw.get("name") or raw.get("display_name"), model_id)
    declared_services = _normalized_tokens(raw.get("services"))
    if not declared_services:
        raw_metadata = raw.get("metadata")
        if isinstance(raw_metadata, Mapping):
            declared_services = _normalized_tokens(raw_metadata.get("services"))
    services = tuple(
        item
        for item in declared_services
        if item in {"llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"}
    )
    if not services:
        services = generic_services_for_model(model_id, binding)
    identity = binding.strip().lower().replace("-", "_")
    official = is_official_provider_host(binding, base_url)
    kind = "provider_api" if official else "endpoint_api"
    parameters = _structured_parameters(
        raw,
        identity=identity,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
    )
    if parameters is not None and not official:
        parameters = replace(parameters, provenance={
            key: replace(source, kind="endpoint_api")
            for key, source in parameters.provenance.items()
        })
    if official:
        documented = official_parameters_for(provider=identity, model_id=model_id)
        parameters = parameters.fill_missing(documented) if parameters else documented
    reasoning_controls = _discovery_reasoning_controls(
        raw,
        identity=identity,
        model_id=model_id,
        kind=kind,
        source_url=source_url,
        checked_at=checked_at,
        allow_static=official,
    )
    if parameters is not None and not services:
        values = parameters.values
        if service == "embedding" and (
            values.get("default_dimensions") or values.get("supported_dimensions")
        ):
            services = ("embedding",)
        else:
            outputs = tuple(values.get("output_modalities") or ())
            inputs = tuple(values.get("input_modalities") or ())
            if "text" in outputs:
                services = ("llm",) if "image" not in inputs else ("llm", "vision")
    if service == "embedding" and parameters is None and official:
        parameters = embedding_parameters(
            raw,
            kind=kind,
            source_url=source_url,
            checked_at=checked_at,
        )
    classification = (
        Classification.PROVIDER
        if declared_services
        else Classification.CURATED
        if services
        else Classification.UNKNOWN
    )
    if provider_declared or official:
        classification = Classification.PROVIDER
    compatibility, reason = generic_runtime_compatibility(
        service,
        services,
        binding=binding,
        adapter=adapter,
        model_id=model_id,
    )
    if not services:
        compatibility, reason = RuntimeCompatibility.UNKNOWN, "category_unconfirmed"
    context_window = (
        parameters.context_window
        if parameters is not None and parameters.context_window
        else coerce_context_window(
            raw.get("context_window")
            or raw.get("context_length")
            or raw.get("max_context_length")
        )
    )
    return DiscoveredModel(
        id=model_id,
        name=name,
        services=services,
        classification=classification,
        runtime_compatibility=compatibility,
        reason_code=reason,
        source=ModelSource.REMOTE,
        context_window=context_window,
        parameters=parameters,
        reasoning_controls=reasoning_controls,
    )


def _with_metadata(
    model: DiscoveredModel,
    parameters,
    reasoning_controls=None,
) -> DiscoveredModel:
    controls = reasoning_controls if reasoning_controls is not None else model.reasoning_controls
    if parameters is None and controls is None:
        return model
    context = parameters.context_window if parameters is not None else None
    return DiscoveredModel(
        id=model.id,
        name=model.name,
        services=model.services,
        classification=model.classification,
        runtime_compatibility=model.runtime_compatibility,
        reason_code=model.reason_code,
        source=model.source,
        callability=model.callability,
        context_window=context or model.context_window,
        parameters=parameters,
        reasoning_controls=controls,
        resource_name=model.resource_name,
        deployment_mapping_required=model.deployment_mapping_required,
    )


def anthropic_model(
    raw: Mapping[str, Any],
    service: str,
    *,
    source_url: str,
    checked_at: datetime | str,
) -> DiscoveredModel | None:
    """Native Anthropic /v1/models entry (old versions may omit metadata)."""

    model_id = str(raw.get("id") or "").strip()
    try:
        model_id = clean_model_id(model_id)
    except ValueError:
        return None
    name = clean_model_name(raw.get("display_name") or raw.get("name"), model_id)
    parameters = anthropic_parameters(
        raw, source_url=source_url, checked_at=checked_at,
        kind="provider_api" if (
            is_official_provider_host("anthropic", source_url)
            or is_official_provider_host("minimax", source_url)
        ) else "endpoint_api",
    )
    official_host = is_official_provider_host("anthropic", source_url)
    reasoning_controls = _discovery_reasoning_controls(
        raw,
        identity="anthropic",
        model_id=model_id,
        kind="provider_api" if official_host else "endpoint_api",
        source_url=source_url,
        checked_at=checked_at,
        allow_static=official_host,
    )
    capabilities = raw.get("capabilities")
    image_supported = None
    if isinstance(capabilities, Mapping):
        image = capabilities.get("image_input")
        if isinstance(image, Mapping):
            image_supported = image.get("supported")
    if service == "llm":
        services = ("llm",)
        compatibility, reason = RuntimeCompatibility.SUPPORTED, None
    elif service == "vision":
        services = ("vision",)
        if image_supported is True:
            compatibility, reason = RuntimeCompatibility.SUPPORTED, None
        elif image_supported is False:
            compatibility, reason = RuntimeCompatibility.UNSUPPORTED, "anthropic_image_input_unsupported"
        else:
            compatibility, reason = RuntimeCompatibility.UNKNOWN, "anthropic_vision_capability_not_exposed"
    else:
        return None
    model = DiscoveredModel(
        id=model_id,
        name=name,
        services=services,
        classification=Classification.PROVIDER,
        runtime_compatibility=compatibility,
        reason_code=reason,
        source=ModelSource.REMOTE,
    )
    return _with_metadata(model, parameters, reasoning_controls)


def gemini_model(
    raw: Mapping[str, Any],
    service: str,
    *,
    source_url: str,
    checked_at: datetime | str,
) -> DiscoveredModel | None:
    resource_name = str(raw.get("name") or "").strip()
    if not resource_name:
        return None
    # Only the protocol's ``models/`` prefix is removed for the compatible
    # inference id; version segments and the rest of the name stay intact.
    model_id = resource_name[7:] if resource_name.startswith("models/") else resource_name
    try:
        model_id = clean_model_id(model_id)
    except ValueError:
        return None
    name = clean_model_name(raw.get("displayName") or raw.get("name"), model_id)
    methods = {
        str(item) for item in (raw.get("supportedGenerationMethods") or []) if isinstance(item, str)
    }
    if service == "embedding":
        if "embedContent" not in methods and "batchEmbedContents" not in methods:
            return None
        compatibility, reason = RuntimeCompatibility.SUPPORTED, None
    elif service == "vision":
        if "generateContent" not in methods:
            return None
        compatibility, reason = RuntimeCompatibility.UNKNOWN, "gemini_vision_capability_not_exposed"
    else:
        if "generateContent" not in methods:
            return None
        # generateContent alone does not prove a plain text chat model: Gemini
        # also exposes audio/image generation through the same method.
        compatibility, reason = RuntimeCompatibility.UNKNOWN, "gemini_generate_content_category_unverified"
    parameters = gemini_parameters(
        raw, source_url=source_url, checked_at=checked_at,
        kind="provider_api" if is_official_provider_host("gemini", source_url) else "endpoint_api",
    )
    official_host = is_official_provider_host("gemini", source_url)
    reasoning_controls = _discovery_reasoning_controls(
        raw,
        identity="gemini",
        model_id=model_id,
        kind="provider_api" if official_host else "endpoint_api",
        source_url=source_url,
        checked_at=checked_at,
        allow_static=official_host,
    )
    if service == "embedding":
        parameters = embedding_parameters(
            raw,
            kind="provider_api" if is_official_provider_host("gemini", source_url) else "endpoint_api",
            source_url=source_url,
            checked_at=checked_at,
            fallback=parameters,
        )
        reasoning_controls = None
    model = DiscoveredModel(
        id=model_id,
        name=name,
        services=(service,),
        classification=Classification.PROVIDER,
        runtime_compatibility=compatibility,
        reason_code=reason,
        source=ModelSource.REMOTE,
        resource_name=resource_name,
    )
    return _with_metadata(model, parameters, reasoning_controls)


def azure_model(
    raw: Mapping[str, Any],
    service: str,
    *,
    source_url: str,
    checked_at: datetime | str,
) -> DiscoveredModel | None:
    model = generic_model(
        raw,
        service,
        binding="azure_openai",
        adapter="azure",
        provider_declared=False,
        base_url="https://azure.openai.example",
        source_url=source_url,
        checked_at=checked_at,
    )
    if model is None:
        return None
    return DiscoveredModel(
        id=model.id,
        name=model.name,
        services=model.services,
        classification=model.classification,
        runtime_compatibility=RuntimeCompatibility.UNKNOWN,
        reason_code="azure_deployment_mapping_required",
        source=model.source,
        callability=model.callability,
        context_window=model.context_window,
        parameters=model.parameters,
        reasoning_controls=model.reasoning_controls,
        resource_name=model.resource_name,
        deployment_mapping_required=True,
    )


def presets_for(service: str, adapter: str) -> tuple[PresetModel, ...]:
    if adapter == "siliconflow":
        return SILICONFLOW_PRESETS.get(service, ())
    if adapter == "aliyun":
        return ALIYUN_PRESETS.get(service, ())
    return ()


def preset_supported(service: str, adapter: str) -> bool:
    return bool(presets_for(service, adapter))


__all__ = [
    "ALIYUN_CAPABILITY_SERVICES",
    "ALIYUN_PRESETS",
    "ALIYUN_REALTIME_CAPABILITIES",
    "SILICONFLOW_PRESETS",
    "SILICONFLOW_SUBTYPE_SERVICES",
    "aliyun_model",
    "aliyun_runtime_compatibility",
    "anthropic_model",
    "azure_model",
    "gemini_model",
    "aliyun_services",
    "generic_model",
    "generic_runtime_compatibility",
    "generic_services_for_model",
    "preset_supported",
    "presets_for",
    "siliconflow_model",
    "siliconflow_runtime_compatibility",
]
