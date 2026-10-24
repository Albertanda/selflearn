from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from deeptutor.services.model_discovery.metadata import (
    MAX_JSON_SAFE_INTEGER,
    ModelParameters,
    aliyun_parameters,
    anthropic_parameters,
    build_parameters,
    clean_source_url,
    deepseek_parameters,
    embedding_parameters,
    gemini_parameters,
    generic_parameters,
    groq_parameters,
    initial_catalog_parameters,
    mistral_parameters,
    model_override_flags,
    official_parameters_for,
    openrouter_parameters,
    parameter_update_preview,
    validate_catalog_model_metadata,
)

CHECKED = datetime(2026, 10, 24, tzinfo=timezone.utc)


def test_positive_integer_whitelist_rejects_non_numbers_and_huge_values():
    parameters = build_parameters(
        {
            "context_window": True,
            "max_input_tokens": -1,
            "max_output_tokens": 0,
            "max_reasoning_tokens": 10**20,
            "default_dimensions": 1.5,
            "supported_dimensions": [1024, True, 1024, "2048", 0, -5],
            "supports_dimensions_parameter": "yes",
            "input_modalities": ["text", "TEXT", "bogus", 4],
            "output_modalities": ["text"],
            "random_extra": 123,
        },
        kind="provider_api",
        source_url="https://api.example.com/models?key=secret#frag",
        checked_at=CHECKED,
    )
    assert parameters is not None
    values = parameters.to_dict()
    assert "context_window" not in values
    assert "max_input_tokens" not in values
    assert "max_output_tokens" not in values
    assert "max_reasoning_tokens" not in values
    assert "default_dimensions" not in values
    assert values["supported_dimensions"] == [1024, 2048]
    assert "supports_dimensions_parameter" not in values
    assert values["input_modalities"] == ["text"]
    assert "random_extra" not in values
    assert values["provenance"]["input_modalities"]["source_url"] == "https://api.example.com/models"
    assert "key=" not in json.dumps(values)
    assert clean_source_url("https://user:pass@api.example.com/models?q=1#x") == "https://api.example.com/models"


