"""The compressed-history summary must reach the final LLM messages.

Regression test: ``ContextBuilder`` emits the summary as a leading
``role: "system"`` entry in ``conversation_history``; the agentic pipeline
used to filter history to user/assistant roles, silently dropping it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext


@pytest.fixture(autouse=True)
def _fake_model_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """两个场景只验证消息组织，因此显式提供模型配置替身。

    生产构造器不去猜一个模型，也不读真实 model catalog：这里把
    ``get_llm_config`` 换成一个固定形状的替身，测试才真正执行断言而不是在
    构造阶段失败。
    """
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(
            model="test-model",
            provider_name="test-provider",
            binding="openai",
            api_key="",
            base_url="",
            api_version=None,
            extra_headers={},
            reasoning_effort=None,
        ),
    )


def test_summary_system_message_reaches_messages() -> None:
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="next question",
        conversation_history=[
            {"role": "system", "content": "earlier turns summary"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ],
    )

    messages = pipeline._build_loop_messages(
        context=context,
        enabled_tools=[],
    )

    # The summary rides directly after the main system prompt, before history.
    assert messages[1]["role"] == "system"
    assert "earlier turns summary" in str(messages[1]["content"])
    assert messages[2] == {"role": "user", "content": "old question"}
    # Exactly one summary injection — no duplicates elsewhere.
    summary_count = sum(
        1
        for m in messages[1:]
        if m["role"] == "system" and "earlier turns summary" in str(m["content"])
    )
    assert summary_count == 1


def test_empty_system_entries_still_filtered() -> None:
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="q",
        conversation_history=[
            {"role": "system", "content": "   "},
            {"role": "user", "content": "old question"},
        ],
    )

    messages = pipeline._build_loop_messages(
        context=context,
        enabled_tools=[],
    )

    assert messages[1] == {"role": "user", "content": "old question"}
