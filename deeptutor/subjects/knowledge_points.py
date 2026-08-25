"""Knowledge-point index (M5) — per-subject knowledge map with links.

Each point is a named node in the subject's knowledge tree. Wrong-book
entries and exam points link in by knowledge-point name, so a point
aggregates its mistakes (and their mastery) and its exam flags.

Storage: ``data/subjects/<id>/knowledge_points.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import uuid

from deeptutor.subjects import store


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "knowledge_points.json"


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


def add_point(subject_id: str, *, name: str, path: str = "", source: str = "manual") -> dict:
    name = name.strip()
    existing = next((p for p in load(subject_id) if p["name"] == name), None)
    if existing is not None:
        return existing
    point = {
        "id": uuid.uuid4().hex[:12],
        "subject_id": subject_id,
        "name": name,
        "path": path.strip() or name,
        "source": source,
        "wrong_ids": [],
        "exam_point_ids": [],
        "created_at": int(time.time()),
    }
    points = load(subject_id)
    points.append(point)
    _save(subject_id, points)
    return point


def add_many(subject_id: str, names: list[str], path: str = "", source: str = "llm") -> list[dict]:
    out = []
    for n in names:
        if n and n.strip():
            out.append(add_point(subject_id, name=n, path=path, source=source))
    return out


def get_point(subject_id: str, point_id: str) -> dict | None:
    return next((p for p in load(subject_id) if p["id"] == point_id), None)


def find_by_name(subject_id: str, name: str) -> dict | None:
    name = name.strip().lower()
    return next((p for p in load(subject_id) if p["name"].strip().lower() == name), None)


def link_wrong_entry(subject_id: str, kp: str, wrong_id: str) -> dict | None:
    """Attach a wrong-book entry to the matching knowledge point."""
    point = find_by_name(subject_id, kp)
    if point is None:
        return None
    points = load(subject_id)
    for p in points:
        if p["id"] == point["id"] and wrong_id not in p["wrong_ids"]:
            p["wrong_ids"].append(wrong_id)
            _save(subject_id, points)
            return p
    return point


def link_exam_point(subject_id: str, kp: str, exam_point_id: str) -> dict | None:
    point = find_by_name(subject_id, kp)
    if point is None:
        return None
    points = load(subject_id)
    for p in points:
        if p["id"] == point["id"] and exam_point_id not in p["exam_point_ids"]:
            p["exam_point_ids"].append(exam_point_id)
            _save(subject_id, points)
            return p
    return point


def aggregate(subject_id: str) -> list[dict]:
    """Knowledge points enriched with wrong-book + exam-point aggregates.

    Each point gains ``wrong_count``, ``mastery`` (mean of linked wrong
    entries, 1.0 when none) and ``exam_count`` so the context summary and
    review guide can rank by weakness.
    """
    from deeptutor.subjects import exam_points as ep_mod, wrong_book

    wrongs = {e["id"]: e for e in wrong_book.load(subject_id) if not e.get("archived")}
    exams = {p["id"]: p for p in ep_mod.load(subject_id) if p.get("confirmed")}
    out = []
    for p in load(subject_id):
        item = dict(p)
        item["wrong_count"] = sum(1 for wid in p.get("wrong_ids", []) if wid in wrongs)
        scores = [
            wrongs[wid].get("mastery", 0.0)
            for wid in p.get("wrong_ids", [])
            if wid in wrongs and wrongs[wid].get("mastery") is not None
        ]
        item["mastery"] = round(sum(scores) / len(scores), 3) if scores else 1.0
        item["exam_count"] = sum(1 for eid in p.get("exam_point_ids", []) if eid in exams)
        out.append(item)
    return out


def context_summary(subject_id: str, limit: int = 12) -> str:
    """Lightweight knowledge-map injection block (常驻轻量层)."""
    points = aggregate(subject_id)
    if not points:
        return ""
    weak = [p for p in points if p["wrong_count"] > 0 or p["exam_count"] > 0]
    weak.sort(key=lambda p: (p["mastery"], -p["wrong_count"]))
    lines = ["【该科目知识点索引】"]
    for p in points[:limit]:
        tags = []
        if p["wrong_count"]:
            tags.append(f"错题{p['wrong_count']}")
        if p["exam_count"]:
            tags.append("考点")
        suffix = f"（{'、'.join(tags)}）" if tags else ""
        lines.append(f"- {p['name']}{suffix}")
    if weak and len(points) > limit:
        lines.append(f"……共 {len(points)} 个知识点，最薄弱：{weak[0]['name']}（掌握度 {weak[0]['mastery']}）")
    return "\n".join(lines)
