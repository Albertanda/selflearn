from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.llm.reasoning_controls import PROVIDER_DEFAULT_EFFORT
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager


async def _noop_async(*_args, **_kwargs):
    return None


def _catalog() -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "p-ds",
                "active_model_id": "m-flash",
                "profiles": [
                    {
                        "id": "p-ds",
                        "name": "DeepSeek",
                        "binding": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-test",
                        "models": [
                            {
                                "id": "m-flash",
                                "name": "Flash",
                                "model": "deepseek-flash",
                                "reasoning_effort": "medium",
                            },
                            {
                                "id": "m-pro",
                                "name": "Pro",
                                "model": "deepseek-v4-pro",
                            },
                        ],
                    },
                    {
                        "id": "p-qwen",
                        "name": "Qwen",
                        "binding": "dashscope",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "api_key": "sk-qwen",
                        "models": [
                            {
                                "id": "m-qwen",
                                "name": "Qwen 3.8",
                                "model": "qwen3.8-max",
                            }
                        ],
                    },
                ],
            }
        },
    }


class FakeContextBuilder:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def build(self, **kwargs):
        return SimpleNamespace(
            conversation_history=[],
            conversation_summary="",
            context_text="",
            token_count=0,
            budget=0,
        )


class FakeOrchestrator:
    async def handle(self, context):
        yield StreamEvent(
            type=StreamEventType.CONTENT,
            source="chat",
            stage="responding",
            content="ok",
            metadata={"call_kind": "llm_final_response"},
        )
        yield StreamEvent(type=StreamEventType.DONE, source="chat")


def _wire_fakes(monkeypatch: pytest.MonkeyPatch, runtime: TurnRuntimeManager, captured):
    def fake_activate(selection, **kwargs):
        captured.setdefault("activations", []).append(
            {"selection": selection, **kwargs}
        )
        return SimpleNamespace(
            model="deepseek-flash", provider_name="deepseek"
        ), object()

    monkeypatch.setattr(
        "deeptutor.services.config.get_model_catalog_service",
        lambda: SimpleNamespace(load=_catalog),
    )
    monkeypatch.setattr(
        "deeptutor.services.model_selection.runtime.activate_llm_selection",
        fake_activate,
    )
    monkeypatch.setattr(
        "deeptutor.services.model_selection.runtime.reset_llm_selection",
        lambda _token: captured.setdefault("reset_called", True),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder
    )
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_store",
        lambda: SimpleNamespace(read_l3_concat=lambda: "", emit=_noop_async),
    )
    monkeypatch.setattr(
        "deeptutor.services.skill.get_skill_service",
        lambda: SimpleNamespace(
            summary_entries=lambda: [],
            load_always_for_context=lambda: "",
            load_for_context=lambda _skills: "",
            list_skills=lambda: [],
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.persona.get_persona_service",
        lambda: SimpleNamespace(load_for_context=lambda name: ""),
    )
    async def no_title(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runtime, "_maybe_generate_session_title", no_title)


@pytest.mark.asyncio
async def test_effort_override_is_authorised_then_resolved_and_snapshotted(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    _wire_fakes(monkeypatch, runtime, captured)

    selection = {"profile_id": "p-ds", "model_id": "m-flash"}
    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "config": {},
            "llm_selection": selection,
            "reasoning_override": {"mode": "effort", "effort": "minimal"},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    activation = captured["activations"][-1]
    assert activation["reasoning_effort"] == "low"
    assert activation["reasoning_protocol"] == "deepseek"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    snapshot = detail["messages"][0]["metadata"]["request_snapshot"]
    assert snapshot["reasoningOverride"] == {"mode": "effort", "effort": "minimal"}
    assert snapshot["reasoning"]["requested"] == "minimal"
    assert snapshot["reasoning"]["effective"] == "low"
    assert snapshot["reasoning"]["source"] == "alias"
    assert detail["preferences"]["reasoning_preferences"]["p-ds:m-flash"] == {
        "mode": "effort",
        "effort": "minimal",
    }

    # A provider-default selection suppresses the project default and is not
    # written to the vendor as the literal sentinel.
    _, second = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "again",
            "session_id": session["id"],
            "config": {},
            "llm_selection": selection,
            "reasoning_override": {"mode": "provider_default"},
        }
    )
    async for _event in runtime.subscribe_turn(second["id"], after_seq=0):
        pass
    assert captured["activations"][-1]["reasoning_effort"] == PROVIDER_DEFAULT_EFFORT
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    second_user = [m for m in detail["messages"] if m["role"] == "user"][-1]
    assert second_user["metadata"]["request_snapshot"]["reasoning"]["effective"] == (
        "provider_default"
    )


