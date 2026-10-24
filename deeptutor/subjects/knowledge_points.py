"""Knowledge-point index (M5) — per-subject knowledge map with links.

Each point is a named node in the subject's knowledge tree. Wrong-book
entries and exam points link in by knowledge-point name, so a point
aggregates its mistakes (and their mastery) and its exam flags.

Storage: ``data/subjects/<id>/knowledge_points.json``.
"""

from __future__ import annotations

from pathlib import Path
import time
import uuid

from deeptutor.subjects import json_store, store

KNOWLEDGE_POINTS_NAME = "knowledge_points.json"


def _path(subject_id: str) -> Path:
    """The collection file, confined before anything opens it."""
    return store.subject_data_path(subject_id, KNOWLEDGE_POINTS_NAME)


_LINK_FIELDS = ("wrong_ids", "exam_point_ids")


def _validate(points: list[dict], source: Path) -> list[dict]:
    """Check the fields this module reads; keep every unknown field.

    A *missing* link list is a legacy record and reads as ``[]``. A present but
    wrong value — including an explicit ``null`` — is corruption, because the
    append/aggregate paths would otherwise fail later with a raw ``TypeError``.
    """
    for index, point in enumerate(points):
        if not isinstance(point.get("id"), str) or not point["id"]:
            raise json_store.corrupt_error(source.name, "知识点记录缺少合法 id", index=index)
        if not isinstance(point.get("name"), str):
            raise json_store.corrupt_error(source.name, "知识点缺少 name", index=index)
        for key in ("path", "source"):
            value = point.get(key)
            if key in point and not isinstance(value, str):
                raise json_store.corrupt_error(
                    source.name, f"{key} 不是字符串", index=index
                )
        created = point.get("created_at")
        if "created_at" in point and (
            isinstance(created, bool) or not isinstance(created, (int, float))
        ):
            raise json_store.corrupt_error(
                source.name, "created_at 不是数值", index=index
            )
        for key in _LINK_FIELDS:
            # An absent key is legacy (reads as []); an explicit null/wrong type
            # is corruption, not "missing".
            if key not in point:
                continue
            value = point[key]
            if not isinstance(value, list):
                raise json_store.corrupt_error(source.name, f"{key} 不是数组", index=index)
            for item in value:
                if not isinstance(item, str):
                    raise json_store.corrupt_error(
                        source.name, f"{key} 的元素不是字符串", index=index
                    )
    return points


def load(subject_id: str) -> list[dict]:
    """Load the collection; ``[]`` only when the file does not exist."""
    path = _path(subject_id)
    return _validate(json_store.read_list(path), path)


def _save(subject_id: str, points: list[dict]) -> None:
    """Atomically write the collection (the caller already holds the lock)."""
    path = _path(subject_id)
    json_store.atomic_write_list(path, points)


def _required_name(name: object) -> str:
    """A blank or non-string name is a caller error, not storage damage."""
    if not isinstance(name, str):
        raise json_store.invalid_input("知识点名称必须是字符串")
    cleaned = name.strip()
    if not cleaned:
        raise json_store.invalid_input("知识点名称不能为空")
    return cleaned


def _optional_text(value: object, what: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    return value.strip()


def _build_point(
    subject_id: str, *, name: str, path: str = "", source: str = "manual"
) -> dict:
    cleaned = _required_name(name)
    return {
        "id": uuid.uuid4().hex[:12],
        "subject_id": subject_id,
        "name": cleaned,
        "path": _optional_text(path, "知识点路径") or cleaned,
        "source": _optional_text(source, "来源") or "manual",
        "wrong_ids": [],
        "exam_point_ids": [],
        "created_at": int(time.time()),
    }


def add_point(subject_id: str, *, name: str, path: str = "", source: str = "manual") -> dict:
    """Add a named point, reusing an existing one.

    The "already exists?" lookup and the append share one transaction, so two
    concurrent adds of the same name cannot both decide to append.
    """
    cleaned = _required_name(name)

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)
        existing = next((p for p in points if p.get("name") == cleaned), None)
        if existing is not None:
            return existing
        point = _build_point(subject_id, name=name, path=path, source=source)
        points.append(point)
        tx.write_list(file_path, points)
    return point


def add_many(subject_id: str, names: list[str], path: str = "", source: str = "llm") -> list[dict]:
    """Add several names in one locked read-modify-write."""
    if not isinstance(names, list):
        raise json_store.invalid_input("names 必须是数组")
    if any(not isinstance(name, str) for name in names):
        raise json_store.invalid_input("知识点名称必须是字符串")

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)
        by_name = {p.get("name"): p for p in points}
        out: list[dict] = []
        added = False
        for raw in names:
            if not isinstance(raw, str) or not raw.strip():
                continue
            cleaned = raw.strip()
            existing = by_name.get(cleaned)
            if existing is None:
                existing = _build_point(subject_id, name=cleaned, path=path, source=source)
                points.append(existing)
                by_name[cleaned] = existing
                added = True
            out.append(existing)
        if added:
            tx.write_list(file_path, points)
    return out


