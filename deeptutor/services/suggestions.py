"""Starter suggestions — the three lines offered under the home composer.

What makes one of these worth showing is a jump, not a summary. The material
is a set of traces — a session titled "Agentic RAG retrieval flow", a quiz
question, a knowledge-base search. Restating a trace ("接着讲 Agentic RAG 的检索
流程") proposes nothing: the learner already knows they were there. Naming a
field ("探索一下检索") proposes nothing either. What earns the click is the
specific thing about that subject worth understanding next — "Agentic RAG 和
naive RAG 的检索差在哪". Same root, one step further.

So ``label`` is that proposal, and it names an idea, a distinction, a
mechanism or a question — never an activity. ``prompt`` is what gets *sent as
the learner's own message* when they click, so it is first-person, complete,
and pointed enough that answering it teaches something.

The jump has a floor: every proposal must be traceable to the material. One
step beyond what a trace literally says is the point; a subject with no root in
it is invention, and invention is worse than silence here.

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

Empty is a valid answer. A learner with no usable history gets no lines and no
LLM call, and the frontend renders nothing at all — generic copy in that slot
would teach people to stop reading it. But empty is only *cached* when it is
the right answer: an empty result produced despite having material is a
failure, and writing it would pin that failure in place for a whole TTL.
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
# How much history shapes the lines. A month rather than a week: labels are
# deduplicated by name and capped per surface, so a long window does not mean a
# long list — it means a learner who spent this week on one thing still has
# something to be offered. A week left an active user with a single usable
# trace once repeats were collapsed.
_LOOKBACK_DAYS = 30
_MAX_TOPICS = 8
# Per surface, so chat cannot crowd out the quiz and the KB. The whole point of
# reading every surface is that the three differ in kind.
_MAX_PER_SURFACE = 3
# Below this a label carries no subject to propose anything about — a knowledge
# base named "q", a search for "q2", an untitled draft. They are real activity
# and recall is right to return them; they just cannot ground a suggestion, and
# left in they crowd out traces that can.
_MIN_TOPIC_CHARS = 3
# Titles a surface assigns before the learner (or the model) names the thing.
# They are the *newest* rows by definition — a conversation is created before
# it is titled — so without this they take the per-surface budget and leave the
# named work outside it. Mirrors ``DEFAULT_SESSION_TITLE`` in
# ``web/lib/session-title.ts``; drifting means one placeholder slips through,
# which costs a suggestion rather than breaking anything.
_PLACEHOLDER_LABELS = frozenset(
    {
        "new conversation",
        "new chat",
        "新对话",
        "untitled",
        "untitled draft",
        "无标题",
    }
)
# The line the learner reads, and the message behind it. Over-long output means
# the model ignored the brief; the item is dropped rather than truncated,
# because half a sentence is worse than one fewer starting point. The label
# bound is generous enough for "How agentic RAG differs from naive RAG" —
# naming a real distinction costs words, and that is the whole point.
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
        stripped = label.strip()
        if len(stripped) < _MIN_TOPIC_CHARS or stripped.casefold() in _PLACEHOLDER_LABELS:
            return
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


_SYSTEM_EN = """You propose the three things a learner should explore next. Each is one line they click to begin.

You are given traces of what they have been working on — conversations, practice questions, searches, documents. Your job is to see the *subject* behind those traces and name something specific about it that is worth understanding.

Each proposal is an object with two fields:
- "label": the line they read. 4 to 10 words, no ending punctuation. It names a specific idea, distinction, mechanism or question — never an activity.
- "prompt": the message sent as the learner's own words when they click. First person, complete, and pointed enough that a good answer teaches them something.

The move you are making, in one example:
  Trace: [conversation, 2d ago] Agentic RAG retrieval flow
  GOOD: "How agentic RAG differs from naive RAG"
  BAD:  "Continue the Agentic RAG conversation"  <- restates the trace; proposes nothing to understand
  BAD:  "Explore retrieval"                      <- names a field, not a question

Other good shapes: "Why the chain rule underlies backpropagation" / "Where self-attention beats a plain RNN" / "What an eigenvalue actually measures" / "When BM25 still beats embeddings"

