from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import settings as settings_router
from deeptutor.services.config.model_catalog import ModelCatalogService

CP_ID = "cp_11111111-1111-4111-8111-111111111111"


def admin():
    return SimpleNamespace(id="admin-1", is_admin=True)


def user():
    return SimpleNamespace(id="user-1", is_admin=False)


def profile(profile_id="p-custom", binding="custom", name="School connection"):
    return {
        "id": profile_id,
        "name": name,
        "binding": binding,
        "custom_provider_id": CP_ID,
        "base_url": "https://school.example/v1",
        "api_key": "sk-real-school-secret",
        "api_version": "",
        "extra_headers": {"X-Route": "blue"},
        "models": [
            {
                "id": "m-custom",
                "name": "Mystery",
                "model": "school/mystery",
                "unknown_model_field": "keep",
            }
        ],
    }


def definition(**overrides):
    value = {
        "id": CP_ID,
        "service": "llm",
        "binding": "custom",
        "name": "学校网关",
        "icon": {"kind": "builtin", "value": "school"},
    }
    value.update(overrides)
    return value


def catalog_payload():
    def shell(active_profile=None, active_model=None):
        return {
            "active_profile_id": active_profile,
            "active_model_id": active_model,
            "profiles": [],
        }

    return {
        "version": 1,
        "unknown_top_level": {"keep": "me"},
        "custom_providers": [definition()],
        "services": {
            "llm": {
                "active_profile_id": "p-custom",
                "active_model_id": "m-custom",
                "profiles": [profile()],
            },
            "embedding": shell(),
            "search": {"active_profile_id": None, "profiles": []},
            "tts": shell(),
            "stt": shell(),
            "imagegen": shell(),
            "videogen": shell(),
            "vision": shell(),
        },
    }


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api/v1/settings")
    return app


@pytest.fixture()
def service(tmp_path: Path) -> ModelCatalogService:
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    return ModelCatalogService(path)


@pytest.fixture()
def client(app, service, monkeypatch):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    return TestClient(app)


def revision(client: TestClient) -> str:
    response = client.get("/api/v1/settings/catalog")
    assert response.status_code == 200, response.text
    return response.json()["revision"]


@pytest.mark.parametrize("invalid", [[], {}, 42])
def test_review_bad_service_type_is_422_and_does_not_write(client, service, invalid):
    response = client.get("/api/v1/settings/catalog").json()
    before = service.path.read_bytes()
    response["catalog"]["custom_providers"][0]["service"] = invalid
    rejected = client.put("/api/v1/settings/catalog", json={"catalog": response["catalog"], "expected_revision": response["revision"]})
    assert rejected.status_code == 422
    assert service.path.read_bytes() == before


def test_get_customizes_capabilities_and_redacts_secrets(client: TestClient):
    response = client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["custom_provider_capabilities"]["protocols"]["llm"][0]["value"] == "custom"
    assert payload["catalog"]["custom_providers"] == [definition()]
    assert payload["catalog"]["services"]["llm"]["profiles"][0]["api_key"] == "***"
    assert payload["catalog"]["services"]["llm"]["profiles"][0]["extra_headers"] == {
        "X-Route": "***"
    }
    assert "sk-real-school-secret" not in json.dumps(payload)
    assert "blue" not in json.dumps(payload)


def test_default_options_and_llm_options_use_presenter(client: TestClient):
    defaults = client.get("/api/v1/settings/default-models").json()
    llm = defaults["services"]["llm"]
    assert llm["profiles"][0]["provider"] == "custom"
    assert llm["profiles"][0]["provider_label"] == "学校网关"
    assert llm["profiles"][0]["provider_icon"] == {
        "kind": "builtin",
        "value": "school",
    }
    assert llm["profiles"][0]["custom_provider_id"] == CP_ID
    serialized = json.dumps(defaults)
    assert "sk-real-school-secret" not in serialized
    assert "school.example" not in serialized
    options = client.get("/api/v1/settings/llm-options").json()
    assert options["options"][0]["provider"] == "custom"
    assert options["options"][0]["provider_label"] == "学校网关"
    assert options["options"][0]["provider_icon"] == {
        "kind": "builtin",
        "value": "school",
    }