def get_point(subject_id: str, point_id: str) -> dict | None:
    return next((p for p in load(subject_id) if p["id"] == point_id), None)


def find_by_name(subject_id: str, name: str) -> dict | None:
    name = name.strip().lower()
    return next((p for p in load(subject_id) if p["name"].strip().lower() == name), None)


def _link(subject_id: str, kp: str, linked_id: str, key: str) -> dict | None:
    """Idempotently append *linked_id* to *key* on the point named *kp*.

    Lookup, existence check and append all happen under one lock, so two
    concurrent links cannot drop one of the ids, and re-linking the same id is
    a no-op (the existing "don't add twice" rule).
    """
    if not isinstance(kp, str) or not isinstance(linked_id, str):
        raise json_store.invalid_input("知识点名称与关联 id 必须是字符串")
    target = kp.strip().lower()
    if not target or not linked_id:
        return None

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)
        for point in points:
            if str(point.get("name", "")).strip().lower() != target:
                continue
            linked = point.setdefault(key, [])
            if linked_id in linked:
                return point
            linked.append(linked_id)
            tx.write_list(file_path, points)
            return point
        return None


def link_wrong_entry(subject_id: str, kp: str, wrong_id: str) -> dict | None:
    """Attach a wrong-book entry to the matching knowledge point."""
    return _link(subject_id, kp, wrong_id, "wrong_ids")


def link_exam_point(subject_id: str, kp: str, exam_point_id: str) -> dict | None:
    """Attach an exam point to the matching knowledge point."""
    return _link(subject_id, kp, exam_point_id, "exam_point_ids")


ASSESSMENT_ASSESSED = "assessed"
ASSESSMENT_UNASSESSED = "unassessed"


def _name_key(value: object) -> str:
    """The case/whitespace-insensitive knowledge-point identity used for joins."""
    return str(value or "").strip().lower()


def _evidence_entries(entries: list[dict]) -> list[dict]:
    """Current unarchived entries that actually carry attempt evidence."""
    return [
        entry
        for entry in entries
        if not entry.get("archived") and bool(entry.get("attempts"))
    ]


def _source_maps(subject_id: str, term: str | None = None) -> tuple[dict, dict]:
    """Derive current KP -> wrong/exam ids from the authoritative collections.

    The stored link arrays are a cache: ``build_from_sources`` rewrites them, but
    reads must also work for a newly added entry, an archived/deleted row or a
    renamed ``kp`` without requiring the learner to press "build" again. So the
    join is recomputed from the trusted wrong-book read views (attempt-derived
    mastery) and the currently confirmed exam points of this subject.
    """
    from deeptutor.subjects import exam_points as ep_mod
    from deeptutor.subjects import wrong_book

    wrong_by_name: dict[str, list[dict]] = {}
    for entry in wrong_book.load(subject_id):
        if entry.get("archived"):
            continue
        key = _name_key(entry.get("kp"))
        if key:
            wrong_by_name.setdefault(key, []).append(entry)

    exam_by_name: dict[str, list[dict]] = {}
    for point in ep_mod.load(subject_id):
        if not point.get("confirmed"):
            continue
        if term and point.get("term") != term:
            continue
        key = _name_key(point.get("kp"))
        if key:
            exam_by_name.setdefault(key, []).append(point)
    return wrong_by_name, exam_by_name


def _assessment(entries: list[dict]) -> tuple[float | None, int, str]:
    """Mastery/evidence triple for one point under C10.

    Only entries with a non-empty attempt history count as evidence. Mastery is
    the unweighted mean of those entries' *derived* mastery (the wrong-book read
    view recomputes it from attempts), rounded to three places; an entry with
    ten attempts has exactly the same weight as an entry with one. No evidence
    is ``null`` / 0 / ``unassessed`` -- never the historical 1.0 default.
    """
    evidence = _evidence_entries(entries)
    if not evidence:
        return None, 0, ASSESSMENT_UNASSESSED
    scores = [float(entry["mastery"]) for entry in evidence]
    return round(sum(scores) / len(scores), 3), len(evidence), ASSESSMENT_ASSESSED


def format_mastery(value: object) -> str:
    """Render a nullable mastery for prompts/templates without ``None``/``NaN``."""
    if value is None:
        return "未评估"
    return f"{value}"


