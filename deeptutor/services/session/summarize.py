"""Conversation summarization (M5+) — compress early history into a
durable summary instead of dropping it, and extract learner facts.

Policy:
  * history within the per-turn budget stays verbatim;
  * older messages are folded into a running summary via one LLM call
    (summary + recent tail kept);
  * the summarizer also extracts durable learner facts (preferences,
    personal details worth remembering) into the subject profile.
"""

from __future__ import annotations

from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.llm.factory import complete

SUMMARIZE_PROMPT = """你是一个对话摘要器。请把下面这段师生对话压缩成一份中文摘要。

## 要求
1. 保留：讨论过的知识点与结论、学生犯过的错误与纠错过程、学生提出的问题、教师/助手给出的关键解释、任何个人信息或偏好。
2. 输出两条：
   - 摘要：3-8 条要点，每条一行，用"- "开头，覆盖上述信息，具体（保留公式或专有名词）。
   - 新事实：从中提取值得长期记住的学生信息（如：喜欢用例子理解、在学某门课、生日、喜欢的方程等），每条一行，用"FACT: "开头；没有则输出 "FACT: 无"。

## 输出格式
摘要：
- 要点1
- 要点2

新事实：
FACT: xxx
"""


async def summarize(messages: list[dict], language: str = "zh") -> tuple[str, list[str]]:
    """Return ``(summary, facts)`` for a list of messages."""
    if not messages:
        return "", []
    transcript = "\n".join(
        f"{m.get('role', 'user')}: {str(m.get('content', ''))[:400]}" for m in messages
    )
    cfg = get_llm_config()
    raw = await complete(
        prompt=SUMMARIZE_PROMPT + "\n\n## 对话\n" + transcript,
        system_prompt="你是对话摘要器。",
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
    )
    return _parse(raw)


def _parse(raw: str) -> tuple[str, list[str]]:
    summary_lines: list[str] = []
    facts: list[str] = []
    in_facts = False
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("新事实"):
            in_facts = True
            continue
        if line.startswith("FACT:"):
            f = line[5:].strip()
            if f and f != "无":
                facts.append(f)
            continue
        if in_facts:
            continue
        if line.startswith("- ") or line.startswith("摘要"):
            summary_lines.append(line.lstrip("- ").strip())
    summary = "\n".join(summary_line for summary_line in summary_lines if summary_line)
    return summary, facts
