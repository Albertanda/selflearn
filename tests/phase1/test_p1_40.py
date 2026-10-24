"""P1-40: subject export snapshot, completeness and activity exclusion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
import zipfile

import pytest

from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_store
from deeptutor.subjects import export_bundle, store, subject_operations, wrong_book
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers


def _subject(admin_root: Path, label: str = "导出科目") -> helpers.SubjectPaths:
    return helpers.make_subject(admin_root, label)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf(path: Path, text: str = "真实 PDF") -> None:
    import pymupdf

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(str(path))


def _docx(path: Path, text: str = "真实 DOCX") -> None:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    document.save(str(path))


def _png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (2, 2), (20, 30, 40)).save(path, format="PNG")


def _completed_report(subject: helpers.SubjectPaths, marker: str) -> tuple[str, Path]:
    run = report_store.create_report_run(subject.subject_id)
    (run.workdir / "report.md").write_text(f"# {marker}\n", encoding="utf-8")
    _pdf(run.workdir / "report.pdf", marker)
    _png(run.workdir / "chart_1.png")
    files = [
        report_mod._file_entry(run.workdir / "report.md", report_store.ROLE_MARKDOWN),
        report_mod._file_entry(run.workdir / "report.pdf", report_store.ROLE_PDF),
        report_mod._file_entry(run.workdir / "chart_1.png", report_store.ROLE_CHART),
    ]
    report_store.publish_report_run(run, files=files, verification_status="not_requested")
    return run.report_id, run.public_dir


def _add_completed_review_pack(outputs: Path) -> tuple[Path, Path]:
    token = uuid.uuid4().hex
    pdf = outputs / f"review-guide-{token}.pdf"
    docx = outputs / f"review-guide-{token}.docx"
    _pdf(pdf, "completed review pack")
    _docx(docx, "completed review pack")
    return pdf, docx


def _make_rich_subject(admin_root: Path) -> tuple[helpers.SubjectPaths, dict[str, Path]]:
    subject = _subject(admin_root)
    # Learning JSON that must be exported (not excluded by a blanket .json rule).
    entry = wrong_book.add_entry(subject.subject_id, question="导出题", kp="导出点")
    wrong_book.record_attempt(subject.subject_id, entry["id"], correct=False)
    (subject.root / "materials" / "lecture" / "note.txt").write_text("材料正文", encoding="utf-8")
    kb = helpers.make_kb(subject.knowledge_bases, "shared-kb", "导出KB")
    (kb / "docstore.json").write_text('{"index": "completed"}\n', encoding="utf-8")
    report_id, report_dir = _completed_report(subject, "报告正文")
    review_pdf, review_docx = _add_completed_review_pack(subject.outputs)
    return subject, {
        "report_id": report_id,
        "report_dir": report_dir,
        "review_pdf": review_pdf,
        "review_docx": review_docx,
    }


def _read_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("manifest.json").decode("utf-8"))


def _zip_bytes(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_nested_zips_and_incomplete_indexes_are_never_exported(p1_runtime):
    subject = _subject(p1_runtime)
    material = subject.root / "materials" / "lecture"
    (material / "nested.ZIP").write_bytes(b"PK-old-export")
    kb = helpers.make_kb(subject.knowledge_bases, "failed-kb", "失败KB")
    (kb / "metadata.json").write_text('{"status":"error"}')
    (kb / "raw" / "source.txt").write_text("原件保留")
    (kb / "docstore.json").write_text('{"partial":true}')
    (kb / "worker.log").write_text("private traceback")
    result = export_bundle.export_subject_bundle(subject.subject_id)
    payloads = _zip_bytes(result["zip_path"])
    assert not any(name.lower().endswith(".zip") for name in payloads)
    assert "learning/knowledge_bases/failed-kb/raw/source.txt" in payloads
    assert "learning/knowledge_bases/failed-kb/docstore.json" not in payloads
    assert not any(name.endswith("worker.log") for name in payloads)


def test_nested_private_metadata_is_redacted_but_benign_unknown_fields_survive(p1_runtime):
    subject = _subject(p1_runtime)
    index = helpers.learning_root(p1_runtime) / "index.json"
    records = json.loads(index.read_text())
    record = next(r for r in records if r["id"] == subject.subject_id)
    record["monkey_label"] = "保留未知字段"
    record["extra"] = {"label": "保留嵌套字段", "api_key": "secret-nested-43",
                       "rows": [{"password": "secret-nested-43", "title": "保留列表字段"}]}
    index.write_text(json.dumps(records))
    result = export_bundle.export_subject_bundle(subject.subject_id)
    payloads = _zip_bytes(result["zip_path"])
    assert b"secret-nested-43" not in payloads["subject.json"]
    assert b"secret-nested-43" not in payloads["manifest.json"]
    exported = json.loads(payloads["subject.json"])
    assert exported["monkey_label"] == "保留未知字段"
    assert exported["extra"]["label"] == "保留嵌套字段"
    assert exported["extra"]["rows"][0]["title"] == "保留列表字段"


def test_export_rejects_an_image_renamed_as_a_review_pdf(p1_runtime):
    subject = _subject(p1_runtime)
    _png(subject.outputs / f"review-guide-{'d' * 32}.pdf")
    with pytest.raises(SubjectOperationError) as error:
        export_bundle.export_subject_bundle(subject.subject_id)
    assert error.value.code == ErrorCode.STORAGE_CORRUPT
    assert not list(subject.outputs.glob("subject-export-*.zip"))


def test_uuid_collision_does_not_remove_an_existing_private_export(p1_runtime, monkeypatch):
    from types import SimpleNamespace

    subject = _subject(p1_runtime)
    token = "e" * 32
    root = store.current_subject_paths().get_public_outputs_root() / ".export-staging" / token
    root.mkdir(parents=True)
    (root / "keep.txt").write_bytes(b"keep original")
    monkeypatch.setattr(export_bundle.uuid, "uuid4", lambda: SimpleNamespace(hex=token))
    from deeptutor.subjects.errors import SubjectStorageError

    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        export_bundle.prepare_export_bundle(subject.subject_id)
    assert (root / "keep.txt").read_bytes() == b"keep original"


@pytest.mark.parametrize("action", ["commit", "discard"])
def test_foreign_preparation_cannot_be_committed_or_cleaned_by_another_user(p1_runtime, action):
    from deeptutor.multi_user.context import reset_current_user
    from deeptutor.subjects.errors import SubjectStorageError
    from tests.phase1.test_p1_41 import _user

    _, alice = _user("export-alice")
    try:
        a = store.create_subject("同名导出")
        prepared = export_bundle.prepare_export_bundle(a["id"])
        _, bob = _user("export-bob")
        try:
            store.create_subject("同名导出")
            operation = export_bundle.commit_export_bundle if action == "commit" else export_bundle.discard_export_bundle
            with pytest.raises((SubjectOperationError, SubjectStorageError)):
                operation(prepared)
            assert prepared.staging_root.is_dir()
            assert prepared.lease.active
        finally:
            reset_current_user(bob)
        export_bundle.discard_export_bundle(prepared)
    finally:
        reset_current_user(alice)


@pytest.mark.parametrize("check", ["export_tree", "export_files", "delete_tree"])
def test_walk_enumeration_failure_cannot_be_treated_as_an_empty_tree(p1_runtime, monkeypatch, check):
    import os

    from deeptutor.subjects.errors import SubjectStorageError

    subject = _subject(p1_runtime)
    denied = subject.root / "materials" / "lecture" / "unreadable"
    denied.mkdir()
    (denied / "keep.txt").write_text("must not be silently omitted")
    real_scandir = os.scandir

    def scandir(path):
        if Path(path) == denied:
            raise PermissionError("injected")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        if check == "export_tree":
            export_bundle._assert_tree_safe(subject.root)
        elif check == "export_files":
            list(export_bundle._iter_regular_files(subject.root))
        else:
            store._assert_deletable_tree(subject.root, store.subjects_root())


def test_zip_payload_verification_reads_large_entries_in_chunks(p1_runtime, monkeypatch):
    subject = _subject(p1_runtime)
    (subject.root / "materials" / "lecture" / "large.txt").write_bytes(b"a" * (3 << 20))
    real_read = zipfile.ZipExtFile.read

    def bounded(handle, size=-1):
        if handle.name != "manifest.json":
            assert 0 <= size <= 1 << 20, "unbounded ZIP payload read"
        return real_read(handle, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded)
    assert export_bundle.export_subject_bundle(subject.subject_id)["zip_path"].is_file()


def test_export_contains_only_verified_authoritative_content(p1_runtime: Path) -> None:
    subject, paths = _make_rich_subject(p1_runtime)
    result = export_bundle.export_subject_bundle(subject.subject_id)
    zip_path = result["zip_path"]
    assert zip_path.is_file() and zip_path.name.startswith("subject-export-")
    assert result["schema_version"] == 1 and len(result["export_id"]) == 32

    manifest = _read_manifest(zip_path)
    import jsonschema

    schemas = json.loads(
        (Path(__file__).resolve().parents[2] / "plans" / "phase1" / "schemas.json").read_text("utf-8")
    )
    jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/ExportManifest", "$defs": schemas["$defs"]}
    ).validate(manifest)
    assert manifest["schema_version"] == 1
    assert manifest["export_id"] == result["export_id"]
    assert manifest["subject"]["id"] == subject.subject_id
    assert manifest["subject"]["marker"] == subject.marker
    assert "chat_history:not_included_no_subject_binding" in manifest["exclusions"]

    payloads = _zip_bytes(zip_path)
    listed = {entry["path"]: entry for entry in manifest["files"]}
    assert set(payloads) == set(listed) | {"manifest.json"}
    assert len(listed) == len(manifest["files"]), "duplicate manifest paths"
    for name, entry in listed.items():
        data = payloads[name]
        assert len(data) == entry["size"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert entry["category"] in {"subject_metadata", "learning", "artifact"}
        assert not name.startswith("/") and ".." not in name.split("/")

    assert "subject.json" in listed
    assert listed["subject.json"]["category"] == "subject_metadata"
    assert json.loads(payloads["subject.json"])["marker"] == subject.marker
    assert "learning/wrong_book.json" in listed, "learner JSON is authoritative"
    assert "learning/materials/lecture/note.txt" in listed
    assert any(name.startswith("learning/knowledge_bases/shared-kb/") for name in listed)
    assert "learning/knowledge_bases/shared-kb/docstore.json" in listed
    report_prefix = f"artifacts/reports/{paths['report_id']}/"
    assert report_prefix + "report.pdf" in listed
    assert report_prefix + "report.md" in listed
    assert report_prefix + "chart_1.png" in listed
    assert f"artifacts/{paths['review_pdf'].name}" in listed
    assert f"artifacts/{paths['review_docx'].name}" in listed
    assert b"%PDF-" in payloads[report_prefix + "report.pdf"]
    assert payloads[report_prefix + "chart_1.png"].startswith(b"\x89PNG")
    assert b"%PDF-" in payloads[f"artifacts/{paths['review_pdf'].name}"]
    assert payloads[f"artifacts/{paths['review_docx'].name}"].startswith(b"PK\x03\x04")


def test_export_excludes_secrets_other_subjects_and_all_previous_zips(p1_runtime: Path) -> None:
    subject, _paths = _make_rich_subject(p1_runtime)
    other = _subject(p1_runtime, "别科导出")
    (other.outputs / f"review-guide-{'a' * 32}.pdf").write_bytes(b"%PDF-other")
    settings = p1_runtime / "user" / "settings"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "secret.json").write_text('{"api_key": "sk-never-export"}', encoding="utf-8")
    # Unknown/private artifacts and an old export are present but never selected.
    (subject.outputs / "subject-backup-1700000000.zip").write_bytes(b"old zip")
    (subject.outputs / "reports" / "unknown.pdf").write_bytes(b"%PDF-unknown")
    failed = report_store.create_report_run(subject.subject_id)
    report_store.fail_report_run(failed)

    first = export_bundle.export_subject_bundle(subject.subject_id)
    second = export_bundle.export_subject_bundle(subject.subject_id)
    first_name = first["zip_path"].name
    assert first_name != second["zip_path"].name

    payloads = _zip_bytes(second["zip_path"])
    joined = "\n".join(payloads)
    assert "sk-never-export" not in joined
    assert "subject-backup-1700000000.zip" not in payloads
    assert "unknown.pdf" not in payloads
    assert "chat_history" not in payloads
    assert f"subjects/{subject.subject_id}" not in joined
    assert "current-new-subject" not in joined
    assert first_name not in payloads
    assert failed.report_id not in payloads
    # Both exports remain distinct public files; the second never absorbed the first.
    assert first["zip_path"].is_file() and second["zip_path"].is_file()


def test_busy_shared_activity_returns_409_for_export(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    lease = subject_operations.acquire_activity(subject.subject_id, kind="upload")
    try:
        with pytest.raises(SubjectOperationError) as error:
            export_bundle.export_subject_bundle(subject.subject_id)
        assert error.value.code == ErrorCode.KB_BUSY
        assert error.value.http_status == 409
        assert error.value.retryable is True
        assert list(subject.outputs.glob("subject-export-*.zip")) == []
    finally:
        lease.release()
    result = export_bundle.export_subject_bundle(subject.subject_id)
    assert result["zip_path"].is_file()


def test_any_deep_symlink_is_refused_and_publishes_nothing(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    victim = p1_runtime / "victim.txt"
    victim.write_text("victim bytes", encoding="utf-8")
    deep = subject.root / "knowledge_bases" / "shared-kb" / "raw" / "deep"
    deep.mkdir(parents=True, exist_ok=True)
    (deep / "link.txt").symlink_to(victim)
    before = set(subject.outputs.glob("subject-export-*.zip"))

    with pytest.raises(SubjectOperationError) as error:
        export_bundle.export_subject_bundle(subject.subject_id)
    assert error.value.code == ErrorCode.STORAGE_IO
    assert victim.read_text(encoding="utf-8") == "victim bytes"
    assert set(subject.outputs.glob("subject-export-*.zip")) == before
    assert not list((p1_runtime / "user" / ".export-staging").glob("*"))


def test_corrupt_completed_artifact_fails_without_a_new_public_zip(p1_runtime: Path) -> None:
    subject, paths = _make_rich_subject(p1_runtime)
    first = export_bundle.export_subject_bundle(subject.subject_id)
    (paths["report_dir"] / "report.pdf").write_bytes(b"%PDF-tampered")
    before = set(subject.outputs.glob("subject-export-*.zip"))

    with pytest.raises(SubjectOperationError) as error:
        export_bundle.export_subject_bundle(subject.subject_id)
    assert error.value.code == ErrorCode.STORAGE_CORRUPT
    assert set(subject.outputs.glob("subject-export-*.zip")) == before
    assert first["zip_path"].is_file()


def test_compression_failure_leaves_the_old_zip_and_releases_the_lease(
    p1_runtime: Path, monkeypatch
) -> None:
    subject = _subject(p1_runtime)
    first = export_bundle.export_subject_bundle(subject.subject_id)
    first_hash = _sha(first["zip_path"])

    def failing(_content, _zip_path):
        from deeptutor.subjects.errors import subject_error

        raise subject_error(ErrorCode.STORAGE_IO)

    monkeypatch.setattr(export_bundle, "_zip_content", failing)
    before = set(subject.outputs.glob("subject-export-*.zip"))
    with pytest.raises(SubjectOperationError) as error:
        export_bundle.export_subject_bundle(subject.subject_id)
    assert error.value.code == ErrorCode.STORAGE_IO
    assert set(subject.outputs.glob("subject-export-*.zip")) == before
    assert _sha(first["zip_path"]) == first_hash
    assert not list((p1_runtime / "user" / ".export-staging").glob("*"))
    lease = subject_operations.acquire_activity(
        subject.subject_id, mode=subject_operations.EXCLUSIVE, kind="after-failure"
    )
    lease.release()


def test_snapshot_change_is_retried_once_and_then_succeeds(
    p1_runtime: Path, monkeypatch
) -> None:
    from dataclasses import replace

    subject = _subject(p1_runtime)
    original = export_bundle._collect
    calls = {"n": 0}

    def changing(subject_id, paths):
        calls["n"] += 1
        record, sources = original(subject_id, paths)
        if calls["n"] == 1:
            first = next(source for source in sources if source.source is not None)
            sources = [replace(first, size=first.size + 1) if source is first else source
                       for source in sources]
        return record, sources

    monkeypatch.setattr(export_bundle, "_collect", changing)
    result = export_bundle.export_subject_bundle(subject.subject_id)
    assert result["zip_path"].is_file()
    assert calls["n"] >= 3, "the first inconsistent snapshot must trigger a retry"


def test_manifest_and_zip_are_reverified_independently(p1_runtime: Path, monkeypatch) -> None:
    subject, _paths = _make_rich_subject(p1_runtime)
    original = export_bundle._write_manifest

    def tampering(content, record, sources, export_id):
        manifest = original(content, record, sources, export_id)
        manifest["files"][0]["sha256"] = "0" * 64
        (content / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    monkeypatch.setattr(export_bundle, "_write_manifest", tampering)
    with pytest.raises(SubjectOperationError) as error:
        export_bundle.export_subject_bundle(subject.subject_id)
    assert error.value.code == ErrorCode.STORAGE_CORRUPT
    assert list(subject.outputs.glob("subject-export-*.zip")) == []


def test_manifest_subject_projection_drops_private_fields(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    index = helpers.learning_root(p1_runtime) / "index.json"
    records = json.loads(index.read_text(encoding="utf-8"))
    for record in records:
        if record["id"] == subject.subject_id:
            record["api_key"] = "sk-private"
            record["owner_id"] = "owner-private"
            record["diagnostics"] = {"path": "/host/private"}
            record["custom_label"] = "保留"
    index.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    result = export_bundle.export_subject_bundle(subject.subject_id)
    payloads = _zip_bytes(result["zip_path"])
    body = json.loads(payloads["subject.json"])
    assert body["custom_label"] == "保留"
    assert "api_key" not in body and "owner_id" not in body and "diagnostics" not in body
    assert "sk-private" not in json.dumps(body, ensure_ascii=False)
