from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deeptutor.services.llm.reasoning_controls import (
    PROVIDER_DEFAULT_EFFORT,
    ReasoningControls,
    anthropic_reasoning_fields,
    controls_for,
    controls_for_catalog_selection,
    controls_from_effort_payload,
    dashscope_budget_for,
    discoverable_controls,
    openai_compat_reasoning_fields,
    resolve_turn_reasoning,
    responses_reasoning_fields,
    static_controls_for,
    validate_override,
)

CHECKED = "2026-10-24T00:00:00Z"


def test_deepseek_flash_and_pro_have_three_native_levels_and_official_aliases():
    for model in ("deepseek-flash", "deepseek-v4-pro"):
        controls = static_controls_for("deepseek", model)
        assert controls is not None
        assert controls.supported is True
        assert controls.wire == "deepseek"
        assert controls.levels == ("low", "high", "max")
        assert controls.default_level == "high"
        assert controls.can_disable is True
        assert controls.aliases["minimal"] == "low"
        assert controls.aliases["medium"] == "high"
        assert controls.aliases["xhigh"] == "high"
        assert controls.aliases["ultra"] == "max"


def test_minimal_is_low_not_off_and_none_is_the_only_off_semantic():
    controls = static_controls_for("deepseek", "deepseek-flash")
    assert controls is not None
    low = resolve_turn_reasoning(
        controls,
        model_default=None,
        mode="effort",
        effort="minimal",
    )
    assert low.scoped_effort == "low"
    assert low.snapshot["source"] == "alias"
    off = resolve_turn_reasoning(
        controls,
        model_default=None,
        mode="effort",
        effort="none",
    )
    assert off.scoped_effort == "none"
    assert openai_compat_reasoning_fields(
        provider="deepseek",
        model="deepseek-flash",
        effort="minimal",
    ) == {
        "reasoning_effort": "low",
        "extra_body": {"thinking": {"type": "enabled"}},
    }
    assert openai_compat_reasoning_fields(
        provider="deepseek",
        model="deepseek-flash",
        effort="none",
    ) == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_provider_default_suppresses_every_project_default():
    controls = static_controls_for("deepseek", "deepseek-flash")
    assert controls is not None
    resolved = resolve_turn_reasoning(
        controls,
        model_default="high",
        mode="provider_default",
        effort=None,
    )
    assert resolved.scoped_effort == PROVIDER_DEFAULT_EFFORT
    assert resolved.snapshot["effective"] == "provider_default"
    for effort in (PROVIDER_DEFAULT_EFFORT, None):
        assert (
            openai_compat_reasoning_fields(
                provider="deepseek",
                model="deepseek-flash",
                effort=effort,
            )
            == {}
        )
        assert (
            responses_reasoning_fields(
                provider="deepseek",
                model="deepseek-flash",
                effort=effort,
            )
            == {}
        )


def test_unknown_custom_proxy_does_not_inherit_an_official_name():
    controls = controls_for("custom", "deepseek-v4-pro")
    assert controls.supported is None
    assert (
        openai_compat_reasoning_fields(
            provider="custom",
            model="deepseek-v4-pro",
            effort="high",
        )
        == {}
    )


def test_unknown_custom_proxy_without_metadata_suppresses_saved_value():
    controls, model, _profile = controls_for_catalog_selection(
        {
            "services": {
                "llm": {
                    "active_profile_id": "p",
                    "active_model_id": "m",
                    "profiles": [
                        {
                            "id": "p",
                            "binding": "custom",
                            "models": [
                                {
                                    "id": "m",
                                    "model": "deepseek-v4-pro",
                                    "reasoning_effort": "max",
                                }
                            ],
                        }
                    ],
                }
            }
        },
        None,
    )
    assert model is not None
    resolved = resolve_turn_reasoning(
        controls,
        model_default="max",
        mode="inherit",
        effort=None,
    )
    assert resolved.scoped_effort == PROVIDER_DEFAULT_EFFORT
    assert resolved.snapshot["source"] == "unsupported_saved_value"
    with pytest.raises(ValueError):
        validate_override(controls, "effort", "high")


