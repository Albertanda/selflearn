from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from deeptutor.services.model_discovery.cache import (
    EMPTY_SUCCESS_TTL,
    FAILURE_COOLDOWN,
    FRESH_SUCCESS_TTL,
    CacheIOError,
    DiscoveryCache,
    cache_state_for,
)
from deeptutor.services.model_discovery.types import (
    Classification,
    DiscoveredModel,
    DiscoveryError,
    DiscoveryErrorCode,
    RuntimeCompatibility,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


def model(model_id: str = "m1") -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        name=model_id,
        services=("llm",),
        classification=Classification.PROVIDER,
        runtime_compatibility=RuntimeCompatibility.SUPPORTED,
    )


def test_empty_ttl_and_fresh_ttl(tmp_path: Path):
    clock = Clock()
    cache = DiscoveryCache(tmp_path / "cache", now=clock)
    cache.save_success(
        fingerprint="a" * 64, service="llm", models=[model()], complete=True, empty=False
    )
    entry = cache.load("a" * 64)
    assert entry is not None
    assert cache_state_for(entry, clock()) == "fresh"
    assert entry.expires_at == clock() + FRESH_SUCCESS_TTL

    clock.advance(hours=1, seconds=1)
    assert cache_state_for(entry, clock()) == "stale"
    cache.save_success(
        fingerprint="b" * 64, service="llm", models=[], complete=True, empty=True
    )
    empty = cache.load("b" * 64)
    assert empty is not None
    assert empty.status == "empty"
    assert empty.expires_at == clock() + EMPTY_SUCCESS_TTL


def test_failure_preserves_success_payload_and_fetched_at(tmp_path: Path):
    clock = Clock()
    cache = DiscoveryCache(tmp_path / "cache", now=clock)
    cache.save_success(
        fingerprint="a" * 64, service="llm", models=[model("kept")], complete=True, empty=False
    )
    success = cache.load("a" * 64)
    assert success is not None
    fetched = success.fetched_at
    clock.advance(minutes=3)
    stored = cache.record_failure(
        fingerprint="a" * 64,
        service="llm",
        error=DiscoveryError(DiscoveryErrorCode.TIMEOUT, "slow", True),
    )
    assert stored.fetched_at == fetched
    assert [item.id for item in stored.models] == ["kept"]
    assert stored.last_failure_at == clock()
    assert stored.in_failure_cooldown(clock())
    clock.advance(seconds=61)
    assert not stored.in_failure_cooldown(clock())


def test_cache_is_0600_and_only_stores_digest_and_sanitized_models(tmp_path: Path):
    cache_root = tmp_path / "cache"
    cache = DiscoveryCache(cache_root)
    cache.save_success(
        fingerprint="c" * 64,
        service="stt",
        models=[model("qwen3-asr-flash")],
        complete=True,
        empty=False,
    )
    path = cache_root / f"{'c' * 64}.json"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct(cache_root.stat().st_mode & 0o777) == "0o700"
    raw = path.read_text(encoding="utf-8")
    assert "sk-" not in raw
    assert "https://" not in raw
    assert "api_key" not in raw
    payload = json.loads(raw)
    assert payload["connection_fingerprint"] == "c" * 64
    assert "base_url" not in payload


def test_corrupt_cache_is_ignored_and_replaced(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir(parents=True)
    path = root / f"{'d' * 64}.json"
    path.write_text("{not json", encoding="utf-8")
    cache = DiscoveryCache(root)
    assert cache.load("d" * 64) is None
    assert not path.exists()
    cache.save_success(
        fingerprint="d" * 64, service="llm", models=[model()], complete=True, empty=False
    )
    assert cache.load("d" * 64) is not None


def test_capacity_prunes_oldest_but_keeps_current(tmp_path: Path):
    root = tmp_path / "cache"
    cache = DiscoveryCache(root, max_entries=2)
    for index in range(3):
        cache.save_success(
            fingerprint=f"{index:064x}",
            service="llm",
            models=[model(f"m{index}")],
            complete=True,
            empty=False,
        )
        # mtime granularity can otherwise make the order ambiguous.
        os.utime(root / f"{index:064x}.json", (index + 1, index + 1))
    remaining = {path.stem for path in root.glob("*.json")}
    assert len(remaining) == 2
    assert f"{0:064x}" not in remaining
    assert f"{2:064x}" in remaining


def test_write_failure_is_reported_as_cache_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = DiscoveryCache(tmp_path / "cache")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(CacheIOError):
        cache.save_success(
            fingerprint="e" * 64,
            service="llm",
            models=[model()],
            complete=True,
            empty=False,
        )


def test_fingerprint_mismatch_is_not_returned(tmp_path: Path):
    cache = DiscoveryCache(tmp_path / "cache")
    cache.save_success(
        fingerprint="f" * 64, service="llm", models=[model()], complete=True, empty=False
    )
    path = tmp_path / "cache" / f"{'f' * 64}.json"
    payload = json.loads(path.read_text())
    payload["connection_fingerprint"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert cache.load("f" * 64) is None
