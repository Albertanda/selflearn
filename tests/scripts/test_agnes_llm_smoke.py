from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib import error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import agnes_llm_smoke as smoke


def catalog():
    return {
        "services": {
            "llm": {
                "active_profile_id": "deepseek",
                "active_model_id": "ds",
                "profiles": [
                    {
                        "id": "deepseek",
                        "name": "DeepSeek",
                        "binding": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                        "models": [{"id": "ds", "model": "deepseek-chat"}],
                    },
                    {
                        "id": smoke.TARGET_PROFILE_ID,
                        "name": "Agnes",
                        "binding": "custom",
                        "base_url": "https://apihub.agnes-ai.com/v1",
                        "api_key": "sk-agnes-secret",
                        "models": [
                            {
                                "id": smoke.TARGET_MODEL_ID,
                                "model": "agnes-3.0-flash",
                            }
                        ],
                    },
                ],
            }
        }
    }


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size=-1):
        return json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()


class Opener:
    def __init__(self):
        self.requests = []

    def open(self, req, timeout):
        self.requests.append((req, timeout))
        return Response()


def test_smoke_is_explicit_bounded_and_does_not_log_secrets_or_content():
    opener = Opener()
    result = smoke.run_smoke(
        catalog(),
        profile_id=smoke.TARGET_PROFILE_ID,
        model_id=smoke.TARGET_MODEL_ID,
        calls=2,
        opener_factory=lambda: opener,
    )
    assert result["status"] == "success"
    assert result["calls"] == 2
    assert result["default_fallback"] is False
    assert all(item["model"] == "agnes-3.0-flash" for item in result["results"])
    assert len(opener.requests) == 2
    for req, timeout in opener.requests:
        payload = json.loads(req.data)
        assert payload["model"] == "agnes-3.0-flash"
        assert payload["max_tokens"] <= 64
        assert "Synthetic" in payload["messages"][0]["content"]
        assert req.full_url == "https://apihub.agnes-ai.com/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer sk-agnes-secret"
        assert timeout == 45
    serialized = json.dumps(result)
    assert "sk-agnes-secret" not in serialized
    assert "SYNTHETIC" not in serialized
    assert "Authorization" not in serialized


def test_smoke_rejects_more_than_three_calls():
    with pytest.raises(smoke.SmokeError, match="between 1 and 3"):
        smoke.run_smoke(
            catalog(),
            profile_id=smoke.TARGET_PROFILE_ID,
            model_id=smoke.TARGET_MODEL_ID,
            calls=4,
            opener_factory=Opener,
        )


def test_smoke_refuses_other_host_model_or_missing_key():
    wrong_host = catalog()
    wrong_host["services"]["llm"]["profiles"][1]["base_url"] = "https://example.com/v1"
    with pytest.raises(smoke.SmokeError, match="host"):
        smoke.run_smoke(
            wrong_host,
            profile_id=smoke.TARGET_PROFILE_ID,
            model_id=smoke.TARGET_MODEL_ID,
            opener_factory=Opener,
        )
    wrong_model = catalog()
    wrong_model["services"]["llm"]["profiles"][1]["models"][0]["model"] = "gpt-4o"
    with pytest.raises(smoke.SmokeError, match="agnes-3.0-flash"):
        smoke.run_smoke(
            wrong_model,
            profile_id=smoke.TARGET_PROFILE_ID,
            model_id=smoke.TARGET_MODEL_ID,
            opener_factory=Opener,
        )
    no_key = catalog()
    no_key["services"]["llm"]["profiles"][1]["api_key"] = ""
    with pytest.raises(smoke.SmokeError, match="credential"):
        smoke.run_smoke(
            no_key,
            profile_id=smoke.TARGET_PROFILE_ID,
            model_id=smoke.TARGET_MODEL_ID,
            opener_factory=Opener,
        )


def test_smoke_reports_rate_limit_as_failure_without_default_fallback():
    class Limited:
        def open(self, req, timeout):
            raise error.HTTPError(req.full_url, 429, "limited", {}, None)

    result = smoke.run_smoke(
        catalog(),
        profile_id=smoke.TARGET_PROFILE_ID,
        model_id=smoke.TARGET_MODEL_ID,
        calls=1,
        opener_factory=Limited,
    )
    assert result["status"] == "failed"
    assert result["results"][0]["http_status"] == 429
    assert result["results"][0]["error_category"] == "rate_limited"
    assert result["default_fallback"] is False


@pytest.mark.parametrize("url", [
    "http://apihub.agnes-ai.com/v1",
    "https://apihub.agnes-ai.com:443@evil.example/v1",
    "https://apihub.agnes-ai.com:444/v1",
    "https://apihub.agnes-ai.com/v1?key=secret",
    "https://apihub.agnes-ai.com/v1#fragment",
    "https://apihub.agnes-ai.com/other",
])
def test_review_smoke_refuses_noncanonical_endpoint_before_attaching_credentials(url):
    value = catalog()
    value["services"]["llm"]["profiles"][1]["base_url"] = url
    opener = Opener()
    with pytest.raises(smoke.SmokeError):
        smoke.run_smoke(value, profile_id=smoke.TARGET_PROFILE_ID, model_id=smoke.TARGET_MODEL_ID, opener_factory=lambda: opener)
    assert opener.requests == []


@pytest.mark.parametrize("choices", [[{}], [{"message": {}}], [{"message": {"content": "   "}}], [{"message": {"content": None}}]])
def test_review_http_200_without_assistant_text_is_not_a_success(choices):
    class EmptyResponse(Response):
        def read(self, size=-1):
            return json.dumps({"choices": choices}).encode()

    class EmptyOpener(Opener):
        def open(self, req, timeout):
            return EmptyResponse()

    result = smoke.run_smoke(catalog(), profile_id=smoke.TARGET_PROFILE_ID, model_id=smoke.TARGET_MODEL_ID, opener_factory=EmptyOpener)
    assert result["status"] == "failed"
    assert result["results"][0]["error_category"] == "invalid_response"


def test_review_keyboard_interrupt_stops_smoke_immediately():
    class Interrupt:
        def open(self, req, timeout):
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        smoke.run_smoke(catalog(), profile_id=smoke.TARGET_PROFILE_ID, model_id=smoke.TARGET_MODEL_ID, opener_factory=Interrupt)
