"""Independent MD-R2 review regressions; metadata only, no real credentials."""

from datetime import datetime, timezone

import pytest

from deeptutor.services.model_discovery.compatibility import (
    aliyun_model,
    generic_model,
    siliconflow_model,
)
from deeptutor.services.model_discovery.metadata import (
    build_parameters,
    clean_source_url,
    generic_parameters,
    official_parameters_for,
    parameter_update_preview,
)

CHECKED = datetime(2026, 10, 24, tzinfo=timezone.utc)


def test_embedding_metadata_keeps_limits_and_dimensions_in_one_record():
    value = generic_parameters(
        {"context_window": 8192, "dimension": 1024, "supported_dimensions": [1024, 512]},
        kind="endpoint_api", source_url="https://school.example/models", checked_at=CHECKED,
    )
    assert value.values["context_window"] == 8192
    assert value.values["default_dimensions"] == 1024
    assert value.values["supported_dimensions"] == [1024, 512]
    assert value.provenance["default_dimensions"].json_path == "data[].dimension"


@pytest.mark.parametrize("provider", ["deepseek", "openrouter", "mistral", "groq"])
def test_provider_specific_shape_on_proxy_does_not_claim_official_provenance(provider):
    model = generic_model(
        {"id": "gateway-alias", "context_window": 8192, "context_length": 8192,
         "max_context_length": 8192, "max_completion_tokens": 512,
         "top_provider": {"max_completion_tokens": 512}},
        "llm", binding=provider, adapter="openai_compatible", provider_declared=False,
        base_url="https://school.example/v1", source_url="https://school.example/v1/models",
        checked_at=CHECKED,
    )
    assert model.parameters
    assert all(p.kind == "endpoint_api" for p in model.parameters.provenance.values())


def test_siliconflow_keeps_context_and_dimension_fields_together():
    model = siliconflow_model(
        {"id": "example/embed", "sub_type": "embedding", "context_window": 8192,
         "dimension": 1024, "__source_url": "https://api.siliconflow.cn/v1/models",
         "__checked_at": CHECKED}, "embedding",
    )
    assert model.parameters.values["context_window"] == 8192
    assert model.parameters.values["default_dimensions"] == 1024


@pytest.mark.parametrize("model_id,default,choices", [
    ("qwen3.7-text-embedding", 1024, [2560, 2048, 1536, 1024, 768, 512, 256]),
    ("tongyi-embedding-vision-flash-2026-03-06", 768, [768, 512, 256, 128, 64]),
])
def test_current_user_embedding_models_have_documented_defaults(model_id, default, choices):
    params = official_parameters_for(provider="dashscope", model_id=model_id)
    assert params
    assert params.values["default_dimensions"] == default
    assert params.values["supported_dimensions"] == choices
    assert params.values["supports_dimensions_parameter"] is True
    model = aliyun_model(
        {"model": model_id, "capabilities": ["TR" if model_id.startswith("qwen3.7") else "ME"],
         "model_info": {"context_window": 131072}, "__official": True,
         "__source_url": "https://dashscope.aliyuncs.com/api/v1/models", "__checked_at": CHECKED},
        "embedding", requested_service="embedding",
    )
    assert model.parameters.values["default_dimensions"] == default


@pytest.mark.parametrize("url", ["https://example.test:bad/models", "https://example.test:99999/models"])
def test_malformed_optional_metadata_url_is_ignored(url):
    assert clean_source_url(url) == ""


def test_update_parameters_can_refresh_choices_and_request_policy_without_changing_dimension():
    params = build_parameters(
        {"default_dimensions": 1024, "supported_dimensions": [1024, 512],
         "supports_dimensions_parameter": False}, kind="endpoint_api",
        source_url="https://school.example/models", checked_at=CHECKED,
    )
    existing = {"dimension": "1024", "send_dimensions": True,
                "parameter_overrides": {"dimension": False, "send_dimensions": False}}
    preview = parameter_update_preview(existing, params, service="embedding")
    assert preview["updates"]["send_dimensions"] is False
    assert preview["updates"]["supported_dimensions"] == "1024,512"
    assert preview["updates"]["provider_metadata"]["parameters"]["default_dimensions"] == 1024
    assert "dimension" not in preview["updates"]


