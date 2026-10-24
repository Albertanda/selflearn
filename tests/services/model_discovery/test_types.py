from __future__ import annotations

import pytest

from deeptutor.services.model_discovery.types import (
    CacheInfo,
    CacheState,
    Classification,
    Connection,
    DiscoveredModel,
    DiscoveryError,
    DiscoveryErrorCode,
    DiscoveryRequestError,
    DiscoveryResult,
    DiscoveryStatus,
    ModelSource,
    RuntimeCompatibility,
    append_url_path,
    canonical_endpoint,
    canonicalize_binding,
    clean_model_id,
    clean_model_name,
    hide_current_default,
    is_aliyun_official_host,
    merge_candidates,
    model_visible,
    validate_base_url,
    validate_service,
)


def test_service_enumeration_is_exact_and_search_is_rejected():
    for service in ("llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"):
        assert validate_service(service) == service
    with pytest.raises(DiscoveryRequestError) as exc:
        validate_service("search")
    assert exc.value.status_code == 422
    with pytest.raises(DiscoveryRequestError):
        validate_service("chat")


def test_connection_keeps_dotted_key_and_validates_url():
    connection = Connection.from_mapping(
        {
            "binding": "aliyun",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1?x=1",
            "api_key": "sk.a.b.c-dot",
            "extra_headers": {"X-App": "one", "X-Secret": "two"},
        }
    )
    assert connection.api_key == "sk.a.b.c-dot"
    assert connection.canonical_binding == "dashscope"
    assert connection.header_digest() == connection.header_digest()
    assert "sk.a.b.c-dot" not in str(connection.public_dict())

    for bad in (
        "ftp://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1#fragment",
        "not-a-url",
    ):
        with pytest.raises(DiscoveryRequestError):
            validate_base_url(bad)
    assert validate_base_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"


def test_model_ids_preserve_case_slash_colon_dot_dash_and_reject_control():
    assert clean_model_id("OpenAI/GPT-4.1:Mini.v2-beta") == "OpenAI/GPT-4.1:Mini.v2-beta"
    with pytest.raises(ValueError):
        clean_model_id("bad\nid")
    with pytest.raises(ValueError):
        clean_model_id("x" * 513)
    assert clean_model_name("x" * 400, "fallback") == "x" * 256
    assert clean_model_name("\x00 ", "fallback") == "fallback"


def test_canonical_urls_and_provider_hosts():
    assert canonicalize_binding("dashscope") == "dashscope"
    assert canonicalize_binding("aliyun") == "dashscope"
    assert canonicalize_binding("custom") == "custom"
    assert canonicalize_binding("vllm") == "vllm"
    assert canonicalize_binding("openai-compatible") == "custom"
    assert canonical_endpoint("HTTPS://API.Example.com:443/v1/?a=1") == "https://api.example.com/v1?a=1"
    assert append_url_path("https://api.example.com/v1?x=1", "models") == "https://api.example.com/v1/models?x=1"
    assert is_aliyun_official_host("https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    assert is_aliyun_official_host("https://ws.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    assert is_aliyun_official_host("https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1")
    assert not is_aliyun_official_host("https://proxy.example.com/compatible-mode/v1")
    assert not is_aliyun_official_host("https://evil.aliyuncs.com/compatible-mode/v1")


def test_missing_visibility_is_true_and_never_migrated():
    assert model_visible({}) is True
    assert model_visible({"visible_in_picker": True}) is True
    assert model_visible({"visible_in_picker": False}) is False


def test_hide_current_default_detects_only_saved_default():
    current = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "models": [
                            {"id": "m1", "model": "a"},
                            {"id": "m2", "model": "b"},
                        ],
                    }
                ],
            }
        }
    }
    proposed = {
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "models": [
                            {"id": "m1", "model": "a", "visible_in_picker": False},
                            {"id": "m2", "model": "b"},
                        ],
                    }
                ],
            }
        }
    }
    assert hide_current_default(current, proposed) == ("p1", "m1")
    proposed["services"]["llm"]["profiles"][0]["models"][0]["visible_in_picker"] = True
    assert hide_current_default(current, proposed) is None
    proposed["services"]["llm"]["profiles"][0]["models"][1]["visible_in_picker"] = False
    assert hide_current_default(current, proposed) is None


def test_merge_candidates_reuses_existing_and_keeps_alias_parameters():
    existing = [
        {"id": "stable-1", "name": "My alias", "model": "Model/A", "context_window": "99"},
    ]
    candidates = [
        {
            "id": "Model/A",
            "name": "Remote A",
            "services": ["llm"],
            "runtime_compatibility": "supported",
        },
        {
            "id": "Model/B",
            "name": "Remote B",
            "services": ["llm"],
            "runtime_compatibility": "supported",
        },
        {
            "id": "Model/C",
            "name": "Unsupported C",
            "services": ["llm"],
            "runtime_compatibility": "unsupported",
        },
    ]
    ids = iter(["stable-2", "stable-3"])
    models, added, reused = merge_candidates(
        existing,
        candidates,
        ["Model/A", "Model/B", "Model/C"],
        service="llm",
        id_factory=lambda: next(ids),
    )
    assert models[0] == existing[0]
    assert reused == ["stable-1"]
    assert added == ["stable-2"]
    assert models[1]["model"] == "Model/B"
    assert models[1]["name"] == "Remote B"
    assert "Model/C" not in {model["model"] for model in models}


def test_response_shape_and_all_statuses_serialize_safely():
    model = DiscoveredModel(
        id="qwen3-asr-flash",
        name="ASR",
        services=("stt",),
        classification=Classification.PROVIDER,
        runtime_compatibility=RuntimeCompatibility.SUPPORTED,
        source=ModelSource.PRESET,
        context_window=4096,
    )
    result = DiscoveryResult(
        service="stt",
        profile_id="p1",
        status=DiscoveryStatus.OK,
        models=(model,),
        cache=CacheInfo(state=CacheState.FRESH, fetched_at="2026-10-23T00:00:00Z"),
        complete=True,
        error=DiscoveryError(DiscoveryErrorCode.AUTH_FAILED, "bad key", False),
    )
    payload = result.to_dict()
    assert payload["schema_version"] == 1
    assert payload["models"][0]["callability"] == "not_tested"
    assert payload["models"][0]["source"] == "preset"
    assert payload["models"][0]["context_window"] == 4096
    assert payload["cache"]["state"] == "fresh"
    assert payload["error"] == {
        "code": "AUTH_FAILED",
        "message": "bad key",
        "retryable": False,
    }
