"""Exam points (M4) — per-subject final-exam key points with evidence.

Each point records what the teacher stressed as examinable, with a
confidence level, the evidence quote, and a term so stale semesters do
not leak into the current one.

    explicit  明示 — teacher explicitly said it will be on the exam
    emphasis  强调 — repeated/strong emphasis, "常考/很重要" signals
    inferred  推断 — system inference (e.g. overlap with past papers)

Storage: ``data/subjects/<id>/exam_points.json`` (C01/C06).

Two storage rules matter here:

* **One batch, one write.** :func:`add_many` validates the whole batch before
  touching the file and then commits it in a single locked write, so an invalid
  item near the end cannot leave the earlier items stored.
* **Confirm and add cannot clobber each other.** Both run their read-modify-write
  inside the same subject transaction, so a confirmation landing between a
  detector batch's read and write no longer disappears.

Detection rounds use :func:`upsert_detected`, which additionally applies the C06
confirmation policy and exact ``(term, content, evidence)`` deduplication, so
running the same transcript twice does not grow the collection.
"""

from __future__ import annotations

from pathlib import Path
import re
import time
import uuid

from deeptutor.subjects import json_store, store

LEVEL_LABELS = {"explicit": "明示考点", "emphasis": "强调考点", "inferred": "推断考点"}

EXAM_POINTS_NAME = "exam_points.json"

#: Payload fields copied onto a point, with the default used when absent.
_TEXT_FIELDS = (
    ("content", ""),
    ("evidence", ""),
    ("kp", ""),
    ("term", ""),
    ("source", "manual"),
    ("anchor", ""),
)


#: A malformed point payload is a caller error (C02 ``invalid_input``, 400),
#: not damage to stored data.
InvalidExamPointError = json_store.InvalidInputError


def _path(subject_id: str) -> Path:
    """The collection file, confined before anything opens it."""
    return store.subject_data_path(subject_id, EXAM_POINTS_NAME)


#: Optional text fields a stored point may carry.
_OPTIONAL_TEXT = ("evidence", "kp", "term", "source", "anchor", "level")

#: Levels a **stored** point may carry: C06 detection levels plus the historical
#: manual ``inferred`` row. A present value outside this tuple is corruption.
STORED_LEVELS: tuple[str, ...] = ("explicit", "emphasis", "inferred")


def _validate(points: list[dict], source: Path, subject_id: str) -> list[dict]:
    """Check the fields this module reads; keep every unknown field.

    ``id`` and ``content`` are required; the display/query text fields and
    ``confirmed`` are validated only when present (a missing optional field is
    a legacy record, an explicitly wrong type is corruption).

    Two *identity* checks matter for the response contract (C01/R3): a stored
    ``subject_id`` that is present must be a legal slug **and** the subject this
    file belongs to — a record that claims another subject (or carries ``null``,
    a number, or ``bad/id``) must not be returned as if it belonged here. A
    missing key stays legal for legacy rows and is filled in the read view only.
    A present ``level`` must be one of :data:`STORED_LEVELS`.
    """
    for index, point in enumerate(points):
        if not isinstance(point.get("id"), str) or not point["id"]:
            raise json_store.corrupt_error(source.name, "考点记录缺少合法 id", index=index)
        if not isinstance(point.get("content"), str):
            raise json_store.corrupt_error(source.name, "考点缺少 content", index=index)
        if "subject_id" in point:
            owner = point["subject_id"]
            if not isinstance(owner, str) or not store.is_valid_subject_id(owner):
                raise json_store.corrupt_error(
                    source.name, "subject_id 不是合法科目 id", index=index
                )
            if owner != subject_id:
                raise json_store.corrupt_error(
                    source.name, "subject_id 与当前科目不一致", index=index
                )
        for key in _OPTIONAL_TEXT:
            value = point.get(key)
            if key in point and not isinstance(value, str):
                raise json_store.corrupt_error(
                    source.name, f"{key} 不是字符串", index=index
                )
        if "level" in point and point["level"] not in STORED_LEVELS:
            raise json_store.corrupt_error(
                source.name, "level 不在 explicit/emphasis/inferred 内", index=index
            )
        confirmed = point.get("confirmed")
        if "confirmed" in point and not isinstance(confirmed, bool):
            raise json_store.corrupt_error(source.name, "confirmed 不是布尔值", index=index)
        created = point.get("created_at")
        if "created_at" in point and (
            isinstance(created, bool) or not isinstance(created, (int, float))
        ):
            raise json_store.corrupt_error(
                source.name, "created_at 不是数值", index=index
            )
    return points


