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

import json
import time
from pathlib import Path

from deeptutor.subjects import store

STYLE_LABELS = {
    "examples": "例子与实际应用优先",
    "theory": "理论推导优先",
    "balanced": "两者兼顾",
}
_VALID_STYLES = set(STYLE_LABELS)


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "profile.json"


def _defaults() -> dict:
    return {
        "goals": "",
        "explanation_style": "balanced",
        "facts": [],
        "updated_at": 0,
    }


def load(subject_id: str) -> dict:
    path = _path(subject_id)
    if not path.exists():
        return _defaults()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _defaults()
    merged = _defaults()
    merged.update({k: v for k, v in data.items() if k in merged})
    if merged["explanation_style"] not in _VALID_STYLES:
        merged["explanation_style"] = "balanced"
    return merged


def _save(subject_id: str, profile: dict) -> None:
    profile["updated_at"] = int(time.time())
    path = _path(subject_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def update(subject_id: str, *, goals: str | None = None, explanation_style: str | None = None) -> dict:
    profile = load(subject_id)
    if goals is not None:
        profile["goals"] = goals.strip()
    if explanation_style is not None:
        if explanation_style not in _VALID_STYLES:
            explanation_style = "balanced"
        profile["explanation_style"] = explanation_style
    _save(subject_id, profile)
    return profile


def add_fact(subject_id: str, fact: str) -> dict:
    """Append a durable learner fact (dedup by exact text)."""
    profile = load(subject_id)
    fact = fact.strip()
    if not fact:
        return profile
    facts = profile.get("facts", [])
    if fact not in [f.get("text") for f in facts]:
        facts.append({"text": fact, "ts": int(time.time())})
        profile["facts"] = facts[-20:]  # keep the most recent 20
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
        lines.append("已知事实：" + "；".join(f["text"][:80] for f in facts[-5:]))
    return "\n".join(lines)
