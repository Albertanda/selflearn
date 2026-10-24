"""Subject profile (M5+) — per-subject learner profile for injection.

Holds the learner's goals, answer-style preference and notable facts so
the chat pipeline can inject them as part of the lightweight context
layer instead of relying on raw history.

Answer style (``explanation_style``):
    examples — 偏好用例子和实际应用说明
    theory   — 偏好先搞懂理论/证明
    balanced — 两者兼顾（默认）
"""

from __future__ import annotations

from pathlib import Path
import time

from deeptutor.subjects import json_store, store

PROFILE_NAME = "profile.json"
#: Keep the most recent N facts (unchanged policy).
MAX_FACTS = 20

STYLE_LABELS = {
    "examples": "例子与实际应用优先",
    "theory": "理论推导优先",
    "balanced": "两者兼顾",
}
_VALID_STYLES = set(STYLE_LABELS)


def _path(subject_id: str) -> Path:
    """The profile file, confined before anything opens it."""
    return store.subject_data_path(subject_id, PROFILE_NAME)


def _defaults() -> dict:
    """A **fresh** default profile.

    Built per call so the mutable ``facts`` list cannot be shared between
    callers — a cached default would let one subject's appended fact appear in
    another subject's profile before it was ever saved.
    """
    return {
        "goals": "",
        "explanation_style": "balanced",
        "facts": [],
        "updated_at": 0,
    }


def _merge(stored: dict) -> dict:
    """Defaults for absent keys, stored values (including unknown) for the rest.

    An absent optional field is a legacy record and takes its default; an
    explicitly wrong *type* is corruption. In particular an unknown but
    string-valued ``explanation_style`` keeps the existing "balanced" fallback,
    while a list/dict/int style is refused rather than "repaired".
    """
    merged = _defaults()
    merged.update(stored)

    # A key that is *absent* is a legacy record and takes its default. A key
    # that is present with an explicit `null`/wrong type is corruption — the
    # two must not collapse into "treat it as missing".
    if "goals" in stored:
        goals = stored["goals"]
        if not isinstance(goals, str):
            raise json_store.corrupt_error(PROFILE_NAME, "goals 不是字符串")
        merged["goals"] = goals

    if "explanation_style" in stored:
        style = stored["explanation_style"]
        if not isinstance(style, str):
            raise json_store.corrupt_error(PROFILE_NAME, "explanation_style 不是字符串")
        merged["explanation_style"] = style if style in _VALID_STYLES else "balanced"

    if "facts" in stored:
        facts = stored["facts"]
        if not isinstance(facts, list):
            raise json_store.corrupt_error(PROFILE_NAME, "facts 不是数组")
        for index, item in enumerate(facts):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise json_store.corrupt_error(
                    PROFILE_NAME, "fact 缺少合法 text", index=index
                )
            stamp = item.get("ts")
            if "ts" in item and (
                isinstance(stamp, bool) or not isinstance(stamp, (int, float))
            ):
                raise json_store.corrupt_error(
                    PROFILE_NAME, "fact 的 ts 不是数值", index=index
                )
        merged["facts"] = facts

    if "updated_at" in stored:
        updated = stored["updated_at"]
        if isinstance(updated, bool) or not isinstance(updated, (int, float)):
            raise json_store.corrupt_error(PROFILE_NAME, "updated_at 不是数值")
        merged["updated_at"] = updated

    return merged


def load(subject_id: str) -> dict:
    """Load the profile.

    Missing file -> a fresh default profile. An **existing but damaged** file
    raises: returning defaults for a corrupt profile is how a learner's goals
    and facts get silently replaced by an empty profile on the next update.
    """
    path = _path(subject_id)
    return _merge(json_store.read_object(path, default=_defaults()))


def _save(subject_id: str, profile: dict) -> None:
    """Stamp ``updated_at`` and atomically write (caller holds the lock)."""
    profile["updated_at"] = int(time.time())
    path = _path(subject_id)
    json_store.atomic_write_object(path, profile)


def update(
    subject_id: str, *, goals: str | None = None, explanation_style: str | None = None
) -> dict:
    """Update goals/style under the subject lock, keeping unknown fields."""
    if goals is not None and not isinstance(goals, str):
        raise json_store.invalid_input("学习目标必须是字符串")
    if explanation_style is not None and not isinstance(explanation_style, str):
        raise json_store.invalid_input("回答方式偏好必须是字符串")

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(PROFILE_NAME)
        profile = _merge(tx.read_object(path, default=_defaults()))
        if goals is not None:
            profile["goals"] = goals.strip()
        if explanation_style is not None:
            if explanation_style not in _VALID_STYLES:
                explanation_style = "balanced"
            profile["explanation_style"] = explanation_style
        _save(subject_id, profile)
        return profile


def add_fact(subject_id: str, fact: str) -> dict:
    """Append a durable learner fact (dedup by exact text, keep the last 20).

    Read, dedup check and write share one lock, so two concurrent facts cannot
    overwrite each other.
    """
    if not isinstance(fact, str):
        raise json_store.invalid_input("事实内容必须是字符串")
    cleaned = fact.strip()

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(PROFILE_NAME)
        profile = _merge(tx.read_object(path, default=_defaults()))
        if not cleaned:
            return profile
        facts = profile.get("facts") or []
        if cleaned not in [f.get("text") for f in facts]:
            facts.append({"text": cleaned, "ts": int(time.time())})
            profile["facts"] = facts[-MAX_FACTS:]
            _save(subject_id, profile)
        return profile


def context_summary(subject_id: str) -> str:
    """Lightweight profile injection block."""
    profile = load(subject_id)
    lines = ["【用户画像】"]
    style = STYLE_LABELS.get(profile.get("explanation_style", "balanced"), "两者兼顾")
    lines.append(f"回答方式偏好：{style}。请按此偏好组织讲解（如偏好例子则多用实例与应用场景，如偏好理论则先讲清推导与证明）。")
    if profile.get("goals"):
        lines.append(f"学习目标：{profile['goals'][:120]}")
    facts = profile.get("facts") or []
    if facts:
        lines.append("已知事实：" + "；".join(str(f.get("text", ""))[:80] for f in facts[-5:]))
    return "\n".join(lines)
