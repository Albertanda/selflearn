"""P1-39: knowledge-point mastery must be evidence-based and self-updating."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.subjects import knowledge_points as kp
from deeptutor.subjects import store, wrong_book
from tests.phase1 import helpers


def _subject(admin_root: Path, label: str = "证据科目") -> helpers.SubjectPaths:
    return helpers.make_subject(admin_root, label)


def _kp_file(subject: helpers.SubjectPaths) -> Path:
    return subject.root / "knowledge_points.json"


def _wrong_file(subject: helpers.SubjectPaths) -> Path:
    return subject.root / "wrong_book.json"


def _attempt(subject: helpers.SubjectPaths, entry_id: str, *correct: bool) -> dict:
    result = None
    for value in correct:
        result = wrong_book.record_attempt(subject.subject_id, entry_id, correct=value)
    assert result is not None
    return result


def test_no_wrong_entry_is_unassessed_and_lists_null(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    point = kp.add_point(subject.subject_id, name="极限")

    [view] = kp.aggregate(subject.subject_id)

    assert view["id"] == point["id"]
    assert view["mastery"] is None
    assert view["evidence_count"] == 0
    assert view["assessment_status"] == "unassessed"
    assert view["wrong_count"] == 0
    assert "None" not in kp.context_summary(subject.subject_id)


def test_no_attempt_ignores_a_forged_stored_mastery(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    entry = wrong_book.add_entry(subject.subject_id, question="无作答", kp="极限")
    kp.add_point(subject.subject_id, name="极限")
    payload = json.loads(_wrong_file(subject).read_text(encoding="utf-8"))
    payload[0]["mastery"] = 1.0
    payload[0]["status"] = "mastered"
    _wrong_file(subject).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # The read view is still derived from the empty attempt history.
    [stored_view] = wrong_book.load(subject.subject_id)
    assert stored_view["mastery"] == 0.0 and stored_view["status"] == "untracked"

    [view] = kp.aggregate(subject.subject_id)
    assert view["mastery"] is None, "stored 1.0 must not be treated as evidence"
    assert view["evidence_count"] == 0
    assert view["assessment_status"] == "unassessed"
    assert view["wrong_count"] == 1
    assert entry["id"] in view["wrong_ids"]


def test_mean_of_entry_mastery_is_rounded_and_not_attempt_weighted(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    first = wrong_book.add_entry(subject.subject_id, question="一", kp="线性代数")
    second = wrong_book.add_entry(subject.subject_id, question="二", kp="线性代数")
    # Different attempt counts: an entry with four attempts must not outweigh one.
    _attempt(subject, first["id"], True, True, True, True)
    _attempt(subject, second["id"], False, False, True)
    kp.add_point(subject.subject_id, name="线性代数")

    entries = {entry["id"]: entry for entry in wrong_book.load(subject.subject_id)}
    expected = round((entries[first["id"]]["mastery"] + entries[second["id"]]["mastery"]) / 2, 3)

    [view] = kp.aggregate(subject.subject_id)
    assert view["evidence_count"] == 2
    assert view["assessment_status"] == "assessed"
    assert view["mastery"] == expected
    assert view["mastery"] == round(view["mastery"], 3)


def test_archived_deleted_and_relabelled_entries_do_not_linger(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    archived = wrong_book.add_entry(subject.subject_id, question="归档", kp="积分")
    deleted = wrong_book.add_entry(subject.subject_id, question="删除", kp="积分")
    renamed = wrong_book.add_entry(subject.subject_id, question="改名", kp="积分")
    _attempt(subject, archived["id"], False)
    _attempt(subject, deleted["id"], False)
    _attempt(subject, renamed["id"], False)
    kp.add_point(subject.subject_id, name="积分")
    kp.add_point(subject.subject_id, name="级数")

    assert kp.aggregate(subject.subject_id)[0]["wrong_count"] == 3

    wrong_book.archive(subject.subject_id, archived["id"])
    wrong_book.delete(subject.subject_id, deleted["id"])
    raw = json.loads(_wrong_file(subject).read_text(encoding="utf-8"))
    for item in raw:
        if item["id"] == renamed["id"]:
            item["kp"] = "级数"
    _wrong_file(subject).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    views = {view["name"]: view for view in kp.aggregate(subject.subject_id)}
    assert views["积分"]["wrong_count"] == 0
    assert views["积分"]["mastery"] is None
    assert views["级数"]["wrong_count"] == 1
    assert views["级数"]["evidence_count"] == 1
    assert views["级数"]["assessment_status"] == "assessed"


def test_build_is_idempotent_and_preserves_manual_fields(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    entry = wrong_book.add_entry(subject.subject_id, question="题", kp="概率论")
    _attempt(subject, entry["id"], True)
    manual = kp.add_point(subject.subject_id, name="手工点", path="第一章/手工", source="manual")
    raw = json.loads(_kp_file(subject).read_text(encoding="utf-8"))
    raw[0]["unknown_field"] = {"kept": True}
    _kp_file(subject).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    first = kp.build_from_sources(subject.subject_id)
    second = kp.build_from_sources(subject.subject_id)
    assert first["created"] == 1  # only the wrong-book label is new
    assert second["created"] == 0
    assert len([p for p in second["points"] if p["name"] == "概率论"]) == 1
    assert len([p for p in second["points"] if p["name"] == "手工点"]) == 1

    record = next(p for p in kp.load(subject.subject_id) if p["name"] == "手工点")
    assert record["id"] == manual["id"]
    assert record["path"] == "第一章/手工"
    assert record["source"] == "manual"
    assert record["unknown_field"] == {"kept": True}
    derived = next(p for p in kp.load(subject.subject_id) if p["name"] == "概率论")
    assert derived["wrong_ids"] == [entry["id"]]


def test_other_subject_evidence_is_never_counted(p1_runtime: Path) -> None:
    a = _subject(p1_runtime, "甲证据科")
    b = _subject(p1_runtime, "乙证据科")
    entry_b = wrong_book.add_entry(b.subject_id, question="别科", kp="同名点")
    _attempt(b, entry_b["id"], True)
    kp.add_point(a.subject_id, name="同名点")
    kp.add_point(b.subject_id, name="同名点")

    [view_a] = kp.aggregate(a.subject_id)
    [view_b] = kp.aggregate(b.subject_id)
    assert view_a["wrong_count"] == 0 and view_a["mastery"] is None
    assert view_b["wrong_count"] == 1 and view_b["assessment_status"] == "assessed"


def test_context_and_review_guide_show_unassessed_not_none(p1_runtime: Path) -> None:
    from deeptutor.services.pdf import review_guide

    subject = _subject(p1_runtime)
    entry = wrong_book.add_entry(subject.subject_id, question="有证据", kp="已评估点")
    _attempt(subject, entry["id"], False)
    wrong_book.add_entry(subject.subject_id, question="无证据", kp="未评估点")
    kp.build_from_sources(subject.subject_id)

    summary = kp.context_summary(subject.subject_id, limit=1)
    assert "None" not in summary and "nan" not in summary.lower()

    data = review_guide._aggregate(subject.subject_id, "")
    text = review_guide._format_input(data)
    assert "掌握度 未评估" in text
    assert "None" not in text


def test_unassessed_points_render_in_the_weak_point_footer(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    for name in ("未评估甲", "未评估乙"):
        kp.add_point(subject.subject_id, name=name)
        wrong_book.add_entry(subject.subject_id, question=name, kp=name)
    summary = kp.context_summary(subject.subject_id, limit=1)
    assert "未评估" in summary
    assert "None" not in summary
    assert "nan" not in summary.lower()


def test_http_build_and_list_return_the_same_evidence(p1_runtime: Path, p1_route_client) -> None:
    subject = _subject(p1_runtime)
    entry = wrong_book.add_entry(subject.subject_id, question="HTTP", kp="HTTP点")
    _attempt(subject, entry["id"], True)

    built = p1_route_client.post(f"/api/v1/subjects/{subject.subject_id}/knowledge-points/build")
    assert built.status_code == 200, built.text
    body = built.json()
    assert body["created"] == 1
    [point] = body["points"]
    assert point["name"] == "HTTP点"
    assert point["assessment_status"] == "assessed"
    assert point["mastery"] == round(point["mastery"], 3)

    listed = p1_route_client.get(f"/api/v1/subjects/{subject.subject_id}/knowledge-points")
    assert listed.status_code == 200, listed.text
    assert listed.json()["points"][0]["evidence_count"] == 1