Rules:
- Reply with ONLY a JSON array of exactly 3 such objects. No prose, no markdown fence.
- Every proposal must be traceable to the material below. Going one step beyond what it literally says is the point — but never introduce a subject with no root in it.
- The material is raw activity and some of it is noise: a scratch file, a one-word search, a conversation that went nowhere. Skip those and build on the traces that carry a real subject. Three proposals from two good traces beat three that include one about "hello".
- Make the three differ: different subjects from the material, and different kinds of question (a distinction, a mechanism, a why, a boundary case).
- No greetings, no emoji, no quotes around the fields' text."""

_SYSTEM_ZH = """你要提出三个"接下来值得探索什么"。每一个都是一行字，学习者点一下就开始。

给你的是这个学习者最近留下的痕迹——对话、错题、检索、文档。你要做的是：看出这些痕迹背后是什么**学科内容**，然后点出关于它的、一个具体的、值得搞懂的东西。

每一个是一个对象，含两个字段：
- "label"：学习者读到的那行字。8 到 20 个字，结尾不加标点。它点出的是一个具体的概念、区别、机制或问题，绝不是一类活动。
- "prompt"：学习者点击后以自己的身份发出的那句话。第一人称、完整、问得足够到位，好的回答能让他真的学到东西。

你要做的这个跃迁，看一个例子：
  痕迹：[对话，2 天前] Agentic RAG 的检索流程
  好："Agentic RAG 和 naive RAG 的检索差在哪"
  差："接着讲 Agentic RAG 的检索流程"  <- 只是把痕迹复述一遍，没提出任何要搞懂的东西
  差："探索一下检索"                    <- 说的是一个领域，不是一个问题

其他好的形态："为什么链式法则是反向传播的基础" / "自注意力比 RNN 强在哪一步" / "特征值到底在度量什么" / "什么时候 BM25 反而比向量检索准"

规则：
- 只回复一个 JSON 数组，正好 3 个这样的对象。不要有任何解释文字，不要 markdown 代码块。
- 每一个都必须能追溯到下面的素材。比素材字面上说的**多走一步**正是要点——但绝不能引入素材里毫无根据的话题。
- 素材是原始活动记录，其中有噪音：随手建的文件、一个词的检索、没聊起来的对话。跳过它们，只在真正有内容的痕迹上做文章。宁可三个都从两条好素材里长出来，也不要有一个是关于 "hello" 的。
- 三个之间要有区别：取素材里不同的内容，也问不同类型的问题（一个区别、一个机制、一个为什么、一个边界情况）。
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


async def _generate(language: str, topics: list[_Topic]) -> SuggestionSet:
    """Build a fresh set from *topics*. Always returns one — empty on failure.

    Takes the material rather than collecting it, so one pass reads the
    surfaces once and every downstream decision — the fingerprint, whether an
    empty result is meaningful — is made about the same snapshot.
    """
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
        f"这个学习者最近留下的痕迹：\n{_render_topics(topics, zh)}\n\n请提出那三个探索方向。"
        if zh
        else (
            "Traces this learner has left recently:\n"
            f"{_render_topics(topics, zh)}\n\nPropose the three things worth exploring next."
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


async def _generate_and_cache(language: str, topics: list[_Topic]) -> SuggestionSet:
    """Generate from *topics* and cache the result — unless it is a failure.

    An empty result is only written when it is the *right* answer: there was no
    material to work from, and saying so costs nothing to repeat. An empty
    result produced *despite* having material means the call failed or the
    model ignored the brief, and writing that would pin the failure in place
    for a full TTL — the fingerprint would keep matching, so the background
    pass would see nothing due and never retry. Those are dropped instead, and
    the next visit tries again.
    """
    value = await _generate(language, topics)
    if value.suggestions or not topics:
        _save(value)
    return value


async def refresh_suggestions(language: str = "en") -> SuggestionSet:
    """Generate a new set now and cache it. For the manual reroll."""
    return await _generate_and_cache(language, _collect_topics())


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
    await _generate_and_cache(language, topics)


def _schedule_probe(language: str) -> None:
    """Check (and maybe regenerate) in the background, throttled and deduped.

    The throttle is keyed by scope *and* language. A cached set in one language
    is not an answer for another, so a learner whose UI is Chinese must not be
    held behind a throttle stamped by an English probe — that combination
    leaves them looking at an empty slot until the interval expires, with a
    perfectly fresh cache sitting there in the wrong language.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    scope = _scope_key()
    key = f"{scope}\0{language}"
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
