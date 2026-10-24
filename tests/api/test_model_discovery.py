from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from deeptutor.api.routers import settings as settings_router
from deeptutor.services.config.model_catalog import ModelCatalogService
from deeptutor.services.model_discovery.service import ModelDiscoveryService
from deeptutor.services.model_discovery.types import (
    DiscoveryRequestError,
    DiscoveryResult,
    DiscoveryStatus,
)


def admin():
    return SimpleNamespace(id="admin-1", is_admin=True)


def user():
    return SimpleNamespace(id="user-1", is_admin=False)


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api/v1/settings")
    return app


def client_for(app: FastAPI) -> TestClient:
    return TestClient(app)


def catalog_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "OpenAI",
                        "binding": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk.old.with.dots",
                        "api_version": "",
                        "extra_headers": {},
                        "models": [
                            {"id": "m1", "name": "Main", "model": "gpt-4.1"},
                            {"id": "m2", "name": "Second", "model": "gpt-4.1-mini"},
                        ],
                    }
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
            "stt": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "tts": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "imagegen": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "videogen": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "vision": {"active_profile_id": None, "active_model_id": None, "profiles": []},
        },
    }


def test_requires_admin(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_router, "get_current_user", user)

    async def fake_discover(**_kwargs):
        raise AssertionError("must not run")

    monkeypatch.setattr(
        settings_router,
        "get_model_discovery_service",
        lambda: SimpleNamespace(discover=fake_discover),
    )
    response = client_for(app).post(
        "/api/v1/settings/model-discovery", json={"service": "llm"}
    )
    assert response.status_code == 403


