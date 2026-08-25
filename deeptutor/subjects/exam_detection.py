"""Exam-point detection (M4) — find teacher-stressed examinable content
in lecture transcripts (e.g. ASR output).

Pipeline: transcript → LLM detection (signal-based) → candidate points
(level explicit/emphasis, evidence quote) → user confirmation → store.

``DETECT_PROMPT_V1`` is the tuned prompt; bump the version when the
detection policy changes so test records stay comparable.
"""

from __future__ import annotations

import json
import re

from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.llm.factory import complete

DETECT_PROMPT_VERSION = "v3"

DETECT_PROMPT_V3 = """你是一名严谨的课程助教，任务是从大学课堂讲课转写文本中识别【教师明确暗示会考】的内容。

## 识别信号（按强度分级）
- explicit（明示）：教师明确说【今年/本学期】考试会考。信号词如："这是重中之重""期末肯定要考""必考""一定会考""每年都考""考试重点""重点掌握""这里会考""必出""大题必考"等。注意："每年都考/每年都出题"属于明确的考试暗示，可判 explicit；但"去年考过/往年考过"只是历史经验，判 emphasis。
- emphasis（强调）：教师强烈提示重要性但没有直说【今年会考】。信号词如："这个很重要""特别重要""一定要重视""务必掌握""最关键""最容易错""经常考""往年考过""去年考过""基础中的基础""年年都要用到""大家注意""重点""核心""多练几遍"等。

## 输出要求
只输出 JSON（不要任何其他文字）：
{"points": [{"content": "考点内容的完整描述（含具体知识点/公式/结论）", "level": "explicit", "evidence": "原文中的直接引文（教师原话，越短越好）", "kp": "所属知识点名称（如：一阶线性方程、洛必达法则）"}]}

## 规则
1. 只提取有明确依据的考点，宁缺毋滥；闲聊、过渡句、题外话不要提取。
2. explicit 必须真的有"必考/肯定考/每年都考/重中之重"这类【指向今年考试】的字面信号；只有"重要/注意/重视"而没有考试指向的归为 emphasis；"去年考过/往年考过"归为 emphasis。
3. 教师用强语气强调（"很重要+一定要重视""务必掌握""基础中的基础""几乎年年都要用到"）即使没有"考"字，也要提取为 emphasis——知识点主题本身可以作为考点内容。
4. 教师明确说"不用重点看""不会考""了解即可""看看书就行"的内容，即使前面有"重要"字样，也【不要】提取（负向信号优先）。
5. evidence 必须是原文引文，不得改写。
6. 同一知识点被多次强调时合并为一条，evidence 取最强的那句。
7. 找不到任何考点时输出 {"points": []}。

## 示例
输入："这个内容很重要，大家一定要重视起来，几乎年年都要用到。"
输出：{"points": [{"content": "常微分方程组的解法（整体重要性）", "level": "emphasis", "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到", "kp": "常微分方程组"}]}

输入："去年期末考试最后一道大题就考的消元法，大家今年注意。"
输出：{"points": [{"content": "消元法解常微分方程组", "level": "emphasis", "evidence": "去年期末考试，最后一道大题就是考的消元法", "kp": "消元法"}]}

输入："这个不难，不用重点看，大家了解一下就行。"
输出：{"points": []}
"""


async def detect_points(
    transcript: str,
    *,
    term: str = "",
    source: str = "lecture",
    language: str = "zh",
    prompt_version: str = DETECT_PROMPT_VERSION,
) -> dict:
    """Run detection and return ``{version, points, raw}`` (unconfirmed)."""
    prompt = DETECT_PROMPT_V3
    cfg = get_llm_config()
    try:
        raw = await complete(
            prompt=prompt + "\n\n## 课堂转写文本\n" + transcript,
            system_prompt=(
                "你是课堂考点提取助手，只输出 JSON。"
                if language.startswith("zh")
                else "You extract exam points from lectures. JSON only."
            ),
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
    except Exception as exc:  # noqa: BLE001
        return {"version": prompt_version, "points": [], "raw": "", "error": str(exc)}

    points = _parse_points(raw)
    for p in points:
        p.setdefault("term", term)
        p.setdefault("source", source)
        p.setdefault("anchor", "")
    return {"version": prompt_version, "points": points, "raw": raw}


def _parse_points(raw: str) -> list[dict]:
    """Robustly pull ``{"points": [...]}`` out of an LLM response."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        # Trailing commas / prose tolerance.
        cleaned = re.sub(r",\s*([}\]])", r"\1", m.group(0))
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        return []
    out = []
    for p in points:
        if not isinstance(p, dict):
            continue
        content = str(p.get("content") or "").strip()
        if not content:
            continue
        level = str(p.get("level") or "emphasis").lower()
        if level not in ("explicit", "emphasis", "inferred"):
            level = "emphasis"
        out.append(
            {
                "content": content,
                "level": level,
                "evidence": str(p.get("evidence") or "").strip(),
                "kp": str(p.get("kp") or "").strip(),
            }
        )
    return out
