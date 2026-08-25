"""Report writing (M7) — generate a chart-bearing course report and
export it as PDF.

Pipeline: LLM writes Markdown with ``{{CHART: description}}`` placeholders
-> LLM emits matplotlib code per chart -> server executes (venv python,
timeout-bounded) -> PNGs -> Markdown+images rendered via Typst -> PDF.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.llm.factory import complete
from deeptutor.services.pdf.review_guide import _md_to_typst, _TYST_DOC, estimate_tokens

REPORT_PROMPT = """你是一名大学助教，根据题目要求撰写一份课程报告（中文）。

## 报告题目
{title}

## 题目要求
{requirements}

## 写作要求
1. 结构：# 标题 开头，然后是 ## 引言、## 各分析章节（按题目要求组织）、## 结论。
2. 需要用图表达的地方插入占位符：{{CHART: 图表描述}}——描述里写清楚要画什么（函数/数据、坐标轴含义、x 范围）。每张图占位符独占一行。
3. 数学公式用 Unicode 文本（如 y′ = x² − y、e^(−x)），不要用 LaTeX 命令。
4. 只使用 Markdown 子集：#、##、-、**加粗**；不要表格、代码块、链接。
5. 正文 800-1200 字（不含图），内容准确、结构完整，直接基于题目要求。
"""

CHART_CODE_PROMPT = """为下面这张图生成 matplotlib Python 代码。

## 图表需求
{description}

## 代码要求
1. 完整可运行的脚本：import numpy 和 matplotlib.pyplot as plt。
2. 中文字体设置：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']；plt.rcParams['axes.unicode_minus'] = False。
3. 图内文字可用中文或英文（数学变量用 x, y, t）。
4. 保存：plt.savefig('{out_path}', dpi=150, bbox_inches='tight')；不要 plt.show()。
5. 只输出 JSON：{{"code": "..."}}（code 为完整脚本字符串，转义换行）。
"""


async def _llm(prompt: str, system: str) -> str:
    cfg = get_llm_config()
    return await complete(
        prompt=prompt,
        system_prompt=system,
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
    )


def _extract_json(raw: str) -> dict:
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _run_chart_code(code: str, workdir: Path) -> bool:
    """Execute LLM-generated matplotlib code in a subprocess."""
    script = workdir / "_chart.py"
    script.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(workdir),
            capture_output=True,
            timeout=60,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _render_report_pdf(markdown: str, charts: list[Path], out_path: Path, typst_bin: Path) -> bool:
    """Render report markdown (with chart image lines) to PDF via Typst."""
    lines = []
    for line in markdown.splitlines():
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
        if m:
            lines.append(f"#image(\"{m.group(1)}\", width: 85%)")
            lines.append("")
            continue
        lines.append(line)
    body = _md_to_typst("\n".join(lines))
    src = _TYST_DOC.format(body=body)
    tmp = out_path.with_suffix(".typ")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run(
            [str(typst_bin), "compile", str(tmp), str(out_path)],
            capture_output=True,
            timeout=120,
        )
        return proc.returncode == 0 and out_path.exists()
    except Exception:
        return False


async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path,
) -> dict:
    """Generate a report with charts and render it to PDF.

    Returns ``{title, markdown, markdown_tokens, chart_count, pdf_path}``.
    """
    from deeptutor.services.path_service import get_path_service

    markdown = (await _llm(REPORT_PROMPT.format(title=title, requirements=requirements),
                           "你是课程报告撰写助手。")).strip()

    chart_specs = re.findall(r"\{CHART:\s*([^}]+)\}", markdown)
    chart_paths: list[Path] = []
    for i, spec in enumerate(chart_specs):
        png = out_dir / f"chart_{i + 1}.png"
        raw = await _llm(
            CHART_CODE_PROMPT.format(description=spec.strip(), out_path=png.name),
            "你生成 matplotlib 代码，只输出 JSON。",
        )
        data = _extract_json(raw)
        code = data.get("code", "")
        if code and _run_chart_code(code, out_dir) and png.exists():
            chart_paths.append(png)
        # Replace the placeholder with an image line (or drop on failure).
        markdown = markdown.replace(
            "{CHART: " + spec + "}", f"![chart {i + 1}]({png.name})", 1
        )

    typst_bin = Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst"
    ts = int(time.time())
    pdf_path = out_dir / f"report-{ts}.pdf"
    ok = _render_report_pdf(markdown, chart_paths, pdf_path, typst_bin)
    return {
        "title": title,
        "markdown": markdown,
        "markdown_tokens": estimate_tokens(markdown),
        "chart_count": len(chart_paths),
        "pdf_ok": ok,
        "pdf_path": str(pdf_path),
    }