def load(subject_id: str) -> list[dict]:
    """Load the collection; ``[]`` only when the file does not exist."""
    path = _path(subject_id)
    return _validate(json_store.read_list(path), path, subject_id)


def _save(subject_id: str, points: list[dict]) -> None:
    """Atomically write the collection (the caller already holds the lock)."""
    path = _path(subject_id)
    json_store.atomic_write_list(path, points)


def _text(raw: dict, key: str, default: str) -> str:
    value = raw.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{key} 必须是字符串")
    return value.strip()


def _required_content(raw: dict) -> str:
    """``content`` must be a non-blank string (C06: trim 非空)."""
    value = raw.get("content", "")
    if not isinstance(value, str):
        raise json_store.invalid_input("考点内容必须是字符串")
    cleaned = value.strip()
    if not cleaned:
        raise json_store.invalid_input("考点内容不能为空")
    return cleaned


def _build_point(subject_id: str, raw: dict, *, confirmed: bool) -> dict:
    """Validate one payload and build its stored record (no I/O)."""
    if not isinstance(raw, dict):
        raise json_store.invalid_input("考点必须是对象")
    content = _required_content(raw)
    level = raw.get("level", "inferred")
    if level is None:
        level = "inferred"
    if not isinstance(level, str):
        raise json_store.invalid_input("level 必须是字符串")
    if level not in LEVEL_LABELS:
        level = "inferred"  # 保留既有规则：未知 level 归为推断
    if not isinstance(confirmed, bool):
        raise json_store.invalid_input("confirmed 必须是布尔值")

    now = int(time.time())
    point: dict = {"id": uuid.uuid4().hex[:12], "subject_id": subject_id, "level": level}
    for key, default in _TEXT_FIELDS:
        point[key] = _text(raw, key, default)
    point["content"] = content
    point["confirmed"] = confirmed
    point["created_at"] = now
    return point


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
    payload = {
        "content": content,
        "level": level,
        "evidence": evidence,
        "kp": kp,
        "term": term,
        "source": source,
        "anchor": anchor,
    }
    point = _build_point(subject_id, payload, confirmed=confirmed)

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        points = _validate(tx.read_list(path), path, subject_id)
        points.append(point)
        tx.write_list(path, points)
    return point


def add_many(subject_id: str, points: list[dict]) -> list[dict]:
    """Add a batch (detector output) and return the stored points.

    The whole batch is validated and built **before** the file is opened, and
    all of it is committed in one locked write: a malformed item at position N
    leaves nothing from positions 0..N-1 behind.
    """
    if not isinstance(points, list):
        raise json_store.invalid_input("批次必须是数组")

    batch: list[dict] = []
    for raw in points:
        payload = dict(raw) if isinstance(raw, dict) else raw
        if isinstance(payload, dict):
            payload.setdefault("source", "lecture_detection")
        batch.append(_build_point(subject_id, payload, confirmed=False))

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        stored = _validate(tx.read_list(path), path, subject_id)
        stored.extend(batch)
        tx.write_list(path, stored)

    return [point for point in batch if point["content"]]


#: Levels a *detector* may produce (C06). ``inferred`` stays readable for
#: historical manual rows but is never produced or accepted here.
DETECTED_LEVELS: tuple[str, ...] = ("explicit", "emphasis")

_WHITESPACE = re.compile(r"\s+")


def _normalized(text: str) -> str:
    """Whitespace-only normalisation for the dedupe key (C06)."""
    return _WHITESPACE.sub("", text)


def _stored_view(record: dict, subject_id: str) -> dict:
    """A response-shaped copy of a stored point (never written back).

    Reused legacy records may predate some keys; the response still has to match
    the ExamStored schema, so the *missing* fields get their defaults here. A
    value that is present is never replaced.
    """
    view = dict(record)
    for key, default in (
        ("subject_id", subject_id),
        ("content", ""),
        ("level", "inferred"),
        ("evidence", ""),
        ("kp", ""),
        ("term", ""),
        ("source", "manual"),
        ("anchor", ""),
        ("confirmed", False),
    ):
        view.setdefault(key, default)
    return view