def test_restore_automatic_mode_works_when_value_already_matches():
    params = build_parameters({"default_dimensions": 1024}, kind="endpoint_api",
                              source_url="https://school.example/models", checked_at=CHECKED)
    existing = {"dimension": "1024", "parameter_overrides": {"dimension": True}}
    preview = parameter_update_preview(existing, params, service="embedding", restore_auto=["dimension"])
    assert preview["updates"]["parameter_overrides"]["dimension"] is False


def test_dimension_request_override_is_preserved_until_explicitly_restored():
    params = build_parameters({"supports_dimensions_parameter": False}, kind="endpoint_api",
                              source_url="https://school.example/models", checked_at=CHECKED)
    existing = {"send_dimensions": True, "parameter_overrides": {"send_dimensions": True}}
    assert "send_dimensions" not in parameter_update_preview(existing, params, service="embedding")["updates"]
    restored = parameter_update_preview(existing, params, service="embedding", restore_auto=["send_dimensions"])
    assert restored["updates"]["send_dimensions"] is False


@pytest.mark.parametrize("model,default", [
    ("qwen3.7-text-embedding", 1024),
    ("tongyi-embedding-vision-flash-2026-03-06", 768),
    ("multimodal-embedding-v1", 1024),
])
def test_aliyun_connection_capabilities_agree_with_official_metadata(model, default):
    from deeptutor.services.embedding.adapters.dashscope_native import (
        DashScopeMultiModalEmbeddingAdapter,
    )

    adapter = DashScopeMultiModalEmbeddingAdapter({"model": model})
    assert adapter.get_model_info()["dimensions"] == default


@pytest.mark.parametrize("model", ["text-embedding-v4", "tongyi-embedding-vision-flash-2026-03-06"])
def test_native_embedding_respects_explicit_no_dimension_request(model):
    from deeptutor.services.embedding.adapters.base import EmbeddingRequest
    from deeptutor.services.embedding.adapters.dashscope_native import (
        DashScopeMultiModalEmbeddingAdapter,
    )

    adapter = DashScopeMultiModalEmbeddingAdapter({"model": model, "dimensions": 512, "send_dimensions": False})
    request = EmbeddingRequest(model=model, texts=["test"], dimensions=512)
    assert "dimension" not in adapter._build_parameters(request)
    assert "dimension" not in adapter._build_text_parameters(request)


def test_tongyi_vision_uses_multimodal_surface():
    from deeptutor.services.config.embedding_endpoint import dashscope_embedding_endpoint

    assert "/multimodal-embedding/" in dashscope_embedding_endpoint("tongyi-embedding-vision-flash-2026-03-06")


def test_aliyun_proxy_does_not_inherit_official_documentation_or_source_kind():
    model = aliyun_model(
        {"model": "text-embedding-v4", "capabilities": ["TR"], "model_info": {"context_window": 4096},
         "__source_url": "https://school.example/models", "__checked_at": CHECKED, "__official": False},
        "embedding", requested_service="embedding",
    )
    assert "default_dimensions" not in model.parameters.values
    assert model.parameters.provenance["context_window"].kind == "endpoint_api"


@pytest.mark.parametrize("family", ["anthropic", "gemini"])
def test_native_proxy_metadata_is_labeled_as_endpoint(family):
    from deeptutor.services.model_discovery.compatibility import anthropic_model, gemini_model

    if family == "anthropic":
        model = anthropic_model({"id": "claude-test", "max_tokens": 4096}, "llm",
                                source_url="https://school.example/models", checked_at=CHECKED)
    else:
        model = gemini_model({"name": "models/gemini-test", "outputTokenLimit": 4096,
                              "supportedGenerationMethods": ["generateContent"]}, "llm",
                             source_url="https://school.example/models", checked_at=CHECKED)
    assert model.parameters
    assert all(p.kind == "endpoint_api" for p in model.parameters.provenance.values())


def test_gemini_embedding_proxy_dimension_provenance_stays_endpoint():
    from deeptutor.services.model_discovery.compatibility import gemini_model

    model = gemini_model(
        {"name": "models/gemini-embedding-001", "inputTokenLimit": 8192,
         "supportedGenerationMethods": ["embedContent"], "default_dimensions": 512},
        "embedding", source_url="https://school.example/models", checked_at=CHECKED,
    )
    assert model.parameters.values["default_dimensions"] == 512
    assert model.parameters.provenance["default_dimensions"].kind == "endpoint_api"
