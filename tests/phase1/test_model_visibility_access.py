from __future__ import annotations

from deeptutor.services.model_discovery.types import (
    hide_current_default,
    model_visible,
)


def test_old_models_without_visibility_field_are_visible():
    assert model_visible({"id": "m1"}) is True
    assert model_visible({"id": "m1", "visible_in_picker": True}) is True
    assert model_visible({"id": "m1", "visible_in_picker": False}) is False


def test_hidden_current_and_proposed_defaults_are_rejected():
    current = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "models": [
                            {"id": "m1", "visible_in_picker": True},
                            {"id": "m2", "visible_in_picker": True},
                        ],
                    }
                ],
            }
        }
    }
    current_default_hidden = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "models": [
                            {"id": "m1", "visible_in_picker": False},
                            {"id": "m2", "visible_in_picker": True},
                        ],
                    }
                ],
            }
        }
    }
    assert hide_current_default(current, current_default_hidden) == ("p1", "m1")
    proposed_default_hidden = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m2",
                "profiles": [
                    {
                        "id": "p1",
                        "models": [
                            {"id": "m1", "visible_in_picker": True},
                            {"id": "m2", "visible_in_picker": False},
                        ],
                    }
                ],
            }
        }
    }
    assert hide_current_default(current, proposed_default_hidden) == ("p1", "m2")
