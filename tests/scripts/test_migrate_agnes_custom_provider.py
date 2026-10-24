from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from urllib import error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import migrate_agnes_custom_provider as migrate


def base_catalog(*, extra_vllm=False):
    profiles = [
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "binding": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-deepseek",
            "extra_headers": {},
            "models": [{"id": "ds-model", "name": "DeepSeek", "model": "deepseek-chat"}],
        },
        {
            "id": migrate.TARGET_PROFILE_ID,
            "name": "OpenAI",
            "binding": "vllm",
            "base_url": migrate.TARGET_BASE_URL,
            "api_key": "sk-agnes-secret",
            "api_version": "",
            "extra_headers": {"X-Route": "violet"},
            "models": [
                {
                    "id": migrate.TARGET_MODEL_ID,
                    "name": "agnes-3.0-flash",
                    "model": "agnes-3.0-flash",
                    "max_tokens": "65536",
                    "context_window": "512000",
                    "parameter_overrides": {"max_tokens": True, "context_window": True},
                }
            ],
        },
    ]
    if extra_vllm:
        profiles.append(
            {
                "id": "vllm-clean-existing",
                "name": "Local vLLM",
                "binding": "vllm",
                "base_url": "",
                "api_key": "",
                "models": [],
            }
        )
    return {
        "version": 1,
        "unknown_top_level": {"keep": True},
        "services": {
            "llm": {
                "active_profile_id": "deepseek",
                "active_model_id": "ds-model",
                "profiles": profiles,
            }
        },
    }


def test_dry_run_is_sanitized_and_preserves_ids_secrets_parameters_and_default():
    before = base_catalog()
    snapshot = deepcopy(before)
    plan = migrate.migration_plan(before)
    assert before == snapshot
    assert plan["no_op"] is False
    assert plan["created_definition"] is True
    assert plan["added_vllm_slot"] is True
    assert plan["definition_id"].startswith("cp_")
    profile = next(
        p for p in plan["catalog"]["services"]["llm"]["profiles"] if p["id"] == migrate.TARGET_PROFILE_ID
    )
    assert profile["name"] == "Agnes"
    assert profile["binding"] == "custom"
    assert profile["custom_provider_id"] == plan["definition_id"]
    assert profile["base_url"] == migrate.TARGET_BASE_URL
    assert profile["api_key"] == "sk-agnes-secret"
    assert profile["extra_headers"] == {"X-Route": "violet"}
    assert profile["models"] == before["services"]["llm"]["profiles"][1]["models"]
    assert plan["catalog"]["services"]["llm"]["active_profile_id"] == "deepseek"
    assert plan["catalog"]["services"]["llm"]["active_model_id"] == "ds-model"
    assert plan["catalog"]["unknown_top_level"] == {"keep": True}
    assert plan["catalog"]["custom_providers"] == [
        {
            "id": plan["definition_id"],
            "service": "llm",
            "binding": "custom",
            "name": "Agnes",
            "icon": {"kind": "builtin", "value": "flask"},
        }
    ]
    assert any(
        p["binding"] == "vllm"
        and p["base_url"] == ""
        and p["api_key"] == ""
        and p["models"] == []
        for p in plan["catalog"]["services"]["llm"]["profiles"]
    )
    assert "sk-agnes-secret" not in json.dumps(plan["changes"])


def test_second_plan_is_noop_and_existing_clean_vllm_is_preserved():
    first = migrate.migration_plan(base_catalog())
    second = migrate.migration_plan(first["catalog"])
    assert second["no_op"] is True
    assert second["added_vllm_slot"] is False
    assert second["changes"] == []
    assert second["catalog"] == first["catalog"]

    existing = migrate.migration_plan(base_catalog(extra_vllm=True))
    assert existing["added_vllm_slot"] is False
    vllm_profiles = [
        p
        for p in existing["catalog"]["services"]["llm"]["profiles"]
        if p["binding"] == "vllm"
    ]
    assert len(vllm_profiles) == 1
    assert vllm_profiles[0]["id"] == "vllm-clean-existing"


def test_ambiguous_or_changed_target_is_refused():
    wrong = base_catalog()
    wrong["services"]["llm"]["profiles"][1]["base_url"] = "https://evil.example/v1"
    with pytest.raises(migrate.AgnesMigrationError, match="endpoint"):
        migrate.migration_plan(wrong)
    missing = base_catalog()
    missing["services"]["llm"]["profiles"][1]["models"][0]["id"] = "other"
    with pytest.raises(migrate.AgnesMigrationError, match="model"):
        migrate.migration_plan(missing)


