from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from deeptutor.services.config.model_catalog import (
    CatalogRevisionConflict,
    ModelCatalogService,
    catalog_revision,
)


def _catalog():
    return {
        "version": 1,
        "legacy_key": {"keep": True},
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "P1",
                        "binding": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "secret-key",
                        "models": [
                            {"id": "m1", "name": "One", "model": "deepseek-flash"},
                            {"id": "m2", "name": "Two", "model": "deepseek-v4-pro"},
                        ],
                    }
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
            "tts": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "stt": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "imagegen": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "videogen": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "vision": {"active_profile_id": None, "active_model_id": None, "profiles": []},
        },
    }


@pytest.fixture()
def service(tmp_path: Path) -> ModelCatalogService:
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")
    return ModelCatalogService(path)


def test_revision_is_stable_for_loaded_bytes_and_changes_on_write(service):
    first = service.load()
    assert catalog_revision(first) == catalog_revision(service.load())
    service.update_checked(
        catalog_revision(first),
        lambda catalog: {**catalog, "version": 2},
    )
    assert catalog_revision(service.load()) != catalog_revision(first)


def test_threaded_default_patch_and_catalog_save_cannot_both_win(service):
    revision = catalog_revision(service.load())

    def patch_default():
        def build(catalog):
            catalog["services"]["llm"]["active_model_id"] = "m2"
            return catalog

        return service.update_checked(revision, build)

    def save_name():
        def build(catalog):
            catalog["services"]["llm"]["profiles"][0]["models"][0]["name"] = "Renamed"
            return catalog

        return service.update_checked(revision, build)

    results: list[str] = []
    conflicts: list[str] = []

    def run(fn):
        try:
            fn()
            results.append("ok")
        except CatalogRevisionConflict:
            conflicts.append("conflict")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, (patch_default, save_name)))

    assert len(results) == 1
    assert len(conflicts) == 1
    saved = service.load()
    # Whichever writer won, the API key/model list/legacy key stayed intact.
    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "secret-key"
    assert [m["id"] for m in saved["services"]["llm"]["profiles"][0]["models"]] == [
        "m1",
        "m2",
    ]
    assert saved["legacy_key"] == {"keep": True}
    if saved["services"]["llm"]["active_model_id"] == "m2":
        assert saved["services"]["llm"]["profiles"][0]["models"][0]["name"] == "One"
    else:
        assert saved["services"]["llm"]["profiles"][0]["models"][0]["name"] == "Renamed"


def test_legacy_writer_without_revision_stays_compatible_but_is_locked(service):
    saved = service.update_checked(None, lambda catalog: {**catalog, "version": 3})
    assert saved["version"] == 3
    assert service.update_checked(
        catalog_revision(saved),
        lambda catalog: {**catalog, "version": 4},
    )["version"] == 4
    with pytest.raises(CatalogRevisionConflict):
        service.update_checked(
            "not-the-current-revision",
            lambda catalog: {**catalog, "version": 5},
        )
