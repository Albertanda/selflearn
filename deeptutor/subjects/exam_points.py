"""Exam points (M4) — per-subject final-exam key points with evidence.

Each point records what the teacher stressed as examinable, with a
confidence level, the evidence quote, and a term so stale semesters do
not leak into the current one.

    explicit  明示 — teacher explicitly said it will be on the exam
    emphasis  强调 — repeated/strong emphasis, "常考/很重要" signals
    inferred  推断 — system inference (e.g. overlap with past papers)

Storage: ``data/subjects/<id>/exam_points.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import uuid

from deeptutor.subjects import store

LEVEL_LABELS = {"explicit": "明示考点", "emphasis": "强调考点", "inferred": "推断考点"}


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "exam_points.json"


def load(subject_id: str) -> list[dict]:
    path = _path(subject_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(subject_id: str, points: list[dict]) -> None:
    path = _path(subject_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8")


def add_point(
    subject_id: str,
    *,
    content: str,
    level: str = "inferred",
    evidence: str = "",
    kp: str = "",
    term: str = "",
    source: str = "manual",
    anchor: str = "",
    confirmed: bool = False,
) -> dict:
    if level not in LEVEL_LABELS:
        level = "inferred"
    now = int(time.time())
    point = {
        "id": uuid.uuid4().hex[:12],
        "subject_id": subject_id,
        "content": content.strip(),
        "level": level,
        "evidence": evidence.strip(),
        "kp": kp.strip(),
        "term": term.strip(),
        "source": source,
        "anchor": anchor.strip(),
        "confirmed": bool(confirmed),
        "created_at": now,
    }
    points = load(subject_id)
    points.append(point)
    _save(subject_id, points)
    return point


def add_many(subject_id: str, points: list[dict]) -> list[dict]:
    """Add a batch (detector output) and return the stored points."""
    stored = []
    for p in points:
        stored.append(
            add_point(
                subject_id,
                content=p.get("content", ""),
                level=p.get("level", "inferred"),
                evidence=p.get("evidence", ""),
                kp=p.get("kp", ""),
                term=p.get("term", ""),
                source=p.get("source", "lecture_detection"),
                anchor=p.get("anchor", ""),
                confirmed=False,
            )
        )
    return [s for s in stored if s["content"]]


def list_points(
    subject_id: str, *, term: str | None = None, confirmed: bool | None = None
) -> list[dict]:
    points = load(subject_id)
    if term:
        points = [p for p in points if p["term"] == term]
    if confirmed is not None:
        points = [p for p in points if p["confirmed"] is confirmed]
    return sorted(points, key=lambda p: p.get("created_at", 0), reverse=True)


def set_confirmed(subject_id: str, point_id: str, confirmed: bool = True) -> dict | None:
    points = load(subject_id)
    for p in points:
        if p["id"] == point_id:
            p["confirmed"] = bool(confirmed)
            _save(subject_id, points)
            return p
    return None


def delete(subject_id: str, point_id: str) -> bool:
    points = load(subject_id)
    kept = [p for p in points if p["id"] != point_id]
    if len(kept) == len(points):
        return False
    _save(subject_id, kept)
    return True


def term_summary(subject_id: str, term: str = "", limit: int = 8) -> str:
    """Lightweight injection block: confirmed exam points for the term."""
    points = [p for p in load(subject_id) if p.get("confirmed")]
    if term:
        points = [p for p in points if p["term"] == term]
    if not points:
        return ""
    points.sort(key=lambda p: p.get("created_at", 0), reverse=True)
    lines = ["【本学期期末考点】"]
    for p in points[:limit]:
        level = LEVEL_LABELS.get(p["level"], p["level"])
        kp = f"[{p['kp']}] " if p.get("kp") else ""
        lines.append(f"- {kp}{p['content'][:100]}（{level}）")
    return "\n".join(lines)