def aggregate(subject_id: str, *, term: str | None = None) -> list[dict]:
    """Knowledge points enriched with current wrong-book + exam-point evidence.

    Each point gains ``wrong_count``, ``evidence_count``, ``mastery`` and
    ``exam_count``. ``mastery`` is ``None`` when none of the associated entries
    has attempt evidence (``assessment_status=unassessed``), otherwise the
    unweighted mean of the effective entries' derived mastery, rounded to
    three places. Associations are recomputed from the current collections, so
    archived/deleted/renamed rows disappear without a manual rebuild.

    ``term`` optionally restricts the exam-point side to one term, matching the
    review guide's existing semester semantics; omitting it keeps the historical
    "all confirmed" view.
    """
    wrong_by_name, exam_by_name = _source_maps(subject_id, term)
    out = []
    for p in load(subject_id):
        key = _name_key(p.get("name"))
        wrongs = wrong_by_name.get(key, [])
        exams = exam_by_name.get(key, [])
        item = dict(p)
        item["wrong_ids"] = sorted({entry["id"] for entry in wrongs})
        item["exam_point_ids"] = sorted({point["id"] for point in exams})
        item["wrong_count"] = len(wrongs)
        mastery, evidence_count, status = _assessment(wrongs)
        item["mastery"] = mastery
        item["evidence_count"] = evidence_count
        item["assessment_status"] = status
        item["exam_count"] = len(exams)
        out.append(item)
    return out


def build_from_sources(subject_id: str) -> dict:
    """Idempotently create missing points and refresh every derived link.

    One subject short transaction covers the reads from the wrong book / exam
    points, the point creation and the link rewrite. Manual points keep their
    id/path/source and every unknown field; only the two derived link arrays
    are replaced with the *current* ids. Re-running with unchanged data writes
    nothing and creates nothing.
    """
    from deeptutor.subjects import exam_points as ep_mod
    from deeptutor.subjects import wrong_book

    d = store.subject_dir(subject_id)
    created = 0
    with store.subject_transaction(subject_id, directory=d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)

        wrongs: list[tuple[str, str]] = []
        for entry in wrong_book.load(subject_id):
            if entry.get("archived"):
                continue
            name = str(entry.get("kp") or "").strip()
            if name:
                wrongs.append((name, str(entry.get("id") or "")))
        exams: list[tuple[str, str]] = []
        for point in ep_mod.load(subject_id):
            if not point.get("confirmed"):
                continue
            name = str(point.get("kp") or "").strip()
            if name:
                exams.append((name, str(point.get("id") or "")))

        by_name: dict[str, dict[str, list[str]]] = {}
        for name, entry_id in wrongs:
            if entry_id:
                by_name.setdefault(_name_key(name), {"wrong": [], "exam": []})["wrong"].append(entry_id)
        for name, point_id in exams:
            if point_id:
                by_name.setdefault(_name_key(name), {"wrong": [], "exam": []})["exam"].append(point_id)
        desired = {
            key: {
                "wrong_ids": sorted(set(value["wrong"])),
                "exam_point_ids": sorted(set(value["exam"])),
            }
            for key, value in by_name.items()
        }

        by_existing = {_name_key(point.get("name")): point for point in points}
        for key, values in desired.items():
            if key in by_existing:
                continue
            # The first occurrence keeps its provenance; exam-only names are
            # marked as exam-derived. This is metadata, not a new textbook
            # extraction: only labels already present in the two collections.
            source = "wrong_book" if values["wrong_ids"] else "exam_point"
            original = next(
                (name for name, _ in wrongs if _name_key(name) == key),
                next((name for name, _ in exams if _name_key(name) == key), key),
            )
            point = _build_point(subject_id, name=original, source=source)
            points.append(point)
            by_existing[key] = point
            created += 1

        changed = created > 0
        for point in points:
            key = _name_key(point.get("name"))
            wanted = desired.get(key, {"wrong_ids": [], "exam_point_ids": []})
            for field in _LINK_FIELDS:
                if point.get(field) != wanted[field]:
                    point[field] = list(wanted[field])
                    changed = True
        if changed:
            tx.write_list(file_path, points)

    return {"created": created, "points": aggregate(subject_id)}

def context_summary(subject_id: str, limit: int = 12) -> str:
    """Lightweight knowledge-map injection block (常驻轻量层)."""
    points = aggregate(subject_id)
    if not points:
        return ""
    weak = [p for p in points if p["wrong_count"] > 0 or p["exam_count"] > 0]
    # ``mastery`` is deliberately nullable: a point with no attempt evidence is
    # not "0% mastered" and must never be ordered as if it were. Keep it after
    # the assessed points and only use the numeric value when one exists.
    weak.sort(
        key=lambda p: (
            p["mastery"] is None,
            0.0 if p["mastery"] is None else p["mastery"],
            -p["wrong_count"],
        )
    )
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
        lines.append(
            f"……共 {len(points)} 个知识点，最薄弱：{weak[0]['name']}"
            f"（掌握度 {format_mastery(weak[0]['mastery'])}）"
        )
    return "\n".join(lines)
