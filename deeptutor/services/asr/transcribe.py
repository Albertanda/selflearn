"""ASR transcription (M4+) — upload a real lecture recording, get text.

Uses the configured STT profile. Multipart recordings are streamed from a
controlled handle; Qwen chat-audio requests buffer only bounded short clips.
Long recordings belong to the asynchronous, automatically chunked job API.
Every failure has a kind (timeout/provider/invalid_output/io/unconfigured),
so callers map it onto a fixed C02 error without echoing upstream bodies.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from deeptutor.services.voice.config import STT_QWEN_CHAT, STTConfig
from deeptutor.subjects.errors import SubjectOperationError, SubjectStorageError

logger = logging.getLogger(__name__)

#: Fallback defaults when no STT profile is configured.
DEFAULT_STT_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_STT_MODEL = "FunAudioLLM/SenseVoiceSmall"

#: Per-request timeout, unchanged from the previous implementation.
STT_TIMEOUT_SECONDS = 300

#: Audio extension → MIME sent for the multipart part.
MIME_BY_EXTENSION = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".aac": "audio/aac",
    ".amr": "audio/amr",
    ".wma": "audio/x-ms-wma",
    ".webm": "audio/webm",
}


def mime_for(audio_path: Path | str) -> str:
    """MIME for one recording, derived from its extension (never hard-coded)."""
    return MIME_BY_EXTENSION.get(Path(audio_path).suffix.lower(), "application/octet-stream")


def _stt_config() -> STTConfig:
    """Resolve the same provider/protocol as voice and asynchronous jobs."""
    from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config

    return resolve_stt_runtime_config()


_JSON_LEADING = ("{", "[", '"')
_JSON_LITERALS = {"null", "true", "false"}


def _is_json_payload(body: str, content_type: str) -> bool:
    """Is this body a JSON document rather than plain transcript text?

    The declared content type decides first (an ``application/json`` body is
    JSON even when it is an array or a bare scalar). Without a JSON content
    type, only an unambiguous JSON shape counts — a leading object/array/string
    delimiter or a bare literal. Ordinary text is left alone.
    """
    if "json" in (content_type or "").lower():
        return True
    stripped = body.lstrip()
    if not stripped:
        return False
    if stripped[0] in _JSON_LEADING:
        return True
    head = stripped.split(maxsplit=1)[0].rstrip(",:")
    return head in _JSON_LITERALS


def _validated_text(value: str) -> str | None:
    """Trim and UTF-8-encode a candidate transcript; ``None`` when impossible."""
    text = value.strip()
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return text


def extract_transcript_text(body: str, *, content_type: str = "") -> str | None:
    """The transcript in a provider body, or ``None`` when there is none.

    A plain-text body is the transcript (an empty body is a legal empty
    transcript). A JSON body must be an **object** carrying a real string
    ``text``: an array, ``null``, a scalar, a missing/non-string field, broken
    JSON or any non-UTF-8 value is a malformed provider answer — never
    stringified or stored as a transcript.
    """
    raw = body if isinstance(body, str) else ""
    if not _is_json_payload(raw, content_type):
        return _validated_text(raw)
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("text")
    if not isinstance(value, str):
        return None
    return _validated_text(value)


def _unconfigured_failure(kind: str, detail: str) -> dict:
    """A failure that happens before any endpoint/model is known."""
    if detail:
        logger.warning("ASR unavailable (%s): %s", kind, detail)
    return {
        "text": "",
        "model": "",
        "base_url": "",
        "error": detail or kind,
        "error_kind": kind,
    }


def _failure(base_url: str, model_name: str, kind: str, detail: str) -> dict:
    """Server-side diagnostic; ``detail`` is never echoed to a client."""
    if detail:
        logger.warning("ASR failure (%s): %s", kind, detail)
    return {
        "text": "",
        "model": model_name,
        "base_url": base_url,
        "error": detail or kind,
        "error_kind": kind,
    }


async def transcribe(audio_path: Path, *, language: str = "zh") -> dict:
    """Transcribe one audio file via its resolved STT protocol.

    Returns ``{text, model, base_url}`` plus ``error``/``error_kind`` when the
    call failed; ``text`` is "" on failure. A legal empty transcript is a
    success with ``text == ""`` and no error.
    """
    try:
        config = _stt_config()
        base_url, api_key, model_name = config.base_url.rstrip("/"), config.api_key, config.model
    except (SubjectOperationError, SubjectStorageError):
        # Preserve already-classified local corruption/IO and domain failures.
        raise
    except (TimeoutError, httpx.TimeoutException) as exc:
        return _unconfigured_failure("timeout", f"STT 配置读取超时：{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001 - configuration is a provider boundary
        # Reading the STT profile is part of the same controlled boundary as the
        # request itself: a broken catalog/settings file must surface as
        # "provider unavailable", never as an internal server error.
        return _unconfigured_failure("unconfigured", f"STT 配置读取失败：{type(exc).__name__}")
    if not api_key:
        return _failure(
            base_url,
            model_name,
            "unconfigured",
            "STT 服务未配置（请在 设置→模型→语音识别 配置 API Key 与模型）",
        )

    audio_path = Path(audio_path)
    if config.request_style == STT_QWEN_CHAT:
        return await _transcribe_qwen(audio_path, config, language)
    url = f"{base_url}/audio/transcriptions"
    data = {"model": model_name, "language": language, "response_format": "text"}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_SECONDS) as client:
            # Streamed multipart: the provider reads the file handle directly,
            # so a 200MiB recording never becomes one in-memory bytes object.
            with open(audio_path, "rb") as handle:
                files = {"file": (audio_path.name, handle, mime_for(audio_path))}
                resp = await client.post(url, headers=headers, files=files, data=data)
    except httpx.TimeoutException as exc:
        return _failure(base_url, model_name, "timeout", f"ASR 请求超时：{type(exc).__name__}")
    except OSError as exc:
        return _failure(base_url, model_name, "io", f"ASR 无法读取音频：{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        return _failure(base_url, model_name, "provider", f"ASR 调用异常：{type(exc).__name__}")

    if resp.status_code != 200:
        return _failure(
            base_url, model_name, "provider", f"ASR 请求失败，状态码 {resp.status_code}"
        )
    content_type = ""
    try:
        content_type = str(resp.headers.get("content-type") or "")
    except Exception:  # pragma: no cover - defensive for odd response objects
        content_type = ""
    text = extract_transcript_text(resp.text, content_type=content_type)
    if text is None:
        return _failure(base_url, model_name, "invalid_output", "ASR 响应不是合法转写文本")
    return {"text": text, "model": model_name, "base_url": base_url, "error": ""}


async def _transcribe_qwen(audio_path: Path, config: STTConfig, language: str) -> dict:
    from deeptutor.services.voice.adapters.qwen_asr import (
        QWEN_MAX_SOURCE_BYTES,
        QwenASRAdapter,
        QwenInvalidOutputError,
        QwenTimeoutError,
    )
    from deeptutor.services.voice.base import VoiceProviderError

    base_url, model = config.base_url, config.model
    try:
        with audio_path.open("rb") as handle:
            # Never read a whole lecture into memory through the old endpoint.
            audio = handle.read(QWEN_MAX_SOURCE_BYTES + 1)
        config.language = language
        text = await QwenASRAdapter().transcribe(audio, config, filename=audio_path.name)
    except OSError:
        return _failure(base_url, model, "io", "ASR 无法读取音频。")
    except QwenInvalidOutputError:
        return _failure(base_url, model, "invalid_output", "ASR 响应不是合法转写文本。")
    except QwenTimeoutError:
        return _failure(base_url, model, "timeout", "千问 ASR 请求超时，请稍后重试。")
    except VoiceProviderError as exc:
        return _failure(base_url, model, "provider", str(exc))
    return {"text": text, "model": model, "base_url": base_url, "error": ""}


__all__ = [
    "DEFAULT_STT_BASE",
    "DEFAULT_STT_MODEL",
    "MIME_BY_EXTENSION",
    "STT_TIMEOUT_SECONDS",
    "extract_transcript_text",
    "mime_for",
    "transcribe",
]
