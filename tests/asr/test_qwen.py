"""Qwen protocol, file bounds, voice conversion and real job integration."""

import asyncio
import base64
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import uuid
import wave

import httpx
import pytest
from starlette.datastructures import UploadFile

from deeptutor.services.asr import jobs, media, provider, transcribe
from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config
from deeptutor.services.voice import transcribe_audio
from deeptutor.services.voice.adapters import qwen_asr
from deeptutor.services.voice.base import VoiceProviderError, VoiceProviderHTTPError
from deeptutor.services.voice.config import STT_QWEN_CHAT, STTConfig
from deeptutor.subjects.errors import AsrErrorCode, ErrorCode


def _catalog():
    return {
        "services": {
            "stt": {
                "active_profile_id": "qwen",
                "active_model_id": "asr",
                "profiles": [
                    {
                        "id": "qwen",
                        "binding": "aliyun",
                        "api_key": "sk-test-secret",
                        "models": [{"id": "asr", "model": "qwen3-asr-flash"}],
                    }
                ],
            }
        }
    }


def _config():
    return resolve_stt_runtime_config(catalog=_catalog())


def _wav(seconds=0.1):
    stream = BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * round(seconds * 16000))
    return stream.getvalue()


def _response(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_media_tools_persisted_paths_and_environment_precedence(asr_runtime, tmp_path, monkeypatch):
    from deeptutor.services.path_service import get_path_service

    config_path = get_path_service().get_settings_file("asr_media")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()
    monkeypatch.delenv("SELFLEARN_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("SELFLEARN_FFPROBE_BIN", raising=False)
    config_path.write_text(json.dumps({"ffmpeg_bin": str(ffmpeg), "ffprobe_bin": str(ffprobe)}))
    assert media.resolve_tools() == media.MediaTools(str(ffmpeg), str(ffprobe))
    config_path.write_text("invalid-json")
    with pytest.raises(Exception) as caught:
        media.resolve_tools()
    assert caught.value.code == AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE
    monkeypatch.setenv("SELFLEARN_FFMPEG_BIN", str(ffmpeg))
    monkeypatch.setenv("SELFLEARN_FFPROBE_BIN", str(ffprobe))
    assert media.resolve_tools() == media.MediaTools(str(ffmpeg), str(ffprobe))


def _chunk_provider(config, handler, sleeps=None):
    async def sleep(value):
        if sleeps is not None:
            sleeps.append(value)

    return provider.OpenAICompatibleProvider(
        config,
        client_factory=lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=sleep,
        jitter=lambda: 0,
    )


def test_resolver_and_settings_supplier_entry():
    from deeptutor.api.routers.settings import _provider_choices

    cfg = _config()
    assert (cfg.provider_name, cfg.adapter, cfg.request_style) == (
        "aliyun",
        "qwen_asr",
        STT_QWEN_CHAT,
    )
    assert cfg.model == "qwen3-asr-flash"
    assert cfg.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # This is the actual source of frontend supplier dropdowns.
    payload = _provider_choices()
    assert any(p["value"] == "aliyun" for p in payload["stt"])


def test_180_second_chunk_fits_final_request_and_has_correct_language():
    audio = _wav(180)
    body = qwen_asr.build_request(audio, _config(), language="zh")
    payload = json.loads(body)
    assert len(body) < 10_000_000
    assert payload["asr_options"]["language"] == "zh"
    item = payload["messages"][0]["content"][0]
    assert item["type"] == "input_audio"
    assert base64.b64decode(item["input_audio"]["data"].split(",", 1)[1]) == audio


def test_size_checked_before_encoding_and_final_envelope_checked(monkeypatch):
    def never_encode(*args):
        raise AssertionError("oversized audio must not be encoded")

    with monkeypatch.context() as patch:
        patch.setattr(qwen_asr.base64, "b64encode", never_encode)
        with pytest.raises(qwen_asr.QwenAudioLimitError):
            qwen_asr.build_request(b"x" * (qwen_asr.QWEN_MAX_AUDIO_BYTES + 1), _config())
    with pytest.raises(qwen_asr.QwenAudioLimitError):
        qwen_asr.build_request(_wav(), replace(_config(), model="x" * 10_000_000))


@pytest.mark.parametrize("text", ["课程内容", ""])
def test_job_transport_uses_chat_endpoint_and_parses_empty_silence(tmp_path, text):
    path = media.make_silent_wav(tmp_path / "chunk.wav", 0.1)

    def handler(request):
        assert str(request.url).endswith("/compatible-mode/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer sk-test-secret"
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content)["model"] == "qwen3-asr-flash"
        return _response(text)

    result = asyncio.run(_chunk_provider(_config(), handler).transcribe_chunk(path))
    assert result.text == text


@pytest.mark.parametrize(
    "status,code,attempts",
    [
        (401, AsrErrorCode.ASR_PROVIDER_AUTH, 1),
        (403, AsrErrorCode.ASR_PROVIDER_AUTH, 1),
        (413, AsrErrorCode.ASR_PROVIDER_LIMIT, 1),
        (429, AsrErrorCode.ASR_RATE_LIMITED, 3),
        (503, ErrorCode.PROVIDER_UNAVAILABLE, 3),
    ],
)
def test_job_errors_and_retry_policy(tmp_path, caplog, status, code, attempts):
    path = media.make_silent_wav(tmp_path / "chunk.wav", 0.1)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, text="secret-upstream-body sk-test-secret")

    with pytest.raises(provider.AsrProviderError) as caught:
        asyncio.run(_chunk_provider(_config(), handler).transcribe_chunk(path))
    assert caught.value.code == code
    assert len(calls) == attempts
    assert "secret-upstream-body" not in str(caught.value) + caplog.text
    assert "sk-test-secret" not in str(caught.value) + caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": "wrong-protocol"},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        ["bad"],
    ],
)
def test_job_malformed_output_is_classified(tmp_path, payload):
    path = media.make_silent_wav(tmp_path / "chunk.wav", 0.1)
    with pytest.raises(provider.AsrProviderError) as caught:
        asyncio.run(
            _chunk_provider(
                _config(), lambda r: httpx.Response(200, json=payload)
            ).transcribe_chunk(path)
        )
    assert caught.value.code == ErrorCode.INVALID_MODEL_OUTPUT


