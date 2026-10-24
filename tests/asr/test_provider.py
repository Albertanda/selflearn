from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from deeptutor.services.asr.contracts import (
    SILICONFLOW_MAX_AUDIO_BYTES,
    SILICONFLOW_MAX_AUDIO_SECONDS,
    UNKNOWN_MAX_CHUNK_BYTES,
    UNKNOWN_MAX_CHUNK_SECONDS,
)
from deeptutor.services.asr.media import make_silent_wav
from deeptutor.services.asr.provider import (
    AsrProviderError,
    OpenAICompatibleProvider,
    auth_headers,
    capabilities,
    transcriptions_url,
)
from deeptutor.services.voice.config import STTConfig
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode


def _config(**overrides) -> STTConfig:
    values = dict(
        model="fake-model",
        provider_name="custom",
        adapter="openai_compat",
        request_style="multipart",
        auth_style="bearer",
        api_key="sk-test-secret-key",
        base_url="https://stt.invalid/v1",
        language="zh",
    )
    values.update(overrides)
    return STTConfig(**values)


def _run(handler, config: STTConfig, path: Path, *, sleeps=None, clock=None):
    seen = []

    def factory(timeout):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def record_sleep(value: float) -> None:
        if sleeps is not None:
            sleeps.append(value)

    provider = OpenAICompatibleProvider(
        config,
        client_factory=factory,
        sleep=record_sleep,
        jitter=lambda: 0.0,
        clock=clock,
    )
    result = asyncio.run(provider.transcribe_chunk(path, language="zh"))
    return result, seen


async def _noop_sleep(value: float) -> None:
    return None


def test_capabilities_use_protocol_and_endpoint_not_display_name():
    unknown = capabilities(_config())
    assert (unknown.max_bytes, unknown.max_seconds) == (
        UNKNOWN_MAX_CHUNK_BYTES,
        UNKNOWN_MAX_CHUNK_SECONDS,
    )
    sf = capabilities(_config(provider_name="siliconflow", base_url="https://api.siliconflow.cn/v1"))
    assert (sf.max_bytes, sf.max_seconds) == (
        SILICONFLOW_MAX_AUDIO_BYTES,
        SILICONFLOW_MAX_AUDIO_SECONDS,
    )
    with pytest.raises(Exception) as excinfo:
        capabilities(_config(request_style="base64_json"))
    assert excinfo.value.code == AsrErrorCode.ASR_PROTOCOL_UNSUPPORTED


def test_url_and_auth_headers_do_not_expose_key():
    config = _config(api_version="2026-01-01", extra_headers={"X-Trace": "one"})
    assert transcriptions_url(config) == "https://stt.invalid/v1/audio/transcriptions?api-version=2026-01-01"
    headers = auth_headers(config)
    assert headers["Authorization"] == "Bearer sk-test-secret-key"
    assert headers["X-Trace"] == "one"


def test_multipart_is_streamed_with_real_headers_and_no_secret_log(tmp_path, caplog):
    audio = make_silent_wav(tmp_path / "lecture.wav", 0.2)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content
        return httpx.Response(200, text="hello transcript", headers={"content-type": "text/plain"})

    with caplog.at_level(logging.INFO):
        result, _ = _run(handler, _config(), audio)
    assert result.text == "hello transcript"
    assert captured["url"] == "https://stt.invalid/v1/audio/transcriptions"
    assert captured["headers"]["authorization"] == "Bearer sk-test-secret-key"
    assert "multipart/form-data" in captured["headers"]["content-type"]
    assert b"lecture.wav" in captured["body"]
    assert b"fake-model" in captured["body"]
    assert "sk-test-secret-key" not in caplog.text


def test_401_and_403_are_not_retried(tmp_path):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key sk-test-secret-key")

    with pytest.raises(AsrProviderError) as excinfo:
        _run(handler, _config(), audio)
    assert excinfo.value.code == AsrErrorCode.ASR_PROVIDER_AUTH
    assert len(calls) == 1
    assert "sk-test-secret-key" not in str(excinfo.value)


def test_413_is_surfaced_without_retry(tmp_path):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(413)

    with pytest.raises(AsrProviderError) as excinfo:
        _run(handler, _config(), audio)
    assert excinfo.value.code == AsrErrorCode.ASR_PROVIDER_LIMIT
    assert len(calls) == 1


def test_500_retries_at_most_three_attempts_and_stops(tmp_path):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)
    calls = []
    sleeps = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(AsrProviderError) as excinfo:
        _run(handler, _config(), audio, sleeps=sleeps)
    assert excinfo.value.code == ErrorCode.PROVIDER_UNAVAILABLE
    assert len(calls) == 3
    assert len(sleeps) == 2


def test_429_uses_retry_after_and_caps_the_wait(tmp_path):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)
    calls = []
    sleeps = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "120"})
        return httpx.Response(200, text="ok")

    result, _ = _run(handler, _config(), audio, sleeps=sleeps)
    assert result.text == "ok"
    assert sleeps == [60.0]
    assert len(calls) == 2


def test_empty_plain_text_is_a_legal_empty_transcript(tmp_path):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)

    def handler(request):
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    result, _ = _run(handler, _config(), audio)
    assert result.text == ""


@pytest.mark.parametrize("body", ['{"text": 12}', "[]", "null", "{bad"])
def test_invalid_json_is_not_reported_as_empty_success(tmp_path, body):
    audio = make_silent_wav(tmp_path / "a.wav", 0.1)

    def handler(request):
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    with pytest.raises(AsrProviderError) as excinfo:
        _run(handler, _config(), audio)
    assert excinfo.value.code == ErrorCode.INVALID_MODEL_OUTPUT
