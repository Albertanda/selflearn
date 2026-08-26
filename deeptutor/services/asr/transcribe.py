"""ASR transcription (M4+) — upload a real lecture recording, get text.

Uses the configured STT profile (OpenAI-compatible
``/audio/transcriptions`` wire shape — e.g. SiliconFlow SenseVoice) so no
FunASR runtime is required; a local FunASR server can substitute later by
pointing the STT profile at it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

#: Fallback defaults when no STT profile is configured.
DEFAULT_STT_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_STT_MODEL = "FunAudioLLM/SenseVoiceSmall"


def _stt_config() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) from the active STT profile."""
    from deeptutor.services.config.model_catalog import get_model_catalog_service
    from deeptutor.services.config.provider_runtime import _active_profile_and_model

    service = get_model_catalog_service()
    catalog = service.load()
    profile, model = _active_profile_and_model(catalog, service, "stt")
    api_key = str((profile or {}).get("api_key") or "")
    base_url = str((profile or {}).get("base_url") or DEFAULT_STT_BASE).rstrip("/")
    model_name = str((model or {}).get("model") or DEFAULT_STT_MODEL)
    return base_url, api_key, model_name


async def transcribe(audio_path: Path, *, language: str = "zh") -> dict:
    """Transcribe one audio file via the OpenAI-compatible STT endpoint.

    Returns ``{text, model, base_url}``; ``text`` is "" on failure with
    ``error`` set.
    """
    base_url, api_key, model_name = _stt_config()
    if not api_key:
        return {
            "text": "",
            "model": model_name,
            "base_url": base_url,
            "error": "STT 服务未配置（请在 设置→模型→语音识别 配置 API Key 与模型）",
        }
    url = f"{base_url}/audio/transcriptions"
    files = {"file": (audio_path.name, audio_path.read_bytes(), "audio/mpeg")}
    data = {"model": model_name, "language": language, "response_format": "text"}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
        if resp.status_code != 200:
            return {
                "text": "",
                "model": model_name,
                "base_url": base_url,
                "error": f"ASR 请求失败 ({resp.status_code}): {resp.text[:200]}",
            }
        text = resp.text.strip()
        # Some endpoints wrap in JSON {"text": ...}
        if text.startswith("{"):
            try:
                import json as _json

                text = str(_json.loads(text).get("text", text))
            except Exception:
                pass
        return {"text": text, "model": model_name, "base_url": base_url, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {
            "text": "",
            "model": model_name,
            "base_url": base_url,
            "error": f"ASR 调用异常：{exc}",
        }
