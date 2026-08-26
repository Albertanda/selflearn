"""Report tool (M7+) — generate or review course reports inside chat.

Invoked when the learner asks for a report (optionally with the teacher's
assignment file). ``action=create`` builds a chart-bearing report PDF;
``action=review`` re-reads the full report text, has the model re-check
math/content against the requirements, and renders a revised PDF.

The subject id is server-injected via ``_subject_id`` (never accepted from
the model).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """你是一名严谨的课程助教，正在对一份课程报告做**核查与修复**。请逐条核对：
1. 数学正确性（公式、解的推导、结论是否站得住；能代入验证的必须验证）；
2. 图表与文字是否对应（图的内容是否支持对应章节的说法）；
3. 结构完整性与题目要求覆盖度。

输出修复后的完整报告（Markdown，结构与要求同原报告；数学用 Unicode 表达；不引入新图，保留原图引用行 `![chart N](chart_N.png)`）。直接输出修复版全文，开头加一行 `<!-- reviewed -->`。
"""


class ReportTool(BaseTool):
    """Generate or review a course report (create | review)."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_report",
            description=(
                "课程报告助手：用户要求【生成或核查课程报告】时必须调用本工具（不要自己用文字替代，"
                "本工具产出排版好的 PDF 并给出下载链接）。"
                "action=create：传入 title 与 requirements（可附教师题目文件路径 source_file、"
                "微分方程 ode_rhs 如 'x**2 - y'）。"
                "action=review：核查最近一次生成的报告并用 LLM 修复后重新渲染 PDF——"
                "**无需也不允许传 report_path**（工具自动取最近报告），不要自行查找或读取报告文件。"
            ),
            parameters=[
                ToolParameter(name="action", type="string", enum=["create", "review"], required=True),
                ToolParameter(name="title", type="string", description="报告题目", required=False),
                ToolParameter(name="requirements", type="string", description="分条列出的撰写要求", required=False),
                ToolParameter(name="ode_rhs", type="string", description="微分方程 f(x,y)（可选，图表数值校验基准，如 x**2 - y）", required=False),
                ToolParameter(name="source_file", type="string", description="教师发出的题目文件路径（附件 manifest id 或本地路径）", required=False),
                ToolParameter(name="report_path", type="string", description="要核查的报告路径（action=review）", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        subject_id = str(kwargs.get("_subject_id", "") or "").strip()
        action = str(kwargs.get("action") or "create").lower()
        if not subject_id:
            return ToolResult(content="此功能需要先选择一个科目（聊天工具栏的科目选择器）。", success=False)

        # Deferred imports: builtin -> report_tool -> pdf.report -> subjects
        # -> path_service -> runtime.registry -> builtin would otherwise cycle.
        from deeptutor.services.path_service import get_path_service
        from deeptutor.services.pdf import report as report_mod

        outputs_root = get_path_service().get_public_outputs_root()
        out_dir = outputs_root / "subjects" / subject_id / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)

        if action == "review":
            report_path = str(kwargs.get("report_path") or "").strip()
            if report_path in ("latest", "recent", "最近", "最新", "last"):
                report_path = ""
            if not report_path:
                # No path given: review the most recent report for this subject.
                candidates = sorted(out_dir.glob("report-*.md"))
                if not candidates:
                    return ToolResult(content="该科目还没有可核查的报告，请先创建一份。", success=False)
                md_path = candidates[-1]
            else:
                md_path = Path(report_path).with_suffix(".md")
            if not md_path.exists():
                # Accept the .pdf path: look for the sibling .md.
                return ToolResult(
                    content=f"未找到报告正文 {md_path}；请确认路径来自本工具生成结果。", success=False
                )
            markdown = md_path.read_text(encoding="utf-8")
            markdown = await report_mod._llm(
                REVIEW_PROMPT + "\n\n## 原报告\n" + markdown,
                "你是课程报告核查助手。",
            )
            pdf_path = await report_mod._render_reviewed(markdown, out_dir, md_path)
            if not pdf_path:
                return ToolResult(content="报告核查后重新渲染失败，请重试。", success=False)
            return ToolResult(
                content=(
                    f"已核查并修复报告，可下载：`{pdf_path.name}`（url: "
                    f"/api/outputs/subjects/{subject_id}/reports/{pdf_path.name}）"
                )
            )

        title = str(kwargs.get("title") or "").strip()
        if not title:
            return ToolResult(content="请提供报告题目（title）。", success=False)
        requirements = str(kwargs.get("requirements") or "").strip()
        ode_rhs = str(kwargs.get("ode_rhs") or "").strip()
        # The teacher's assignment file may ride as an attachment content ref.
        source_file = str(kwargs.get("source_file") or "").strip()
        if source_file and requirements:
            requirements = f"{requirements}\n（教师题目文件：{source_file}）"

        result = await report_mod.generate_report(
            subject_id, title=title, requirements=requirements, out_dir=out_dir, ode_rhs=ode_rhs
        )
        if not result["pdf_ok"]:
            return ToolResult(content="报告渲染失败，请重试。", success=False)
        pdf_path = Path(result["pdf_path"])
        # Persist the markdown next to the PDF so `review` can re-read it.
        md_name = pdf_path.with_suffix(".md").name
        md_path = out_dir / md_name
        md_path.write_text(result["markdown"], encoding="utf-8")
        ts = int(time.time())
        return ToolResult(
            content=(
                f"报告《{title}》已生成（{result['chart_count']} 张图表，{result['markdown_tokens']} tokens）。"
                f"\n\n下载：`/api/outputs/subjects/{subject_id}/reports/{pdf_path.name}`"
                f"\n\n如需我核查修改，请回复：核查这份报告（或指出具体问题）。"
                f"\n\n（报告路径：{md_path}）"
            )
        )