def test_aliyun_deepseek_versions_have_distinct_level_sets():
    new = static_controls_for("dashscope", "deepseek-v4.1-flash")
    old = static_controls_for("dashscope", "deepseek-v4-pro")
    assert new is not None and old is not None
    assert new.levels == ("low", "high", "max")
    assert old.levels == ("high", "max")
    assert old.aliases["low"] == "high"
    assert new.wire == "dashscope_deepseek_effort"
    assert openai_compat_reasoning_fields(
        provider="dashscope",
        model="deepseek-v4.1-flash",
        effort="low",
    ) == {
        "reasoning_effort": "low",
        "extra_body": {"enable_thinking": True},
    }
    assert openai_compat_reasoning_fields(
        provider="dashscope",
        model="deepseek-v4-pro",
        effort="low",
    ) == {
        "reasoning_effort": "high",
        "extra_body": {"enable_thinking": True},
    }


def test_qwen38_uses_native_effort_and_never_sends_budget():
    controls = static_controls_for("dashscope", "qwen3.8-max")
    assert controls is not None
    assert controls.levels == ("low", "medium", "xhigh")
    assert controls.default_level == "xhigh"
    assert controls.can_disable is True
    fields = openai_compat_reasoning_fields(
        provider="dashscope",
        model="qwen3.8-max",
        effort="high",
        max_tokens=4096,
    )
    assert fields == {
        "reasoning_effort": "xhigh",
        "extra_body": {"enable_thinking": True},
    }
    assert "thinking_budget" not in fields["extra_body"]


def test_qwen_old_families_use_budget_presets_with_capped_output():
    fields = openai_compat_reasoning_fields(
        provider="dashscope",
        model="qwen3.5-plus",
        effort="medium",
        max_tokens=4096,
    )
    assert "reasoning_effort" not in fields
    assert fields["extra_body"]["enable_thinking"] is True
    assert 0 < fields["extra_body"]["thinking_budget"] < 4096
    assert fields["extra_body"]["thinking_budget"] == dashscope_budget_for(
        "medium", 4096
    )


def test_anthropic_adaptive_sends_output_config_effort_and_keeps_mode_separate():
    fields = anthropic_reasoning_fields(
        model="claude-opus-5",
        effort="medium",
        max_tokens=4096,
    )
    assert fields == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
    }
    # Can't disable: none is rejected rather than silently sent as adaptive.
    controls = static_controls_for("anthropic", "claude-opus-5")
    assert controls is not None and controls.can_disable is False
    with pytest.raises(ValueError):
        validate_override(controls, "effort", "none")


def test_anthropic_legacy_budget_stays_below_max_tokens():
    fields = anthropic_reasoning_fields(
        model="claude-sonnet-4-5",
        effort="high",
        max_tokens=4096,
    )
    assert fields["thinking"]["type"] == "enabled"
    assert fields["thinking"]["budget_tokens"] < 4096
    assert anthropic_reasoning_fields(
        model="claude-sonnet-4-5",
        effort=PROVIDER_DEFAULT_EFFORT,
        max_tokens=4096,
    ) == {}


def test_gemini_25_and_3_keep_different_off_rules():
    g3 = static_controls_for("gemini", "gemini-3.6-flash")
    g25 = static_controls_for("gemini", "gemini-2.5-flash")
    assert g3 is not None and g25 is not None
    assert g3.can_disable is False
    assert "none" not in g3.levels
    assert g25.can_disable is True
    assert openai_compat_reasoning_fields(
        provider="gemini",
        model="gemini-3.6-flash",
        effort="minimal",
    ) == {"reasoning_effort": "minimal"}
    assert openai_compat_reasoning_fields(
        provider="gemini",
        model="gemini-2.5-flash",
        effort="none",
    ) == {"reasoning_effort": "none"}


def test_openai_family_is_exact_and_unknown_models_stay_unknown():
    assert controls_for("openai", "gpt-4o").supported is None
    controls = static_controls_for("openai", "gpt-5")
    assert controls is not None
    assert controls.levels == ("minimal", "low", "medium", "high")
    assert controls.can_disable is False
    assert responses_reasoning_fields(
        provider="openai", model="gpt-5", effort="high"
    ) == {"reasoning": {"effort": "high"}}
    assert responses_reasoning_fields(
        provider="openai", model="gpt-5.1", effort="none"
    ) == {"reasoning": {"effort": "none"}}


def test_metadata_narrows_levels_and_preserves_exact_source():
    metadata = {
        "schema_version": 1,
        "parameters": {},
        "reasoning_controls": {
            "supported": True,
            "control": "effort",
            "levels": ["high", "max"],
            "can_disable": True,
            "default_level": "high",
            "aliases": {"xhigh": "max"},
            "source": {
                "kind": "provider_api",
                "source_url": "https://api.deepseek.com/models",
                "checked_at": CHECKED,
            },
        },
    }
    controls = controls_for(
        "deepseek", "deepseek-flash", metadata=metadata
    )
    assert controls.levels == ("high", "max")
    assert controls.default_level == "high"
    assert controls.source is not None
    assert controls.source.kind == "provider_api"


