"""P1-37 行为测试：报告/复习包的 API 与工具一致失败响应。

证明目标：

* 真实 ``LLMReasoningBudgetExhausted``、非空截断、图表/渲染失败在 HTTP 与 Tool
  两侧都是同名 C02 失败，不拼 raw 异常文本；
* 成功响应是 ``ReportResponse`` 形状，URL 对应当前用户同科目真实文件；
* API 创建的报告能被 Tool 的 latest review 发现并生成新 revision；
* 无学情数据时复习提示仍是合法正文，真实 Typst PDF 可打开；DOCX 通过真实
  OOXML/docx parser 验证；
* 渲染失败没有 URL、没有半文件；非法 format/title 是 400 invalid_input。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from deeptutor.services.llm.exceptions import LLMReasoningBudgetExhausted
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import review_guide
from deeptutor.services.pdf.chart_executor import ChartExecutionResult
from deeptutor.services.pdf.report_inputs import chart_target_basename
from deeptutor.subjects import store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error
from deeptutor.subjects.generation import SubjectOutputTruncated
from deeptutor.tools.report_tool import ReportTool
from tests.phase1 import helpers

REPORT_MARKER = "p1-37-BUDGET-MARKER-7f3c"
ROUTE = helpers.ROUTE_PREFIX


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (80, 60), (20, 100, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


class PipelineStub:
    """Provider/executor stub with real PNG/PDF bytes for both entry points."""

    def __init__(self) -> None:
        self.writer_body = "# 课程报告\n\n正文。\n"
        self.review_body = "# 修复版\n\n正文。\n"
        self.chart_body = '{"code": "import matplotlib.pyplot as plt\\nplt.savefig(\'chart_1.png\')\\n"}'
        self.calls: list[str] = []

    async def fake_llm(self, prompt: str, system: str) -> str:
        if "## 原报告" in prompt:
            self.calls.append("review")
            return self.review_body
        if "## 报告题目" in prompt:
            self.calls.append("writer")
            return self.writer_body
        self.calls.append("chart")
        return self.chart_body

    async def fake_execute(self, code: str, *, run, expected_png: str, policy=None):
        target = Path(run.workdir) / expected_png
        target.write_bytes(_png_bytes())
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
        return {
            "path": name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "role": "chart",
        }

    def fake_render(self, markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
        import pymupdf

        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "report")
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
        monkeypatch.setattr(report_mod.chart_executor, "execute_chart_code", self.fake_execute)
        monkeypatch.setattr(report_mod.chart_validation, "validate_chart_output", self.fake_validate)
        monkeypatch.setattr(report_mod, "_render_report_pdf", self.fake_render)


def _error(response, code: str, status: int) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert body["detail"] == body["error"]["message"]
    return body


def _public_root() -> Path:
    return store.current_subject_paths().get_public_outputs_root()


def test_review_pack_rejects_an_image_renamed_as_pdf(
    p1_subjects, p1_route_client, monkeypatch
) -> None:
    subject = p1_subjects["科目A"]

    def disguised(markdown, path, typst_bin=None):
        path.write_bytes(_png_bytes())
        return True

    monkeypatch.setattr(review_guide, "render_pdf", disguised)
    response = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"})
    _error(response, "render_failed", 502)
    assert "url" not in response.json()
    assert not list((_public_root() / "subjects" / subject.subject_id).glob("review-guide-*"))


# ---------------------------------------------------------------------------
# 成功路径与真实 URL
# ---------------------------------------------------------------------------
def test_report_route_returns_report_response_and_a_real_file(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    stub = PipelineStub()
    stub.writer_body = "# 课程报告\n\n{CHART:图}\n"
    stub.install(monkeypatch)

    response = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/report",
        data={"title": "课程报告", "requirements": "要求"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["report_id"] and len(body["report_id"]) == 32
    assert body["chart_count"] == 1
    assert body["markdown_tokens"] > 0
    assert body["url"].startswith(f"/api/outputs/subjects/{subject.subject_id}/reports/")
    assert not Path(body["path"]).is_absolute()
    assert body["verification_status"] == "not_requested"
    assert (_public_root() / body["path"]).is_file()
    assert body["url"].endswith("/report.pdf")


def test_api_created_report_is_discoverable_by_tool_latest(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    stub = PipelineStub()
    stub.install(monkeypatch)
    created = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/report", data={"title": "报告", "requirements": "要求"}
    )
    assert created.status_code == 200
    report_id = created.json()["report_id"]

    result = asyncio.run(
        ReportTool().execute(_subject_id=subject.subject_id, action="review")
    )

    assert result.success is True
    assert result.metadata["report_id"] != report_id
    assert result.metadata["url"].startswith(f"/api/outputs/subjects/{subject.subject_id}/reports/")
    assert "/tmp" not in result.content and str(_public_root()) not in result.content


# ---------------------------------------------------------------------------
# 真实预算/截断：HTTP 与 Tool 同名失败
# ---------------------------------------------------------------------------
def test_review_pack_budget_error_is_named_on_http(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise LLMReasoningBudgetExhausted(f"{REPORT_MARKER} raw provider text")

    monkeypatch.setattr(review_guide, "generate_guide_markdown", failing)

    response = p1_route_client.post(f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"})

    body = _error(response, "reasoning_budget_exhausted", 502)
    assert REPORT_MARKER not in response.text
    assert "raw provider text" not in response.text
    assert "url" not in body


def test_report_route_budget_error_is_named_and_has_no_url(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise LLMReasoningBudgetExhausted(f"{REPORT_MARKER} raw provider text")

    monkeypatch.setattr(report_mod, "generate_report", failing)

    response = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/report", data={"title": "报告", "requirements": "要求"}
    )

    body = _error(response, "reasoning_budget_exhausted", 502)
    assert REPORT_MARKER not in response.text
    assert "url" not in body


def test_tool_uses_the_same_budget_error_code(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise LLMReasoningBudgetExhausted(f"{REPORT_MARKER} raw provider text")

    monkeypatch.setattr(report_mod, "generate_report", failing)

    result = asyncio.run(
        ReportTool().execute(_subject_id=subject.subject_id, action="create", title="报告")
    )

    assert result.success is False
    assert result.metadata["error"]["code"] == "reasoning_budget_exhausted"
    assert REPORT_MARKER not in result.content
    assert "url" not in result.metadata


@pytest.mark.parametrize("endpoint", ["report", "review-pack"])
def test_partial_truncation_is_named_and_never_has_a_url(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    subject = p1_subjects["科目A"]

    async def truncated(*args, **kwargs):
        raise SubjectOutputTruncated(diagnostics={"content_chars": 12})

    if endpoint == "review-pack":
        monkeypatch.setattr(review_guide, "generate_guide_markdown", truncated)
        response = p1_route_client.post(
            f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"}
        )
    else:
        monkeypatch.setattr(report_mod, "generate_report", truncated)
        response = p1_route_client.post(
            f"{ROUTE}/{subject.subject_id}/report", data={"title": "报告"}
        )

    body = _error(response, "output_truncated", 502)
    assert "url" not in body


# ---------------------------------------------------------------------------
# 复习包：真实渲染、无学情、DOCX、失败无半文件
# ---------------------------------------------------------------------------
def test_review_pack_without_learning_data_is_a_real_pdf(
    p1_subjects, p1_route_client
) -> None:
    import pymupdf

    subject = p1_subjects["科目A"]
    response = p1_route_client.post(f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "pdf"
    assert body["markdown_tokens"] > 0
    assert body["status"] == "completed"
    path = _public_root() / body["path"]
    assert path.is_file()
    with pymupdf.open(str(path)) as document:
        assert document.page_count >= 1
        text = "".join(page.get_text() for page in document)
    assert "期末复习指南" in text


def test_review_pack_docx_is_a_real_ooxml_package(
    p1_subjects, p1_route_client
) -> None:
    from docx import Document

    subject = p1_subjects["科目A"]
    response = p1_route_client.post(f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "docx"})

    assert response.status_code == 200, response.text
    path = _public_root() / response.json()["path"]
    assert path.is_file()
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    assert "[Content_Types].xml" in names
    assert "word/document.xml" in names
    text = "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    assert "期末复习指南" in text


def test_review_pack_render_failure_has_no_url_and_no_half_file(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    monkeypatch.setattr(review_guide, "render_pdf", lambda markdown, path, typst_bin=None: False)
    public_dir = _public_root() / "subjects" / subject.subject_id
    before = sorted(path.name for path in public_dir.iterdir()) if public_dir.is_dir() else []

    response = p1_route_client.post(f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "pdf"})

    body = _error(response, "render_failed", 502)
    assert "url" not in body
    after = sorted(path.name for path in public_dir.iterdir()) if public_dir.is_dir() else []
    assert after == before


def test_tool_review_render_failure_is_not_success(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise subject_error(ErrorCode.RENDER_FAILED)

    monkeypatch.setattr(report_mod, "review_report", failing)

    result = asyncio.run(
        ReportTool().execute(_subject_id=subject.subject_id, action="review")
    )

    assert result.success is False
    assert result.metadata["error"]["code"] == "render_failed"
    assert "url" not in result.metadata


# ---------------------------------------------------------------------------
# 输入边界
# ---------------------------------------------------------------------------
def test_invalid_format_and_empty_title_are_invalid_input(
    p1_subjects, p1_route_client
) -> None:
    subject = p1_subjects["科目A"]
    bad_format = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/review-pack", data={"format": "txt"}
    )
    _error(bad_format, "invalid_input", 400)

    empty_title = p1_route_client.post(
        f"{ROUTE}/{subject.subject_id}/report", data={"title": "   "}
    )
    _error(empty_title, "invalid_input", 400)
