"""Starter suggestions — caching, shaping, and staying off the request path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time

import pytest

from deeptutor.services import suggestions
from deeptutor.services.memory.recall import RecallHit


class _FakePathService:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_workspace_dir(self) -> Path:
        return self._root


@pytest.fixture(autouse=True)
def isolated_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route the cache into tmp_path and clear the in-process maps."""
    import deeptutor.services.path_service as path_service

    monkeypatch.setattr(path_service, "get_path_service", lambda: _FakePathService(tmp_path))
    suggestions._inflight.clear()
    suggestions._last_probe.clear()
    yield tmp_path
    suggestions._inflight.clear()
    suggestions._last_probe.clear()


@pytest.fixture
def no_material(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.memory import recall

    monkeypatch.setattr(recall, "recent", lambda **_: [])
    monkeypatch.setattr(recall, "recent_queries", lambda **_: [])


def _hit(surface: str, label: str, age: int = 1) -> RecallHit:
    return RecallHit(surface=surface, label=label, ts="2026-08-15T10:00:00+00:00", days_ago=age)


def _stub_material(monkeypatch: pytest.MonkeyPatch, hits: list[RecallHit]) -> None:
    from deeptutor.services.memory import recall

    monkeypatch.setattr(recall, "recent", lambda **_: list(hits))
    monkeypatch.setattr(recall, "recent_queries", lambda **_: [])


def _stub_llm(monkeypatch: pytest.MonkeyPatch, reply: str) -> list[str]:
    """Replace the LLM with a canned reply; returns the list of prompts seen."""
    import deeptutor.services.llm as llm

    seen: list[str] = []

    async def _complete(prompt: str, **kwargs) -> str:
        seen.append(prompt)
        return reply

    monkeypatch.setattr(llm, "complete", _complete)
    return seen


_THREE = json.dumps(
    [
        {"label": "复习链式法则", "prompt": "把我上次做错的那道链式法则的题再讲一遍"},
        {"label": "练特征值", "prompt": "出五道特征值的练习题给我"},
        {"label": "回到 Agentic RAG", "prompt": "接着上次的 Agentic RAG，讲讲检索怎么排序"},
    ],
    ensure_ascii=False,
)


def _write_cache(root: Path, payload: dict) -> None:
    directory = root / "suggestions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "starters.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ── Shaping ──────────────────────────────────────────────────────────────


def test_sanitize_accepts_a_plain_array() -> None:
    items = suggestions._sanitize(_THREE)

    assert [item.label for item in items] == ["复习链式法则", "练特征值", "回到 Agentic RAG"]
    assert items[0].prompt.startswith("把我上次")


def test_sanitize_accepts_a_fenced_array_with_prose_around_it() -> None:
    raw = f"Sure, here they are:\n```json\n{_THREE}\n```\nHope that helps!"

    assert len(suggestions._sanitize(raw)) == 3


def test_sanitize_discards_a_partial_set() -> None:
    """One lonely line under the composer reads as a rendering bug."""
    raw = json.dumps([{"label": "a", "prompt": "b"}, {"label": "c", "prompt": "d"}])

    assert suggestions._sanitize(raw) == ()


def test_sanitize_keeps_labels_long_enough_to_be_specific() -> None:
    """Naming a real distinction costs words, and that is the whole point.

    A label bound tight enough to force "Explain a topic" would throw away
    every line worth showing, so these realistic ones must survive.
    """
    raw = json.dumps(
        [
            {"label": "How agentic RAG differs from naive RAG", "prompt": "a"},
            {"label": "Why the chain rule underlies backpropagation", "prompt": "b"},
            {"label": "自注意力比 RNN 强在哪一步", "prompt": "c"},
        ],
        ensure_ascii=False,
    )

    assert len(suggestions._sanitize(raw)) == 3


def test_sanitize_drops_items_that_ignored_the_brief() -> None:
    raw = json.dumps(
        [
            {"label": "x" * 80, "prompt": "fine"},  # label is a paragraph
            {"label": "ok", "prompt": "y" * 400},  # prompt is an essay
            {"label": "missing prompt"},
            {"label": "good", "prompt": "a real question"},
        ]
    )

    # Three were dropped, so the batch is short and goes entirely.
    assert suggestions._sanitize(raw) == ()


def test_sanitize_dedupes_repeated_labels() -> None:
    raw = json.dumps(
        [
            {"label": "Same", "prompt": "one"},
            {"label": "same", "prompt": "two"},
            {"label": "Other", "prompt": "three"},
            {"label": "Third", "prompt": "four"},
        ]
    )

    assert [item.label for item in suggestions._sanitize(raw)] == ["Same", "Other", "Third"]


def test_sanitize_strips_quotes_and_collapses_whitespace() -> None:
    raw = json.dumps(
        [
            {"label": '"Quoted"', "prompt": "a  ragged\n\nquestion"},
            {"label": "B", "prompt": "b"},
            {"label": "C", "prompt": "c"},
        ]
    )

    items = suggestions._sanitize(raw)
    assert items[0].label == "Quoted"
    assert items[0].prompt == "a ragged question"


def test_sanitize_rejects_non_arrays() -> None:
    assert suggestions._sanitize('{"label": "x", "prompt": "y"}') == ()
    assert suggestions._sanitize("no json here at all") == ()


# ── Material ─────────────────────────────────────────────────────────────


def test_topics_are_capped_per_surface_and_interleaved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat updates on every turn; without a cap it would be the whole list."""
    _stub_material(
        monkeypatch,
        [_hit("chat", f"Session {i}") for i in range(6)]
        + [_hit("quiz", "What is an eigenvalue?")]
        + [_hit("book", "Calculus notes")],
    )

    topics = suggestions._collect_topics()

    by_surface = [topic.surface for topic in topics]
    assert by_surface.count("chat") == suggestions._MAX_PER_SURFACE
    assert {"quiz", "book"} <= set(by_surface)
    # Every kind gets its first item before any kind gets its second.
    assert by_surface[:3] == ["chat", "quiz", "book"]


def test_topics_merge_kb_queries_from_the_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.memory import recall

    monkeypatch.setattr(recall, "recent", lambda **_: [_hit("chat", "Chain rule")])
    monkeypatch.setattr(
        recall, "recent_queries", lambda **_: [_hit("kb", "how does backprop work")]
    )

    labels = [topic.label for topic in suggestions._collect_topics()]

    assert labels == ["Chain rule", "how does backprop work"]


def test_topics_survive_a_broken_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.memory import recall

    def _boom(**_):
        raise RuntimeError("memory unreadable")

    monkeypatch.setattr(recall, "recent", _boom)
    monkeypatch.setattr(recall, "recent_queries", lambda **_: [_hit("kb", "a query")])

    assert [topic.label for topic in suggestions._collect_topics()] == ["a query"]


# ── Reads ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_without_a_cache_is_empty_and_stale(no_material) -> None:
    result = await suggestions.get_suggestions("zh")

    assert result["suggestions"] == []
    assert result["stale"] is True


@pytest.mark.asyncio
async def test_read_never_calls_the_model(
    monkeypatch: pytest.MonkeyPatch, isolated_scope: Path
) -> None:
    """The request path reads one JSON file and nothing else."""
    _stub_material(monkeypatch, [_hit("chat", "Chain rule")])
    calls = _stub_llm(monkeypatch, _THREE)
    _write_cache(
        isolated_scope,
        {
            "suggestions": [{"label": "cached", "prompt": "from disk"}],
            "language": "zh",
            "generated_at": time.time(),
            "fingerprint": "whatever",
        },
    )

    result = await suggestions.get_suggestions("zh")

    assert [item["label"] for item in result["suggestions"]] == ["cached"]
    assert result["stale"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_expired_cache_is_still_served_while_it_regenerates(
    monkeypatch: pytest.MonkeyPatch, isolated_scope: Path
) -> None:
    _stub_material(monkeypatch, [_hit("chat", "Chain rule")])
    _stub_llm(monkeypatch, _THREE)
    _write_cache(
        isolated_scope,
        {
            "suggestions": [{"label": "yesterday", "prompt": "old"}],
            "language": "zh",
            "generated_at": time.time() - suggestions._TTL_SECONDS - 1,
            "fingerprint": "old",
        },
    )

    result = await suggestions.get_suggestions("zh")

    # Served immediately, flagged for a second look.
    assert [item["label"] for item in result["suggestions"]] == ["yesterday"]
    assert result["stale"] is True

    # The background pass replaces it.
    await asyncio.gather(*suggestions._inflight.values())
    after = await suggestions.get_suggestions("zh")
    assert [item["label"] for item in after["suggestions"]] == [
        "复习链式法则",
        "练特征值",
        "回到 Agentic RAG",
    ]


@pytest.mark.asyncio
async def test_a_language_switch_is_not_served_from_the_other_language(
    isolated_scope: Path, no_material
) -> None:
    _write_cache(
        isolated_scope,
        {
            "suggestions": [{"label": "cached", "prompt": "from disk"}],
            "language": "zh",
            "generated_at": time.time(),
            "fingerprint": "x",
        },
    )

    result = await suggestions.get_suggestions("en")

    assert result["suggestions"] == []
    assert result["stale"] is True


@pytest.mark.asyncio
async def test_probe_is_throttled_across_a_burst_of_loads(
    monkeypatch: pytest.MonkeyPatch, no_material
) -> None:
    scheduled: list[str] = []
    monkeypatch.setattr(
        suggestions, "_regenerate_if_due", lambda language: _noop(scheduled, language)
    )

    for _ in range(5):
        await suggestions.get_suggestions("en")
    await asyncio.gather(*suggestions._inflight.values())

    assert len(scheduled) == 1


async def _noop(sink: list[str], language: str) -> None:
    sink.append(language)


# ── Generation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_material_means_no_model_call(
    monkeypatch: pytest.MonkeyPatch, no_material
) -> None:
    """A brand-new learner has no history to ground a suggestion in."""
    calls = _stub_llm(monkeypatch, _THREE)

    result = await suggestions.refresh_suggestions("en")

    assert result.suggestions == ()
    assert calls == []


@pytest.mark.asyncio
async def test_generation_describes_the_material_in_the_learners_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_material(monkeypatch, [_hit("quiz", "What is an eigenvalue?", age=0)])
    calls = _stub_llm(monkeypatch, _THREE)

    await suggestions.refresh_suggestions("zh")

    assert "错题" in calls[0]
    assert "今天" in calls[0]
    assert "What is an eigenvalue?" in calls[0]


@pytest.mark.asyncio
async def test_a_failing_model_leaves_an_empty_set_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeptutor.services.llm as llm

    _stub_material(monkeypatch, [_hit("chat", "Chain rule")])

    async def _boom(**_):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr(llm, "complete", _boom)

    result = await suggestions.refresh_suggestions("en")

    assert result.suggestions == ()


@pytest.mark.asyncio
async def test_unchanged_material_inside_the_ttl_skips_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_material(monkeypatch, [_hit("chat", "Chain rule")])
    calls = _stub_llm(monkeypatch, _THREE)

    await suggestions.refresh_suggestions("en")
    assert len(calls) == 1

    # Same material, still fresh: the background pass must not spend a call.
    await suggestions._regenerate_if_due("en")
    assert len(calls) == 1

    # New material: it must.
    _stub_material(monkeypatch, [_hit("chat", "Eigenvalues")])
    await suggestions._regenerate_if_due("en")
    assert len(calls) == 2


# ── Isolation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_users_never_see_each_others_suggestions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cache is addressed through the multi-user path service, so one
    user's chips must not leak into another's response."""
    import deeptutor.services.path_service as path_service

    alice, bob = tmp_path / "alice", tmp_path / "bob"
    current = {"root": alice}
    monkeypatch.setattr(path_service, "get_path_service", lambda: _FakePathService(current["root"]))
    _stub_material(monkeypatch, [_hit("chat", "Chain rule")])
    _stub_llm(monkeypatch, _THREE)

    await suggestions.refresh_suggestions("zh")
    mine = await suggestions.get_suggestions("zh")
    assert len(mine["suggestions"]) == 3

    current["root"] = bob
    theirs = await suggestions.get_suggestions("zh")
    assert theirs["suggestions"] == []
