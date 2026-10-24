from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from deeptutor.services.llm.reasoning_controls import (
    ReasoningControls,
    ReasoningSource,
)
from deeptutor.services.model_discovery.cache import DiscoveryCache
from deeptutor.services.model_discovery.compatibility import generic_model
from deeptutor.services.model_discovery.metadata import (
    initial_catalog_parameters,
    validate_catalog_model_metadata,
)
from deeptutor.services.model_discovery.types import DiscoveredModel, ModelSource

CHECKED = "2026-10-24T00:00:00Z"
SOURCE = "https://api.deepseek.com/models"


def _controls() -> ReasoningControls:
    return ReasoningControls(
        supported=True,
        control="effort",
        levels=("low", "high", "max"),
        can_disable=True,
        default_level="high",
        aliases={"minimal": "low", "medium": "high", "xhigh": "high", "ultra": "max"},
        source=ReasoningSource(
            kind="provider_api",
            source_url=SOURCE,
            checked_at=CHECKED,
        ),
        wire="deepseek",
    )


def test_official_deepseek_directory_effort_survives_candidate_and_catalog_shape():
    raw = {
        "id": "deepseek-flash",
        "context_window": 1048576,
        "max_output_tokens": 393216,
        "effort": {
            "supported_levels": ["low", "high", "max"],
            "default_level": "high",
        },
    }
    model = generic_model(
        raw,
        "llm",
        binding="deepseek",
        adapter="openai_compatible",
        provider_declared=True,
        base_url="https://api.deepseek.com/v1",
        source_url=SOURCE,
        checked_at=CHECKED,
    )
    assert model is not None
    assert model.parameters is not None
    assert "effort" not in model.parameters.values
    assert model.reasoning_controls is not None
    assert model.reasoning_controls.levels == ("low", "high", "max")
    payload = model.to_dict()
    assert payload["reasoning_controls"]["default_level"] == "high"
    assert payload["reasoning_controls"]["source"]["kind"] == "provider_api"
    updates = initial_catalog_parameters(
        "llm", model.parameters, model.reasoning_controls
    )
    assert updates["provider_metadata"]["reasoning_controls"]["levels"] == [
        "low",
        "high",
        "max",
    ]
    assert updates["provider_metadata"]["parameters"]["context_window"] == 1048576


def test_proxy_without_official_host_does_not_get_static_deepseek_controls():
    model = generic_model(
        {"id": "deepseek-flash", "context_window": 8192},
        "llm",
        binding="deepseek",
        adapter="openai_compatible",
        provider_declared=True,
        base_url="https://proxy.example/v1",
        source_url="https://proxy.example/models",
        checked_at=CHECKED,
    )
    assert model is not None
    assert model.reasoning_controls is None


def test_explicit_endpoint_metadata_is_kept_with_endpoint_provenance():
    raw = {
        "id": "school-model",
        "reasoning_controls": {
            "supported": True,
            "control": "toggle",
            "levels": ["none", "high"],
            "can_disable": True,
            "default_level": "high",
            "aliases": {"minimal": "high"},
        },
    }
    model = generic_model(
        raw,
        "llm",
        binding="custom",
        adapter="openai_compatible",
        provider_declared=True,
        base_url="https://school.example/v1",
        source_url="https://school.example/models",
        checked_at=CHECKED,
    )
    assert model is not None
    # A custom connection has no known wire for a toggle; do not claim one.
    assert model.reasoning_controls is None


def test_catalog_validation_accepts_controls_without_parameters_and_rejects_bad_source():
    model = {
        "id": "m",
        "provider_metadata": {
            "schema_version": 1,
            "parameters": {},
            "reasoning_controls": _controls().to_dict(),
        },
    }
    validate_catalog_model_metadata(model)
    broken = json.loads(json.dumps(model))
    broken["provider_metadata"]["reasoning_controls"]["source"]["source_url"] = (
        "https://api.deepseek.com/models?token=secret"
    )
    with pytest.raises(ValueError):
        validate_catalog_model_metadata(broken)
    missing_source = json.loads(json.dumps(model))
    missing_source["provider_metadata"]["reasoning_controls"].pop("source")
    with pytest.raises(ValueError):
        validate_catalog_model_metadata(missing_source)


def test_cache_schema_roundtrips_controls_and_bumps_generation(tmp_path: Path):
    from deeptutor.services.model_discovery.cache import CACHE_SCHEMA_VERSION

    assert CACHE_SCHEMA_VERSION == 5
    cache = DiscoveryCache(tmp_path / "cache")
    model = DiscoveredModel(
        id="deepseek-flash",
        name="DeepSeek Flash",
        services=("llm",),
        source=ModelSource.REMOTE,
        context_window=1048576,
        reasoning_controls=_controls(),
    )
    cache.save_success(
        fingerprint="f" * 64,
        service="llm",
        models=[model],
        complete=True,
        empty=False,
    )
    loaded = cache.load("f" * 64)
    assert loaded is not None
    assert loaded.models[0].reasoning_controls is not None
    assert loaded.models[0].reasoning_controls.levels == ("low", "high", "max")
    assert loaded.models[0].reasoning_controls.source is not None
    assert loaded.models[0].reasoning_controls.source.checked_at == CHECKED


def test_initial_catalog_parameters_can_store_controls_alone():
    updates = initial_catalog_parameters("llm", None, _controls())
    assert updates["provider_metadata"]["parameters"] == {}
    assert updates["provider_metadata"]["reasoning_controls"]["supported"] is True
    assert updates["parameter_overrides"] == {
        "context_window": False,
        "max_tokens": False,
    }
