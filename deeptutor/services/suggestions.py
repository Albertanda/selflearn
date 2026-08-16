"""Starter suggestions — the three lines offered under the home composer.

Each is two strings that do different jobs. ``label`` is the line the learner
reads, and it has one job: name the specific thing worth doing next. "Explain a
topic" names an activity and would fit any learner's screen; "把链式法则的直觉
讲透" names theirs. ``prompt`` is what gets *sent as their own message* when
they click, so it has to be first-person, complete, and specific enough to
answer — "把我上次做错的那道链式法则的题再讲一遍", not "你上次在学链式法则",
which a model can only agree with.

Never on the request path
-------------------------
An LLM call is far too slow to sit between a click and a rendered page. So
reads are stale-while-revalidate: :func:`get_suggestions` returns whatever is
cached immediately — even if stale, even if empty — and schedules the work
behind the response. The next visit gets the new set.

Reading the cache is the *only* thing that happens synchronously: one small
JSON file. Deciding whether the material changed means walking seven surfaces,
which is cheap but not free, so that decision lives in the background task
too, throttled to at most once a minute per user.

When it regenerates
-------------------
The background pass regenerates when the material changed (a fingerprint over
the labels) or when the set is older than :data:`_TTL_SECONDS` — the first is
when the *content* should change, the second is so the same three lines do not
greet someone all week. A manual refresh bypasses both and generates
synchronously, because there a human is deliberately waiting.

Empty is a valid answer. A learner with no history gets no generated lines and
no LLM call; the frontend shows a fixed set of product starters instead, which
is honest about knowing nothing yet.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# How many starting points the home screen offers. One per line, so fewer than
# three reads as a stub and more turns the empty screen into a menu.
_COUNT = 3
# Long enough that the same three lines are not re-generated all afternoon,
# short enough to feel responsive to a day's work.
_TTL_SECONDS = 6 * 3600
# Floor between two background material checks for one user. Page loads can
# come in bursts (navigation, refresh, a second tab); the material cannot
# meaningfully change that fast.
_PROBE_INTERVAL_SECONDS = 60.0
_LLM_TIMEOUT = 25.0
# How much history shapes the lines.
_LOOKBACK_DAYS = 7
_MAX_TOPICS = 8
# Per surface, so three chats cannot crowd out the quiz and the KB. The whole
# point of reading every surface is that the three differ in kind.
_MAX_PER_SURFACE = 2
# The line the learner reads, and the message behind it. Over-long output means
# the model ignored the brief; the item is dropped rather than truncated,
# because half a sentence is worse than one fewer starting point. The label
# bound is generous enough for "Redo the two eigenvalue questions you missed" —
# naming the actual thing costs words, and that specificity is the point.
_MAX_LABEL_CHARS = 60
_MAX_PROMPT_CHARS = 240

# One in-flight regeneration per scope; a burst of page loads must not fan out
# into a burst of LLM calls.
_inflight: dict[str, asyncio.Task[Any]] = {}
# Last time a scope's material was checked, for the throttle above. In-process
# only: losing it on restart costs one extra walk.
_last_probe: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One starting point: what it says, and what it sends."""

    label: str
    prompt: str

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "prompt": self.prompt}


@dataclass(frozen=True, slots=True)
class SuggestionSet:
    """The lines currently on offer, plus what they were generated from."""

    suggestions: tuple[Suggestion, ...]
    language: str
    generated_at: float
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [item.to_dict() for item in self.suggestions],
            "language": self.language,
            "generated_at": self.generated_at,
            "fingerprint": self.fingerprint,
        }


# ── Cache ────────────────────────────────────────────────────────────────


def _cache_path():
    from deeptutor.services.path_service import get_path_service

    directory = get_path_service().get_workspace_dir() / "suggestions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "starters.json"