def test_search_and_unknown_service_are_422(app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    svc = ModelDiscoveryService(
        catalog_path=catalog_path,
        cache_root=tmp_path / "cache",
        owner="admin-1",
    )
    monkeypatch.setattr(settings_router, "get_model_discovery_service", lambda: svc)
    client = client_for(app)
    search = client.post(
        "/api/v1/settings/model-discovery", json={"service": "search"}
    )
    assert search.status_code == 422
    assert search.json()["error"]["code"] == "BAD_REQUEST"
    unknown = client.post(
        "/api/v1/settings/model-discovery", json={"service": "audio"}
    )
    assert unknown.status_code == 422


def test_all_seven_services_share_the_envelope(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    seen: list[str] = []

    async def fake_discover(*, service, **_kwargs):
        seen.append(service)
        return DiscoveryResult(
            service=service,
            profile_id="p1",
            status=DiscoveryStatus.OK,
            models=(),
            complete=True,
        )

    monkeypatch.setattr(
        settings_router,
        "get_model_discovery_service",
        lambda: SimpleNamespace(discover=fake_discover),
    )
    client = client_for(app)
    for service in ("llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"):
        response = client.post(
            "/api/v1/settings/model-discovery", json={"service": service}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == 1
        assert payload["service"] == service
        assert payload["status"] == "ok"
    assert seen == ["llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"]


def test_connection_payload_keeps_dotted_key_and_omits_unset_fields(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    captured: dict[str, Any] = {}

    async def fake_discover(*, service, profile_id, mode, connection):
        captured.update(
            {
                "service": service,
                "profile_id": profile_id,
                "mode": mode,
                "connection": connection,
            }
        )
        return DiscoveryResult(
            service=service, profile_id=profile_id, status=DiscoveryStatus.OK
        )

    monkeypatch.setattr(
        settings_router,
        "get_model_discovery_service",
        lambda: SimpleNamespace(discover=fake_discover),
    )
    response = client_for(app).post(
        "/api/v1/settings/model-discovery",
        json={
            "service": "stt",
            "profile_id": "profile-1",
            "mode": "refresh",
            "connection": {
                "binding": "aliyun",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "sk.a.b.c",
            },
        },
    )
    assert response.status_code == 200
    assert captured["connection"]["api_key"] == "sk.a.b.c"
    assert "api_version" not in captured["connection"]
    assert "extra_headers" not in captured["connection"]
    assert captured["mode"] == "refresh"


def test_local_errors_are_structured_and_do_not_expose_input(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    secret = "sk.secret.in.error.123"

    async def fake_discover(**_kwargs):
        raise DiscoveryRequestError(
            "The provider identity changed.",
            status_code=409,
            code="CREDENTIAL_REENTRY_REQUIRED",
        )

    monkeypatch.setattr(
        settings_router,
        "get_model_discovery_service",
        lambda: SimpleNamespace(discover=fake_discover),
    )
    response = client_for(app).post(
        "/api/v1/settings/model-discovery",
        json={
            "service": "llm",
            "connection": {"api_key": secret, "binding": "openai"},
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == {
        "code": "CREDENTIAL_REENTRY_REQUIRED",
        "message": "The provider identity changed.",
        "retryable": False,
    }
    assert secret not in response.text


def test_real_route_fetches_and_never_writes_catalog(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    before = catalog_path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps({"data": [{"id": "gpt-4.1"}]}).encode(),
            headers={"content-type": "application/json"},
        )

    svc = ModelDiscoveryService(
        catalog_path=catalog_path,
        cache_root=tmp_path / "cache",
        owner="admin-1",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    monkeypatch.setattr(settings_router, "get_model_discovery_service", lambda: svc)
    response = client_for(app).post(
        "/api/v1/settings/model-discovery",
        json={"service": "llm", "profile_id": "p1", "mode": "refresh"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["models"][0]["id"] == "gpt-4.1"
    assert payload["models"][0]["callability"] == "not_tested"
    assert catalog_path.read_bytes() == before


def test_old_fetch_models_still_restores_llm_mask(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    catalog = catalog_payload()
    current = ModelCatalogService.__new__(ModelCatalogService)
    current.load = lambda: catalog  # type: ignore[method-assign]
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: current)
    captured: dict[str, Any] = {}

    async def fake_fetch(binding, base_url, api_key):
        captured.update({"binding": binding, "base_url": base_url, "api_key": api_key})
        return ["gpt-4.1", "gpt-4.1-mini"]

    import deeptutor.services.llm.factory as factory

    monkeypatch.setattr(factory, "fetch_models", fake_fetch)
    response = client_for(app).post(
        "/api/v1/settings/fetch-models",
        json={
            "binding": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "***",
            "profile_id": "p1",
        },
    )
    assert response.status_code == 200
    assert captured["api_key"] == "sk.old.with.dots"
    assert [item["id"] for item in response.json()["models"]] == [
        "gpt-4.1",
        "gpt-4.1-mini",
    ]


def test_catalog_put_rejects_hidden_current_default_before_saving(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    before = path.read_bytes()
    proposed = catalog_payload()
    proposed["services"]["llm"]["profiles"][0]["models"][0]["visible_in_picker"] = False
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 400
    assert path.read_bytes() == before

    proposed = catalog_payload()
    proposed["services"]["llm"]["profiles"][0]["models"][1]["visible_in_picker"] = False
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 200
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["services"]["llm"]["profiles"][0]["models"][1]["visible_in_picker"] is False


def test_catalog_put_rejects_non_boolean_visibility(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    proposed = catalog_payload()
    proposed["services"]["llm"]["profiles"][0]["models"][0]["visible_in_picker"] = "false"
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 400


def test_llm_options_separates_hidden_and_reports_usable(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    catalog = catalog_payload()
    catalog["services"]["llm"]["profiles"][0]["models"][1]["visible_in_picker"] = False
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    response = client_for(app).get("/api/v1/settings/llm-options")
    assert response.status_code == 200
    payload = response.json()
    assert [item["model_id"] for item in payload["options"]] == ["m1"]
    assert [item["model_id"] for item in payload["hidden_options"]] == ["m2"]
    assert payload["has_usable_models"] is True
    assert "api_key" not in response.text


def test_provider_choices_expose_one_identifiable_aliyun_entry():
    choices = settings_router._provider_choices()
    llm = choices["llm"]
    matches = [item for item in llm if item["value"] == "dashscope"]
    assert len(matches) == 1
    assert "阿里云百炼" in matches[0]["label"]
    assert not [item for item in llm if item["value"] == "aliyun"]
    assert matches[0]["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_catalog_put_persists_valid_source_backed_parameters(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    proposed = catalog_payload()
    model = proposed["services"]["llm"]["profiles"][0]["models"][0]
    model.update(
        {
            "context_window": "1048576",
            "max_tokens": "393216",
            "provider_metadata": {
                "schema_version": 1,
                "parameters": {
                    "context_window": 1048576,
                    "max_output_tokens": 393216,
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
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
    )
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 200, response.text
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved_model = saved["services"]["llm"]["profiles"][0]["models"][0]
    assert saved_model["max_tokens"] == "393216"
    assert saved_model["provider_metadata"]["parameters"]["max_output_tokens"] == 393216


@pytest.mark.parametrize(
    "mutation",
    [
        lambda model: model.update({"max_tokens": True}),
        lambda model: model.update({"context_window": "abc"}),
        lambda model: model.update({"supported_dimensions": "1024,nope"}),
        lambda model: model.update({"parameter_overrides": {"max_tokens": "yes"}}),
        lambda model: model.update(
            {
                "provider_metadata": {
                    "schema_version": 1,
                    "parameters": {"context_window": -1},
                }
            }
        ),
        lambda model: model.update(
            {
                "provider_metadata": {
                    "schema_version": 1,
                    "parameters": {
                        "context_window": 1000,
                        "provenance": {
                            "context_window": {
                                "kind": "provider_api",
                                "source_url": "https://user:pass@example.com/models?key=1",
                                "checked_at": "2026-10-23T00:00:00Z",
                            }
                        },
                    },
                }
            }
        ),
    ],
)
def test_catalog_put_rejects_invalid_parameter_metadata_before_saving(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    before = path.read_bytes()
    proposed = catalog_payload()
    mutation(proposed["services"]["llm"]["profiles"][0]["models"][0])
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 400
    assert path.read_bytes() == before


def test_catalog_put_rejects_invalid_directory_url(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    proposed = catalog_payload()
    proposed["services"]["llm"]["profiles"][0]["model_directory_url"] = (
        "https://user:pass@example.com/models"
    )
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 400


def test_model_discovery_payload_accepts_complete_directory_url(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    captured: dict[str, Any] = {}

    class FakeService:
        async def discover(self, **kwargs):
            captured.update(kwargs)
            return DiscoveryResult(
                service="llm",
                profile_id=None,
                status=DiscoveryStatus.OK,
                models=(),
            )

    monkeypatch.setattr(
        settings_router, "get_model_discovery_service", lambda: FakeService()
    )
    response = client_for(app).post(
        "/api/v1/settings/model-discovery",
        json={
            "service": "llm",
            "mode": "refresh",
            "connection": {
                "binding": "custom",
                "base_url": "https://school.example/ai/v1",
                "api_key": "sk.fictitious",
                "model_directory_url": "https://catalog.example/ai/models?tenant=1",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert (
        captured["connection"]["model_directory_url"]
        == "https://catalog.example/ai/models?tenant=1"
    )


def test_catalog_put_requires_reentry_when_masked_key_changes_directory_origin(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(settings_router, "get_current_user", admin)
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    service = ModelCatalogService(path)
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: service)
    before = path.read_bytes()
    proposed = catalog_payload()
    profile = proposed["services"]["llm"]["profiles"][0]
    profile["api_key"] = "***"
    profile["model_directory_url"] = "https://catalog.example.test/models"
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CREDENTIAL_REENTRY_REQUIRED"
    assert path.read_bytes() == before

    # Same-origin directory path is allowed with the saved key.
    proposed = catalog_payload()
    profile = proposed["services"]["llm"]["profiles"][0]
    profile["api_key"] = "***"
    profile["model_directory_url"] = "https://api.openai.com/other/models"
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 200

    # An explicitly re-entered key permits the new origin.
    proposed = catalog_payload()
    profile = proposed["services"]["llm"]["profiles"][0]
    profile["api_key"] = "sk.brand.new"
    profile["model_directory_url"] = "https://catalog.example.test/models"
    response = client_for(app).put(
        "/api/v1/settings/catalog", json={"catalog": proposed}
    )
    assert response.status_code == 200
