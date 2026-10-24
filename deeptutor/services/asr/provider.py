"""Bounded multipart and Qwen chat-audio STT transport for lecture jobs.

A caller supplies a resolved ``STTConfig``. The config fingerprint excludes
the secret; credentials, request bodies and upstream errors are never logged.

Per-chunk transport policy (CONTRACTS D5): connect 15 s, read 180 s, write 60 s,
total wall clock 240 s, at most three attempts for retryable failures.  HTTP
401/403 and 413 are never retried here; 413 is surfaced to the job layer so it
can split only the failed sample range.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime as dt
import email.utils
import logging
from pathlib import Path
import random
import time
from typing import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from deeptutor.services.asr import transcribe as transcribe_mod
from deeptutor.services.asr.contracts import (
    PROVIDER_CONNECT_TIMEOUT,
    PROVIDER_MAX_ATTEMPTS,
    PROVIDER_READ_TIMEOUT,
    PROVIDER_RETRY_AFTER_CAP,
    PROVIDER_TOTAL_TIMEOUT,
    PROVIDER_WRITE_TIMEOUT,
    media_chunk_cap,
)
from deeptutor.services.voice.config import (
    AUTH_API_KEY_HEADER,
    AUTH_BEARER,
    AUTH_TOKEN,
    STT_MULTIPART,
    STT_QWEN_CHAT,
    STTConfig,
)
from deeptutor.subjects.errors import (
    AsrErrorCode,
    AsrOperationError,
    ErrorCode,
    asr_error,
    subject_error,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderCapabilities:
    max_bytes: int
    max_seconds: int
    protocol: str


class AsrProviderError(AsrOperationError):
    """Safe provider failure; ``reason`` is server-side and never serialized."""

    def __init__(
        self,
        code: ErrorCode | str,
        *,
        status: int | None = None,
        reason: str = "",
        retry_after: float | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(code, cause=cause)
        self.upstream_status = status
        self.reason = reason[:240]
        self.retry_after = retry_after

    def __repr__(self) -> str:  # pragma: no cover - never include cause/body
        return f"AsrProviderError(code={self.code.value!r}, status={self.upstream_status!r})"


@dataclass(frozen=True)
class ProviderResult:
    text: str
    model: str
    attempts: int


def capabilities(config: STTConfig) -> ProviderCapabilities:
    """Return conservative request limits for the resolved provider.

    Capability selection uses explicit adapter/protocol, never a display name.
    """
    if (config.adapter, config.request_style) not in (
        ("openai_compat", STT_MULTIPART),
        ("qwen_asr", STT_QWEN_CHAT),
    ):
        raise asr_error(AsrErrorCode.ASR_PROTOCOL_UNSUPPORTED)
    max_bytes, max_seconds = media_chunk_cap(config)
    return ProviderCapabilities(
        max_bytes=max_bytes, max_seconds=max_seconds, protocol=config.request_style
    )


def transcriptions_url(config: STTConfig) -> str:
    base = str(config.base_url or "").strip().rstrip("/")
    if not base:
        raise subject_error(ErrorCode.PROVIDER_UNAVAILABLE)
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise subject_error(ErrorCode.PROVIDER_UNAVAILABLE)
    path = parts.path.rstrip("/")
    if not path.endswith("/audio/transcriptions"):
        path += "/audio/transcriptions"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if config.api_version and "api-version" not in query:
        query["api-version"] = str(config.api_version)
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def auth_headers(config: STTConfig) -> dict[str, str]:
    key = str(config.api_key or "")
    if config.auth_style == AUTH_BEARER:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    elif config.auth_style == AUTH_API_KEY_HEADER:
        headers = {"api-key": key} if key else {}
    elif config.auth_style == AUTH_TOKEN:
        headers = {"Authorization": f"Token {key}"} if key else {}
    else:
        headers = {}
    headers.update({str(k): str(v) for k, v in (config.extra_headers or {}).items()})
    return headers


def _retry_after_seconds(value: str | None, *, now: float | None = None) -> float | None:
    if not value:
        return None
    raw = value.strip()
    try:
        return max(0.0, min(PROVIDER_RETRY_AFTER_CAP, float(raw)))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        current = dt.datetime.fromtimestamp(now or time.time(), tz=dt.timezone.utc)
        return max(0.0, min(PROVIDER_RETRY_AFTER_CAP, (parsed - current).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _classify_status(status: int, *, retry_after: float | None) -> AsrProviderError:
    if status == 402:
        return AsrProviderError(
            AsrErrorCode.ASR_PROVIDER_BILLING, status=status, reason="account_billing"
        )
    if status in (401, 403):
        return AsrProviderError(
            AsrErrorCode.ASR_PROVIDER_AUTH, status=status, reason=f"provider_status_{status}"
        )
    if status == 413:
        return AsrProviderError(
            AsrErrorCode.ASR_PROVIDER_LIMIT, status=status, reason="provider_413"
        )
    if status == 429:
        return AsrProviderError(
            AsrErrorCode.ASR_RATE_LIMITED,
            status=status,
            reason="rate_limited",
            retry_after=retry_after,
        )
    if status in (408, 504):
        return AsrProviderError(
            ErrorCode.PROVIDER_TIMEOUT, status=status, reason="upstream_timeout"
        )
    if status in (400, 415, 422):
        return AsrProviderError(
            AsrErrorCode.ASR_INVALID_AUDIO, status=status, reason=f"invalid_audio_{status}"
        )
    if 500 <= status <= 599:
        return AsrProviderError(
            ErrorCode.PROVIDER_UNAVAILABLE, status=status, reason=f"upstream_{status}"
        )
    return AsrProviderError(
        ErrorCode.PROVIDER_UNAVAILABLE, status=status, reason="unexpected_status"
    )


def _trace_id(response: httpx.Response) -> str:
    for name in ("x-siliconcloud-trace-id", "x-request-id", "x-trace-id", "trace-id"):
        value = response.headers.get(name)
        if value:
            return str(value)[:80]
    return ""


def _default_client_factory(timeout: httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)


class OpenAICompatibleProvider:
    """One provider instance bound to one resolved, non-secret configuration."""

    def __init__(
        self,
        config: STTConfig,
        *,
        client_factory: Callable[[httpx.Timeout], httpx.AsyncClient] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        jitter: Callable[[], float] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self.capabilities = capabilities(config)
        self._client_factory = client_factory or _default_client_factory
        self._sleep = sleep or asyncio.sleep
        self._jitter = jitter or (lambda: random.uniform(0.0, 0.25))
        self._clock = clock or time.monotonic

    async def transcribe_chunk(
        self,
        audio_path: Path,
        *,
        language: str = "zh",
        max_attempts: int = PROVIDER_MAX_ATTEMPTS,
    ) -> ProviderResult:
        """Transcribe one bounded WAV chunk, retrying only transient failures."""
        path = Path(audio_path)
        if path.stat().st_size > self.capabilities.max_bytes:
            raise AsrProviderError(AsrErrorCode.ASR_PROVIDER_LIMIT, reason="chunk_bytes")
        from deeptutor.services.asr.media import wav_info

        frames, rate, channels, width = wav_info(path)
        if (rate, channels, width) != (16000, 1, 2):
            raise AsrProviderError(AsrErrorCode.ASR_INVALID_AUDIO, reason="chunk_encoding")
        if frames <= 0 or frames > self.capabilities.max_seconds * rate:
            raise AsrProviderError(AsrErrorCode.ASR_PROVIDER_LIMIT, reason="chunk_duration")
        max_attempts = min(PROVIDER_MAX_ATTEMPTS, max(1, max_attempts))
        is_qwen = self.config.request_style == STT_QWEN_CHAT
        request_body = None
        if is_qwen:
            from deeptutor.services.voice.adapters.qwen_asr import (
                QwenAudioLimitError,
                build_request,
                chat_url,
            )

            with path.open("rb") as handle:
                audio = handle.read(self.capabilities.max_bytes + 1)
            try:
                request_body = build_request(audio, self.config, language=language)
            except QwenAudioLimitError as exc:
                raise AsrProviderError(
                    AsrErrorCode.ASR_PROVIDER_LIMIT, reason="request_bytes"
                ) from exc
            url = chat_url(self.config)
        else:
            url = transcriptions_url(self.config)
        headers = auth_headers(self.config)
        if is_qwen:
            headers["Content-Type"] = "application/json"
        timeout = httpx.Timeout(
            connect=PROVIDER_CONNECT_TIMEOUT,
            read=PROVIDER_READ_TIMEOUT,
            write=PROVIDER_WRITE_TIMEOUT,
            pool=PROVIDER_CONNECT_TIMEOUT,
        )
        started = self._clock()
        last: AsrProviderError | None = None
        for attempt in range(1, max_attempts + 1):
            elapsed = self._clock() - started
            remaining = PROVIDER_TOTAL_TIMEOUT - elapsed
            if remaining <= 0:
                raise AsrProviderError(ErrorCode.PROVIDER_TIMEOUT, reason="chunk_deadline")
            try:
                async with asyncio.timeout(remaining):
                    async with self._client_factory(timeout) as client:
                        if is_qwen:
                            response = await client.post(url, headers=headers, content=request_body)
                        else:
                            response = await self._post_multipart(
                                client, url, headers, path, language
                            )
            except (TimeoutError, httpx.TimeoutException) as exc:
                last = AsrProviderError(
                    ErrorCode.PROVIDER_TIMEOUT, reason="client_timeout", cause=exc
                )
            except (OSError, httpx.HTTPError) as exc:
                last = AsrProviderError(
                    ErrorCode.PROVIDER_UNAVAILABLE, reason="transport", cause=exc
                )
            except AsrProviderError:
                raise
            else:
                status = int(response.status_code)
                trace = _trace_id(response)
                if status == 200:
                    if is_qwen:
                        from deeptutor.services.voice.adapters.qwen_asr import parse_response
                        from deeptutor.services.voice.base import VoiceProviderError

                        try:
                            text = parse_response(response)
                        except VoiceProviderError:
                            text = None
                    else:
                        content_type = str(response.headers.get("content-type") or "")
                        text = transcribe_mod.extract_transcript_text(
                            response.text, content_type=content_type
                        )
                    if text is None:
                        raise AsrProviderError(
                            ErrorCode.INVALID_MODEL_OUTPUT,
                            status=status,
                            reason=f"invalid_output trace={trace}"[:240],
                        )
                    logger.info(
                        "ASR chunk ok status=200 attempt=%s bytes=%s trace=%s",
                        attempt,
                        path.stat().st_size,
                        trace or "-",
                    )
                    return ProviderResult(text=text, model=str(self.config.model), attempts=attempt)
                retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                last = _classify_status(status, retry_after=retry_after)
                logger.warning(
                    "ASR chunk failure status=%s attempt=%s trace=%s",
                    status,
                    attempt,
                    trace or "-",
                )
                if last.code not in (
                    AsrErrorCode.ASR_RATE_LIMITED,
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    ErrorCode.PROVIDER_TIMEOUT,
                ):
                    raise last

            if attempt >= max_attempts:
                break
            elapsed = self._clock() - started
            remaining = PROVIDER_TOTAL_TIMEOUT - elapsed
            if remaining <= 0:
                break
            if last is not None and last.retry_after is not None:
                delay = last.retry_after
            else:
                delay = min(30.0, 0.5 * (2 ** (attempt - 1))) + self._jitter()
            if delay > remaining:
                break
            await self._sleep(delay)

        if last is None:  # pragma: no cover - defensive
            last = AsrProviderError(ErrorCode.PROVIDER_UNAVAILABLE, reason="no_attempt")
        raise last

    async def _post_multipart(self, client, url, headers, path, language):
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, transcribe_mod.mime_for(path))}
            data = {"model": self.config.model, "language": language, "response_format": "text"}
            return await client.post(url, headers=headers, files=files, data=data)


__all__ = [
    "AsrProviderError",
    "OpenAICompatibleProvider",
    "ProviderCapabilities",
    "ProviderResult",
    "auth_headers",
    "capabilities",
    "transcriptions_url",
]
