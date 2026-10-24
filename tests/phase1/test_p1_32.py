"""P1-32 行为测试：独立运行目录、状态与**显式发布**。

目标：每次报告有服务端身份与私有目录；失败不覆盖旧 ``completed``、不暴露正式
URL；只有显式 publish 才产生正式产物，且清单里的每个字节都经过复核。

必证场景（对应卡片清单与 START_S08 第二节 P1-32 的"证据"）：

* 并发两个 run 的 id/目录/文件互不复用；强制 UUID 碰撞被拒绝且不覆盖已有内容；
* 发布中注入 IO 失败 → 没有半完成目录、没有正式 URL、旧报告 hash 不变；
* symlink / 跨科 / 越界 / 未知角色 / 坏 metadata / 失败验证一律拒绝；
* 完成 metadata 与文件 hash 逐项吻合，公开投影只含契约字段；
* legacy 合法同科可发现且整棵树不变，未知/越界文件**不被读取**；
* active 登记的释放与 abandoned 分支（含**真实结束进程**留下的 running）。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time

import jsonschema
import pytest

from deeptutor.services.pdf import report_store as rs
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    SubjectStorageError,
)
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]


def _schema_validator(name: str) -> jsonschema.Draft202012Validator:
    schemas = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text("utf-8"))
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schemas["$defs"]})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    """一张真实的 1x1 PNG（P34 才做解码校验，这里只要真实字节）。"""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (1, 1), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _entry(path: Path, role: str) -> dict:
    return {
        "path": path.name,
        "size": path.stat().st_size,
        "sha256": _sha256(path),
        "role": role,
    }


class _Clock:
    """确定性的 created_at：让"最新一份报告"这类断言不依赖秒级时间。"""

    def __init__(self, start: int = 1_700_000_000) -> None:
        self.value = start

    def time(self) -> float:
        self.value += 1
        return float(self.value)


@pytest.fixture
def p1_subject(p1_runtime: Path):
    rs._reset_active_runs_for_tests()
    try:
        yield helpers.make_subject(p1_runtime, "报告科目")
    finally:
        rs._reset_active_runs_for_tests()


@pytest.fixture
def p1_subject_b(p1_runtime: Path):
    return helpers.make_subject(p1_runtime, "另一个科目")


def _materialize(run: rs.ReportRun, *, charts: tuple[str, ...] = ("chart_1.png",)) -> list[dict]:
    """在私有 workdir 里写出正文/PDF/图，并返回服务端清单。"""
    markdown = run.workdir / "report.md"
    markdown.write_text("# 报告\n正文\n", encoding="utf-8")
    pdf = run.workdir / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake but declared\n")
    entries = [_entry(markdown, rs.ROLE_MARKDOWN), _entry(pdf, rs.ROLE_PDF)]
    for index, name in enumerate(charts, start=1):
        chart = run.workdir / name
        chart.write_bytes(_png_bytes((index, index, index)))
        entries.append(_entry(chart, rs.ROLE_CHART))
    return entries


def _publish_ok(run: rs.ReportRun, **kwargs: object) -> rs.ReportManifest:
    files = kwargs.pop("files", None)
    if files is None:
        files = _materialize(run)
    status = kwargs.pop("verification_status", rs.VERIFICATION_NOT_REQUESTED)
    return rs.publish_report_run(run, files=files, verification_status=status)


# ---------------------------------------------------------------------------
# 身份与目录独立
# ---------------------------------------------------------------------------
def test_two_runs_get_independent_ids_and_private_dirs(p1_subject) -> None:
    first = rs.create_report_run(p1_subject.subject_id)
    second = rs.create_report_run(p1_subject.subject_id)

    assert first.report_id != second.report_id
    assert len(first.report_id) == 32 and first.report_id == first.report_id.lower()
    assert first.staging_dir != second.staging_dir
    assert first.public_dir != second.public_dir
    assert first.staging_dir.parent.name == rs.REPORT_RUNS_DIRNAME
    assert first.public_dir.parent.name == rs.REPORTS_DIRNAME
    # create 只建私有目录：正式 URL/目录都不存在。
    assert first.staging_dir.is_dir() and second.staging_dir.is_dir()
    assert not first.public_dir.exists() and not second.public_dir.exists()
    assert rs.report_url(rs.read_run_manifest(first)) is None

    (first.workdir / "chart_1.png").write_bytes(_png_bytes())
    assert not (second.workdir / "chart_1.png").exists()
    assert sorted(item.name for item in first.workdir.iterdir()) == ["chart_1.png"]


def test_uuid_collision_is_rejected_without_overwriting(p1_subject, monkeypatch) -> None:
    import uuid as uuid_module

    fixed = uuid_module.UUID("0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(rs.uuid, "uuid4", lambda: fixed)

    first = rs.create_report_run(p1_subject.subject_id)
    sentinel = first.workdir / "keep.txt"
    sentinel.write_text("不要被覆盖\n", encoding="utf-8")
    before = helpers.tree_digest(first.staging_dir)

    with pytest.raises(SubjectOperationError) as info:
        rs.create_report_run(p1_subject.subject_id)

    assert info.value.code is ErrorCode.INTERNAL_ERROR
    assert helpers.tree_digest(first.staging_dir) == before
    assert sentinel.read_text(encoding="utf-8") == "不要被覆盖\n"


def test_create_requires_a_registered_subject(p1_subject) -> None:
    with pytest.raises(SubjectOperationError) as info:
        rs.create_report_run("不存在的科目")
    assert info.value.code is ErrorCode.SUBJECT_NOT_FOUND
    with pytest.raises(SubjectOperationError) as info:
        rs.create_report_run("../../etc")
    assert info.value.code is ErrorCode.INVALID_SUBJECT_ID


def test_create_validates_reviewed_from(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id, reviewed_from="legacy:report-1.md")
    assert run.reviewed_from == "legacy:report-1.md"
    assert rs.read_run_manifest(run).reviewed_from == "legacy:report-1.md"
    assert rs.create_report_run(p1_subject.subject_id, reviewed_from="  ").reviewed_from is None
    for bad in (5, ["x"], "y" * 500):
        with pytest.raises(json_store.InvalidInputError):
            rs.create_report_run(p1_subject.subject_id, reviewed_from=bad)


# ---------------------------------------------------------------------------
# 发布成功路径与 metadata 契约
# ---------------------------------------------------------------------------
def test_publish_copies_verified_files_and_matches_metadata(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run, charts=("chart_1.png", "chart_2.png"))
    manifest = _publish_ok(run, files=declared)

    assert manifest.status == rs.STATUS_COMPLETED
    assert manifest.report_id == run.report_id
    assert [entry.role for entry in manifest.files] == ["markdown", "pdf", "chart", "chart"]
    for entry in declared:
        source = run.workdir / entry["path"]
        published = run.public_dir / entry["path"]
        assert published.is_file()
        # 逐项吻合：公开发布的就是声明的那份字节。
        assert _sha256(published) == entry["sha256"] == _sha256(source)
        assert published.stat().st_size == entry["size"]
    assert rs.report_url(manifest) == (
        f"/api/outputs/subjects/{p1_subject.subject_id}/reports/{run.report_id}/report.pdf"
    )

    # 公开 metadata 是 schema 合法投影，且不含任何宿主内部信息。
    public = json.loads((run.public_dir / rs.METADATA_NAME).read_text("utf-8"))
    _schema_validator("ReportMetadata").validate(public)
    for entry in public["files"]:
        _schema_validator("ReportFile").validate(entry)
    for leaked in ("staging_dir", "public_dir", "owner_pid", "failure_detail"):
        assert leaked not in public
    # 权威 metadata 留在私有目录，并且带服务端内部字段。
    private = json.loads(run.metadata_path.read_text("utf-8"))
    assert private["staging_dir"] == str(run.staging_dir)
    assert private["public_dir"] == str(run.public_dir)
    assert private["owner_pid"] == os.getpid()
    assert private["status"] == rs.STATUS_COMPLETED
    assert rs.read_published_manifest(p1_subject.subject_id, run.report_id).files == manifest.files
    assert sorted(item.name for item in run.public_dir.iterdir()) == [
        "chart_1.png",
        "chart_2.png",
        "metadata.json",
        "report.md",
        "report.pdf",
    ]
    # 临时发布目录不残留。
    assert not list(run.public_dir.parent.glob(".publishing-*"))


def test_publish_with_passed_verification(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    manifest = _publish_ok(run, verification_status=rs.VERIFICATION_PASSED)
    assert manifest.verification_status == rs.VERIFICATION_PASSED
    public = json.loads((run.public_dir / rs.METADATA_NAME).read_text("utf-8"))
    _schema_validator("ReportMetadata").validate(public)


def test_publish_rejects_failed_verification(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)

    with pytest.raises(SubjectOperationError) as info:
        rs.publish_report_run(run, files=declared, verification_status=rs.VERIFICATION_FAILED)

    assert info.value.code is ErrorCode.CHART_FAILED
    assert not run.public_dir.exists()
    # R3：被拒绝的发布必须收尾成 failed（不能留下假 running/active），但仍无 URL。
    assert rs.read_run_manifest(run).status == rs.STATUS_FAILED
    assert not rs.report_run_is_active(run)
    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(run, files=declared, verification_status="maybe")


def test_publish_rejects_unknown_role_duplicates_and_missing_main_document(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)

    def _variant(**changes: object) -> list[dict]:
        return [dict(entry) for entry in declared]

    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(
            run,
            files=[*declared, {"path": "clip.mp4", "size": 1, "sha256": "0" * 64, "role": "video"}],
            verification_status=rs.VERIFICATION_NOT_REQUESTED,
        )
    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(
            run,
            files=[*declared, dict(declared[0])],
            verification_status=rs.VERIFICATION_NOT_REQUESTED,
        )
    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(
            run, files=declared[1:], verification_status=rs.VERIFICATION_NOT_REQUESTED
        )
    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(
            run,
            files=[entry for entry in declared if entry["role"] != rs.ROLE_PDF],
            verification_status=rs.VERIFICATION_NOT_REQUESTED,
        )
    assert not run.public_dir.exists()
    assert _variant()


def test_publish_rejects_more_than_eight_charts(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    charts = tuple(f"chart_{index}.png" for index in range(1, 10))
    declared = _materialize(run, charts=charts)

    with pytest.raises(json_store.InvalidInputError) as info:
        _publish_ok(run, files=declared)
    assert info.value.code is ErrorCode.INVALID_INPUT
    assert not run.public_dir.exists()


# ---------------------------------------------------------------------------
# 发布拒绝：内容、路径、链接
# ---------------------------------------------------------------------------
def test_publish_rejects_declared_size_and_hash_mismatch(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)

    tampered = [dict(entry) for entry in declared]
    tampered[0]["sha256"] = "0" * 64
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=tampered)

    tampered = [dict(entry) for entry in declared]
    tampered[1]["size"] = tampered[1]["size"] + 1
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=tampered)

    empty = [dict(entry) for entry in declared]
    (run.workdir / "report.pdf").write_bytes(b"")
    empty[1]["size"] = 0
    empty[1]["sha256"] = hashlib.sha256(b"").hexdigest()
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=empty)

    assert not run.public_dir.exists()
    assert not list(run.workdir.parent.glob(".publishing-*"))


def test_publish_rejects_paths_outside_the_run_workdir(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    outside = run.workdir.parent / "outside.md"
    outside.write_text("外部文件\n", encoding="utf-8")

    for bad_path in ("../outside.md", "/etc/hostname", "sub/report.md", "..", "."):
        forged = [dict(entry) for entry in declared]
        forged[0]["path"] = bad_path
        with pytest.raises(json_store.InvalidInputError):
            _publish_ok(run, files=forged)

    # 模型不能指定"从别的地方复制过来"：工作目录之外的文件即使同名也不会被读。
    sneaky = [dict(entry) for entry in declared]
    sneaky[0] = {
        "path": "extra.md",
        "size": outside.stat().st_size,
        "sha256": _sha256(outside),
        "role": rs.ROLE_MARKDOWN,
    }
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=sneaky)
    assert not run.public_dir.exists()


def test_publish_rejects_symlinked_and_non_regular_artifacts(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    real = run.workdir / "real.png"
    real.write_bytes(_png_bytes())
    chart = run.workdir / "chart_1.png"
    chart.unlink()
    chart.symlink_to(real)

    with pytest.raises((StorageIOError, json_store.InvalidInputError)):
        _publish_ok(run, files=declared)
    assert not run.public_dir.exists()

    # 目录冒充正文：常规文件检查必须拦住。
    chart.unlink()
    chart.write_bytes(_png_bytes())
    (run.workdir / "report.pdf").unlink()
    (run.workdir / "report.pdf").mkdir()
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=declared)
    assert not run.public_dir.exists()


def test_publish_rejects_a_run_from_another_subject_directory(p1_subject, p1_subject_b) -> None:
    """跨科：把文件写到别的 subject 的目录里，不能借清单把它发布成本科的产物。"""
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    foreign_run = rs.create_report_run(p1_subject_b.subject_id)
    foreign = foreign_run.workdir / "report.md"
    foreign.write_text("别的科目的正文\n", encoding="utf-8")

    forged = [dict(entry) for entry in declared]
    forged[0]["path"] = str(foreign)
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=forged)
    assert not run.public_dir.exists()


# ---------------------------------------------------------------------------
# 发布失败注入：没有半完成目录、没有 URL、旧报告不变
# ---------------------------------------------------------------------------
def test_injected_publish_failure_keeps_old_report_and_leaves_no_partial_dir(
    p1_subject, monkeypatch
) -> None:
    old_run = rs.create_report_run(p1_subject.subject_id)
    old_manifest = _publish_ok(old_run)
    old_before = helpers.tree_digest(old_run.public_dir)

    new_run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(new_run)

    real_replace = os.replace

    def failing_replace(source, destination, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(destination).endswith(new_run.report_id):
            raise OSError("injected publish failure")
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(rs.os, "replace", failing_replace)
    with pytest.raises(SubjectOperationError) as info:
        _publish_ok(new_run, files=declared)
    assert info.value.code is ErrorCode.STORAGE_IO

    assert not new_run.public_dir.exists()
    assert not list(new_run.public_dir.parent.glob(".publishing-*"))
    assert helpers.tree_digest(old_run.public_dir) == old_before
    assert rs.read_published_manifest(p1_subject.subject_id, old_run.report_id).files == (
        old_manifest.files
    )
    # 失败运行留在私有目录里，状态是 failed，没有 URL。
    failed = rs.read_run_manifest(new_run)
    assert failed.status == rs.STATUS_FAILED
    assert rs.report_url(failed) is None


def test_publish_twice_is_refused_and_the_completed_report_is_intact(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    manifest = _publish_ok(run)
    before = helpers.tree_digest(run.public_dir)

    (run.workdir / "report.md").write_text("# 被改过的正文\n", encoding="utf-8")
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run)

    assert helpers.tree_digest(run.public_dir) == before
    assert rs.read_run_manifest(run).status == rs.STATUS_COMPLETED
    assert rs.read_published_manifest(p1_subject.subject_id, run.report_id).files == manifest.files


def test_concurrent_publish_of_one_run_commits_exactly_once(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    outcomes: list[object] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            outcome: object = rs.publish_report_run(
                run, files=declared, verification_status=rs.VERIFICATION_NOT_REQUESTED
            )
        except BaseException as exc:  # noqa: BLE001 - 记录真实结果
            outcome = exc
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [item for item in outcomes if isinstance(item, rs.ReportManifest)]
    losers = [item for item in outcomes if isinstance(item, BaseException)]
    assert len(winners) == 1, outcomes
    assert len(losers) == 3
    assert all(isinstance(item, (SubjectOperationError, SubjectStorageError)) for item in losers)
    assert sorted(item.name for item in run.public_dir.iterdir()) == [
        "chart_1.png",
        "metadata.json",
        "report.md",
        "report.pdf",
    ]
    assert not list(run.public_dir.parent.glob(".publishing-*"))
    assert rs.read_run_manifest(run).status == rs.STATUS_COMPLETED


# ---------------------------------------------------------------------------
# 失败与活跃登记
# ---------------------------------------------------------------------------
def test_fail_marks_failed_without_url_and_releases_the_run(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    assert rs.report_run_is_active(run)
    assert run.report_id in rs.active_report_runs()

    failed = rs.fail_report_run(run, detail="模型中途失败")

    assert failed.status == rs.STATUS_FAILED
    assert failed.files == ()
    assert rs.report_url(failed) is None
    assert not run.public_dir.exists()
    assert not rs.report_run_is_active(run)
    assert rs.active_report_runs() == ()
    # 失败之后不能再发布。
    declared = _materialize(run)
    with pytest.raises(json_store.InvalidInputError):
        _publish_ok(run, files=declared)
    assert not run.public_dir.exists()


def test_failed_run_cannot_erase_an_already_completed_report(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    completed = _publish_ok(run)
    before = helpers.tree_digest(run.public_dir)

    again = rs.fail_report_run(run, detail="迟到的失败")

    assert again.status == rs.STATUS_COMPLETED
    assert rs.read_run_manifest(run).status == rs.STATUS_COMPLETED
    assert helpers.tree_digest(run.public_dir) == before
    assert rs.read_published_manifest(p1_subject.subject_id, run.report_id) is not None
    assert completed.report_id == run.report_id


def test_stale_running_is_abandoned_but_a_live_run_is_not(p1_subject) -> None:
    live = rs.create_report_run(p1_subject.subject_id)
    assert rs.mark_abandoned_if_stale(live) is None
    assert rs.read_run_manifest(live).status == rs.STATUS_RUNNING

    stale = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(stale)  # 模拟"持有它的执行已经结束"
    assert rs.mark_abandoned_if_stale(stale) is not None
    assert rs.read_run_manifest(stale).status == rs.STATUS_ABANDONED
    assert rs.mark_abandoned_if_stale(stale) is None  # 幂等：已不是 running
    assert rs.read_run_manifest(live).status == rs.STATUS_RUNNING


def test_running_left_by_a_dead_process_is_abandoned(p1_subject, tmp_path) -> None:
    """真实进程结束留下的 running：只有本进程登记表能证明活跃。"""
    assert hasattr(os, "fork"), "该断言需要真实进程边界"
    handoff = tmp_path / "child_run.txt"
    pid = os.fork()
    if pid == 0:  # pragma: no cover - 子进程
        try:
            child_run = rs.create_report_run(p1_subject.subject_id)
            handoff.write_text(child_run.report_id, encoding="utf-8")
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0

    report_id = handoff.read_text(encoding="utf-8").strip()
    assert report_id and report_id not in rs.active_report_runs()

    recovered = rs.ReportRun(
        report_id=report_id,
        subject_id=p1_subject.subject_id,
        staging_dir=Path(p1_subject.root) / rs.REPORT_RUNS_DIRNAME / report_id,
        public_dir=Path(p1_subject.outputs) / rs.REPORTS_DIRNAME / report_id,
        created_at=0,
        owner_pid=pid,
    )
    stale = rs.read_run_manifest(recovered)
    assert stale.status == rs.STATUS_RUNNING
    assert stale.owner_pid == pid
    assert not rs.report_run_is_active(stale)
    abandoned = rs.mark_abandoned_if_stale(recovered)
    assert abandoned is not None and abandoned.status == rs.STATUS_ABANDONED
    assert rs.read_run_manifest(recovered).status == rs.STATUS_ABANDONED


# ---------------------------------------------------------------------------
# review 解析
# ---------------------------------------------------------------------------
def test_resolve_latest_skips_non_completed_reports(p1_subject, monkeypatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(rs, "time", clock)

    first = rs.create_report_run(p1_subject.subject_id)
    first_manifest = _publish_ok(first)

    second = rs.create_report_run(p1_subject.subject_id)
    second_manifest = _publish_ok(second)

    running = rs.create_report_run(p1_subject.subject_id)
    failed = rs.create_report_run(p1_subject.subject_id)
    rs.fail_report_run(failed)
    abandoned = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(abandoned)
    rs.mark_abandoned_if_stale(abandoned)

    latest = rs.resolve_report_for_review(p1_subject.subject_id)

    assert latest.report_id == second_manifest.report_id
    assert latest.reviewed_from == second.report_id
    assert latest.created_at == second_manifest.created_at
    assert latest.status == rs.STATUS_COMPLETED
    assert first_manifest.created_at < second_manifest.created_at

    # 明确指定 id 只发现完成态。
    assert (
        rs.resolve_report_for_review(p1_subject.subject_id, report_id=first.report_id).report_id
        == first.report_id
    )
    for not_ready in (running.report_id, failed.report_id, abandoned.report_id):
        with pytest.raises(SubjectOperationError) as info:
            rs.resolve_report_for_review(p1_subject.subject_id, report_id=not_ready)
        assert info.value.code is ErrorCode.ENTRY_NOT_FOUND
    with pytest.raises(json_store.InvalidInputError):
        rs.resolve_report_for_review(p1_subject.subject_id, report_id="not-a-uuid")
    with pytest.raises(SubjectOperationError) as info:
        rs.resolve_report_for_review(p1_subject.subject_id, report_id="f" * 32)
    assert info.value.code is ErrorCode.ENTRY_NOT_FOUND


def test_resolve_rejects_two_sources_at_once(p1_subject) -> None:
    with pytest.raises(json_store.InvalidInputError):
        rs.resolve_report_for_review(
            p1_subject.subject_id, report_id="0" * 32, legacy_path="report-1.md"
        )


def _make_legacy(subject, stem: str = "report-1700000000", *, color=(9, 9, 9)) -> Path:
    reports_dir = Path(subject.outputs) / rs.REPORTS_DIRNAME
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown = reports_dir / f"{stem}.md"
    markdown.write_text("# 旧报告\n![chart 1](chart_1.png)\n", encoding="utf-8")
    markdown.with_suffix(".pdf").write_bytes(b"%PDF-1.4 legacy\n")
    (reports_dir / "chart_1.png").write_bytes(_png_bytes(color))
    return markdown


def test_legacy_report_is_discovered_without_touching_the_tree(p1_subject) -> None:
    markdown = _make_legacy(p1_subject)
    reports_dir = markdown.parent

    read_only = {}
    for item in sorted(reports_dir.iterdir()):
        if item.is_file():
            read_only[item.name] = _sha256(item)
    before = helpers.tree_digest(reports_dir)

    manifest = rs.resolve_report_for_review(p1_subject.subject_id)

    assert manifest.report_id == f"legacy:{markdown.name}"
    assert manifest.status == rs.STATUS_COMPLETED
    assert manifest.reviewed_from == markdown.name
    assert manifest.subject_id == p1_subject.subject_id
    assert {entry.role for entry in manifest.files} == {
        rs.ROLE_MARKDOWN,
        rs.ROLE_PDF,
        rs.ROLE_CHART,
    }
    for entry in manifest.files:
        assert _sha256(reports_dir / entry.path) == entry.sha256

    by_path = rs.resolve_report_for_review(p1_subject.subject_id, legacy_path=markdown.name)
    assert by_path.report_id == manifest.report_id
    by_pdf = rs.resolve_report_for_review(
        p1_subject.subject_id, legacy_path=str(markdown.with_suffix(".pdf"))
    )
    assert by_pdf.reviewed_from == markdown.name

    # 旧文件一个字都没被改。
    assert helpers.tree_digest(reports_dir) == before
    for name, digest in read_only.items():
        assert _sha256(reports_dir / name) == digest


def test_legacy_resolution_rejects_unknown_and_out_of_tree_without_reading(
    p1_subject, p1_subject_b, tmp_path
) -> None:
    markdown = _make_legacy(p1_subject)
    reports_dir = markdown.parent

    # 陌生 md（内容是二进制垃圾）：不许当"已知报告"，也不许被读出来。
    unknown = reports_dir / "notes.md"
    unknown.write_bytes(b"\xff\xfe\x00\x01 not utf-8 \x00")
    with pytest.raises(SubjectOperationError) as info:
        rs.resolve_report_for_review(p1_subject.subject_id, legacy_path="notes.md")
    assert info.value.code is ErrorCode.ENTRY_NOT_FOUND

    outside = tmp_path / "outside.md"
    outside.write_text("# 外部\n", encoding="utf-8")
    strange = tmp_path / "report-1700000000.md"
    strange.write_text("# 外部同名\n", encoding="utf-8")

    for bad in (str(outside), str(strange), "../outside.md", "/etc/hostname", "报告.txt", ""):
        with pytest.raises((SubjectOperationError, SubjectStorageError)):
            rs.resolve_report_for_review(p1_subject.subject_id, legacy_path=bad)

    # 跨科：B 科的目录里放一份合法旧报告，用 A 科去解析也不行。
    foreign = _make_legacy(p1_subject_b)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        rs.resolve_report_for_review(p1_subject.subject_id, legacy_path=str(foreign))
    assert (
        rs.resolve_report_for_review(
            p1_subject_b.subject_id, legacy_path=foreign.name
        ).reviewed_from
        == foreign.name
    )

    # symlink 指向同目录合法文件：拒绝，不跟随。
    link = reports_dir / "report-1700000001.md"
    link.symlink_to(markdown)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        rs.resolve_report_for_review(p1_subject.subject_id, legacy_path=link.name)


def test_resolve_does_not_create_directories_and_404s_on_empty_subject(p1_subject) -> None:
    reports_dir = Path(p1_subject.outputs) / rs.REPORTS_DIRNAME
    assert not reports_dir.exists()

    with pytest.raises(SubjectOperationError) as info:
        rs.resolve_report_for_review(p1_subject.subject_id)

    assert info.value.code is ErrorCode.ENTRY_NOT_FOUND
    assert not reports_dir.exists()
    assert rs.read_published_manifest(p1_subject.subject_id, "a" * 32) is None


def test_corrupt_published_metadata_is_reported_not_skipped(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    _publish_ok(run)
    metadata = run.public_dir / rs.METADATA_NAME

    metadata.write_text('{"schema_version": 2, "report_id": "x"}', encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        rs.read_published_manifest(p1_subject.subject_id, run.report_id)
    with pytest.raises(StorageCorruptError):
        rs.resolve_report_for_review(p1_subject.subject_id)

    metadata.write_text('{"schema_version": 1, "report_id": NaN}', encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        rs.read_published_manifest(p1_subject.subject_id, run.report_id)


def test_private_metadata_rejects_unknown_status_and_nonfinite(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    payload = json.loads(run.metadata_path.read_text("utf-8"))
    payload["status"] = "half_done"
    run.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        rs.read_run_manifest(run)


def test_public_projection_is_valid_for_every_completed_status(p1_subject, monkeypatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(rs, "time", clock)
    validator = _schema_validator("ReportMetadata")
    for index in range(3):
        run = rs.create_report_run(p1_subject.subject_id)
        charts = tuple(f"chart_{n}.png" for n in range(1, index + 1))
        manifest = _publish_ok(run, files=_materialize(run, charts=charts))
        public = json.loads((run.public_dir / rs.METADATA_NAME).read_text("utf-8"))
        validator.validate(public)
        assert len(manifest.files) == 2 + index
        for entry in manifest.files:
            _schema_validator("ReportFile").validate(entry.as_contract())


def test_report_store_never_accepts_a_path_object_as_a_run(p1_subject) -> None:
    for bad in (Path("/tmp"), "0" * 32, None, {"report_id": "0" * 32}):
        with pytest.raises(json_store.InvalidInputError):
            rs.publish_report_run(  # type: ignore[arg-type]
                bad, files=[], verification_status=rs.VERIFICATION_NOT_REQUESTED
            )


def test_metadata_owner_pid_is_not_the_liveness_proof(p1_subject) -> None:
    """只凭 owner_pid 存在不能证明运行仍活跃（同 PID 复用是最常见的误判）。"""
    run = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(run)
    manifest = rs.read_run_manifest(run)
    assert manifest.owner_pid == os.getpid()  # 该 PID 确实存在（就是本进程）
    assert not rs.report_run_is_active(run)
    assert rs.mark_abandoned_if_stale(run) is not None
    assert sys.version_info >= (3, 11)


# ---------------------------------------------------------------------------
# R2：服务端身份、保留产物名与严格 metadata 类型
# ---------------------------------------------------------------------------
def test_publish_revalidates_server_owned_public_path(p1_subject, tmp_path: Path) -> None:
    """``dataclass`` 类型不是所有权证明：伪造 public_dir 必须在任何写入前被拒。"""
    from dataclasses import replace

    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    forged = replace(run, public_dir=tmp_path / "outside-public")
    before = helpers.tree_digest(run.staging_dir)

    with pytest.raises(json_store.InvalidInputError):
        rs.publish_report_run(
            forged, files=declared, verification_status=rs.VERIFICATION_NOT_REQUESTED
        )

    assert not forged.public_dir.exists()
    assert helpers.tree_digest(run.staging_dir) == before
    assert not (tmp_path / "outside-public").exists()


def test_forged_run_paths_are_rejected_before_any_write(p1_subject, tmp_path: Path) -> None:
    """staging/workdir/attempts/metadata 任一路径被换掉都拒绝，且不落任何文件。"""
    from dataclasses import replace

    run = rs.create_report_run(p1_subject.subject_id)
    outside = tmp_path / "foreign-staging"
    outside.mkdir()
    forged_variants = [
        replace(run, staging_dir=outside),
        replace(run, staging_dir=outside, public_dir=run.public_dir),
        replace(run, report_id="f" * 32),
    ]
    for forged in forged_variants:
        for call in (
            lambda item: rs.read_run_manifest(item),
            lambda item: rs.fail_report_run(item),
            lambda item: rs.mark_abandoned_if_stale(item),
            lambda item: rs.publish_report_run(
                item, files=[], verification_status=rs.VERIFICATION_NOT_REQUESTED
            ),
        ):
            with pytest.raises((json_store.InvalidInputError, SubjectOperationError)):
                call(forged)
    assert sorted(item.name for item in outside.iterdir()) == []
    # 唯一允许出现的新目录是隔离运行根；没有任何来自伪造 run 的写入。
    assert sorted(item.name for item in tmp_path.iterdir()) == sorted(
        [outside.name, "deeptutor-home"]
    )


def test_legitimate_reconstructed_run_is_accepted(p1_subject) -> None:
    """合法读取允许消费端重建对象：只要路径与服务端推出的完全一致。"""
    run = rs.create_report_run(p1_subject.subject_id)
    rebuilt = rs.ReportRun(
        report_id=run.report_id,
        subject_id=run.subject_id,
        staging_dir=run.staging_dir,
        public_dir=run.public_dir,
        created_at=run.created_at,
        owner_pid=run.owner_pid,
        reviewed_from=run.reviewed_from,
    )
    assert rs.require_report_run(rebuilt) is rebuilt
    assert rs.read_run_manifest(rebuilt).report_id == run.report_id


def test_a_real_non_admin_user_only_sees_its_own_report_tree(p1_runtime, monkeypatch) -> None:
    """跨用户：普通用户既不能读也不能发布 admin 作用域的 run，对方树逐字节不变。"""
    from deeptutor.multi_user import identity
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user, user_context

    admin_subject = helpers.make_subject(p1_runtime, "管理员科目")
    admin_run = rs.create_report_run(admin_subject.subject_id)
    declared = _materialize(admin_run)
    admin_before = helpers.tree_digest(admin_run.staging_dir)

    identity.save_user("report-admin-seed", "x", role="user")
    account = identity.save_user("report-user", "x", role="user")
    user = CurrentUser(
        id=account["id"],
        username=account["id"],
        role="user",
        scope=scope_for_user(account["id"], is_admin=False),
    )
    with user_context(user):
        for call in (
            lambda: rs.read_run_manifest(admin_run),
            lambda: rs.fail_report_run(admin_run),
            lambda: rs.mark_abandoned_if_stale(admin_run),
            lambda: rs.publish_report_run(
                admin_run, files=declared, verification_status=rs.VERIFICATION_NOT_REQUESTED
            ),
        ):
            with pytest.raises((json_store.InvalidInputError, SubjectOperationError)):
                call()

        # 同一套 API 在该用户自己的作用域里正常工作（合法当前用户正例）。
        from deeptutor.subjects import store as subject_store

        record = subject_store.create_subject("用户自己的科目")
        own_run = rs.create_report_run(record["id"])
        assert str(own_run.staging_dir).find(str(p1_runtime)) == 0
        assert own_run.staging_dir != admin_run.staging_dir
        rs.release_report_run(own_run)

    assert helpers.tree_digest(admin_run.staging_dir) == admin_before
    assert not admin_run.public_dir.exists()


def test_published_artifact_cannot_collide_with_metadata(p1_subject) -> None:
    """保留名/固定 role 名：metadata、脚本、日志、cache 与名字/role 混用都拒绝。"""
    forbidden = [
        ("metadata.json", rs.ROLE_MARKDOWN),
        ("_chart.py", rs.ROLE_MARKDOWN),
        ("_ode_check.py", rs.ROLE_MARKDOWN),
        ("report.log", rs.ROLE_MARKDOWN),
        ("report.md", rs.ROLE_PDF),
        ("report.pdf", rs.ROLE_MARKDOWN),
        ("chart_1.md", rs.ROLE_CHART),
        ("report.md", rs.ROLE_CHART),
        ("chart_9.png", rs.ROLE_CHART),
        (".hidden.png", rs.ROLE_CHART),
    ]
    for name, role in forbidden:
        run = rs.create_report_run(p1_subject.subject_id)
        declared = _materialize(run)
        # 用**真实字节**声明（size/sha 都对）：这样命中的只能是保留名/role 名字门，
        # 不会被"大小/摘要不符"顺带挡掉。
        forged = run.workdir / name
        if forged.exists() and forged.is_dir():
            continue
        forged.parent.mkdir(parents=True, exist_ok=True)
        forged.write_bytes(b"# content\n")
        declared[0] = _entry(forged, role)
        with pytest.raises(json_store.InvalidInputError):
            rs.publish_report_run(
                run, files=declared, verification_status=rs.VERIFICATION_NOT_REQUESTED
            )
        assert not run.public_dir.exists()

    # 固定名字的正例照常通过。
    run = rs.create_report_run(p1_subject.subject_id)
    manifest = _publish_ok(run, files=_materialize(run))
    assert sorted(entry.path for entry in manifest.files) == [
        "chart_1.png",
        "report.md",
        "report.pdf",
    ]


def test_metadata_written_after_copy_cannot_overwrite_the_published_bytes(p1_subject) -> None:
    """公开 metadata 写入发生在复制之后：它不能覆盖已发布的正文/PDF/图字节。"""
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    manifest = _publish_ok(run, files=declared)

    published = {entry.path: entry for entry in manifest.files}
    for name, entry in published.items():
        payload = (run.public_dir / name).read_bytes()
        import hashlib

        assert hashlib.sha256(payload).hexdigest() == entry.sha256
        assert len(payload) == entry.size
    public_metadata = json.loads((run.public_dir / rs.METADATA_NAME).read_text("utf-8"))
    assert public_metadata["files"] == [entry.as_contract() for entry in manifest.files]
    for internal in ("staging_dir", "public_dir", "owner_pid", "owner_birth"):
        assert internal not in public_metadata


METADATA_TYPE_PATCHES = [
    {"status": []},
    {"status": {"running": True}},
    {"verification_status": []},
    {"schema_version": True},
    {"schema_version": "1"},
    {"created_at": True},
    {"report_id": []},
    {"files": "not-a-list"},
    {"owner_pid": []},
]


@pytest.mark.parametrize("patch", METADATA_TYPE_PATCHES)
def test_bad_metadata_has_stable_corruption_error(p1_subject, patch: dict) -> None:
    """坏类型必须稳定报 storage_corrupt，不能抛 unhashable TypeError 之类裸异常。"""
    run = rs.create_report_run(p1_subject.subject_id)
    payload = json.loads(run.metadata_path.read_text("utf-8"))
    payload.update(patch)
    run.metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StorageCorruptError) as info:
        rs.read_run_manifest(run)

    # SubjectStorageError 是"C01 存储"异常族，没有 C02 的 code；固定消息必须一致。
    assert "科目数据文件已损坏" in str(info.value)
    # 被拒原值不回显。
    for value in patch.values():
        assert str(value) not in str(info.value) or value in (True, "1")


def test_metadata_bool_schema_version_is_not_one(p1_subject) -> None:
    """``True == 1`` 是 Python 的陷阱，契约要求 schema_version 是真 int 且恰为 1。"""
    run = rs.create_report_run(p1_subject.subject_id)
    payload = json.loads(run.metadata_path.read_text("utf-8"))
    assert payload["schema_version"] == 1
    payload["schema_version"] = True
    run.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        rs.read_run_manifest(run)


# ---------------------------------------------------------------------------
# R3：创建竞争、失败收尾与跨进程 abandoned 判定
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fault", ["digest", "verification", "declaration"])
def test_publish_rejection_finishes_run_and_releases_active(p1_subject, fault: str) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    status = rs.VERIFICATION_NOT_REQUESTED
    if fault == "digest":
        declared[0] = {**declared[0], "sha256": "0" * 64}
    elif fault == "verification":
        status = rs.VERIFICATION_FAILED
    else:
        declared = []

    with pytest.raises(SubjectOperationError):
        rs.publish_report_run(run, files=declared, verification_status=status)

    current = rs.read_run_manifest(run)
    assert current.status == rs.STATUS_FAILED, "失败发布仍留下 running 状态"
    assert not rs.report_run_is_active(run), "早期拒绝绕过 finally 导致 active 泄漏"
    assert not run.public_dir.exists() and rs.report_url(current) is None


def test_fail_cleanup_survives_corrupt_manifest(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    run.metadata_path.write_text('{"broken": true}', encoding="utf-8")

    with pytest.raises(SubjectStorageError):
        rs.fail_report_run(run)

    assert not rs.report_run_is_active(run), "fail 在读取坏 metadata 时未释放 active"
    # 损坏原件必须保留（不能被"修复"成新的空 metadata）。
    assert run.metadata_path.read_text("utf-8") == '{"broken": true}'


def test_publish_with_corrupt_manifest_releases_active_without_repair(p1_subject) -> None:
    run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(run)
    run.metadata_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SubjectStorageError):
        rs.publish_report_run(
            run, files=declared, verification_status=rs.VERIFICATION_NOT_REQUESTED
        )

    assert not rs.report_run_is_active(run)
    assert run.metadata_path.read_text("utf-8") == "{not json"
    assert not run.public_dir.exists()


def test_uuid_create_race_cannot_delete_successful_creator(p1_runtime, monkeypatch) -> None:
    """两个已越过 exists 检查的并发 create：失败者不能删掉成功者的 staging。"""
    import threading
    import uuid as uuid_module

    rs._reset_active_runs_for_tests()
    subject = helpers.make_subject(p1_runtime, "UUID竞争")
    fixed = uuid_module.UUID("11" * 16)
    monkeypatch.setattr(rs.uuid, "uuid4", lambda: fixed)

    real = rs.json_store.make_directory
    barrier = threading.Barrier(2)
    complete = threading.Event()
    guard = threading.Lock()
    order: list[int] = []
    result: list[object] = []

    def intercepted(path, **kwargs):  # type: ignore[no-untyped-def]
        if Path(path).name == fixed.hex and kwargs.get("exist_ok") is False:
            with guard:
                index = len(order)
                order.append(index)
            barrier.wait(timeout=5)
            if index == 1:
                assert complete.wait(5)
        return real(path, **kwargs)

    monkeypatch.setattr(rs.json_store, "make_directory", intercepted)

    def create() -> None:
        try:
            result.append(rs.create_report_run(subject.subject_id))
            complete.set()
        except BaseException as exc:  # noqa: BLE001 - 记录真实结果
            result.append(exc)

    first = threading.Thread(target=create)
    second = threading.Thread(target=create)
    first.start()
    second.start()
    first.join(7)
    second.join(7)

    assert not first.is_alive() and not second.is_alive()
    winners = [item for item in result if isinstance(item, rs.ReportRun)]
    assert len(winners) == 1, result
    assert winners[0].metadata_path.is_file(), "失败竞争者删掉了成功者的整个 staging"
    assert len(order) == 2
    rs.release_report_run(winners[0])
    rs._reset_active_runs_for_tests()


def test_live_foreign_owner_is_not_declared_abandoned(p1_subject) -> None:
    """仍然存活的其他进程持有的 running 不能被写成 abandoned（出生标识可证）。"""
    ready_r, ready_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - 子进程
        os.close(ready_r)
        try:
            child_run = rs.create_report_run(p1_subject.subject_id)
            payload = dict(child_run.__dict__)
            payload["staging_dir"] = str(child_run.staging_dir)
            payload["public_dir"] = str(child_run.public_dir)
            os.write(ready_w, json.dumps(payload).encode())
            time.sleep(20)
        finally:
            os._exit(0)
    os.close(ready_w)
    try:
        payload = json.loads(os.read(ready_r, 4096))
        payload["staging_dir"] = Path(payload["staging_dir"])
        payload["public_dir"] = Path(payload["public_dir"])
        foreign = rs.ReportRun(**payload)

        assert not rs.report_run_is_active(foreign)
        assert rs.mark_abandoned_if_stale(foreign) is None
        assert rs.read_run_manifest(foreign).status == rs.STATUS_RUNNING
    finally:
        os.close(ready_r)
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        rs._reset_active_runs_for_tests()


def test_pid_reuse_does_not_keep_a_dead_owner_running(p1_subject) -> None:
    """PID 复用不能冒充"原拥有者还活着"：出生标识不匹配即判定已结束。"""
    run = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(run)
    payload = json.loads(run.metadata_path.read_text("utf-8"))
    # 同一 PID、不同出生标识 = 该 PID 现在是别的进程。
    payload["owner_pid"] = os.getpid()
    payload["owner_birth"] = "0"
    run.metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = rs.read_run_manifest(run)
    assert manifest.owner_pid == os.getpid()
    # 本进程就是记录里的 owner 且已不在 registry：判定为本 run 已结束（self_stale）。
    assert rs.mark_abandoned_if_stale(run) is not None


def test_unknown_owner_state_stays_running(p1_subject) -> None:
    """没有 owner 信息的记录：未知 ≠ abandoned，保守保持 running。"""
    run = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(run)
    payload = json.loads(run.metadata_path.read_text("utf-8"))
    payload.pop("owner_pid", None)
    payload.pop("owner_birth", None)
    run.metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    assert rs.mark_abandoned_if_stale(run) is None
    assert rs.read_run_manifest(run).status == rs.STATUS_RUNNING


def test_dead_foreign_owner_is_abandoned(p1_subject) -> None:
    """真正结束的其它进程留下的 running 仍然会被判定 abandoned。"""
    handoff = p1_subject.root.parent / "dead-owner-run.json"
    pid = os.fork()
    if pid == 0:  # pragma: no cover - 子进程
        try:
            child_run = rs.create_report_run(p1_subject.subject_id)
            payload = dict(child_run.__dict__)
            payload["staging_dir"] = str(child_run.staging_dir)
            payload["public_dir"] = str(child_run.public_dir)
            handoff.write_text(json.dumps(payload), encoding="utf-8")
        finally:
            os._exit(0)
    os.waitpid(pid, 0)

    payload = json.loads(handoff.read_text("utf-8"))
    payload["staging_dir"] = Path(payload["staging_dir"])
    payload["public_dir"] = Path(payload["public_dir"])
    dead = rs.ReportRun(**payload)

    assert rs.mark_abandoned_if_stale(dead) is not None
    assert rs.read_run_manifest(dead).status == rs.STATUS_ABANDONED


# Coordinator acceptance: remaining boundary failures, 2026-10-17.


@pytest.mark.parametrize("piece", ["staging", "work"])
def test_run_link_components_are_rejected_before_any_write(p1_subject, tmp_path, piece):
    from deeptutor.services.pdf import chart_executor as ce

    run = rs.create_report_run(p1_subject.subject_id)
    if piece == "attempts":
        outside = tmp_path / "outside-attempts"
        outside.mkdir()
        run.attempts_dir.rmdir()
        run.attempts_dir.symlink_to(outside)
    elif piece == "staging":
        outside = tmp_path / "outside-staging"
        shutil.move(run.staging_dir, outside)
        run.staging_dir.symlink_to(outside)
    else:
        outside = tmp_path / "outside-work"
        shutil.move(run.workdir, outside)
        run.workdir.symlink_to(outside)
    before = helpers.tree_digest(outside)
    with pytest.raises((SubjectOperationError, SubjectStorageError)):
        if piece == "work":
            ce.plan_chart_request(run, "chart_1.png")
        else:
            ce.begin_chart_attempt(run, "chart_1.png")
    assert helpers.tree_digest(outside) == before


def test_missing_metadata_failure_always_releases_active(p1_subject):
    run = rs.create_report_run(p1_subject.subject_id)
    run.metadata_path.unlink()
    with pytest.raises(SubjectOperationError):
        rs.fail_report_run(run)
    assert not rs.report_run_is_active(run), "missing metadata早于finally，active未释放"


def test_unreadable_birth_marker_is_not_proof_of_dead_owner(p1_subject, monkeypatch):
    run = rs.create_report_run(p1_subject.subject_id)
    rs.release_report_run(run)
    payload = json.loads(run.metadata_path.read_text())
    payload.update(owner_pid=os.getppid(), owner_birth="known-but-unreadable")
    run.metadata_path.write_text(json.dumps(payload))
    monkeypatch.setattr(rs, "process_birth_marker", lambda pid: None)
    assert rs.mark_abandoned_if_stale(run) is None
    assert rs.read_run_manifest(run).status == "running"


def test_metadata_digest_with_trailing_newline_is_corrupt(p1_subject):
    run = rs.create_report_run(p1_subject.subject_id)
    payload = json.loads(run.metadata_path.read_text())
    payload["files"] = [
        {"path": "report.md", "size": 1, "sha256": "a" * 64 + "\n", "role": "markdown"}
    ]
    run.metadata_path.write_text(json.dumps(payload))
    with pytest.raises(SubjectStorageError):
        rs.read_run_manifest(run)
