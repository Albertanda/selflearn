"""Independent regressions for capability resolution and vendor wire output."""

import pytest

from deeptutor.services.llm.reasoning_controls import (
    anthropic_reasoning_fields,
    budget_tokens_for,
    controls_for,
    dashscope_budget_for,
    openai_compat_reasoning_fields,
    resolve_turn_reasoning,
    responses_reasoning_fields,
    static_controls_for,
)


@pytest.mark.parametrize(
    "provider,model,level,formatter,wire_level",
    [
        ("deepseek", "deepseek-flash", "xhigh", openai_compat_reasoning_fields, "xhigh"),
        ("dashscope", "qwen3.8-max", "high", openai_compat_reasoning_fields, "high"),
        ("openai", "gpt-5", "xhigh", responses_reasoning_fields, "xhigh"),
        ("anthropic", "claude-opus-5", "minimal", anthropic_reasoning_fields, "minimal"),
    ],
)
def test_explicit_directory_native_level_reaches_wire_unchanged(
    provider, model, level, formatter, wire_level
):
    # An explicit, connection-specific API answer takes priority over the
    # bundled documentation table, including when that table defines an alias.
    controls = controls_for(
        provider,
        model,
        metadata={
            "reasoning_controls": {
                "supported": True,
                "control": "effort",
                "levels": [level],
                "can_disable": True,
                "default_level": level,
                "aliases": {},
            }
        },
    )
    resolved = resolve_turn_reasoning(
        controls, model_default=None, mode="effort", effort=level
    )
    kwargs = dict(model=model, effort=resolved.scoped_effort, protocol=controls.wire)
    if provider == "anthropic":
        kwargs["max_tokens"] = 4096
    else:
        kwargs["provider"] = provider
    fields = formatter(**kwargs)
    if provider == "anthropic":
        assert fields["output_config"]["effort"] == wire_level
    elif formatter is responses_reasoning_fields:
        assert fields["reasoning"]["effort"] == wire_level
    else:
        assert fields["reasoning_effort"] == wire_level


def test_explicit_directory_can_disable_overrides_static_responses_rule():
    assert responses_reasoning_fields(
        provider="openai", model="gpt-5", effort="none", protocol="openai"
    ) == {"reasoning": {"effort": "none"}}


@pytest.mark.parametrize("limit", [1027, 1536, 2048, 4096, 8000])
def test_anthropic_budget_presets_remain_distinct_at_small_output_limits(limit):
    values = [budget_tokens_for(level, limit) for level in ("low", "medium", "high")]
    assert 1024 <= values[0] < values[1] < values[2] < limit


@pytest.mark.parametrize("limit", [4, 32, 256, 1024, 2048, 4096, 8000])
def test_qwen_budget_presets_remain_distinct_and_below_output_limit(limit):
    values = [dashscope_budget_for(level, limit) for level in ("low", "medium", "high")]
    assert 0 < values[0] < values[1] < values[2] < limit


@pytest.mark.parametrize("limit", [1024, 1025, 1026])
def test_anthropic_rejects_budget_too_small_for_three_presets(limit):
    with pytest.raises(ValueError, match="too small"):
        budget_tokens_for("high", limit)


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_qwen_rejects_budget_too_small_for_three_presets(limit):
    with pytest.raises(ValueError, match="too small"):
        dashscope_budget_for("high", limit)


def test_gemini_snapshot_controls_do_not_inherit_invalid_generic_levels():
    flash = static_controls_for("gemini", "gemini-3.8-flash")
    assert flash.levels == ("low", "medium", "high")
    assert flash.default_level == "medium"
    with pytest.raises(ValueError, match="Unsupported reasoning level"):
        resolve_turn_reasoning(flash, model_default=None, mode="effort", effort="minimal")
    image = static_controls_for("gemini", "gemini-3.1-flash-lite-image-preview")
    assert image.levels == ("minimal", "high")
    assert image.default_level == "minimal"


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-haiku-5-5"])
def test_claude_55_inherits_its_documented_medium_default(model):
    controls = static_controls_for("anthropic", model)
    resolved = resolve_turn_reasoning(controls, model_default=None, mode="inherit", effort=None)
    assert resolved.scoped_effort == "medium"


@pytest.mark.parametrize("kind,expected", [("official_docs", "medium"), ("provider_api", "high"), ("endpoint_api", "high")])
def test_only_old_documentation_fallback_is_refreshed_not_live_endpoint_metadata(kind, expected):
    controls = controls_for(
        "gemini", "gemini-3.8-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        metadata={"reasoning_controls": {
            "supported": True, "control": "effort",
            "levels": ["low", "medium", "high"], "can_disable": False,
            "default_level": "high", "aliases": {},
            "source": {"kind": kind, "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/thinking", "checked_at": "2026-10-24T00:00:00Z"},
        }},
    )
    assert controls.default_level == expected
