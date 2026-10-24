from __future__ import annotations

import pytest

from deeptutor.runtime.request_contracts import (
    ReasoningOverride,
    validate_reasoning_override,
)


def test_omitted_reasoning_override_is_inherit_for_old_clients():
    assert validate_reasoning_override(None) == {"mode": "inherit"}


@pytest.mark.parametrize(
    "value, expected",
    [
        ({"mode": "inherit"}, {"mode": "inherit"}),
        ({"mode": "provider_default"}, {"mode": "provider_default"}),
        ({"mode": "effort", "effort": "high"}, {"mode": "effort", "effort": "high"}),
        ({"mode": "inherit", "effort": ""}, {"mode": "inherit"}),
    ],
)
def test_valid_modes_normalize_without_leaking_effort(value, expected):
    assert validate_reasoning_override(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        {"mode": "effort"},
        {"mode": "effort", "effort": ""},
        {"mode": "inherit", "effort": "high"},
        {"mode": "provider_default", "effort": "max"},
        {"mode": "auto", "effort": "high"},
        {"mode": "effort", "effort": "high", "unknown": 1},
        {"effort": "high"},
        "high",
        3,
    ],
)
def test_invalid_shape_or_extra_fields_are_rejected(value):
    with pytest.raises(ValueError):
        validate_reasoning_override(value)


def test_effort_is_trimmed_and_extra_forbid_is_strict():
    parsed = ReasoningOverride.model_validate(
        {"mode": "effort", "effort": "  low "}
    )
    assert parsed.effort == "  low "
    with pytest.raises(Exception):
        ReasoningOverride.model_validate(
            {"mode": "effort", "effort": "low", "auto": True}
        )
