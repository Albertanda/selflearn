from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import settings as settings_router
from deeptutor.services.config.model_catalog import ModelCatalogService


def admin():
    return SimpleNamespace(id="admin-1", is_admin=True)


def user():
    return SimpleNamespace(id="user-1", is_admin=False)


def _service_shell(active_profile=None, active_model=None, profiles=None):
    return {
        "active_profile_id": active_profile,
        "active_model_id": active_model,
        "profiles": profiles or [],
    }


def _profile(profile_id, name, binding, models):
    return {
        "id": profile_id,
        "name": name,
        "binding": binding,
        "base_url": (
            "https://api.deepseek.com"
            if binding == "deepseek"
            else f"https://{binding}.example/v1"
        ),
        "api_key": "sk-real-secret",
        "api_version": "",
        "extra_headers": {"X-Secret": "header-secret"},
        "models": models,
    }


def catalog_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "unknown_top_level": {"keep": "me"},
        "services": {
            "llm": _service_shell(
                "p1",
                "m1",
                [
                    _profile(
                        "p1",
                        "DeepSeek",
                        "deepseek",
                        [
                            {
                                "id": "m1",
                                "name": "DeepSeek Pro",
                                "model": "deepseek-v4-pro",
                                "context_window": "1048576",
                                "unknown_model_field": "keep",
                            },
                            {
                                "id": "m2",
                                "name": "Alias Flash",
                                "model": "deepseek-v4.1-flash",
                            },
                        ],
                    ),
                    _profile(
                        "p2",
                        "School",
                        "custom",
                        [
                            {
                                "id": "m3",
                                "name": "School Pro",
                                "model": "school-pro",
                            }
                        ],
                    ),
                ],
            ),
            "embedding": _service_shell(
                "e1",
                "em1",
                [
                    _profile(
                        "e1",
                        "Embedding",
                        "openai",
                        [{"id": "em1", "name": "Embed", "model": "text-embedding-3-small"}],
                    )
                ],
            ),
            "search": _service_shell(
                "s1",
                None,
                [
                    {
                        "id": "s1",
                        "name": "Brave",
                        "provider": "brave",
                        "api_key": "search-key",
                        "models": [],
                    }
                ],
            ),
            "stt": _service_shell(
                "st1",
                "stm1",
                [
                    _profile(
                        "st1",
                        "ASR",
                        "openai",
                        [{"id": "stm1", "name": "Whisper", "model": "whisper-1"}],
                    )
                ],
            ),
            "tts": _service_shell(),
            "imagegen": _service_shell(),
            "videogen": _service_shell(),
            "vision": _service_shell(),
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
def client(app: FastAPI, service: ModelCatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    return TestClient(app)


def test_get_returns_saved_references_options_and_no_secrets(client: TestClient):
    response = client.get("/api/v1/settings/default-models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"]
    assert payload["defaults"]["llm"] == {"profile_id": "p1", "model_id": "m1"}
    assert payload["defaults"]["search"] == {"profile_id": "s1"}
    llm = payload["services"]["llm"]
    assert llm["kind"] == "model"
    assert [p["profile_id"] for p in llm["profiles"]] == ["p1", "p2"]
    serialized = json.dumps(payload)
    assert "sk-real-secret" not in serialized
    assert "header-secret" not in serialized
    assert "base_url" not in serialized


def test_patch_changes_only_active_references_and_preserves_everything_else(
    client: TestClient, service: ModelCatalogService, tmp_path: Path
):
    before = service.load()
    revision = client.get("/api/v1/settings/default-models").json()["revision"]
    response = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": revision,
            "defaults": {
                "llm": {"profile_id": "p2", "model_id": "m3"},
                "stt": {"profile_id": "st1", "model_id": "stm1"},
            },
        },
    )
    assert response.status_code == 200, response.text
    after = service.load()
    assert after["services"]["llm"]["active_profile_id"] == "p2"
    assert after["services"]["llm"]["active_model_id"] == "m3"
    assert after["services"]["stt"]["active_profile_id"] == "st1"
    assert after["services"]["stt"]["active_model_id"] == "stm1"
    # Other byte-level semantics survive: API keys, model fields, order, and
    # even a legacy top-level field this build does not interpret.
    assert after["unknown_top_level"] == before["unknown_top_level"]
    assert after["services"]["llm"]["profiles"][0]["api_key"] == "sk-real-secret"
    assert after["services"]["llm"]["profiles"][0]["extra_headers"] == {
        "X-Secret": "header-secret"
    }
    assert after["services"]["llm"]["profiles"][0]["models"][0][
        "unknown_model_field"
    ] == "keep"
    assert [p["id"] for p in after["services"]["llm"]["profiles"]] == ["p1", "p2"]
    assert after["services"]["embedding"] == before["services"]["embedding"]