def test_put_accepts_custom_definition_and_keeps_secret_on_mask(client, service):
    current = client.get("/api/v1/settings/catalog").json()
    proposed = current["catalog"]
    proposed["custom_providers"][0]["name"] = "校园网关"
    proposed["custom_providers"][0]["icon"] = {"kind": "emoji", "value": "🏫"}
    proposed["services"]["llm"]["profiles"][0]["api_key"] = "***"
    response = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": proposed, "expected_revision": current["revision"]},
    )
    assert response.status_code == 200, response.text
    saved = service.load()
    assert saved["custom_providers"][0]["name"] == "校园网关"
    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "sk-real-school-secret"
    assert saved["services"]["llm"]["profiles"][0]["id"] == "p-custom"
    assert saved["services"]["llm"]["profiles"][0]["models"][0]["id"] == "m-custom"
    assert saved["services"]["llm"]["profiles"][0]["models"][0]["unknown_model_field"] == "keep"
    assert saved["services"]["llm"]["active_model_id"] == "m-custom"
    assert saved["unknown_top_level"] == {"keep": "me"}


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: p["custom_providers"][0].update({"extra": True}),
        lambda p: p["custom_providers"].append(definition(name="Another", id="cp_2")),
        lambda p: p["custom_providers"][0].update({"binding": "custom_anthropic"}),
        lambda p: p["services"]["llm"]["profiles"][0].update(
            {
                "binding": "custom_anthropic",
                "api_key": "sk-reentered",
                "extra_headers": {"X-Route": "blue"},
            }
        ),
        lambda p: p["services"]["llm"]["profiles"][0].update({"custom_provider_id": "cp_missing"}),
        lambda p: p["custom_providers"][0].update({"icon": {"kind": "image", "value": "x"}}),
    ],
)
def test_put_rejects_invalid_definitions_or_references(client, mutator):
    current = client.get("/api/v1/settings/catalog").json()
    proposed = current["catalog"]
    mutator(proposed)
    response = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": proposed, "expected_revision": current["revision"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "CUSTOM_PROVIDER_INVALID"


def test_referenced_definition_delete_is_409_and_unreferenced_delete_is_allowed(client):
    current = client.get("/api/v1/settings/catalog").json()
    proposed = current["catalog"]
    proposed["custom_providers"] = []
    rejected = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": proposed, "expected_revision": current["revision"]},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "CUSTOM_PROVIDER_REFERENCED"

    current = client.get("/api/v1/settings/catalog").json()
    proposed = current["catalog"]
    proposed["services"]["llm"]["profiles"][0].pop("custom_provider_id")
    proposed["services"]["llm"]["profiles"][0]["binding"] = "custom"
    proposed["custom_providers"] = []
    allowed = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": proposed, "expected_revision": current["revision"]},
    )
    assert allowed.status_code == 200, allowed.text


def test_put_revision_conflict_keeps_saved_catalog(client, service):
    current = client.get("/api/v1/settings/catalog").json()
    first_catalog = current["catalog"]
    first_catalog["custom_providers"][0]["name"] = "校园网关"
    first = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": first_catalog, "expected_revision": current["revision"]},
    )
    assert first.status_code == 200
    stale_catalog = first_catalog
    stale_catalog["custom_providers"][0]["name"] = "过期名字"
    second = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": stale_catalog, "expected_revision": current["revision"]},
    )
    assert second.status_code == 409
    assert service.load()["custom_providers"][0]["name"] == "校园网关"


def test_non_admin_cannot_write_or_read_catalog(client, monkeypatch):
    monkeypatch.setattr(settings_router, "get_current_user", user)
    assert client.get("/api/v1/settings/catalog").status_code == 403
    assert client.put("/api/v1/settings/catalog", json={"catalog": {}}).status_code == 403
