"""Shared isolated fixtures for the ASR-R1 test package.

The app used here mounts the real ``asr`` router without the full application
lifespan (the same pattern as the phase-1 route tests).  Each test gets a fresh
disposable ``DEEPTUTOR_HOME``; the real learning tree and settings are never
read or written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.services.asr import media
from deeptutor.services.asr.provider import ProviderResult
from deeptutor.services.voice.config import STTConfig
from tests.phase1 import helpers

ROUTE_PREFIX = "/api/v1/subjects"


@pytest.fixture
def asr_runtime(tmp_path: Path) -> Iterator[Path]:
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root


@pytest.fixture
def asr_subject(asr_runtime: Path):
    return helpers.make_subject(asr_runtime, "ASR科目")


@pytest.fixture
def asr_client(asr_runtime: Path) -> Iterator[TestClient]:
    from deeptutor.api.routers import asr

    app = FastAPI()
    app.include_router(asr.router, prefix=ROUTE_PREFIX)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def asr_tools() -> media.MediaTools:
    # Explicit env is set by the acceptance command; a missing explicit value is
    # a real dependency failure, not a silently skipped suite.
    return media.resolve_tools()


@pytest.fixture
def fake_config() -> STTConfig:
    return STTConfig(
        model="fake-asr-model",
        provider_name="custom",
        adapter="openai_compat",
        request_style="multipart",
        auth_style="bearer",
        api_key="sk-test-not-real",
        base_url="http://127.0.0.1:9/v1",
        language="zh",
    )


class FakeProvider:
    """Deterministic chunk provider used by the job tests."""

    def __init__(self, text: str = "转写片段", *, delay: float = 0.0) -> None:
        self.text = text
        self.delay = delay
        self.calls: list[dict] = []
        self.fail_once: dict[int, Exception] = {}
        self.fail_always: dict[int, Exception] = {}

    async def transcribe_chunk(self, audio_path: Path, *, language: str = "zh"):
        import asyncio

        index = len(self.calls)
        self.calls.append({"path": str(audio_path), "language": language, "index": index})
        if self.delay:
            await asyncio.sleep(self.delay)
        if index in self.fail_always:
            raise self.fail_always[index]
        if index in self.fail_once:
            raise self.fail_once.pop(index)
        return ProviderResult(text=self.text, model="fake-asr-model", attempts=1)


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


def wav_bytes(seconds: float = 2.0) -> bytes:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="asr-test-wav-"))
    path = media.make_silent_wav(root / "test.wav", seconds)
    payload = path.read_bytes()
    for child in root.iterdir():
        child.unlink()
    root.rmdir()
    return payload


def upload_files(payload: bytes, name: str = "lecture.wav"):
    return [("files", (name, payload, "audio/wav"))]