def test_voice_and_legacy_use_same_protocol(tmp_path, monkeypatch):
    calls = []

    async def post(self, url, *, headers, content):
        calls.append(json.loads(content))
        assert url.endswith("/chat/completions")
        return _response("真实协议替身")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert (
        asyncio.run(transcribe_audio(_wav(), catalog=_catalog(), filename="a.wav"))
        == "真实协议替身"
    )
    path = tmp_path / "short.wav"
    path.write_bytes(_wav())
    monkeypatch.setattr(transcribe, "_stt_config", _config)
    result = asyncio.run(transcribe.transcribe(path))
    assert result["text"] == "真实协议替身"
    assert result["error"] == ""
    assert len(calls) == 2


def test_voice_auth_error_does_not_expose_body(monkeypatch):
    async def post(*args, **kwargs):
        return httpx.Response(401, text="secret-upstream-body sk-test-secret")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(VoiceProviderHTTPError) as caught:
        asyncio.run(transcribe_audio(_wav(), catalog=_catalog(), filename="a.wav"))
    assert caught.value.status_code == 401
    assert not caught.value.body
    assert "sk-test-secret" not in str(caught.value)


@pytest.mark.parametrize("failure,kind", [("timeout", "timeout"), ("malformed", "invalid_output")])
def test_legacy_preserves_qwen_failure_classification(tmp_path, monkeypatch, failure, kind):
    async def post(*args, **kwargs):
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream secret sk-test-secret")
        return httpx.Response(200, json={"text": "wrong-protocol"})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(transcribe, "_stt_config", _config)
    path = tmp_path / "short.wav"
    path.write_bytes(_wav())
    result = asyncio.run(transcribe.transcribe(path))
    assert result["error_kind"] == kind
    assert "sk-test-secret" not in json.dumps(result)


def test_short_endpoint_rejects_long_compressed_recording_before_decode(tmp_path, monkeypatch):
    calls = []

    async def probe(path):
        return media.MediaProbe(path, 100, 45 * 60 * 1000, 16000, 1, "aac", 43200000, 86400000)

    async def normalize(*args, **kwargs):
        calls.append(1)
        raise AssertionError("must reject before full decode")

    monkeypatch.setattr(media, "probe", probe)
    monkeypatch.setattr(media, "normalize_to_wav", normalize)
    with pytest.raises(qwen_asr.QwenAudioLimitError):
        asyncio.run(qwen_asr.prepare_audio(b"compressed-recording", "lecture.m4a"))
    assert not calls


def test_browser_webm_normalizes_to_wav(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "input.wav", 0.3)
    target = tmp_path / "microphone.webm"

    async def run():
        code, _, _ = await media._run(
            [
                asr_tools.ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                media._wsl_path(source, asr_tools.ffmpeg),
                "-c:a",
                "libopus",
                media._wsl_path(target, asr_tools.ffmpeg),
            ],
            timeout=20,
        )
        assert code == 0
        return await qwen_asr.prepare_audio(target.read_bytes(), target.name)

    normalized = asyncio.run(run())
    with wave.open(BytesIO(normalized), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert 0 < wav.getnframes() <= 6000


def test_job_publishes_in_sample_order_after_reversed_qwen_requests(
    asr_subject, asr_tools, monkeypatch
):
    original_plan = media.plan_chunks

    async def small_chunks(probe, *, file_index, tools):
        return await original_plan(
            probe, file_index=file_index, tools=tools, max_chunk_seconds=1, detect_silence=False
        )

    monkeypatch.setattr(media, "plan_chunks", small_chunks)
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        audio = base64.b64decode(
            payload["messages"][0]["content"][0]["input_audio"]["data"].split(",", 1)[1]
        )
        with wave.open(BytesIO(audio), "rb") as wav:
            marker = int.from_bytes(wav.readframes(1), "little", signed=True)
        calls.append(marker)
        return _response(f"片段{marker}")

    service = jobs.AsrJobService(
        asr_subject.subject_id,
        config=_config(),
        tools=asr_tools,
        provider_factory=lambda cfg: _chunk_provider(cfg, handler),
        transcription_order=lambda chunks: list(reversed(chunks)),
    )
    stream = BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        for marker in (1, 2, 3):
            wav.writeframes(marker.to_bytes(2, "little", signed=True) * 16000)

    async def run():
        view, _ = await service.create_job(
            [UploadFile(filename="lecture.wav", file=BytesIO(stream.getvalue()))],
            request_id=str(uuid.uuid4()),
        )
        async with asyncio.timeout(20):
            while service.get_job(view.job_id).status not in ("completed", "failed"):
                await asyncio.sleep(0.02)
        assert service.get_job(view.job_id).status == "completed"
        result = service.get_result(view.job_id)
        return result

    result = asyncio.run(run())
    assert calls == [3, 2, 1]
    assert result["transcripts"][0]["text"] == "片段1\n片段2\n片段3"