def _detected_candidate(raw: object, *, term: str, source: str) -> dict:
    """Validate one detector candidate **strictly** (no level fallback).

    ``add_point``/``add_many`` keep the historical manual rule that an unknown
    level becomes ``inferred`` and that absent optional fields take defaults. A
    detector candidate must not: C06 requires ``content``/``evidence``/``kp`` to
    be *present* strings, ``content``/``evidence`` non-blank after trimming
    (``kp`` may legally be an empty string) and ``level`` to be exactly
    ``explicit``/``emphasis`` — no strip/lower "repair", no default for a missing
    field, no silently skipped candidate.
    """
    if not isinstance(raw, dict):
        raise json_store.invalid_input("考点必须是对象")

    if "content" not in raw:
        raise json_store.invalid_input("考点缺少 content")
    content = raw["content"]
    if not isinstance(content, str):
        raise json_store.invalid_input("考点内容必须是字符串")
    content = content.strip()
    if not content:
        raise json_store.invalid_input("考点内容不能为空")

    if "level" not in raw:
        raise json_store.invalid_input("考点缺少 level")
    level = raw["level"]
    if not isinstance(level, str):
        raise json_store.invalid_input("level 必须是字符串")
    # 精确枚举：' Explicit ' 不会被"修"成合法 level 后写入集合。
    if level not in DETECTED_LEVELS:
        raise json_store.invalid_input("检测考点的 level 只能是 explicit 或 emphasis")

    if "evidence" not in raw:
        raise json_store.invalid_input("考点缺少 evidence")
    evidence = raw["evidence"]
    if not isinstance(evidence, str):
        raise json_store.invalid_input("evidence 必须是字符串")
    evidence = evidence.strip()
    if not evidence:
        raise json_store.invalid_input("evidence 不能为空")

    if "kp" not in raw:
        raise json_store.invalid_input("考点缺少 kp")
    kp = raw["kp"]
    if not isinstance(kp, str):
        raise json_store.invalid_input("kp 必须是字符串")

    return {
        "content": content,
        "level": level,
        "evidence": evidence,
        "kp": kp.strip(),
        "term": term,
        "source": _text(raw, "source", source) or source,
        "anchor": _text(raw, "anchor", ""),
    }


def _resolve_term(subject_id: str, term: str) -> str:
    """``term`` empty/omitted falls back to the subject's own term (C06)."""
    if not isinstance(term, str):
        raise json_store.invalid_input("学期必须是字符串")
    cleaned = term.strip()
    if cleaned:
        return cleaned
    subject = store.get_subject(subject_id)
    if subject is None:
        raise store.SubjectNotFoundError(subject_id)
    stored_term = subject.get("term", "")
    return stored_term.strip() if isinstance(stored_term, str) else ""


