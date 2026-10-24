"""Bounded Qwen ASR chat-audio protocol shared by voice and lecture jobs.

Reference: https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference
This is a distinct wire from OpenRouter's base64_json /audio/transcriptions.
Only bounded audio is encoded. No credentials or upstream bodies enter errors.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit
import wave

import httpx

from deeptutor.services.voice.base import (
    BaseSTTAdapter,
    VoiceProviderError,
    VoiceProviderHTTPError,
    build_auth_headers,
)
from deeptutor.services.voice.config import STTConfig

QWEN_MAX_REQUEST_BYTES = 10_000_000
# Reserve room for the data URI and JSON envelope after 4/3 base64 expansion.
QWEN_MAX_AUDIO_BYTES = 7_490_000
QWEN_MAX_AUDIO_SECONDS = 300
QWEN_MAX_SOURCE_BYTES = 25 * 1024 * 1024
_LIMIT_MESSAGE = "千问单次音频超过大小或时长限制，请使用课程录音上传，由系统自动切片。"


class QwenAudioLimitError(VoiceProviderError):
    """The bounded audio/request budget would be exceeded."""


class QwenInvalidOutputError(VoiceProviderError):
    """The upstream success body was not a Qwen transcript."""


class QwenTimeoutError(VoiceProviderError):
    """The request timed out without exposing its URL or credentials."""


def chat_url(config: STTConfig) -> str:
    parts = urlsplit(str(config.base_url or "").strip())
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise VoiceProviderError("千问 ASR 接口地址无效。")
    path = parts.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def build_request(audio: bytes, config: STTConfig, *, language: str | None = None) -> bytes:
    """Encode one normalized WAV, enforcing both raw and serialized limits."""
    if not audio:
        raise VoiceProviderError("没有可识别的音频。")
    if len(audio) > QWEN_MAX_AUDIO_BYTES:
        raise QwenAudioLimitError(_LIMIT_MESSAGE)
    body = {
        "model": config.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": "data:audio/wav;base64,"
                            + base64.b64encode(audio).decode("ascii")
                        },
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": False},
    }
    selected_language = language if language is not None else config.language
    if selected_language and selected_language != "auto":
        body["asr_options"]["language"] = selected_language
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > QWEN_MAX_REQUEST_BYTES:
        raise QwenAudioLimitError(_LIMIT_MESSAGE)
    return encoded


def parse_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise QwenInvalidOutputError("千问 ASR 返回了无效的转写结果。") from exc
    if not isinstance(text, str):
        raise QwenInvalidOutputError("千问 ASR 返回了无效的转写结果。")
    # Silence can legitimately produce an empty string.
    return text.strip()


async def prepare_audio(audio: bytes, filename: str) -> bytes:
    """Normalize short clips (including browser WebM) to provider-safe WAV.

    Lecture jobs already normalize and bound files; they call build_request
    directly. The voice/legacy endpoints must reject long clips before decode.
    """
    if not audio:
        raise VoiceProviderError("没有可识别的音频。")
    if len(audio) > QWEN_MAX_SOURCE_BYTES:
        raise QwenAudioLimitError(_LIMIT_MESSAGE)
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            if frames <= 0 or rate <= 0:
                raise VoiceProviderError("音频为空或无效。")
            if frames > QWEN_MAX_AUDIO_SECONDS * rate:
                raise QwenAudioLimitError(_LIMIT_MESSAGE)
            if (rate, wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2):
                if len(audio) > QWEN_MAX_AUDIO_BYTES:
                    raise QwenAudioLimitError(_LIMIT_MESSAGE)
                return audio
    except (wave.Error, EOFError):
        pass

    from deeptutor.services.asr import media
    from deeptutor.subjects.errors import AsrOperationError

    suffix = Path(filename).suffix.lower()
    if suffix not in {
        ".webm",
        ".wav",
        ".mp3",
        ".m4a",
        ".ogg",
        ".opus",
        ".aac",
        ".flac",
        ".amr",
        ".wma",
    }:
        suffix = ".webm"
    try:
        with tempfile.TemporaryDirectory(prefix="qwen-asr-") as root:
            source = Path(root) / ("clip" + suffix)
            target = Path(root) / "normalized.wav"
            source.write_bytes(audio)
            info = await media.probe(source)
            if (
                info.duration_ms > QWEN_MAX_AUDIO_SECONDS * 1000
                or info.wav_bytes + 4096 > QWEN_MAX_AUDIO_BYTES
            ):
                raise QwenAudioLimitError(_LIMIT_MESSAGE)
            await media.normalize_to_wav(source, target, timeout=60)
            with target.open("rb") as handle:
                normalized = handle.read(QWEN_MAX_AUDIO_BYTES + 1)
            if len(normalized) > QWEN_MAX_AUDIO_BYTES:
                raise QwenAudioLimitError(_LIMIT_MESSAGE)
            return normalized
    except AsrOperationError as exc:
        raise VoiceProviderError("音频转换失败，请确认音频文件及 FFmpeg/FFprobe 可用。") from exc


class QwenASRAdapter(BaseSTTAdapter):
    async def transcribe(
        self,
        audio: bytes,
        config: STTConfig,
        *,
        filename: str = "audio.webm",
        content_type: str = "application/octet-stream",
    ) -> str:
        normalized = await prepare_audio(audio, filename)
        body = build_request(normalized, config)
        headers = {**build_auth_headers(config.auth_style, config.api_key), **config.extra_headers}
        headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(timeout=config.request_timeout) as client:
                response = await client.post(chat_url(config), headers=headers, content=body)
        except httpx.TimeoutException as exc:
            raise QwenTimeoutError("千问 ASR 请求超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("无法连接千问 ASR 服务，请检查网络和接口地址。") from exc
        if response.status_code != 200:
            message = {
                401: "千问 ASR 密钥无效，请检查 API Key 及地域。",
                403: "千问 ASR 访问被拒绝，请检查业务空间、模型权限及账户状态。",
                402: "千问 ASR 账户计费不可用，请检查账户状态。",
                413: _LIMIT_MESSAGE,
                429: "千问 ASR 请求过于频繁，请稍后重试。",
            }.get(response.status_code, f"千问 ASR 请求失败（HTTP {response.status_code}）。")
            raise VoiceProviderHTTPError(message, status_code=response.status_code)
        return parse_response(response)
