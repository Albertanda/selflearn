"""Wrong-question book (M3) — per-subject mistake collection with mastery.

Each entry records a question the learner got wrong (or asked about), its
knowledge point, and an attempt history. Mastery is computed by the same
recency-weighted policy as ``learning.mastery.compute_mastery`` and mapped
to four status levels:

    repeated  反复错  — multiple errors (>=2) or low score after recovery
    missed    错过    — one error, not yet re-verified
    basic     基本掌握 — recovering (0.5 <= score < 0.8)
    mastered  已掌握   — score >= 0.8 (confidence-capped: 2 clean tries)

Storage: ``data/subjects/<id>/wrong_book.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import uuid

from deeptutor.learning.mastery import compute_mastery
from deeptutor.subjects import store

STATUS_ORDER = ("repeated", "missed", "basic", "mastered", "untracked")
STATUS_LABELS = {
    "repeated": "反复错",
    "missed": "错过",
    "basic": "基本掌握",
    "mastered": "已掌握",
    "untracked": "未标记",
}


def classify(correctness: list[bool]) -> str:
    """Map an attempt history to one of the four mastery status levels."""
    if not correctness:
        return "untracked"
    score = compute_mastery(correctness)
    last = correctness[-1]
    if not last:
        errors = sum(1 for c in correctness if not c)
        return "repeated" if errors >= 2 else "missed"
    if score >= 0.8:
        return "mastered"
    if score >= 0.5:
        return "basic"
    return "repeated"


def _path(subject_id: str) -> Path:
    return store.subject_dir(subject_id) / "wrong_book.json"


def load(subject_id: str) -> list[dict]:
    path = _path(subject_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(subject_id: str, entries: list[dict]) -> None:
    path = _path(subject_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _recompute(entry: dict) -> dict:
    """Refresh mastery score + status from the attempt history."""
    correctness = [bool(a.get("correct")) for a in entry.get("attempts", [])]
    entry["mastery"] = round(compute_mastery(correctness), 3)
    entry["status"] = classify(correctness)
    return entry


def add_entry(
    subject_id: str,
    *,
    question: str,
    answer: str = "",
    analysis: str = "",
    kp: str = "",
    question_type: str = "written",
    source: str = "manual",
    error_type: str = "",
) -> dict:
    """Add a wrong/asked question. Returns the stored entry."""
    now = int(time.time())
    entry = {
        "id": uuid.uuid4().hex[:12],
        "subject_id": subject_id,
        "kp": kp.strip(),
        "question": question.strip(),
        "answer": answer.strip(),
        "analysis": analysis.strip(),
        "question_type": question_type,
        "source": source,
        "error_type": error_type,
        "attempts": [],
        "mastery": 0.0,
        "status": "untracked",
        "archived": False,
        "created_at": now,
        "updated_at": now,
    }
    entries = load(subject_id)
    entries.append(entry)
    _save(subject_id, entries)
    return entry


def record_attempt(
    subject_id: str, entry_id: str, *, correct: bool, session_id: str = ""
) -> dict | None:
    """Record one answer outcome and recompute mastery/status."""
    entries = load(subject_id)
    for entry in entries:
        if entry["id"] == entry_id:
            entry.setdefault("attempts", []).append(
                {
                    "ts": int(time.time()),
                    "correct": bool(correct),
                    "session_id": session_id or "",
                }
            )
            entry = _recompute(entry)
            entry["updated_at"] = int(time.time())
            _save(subject_id, entries)
            return entry
    return None


def find_by_question(subject_id: str, question: str) -> dict | None:
    """Exact-match lookup (used by the check flow to reuse an entry)."""
    q = question.strip()
    return next((e for e in load(subject_id) if e["question"].strip() == q), None)


def list_entries(
    subject_id: str, *, status: str | None = None, archived: bool | None = None
) -> list[dict]:
    entries = load(subject_id)
    if status:
        entries = [e for e in entries if e["status"] == status]
    if archived is not None:
        entries = [e for e in entries if e["archived"] is archived]
    return sorted(entries, key=lambda e: e.get("updated_at", 0), reverse=True)


def stats(subject_id: str) -> dict:
    counts = {s: 0 for s in STATUS_ORDER}
    total = 0
    for e in load(subject_id):
        if e.get("archived"):
            continue
        counts[e.get("status", "untracked")] = counts.get(e.get("status", "untracked"), 0) + 1
        total += 1
    return {"total": total, "by_status": counts}


def archive(subject_id: str, entry_id: str) -> dict | None:
    entries = load(subject_id)
    for e in entries:
        if e["id"] == entry_id:
            e["archived"] = True
            e["updated_at"] = int(time.time())
            _save(subject_id, entries)
            return e
    return None


def delete(subject_id: str, entry_id: str) -> bool:
    entries = load(subject_id)
    kept = [e for e in entries if e["id"] != entry_id]
    if len(kept) == len(entries):
        return False
    _save(subject_id, kept)
    return True


def context_summary(subject_id: str, limit: int = 5) -> str:
    """Lightweight injection block for chat turns (no full answers).

    Used by the chat pipeline when a session is subject-scoped: gives the
    model the recent mistake list without dumping whole transcripts.
    """
    entries = [e for e in load(subject_id) if not e.get("archived")]
    if not entries:
        return ""
    active = [e for e in entries if e["status"] in ("repeated", "missed", "basic")]
    active.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
    lines = ["【该科目的错题集摘要】"]
    counts = {s: 0 for s in ("repeated", "missed", "basic", "mastered")}
    for e in entries:
        counts[e.get("status", "untracked")] = counts.get(e.get("status", "untracked"), 0) + 1
    lines.append(
        f"错题统计：反复错 {counts['repeated']} 道、错过 {counts['missed']} 道、"
        f"基本掌握 {counts['basic']} 道、已掌握 {counts['mastered']} 道。"
    )
    if active:
        lines.append("最近未掌握错题（讲解时请针对性回顾，不要直接念答案）：")
        for e in active[:limit]:
            status = STATUS_LABELS.get(e["status"], e["status"])
            kp = e.get("kp") or "未标注知识点"
            q = e["question"][:80]
            lines.append(f"- [{status}][{kp}] {q}")
    return "\n".join(lines)