def test_directory_effort_payload_roundtrips_and_validates():
    controls = controls_from_effort_payload(
        {"supported_levels": ["low", "high", "max"], "default_level": "high"},
        source_url="https://api.deepseek.com/models?secret=1#x",
        checked_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
        provider="deepseek",
        model="deepseek-flash",
    )
    assert controls is not None
    assert controls.levels == ("low", "high", "max")
    assert controls.source is not None
    assert controls.source.source_url == "https://api.deepseek.com/models"
    parsed = ReasoningControls.from_mapping(controls.to_dict())
    assert parsed is not None
    assert parsed.levels == controls.levels


def test_discoverable_controls_ignores_arbitrary_json_without_schema():
    assert (
        discoverable_controls(
            "deepseek",
            "deepseek-flash",
            {"effort": {"supported_levels": ["nonsense"]}},
            source_url="https://api.deepseek.com/models",
            checked_at=CHECKED,
            kind="provider_api",
        )
        is None
    )


def test_catalog_selection_resolves_by_profile_and_model_not_display_name():
    catalog = {
        "services": {
            "llm": {
                "active_profile_id": "aliyun",
                "active_model_id": "a1",
                "profiles": [
                    {
                        "id": "aliyun",
                        "name": "Aliyun",
                        "binding": "dashscope",
                        "models": [
                            {
                                "id": "a1",
                                "name": "DeepSeek Flash",
                                "model": "deepseek-v4.1-flash",
                            }
                        ],
                    },
                    {
                        "id": "official",
                        "name": "Official",
                        "binding": "deepseek",
                        "models": [
                            {
                                "id": "d1",
                                "name": "DeepSeek Flash",
                                "model": "deepseek-flash",
                            }
                        ],
                    },
                ],
            }
        }
    }
    controls, model, profile = controls_for_catalog_selection(
        catalog, {"profile_id": "official", "model_id": "d1"}
    )
    assert profile is not None and profile["id"] == "official"
    assert model is not None and model["id"] == "d1"
    assert controls.wire == "deepseek"
    assert controls.levels == ("low", "high", "max")


def test_invalid_override_is_rejected_only_after_capability_is_known():
    controls = static_controls_for("deepseek", "deepseek-flash")
    assert controls is not None
    with pytest.raises(ValueError):
        validate_override(controls, "effort", "ultra-bogus")
    with pytest.raises(ValueError):
        validate_override(ReasoningControls(), "effort", "high")


def test_official_vendor_name_on_a_proxy_does_not_inherit_static_levels():
    controls = controls_for(
        "deepseek",
        "deepseek-flash",
        base_url="https://proxy.example/v1",
    )
    assert controls.supported is None
    assert (
        openai_compat_reasoning_fields(
            provider="deepseek",
            model="deepseek-flash",
            effort="high",
            protocol="none",
        )
        == {}
    )
    official = controls_for(
        "deepseek",
        "deepseek-flash",
        base_url="https://api.deepseek.com",
    )
    assert official.supported is True


def test_binary_toggle_metadata_is_a_real_switch_not_three_fake_levels():
    metadata = {
        "schema_version": 1,
        "parameters": {},
        "reasoning_controls": {
            "supported": True,
            "control": "toggle",
            "levels": ["none", "high"],
            "can_disable": True,
            "default_level": "high",
            "aliases": {},
            "source": {
                "kind": "endpoint_api",
                "source_url": "https://school.example/v1/models",
                "checked_at": CHECKED,
            },
        },
    }
    controls = controls_for(
        "dashscope",
        "school-binary",
        metadata=metadata,
        base_url="https://school.example/v1",
    )
    assert controls.control == "toggle"
    assert controls.levels == ("none", "high")
    assert (
        openai_compat_reasoning_fields(
            provider="dashscope",
            model="school-binary",
            effort="high",
            protocol=controls.wire,
        )
        == {"extra_body": {"enable_thinking": True}}
    )
    assert (
        openai_compat_reasoning_fields(
            provider="dashscope",
            model="school-binary",
            effort="none",
            protocol=controls.wire,
        )
        == {"extra_body": {"enable_thinking": False}}
    )