def upsert_detected(
    subject_id: str,
    points: list[dict],
    *,
    term: str = "",
    source: str = "lecture_detection",
    auto_confirm: bool = False,
) -> list[dict]:
    """Save one detection round as a deduplicated batch (C06).

    Behaviour:

    * the **whole** batch is validated before the file is opened, and a valid
      round is committed in exactly one locked write — a bad item at position N
      leaves nothing from positions 0..N-1 behind;
    * ``term`` empty/omitted uses ``subject.term``; an explicit non-empty term
      is used as given;
    * ``confirmed`` is true only for ``auto_confirm=True`` or a validated
      ``explicit`` candidate; ``emphasis`` defaults to unconfirmed. A stored
      confirmation is never revoked by a later ``emphasis`` detection, while
      ``explicit``/``auto_confirm`` may promote it;
    * deduplication is exact on ``(subject, term, whitespace-normalised content,
      whitespace-normalised evidence)`` — within the batch and against the
      existing collection. No similarity matching, no cross-subject or
      cross-term merging;
    * a duplicate **reuses** the existing record (id, created_at and unknown
      fields included) instead of appending a second copy, and untouched legacy
      records are not rewritten;
    * ``stored`` contains every unique candidate of this round (saved or reused)
      once, built from the **final** persisted state, so ``len(stored)`` is the
      number to report as ``detected``;
    * duplicates inside one batch are merged *before* the confirmation policy is
      applied: if any candidate with the same key is a validated ``explicit`` (or
      the round is ``auto_confirm``), the merged entry is confirmed — the result
      does not depend on which duplicate came first.

    Raises:
        InvalidExamPointError: the batch or a candidate is malformed
            (``invalid_input``, 400) — nothing is written.
    """
    if not isinstance(points, list):
        raise json_store.invalid_input("批次必须是数组")
    if not isinstance(source, str):
        raise json_store.invalid_input("来源必须是字符串")
    if not isinstance(auto_confirm, bool):
        raise json_store.invalid_input("auto_confirm 必须是布尔值")

    resolved_term = _resolve_term(subject_id, term)
    resolved_source = source.strip() or "lecture_detection"

    # Validate the whole round first: a bad item at the end must not leave the
    # earlier ones stored.
    candidates: list[dict] = []
    for raw in points:
        # Strict validation first; the confirmation policy then reads the
        # *validated* level, so a broken level can never be mistaken for one.
        candidate = _detected_candidate(raw, term=resolved_term, source=resolved_source)
        candidate["confirmed"] = auto_confirm or candidate["level"] == "explicit"
        candidates.append(candidate)

    # Merge the batch's duplicates **before** deciding confirmations: a later
    # ``explicit`` for the same key must not be dropped by deduplication, so the
    # outcome cannot depend on the candidates' order (R2).
    merged: dict[tuple[str, str, str], dict] = {}
    for candidate in candidates:
        key = (
            candidate["term"],
            _normalized(candidate["content"]),
            _normalized(candidate["evidence"]),
        )
        if key in merged:
            merged[key]["confirmed"] = merged[key]["confirmed"] or candidate["confirmed"]
            continue
        merged[key] = dict(candidate)

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        points_stored = _validate(tx.read_list(path), path, subject_id)

        # Existing keys, including historical records with missing fields.
        by_key: dict[tuple[str, str, str], dict] = {}
        for record in points_stored:
            key = (
                str(record.get("term", "")),
                _normalized(record.get("content", "")),
                _normalized(record.get("evidence", "")),
            )
            by_key.setdefault(key, record)

        # The entities this round touches, in candidate order. The response view
        # is built from them *after* the loop, so promotions are visible instead
        # of a stale pre-promotion copy.
        touched: list[dict] = []
        changed = False
        for key, candidate in merged.items():
            existing = by_key.get(key)
            if existing is not None:
                touched.append(existing)
                if candidate["confirmed"] and not bool(existing.get("confirmed", False)):
                    # explicit / auto_confirm may promote; emphasis never revokes.
                    existing["confirmed"] = True
                    changed = True
                continue

            record = _build_point(
                subject_id,
                {
                    "content": candidate["content"],
                    "level": candidate["level"],
                    "evidence": candidate["evidence"],
                    "kp": candidate["kp"],
                    "term": candidate["term"],
                    "source": candidate["source"],
                    "anchor": candidate["anchor"],
                },
                confirmed=candidate["confirmed"],
            )
            points_stored.append(record)
            by_key[key] = record
            touched.append(record)
            changed = True

        if changed:
            # One round, one write. A round that only reuses existing records
            # leaves the file untouched.
            tx.write_list(path, points_stored)

    return [_stored_view(record, subject_id) for record in touched]


def list_points(
    subject_id: str, *, term: str | None = None, confirmed: bool | None = None
) -> list[dict]:
    points = load(subject_id)
    if term:
        points = [p for p in points if p.get("term", "") == term]
    if confirmed is not None:
        points = [p for p in points if bool(p.get("confirmed", False)) is confirmed]
    return sorted(points, key=lambda p: p.get("created_at", 0), reverse=True)


def set_confirmed(subject_id: str, point_id: str, confirmed: bool = True) -> dict | None:
    """Confirm/unconfirm one point under the subject lock."""
    if not isinstance(confirmed, bool):
        raise json_store.invalid_input("confirmed 必须是布尔值")

    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        points = _validate(tx.read_list(path), path, subject_id)
        for point in points:
            if point["id"] != point_id:
                continue
            point["confirmed"] = confirmed
            tx.write_list(path, points)
            return point
        return None


def delete(subject_id: str, point_id: str) -> bool:
    d = store.subject_dir(subject_id)
    with store.subject_transaction(subject_id, directory=d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        points = _validate(tx.read_list(path), path, subject_id)
        kept = [p for p in points if p["id"] != point_id]
        if len(kept) == len(points):
            return False
        tx.write_list(path, kept)
        return True


def term_summary(subject_id: str, term: str = "", limit: int = 8) -> str:
    """Lightweight injection block: confirmed exam points for the term."""
    points = [p for p in load(subject_id) if p.get("confirmed")]
    if term:
        points = [p for p in points if p.get("term", "") == term]
    if not points:
        return ""
    points.sort(key=lambda p: p.get("created_at", 0), reverse=True)
    lines = ["【本学期期末考点】"]
    for p in points[:limit]:
        level = LEVEL_LABELS.get(p.get("level", "inferred"), p.get("level", "inferred"))
        kp = f"[{p['kp']}] " if p.get("kp") else ""
        lines.append(f"- {kp}{p.get('content', '')[:100]}（{level}）")
    return "\n".join(lines)
