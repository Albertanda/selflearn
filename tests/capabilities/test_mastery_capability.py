"""Tests for mastery loop hooks that bind persisted pending questions."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.capabilities.mastery.capability import MasteryPathCapability
from deeptutor.capabilities.mastery.loop import MasteryLoopCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.learning.models import (
    InteractionStatus,
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
    PendingQuestion,
)
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore


def _use_store_root(monkeypatch, root: Path) -> None:
    def _init(self, root_arg=None):
        self._root = root / "learning"
        self._root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(LearningStore, "__init__", _init)


def _context() -> UnifiedContext:
    return UnifiedContext(
        user_message="continue",
        session_id="session-1",
        metadata={"mastery_mode": True, "mastery_path_id": "path-1", "turn_id": "turn-2"},
    )


def _progress_with_objective() -> LearningProgress:
    return LearningProgress(
        book_id="path-1",
        modules=[
            LearningModule(
                id="module-1",
                name="Colours",
                order=0,
                knowledge_points=[
                    KnowledgePoint(
                        id="kp-1",
                        name="Primary colours",
                        type=KnowledgeType.CONCEPT,
                        module_id="module-1",
                    )
                ],
            )
        ],
    )


def test_pending_question_overrides_reauthored_ask_user_mapping(tmp_path, monkeypatch):
    _use_store_root(monkeypatch, tmp_path)
    progress = LearningProgress(book_id="path-1")
    progress.pending_question = PendingQuestion(
        question_id="stable-question",
        knowledge_point_id="kp-1",
        prompt="Which colour?",
        question_type="choice",
        expected_answer="B",
        options=["A: red", "B: blue"],
    )
    LearningStore().save(progress)

    rebound = MasteryLoopCapability().augment_kwargs(
        "ask_user",
        {
            "intro": "Keep this lead-in",
            "questions": [
                {
                    "id": "new-question",
                    "prompt": "Rewritten question",
                    "options": [
                        {"label": "A", "description": "blue"},
                        {"label": "B", "description": "red"},
                    ],
                }
            ],
        },
        _context(),
    )

    assert rebound == {
        "intro": "Keep this lead-in",
        "questions": [
            {
                "id": "stable-question",
                "prompt": "Which colour?",
                "options": [
                    {"label": "A", "description": "red"},
                    {"label": "B", "description": "blue"},
                ],
                "multi_select": False,
                "allow_free_text": True,
            }
        ],
    }


def test_ask_user_is_untouched_without_pending_question(tmp_path, monkeypatch):
    _use_store_root(monkeypatch, tmp_path)
    LearningStore().save(_progress_with_objective())
    authored = {"questions": [{"id": "clarify", "prompt": "Which scope?"}]}

    assert MasteryLoopCapability().augment_kwargs("ask_user", authored, _context()) == authored


@pytest.mark.asyncio
async def test_pause_and_resume_hooks_persist_interaction_boundaries(tmp_path, monkeypatch):
    _use_store_root(monkeypatch, tmp_path)
    pending = PendingQuestion(
        question_id="stable-question",
        knowledge_point_id="kp-1",
        prompt="Which colour?",
        question_type="choice",
        expected_answer="B",
        options=["A: red", "B: blue"],
    )
    LearningStore().save(_progress_with_objective())
    LearningService().register_question(
        "path-1",
        pending,
        session_id="session-1",
        turn_id="turn-2",
    )
    ask_user = {
        "questions": [
            {
                "id": "stable-question",
                "prompt": "Which colour?",
            }
        ]
    }
    capability = MasteryLoopCapability()

    await capability.on_user_pause(_context(), ask_user)
    awaiting = LearningStore().get_interaction("path-1", "stable-question")
    assert awaiting is not None
    assert awaiting.status == InteractionStatus.AWAITING_INPUT

    await capability.on_user_resume(
        _context(),
        ask_user,
        reply_text="fallback",
        answers=[{"questionId": "stable-question", "text": "B"}],
    )
    answered = LearningStore().get_interaction("path-1", "stable-question")
    assert answered is not None
    assert answered.status == InteractionStatus.ANSWERED
    assert answered.user_answer == "B"


@pytest.mark.asyncio
async def test_direct_capability_call_holds_path_lease(tmp_path, monkeypatch):
    _use_store_root(monkeypatch, tmp_path)
    observed = {}

    async def _observe_lease(_pipeline, context, _stream):
        observed["lease"] = LearningStore().get_path_lease(context.metadata["mastery_path_id"])

    monkeypatch.setattr(AgenticChatPipeline, "run", _observe_lease)
    context = _context()

    await MasteryPathCapability().run(context, StreamBus())

    lease = observed["lease"]
    assert lease is not None
    assert lease.session_id == "session-1"
    assert lease.turn_id == "turn-2"
    assert LearningStore().get_path_lease("path-1") is None
    assert LearningStore().list_session_ids("path-1") == ["session-1"]
