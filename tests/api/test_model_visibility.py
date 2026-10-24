from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.multi_user import model_access


def user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1", is_admin=False)


def test_all_hidden_granted_models_remain_usable_for_capability_and_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(model_access, "get_current_user", user)
    monkeypatch.setattr(
        model_access,
        "redacted_model_access",
        lambda _uid=None: {
            "llm": [
                {
                    "profile_id": "p1",
                    "model_id": "m1",
                    "name": "Only hidden",
                    "model": "hidden-model",
                    "source": "admin",
                    "available": True,
                    "visible_in_picker": False,
                }
            ]
        },
    )
    payload = model_access.allowed_llm_options()
    assert payload["options"] == []
    assert [item["model_id"] for item in payload["hidden_options"]] == ["m1"]
    assert payload["has_usable_models"] is True
    assert model_access.has_capability_access("llm") is True
    selection = {"profile_id": "p1", "model_id": "m1"}
    assert model_access.apply_allowed_llm_selection(selection) == selection


def test_one_hidden_and_one_visible_grant_still_lists_the_visible_one(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(model_access, "get_current_user", user)
    monkeypatch.setattr(
        model_access,
        "redacted_model_access",
        lambda _uid=None: {
            "llm": [
                {
                    "profile_id": "p1",
                    "model_id": "m1",
                    "name": "Visible",
                    "model": "visible-model",
                    "available": True,
                    "visible_in_picker": True,
                },
                {
                    "profile_id": "p1",
                    "model_id": "m2",
                    "name": "Hidden",
                    "model": "hidden-model",
                    "available": True,
                    "visible_in_picker": False,
                },
            ]
        },
    )
    payload = model_access.allowed_llm_options()
    assert [item["model_id"] for item in payload["options"]] == ["m1"]
    assert [item["model_id"] for item in payload["hidden_options"]] == ["m2"]


def test_ordinary_user_options_keep_authorised_reasoning_summary(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(model_access, "get_current_user", user)
    catalog = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "DeepSeek team key",
                        "binding": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "admin-secret",
                        "models": [
                            {
                                "id": "m1",
                                "name": "Flash",
                                "model": "deepseek-flash",
                            }
                        ],
                    }
                ],
            }
        }
    }
    monkeypatch.setattr(model_access, "admin_catalog", lambda: catalog)
    monkeypatch.setattr(
        model_access,
        "redacted_model_access",
        lambda _uid=None: {
            "llm": [
                {
                    "profile_id": "p1",
                    "model_id": "m1",
                    "name": "Flash",
                    "model": "deepseek-flash",
                    "source": "admin",
                    "available": True,
                    "visible_in_picker": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        "deeptutor.multi_user.personal_models.merge_personal_llm_profiles",
        lambda value: value,
    )
    payload = model_access.allowed_llm_options()
    option = payload["options"][0]
    assert option["provider"] == "deepseek"
    assert option["profile_name"] == "DeepSeek team key"
    assert option["reasoning_controls"]["levels"] == ["low", "high", "max"]
    serialized = str(payload)
    assert "admin-secret" not in serialized
    assert "base_url" not in serialized


def test_ordinary_user_sees_only_authorised_custom_name_and_icon(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(model_access, "get_current_user", user)
    catalog = {
        "version": 1,
        "custom_providers": [
            {
                "id": "cp_11111111-1111-4111-8111-111111111111",
                "service": "llm",
                "binding": "custom",
                "name": "学校网关",
                "icon": {"kind": "emoji", "value": "🏫"},
            }
        ],
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "Granted school key",
                        "binding": "custom",
                        "custom_provider_id": "cp_11111111-1111-4111-8111-111111111111",
                        "base_url": "https://private.school.example/v1",
                        "api_key": "admin-secret",
                        "extra_headers": {"X-Secret": "header-secret"},
                        "models": [
                            {"id": "m1", "name": "Mystery", "model": "school/mystery"}
                        ],
                    }
                ],
            }
        },
    }
    monkeypatch.setattr(model_access, "admin_catalog", lambda: catalog)
    monkeypatch.setattr(
        model_access,
        "redacted_model_access",
        lambda _uid=None: {
            "llm": [
                {
                    "profile_id": "p1",
                    "model_id": "m1",
                    "name": "Mystery",
                    "model": "school/mystery",
                    "source": "admin",
                    "available": True,
                    "visible_in_picker": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        "deeptutor.multi_user.personal_models.merge_personal_llm_profiles",
        lambda value: value,
    )
    payload = model_access.allowed_llm_options()
    option = payload["options"][0]
    assert option["provider"] == "custom"
    assert option["provider_label"] == "学校网关"
    assert option["provider_icon"] == {"kind": "emoji", "value": "🏫"}
    assert option["custom_provider_id"] == "cp_11111111-1111-4111-8111-111111111111"
    serialized = str(payload)
    assert "admin-secret" not in serialized
    assert "header-secret" not in serialized
    assert "private.school.example" not in serialized
    assert "custom_providers" not in serialized
