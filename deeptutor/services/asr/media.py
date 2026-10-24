"""Bounded media probing, silence-aware chunk planning and PCM extraction.

All commands use a fixed argv with ``shell=False``.  The input path is opened
read-only by ffmpeg/ffprobe; the module never rewrites it.  On WSL an explicitly
configured ``*.exe`` tool receives a path converted with ``wslpath -w`` rather
than a path string guessed for another platform.

No function here calls the network.  Timeouts kill only the process group this
module created (``start_new_session=True``), never a broad ``pkill``.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from typing import Any, Sequence
import wave

from deeptutor.services.asr.contracts import (
    CHUNK_CHANNELS,
    CHUNK_SAMPLE_RATE,
    CHUNK_SAMPLE_WIDTH,
    MAX_CHUNK_SECONDS,
    MAX_TOTAL_DURATION_MS,
    MAX_WORK_BYTES,
    MEDIA_TOTAL_TIMEOUT_SECONDS,
    PROBE_TIMEOUT_SECONDS,
    SILENCE_LOOKBACK_SECONDS,
    SILENCE_MIN_SECONDS,
    SILENCE_NOISE_DB,
    chunk_id_for,
)
from deeptutor.subjects.errors import (
    AsrErrorCode,
    AsrOperationError,
    ErrorCode,
    asr_error,
)

logger = logging.getLogger(__name__)


class MediaError(AsrOperationError):
    """A media failure with a fixed public code and a server-only reason."""

    def __init__(
        self,
        code: AsrErrorCode | ErrorCode | str,
        *,
        reason: str = "",
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(code, cause=cause)
        self.reason = reason[:240]

    def __repr__(self) -> str:  # pragma: no cover
        return f"MediaError(code={self.code.value!r})"


class MediaCancelled(Exception):
    """The caller cancelled a running probe/extraction."""


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: str
    ffprobe: str

    @property
    def explicit_windows(self) -> bool:
        return self.ffmpeg.lower().endswith(".exe") or self.ffprobe.lower().endswith(".exe")


@dataclass(frozen=True)
class MediaProbe:
    path: Path
    size_bytes: int
    duration_ms: int
    input_sample_rate: int
    channels: int
    codec: str
    total_samples: int
    wav_bytes: int


@dataclass(frozen=True)
class PlannedChunk:
    file_index: int
    chunk_index: int
    start_sample: int
    end_sample: int
    sample_rate: int = CHUNK_SAMPLE_RATE

    @property
    def chunk_id(self) -> str:
        return chunk_id_for(self.file_index, self.start_sample, self.end_sample)

    @property
    def samples(self) -> int:
        return self.end_sample - self.start_sample

    @property
    def duration_ms(self) -> int:
        return round(self.samples * 1000 / self.sample_rate)


def _is_executable(path: Path) -> bool:
    try:
        return path.is_file() and (os.access(path, os.X_OK) or path.suffix.lower() == ".exe")
    except OSError:
        return False


def resolve_tools(env: dict[str, str] | None = None) -> MediaTools:
    """Resolve env paths, optional asr_media.json paths, then native PATH.

    A missing explicit value is a named dependency failure; it never silently
    falls back to a different binary than the operator asked for.
    """
    values = os.environ if env is None else env
    configured = {}
    if env is None and not (
        values.get("SELFLEARN_FFMPEG_BIN") and values.get("SELFLEARN_FFPROBE_BIN")
    ):
        from deeptutor.services.path_service import get_path_service

        config_path = get_path_service().get_settings_file("asr_media")
        if config_path.exists():
            try:
                configured = json.loads(config_path.read_text(encoding="utf-8"))
                if not isinstance(configured, dict) or any(
                    not isinstance(configured.get(key, ""), str)
                    for key in ("ffmpeg_bin", "ffprobe_bin")
                ):
                    raise ValueError("invalid media configuration")
            except (OSError, ValueError) as exc:
                raise asr_error(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE, cause=exc) from exc
    explicit_ffmpeg = str(
        values.get("SELFLEARN_FFMPEG_BIN") or configured.get("ffmpeg_bin") or ""
    ).strip()
    explicit_ffprobe = str(
        values.get("SELFLEARN_FFPROBE_BIN") or configured.get("ffprobe_bin") or ""
    ).strip()
    if explicit_ffmpeg:
        ffmpeg = Path(explicit_ffmpeg).expanduser()
        if not _is_executable(ffmpeg):
            raise asr_error(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE)
    else:
        found = shutil.which("ffmpeg")
        if not found:
            raise asr_error(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE)
        ffmpeg = Path(found)
    if explicit_ffprobe:
        ffprobe = Path(explicit_ffprobe).expanduser()
        if not _is_executable(ffprobe):
            raise asr_error(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE)
    else:
        found = shutil.which("ffprobe")
        if not found:
            raise asr_error(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE)
        ffprobe = Path(found)
    return MediaTools(str(ffmpeg), str(ffprobe))


def _wsl_path(path: Path, tool: str) -> str:
    if not str(tool).lower().endswith(".exe"):
        return str(path)
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(
            AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE, reason="wslpath_failed", cause=exc
        ) from exc
    converted = (result.stdout or "").strip()
    if result.returncode != 0 or not converted:
        raise MediaError(AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE, reason="wslpath_failed")
    return converted


def _reject_input(path: Path) -> Path:
    path = Path(path)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="input_missing", cause=exc) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="input_not_regular")
    if info.st_size <= 0:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="input_empty")
    return path


@dataclass
class MediaBudget:
    root: Path
    remaining: float = MEDIA_TOTAL_TIMEOUT_SECONDS


_BUDGET: ContextVar[MediaBudget | None] = ContextVar("asr_media_budget", default=None)


def set_job_budget(root: Path):
    return _BUDGET.set(MediaBudget(root))


def reset_job_budget(token) -> None:
    _BUDGET.reset(token)


async def _run(
    argv: Sequence[str],
    *,
    timeout: float,
    output_cap: int = 2 * 1024 * 1024,
) -> tuple[int, bytes, bytes]:
    """Drain bounded pipes while running; kill and reap owned children on exit."""
    budget = _BUDGET.get()
    if budget is not None:
        timeout = min(timeout, budget.remaining)
    if timeout <= 0:
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="media_timeout")
    started = time.monotonic()
    proc = None
    readers = []

    async def drain(stream):
        result = bytearray()
        while block := await stream.read(min(65536, output_cap + 1)):
            result.extend(block)
            if len(result) > output_cap:
                raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="output_budget")
        return bytes(result)

    spawn = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    )
    try:
        try:
            proc = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            proc = await spawn
            raise
        except OSError as exc:
            raise MediaError(
                AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE, reason="spawn_failed", cause=exc
            ) from exc
        readers = [asyncio.create_task(drain(proc.stdout)), asyncio.create_task(drain(proc.stderr))]
        waiter = asyncio.create_task(proc.wait())
        readers.append(waiter)
        async with asyncio.timeout(timeout):
            while not all(task.done() for task in readers):
                for task in readers:
                    if task.done():
                        task.result()
                if budget is not None:
                    used = sum(p.lstat().st_size for p in budget.root.rglob("*") if p.is_file())
                    if used > MAX_WORK_BYTES:
                        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="work_budget")
                await asyncio.sleep(0.02)
            stdout, stderr, code = await asyncio.gather(*readers)
        return code, stdout, stderr
    except TimeoutError as exc:
        raise MediaError(
            AsrErrorCode.ASR_RESOURCE_LIMIT, reason="media_timeout", cause=exc
        ) from exc
    finally:
        if proc is not None:
            if proc.returncode is None:
                _kill_group(proc.pid)
            # Drain tasks are cancelled before reaping, including failure paths.
            for task in readers:
                if not task.done():
                    task.cancel()
            if readers:
                await asyncio.gather(*readers, return_exceptions=True)
            try:
                await asyncio.wait_for(proc.wait(), 3)
            finally:
                _close_transport(proc)
        if budget is not None:
            budget.remaining -= time.monotonic() - started


def _kill_group(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _close_transport(proc: asyncio.subprocess.Process) -> None:
    """Close the subprocess transport without waiting on an unread pipe."""
    try:
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()
    except Exception:  # pragma: no cover - defensive
        pass


def _probe_argv(tools: MediaTools, path: Path) -> list[str]:
    return [
        tools.ffprobe,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type,codec_name,sample_rate,channels,duration:format=duration",
        "-of",
        "json",
        _wsl_path(path, tools.ffprobe),
    ]


def parse_probe(path: Path, payload: dict[str, Any], size_bytes: int) -> MediaProbe:
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="no_audio_stream")
    stream = streams[0] if isinstance(streams[0], dict) else {}
    if stream.get("codec_type") != "audio":
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="not_audio")
    try:
        channels = int(stream.get("channels") or 0)
        input_rate = int(stream.get("sample_rate") or 0)
    except (TypeError, ValueError) as exc:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_stream", cause=exc) from exc
    if channels <= 0 or input_rate <= 0:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_stream")
    duration_raw = stream.get("duration")
    if duration_raw in (None, "", "N/A"):
        duration_raw = (payload.get("format") or {}).get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError) as exc:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_duration", cause=exc) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_duration")
    duration_ms = round(duration * 1000)
    if duration_ms > MAX_TOTAL_DURATION_MS:
        raise asr_error(AsrErrorCode.ASR_DURATION_LIMIT)
    total_samples = max(1, round(duration * CHUNK_SAMPLE_RATE))
    wav_bytes = total_samples * CHUNK_CHANNELS * CHUNK_SAMPLE_WIDTH
    if size_bytes + wav_bytes > MAX_WORK_BYTES:
        raise asr_error(AsrErrorCode.ASR_RESOURCE_LIMIT)
    return MediaProbe(
        path=path,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
        input_sample_rate=input_rate,
        channels=channels,
        codec=str(stream.get("codec_name") or ""),
        total_samples=total_samples,
        wav_bytes=wav_bytes,
    )


async def probe(
    path: Path,
    *,
    tools: MediaTools | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> MediaProbe:
    path = _reject_input(path)
    tools = tools or resolve_tools()
    code, stdout, _stderr = await _run(
        _probe_argv(tools, path), timeout=timeout, output_cap=1024 * 1024
    )
    if code != 0:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason=f"ffprobe_exit_{code}")
    try:
        payload = json.loads(stdout.decode("utf-8", "replace") or "{}")
    except ValueError as exc:
        raise MediaError(
            AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_probe_json", cause=exc
        ) from exc
    if not isinstance(payload, dict):
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_probe_json")
    return parse_probe(path, payload, path.stat().st_size)


def probe_sync(path: Path, *, tools: MediaTools | None = None) -> MediaProbe:
    return asyncio.run(probe(path, tools=tools))


async def normalize_to_wav(
    input_path: Path,
    output_path: Path,
    *,
    tools: MediaTools | None = None,
    timeout: float = MEDIA_TOTAL_TIMEOUT_SECONDS,
) -> int:
    """Decode one recording once into 16 kHz mono PCM16 and return its frames.

    Chunk extraction then seeks inside a local PCM WAV, avoiding a full decode
    of the source for every chunk while preserving exact sample boundaries.
    """
    input_path = _reject_input(input_path)
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="normalized_exists")
    final_path = output_path
    output_path = output_path.with_name(output_path.name + ".partial")
    if output_path.is_symlink():
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="partial_symlink")
    output_path.unlink(missing_ok=True)
    tools = tools or resolve_tools()
    argv = [
        tools.ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        _wsl_path(input_path, tools.ffmpeg),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        str(CHUNK_CHANNELS),
        "-ar",
        str(CHUNK_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-y",
        _wsl_path(output_path, tools.ffmpeg),
    ]
    try:
        code, _stdout, _stderr = await _run(argv, timeout=timeout, output_cap=1024 * 1024)
        if code != 0:
            raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason=f"ffmpeg_exit_{code}")
        frames, rate, channels, width = wav_info(output_path)
        if rate != CHUNK_SAMPLE_RATE or channels != CHUNK_CHANNELS or width != CHUNK_SAMPLE_WIDTH:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="normalized_shape")
        if frames <= 0:
            raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="normalized_empty")
        if output_path.stat().st_size > MAX_WORK_BYTES:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="normalized_budget")
        os.replace(output_path, final_path)
        return frames
    finally:
        output_path.unlink(missing_ok=True)


def _decode_argv(tools: MediaTools, path: Path, start: int, end: int) -> list[str]:
    duration = max(0.001, (end - start) / CHUNK_SAMPLE_RATE)
    return [
        tools.ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start / CHUNK_SAMPLE_RATE:.6f}",
        "-t",
        f"{duration:.6f}",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        _wsl_path(path, tools.ffmpeg),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        f"aresample={CHUNK_SAMPLE_RATE},asetpts=PTS-STARTPTS",
        "-ac",
        str(CHUNK_CHANNELS),
        "-ar",
        str(CHUNK_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        "-f",
        "s16le",
        "pipe:1",
    ]


async def _decode_window(
    path: Path,
    start: int,
    end: int,
    *,
    tools: MediaTools,
    timeout: float,
) -> bytes:
    code, stdout, _stderr = await _run(
        _decode_argv(tools, path, start, end),
        timeout=timeout,
        output_cap=max(2 * 1024 * 1024, (end - start) * 2 + 4096),
    )
    if code != 0:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason=f"ffmpeg_exit_{code}")
    return stdout


async def find_silence_midpoint(
    path: Path,
    start_sample: int,
    end_sample: int,
    *,
    tools: MediaTools | None = None,
    timeout: float = 60.0,
) -> int | None:
    """Last >=0.3 s quiet run's midpoint in the lookback window, or ``None``.

    The window is resampled to 16 kHz and scanned at 10 ms resolution.  A
    failure to decode the window is a hard media error; "no quiet run" simply
    returns ``None`` and the caller performs a hard cut.
    """
    start = max(0, int(start_sample))
    end = max(start + 1, int(end_sample))
    tools = tools or resolve_tools()
    raw = await _decode_window(path, start, end, tools=tools, timeout=timeout)
    frame = CHUNK_SAMPLE_RATE // 100  # 10 ms
    frame_bytes = frame * CHUNK_SAMPLE_WIDTH
    threshold = 32768.0 * (10 ** (SILENCE_NOISE_DB / 20.0))
    quiet_runs: list[tuple[int, int]] = []
    run_start: int | None = None
    total_frames = len(raw) // frame_bytes
    for index in range(total_frames):
        block = raw[index * frame_bytes : (index + 1) * frame_bytes]
        # PCM16 little-endian RMS without audioop (removed in Python 3.13).
        total = 0
        for offset in range(0, len(block), 2):
            sample = int.from_bytes(block[offset : offset + 2], "little", signed=True)
            total += sample * sample
        rms = math.sqrt(total / max(1, len(block) // 2))
        silent = rms <= threshold
        if silent and run_start is None:
            run_start = index
        elif not silent and run_start is not None:
            quiet_runs.append((run_start, index))
            run_start = None
    if run_start is not None:
        quiet_runs.append((run_start, total_frames))
    min_frames = max(1, round(SILENCE_MIN_SECONDS * 100))
    candidates = [(a, b) for a, b in quiet_runs if b - a >= min_frames]
    if not candidates:
        return None
    a, b = candidates[-1]
    midpoint = start + ((a + b) // 2) * frame
    return min(end - 1, max(start + 1, midpoint))


async def plan_chunks(
    media: MediaProbe,
    *,
    file_index: int,
    tools: MediaTools | None = None,
    max_chunk_seconds: int = MAX_CHUNK_SECONDS,
    detect_silence: bool = True,
) -> list[PlannedChunk]:
    """Plan contiguous, non-overlapping chunks covering every input sample."""
    total = media.total_samples
    max_samples = max(1, int(max_chunk_seconds) * CHUNK_SAMPLE_RATE)
    tools = tools or resolve_tools()
    chunks: list[PlannedChunk] = []
    start = 0
    while start < total:
        end = min(total, start + max_samples)
        if detect_silence and end < total:
            lookback_samples = min(
                end - start,
                SILENCE_LOOKBACK_SECONDS * CHUNK_SAMPLE_RATE,
            )
            window_start = max(start + 1, end - lookback_samples)
            cut = await find_silence_midpoint(media.path, window_start, end, tools=tools)
            if cut is not None and start < cut < end:
                end = cut
        if end <= start:  # pragma: no cover - defensive
            end = min(total, start + max_samples)
        chunks.append(
            PlannedChunk(
                file_index=file_index,
                chunk_index=len(chunks),
                start_sample=start,
                end_sample=end,
            )
        )
        start = end
    if not chunks:  # pragma: no cover - total_samples is at least 1
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="empty_plan")
    if chunks[0].start_sample != 0 or chunks[-1].end_sample != total:
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="coverage")
    for left, right in zip(chunks, chunks[1:]):
        if left.end_sample != right.start_sample:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="gap")
    return chunks


def wav_info(path: Path) -> tuple[int, int, int, int]:
    """``(frames, rate, channels, width)`` for a PCM WAV; rejects other shapes."""
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            frames = handle.getnframes()
    except (OSError, wave.Error) as exc:
        raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason="bad_wav", cause=exc) from exc
    return frames, rate, channels, width


async def extract_chunk(
    input_path: Path,
    output_path: Path,
    start_sample: int,
    end_sample: int,
    *,
    tools: MediaTools | None = None,
    timeout: float = MEDIA_TOTAL_TIMEOUT_SECONDS,
) -> Path:
    """Write one exact-range 16 kHz mono PCM16 WAV, then verify its frame count."""
    input_path = _reject_input(input_path)
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="chunk_exists")
    final_path = output_path
    output_path = output_path.with_name(output_path.name + ".partial")
    if output_path.is_symlink():
        raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="partial_symlink")
    output_path.unlink(missing_ok=True)
    tools = tools or resolve_tools()
    duration = max(0.001, (int(end_sample) - int(start_sample)) / CHUNK_SAMPLE_RATE)
    flt = (
        f"aresample={CHUNK_SAMPLE_RATE},"
        f"atrim=start_sample=0:end_sample={int(end_sample) - int(start_sample)},"
        "asetpts=PTS-STARTPTS"
    )
    argv = [
        tools.ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{int(start_sample) / CHUNK_SAMPLE_RATE:.6f}",
        "-t",
        f"{duration + 0.5:.6f}",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        _wsl_path(input_path, tools.ffmpeg),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        flt,
        "-ac",
        str(CHUNK_CHANNELS),
        "-ar",
        str(CHUNK_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-y",
        _wsl_path(output_path, tools.ffmpeg),
    ]
    try:
        code, _stdout, _stderr = await _run(argv, timeout=timeout, output_cap=1024 * 1024)
        if code != 0:
            raise MediaError(AsrErrorCode.ASR_INVALID_AUDIO, reason=f"ffmpeg_exit_{code}")
        frames, rate, channels, width = wav_info(output_path)
        expected = int(end_sample) - int(start_sample)
        if frames != expected or rate != CHUNK_SAMPLE_RATE or channels != CHUNK_CHANNELS:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="chunk_shape")
        if width != CHUNK_SAMPLE_WIDTH:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="chunk_width")
        if output_path.stat().st_size > MAX_WORK_BYTES:
            raise MediaError(AsrErrorCode.ASR_RESOURCE_LIMIT, reason="chunk_budget")
        os.replace(output_path, final_path)
        return final_path
    finally:
        output_path.unlink(missing_ok=True)


def make_silent_wav(path: Path, seconds: float = 1.0) -> Path:
    """Small deterministic WAV builder for tests/acceptance (not a provider)."""
    frames = max(1, round(float(seconds) * CHUNK_SAMPLE_RATE))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHUNK_CHANNELS)
        handle.setsampwidth(CHUNK_SAMPLE_WIDTH)
        handle.setframerate(CHUNK_SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def temp_media_dir(prefix: str = "asr-media-") -> Path:
    """Create a private temp directory; callers own its removal."""
    return Path(tempfile.mkdtemp(prefix=prefix))


__all__ = [
    "MediaCancelled",
    "MediaError",
    "MediaProbe",
    "MediaTools",
    "PlannedChunk",
    "extract_chunk",
    "find_silence_midpoint",
    "make_silent_wav",
    "normalize_to_wav",
    "parse_probe",
    "plan_chunks",
    "probe",
    "probe_sync",
    "resolve_tools",
    "temp_media_dir",
    "wav_info",
]