def test_deepseek_and_aliyun_structures_keep_limits_separate():
    deepseek = deepseek_parameters(
        {
            "context_window": 1048576,
            "max_output_tokens": 393216,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        source_url="https://api.deepseek.com/models",
        checked_at=CHECKED,
    )
    assert deepseek is not None
    assert deepseek.values["context_window"] == 1048576
    assert deepseek.values["max_output_tokens"] == 393216
    assert deepseek.to_dict()["context_window"] == 1048576
    assert deepseek.provenance["context_window"].json_path == "data[].context_window"

    ali = aliyun_parameters(
        {
            "model_info": {
                "context_window": 131072,
                "max_input_tokens": 98304,
                "max_output_tokens": 16384,
                "max_reasoning_tokens": None,
            }
        },
        source_url="https://dashscope.aliyuncs.com/api/v1/models",
        checked_at=CHECKED,
    )
    assert ali is not None
    assert ali.values == {
        "context_window": 131072,
        "max_input_tokens": 98304,
        "max_output_tokens": 16384,
    }


def test_openrouter_endpoint_limit_wins_and_nested_fields_are_explicit():
    params = openrouter_parameters(
        {
            "context_length": 200000,
            "top_provider": {
                "context_length": 131072,
                "max_completion_tokens": 8192,
            },
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
        },
        source_url="https://openrouter.ai/api/v1/models",
        checked_at=CHECKED,
    )
    assert params is not None
    assert params.values["context_window"] == 131072
    assert params.values["max_output_tokens"] == 8192
    assert params.values["input_modalities"] == ["text", "image"]


def test_mistral_groq_and_generic_do_not_guess_nested_values():
    mistral = mistral_parameters(
        {"max_context_length": 131072, "max_output_tokens": 16384},
        source_url="https://api.mistral.ai/v1/models",
        checked_at=CHECKED,
    )
    groq = groq_parameters(
        {"context_window": 32768, "max_completion_tokens": 4096},
        source_url="https://api.groq.com/openai/v1/models",
        checked_at=CHECKED,
    )
    generic = generic_parameters(
        {"nested": {"context_window": 999}, "context_length": 65536},
        kind="endpoint_api",
        source_url="https://school.example.test/ai/v1/models",
        checked_at=CHECKED,
    )
    assert mistral is not None and mistral.values["context_window"] == 131072
    assert groq is not None and groq.values["max_output_tokens"] == 4096
    assert generic is not None
    assert generic.values == {"context_window": 65536}
    assert generic.provenance["context_window"].kind == "endpoint_api"


def test_embedding_default_and_choices_are_distinct():
    params = embedding_parameters(
        {
            "default_dimensions": 1024,
            "supported_dimensions": [2048, 1536, 1024, 512],
            "supports_dimensions_parameter": True,
        },
        kind="provider_api",
        source_url="https://api.example.com/models",
        checked_at=CHECKED,
    )
    assert params is not None
    assert params.values["default_dimensions"] == 1024
    assert params.values["supported_dimensions"] == [2048, 1536, 1024, 512]
    assert max(params.values["supported_dimensions"]) == 2048

    choices_only = embedding_parameters(
        {"supported_dimensions": [2048, 1024]},
        kind="provider_api",
        source_url="https://api.example.com/models",
        checked_at=CHECKED,
    )
    assert choices_only is not None
    assert "default_dimensions" not in choices_only.values


def test_anthropic_and_gemini_semantics():
    anthropic = anthropic_parameters(
        {
            "max_input_tokens": 200000,
            "max_tokens": 8192,
            "capabilities": {"image_input": {"supported": True}},
        },
        source_url="https://api.anthropic.com/v1/models",
        checked_at=CHECKED,
    )
    assert anthropic is not None
    assert anthropic.values["max_output_tokens"] == 8192
    assert "context_window" not in anthropic.values
    assert anthropic.values["input_modalities"] == ["text", "image"]

    gemini = gemini_parameters(
        {"inputTokenLimit": 1048576, "outputTokenLimit": 65536},
        source_url="https://generativelanguage.googleapis.com/v1beta/models",
        checked_at=CHECKED,
    )
    assert gemini is not None
    assert gemini.values["max_input_tokens"] == 1048576
    assert "context_window" not in gemini.values
    assert gemini.values["max_output_tokens"] == 65536


def test_official_docs_are_exact_model_and_region_mode_scoped():
    flash = official_parameters_for(provider="deepseek", model_id="deepseek-flash")
    pro = official_parameters_for(provider="deepseek", model_id="deepseek-v4-pro")
    assert flash is not None and flash.values["context_window"] == 1048576
    assert flash.values["input_modalities"] == ["text", "image"]
    assert pro is not None and pro.values["input_modalities"] == ["text"]
    assert official_parameters_for(provider="deepseek", model_id="deepseek-chat") is None
    # A school gateway that happens to use the same ID does not inherit it.
    assert official_parameters_for(provider="custom", model_id="deepseek-flash") is None

    plus = official_parameters_for(provider="dashscope", model_id="qwen-plus")
    assert plus is not None
    assert plus.values["context_window"] == 1000000
    assert plus.values["max_input_tokens"] == 995904
    assert plus.values["max_output_tokens"] == 32768
    assert plus.provenance["context_window"].kind == "official_docs"

    v4 = official_parameters_for(provider="dashscope", model_id="text-embedding-v4")
    v3 = official_parameters_for(provider="dashscope", model_id="text-embedding-v3")
    assert v4 is not None and v4.values["default_dimensions"] == 1024
    assert v4.values["supported_dimensions"][0] == 2048
    assert v3 is not None and v3.values["default_dimensions"] == 1024
    # Region/mode that is not listed does not silently fall back.
    assert (
        official_parameters_for(
            provider="dashscope",
            model_id="qwen-plus",
            region="eu-central-1",
            mode="thinking",
        )
        is not None
    )  # entries are explicitly region/mode "any" (conservative common values)
    assert (
        official_parameters_for(
            provider="dashscope", model_id="qwen-plus", region="", mode="thinking"
        ).values["context_window"]
        == 1000000
    )


def test_initial_llm_and_embedding_defaults_and_manual_override_rules():
    llm_params = ModelParameters(
        values={
            "context_window": 1048576,
            "max_output_tokens": 393216,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        provenance={
            key: build_parameters(
                {"context_window": 1048576},
                kind="provider_api",
                source_url="https://api.deepseek.com/models",
                checked_at=CHECKED,
            ).provenance["context_window"]
            for key in ("context_window",)
        },
    )
    initial = initial_catalog_parameters("llm", llm_params)
    assert initial["context_window"] == "1048576"
    assert initial["max_tokens"] == "393216"
    assert initial["context_window_source"] == "official"
    assert initial["parameter_overrides"] == {
        "context_window": False,
        "max_tokens": False,
    }

    embed_params = ModelParameters(
        values={
            "default_dimensions": 1024,
            "supported_dimensions": [2048, 1024],
            "supports_dimensions_parameter": False,
        },
        provenance={
            "default_dimensions": build_parameters(
                {"default_dimensions": 1024},
                kind="official_docs",
                source_url="https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai",
                checked_at=CHECKED,
            ).provenance["default_dimensions"]
        },
    )
    embed = initial_catalog_parameters("embedding", embed_params)
    assert embed["dimension"] == "1024"
    assert embed["supported_dimensions"] == "2048,1024"
    assert embed["send_dimensions"] is False
    assert "default_dimensions" not in embed


def test_legacy_values_are_manual_clear_preserved_and_restore_is_explicit():
    legacy = {
        "id": "m1",
        "name": "Mine",
        "model": "gpt-4.1",
        "context_window": "1000000",
        "max_tokens": "512",
    }
    flags = model_override_flags(legacy)
    assert flags["context_window"] is True
    assert flags["max_tokens"] is True

    parameters = build_parameters(
        {
            "context_window": 1048576,
            "max_output_tokens": 393216,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        kind="provider_api",
        source_url="https://api.example.com/models",
        checked_at=CHECKED,
    )
    preview = parameter_update_preview(legacy, parameters, service="llm")
    assert preview["changes"] == []
    assert "context_window" not in preview["updates"]
    assert "max_tokens" not in preview["updates"]
    assert "provider_metadata" in preview["updates"]

    restored = parameter_update_preview(
        legacy,
        parameters,
        service="llm",
        restore_auto=["context_window", "max_tokens"],
    )
    assert {change["field"] for change in restored["changes"]} == {
        "context_window",
        "max_tokens",
    }
    assert restored["updates"]["context_window"] == "1048576"
    assert restored["updates"]["max_tokens"] == "393216"

    cleared = {
        "id": "m2",
        "name": "Cleared",
        "model": "gpt-4.1",
        "parameter_overrides": {"context_window": True, "max_tokens": True},
    }
    assert parameter_update_preview(cleared, parameters, service="llm")["changes"] == []


def test_catalog_validation_rejects_bad_types_but_accepts_legacy_rows():
    good = {
        "context_window": "1048576",
        "max_tokens": "393216",
        "provider_metadata": {
            "schema_version": 1,
            "parameters": {
                "context_window": 1048576,
                "max_output_tokens": 393216,
                "provenance": {
                        "context_window": {
                            "kind": "provider_api",
                            "source_url": "https://api.deepseek.com/models",
                            "checked_at": "2026-10-23T00:00:00Z",
                        },
                        "max_output_tokens": {
                            "kind": "provider_api",
                            "source_url": "https://api.deepseek.com/models",
                            "checked_at": "2026-10-23T00:00:00Z",
                        },
                        "input_modalities": {
                            "kind": "provider_api",
                            "source_url": "https://api.deepseek.com/models",
                            "checked_at": "2026-10-23T00:00:00Z",
                        },
                        "output_modalities": {
                            "kind": "provider_api",
                            "source_url": "https://api.deepseek.com/models",
                            "checked_at": "2026-10-23T00:00:00Z",
                        },
                },
            },
        },
        "parameter_overrides": {"context_window": False, "max_tokens": True},
    }
    validate_catalog_model_metadata(good)
    validate_catalog_model_metadata({"context_window": "131072"})
    for bad in (
        {"context_window": "not-a-number"},
        {"max_tokens": True},
        {"provider_metadata": {"schema_version": 2, "parameters": {}}},
        {"provider_metadata": {"schema_version": 1, "parameters": {"bogus": 1}}},
        {
            "provider_metadata": {
                "schema_version": 1,
                "parameters": {"context_window": -1},
            }
        },
        {"parameter_overrides": {"context_window": "yes"}},
        {"supported_dimensions": "1024,abc"},
        {
            "provider_metadata": {
                "schema_version": 1,
                "parameters": {"context_window": 1000},
            }
        },
        {
            "provider_metadata": {
                "schema_version": 1,
                "parameters": {
                    "context_window": 1000,
                    "max_output_tokens": 100,
                    "provenance": {
                        "context_window": {
                            "kind": "provider_api",
                            "source_url": "https://example.com/models",
                            "checked_at": "2026-10-23T00:00:00Z",
                        }
                    },
                },
            }
        },
    ):
        with pytest.raises(ValueError):
            validate_catalog_model_metadata(bad)