def test_local_credentials_are_read_only_for_the_exact_target(tmp_path: Path):
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(base_catalog()), encoding="utf-8")
    credentials = migrate.local_credentials(path)
    assert credentials == {
        "api_key": "sk-agnes-secret",
        "extra_headers": {"X-Route": "violet"},
    }
    wrong = base_catalog()
    wrong["services"]["llm"]["profiles"][1]["base_url"] = "https://evil.example/v1"
    path.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(migrate.AgnesMigrationError, match="endpoint"):
        migrate.local_credentials(path)


def test_apply_retries_one_revision_conflict_then_succeeds(tmp_path: Path, monkeypatch):
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(base_catalog()), encoding="utf-8")
    first = base_catalog()
    second = deepcopy(first)
    reads = iter([(first, "rev-1"), (second, "rev-2")])
    puts: list[dict] = []

    monkeypatch.setattr(migrate, "fetch_catalog", lambda _url: next(reads))

    def fake_http(method, url, *, payload=None, timeout=30):
        puts.append(payload)
        if len(puts) == 1:
            return 409, {"detail": {"code": "CATALOG_REVISION_CONFLICT"}}
        return 200, {"catalog": {}, "revision": "rev-3"}

    monkeypatch.setattr(migrate, "_http_json", fake_http)
    result = migrate.apply_via_api("http://127.0.0.1:8001", path)
    assert result["applied"] is True
    assert result["attempts"] == 2
    assert len(puts) == 2
    assert puts[1]["expected_revision"] == "rev-2"
    profile = next(
        p
        for p in puts[0]["catalog"]["services"]["llm"]["profiles"]
        if p["id"] == migrate.TARGET_PROFILE_ID
    )
    assert profile["api_key"] == "sk-agnes-secret"
    assert profile["extra_headers"] == {"X-Route": "violet"}


def test_apply_noop_does_not_read_or_send_real_credentials(tmp_path: Path, monkeypatch):
    path = tmp_path / "model_catalog.json"
    migrated = migrate.migration_plan(base_catalog())["catalog"]
    monkeypatch.setattr(migrate, "fetch_catalog", lambda _url: (migrated, "rev"))
    called = []
    monkeypatch.setattr(migrate, "_http_json", lambda *a, **k: called.append(True) or (200, {}))
    result = migrate.apply_via_api("http://127.0.0.1:8001", path)
    assert result["applied"] is False
    assert result["no_op"] is True
    assert called == []


def test_authentication_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr(migrate, "fetch_catalog", lambda _url: (_ for _ in ()).throw(
        migrate.AgnesMigrationError("authentication failed")
    ))
    with pytest.raises(migrate.AgnesMigrationError, match="authentication"):
        migrate.apply_via_api("http://127.0.0.1:8001", Path("missing.json"))


def test_review_retry_rereads_rotated_credentials_instead_of_overwriting_them(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    original = base_catalog()
    path.write_text(json.dumps(original))
    snapshots = iter([(original, "rev-1"), (original, "rev-2")])
    monkeypatch.setattr(migrate, "fetch_catalog", lambda _url: next(snapshots))
    sent = []

    def put(method, url, *, payload=None, **kwargs):
        sent.append(deepcopy(payload))
        if len(sent) == 1:
            rotated = base_catalog()
            rotated["services"]["llm"]["profiles"][1]["api_key"] = "rotated-secret"
            rotated["services"]["llm"]["profiles"][1]["extra_headers"] = {}
            path.write_text(json.dumps(rotated))
            return 409, {}
        return 200, {}

    monkeypatch.setattr(migrate, "_http_json", put)
    migrate.apply_via_api("http://127.0.0.1:8001", path)
    target = sent[-1]["catalog"]["services"]["llm"]["profiles"][1]
    assert target["api_key"] == "rotated-secret"
    assert target["extra_headers"] == {}


@pytest.mark.parametrize("api_url", ["https://evil.example", "http://127.0.0.1@evil.example", "http://localhost:8001/?token=x"])
def test_review_migration_refuses_nonlocal_management_endpoint(api_url, monkeypatch):
    calls = []
    monkeypatch.setattr(migrate, "_http_json", lambda *a, **k: calls.append(a) or (200, {}))
    with pytest.raises(migrate.AgnesMigrationError):
        migrate.fetch_catalog(api_url)
    assert calls == []


@pytest.mark.parametrize("binding", ["deepseek", "custom_anthropic", "openai"])
def test_review_migration_refuses_a_user_changed_protocol(binding):
    value = base_catalog()
    value["services"]["llm"]["profiles"][1]["binding"] = binding
    with pytest.raises(migrate.AgnesMigrationError, match="protocol changed"):
        migrate.migration_plan(value)
