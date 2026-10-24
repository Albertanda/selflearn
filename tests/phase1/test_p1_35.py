"""P1-35 行为测试：完整报告生成与安全发布。

覆盖卡片证据清单的每个场景，全部走真实 :func:`report_store` 发布门与真实
Typst 渲染器（除显式验证并发/失败路径的 PDF 替身外，替身也写真实 PDF 字节）：

* 零/多空格/跨行占位符用同一 match 替换，且每张声明图验证后才写入正文；
* 任一声明图失败（坏 JSON/执行失败/ODE 失败/坏产物）→ 整体 ``chart_failed``，
  没有正式目录/URL，旧 completed 报告字节不变；
* 空/截断正文不编译、不发布；
* 两个并发 run 互不阻塞、各自发布自己的目录；
* 模型自带的图片引用只能是本 run 已验证 basename；外部 URL/穿越/绝对/引号/
  未验证图/HTML/reference 全部在 Typst 之前拒绝；
* 无声明图的纯正文报告合法；
* 真实 Typst 中文 + 真实 PNG 生成的 PDF 可被 parser 打开且确有页面/图片；
* 发布后的 Markdown 能被 ``resolve_report_for_review`` 发现（API/Tool 同一 pipeline）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import re

import pytest

from deeptutor.services.pdf import chart_validation, report_store
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf.chart_executor import ChartExecutionResult
from deeptutor.services.pdf.report_inputs import chart_target_basename
from deeptutor.subjects import store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error
from tests.phase1 import helpers

CODE = "import matplotlib.pyplot as plt\nplt.savefig('chart_1.png')\n"


@pytest.mark.parametrize("kind", ["oversized", "symlink", "fifo"])
def test_file_entry_refuses_unbounded_or_nonregular_artifacts(tmp_path, kind) -> None:
    import os

    path = tmp_path / "report.pdf"
    if kind == "oversized":
        with path.open("wb") as handle:
            handle.truncate(report_store.MAX_PUBLISHED_FILE_BYTES + 1)
    elif kind == "symlink":
        target = tmp_path / "other.pdf"
        target.write_bytes(b"%PDF-keep")
        path.symlink_to(target)
    else:
        os.mkfifo(path)
    with pytest.raises(SubjectOperationError) as error:
        report_mod._file_entry(path, "pdf")
    assert error.value.code == ErrorCode.RENDER_FAILED


def test_primary_report_error_survives_missing_cleanup_metadata(subject, monkeypatch) -> None:
    original = subject_error(ErrorCode.CHART_FAILED)

    async def failing(*args):
        for metadata in (subject.root / "_report_runs").glob("*/metadata.json"):
            metadata.unlink()
        raise original

    monkeypatch.setattr(report_mod, "_llm", failing)
    with pytest.raises(SubjectOperationError) as error:
        asyncio.run(report_mod.generate_report(subject.subject_id, title="题目", requirements=""))
    assert error.value is original
    assert report_store.active_report_runs() == ()


def test_duplicate_preparation_does_not_invalidate_the_legitimate_publication(subject) -> None:
    import pymupdf

    run = report_store.create_report_run(subject.subject_id)
    (run.workdir / "report.md").write_text("# 正文", encoding="utf-8")
    with pymupdf.open() as document:
        document.new_page()
        document.save(str(run.workdir / "report.pdf"))
    files = [report_mod._file_entry(run.workdir / name, role)
             for name, role in [("report.md", "markdown"), ("report.pdf", "pdf")]]
    prepared = report_store._prepare_report_publication(
        run, files=files, verification_status="not_requested")
    with pytest.raises(SubjectOperationError):
        report_store._prepare_report_publication(run, files=files, verification_status="not_requested")
    assert report_store.read_run_manifest(run).status == "running"
    committed = report_store._commit_report_publication(prepared)
    assert committed.status == "completed"
    assert (committed.public_dir / "report.pdf").is_file()


# ---------------------------------------------------------------------------
# 替身：provider + P34 executor/validator + PDF
# ---------------------------------------------------------------------------
def _png_bytes(color: tuple[int, int, int] = (32, 96, 200)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (320, 240), color).save(buffer, format="PNG")
    return buffer.getvalue()


class Stub:
    """Provider/executor stub that still produces real PNG/PDF bytes."""

    def __init__(self) -> None:
        self.writer_prompts: list[str] = []
        self.chart_prompts: list[str] = []
        self.executed: list[tuple[str, str]] = []
        self.ode_calls: list[str] = []
        self.renders: list[tuple[str, tuple[str, ...]]] = []
        self.bodies: dict[str, str] = {}
        self.default_body = "# 报告\n\n纯正文。\n"
        self.chart_response: str | None = None
        self.truncate_writer = False
        self.empty_writer = False
        self.execute_error = ""
        self.validate_fails = False
        self.ode_fails = False
        self.real_typst = False
        self.png_builder = _png_bytes
        self.before_execute = None

    async def fake_llm(self, prompt: str, system: str) -> str:
        if "## 报告题目" in prompt:
            self.writer_prompts.append(prompt)
            if self.truncate_writer:
                raise subject_error(ErrorCode.OUTPUT_TRUNCATED)
            if self.empty_writer:
                return ""
            title = prompt.split("## 报告题目", 1)[1].strip().splitlines()[0].strip()
            return self.bodies.get(title, self.default_body)
        self.chart_prompts.append(prompt)
        if self.chart_response is not None:
            return self.chart_response
        match = re.search(r"chart_[1-8]\.png", prompt)
        name = match.group(0) if match else "chart_1.png"
        return json.dumps({"code": f"# {name}\nplt.savefig({name!r})\n"})

    async def fake_execute(self, code: str, *, run, expected_png: str, policy=None):
        if self.before_execute is not None:
            await self.before_execute(expected_png)
        self.executed.append((expected_png, run.report_id))
        if self.execute_error:
            return ChartExecutionResult(
                exit_code=0, timed_out=False, error=self.execute_error, mode="chart", status=""
            )
        if code.startswith("# fail"):
            return ChartExecutionResult(
                exit_code=1, timed_out=False, error="", mode="chart", status="error"
            )
        target = Path(run.workdir) / expected_png
        target.write_bytes(self.png_builder())
        return ChartExecutionResult(
            exit_code=0,
            timed_out=False,
            error="",
            mode="chart",
            status="ok",
            artifact={"name": expected_png, "size": target.stat().st_size, "sha256": "0" * 64},
        )

    def fake_validate(self, run, expected_png: object, *, policy=None) -> dict:
        name = chart_target_basename(expected_png)
        data = (Path(run.workdir) / name).read_bytes()
        if self.validate_fails:
            raise subject_error(ErrorCode.CHART_FAILED)
        return {
            "path": name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "role": "chart",
        }

    async def fake_ode(self, run, expression: object, *, policy=None) -> dict:
        self.ode_calls.append(str(expression))
        if self.ode_fails:
            raise subject_error(ErrorCode.CHART_FAILED)
        return {"status": "passed", "max_abs_error": 1e-12, "points": 5}

    def fake_render(self, markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
        import pymupdf

        self.renders.append((markdown, tuple(chart_names)))
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "课程报告（测试 PDF）")
        for index, name in enumerate(chart_names):
            top = 100 + index * 140
            page.insert_image(
                pymupdf.Rect(72, top, 260, top + 110),
                filename=str(Path(out_path).parent / name),
            )
        document.save(str(out_path))
        document.close()
        return True

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(report_mod, "_llm", self.fake_llm)
        monkeypatch.setattr(report_mod.chart_executor, "execute_chart_code", self.fake_execute)
        monkeypatch.setattr(report_mod.chart_validation, "validate_chart_output", self.fake_validate)
        monkeypatch.setattr(report_mod.chart_validation, "check_ode_numeric", self.fake_ode)
        if not self.real_typst:
            monkeypatch.setattr(report_mod, "_render_report_pdf", self.fake_render)


@pytest.fixture
def subject(p1_runtime: Path):
    return helpers.make_subject(p1_runtime, "报告科")


def _reports_dir(subject) -> Path:
    return store.current_subject_paths().get_public_outputs_root() / "subjects" / subject.subject_id / "reports"


def _run(subject, **kwargs) -> dict:
    return asyncio.run(
        report_mod.generate_report(
            subject.subject_id,
            title=kwargs.pop("title", "课程报告"),
            requirements=kwargs.pop("requirements", "写一份课程报告"),
            **kwargs,
        )
    )


def _published_dirs(subject) -> list[Path]:
    directory = _reports_dir(subject)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir() and not path.is_symlink())


def _tree_hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# 占位符替换与完整发布
# ---------------------------------------------------------------------------
def test_zero_and_multi_space_placeholders_are_replaced(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:零空格}\n{CHART:   多空格   }\n"
    stub.install(monkeypatch)

    result = _run(subject)

    assert result["status"] == "completed"
    assert result["chart_count"] == 2
    assert "{CHART" not in result["markdown"]
    assert "![chart 1](chart_1.png)" in result["markdown"]
    assert "![chart 2](chart_2.png)" in result["markdown"]
    assert "零空格" in stub.chart_prompts[0]
    assert "多空格" in stub.chart_prompts[1]
    assert not result["url"].startswith("http")
    assert result["url"].startswith(f"/api/outputs/subjects/{subject.subject_id}/reports/")
    # path 是服务端正式产物的相对位置，不是宿主绝对路径。
    assert not Path(result["path"]).is_absolute()
    assert result["path"].startswith(f"subjects/{subject.subject_id}/reports/")

    public = _published_dirs(subject)
    assert len(public) == 1
    names = sorted(path.name for path in public[0].iterdir())
    assert names == ["chart_1.png", "chart_2.png", "metadata.json", "report.md", "report.pdf"]
    assert (public[0] / "report.md").read_text(encoding="utf-8") == result["markdown"]
    assert report_store.active_report_runs() == ()


def test_no_chart_report_is_legal(subject, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = Stub()
    stub.default_body = "# 纯正文报告\n\n没有任何图表。\n"
    stub.install(monkeypatch)

    result = _run(subject)

    assert result["chart_count"] == 0
    assert "![chart" not in result["markdown"]
    public = _published_dirs(subject)
    assert len(public) == 1
    assert (public[0] / "report.pdf").stat().st_size > 0


def test_published_markdown_is_discoverable_for_review(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 可核查报告\n\n正文。\n"
    stub.install(monkeypatch)

    result = _run(subject)
    manifest = report_store.resolve_report_for_review(subject.subject_id)

    assert manifest.report_id == result["report_id"]
    markdown_entry = manifest.file_for_role(report_store.ROLE_MARKDOWN)
    assert markdown_entry is not None
    assert (manifest.public_dir / markdown_entry.path).read_text(encoding="utf-8") == result["markdown"]


# ---------------------------------------------------------------------------
# 失败：整体失败、无 URL、旧报告不变
# ---------------------------------------------------------------------------
def test_any_declared_chart_failure_fails_the_whole_report(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:柱状图}\n"
    stub.chart_response = '{"code": [1, 2]}'
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _run(subject)

    assert info.value.code is ErrorCode.CHART_FAILED
    assert stub.executed == []  # 坏 JSON 从未进入执行器
    assert stub.renders == []  # 更不可能编译
    assert _published_dirs(subject) == []
    assert report_store.active_report_runs() == ()
    run_dirs = [path for path in (subject.root / "_report_runs").iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    metadata = json.loads((run_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["files"] == []


def test_failed_run_never_touches_the_previous_completed_report(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 第一版\n\n旧报告。\n"
    stub.install(monkeypatch)
    first = _run(subject)
    first_dir = _reports_dir(subject) / first["report_id"]
    before = _tree_hashes(first_dir)

    stub.default_body = "# 第二版\n{CHART:图}\n"
    stub.chart_response = '{"code": [1, 2]}'
    with pytest.raises(SubjectOperationError) as info:
        _run(subject)

    assert info.value.code is ErrorCode.CHART_FAILED
    assert _tree_hashes(first_dir) == before
    assert not (_reports_dir(subject) / "chart_2.png").exists()
    # 旧 completed 仍是 latest，且仍然可读。
    manifest = report_store.resolve_report_for_review(subject.subject_id)
    assert manifest.report_id == first["report_id"]


def test_empty_or_truncated_body_is_not_compiled(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.install(monkeypatch)
    from deeptutor.services.llm.exceptions import LLMEmptyResponseError

    stub.empty_writer = True
    with pytest.raises(LLMEmptyResponseError):
        _run(subject)
    assert stub.renders == []
    assert _published_dirs(subject) == []

    stub.empty_writer = False
    stub.truncate_writer = True
    with pytest.raises(SubjectOperationError) as truncated:
        _run(subject)
    assert truncated.value.code is ErrorCode.OUTPUT_TRUNCATED
    assert stub.renders == []
    assert _published_dirs(subject) == []


def test_a_forged_out_dir_is_rejected_before_any_run(subject, tmp_path: Path) -> None:
    with pytest.raises(SubjectOperationError) as info:
        _run(subject, out_dir=tmp_path / "evil")
    assert info.value.code is ErrorCode.INVALID_INPUT
    assert not (subject.root / "_report_runs").exists()


def test_three_failed_attempts_end_in_chart_failed(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:图}\n"
    stub.validate_fails = True
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _run(subject)

    assert info.value.code is ErrorCode.CHART_FAILED
    assert len(stub.executed) == 3  # 每次重试都重新执行，绝不复用上一张 PNG
    assert [name for name, _ in stub.executed] == ["chart_1.png"] * 3
    assert _published_dirs(subject) == []


def test_sandbox_unavailable_is_reported_without_retry_or_host_fallback(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:图}\n"
    stub.execute_error = "sandbox_unavailable"
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _run(subject)

    assert info.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert len(stub.executed) == 1
    assert _published_dirs(subject) == []
    source = Path(report_mod.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert not hasattr(report_mod, "_run_chart_code")
    assert not hasattr(report_mod, "_chart_ode_matches")


# ---------------------------------------------------------------------------
# ODE 门
# ---------------------------------------------------------------------------
def test_ode_numeric_check_runs_after_chart_validation(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:方向场}\n"
    stub.install(monkeypatch)

    result = _run(subject, ode_rhs="x**2 - y")

    assert stub.ode_calls == ["x**2 - y"]
    assert result["verification_status"] == "passed"
    assert len(stub.executed) == 1
    assert stub.renders and "x**2 - y" not in stub.renders[0][0]


def test_ode_failure_fails_the_report(subject, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:方向场}\n"
    stub.ode_fails = True
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _run(subject, ode_rhs="x**2 - y")

    assert info.value.code is ErrorCode.CHART_FAILED
    assert len(stub.executed) == 3
    assert stub.renders == []
    assert _published_dirs(subject) == []


# ---------------------------------------------------------------------------
# 图片引用白名单
# ---------------------------------------------------------------------------
FORBIDDEN_IMAGE_LINES = [
    "![x](https://evil.example/x.png)",
    "![x](../outside.png)",
    "![x](/etc/passwd)",
    '![x]("chart_1.png")',
    "![x](chart_1.png \"title\")",
    "![x](chart_9.png)",
    "![x](chart_2.png)",  # 本 run 未验证的图
    "![x][ref]",
    '<img src="chart_1.png">',
    "前缀 ![x](chart_1.png) 后缀",
]


@pytest.mark.parametrize("line", FORBIDDEN_IMAGE_LINES)
def test_untrusted_image_references_are_rejected_before_typst(
    subject, monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    stub = Stub()
    stub.default_body = f"# 报告\n{{CHART:图}}\n{line}\n"
    stub.install(monkeypatch)

    with pytest.raises(SubjectOperationError) as info:
        _run(subject)

    assert info.value.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert len(stub.executed) == 1  # 图本身执行成功，拒绝发生在渲染前
    assert stub.renders == []
    assert _published_dirs(subject) == []


def test_reference_to_a_verified_chart_is_allowed(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:图}\n![again](chart_1.png)\n"
    stub.install(monkeypatch)

    result = _run(subject)

    assert result["chart_count"] == 1
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# 并发与真实 Typst
# ---------------------------------------------------------------------------
def test_two_concurrent_runs_are_independent(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.bodies = {
        "并发一": "# 报告一\n{CHART:图}\n\n正文一。\n",
        "并发二": "# 报告二\n{CHART:图}\n\n正文二。\n",
    }
    barrier = asyncio.Event()
    entered: list[str] = []

    async def before_execute(expected_png: str) -> None:
        entered.append(expected_png)
        if len(entered) == 2:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=5)

    stub.before_execute = before_execute
    stub.install(monkeypatch)

    async def scenario() -> tuple[dict, dict]:
        return await asyncio.gather(
            report_mod.generate_report(subject.subject_id, title="并发一", requirements="一"),
            report_mod.generate_report(subject.subject_id, title="并发二", requirements="二"),
        )

    first, second = asyncio.run(scenario())

    assert first["report_id"] != second["report_id"]
    assert first["url"] != second["url"]
    assert len(entered) == 2  # 两个独立 run 在同一个 event loop 上真实重叠
    assert (Path(first["path"]).name, Path(second["path"]).name) == ("report.pdf", "report.pdf")
    for result in (first, second):
        public = store.current_subject_paths().get_public_outputs_root() / result["path"]
        assert public.is_file()
    assert report_store.active_report_runs() == ()


def test_real_typst_chinese_with_image_is_openable(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image, ImageDraw, ImageFont
    import pymupdf

    font = Path(report_mod.__file__).resolve().parents[3] / "tools" / "fonts" / "msyh.ttc"

    def chinese_png() -> bytes:
        from io import BytesIO

        image = Image.new("RGB", (480, 320), (245, 247, 252))
        draw = ImageDraw.Draw(image)
        draw.text((60, 130), "中文图表：期末成绩分布", font=ImageFont.truetype(str(font), 26), fill=(20, 60, 120))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    stub = Stub()
    stub.default_body = "# 课程报告\n\n## 成绩分析\n\n下图为中文图表。\n{CHART:成绩分布柱状图}\n"
    stub.png_builder = chinese_png
    stub.real_typst = True
    stub.install(monkeypatch)

    result = _run(subject)

    public_pdf = store.current_subject_paths().get_public_outputs_root() / result["path"]
    assert public_pdf.is_file() and public_pdf.stat().st_size > 0
    with pymupdf.open(str(public_pdf)) as document:
        assert document.page_count >= 1
        images = sum(len(page.get_images(full=True)) for page in document)
        text = "".join(page.get_text() for page in document)
    assert images >= 1, "真实 Typst PDF 必须嵌入已验证图表"
    assert "课程报告" in text
    assert "成绩分析" in text
