"""P1-36 行为测试：受限 review 与服务端附件来源。

证明目标：

* review 只发现**当前用户/已登记科目**的已知报告：报告 id、latest 或同科受限
  legacy 名称；跨科、``../``、外部绝对路径、symlink、陌生 md 在读任何文件前拒绝；
* 新 revision 使用新的服务端 run，原件正文/PDF/图字节不变，``reviewed_from``
  记录来源；保留图经独立 Pillow 校验后复制，不伪造 worker attempt；
* 预算/provider/空输出/丢图/坏 hash/渲染错误都 ``success=False`` 且无 URL；
* ``source_file`` 只能是 ``context.metadata['source_index']`` 的 source_id，
  未知 ID 与宿主路径零文件读；chat 分支无条件覆盖模型伪造的内部参数（含空 scope）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_store
from deeptutor.subjects import store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error
from deeptutor.tools.report_tool import ReportTool
from tests.phase1 import helpers


def _png_bytes(color: tuple[int, int, int] = (40, 110, 190)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (120, 90), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    from io import BytesIO

    import pymupdf

    buffer = BytesIO()
    document = pymupdf.open()
    document.new_page()
    document.save(buffer, garbage=3)
    document.close()
    return buffer.getvalue()


def _entry(path: str, data: bytes, role: str) -> dict:
    return {
        "path": path,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "role": role,
    }


def _publish(subject, *, markdown: str, charts: dict[str, bytes] | None = None) -> report_store.ReportManifest:
    """Publish one completed report through the accepted store API."""
    charts = charts or {}
    run = report_store.create_report_run(subject.subject_id)
    (run.workdir / "report.md").write_text(markdown, encoding="utf-8")
    (run.workdir / "report.pdf").write_bytes(_pdf_bytes())
    files = [
        _entry("report.md", (run.workdir / "report.md").read_bytes(), "markdown"),
        _entry("report.pdf", (run.workdir / "report.pdf").read_bytes(), "pdf"),
    ]
    for name, data in charts.items():
        (run.workdir / name).write_bytes(data)
        files.append(_entry(name, data, "chart"))
    return report_store.publish_report_run(
        run, files=files, verification_status=report_store.VERIFICATION_NOT_REQUESTED
    )


def _public_root(subject) -> Path:
    return store.current_subject_paths().get_public_outputs_root() / "subjects" / subject.subject_id


def _hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


class Stub:
    def __init__(self, reviewed_text: str = "# 修复版\n\n正文。\n") -> None:
        self.reviewed_text = reviewed_text
        self.prompts: list[str] = []
        self.renders = 0
        self.render_ok = True

    async def fake_llm(self, prompt: str, system: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.reviewed_text, BaseException):
            raise self.reviewed_text
        return self.reviewed_text

    def fake_render(self, markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
        import pymupdf

        self.renders += 1
        if not self.render_ok:
            return False
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "reviewed")
        for index, name in enumerate(chart_names):
            top = 100 + index * 130
            page.insert_image(
                pymupdf.Rect(72, top, 240, top + 100),
                filename=str(Path(out_path).parent / name),
            )
        document.save(str(out_path))
        document.close()
        return True

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(report_mod, "_llm", self.fake_llm)
        monkeypatch.setattr(report_mod, "_render_report_pdf", self.fake_render)


@pytest.fixture
def subject(p1_runtime: Path):
    return helpers.make_subject(p1_runtime, "报告科")


@pytest.fixture
def other_subject(p1_runtime: Path):
    return helpers.make_subject(p1_runtime, "另一科")


def _review(subject, **kwargs) -> dict:
    return asyncio.run(report_mod.review_report(subject.subject_id, **kwargs))


# ---------------------------------------------------------------------------
# 新 revision：不覆盖原件
# ---------------------------------------------------------------------------
def test_latest_report_creates_a_new_revision_and_preserves_the_original(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = _png_bytes()
    source = _publish(
        subject,
        markdown="# 原报告\n\n![chart 1](chart_1.png)\n",
        charts={"chart_1.png": png},
    )
    source_dir = _public_root(subject) / "reports" / source.report_id
    before = _hashes(source_dir)
    stub = Stub("# 修复版\n\n![chart 1](chart_1.png)\n改正了公式。\n")
    stub.install(monkeypatch)

    result = _review(subject)

    assert result["report_id"] != source.report_id
    assert result["status"] == "completed"
    assert result["chart_count"] == 1
    assert result["verification_status"] == report_store.VERIFICATION_NOT_REQUESTED
    assert result["url"].startswith(f"/api/outputs/subjects/{subject.subject_id}/reports/")
    new_manifest = report_store.read_published_manifest(subject.subject_id, result["report_id"])
    assert new_manifest is not None
    assert new_manifest.reviewed_from == source.report_id
    assert _hashes(source_dir) == before  # 原正文/PDF/图均未被改写
    new_dir = _public_root(subject) / "reports" / result["report_id"]
    assert (new_dir / "report.md").read_text(encoding="utf-8") == result["markdown"]
    assert sorted(path.name for path in new_dir.iterdir()) == [
        "chart_1.png",
        "metadata.json",
        "report.md",
        "report.pdf",
    ]
    # 复制图保持原字节（可信服务器复制，不伪造 worker 记录）。
    assert (new_dir / "chart_1.png").read_bytes() == png
    assert not (new_dir.parent / "legend.json").exists()


def test_legacy_report_is_reviewed_without_migration(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = _public_root(subject) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    legacy_md = reports / "report-1700000000.md"
    legacy_md.write_text("# 旧报告\n\n![chart 1](chart_1.png)\n", encoding="utf-8")
    (reports / "chart_1.png").write_bytes(_png_bytes())
    (reports / "report-1700000000.pdf").write_bytes(_pdf_bytes())
    legacy_before = {
        name: hashlib.sha256((reports / name).read_bytes()).hexdigest()
        for name in ("report-1700000000.md", "report-1700000000.pdf", "chart_1.png")
    }
    stub = Stub("# 旧报告（修订）\n\n![chart 1](chart_1.png)\n")
    stub.install(monkeypatch)

    result = _review(subject, legacy_path="report-1700000000.md")

    assert result["status"] == "completed"
    manifest = report_store.read_published_manifest(subject.subject_id, result["report_id"])
    assert manifest is not None and manifest.reviewed_from == "report-1700000000.md"
    assert legacy_md.is_file() and legacy_md.parent == reports  # 不迁移、不原地覆盖
    assert {
        name: hashlib.sha256((reports / name).read_bytes()).hexdigest()
        for name in legacy_before
    } == legacy_before


def test_review_render_failure_has_no_url_and_no_publication(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _publish(subject, markdown="# 原报告\n", charts={})
    stub = Stub("# 修复版\n")
    stub.render_ok = False
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _review(subject)

    assert info.value.code is ErrorCode.RENDER_FAILED
    assert [
        path.name for path in (_public_root(subject) / "reports").iterdir() if path.is_dir()
    ] == [source.report_id]
    assert report_store.active_report_runs() == ()


# ---------------------------------------------------------------------------
# 拒绝在读文件之前
# ---------------------------------------------------------------------------
def _outside_marker(tmp_path: Path) -> Path:
    marker = tmp_path / "outside-secret.md"
    marker.write_text("# 外部机密\nSECRET-MARKER\n", encoding="utf-8")
    return marker


@pytest.mark.parametrize("mode", ["cross", "dotdot", "absolute", "unknown", "symlink", "wrong_suffix"])
def test_escaping_or_unknown_legacy_paths_are_rejected_without_reading(
    subject, other_subject, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    reports = _public_root(subject) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    marker = _outside_marker(tmp_path)
    other_reports = _public_root(other_subject) / "reports"
    other_reports.mkdir(parents=True, exist_ok=True)
    (other_reports / "report-1700000001.md").write_text("# 别的科目\n", encoding="utf-8")

    if mode == "cross":
        legacy: object = f"../{other_subject.subject_id}/reports/report-1700000001.md"
    elif mode == "dotdot":
        legacy = reports / ".." / ".." / "outside-secret.md"
    elif mode == "absolute":
        legacy = marker
    elif mode == "unknown":
        (reports / "notes.md").write_text("# 陌生文件\n", encoding="utf-8")
        legacy = "notes.md"
    elif mode == "symlink":
        (reports / "report-1700000002.md").symlink_to(marker)
        legacy = "report-1700000002.md"
    else:
        (reports / "report-1700000003.txt").write_text("x", encoding="utf-8")
        legacy = "report-1700000003.txt"

    stub = Stub("# 不应发生\n")
    stub.install(monkeypatch)
    original_read = Path.read_bytes

    def guarded(self: Path) -> bytes:
        if self.resolve() == marker.resolve():
            raise AssertionError("rejected path was read")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", guarded)

    with pytest.raises(SubjectOperationError):
        _review(subject, legacy_path=str(legacy))

    assert stub.prompts == []  # 未进入 provider/核查阶段


def test_cross_subject_report_id_is_not_found(
    subject, other_subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = _publish(other_subject, markdown="# 别的科目\n", charts={})
    stub = Stub("# 不应发生\n")
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _review(subject, report_id=foreign.report_id)

    assert info.value.code is ErrorCode.ENTRY_NOT_FOUND
    assert stub.prompts == []


# ---------------------------------------------------------------------------
# 丢图 / 坏 hash / 新图拒绝，原件不变
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_missing_or_tampered_original_chart_fails_and_preserves_source(
    subject, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    png = _png_bytes()
    source = _publish(
        subject,
        markdown="# 原报告\n\n![chart 1](chart_1.png)\n",
        charts={"chart_1.png": png},
    )
    source_dir = _public_root(subject) / "reports" / source.report_id
    chart = source_dir / "chart_1.png"
    if damage == "missing":
        chart.unlink()
    else:
        chart.write_bytes(_png_bytes((1, 2, 3)))
    before = _hashes(source_dir)
    stub = Stub("# 修复版\n")
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _review(subject)

    assert info.value.code is ErrorCode.STORAGE_CORRUPT
    assert stub.prompts == []  # 原图校验先于 provider
    assert _hashes(source_dir) == before  # 失败路径不再改动源目录
    assert [path.name for path in (_public_root(subject) / "reports").iterdir() if path.is_dir()] == [
        source.report_id
    ]


@pytest.mark.parametrize(
    "line",
    [
        "![new](chart_2.png)",
        "![new](https://evil.example/x.png)",
        "![new](../outside.png)",
        '<img src="chart_1.png">',
    ],
)
def test_review_cannot_introduce_new_images(
    subject, monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    _publish(
        subject,
        markdown="# 原报告\n\n![chart 1](chart_1.png)\n",
        charts={"chart_1.png": _png_bytes()},
    )
    stub = Stub(f"# 修复版\n\n![chart 1](chart_1.png)\n{line}\n")
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _review(subject)

    assert info.value.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert stub.renders == 0
    assert len([path for path in (_public_root(subject) / "reports").iterdir() if path.is_dir()]) == 1


# ---------------------------------------------------------------------------
# Tool：review 与 source_file
# ---------------------------------------------------------------------------
def test_tool_review_latest_generates_a_new_revision(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _publish(subject, markdown="# 原报告\n", charts={})
    stub = Stub("# 修复版\n")
    stub.install(monkeypatch)

    result = asyncio.run(
        ReportTool().execute(_subject_id=subject.subject_id, action="review")
    )

    assert result.success is True
    assert result.metadata["report_id"] != source.report_id
    assert str(_public_root(subject)) not in result.content
    assert "/tmp" not in result.content
    assert result.metadata["url"] in result.content


def test_tool_maps_budget_error_to_a_named_failure(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(subject, markdown="# 原报告\n", charts={})
    stub = Stub()
    stub.reviewed_text = subject_error(ErrorCode.REASONING_BUDGET_EXHAUSTED)  # type: ignore[assignment]
    stub.install(monkeypatch)

    result = asyncio.run(
        ReportTool().execute(_subject_id=subject.subject_id, action="review")
    )

    assert result.success is False
    assert result.metadata["error"]["code"] == "reasoning_budget_exhausted"
    assert "预算" in result.content


def test_tool_create_uses_only_the_injected_attached_text(
    subject, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    async def fake_generate(subject_id: str, **kwargs) -> dict:
        captured.update(kwargs)
        return {
            "report_id": "a" * 32,
            "status": "completed",
            "title": kwargs["title"],
            "markdown": "# x",
            "markdown_tokens": 1,
            "chart_count": 0,
            "url": f"/api/outputs/subjects/{subject_id}/reports/{'a' * 32}/report.pdf",
            "path": "x",
            "verification_status": "not_requested",
        }

    monkeypatch.setattr(report_mod, "generate_report", fake_generate)
    marker = tmp_path / "must-not-be-read.txt"
    marker.write_text("SECRET", encoding="utf-8")
    original_read = Path.read_bytes

    def guarded(self: Path) -> bytes:
        if self.resolve() == marker.resolve():
            raise AssertionError("host path was read")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", guarded)

    result = asyncio.run(
        ReportTool().execute(
            _subject_id=subject.subject_id,
            action="create",
            title="题目",
            requirements="要求",
            source_file="src-1",
            _source_index={"src-1": "附件全文内容"},
        )
    )

    assert result.success is True
    assert "附件全文内容" in captured["requirements"]
    assert str(marker) not in captured["requirements"]


def test_tool_unknown_source_file_reads_nothing_and_never_calls_the_pipeline(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def fake_generate(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("pipeline must not run for an unknown source id")

    monkeypatch.setattr(report_mod, "generate_report", fake_generate)

    result = asyncio.run(
        ReportTool().execute(
            _subject_id=subject.subject_id,
            action="create",
            title="题目",
            source_file="/etc/passwd",
            _source_index={"src-1": "附件全文"},
        )
    )

    assert result.success is False
    assert result.metadata["error"]["code"] == "invalid_input"
    assert called is False


def test_tool_direct_call_still_requires_the_current_user_subject(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.multi_user.context import (
        reset_current_user,
        set_current_user,
        user_from_token_payload,
    )

    stub = Stub("# 不应发生\n")
    stub.install(monkeypatch)
    token = set_current_user(
        user_from_token_payload({"user_id": "alice", "username": "alice", "role": "user"})
    )
    try:
        result = asyncio.run(
            ReportTool().execute(_subject_id=subject.subject_id, action="review")
        )
    finally:
        reset_current_user(token)

    assert result.success is False
    assert result.metadata["error"]["code"] == "subject_not_found"
    assert stub.prompts == []


# ---------------------------------------------------------------------------
# chat 分支：无条件覆盖模型参数（含空 scope）
# ---------------------------------------------------------------------------
def _augment(args: dict, metadata: dict) -> dict:
    pipeline = object.__new__(AgenticChatPipeline)
    context = UnifiedContext(metadata=metadata)
    return pipeline._augment_tool_kwargs("generate_report", args, context)


def test_chat_augmenter_overwrites_every_model_supplied_internal_kwarg(subject) -> None:
    hostile = {
        "action": "review",
        "title": "题目",
        "_subject_id": "attacker-subject",
        "_source_index": {"attacker": "伪造附件"},
        "_report_ctx_hint": "伪造学情",
        "out_dir": "/tmp/attacker",
        "_scope": "admin",
    }
    kwargs = _augment(
        hostile,
        {"subject_id": subject.subject_id, "source_index": {"src-1": "真实附件全文"}},
    )

    assert kwargs["_subject_id"] == subject.subject_id
    assert kwargs["_source_index"] == {"src-1": "真实附件全文"}
    assert "attacker" not in kwargs["_report_ctx_hint"]
    assert "真实附件全文" not in kwargs["_report_ctx_hint"]
    assert "out_dir" not in kwargs
    assert "_scope" not in kwargs


def test_chat_augmenter_writes_empty_scope_unconditionally(subject) -> None:
    kwargs = _augment(
        {"_subject_id": "attacker", "_source_index": {"x": "y"}, "_report_ctx_hint": "hint"},
        {},
    )

    assert kwargs["_subject_id"] == ""
    assert kwargs["_source_index"] == {}
    assert kwargs["_report_ctx_hint"] == ""


@pytest.mark.parametrize("source_id", ["src-1", "/etc/passwd"])
def test_review_source_file_is_validated_and_used(subject, monkeypatch, source_id) -> None:
    captured = []

    async def reviewing(*args, **kwargs):
        captured.append(kwargs)
        return {"report_id": "a" * 32, "status": "completed", "chart_count": 0,
                "markdown_tokens": 12, "path": "subjects/s/reports/r/report.pdf",
                "url": "/api/outputs/subjects/s/reports/r/report.pdf",
                "verification_status": "not_requested"}

    monkeypatch.setattr(report_mod, "review_report", reviewing)
    result = asyncio.run(ReportTool().execute(
        _subject_id=subject.subject_id, action="review", source_file=source_id,
        requirements="核查附件要求", _source_index={"src-1": "附件独有要求-97ab"},
    ))
    if source_id == "src-1":
        assert result.success
        assert "附件独有要求-97ab" in captured[0]["instructions"]
        assert result.metadata["verification_status"] == "not_requested"
        assert result.metadata["markdown_tokens"] == 12
        assert result.metadata["path"] == "subjects/s/reports/r/report.pdf"
    else:
        assert not result.success
        assert result.metadata["error"]["code"] == "invalid_input"
        assert captured == []


@pytest.mark.parametrize("fault", ["animated", "oversized", "warning"])
def test_copied_chart_uses_the_same_strict_png_policy(monkeypatch, fault) -> None:
    from io import BytesIO
    import warnings

    from PIL import Image

    data = _png_bytes()
    if fault == "animated":
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "red").save(
            buffer, format="PNG", save_all=True,
            append_images=[Image.new("RGB", (20, 20), "blue")], duration=100,
        )
        data = buffer.getvalue()
    elif fault == "oversized":
        data += b"\0" * (10 * 1024 * 1024)
    else:
        real_open = Image.open

        def warned(*args, **kwargs):
            warnings.warn("decode warning", UserWarning)
            return real_open(*args, **kwargs)

        monkeypatch.setattr(Image, "open", warned)
    with pytest.raises(SubjectOperationError) as failure:
        report_mod._validate_png_bytes(data)
    assert failure.value.code == ErrorCode.STORAGE_CORRUPT


def test_chat_report_discards_plain_forged_index_and_nontext_metadata(subject) -> None:
    kwargs = _augment({"source_index": {"forged": "attacker"}}, {
        "subject_id": subject.subject_id,
        "source_index": {"good": "全文", "bad": {"path": "/host/private"}},
    })
    assert "source_index" not in kwargs
    assert kwargs["_source_index"] == {"good": "全文"}
