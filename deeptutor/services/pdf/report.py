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
import logging

logger = logging.getLogger(__name__)

from deeptutor.services.pdf.review_guide import _md_to_typst, _TYST_DOC, estimate_tokens, typst_compile

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
6. 数学严谨性：凡是给出解析解、平衡点、稳定性等结论，必须代入原方程验证后再写；精确解写出来前先自查（例如 y' = x² − y 的通解是 y = x² − 2x + 2 + C·e^(−x)，代回可验证）；不要臆造公式或结论。
"""

CHART_CODE_PROMPT = """为下面这张图生成 matplotlib Python 代码。

## 微分方程（必须严格遵守，禁止修改）
本题微分方程为 y′ = f(x, y)，其中：
f(x, y) = {ode_rhs}
代码中必须定义：def f(x, y): return {ode_rhs}，不得使用其他任何方程！

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



def _chart_ode_matches(workdir: Path, ode_rhs: str) -> bool:
    """Verify the chart's f(x, y) against the declared ODE on test points."""
    check = f"""
import sys
sys.path.insert(0, {str(workdir)!r})
import _chart as _c
_declared = lambda x, y: {ode_rhs}
_pts = [(-2.5, 1.0), (0.0, 0.5), (1.7, -2.0), (2.2, 2.5), (-0.8, -3.0)]
_got = [_c.f(x, y) for x, y in _pts]
_exp = [_declared(x, y) for x, y in _pts]
_err = max(abs(a - b) for a, b in zip(_got, _exp))
print("ODE_CHECK_ERR", _err)
raise SystemExit(0 if _err < 1e-6 else 1)
"""
    script = workdir / "_ode_check.py"
    script.write_text(check, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(workdir),
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


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


_FONT_REGISTER = """import matplotlib.font_manager as _fm
for _f in {font_paths!r}:
    try:
        _fm.fontManager.addfont(_f)
    except Exception:
        pass
"""


def _run_chart_code(code: str, workdir: Path) -> bool:
    """Execute LLM-generated matplotlib code in a subprocess."""
    from deeptutor.services.pdf.review_guide import _FONT_DIR

    font_paths = [str(_FONT_DIR / n) for n in ("SimsunExtG.ttf", "msyh.ttc")]
    script = workdir / "_chart.py"
    script.write_text(
        _FONT_REGISTER.format(font_paths=font_paths) + code, encoding="utf-8"
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(workdir),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            (workdir / "_chart_err.txt").write_text(
                (proc.stderr or b"").decode(errors="replace")[:500], encoding="utf-8"
            )
        return proc.returncode == 0
    except Exception as exc:
        (workdir / "_chart_err.txt").write_text(str(exc)[:500], encoding="utf-8")
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
    return typst_compile(tmp, out_path, typst_bin)


async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path,
    ode_rhs: str = "",
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
        chart_ok = False
        for attempt in range(3):  # up to 2 retries on failed ODE self-check
            raw = await _llm(
                CHART_CODE_PROMPT.format(
                    description=spec.strip(), out_path=png.name, ode_rhs=ode_rhs or "x**2 - y"
                ),
                "你生成 matplotlib 代码，只输出 JSON。",
            )
            data = _extract_json(raw)
            code = data.get("code", "")
            if code and _run_chart_code(code, out_dir) and png.exists():
                if not ode_rhs or _chart_ode_matches(out_dir, ode_rhs):
                    chart_ok = True
                    break
                logger.warning("chart %d ODE mismatch (attempt %d)", i + 1, attempt + 1)
        ok = chart_ok
        if ok:
            chart_paths.append(png)
        else:
            err = (out_dir / "_chart_err.txt").read_text(encoding="utf-8")[:200] \
                if (out_dir / "_chart_err.txt").exists() else "no chart code"
            logger.warning("chart %d generation failed: %s", i + 1, err)
        # Replace the placeholder with an image line, or a plain-text note
        # when the chart could not be produced (never leave dangling refs).
        replacement = (
            f"![chart {i + 1}]({png.name})" if ok
            else f"**（图 {i + 1} 生成失败：{spec.strip()[:60]}）**"
        )
        markdown = markdown.replace("{CHART: " + spec + "}", replacement, 1)

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
