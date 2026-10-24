from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from deeptutor.services.model_discovery.service import ModelDiscoveryService
from deeptutor.services.model_discovery.types import (
    DiscoveryRequestError,
    DiscoveryStatus,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


def response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def make_catalog() -> dict[str, Any]:
    profile = {
        "id": "p-gateway",
        "name": "School gateway",
        "binding": "custom",
        "base_url": "https://school.example.test/school/ai/v1",
        "api_key": "school.fictitious.key",
        "api_version": "",
        "extra_headers": {"X-School-App": "demo"},
        "models": [
            {
                "id": "llm-existing",
                "name": "Existing",
                "model": "school/old",
                "context_window": "1234",
            }
        ],
    }
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "p-gateway",
                "active_model_id": "llm-existing",
                "profiles": [profile],
            },
            "embedding": {"active_profile_id": None, "profiles": []},
            "stt": {"active_profile_id": None, "profiles": []},
            "tts": {"active_profile_id": None, "profiles": []},
            "imagegen": {"active_profile_id": None, "profiles": []},
            "videogen": {"active_profile_id": None, "profiles": []},
            "vision": {"active_profile_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings" / "model_catalog.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(make_catalog()), encoding="utf-8")
    return path


def service(catalog_path: Path, tmp_path: Path, handler, clock: Clock | None = None):
    return ModelDiscoveryService(
        catalog_path=catalog_path,
        cache_root=tmp_path / "runtime" / "cache" / "model-discovery",
        owner="admin-1",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0)
        ),
        now=clock or Clock(),
    )


@pytest.mark.asyncio
async def test_directory_url_and_parameters_round_trip_through_cache(
    catalog_path: Path, tmp_path: Path
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(
            {
                "data": [
                    {
                        "id": "school/DeepSeek-V4",
                        "name": "DeepSeek V4",
                        "context_window": 131072,
                        "max_output_tokens": 32768,
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                    }
                ]
            }
        )

    clock = Clock()
    svc = service(catalog_path, tmp_path, handler, clock)
    directory = "https://catalog.example.test/proxy/school/ai/v1/models?tenant=alpha"
    first = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        mode="refresh",
        connection={
            "api_key": "school.fictitious.key",
            "extra_headers": {"X-School-App": "demo"},
            "model_directory_url": directory,
        },
    )
    assert first.status is DiscoveryStatus.OK
    model = first.models[0]
    assert model.parameters is not None
    assert model.parameters.values["context_window"] == 131072
    assert model.parameters.provenance["context_window"].kind == "endpoint_api"
    assert requests[0].headers["x-school-app"] == "demo"
    assert str(requests[0].url) == directory

    cached = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        connection={
            "api_key": "school.fictitious.key",
            "extra_headers": {"X-School-App": "demo"},
            "model_directory_url": directory,
        },
    )
    assert cached.cache.state.value == "fresh"
    assert cached.models[0].parameters.to_dict() == model.parameters.to_dict()
    assert len(requests) == 1
    raw = next((tmp_path / "runtime" / "cache" / "model-discovery").glob("*.json")).read_text()
    assert "school.fictitious.key" not in raw
    assert "tenant=alpha" not in raw


@pytest.mark.asyncio
async def test_directory_url_participates_in_cache_identity(catalog_path: Path, tmp_path: Path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return response({"data": [{"id": f"model-{len(calls)}"}]})

    svc = service(catalog_path, tmp_path, handler)
    first = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        mode="refresh",
        connection={
            "api_key": "school.fictitious.key",
            "extra_headers": {"X-School-App": "demo"},
            "model_directory_url": "https://a.example.test/models",
        },
    )
    second = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        mode="refresh",
        connection={
            "api_key": "school.fictitious.key",
            "extra_headers": {"X-School-App": "demo"},
            "model_directory_url": "https://b.example.test/models",
        },
    )
    assert first.models[0].id == "model-1"
    assert second.models[0].id == "model-2"
    assert len(calls) == 2
    assert len(list((tmp_path / "runtime" / "cache" / "model-discovery").glob("*.json"))) == 2


@pytest.mark.asyncio
async def test_masked_key_cross_origin_directory_change_requires_reentry(
    catalog_path: Path, tmp_path: Path
):
    def handler(request: httpx.Request) -> httpx.Response:
        return response({"data": [{"id": "safe"}]})

    svc = service(catalog_path, tmp_path, handler)
    with pytest.raises(DiscoveryRequestError) as exc:
        await svc.discover(
            service="llm",
            profile_id="p-gateway",
            mode="refresh",
            connection={
                "api_key": "***",
                "model_directory_url": "https://evil.example.test/models",
            },
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "CREDENTIAL_REENTRY_REQUIRED"

    # Same-origin directory path is not a credential boundary change.
    same_origin = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        mode="refresh",
        connection={
            "api_key": "***",
            "model_directory_url": "https://school.example.test/other/models",
        },
    )
    assert same_origin.status is DiscoveryStatus.OK

    # Explicit new credentials allow the new origin.
    reentered = await svc.discover(
        service="llm",
        profile_id="p-gateway",
        mode="refresh",
        connection={
            "api_key": "new.fictitious.key",
            "extra_headers": {"X-School-App": "demo"},
            "model_directory_url": "https://evil.example.test/models",
        },
    )
    assert reentered.status is DiscoveryStatus.OK


@pytest.mark.asyncio
async def test_old_schema_cache_is_ignored_and_refetched(catalog_path: Path, tmp_path: Path):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return response({"data": [{"id": "fresh-model", "context_window": 4096}]})

    clock = Clock()
    svc = service(catalog_path, tmp_path, handler, clock)
    first = await svc.discover(service="llm", profile_id="p-gateway", mode="refresh")
    assert first.status is DiscoveryStatus.OK
    cache_dir = tmp_path / "runtime" / "cache" / "model-discovery"
    cache_file = next(cache_dir.glob("*.json"))
    payload = json.loads(cache_file.read_text())
    payload["schema_version"] = 1
    payload["models"] = [{"id": "old-model", "name": "Old", "services": ["llm"]}]
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    second = await svc.discover(service="llm", profile_id="p-gateway")
    assert second.status is DiscoveryStatus.OK
    assert second.models[0].id == "fresh-model"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_refresh_failure_keeps_stale_parameters_and_original_checked_at(
    catalog_path: Path, tmp_path: Path
):
    state = {"fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["fail"]:
            return httpx.Response(500, content=b"{}")
        return response(
            {
                "data": [
                    {
                        "id": "model-a",
                        "context_window": 65536,
                        "max_output_tokens": 8192,
                    }
                ]
            }
        )

    clock = Clock()
    svc = service(catalog_path, tmp_path, handler, clock)
    first = await svc.discover(service="llm", profile_id="p-gateway", mode="refresh")
    checked = first.models[0].parameters.provenance["context_window"].checked_at
    clock.advance(hours=2)
    state["fail"] = True
    stale = await svc.discover(service="llm", profile_id="p-gateway", mode="refresh")
    assert stale.status is DiscoveryStatus.ERROR
    assert stale.cache.state.value == "stale"
    assert stale.models[0].parameters.provenance["context_window"].checked_at == checked