def _scope_key() -> str:
    """Identifies whose suggestions these are.

    The cache path already resolves per user through the multi-user path
    service, so it doubles as the scope key for the in-flight and throttle
    maps — no separate notion of identity to keep in sync with the one that
    decides where the file lands.
    """
    try:
        return str(_cache_path())
    except Exception:  # pragma: no cover - defensive
        return "<unresolved>"


def _load() -> SuggestionSet | None:
    try:
        path = _cache_path()
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = tuple(
            Suggestion(label=str(item["label"]), prompt=str(item["prompt"]))
            for item in (raw.get("suggestions") or [])
            if isinstance(item, dict) and item.get("label") and item.get("prompt")
        )
        return SuggestionSet(
            suggestions=items,
            language=str(raw.get("language") or "en"),
            generated_at=float(raw.get("generated_at") or 0.0),
            fingerprint=str(raw.get("fingerprint") or ""),
        )
    except Exception:
        logger.debug("suggestions cache unreadable", exc_info=True)
        return None


def _save(value: SuggestionSet) -> None:
    try:
        path = _cache_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(value.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception:
        logger.debug("suggestions cache unwritable", exc_info=True)


# ── Material ─────────────────────────────────────────────────────────────

# What each surface is called when it is described to the model. Deliberately
# the learner's vocabulary, not the codebase's: "错题" is a thing a learner
# recognises, "quiz surface" is not.
_SURFACE_LABELS_EN: dict[str, str] = {
    "chat": "conversation",
    "quiz": "practice question",
    "notebook": "note",
    "kb": "knowledge base",
    "book": "book",
    "cowriter": "document",
    "partner": "conversation",
}
_SURFACE_LABELS_ZH: dict[str, str] = {
    "chat": "对话",
    "quiz": "错题",
    "notebook": "笔记",
    "kb": "知识库",
    "book": "书",
    "cowriter": "文档",
    "partner": "对话",
}


@dataclass(frozen=True, slots=True)
class _Topic:
    surface: str
    label: str
    days_ago: int | None


def _collect_topics() -> list[_Topic]:
    """Recent activity, spread across surfaces rather than dominated by one.

    Chat updates on every turn, so a plain newest-first list is almost all
    chat. Taking a bounded number per surface and interleaving them is what
    makes three starting points of three different kinds possible.
    """
    from deeptutor.services.memory import recall

    by_surface: dict[str, list[_Topic]] = {}

    def _add(surface: str, label: str, age: int | None) -> None:
        bucket = by_surface.setdefault(surface, [])
        if len(bucket) >= _MAX_PER_SURFACE:
            return
        if any(existing.label.casefold() == label.casefold() for existing in bucket):
            return
        bucket.append(_Topic(surface=surface, label=label, days_ago=age))

    try:
        for hit in recall.recent(days=_LOOKBACK_DAYS, limit=_MAX_TOPICS * 4):
            _add(hit.surface, hit.label, hit.days_ago)
    except Exception:
        logger.debug("suggestions: recall.recent failed", exc_info=True)

    try:
        for hit in recall.recent_queries(days=_LOOKBACK_DAYS, limit=_MAX_TOPICS):
            _add(hit.surface, hit.label, hit.days_ago)
    except Exception:
        logger.debug("suggestions: recall.recent_queries failed", exc_info=True)

    # Round-robin across surfaces: every kind gets its first item before any
    # kind gets its second.
    topics: list[_Topic] = []
    for rank in range(_MAX_PER_SURFACE):
        for bucket in by_surface.values():
            if rank < len(bucket):
                topics.append(bucket[rank])
    return topics[:_MAX_TOPICS]


def _fingerprint(topics: list[_Topic], language: str) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(language.encode("utf-8"))
    for topic in topics:
        digest.update(b"\0")
        digest.update(f"{topic.surface}:{topic.label}".encode("utf-8"))
    return digest.hexdigest()[:16]


# ── Generation ───────────────────────────────────────────────────────────


_SYSTEM_EN = """You write the three starting points a learning app offers its learner. Each is one line of text they click to begin.

Each is an object with two fields:
- "label": the line they read. 4 to 9 words, no ending punctuation. It MUST name the specific thing from the material — the concept, the question, the document. It is a proposal for what to do next, not a category of activity.
- "prompt": the message sent as the learner's own words when they click. First person, complete, specific enough to answer directly.

The single most important rule: be concrete. A line that could appear in any learner's app has failed.
- BAD: "Explain a topic" / "Review your notes" / "Practise some questions" — these name an activity, not a subject.
- GOOD: "Build intuition for the chain rule" / "Redo the two eigenvalue questions you missed" / "Pick up where Agentic RAG retrieval left off"

Rules:
- Reply with ONLY a JSON array of exactly 3 such objects. No prose, no markdown fence.
- Every line must be grounded in the material given. Name what is actually there; never invent a topic.
- Make the three differ — different items from the material, and different things to do with them (explain, practise, review, go deeper).
- No greetings, no emoji, no quotes around the fields' text."""

_SYSTEM_ZH = """你要为一个学习应用写出三个"从这里开始"的入口。每一个都是一行字，学习者点一下就开始。

每一个是一个对象，含两个字段：
- "label"：学习者读到的那行字。8 到 16 个字，结尾不加标点。必须点出素材里那个**具体**的东西——具体的概念、具体的题、具体的文档。它是一个"接下来做这个"的提议，不是一类活动的名称。
- "prompt"：学习者点击后以自己的身份发出的那句话。第一人称、完整、具体到可以直接回答。

最重要的一条规则：要具体。一句放在谁的界面上都成立的话，就是失败的。
- 差："讲解一个主题" / "复习一下笔记" / "做几道练习题"——这些说的是活动类型，不是具体内容。
- 好："把链式法则的直觉讲透" / "重做上次错的那两道特征值" / "接着 Agentic RAG 的检索排序讲"

规则：
- 只回复一个 JSON 数组，正好 3 个这样的对象。不要有任何解释文字，不要 markdown 代码块。
- 每一行都要基于下面给出的素材，点出真实存在的内容，绝不编造。
- 三个之间要有区别——取素材里不同的东西，也做不同的事（讲解、练习、复习、深入）。
- 不要问候语、不要 emoji、字段文本里不要加引号。"""


def _is_zh(language: str) -> bool:
    return str(language or "en").lower().startswith("zh")


def _render_topics(topics: list[_Topic], zh: bool) -> str:
    labels = _SURFACE_LABELS_ZH if zh else _SURFACE_LABELS_EN
    lines: list[str] = []
    for topic in topics:
        kind = labels.get(topic.surface, topic.surface)
        if topic.days_ago is None:
            when = ""
        elif zh:
            when = "，今天" if topic.days_ago == 0 else f"，{topic.days_ago} 天前"
        else:
            when = ", today" if topic.days_ago == 0 else f", {topic.days_ago}d ago"
        lines.append(f"- [{kind}{when}] {topic.label}")
    return "\n".join(lines)


def _sanitize(raw: str) -> tuple[Suggestion, ...]:
    """Exactly :data:`_COUNT` usable lines, or nothing at all.

    Partial output is discarded rather than shown: one lonely line under the
    composer reads as a rendering bug, and the caller has a fixed set of
    starters that is better than that.
    """
    from deeptutor.utils.json_parser import parse_json_response

    decoded = parse_json_response(raw, fallback=None)
    if not isinstance(decoded, list):
        return ()

    items: list[Suggestion] = []
    seen: set[str] = set()
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        label = " ".join(str(entry.get("label") or "").split()).strip("\"'“”‘’ ")
        prompt = " ".join(str(entry.get("prompt") or "").split()).strip("\"'“”‘’ ")
        if not label or not prompt:
            continue
        if len(label) > _MAX_LABEL_CHARS or len(prompt) > _MAX_PROMPT_CHARS:
            continue
        if label.casefold() in seen:
            continue
        seen.add(label.casefold())
        items.append(Suggestion(label=label, prompt=prompt))

    return tuple(items[:_COUNT]) if len(items) >= _COUNT else ()


async def _generate(language: str) -> SuggestionSet:
    """Build a fresh set. Always returns one — empty on any failure."""
    topics = _collect_topics()
    fingerprint = _fingerprint(topics, language)
    empty = SuggestionSet(
        suggestions=(),
        language=language,
        generated_at=time.time(),
        fingerprint=fingerprint,
    )
    if not topics:
        # Nothing to ground a suggestion in. Say so instead of asking a model
        # to invent a learning history.
        return empty

    zh = _is_zh(language)
    user_prompt = (
        f"学习者最近接触的内容：\n{_render_topics(topics, zh)}\n\n请写出那三个按钮。"
        if zh
        else (
            "The learner has recently been working on:\n"
            f"{_render_topics(topics, zh)}\n\nWrite the three starting points."
        )
    )

    try:
        from deeptutor.services.llm import complete

        raw = await asyncio.wait_for(
            complete(
                prompt=user_prompt,
                system_prompt=_SYSTEM_ZH if zh else _SYSTEM_EN,
                temperature=0.8,  # suggestions may vary; these are not facts
                max_tokens=500,
            ),
            timeout=_LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.debug("suggestions LLM call timed out")
        return empty
    except Exception:
        logger.debug("suggestions LLM call failed", exc_info=True)
        return empty

    return SuggestionSet(
        suggestions=_sanitize(raw),
        language=language,
        generated_at=time.time(),
        fingerprint=fingerprint,
    )


# ── Public API ───────────────────────────────────────────────────────────


def _is_fresh(cached: SuggestionSet | None, language: str, *, now: float) -> bool:
    return (
        cached is not None
        and cached.language == language
        and now - cached.generated_at <= _TTL_SECONDS
    )


async def refresh_suggestions(language: str = "en") -> SuggestionSet:
    """Generate a new set now and cache it. For the manual reroll."""
    value = await _generate(language)
    _save(value)
    return value


async def _regenerate_if_due(language: str) -> None:
    """The background pass: work out whether anything is due, then do it.

    Walking the surfaces to fingerprint the material happens here rather than
    on the request path — the answer only decides whether to spend an LLM call,
    and acting on it one page load later is exactly what stale-while-revalidate
    means.
    """
    topics = _collect_topics()
    fingerprint = _fingerprint(topics, language)
    cached = _load()
    if _is_fresh(cached, language, now=time.time()) and cached.fingerprint == fingerprint:
        return
    await refresh_suggestions(language)


def _schedule_probe(language: str) -> None:
    """Check (and maybe regenerate) in the background, throttled and deduped."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = _scope_key()
    now = time.monotonic()
    pending = _inflight.get(key)
    if pending is not None and not pending.done():
        return
    if now - _last_probe.get(key, 0.0) < _PROBE_INTERVAL_SECONDS:
        return
    _last_probe[key] = now

    async def _go() -> None:
        try:
            await _regenerate_if_due(language)
        except Exception:
            logger.debug("background suggestion refresh failed", exc_info=True)
        finally:
            if _inflight.get(key) is task:
                _inflight.pop(key, None)

    task = loop.create_task(_go())
    _inflight[key] = task


async def get_suggestions(language: str = "en") -> dict[str, Any]:
    """The lines to show now, plus whether a fresher set is being made.

    Returns immediately, reading one small JSON file. An empty list is a real
    answer — a new learner has nothing to suggest from — and ``stale`` tells
    the caller whether it is worth looking again shortly.
    """
    cached = _load()
    fresh = _is_fresh(cached, language, now=time.time())
    _schedule_probe(language)

    if cached is not None and cached.language == language:
        return {**cached.to_dict(), "stale": not fresh}
    return {
        "suggestions": [],
        "language": language,
        "generated_at": 0.0,
        "fingerprint": "",
        "stale": True,
    }


__all__ = [
    "Suggestion",
    "SuggestionSet",
    "get_suggestions",
    "refresh_suggestions",
]