def test_patch_409_on_revision_conflict_and_keeps_saved_default(
    client: TestClient, service: ModelCatalogService
):
    old_revision = client.get("/api/v1/settings/default-models").json()["revision"]
    first = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": old_revision,
            "defaults": {"llm": {"profile_id": "p2", "model_id": "m3"}},
        },
    )
    assert first.status_code == 200
    second = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": old_revision,
            "defaults": {"llm": {"profile_id": "p1", "model_id": "m1"}},
        },
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "CATALOG_REVISION_CONFLICT"
    after = service.load()
    assert after["services"]["llm"]["active_profile_id"] == "p2"
    assert after["services"]["llm"]["active_model_id"] == "m3"


def test_patch_rejects_cross_profile_missing_model_unknown_service_and_search_model(
    client: TestClient,
):
    revision = client.get("/api/v1/settings/default-models").json()["revision"]
    bad_cross = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": revision,
            "defaults": {"llm": {"profile_id": "p1", "model_id": "m3"}},
        },
    )
    assert bad_cross.status_code == 409
    bad_service = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": revision,
            "defaults": {"title": {"profile_id": "p1", "model_id": "m1"}},
        },
    )
    assert bad_service.status_code == 422
    bad_search = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": revision,
            "defaults": {"search": {"profile_id": "s1", "model_id": "m1"}},
        },
    )
    assert bad_search.status_code == 422


def test_patch_search_accepts_profile_and_duplicate_is_idempotent(
    client: TestClient, service: ModelCatalogService
):
    revision = client.get("/api/v1/settings/default-models").json()["revision"]
    first = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": revision,
            "defaults": {"search": {"profile_id": "s1"}},
        },
    )
    assert first.status_code == 200
    second = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": first.json()["revision"],
            "defaults": {"search": {"profile_id": "s1"}},
        },
    )
    assert second.status_code == 200
    assert (
        second.json()["revision"] == first.json()["revision"]
    )
    assert service.load()["services"]["search"]["active_profile_id"] == "s1"


def test_ordinary_user_is_forbidden(app: FastAPI, service: ModelCatalogService, monkeypatch):
    monkeypatch.setattr(settings_router, "get_current_user", user)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    client = TestClient(app)
    assert client.get("/api/v1/settings/default-models").status_code == 403
    assert (
        client.patch(
            "/api/v1/settings/default-models",
            json={
                "expected_revision": "x",
                "defaults": {"llm": {"profile_id": "p1", "model_id": "m1"}},
            },
        ).status_code
        == 403
    )


def test_normal_catalog_save_with_stale_revision_does_not_overwrite_default(
    client: TestClient, service: ModelCatalogService
):
    stale = client.get("/api/v1/settings/catalog").json()["revision"]
    default_patch = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": stale,
            "defaults": {"llm": {"profile_id": "p2", "model_id": "m3"}},
        },
    )
    assert default_patch.status_code == 200
    save = client.put(
        "/api/v1/settings/catalog",
        json={"catalog": catalog_payload(), "expected_revision": stale},
    )
    assert save.status_code == 409
    after = service.load()
    assert after["services"]["llm"]["active_profile_id"] == "p2"
    assert after["services"]["llm"]["active_model_id"] == "m3"


def test_normal_catalog_save_with_current_revision_keeps_patched_defaults(
    client: TestClient, service: ModelCatalogService
):
    current = client.get("/api/v1/settings/catalog").json()
    patched = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": current["revision"],
            "defaults": {"llm": {"profile_id": "p2", "model_id": "m3"}},
        },
    )
    draft = patched.json()["defaults"]
    source = catalog_payload()
    source["services"]["llm"]["active_profile_id"] = draft["llm"]["profile_id"]
    source["services"]["llm"]["active_model_id"] = draft["llm"]["model_id"]
    source["services"]["llm"]["profiles"][1]["models"][0]["name"] = "Renamed"
    save = client.put(
        "/api/v1/settings/catalog",
        json={
            "catalog": source,
            "expected_revision": patched.json()["revision"],
        },
    )
    assert save.status_code == 200, save.text
    after = service.load()
    assert after["services"]["llm"]["profiles"][1]["models"][0]["name"] == "Renamed"
    assert after["services"]["llm"]["active_model_id"] == "m3"


def test_settings_payload_exposes_safe_reasoning_controls_map(client: TestClient):
    payload = client.get("/api/v1/settings").json()
    assert payload["catalog_revision"]
    key = "p1:m1"
    assert payload["reasoning_controls"][key]["levels"] == ["low", "high", "max"]
    assert "api_key" not in json.dumps(payload["reasoning_controls"])


def test_hidden_models_are_not_offered_or_accepted_as_defaults(
    client: TestClient, service: ModelCatalogService
):
    payload = catalog_payload()
    payload["services"]["llm"]["profiles"][0]["models"][1]["visible_in_picker"] = False
    service.save(payload)
    fetched = client.get("/api/v1/settings/default-models").json()
    models = fetched["services"]["llm"]["profiles"][0]["models"]
    assert [item["model_id"] for item in models] == ["m1"]
    response = client.patch(
        "/api/v1/settings/default-models",
        json={
            "expected_revision": fetched["revision"],
            "defaults": {"llm": {"profile_id": "p1", "model_id": "m2"}},
        },
    )
    assert response.status_code == 422
