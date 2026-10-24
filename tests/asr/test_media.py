from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import wave

import pytest

from deeptutor.services.asr import media
from deeptutor.subjects.errors import AsrErrorCode


def _tone(path: Path, seconds: float, *, rate: int = 16000) -> Path:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(int(8000 * __import__("math").sin(2 * 3.14159265 * 440 * i / rate)).to_bytes(2, "little", signed=True) for i in range(frames)))
    return path


def test_probe_reports_samples_and_does_not_modify_input(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "中文 录音.wav", 2.0)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    probe = asyncio.run(media.probe(source, tools=asr_tools))
    assert probe.duration_ms == 2000
    assert probe.total_samples == 32000
    assert probe.size_bytes == source.stat().st_size
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_plan_covers_every_sample_without_gaps_or_overlap(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "a.wav", 3.0)
    probe = asyncio.run(media.probe(source, tools=asr_tools))
    chunks = asyncio.run(
        media.plan_chunks(probe, file_index=0, tools=asr_tools, max_chunk_seconds=1)
    )
    assert chunks[0].start_sample == 0
    assert chunks[-1].end_sample == probe.total_samples
    assert all(left.end_sample == right.start_sample for left, right in zip(chunks, chunks[1:]))
    assert all(0 < item.samples <= 16000 for item in chunks)


def test_hard_cut_when_window_has_no_silence(tmp_path, asr_tools):
    source = _tone(tmp_path / "tone.wav", 2.2)
    probe = asyncio.run(media.probe(source, tools=asr_tools))
    chunks = asyncio.run(
        media.plan_chunks(probe, file_index=0, tools=asr_tools, max_chunk_seconds=1)
    )
    assert [item.samples for item in chunks] == [16000, 16000, 3200]
    assert all(item.chunk_id.startswith("f0-") for item in chunks)


def test_extract_chunk_has_exact_pcm_shape_and_frames(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "source.wav", 2.0)
    output = tmp_path / "chunk with space.wav"
    asyncio.run(media.extract_chunk(source, output, 1234, 23456, tools=asr_tools))
    frames, rate, channels, width = media.wav_info(output)
    assert (frames, rate, channels, width) == (22222, 16000, 1, 2)
    assert 44 + 22222 * 2 <= output.stat().st_size <= 22222 * 2 + 2048


def test_extract_refuses_existing_output(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "a.wav", 1.0)
    output = tmp_path / "exists.wav"
    output.write_bytes(b"keep")
    with pytest.raises(Exception) as excinfo:
        asyncio.run(media.extract_chunk(source, output, 0, 100, tools=asr_tools))
    assert excinfo.value.code == AsrErrorCode.ASR_RESOURCE_LIMIT
    assert output.read_bytes() == b"keep"


def test_bad_media_is_a_controlled_invalid_audio(tmp_path, asr_tools):
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not audio")
    with pytest.raises(Exception) as excinfo:
        asyncio.run(media.probe(bad, tools=asr_tools))
    assert excinfo.value.code == AsrErrorCode.ASR_INVALID_AUDIO


def test_missing_explicit_tool_is_dependency_unavailable(tmp_path):
    with pytest.raises(Exception) as excinfo:
        media.resolve_tools(
            {"SELFLEARN_FFMPEG_BIN": str(tmp_path / "missing"), "SELFLEARN_FFPROBE_BIN": "/bin/true"}
        )
    assert excinfo.value.code == AsrErrorCode.ASR_DEPENDENCY_UNAVAILABLE


def test_unicode_and_space_paths_work_with_windows_exe(tmp_path, asr_tools):
    source = media.make_silent_wav(tmp_path / "课堂 录音 测试.wav", 0.3)
    probe = asyncio.run(media.probe(source, tools=asr_tools))
    assert probe.total_samples == 4800


def test_duration_limit_is_rejected_before_planning():
    with pytest.raises(Exception) as excinfo:
        media.parse_probe(
            Path("x.wav"),
            {
                "streams": [
                    {"codec_type": "audio", "sample_rate": "16000", "channels": 1, "duration": "18000"}
                ],
                "format": {"duration": "18000"},
            },
            size_bytes=1,
        )
    assert excinfo.value.code == AsrErrorCode.ASR_DURATION_LIMIT


def test_cancelled_probe_does_not_leave_a_hanging_process(tmp_path):
    source = media.make_silent_wav(tmp_path / "a.wav", 0.2)
    script = tmp_path / "slow-tool"
    script.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    script.chmod(0o755)
    tools = media.MediaTools(str(script), str(script))

    async def run():
        task = asyncio.create_task(media.probe(source, tools=tools, timeout=30))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
