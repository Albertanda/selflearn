"""Report tool (M7+/P1-36) — generate or review course reports inside chat.

Invoked when the learner asks for a report (optionally with the teacher's
assignment file).  Both actions go through the same server-owned pipeline in
:mod:`deeptutor.services.pdf.report`; this tool never picks a directory, never
writes Markdown itself and never reads an arbitrary host path.

The subject id and the attached-source index are server-injected (``_subject_id``
/ ``_source_index``); neither can be contributed by the model.
"""

from __future__ import annotations

import logging
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)

_LATEST_ALIASES = frozenset({"latest", "recent", "最近", "最新", "last"})


def _attached_source_text(index: object, source_id: str) -> str:
    """Read one attached source **by id** from the server-injected mapping.

    ``source_id`` is a key in ``context.metadata['source_index']`` (the attached
    full text), never a host path.  Unknown ids and malformed maps are
    ``invalid_input`` before any file or provider access.
    """
    from deeptutor.subjects import json_store

    if not isinstance(index, dict):
        raise json_store.invalid_input("source_file 必须是当前回合已附件的 source_id")
    value = index.get(source_id)
    if not isinstance(value, str) or not value.strip():
        raise json_store.invalid_input("source_file 必须是当前回合已附件的 source_id")
    return value


class ReportTool(BaseTool):
    """Generate or review a course report (create | review)."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_report",
            description=(
                "课程报告助手：用户要求【生成或核查课程报告】时必须调用本工具（不要自己用文字替代，"
                "本工具产出排版好的 PDF 并给出下载链接）。"
                "action=create：传入 title 与 requirements；source_file 只接受当前回合已附件的 "
                "source_id（由服务端提供，不是文件路径），ode_rhs 如 'x**2 - y'。"
                "action=review：默认核查本科目最近一份报告；可传 report_id，或传同科已知旧报告的 "
                "report_path（.md/.pdf）。工具拒绝任意宿主路径与跨科目路径。"
            ),
            parameters=[
                ToolParameter(name="action", type="string", enum=["create", "review"], required=True),
                ToolParameter(name="title", type="string", description="报告题目", required=False),
                ToolParameter(name="requirements", type="string", description="分条列出的撰写要求（review 时为额外核查要求）", required=False),
                ToolParameter(name="ode_rhs", type="string", description="微分方程 f(x,y)（可选，图表数值校验基准，如 x**2 - y）", required=False),
                ToolParameter(name="source_file", type="string", description="当前回合附件的 source_id（不是本地路径）", required=False),
                ToolParameter(name="report_id", type="string", description="要核查的报告 id（action=review，可选）", required=False),
                ToolParameter(name="report_path", type="string", description="同科已知旧报告的 .md/.pdf 名称（action=review，可选）", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401 - tool protocol
        from deeptutor.services.pdf import report as report_mod
        from deeptutor.subjects.errors import map_subject_exception, to_tool_result

        subject_id = str(kwargs.get("_subject_id", "") or "").strip()
        if not subject_id:
            return ToolResult(content="此功能需要先选择一个科目（聊天工具栏的科目选择器）。", success=False)

        action = str(kwargs.get("action") or "create").strip().lower()
        subject_context = str(kwargs.get("_report_ctx_hint") or "").strip()

        try:
            requirements = str(kwargs.get("requirements") or "").strip()
            source_id = str(kwargs.get("source_file") or "").strip()
            if source_id:
                requirements = (
                    f"{requirements}\n\n（教师题目文件内容，来自附件 {source_id}：\n"
                    f"{_attached_source_text(kwargs.get('_source_index'), source_id)}\n）"
                ).strip()
            if action == "review":
                report_id = str(kwargs.get("report_id") or "").strip()
                legacy_path = str(kwargs.get("report_path") or "").strip()
                if report_id.lower() in _LATEST_ALIASES:
                    report_id = ""
                if legacy_path.lower() in _LATEST_ALIASES:
                    legacy_path = ""
                result = await report_mod.review_report(
                    subject_id,
                    report_id=report_id or None,
                    legacy_path=legacy_path or None,
                    instructions=requirements,
                    subject_context=subject_context,
                )
                return ToolResult(
                    content=(
                        f"已核查并修复报告，可下载：`{result['url']}`"
                        f"\n\n（报告 id：{result['report_id']}，{result['chart_count']} 张保留图）"
                        f"\n\n如需再次核查，请回复：核查这份报告。"
                    ),
                    metadata={
                        "report_id": result["report_id"],
                        "url": result["url"],
                        "status": result["status"],
                        "chart_count": result["chart_count"],
                        **{key: result[key] for key in ("path", "markdown_tokens", "verification_status")
                           if key in result},
                    },
                )

            if action != "create":
                from deeptutor.subjects import json_store

                raise json_store.invalid_input("action 必须是 create 或 review")

            title = str(kwargs.get("title") or "").strip()
            if not title:
                from deeptutor.subjects import json_store

                raise json_store.invalid_input("请提供报告题目（title）")
            ode_rhs = str(kwargs.get("ode_rhs") or "").strip()

            result = await report_mod.generate_report(
                subject_id,
                title=title,
                requirements=requirements,
                ode_rhs=ode_rhs,
                subject_context=subject_context,
            )
            return ToolResult(
                content=(
                    f"报告《{title}》已生成（{result['chart_count']} 张图表，"
                    f"{result['markdown_tokens']} tokens）。"
                    f"\n\n下载：`{result['url']}`"
                    f"\n\n如需我核查修改，请回复：核查这份报告（或指出具体问题）。"
                ),
                metadata={
                    "report_id": result["report_id"],
                    "url": result["url"],
                    "status": result["status"],
                    "chart_count": result["chart_count"],
                    **{key: result[key] for key in ("path", "markdown_tokens", "verification_status")
                       if key in result},
                },
            )
        except Exception as exc:  # noqa: BLE001 - C02 tool boundary: never leak
            error = map_subject_exception(exc)
            return ToolResult(
                content=error.message,
                success=False,
                metadata=to_tool_result(error)["metadata"],
            )