@pytest.mark.asyncio
async def test_invalid_effort_is_rejected_before_provider_call_and_keeps_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    _wire_fakes(monkeypatch, runtime, captured)

    selection = {"profile_id": "p-ds", "model_id": "m-flash"}
    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "first",
            "session_id": None,
            "config": {},
            "llm_selection": selection,
            "reasoning_override": {"mode": "effort", "effort": "low"},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass
    assert len(captured["activations"]) == 1
    with pytest.raises(RuntimeError, match="Unsupported reasoning level"):
        await runtime.start_turn(
            {
                "type": "start_turn",
                "content": "bad",
                "session_id": session["id"],
                "config": {},
                "llm_selection": selection,
                "reasoning_override": {
                    "mode": "effort",
                    "effort": "ultra-bogus",
                },
            }
        )
    assert len(captured["activations"]) == 1
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == [
        "first"
    ]


@pytest.mark.asyncio
async def test_reasoning_is_scoped_per_model_and_does_not_change_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    _wire_fakes(monkeypatch, runtime, captured)
    catalog = _catalog()
    original = {
        "active_profile_id": catalog["services"]["llm"]["active_profile_id"],
        "active_model_id": catalog["services"]["llm"]["active_model_id"],
        "model_efforts": [
            model.get("reasoning_effort")
            for profile in catalog["services"]["llm"]["profiles"]
            for model in profile["models"]
        ],
    }
    session, first = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "deepseek",
            "session_id": None,
            "config": {},
            "llm_selection": {"profile_id": "p-ds", "model_id": "m-flash"},
            "reasoning_override": {"mode": "effort", "effort": "max"},
        }
    )
    async for _event in runtime.subscribe_turn(first["id"], after_seq=0):
        pass
    _session2, second = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "qwen",
            "session_id": session["id"],
            "config": {},
            "llm_selection": {"profile_id": "p-qwen", "model_id": "m-qwen"},
            "reasoning_override": {"mode": "effort", "effort": "medium"},
        }
    )
    async for _event in runtime.subscribe_turn(second["id"], after_seq=0):
        pass
    assert [a["reasoning_effort"] for a in captured["activations"]] == [
        "max",
        "medium",
    ]
    assert [a["reasoning_protocol"] for a in captured["activations"]] == [
        "deepseek",
        "dashscope_qwen_effort",
    ]
    assert catalog["services"]["llm"]["active_profile_id"] == original[
        "active_profile_id"
    ]
    assert catalog["services"]["llm"]["active_model_id"] == original["active_model_id"]
    assert [
        model.get("reasoning_effort")
        for profile in catalog["services"]["llm"]["profiles"]
        for model in profile["models"]
    ] == original["model_efforts"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    prefs = detail["preferences"]["reasoning_preferences"]
    assert prefs["p-ds:m-flash"] == {"mode": "effort", "effort": "max"}
    assert prefs["p-qwen:m-qwen"] == {"mode": "effort", "effort": "medium"}


@pytest.mark.asyncio
async def test_inherit_reads_the_models_saved_default_without_an_explicit_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    _wire_fakes(monkeypatch, runtime, captured)
    selection = {"profile_id": "p-ds", "model_id": "m-flash"}
    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "inherit",
            "session_id": None,
            "config": {},
            "llm_selection": selection,
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    activation = captured["activations"][-1]
    # The fixture stores the legacy alias ``medium`` on this model; the
    # backend maps it to the native DeepSeek ``high`` level.
    assert activation["reasoning_effort"] == "high"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    snapshot = detail["messages"][0]["metadata"]["request_snapshot"]
    assert snapshot["reasoning"]["mode"] == "inherit"
    assert snapshot["reasoning"]["requested"] == "medium"
    assert snapshot["reasoning"]["effective"] == "high"
    assert snapshot["reasoning"]["source"] == "alias"
