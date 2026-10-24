"""S14/P1-52: WebSocket 科目检索、作用域与失败闭环验收。

覆盖 W1–W5。测试从真实 ``/api/v1/ws`` 进入真实 ``TurnRuntimeManager``、
``ChatOrchestrator`` 和 ``AgenticChatPipeline``；只把外部模型 HTTP 流与
PageIndex/vision fixture 放在各自边界。RAG 索引/检索、工具 dispatch、scope
resolver、来源投影、会话偏好/快照和事件持久化都实际运行。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from llama_index.core import Settings
from PIL import Image
import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.api.routers import unified_ws
from deeptutor.capabilities.explore_context import explorer as explorer_mod
from deeptutor.services.rag.pipelines.llamaindex import embedding_adapter
from deeptutor.services.rag.pipelines.llamaindex import pipeline as llamaindex_pipeline
from deeptutor.services.rag.pipelines.llamaindex import storage as llamaindex_storage
from deeptutor.services.rag.pipelines.pageindex.pipeline import PageIndexPipeline
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.subjects import errors as subject_errors
from deeptutor.subjects import kb_scope, material_manifest, store
from tests.phase1 import helpers
from tests.phase1.test_p1_22 import _make_ready_kb
from tests.phase1.test_p1_23 import _register_global_kb

KB_NAME = "shared-kb"
ROUTE = "/api/v1/ws"


def _catalog() -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "s14-ws-llm-profile",
                "active_model_id": "s14-ws-llm-model",
                "profiles": [
                    {
                        "id": "s14-ws-llm-profile",
                        "name": "S14 WS stub",
                        "binding": "openai",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "sk-s14-ws-fake-only",
                        "models": [
                            {
                                "id": "s14-ws-llm-model",
                                "name": "s14-ws",
                                "model": "s14-ws-stub",
                            }
                        ],
                    }
                ],
            },
            "embedding": {
                "active_profile_id": "s14-ws-embedding-profile",
                "active_model_id": "s14-ws-embedding-model",
                "profiles": [
                    {
                        "id": "s14-ws-embedding-profile",
                        "name": "S14 WS embedding stub",
                        "binding": "openai",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "sk-s14-ws-fake-only",
                        "models": [
                            {
                                "id": "s14-ws-embedding-model",
                                "name": "s14-ws-embedding",
                                "model": "s14-ws-text-embedding",
                                "dimension": 8,
                            }
                        ],
                    }
                ],
            },
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


def _seed_catalog(admin_root: Path) -> None:
    path = admin_root / "user" / "settings" / "model_catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_catalog(), ensure_ascii=False), encoding="utf-8")


def _configure_llamaindex(self) -> None:  # noqa: ANN001 - bound as a method
    Settings.embed_model = embedding_adapter.CustomEmbedding(
        embedding_config=SimpleNamespace(
            binding="openai",
            model="s14-ws-text-embedding",
            dim=8,
            effective_url="http://127.0.0.1:9/v1",
            base_url="http://127.0.0.1:9/v1",
            api_version=None,
            send_dimensions=None,
        )
    )
    Settings.chunk_size = 128
    Settings.chunk_overlap = 20


async def _noop_verify(self) -> None:  # noqa: ANN001
    return None


@pytest.fixture
def ws_env(p1_runtime: Path, p1_providers, monkeypatch: pytest.MonkeyPatch):
    _seed_catalog(p1_runtime)
    monkeypatch.setattr(llamaindex_pipeline.LlamaIndexPipeline, "_configure_settings", _configure_llamaindex)
    monkeypatch.setattr(llamaindex_pipeline.LlamaIndexPipeline, "_current_signature", lambda self: None)
    monkeypatch.setattr(
        llamaindex_pipeline.LlamaIndexPipeline, "_verify_embedding_connectivity", _noop_verify
    )
    # 本验收手工建立无签名版本的 fixture index；这个不适用于 fixture 的
    # "indexed with unknown" 提示不应变成 raw-log 回调泄漏，业务检索仍然真实。
    monkeypatch.setattr(
        llamaindex_pipeline.LlamaIndexPipeline,
        "_embedding_mismatch_warning",
        lambda self, kb_name: "",
    )

    async def no_title(self, **_kwargs):
        return None

    monkeypatch.setattr(TurnRuntimeManager, "_maybe_generate_session_title", no_title)
    return SimpleNamespace(
        root=p1_runtime,
        embedding=p1_providers["embedding"],
        llm=p1_providers["llm"],
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(unified_ws.router, prefix="/api/v1")
    return app


def _chunk(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    *,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta: dict[str, Any] = {"content": content, "tool_calls": None}
    if tool_calls is not None:
        delta["tool_calls"] = [
            SimpleNamespace(
                index=item.get("index", index),
                id=item["id"],
                function=SimpleNamespace(
                    name=item["name"], arguments=item["arguments"]
                ),
            )
            for index, item in enumerate(tool_calls)
        ]
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(**delta), finish_reason=finish_reason)],
        usage=None,
    )


async def _stream(chunks: list[SimpleNamespace]):
    for chunk in chunks:
        yield chunk


class _ScriptedClient:
    """Deterministic OpenAI-stream double at the real pipeline client seam."""

    def __init__(self, rounds: list[Any]) -> None:
        self.rounds = list(rounds)
        self.calls: list[dict[str, Any]] = []

        owner = self

        class _Completions:
            async def create(self, **kwargs):
                owner.calls.append(kwargs)
                if not owner.rounds:
                    raise AssertionError("scripted LLM stream exhausted")
                item = owner.rounds.pop(0)
                chunks = item(kwargs.get("messages") or []) if callable(item) else item
                return _stream(list(chunks))

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()

    async def aclose(self) -> None:
        return None


def _install_client(monkeypatch: pytest.MonkeyPatch, rounds: list[Any]) -> _ScriptedClient:
    client = _ScriptedClient(rounds)
    monkeypatch.setattr(AgenticChatPipeline, "_build_openai_client", lambda self: client)
    return client


def _tool_round(name: str, arguments: dict[str, Any], *, text: str = "检索中。") -> list[SimpleNamespace]:
    return [
        _chunk(content=text),
        _chunk(
            tool_calls=[
                {
                    "id": f"call-{hashlib.sha1(json.dumps(arguments, sort_keys=True).encode()).hexdigest()[:10]}",
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                }
            ]
        ),
    ]


def _final(text: str) -> list[SimpleNamespace]:
    return [_chunk(content=text)]


def _final_from_tool(prefix: str = "FINAL:") -> Callable[[list[dict[str, Any]]], list[SimpleNamespace]]:
    def build(messages: list[dict[str, Any]]) -> list[SimpleNamespace]:
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        assert tool_messages, "model final round has no real tool result"
        content = "\n".join(str(item.get("content") or "") for item in tool_messages)
        match = re.search(r"(?:A|B|GLOBAL)-ONLY-[0-9a-f]+", content)
        if match is None:
            return _final(prefix + "NO-TOOL-MARKER")
        return _final(prefix + match.group(0))

    return build


def _receive_until(
    websocket, terminal: tuple[str, ...] = ("done", "error"), *, limit: int = 400
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for _ in range(limit):
        event = websocket.receive_json()
        events.append(event)
        if event.get("type") in terminal and event.get("type") != "error":
            return events
        if event.get("type") == "error":
            metadata = event.get("metadata") or {}
            if metadata.get("status") in {"rejected", "failed"} and not metadata.get("turn_terminal"):
                return events
            # A failed turn still emits a following DONE; a rejected start_turn
            # does not create a turn at all.
            if metadata.get("status") == "rejected" and "done" not in [
                item.get("type") for item in events
            ]:
                return events
    raise AssertionError(f"no terminal event; last types={[e.get('type') for e in events[-10:]]}")


def _turn(websocket, payload: dict[str, Any]) -> list[dict[str, Any]]:
    websocket.send_json({"type": "start_turn", **payload})
    return _receive_until(websocket)


def _done(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(event for event in events if event.get("type") == "done")


def _session_id(events: list[dict[str, Any]]) -> str:
    for event in events:
        if event.get("type") == "session":
            value = (event.get("metadata") or {}).get("session_id")
            if value:
                return str(value)
    raise AssertionError("no session event")


def _result(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(event for event in events if event.get("type") == "result")


def _sources(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "sources":
            continue
        metadata = event.get("metadata") or {}
        found.extend(item for item in metadata.get("sources") or [] if isinstance(item, dict))
    return found


def _tool_results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == "tool_result"]


def _build_index(base_dir: Path, kb_name: str, raw_file: Path) -> None:
    async def run() -> None:
        pipeline = llamaindex_pipeline.LlamaIndexPipeline(
            kb_base_dir=str(base_dir), signature_provider=lambda: None
        )
        assert await pipeline.initialize(kb_name, [str(raw_file)]) is True

    asyncio.run(run())


def _libraries(ws_env, *, with_global: bool = True):
    a = helpers.make_subject(ws_env.root, "科目A")
    b = helpers.make_subject(ws_env.root, "科目B")
    kb_a = _make_ready_kb(a, KB_NAME, marker="A-ONLY-71c0", kb_type="assignment")
    kb_b = _make_ready_kb(b, KB_NAME, marker="B-ONLY-82d1", kb_type="assignment")
    _build_index(a.knowledge_bases, KB_NAME, Path(kb_a) / "raw" / "A-ONLY-71c0.txt")
    _build_index(b.knowledge_bases, KB_NAME, Path(kb_b) / "raw" / "B-ONLY-82d1.txt")
    data = SimpleNamespace(A=a, B=b, kb_a=kb_a, kb_b=kb_b)
    if with_global:
        global_dir = _register_global_kb(ws_env.root, KB_NAME)
        (Path(global_dir) / "raw" / "global.txt").write_text(
            "GLOBAL-ONLY-93e2\n", encoding="utf-8"
        )
        _build_index(
            helpers.global_kb_root(ws_env.root),
            KB_NAME,
            Path(global_dir) / "raw" / "global.txt",
        )
        data.global_dir = global_dir
    data.ref_a = kb_scope.encode_subject_kb_ref(a.subject_id, KB_NAME)
    data.ref_b = kb_scope.encode_subject_kb_ref(b.subject_id, KB_NAME)
    data.ref_global = f"admin:kb:{KB_NAME}"
    return data


def _portal(client: TestClient, func, *args):
    """Run a coroutine function on the app's own event loop."""
    portal = getattr(client, "portal", None)
    assert portal is not None, "TestClient portal unavailable"
    return portal.call(func, *args)


# ---------------------------------------------------------------------------
# W1 — 真实 A/B/global 同名 KB，模型先调用 rag，再根据真实工具返回回答
# ---------------------------------------------------------------------------
def test_w1_ws_turn_uses_actual_subject_rag_and_returns_only_that_source(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    libs = _libraries(ws_env)
    client = _install_client(
        monkeypatch,
        [
            _tool_round("rag", {"query": "A marker", "kb_name": libs.ref_a}),
            _final_from_tool("A-ANSWER:"),
            _tool_round("rag", {"query": "B marker", "kb_name": libs.ref_b}),
            _final_from_tool("B-ANSWER:"),
            _tool_round("rag", {"query": "global marker", "kb_name": libs.ref_global}),
            _final_from_tool("GLOBAL-ANSWER:"),
        ],
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            first = _turn(
                websocket,
                {
                    "content": "查 A 的标记",
                    "session_id": None,
                    "capability": "chat",
                    "subject_id": libs.A.subject_id,
                    "tools": ["rag"],
                    "language": "en",
                    "config": {},
                },
            )
            session_id = _session_id(first)
            assert _done(first)["metadata"]["status"] == "completed"
            first_result = _result(first)["metadata"]["response"]
            assert first_result.startswith("A-ANSWER:A-ONLY-71c0")
            first_sources = _sources(first)
            assert first_sources, "real rag result must emit sources"
            assert any(item.get("kb_ref") == libs.ref_a for item in first_sources)
            assert any(item.get("subject_id") == libs.A.subject_id for item in first_sources)
            assert "B-ONLY" not in json.dumps(first, ensure_ascii=False)
            assert "GLOBAL-ONLY" not in json.dumps(first, ensure_ascii=False)
            assert any(
                (item.get("metadata") or {}).get("tool") == "rag"
                or (item.get("metadata") or {}).get("tool_name") == "rag"
                for item in _tool_results(first)
            )

            second = _turn(
                websocket,
                {
                    "content": "查 B 的标记",
                    "session_id": session_id,
                    "subject_id": libs.B.subject_id,
                    "tools": ["rag"],
                    "language": "en",
                    "config": {},
                },
            )
            assert _done(second)["metadata"]["status"] == "completed"
            assert _result(second)["metadata"]["response"].startswith("B-ANSWER:B-ONLY-82d1")
            second_sources = _sources(second)
            assert any(item.get("kb_ref") == libs.ref_b for item in second_sources)
            assert "A-ONLY" not in json.dumps(second, ensure_ascii=False)
            assert "GLOBAL-ONLY" not in json.dumps(second, ensure_ascii=False)

            third = _turn(
                websocket,
                {
                    "content": "显式使用全局库",
                    "session_id": session_id,
                    # 显式 clear + 显式 global：本轮只应挂载 global。
                    "subject_id": None,
                    "knowledge_bases": [libs.ref_global],
                    "tools": ["rag"],
                    "language": "en",
                    "config": {},
                },
            )
            assert _done(third)["metadata"]["status"] == "completed"
            assert _result(third)["metadata"]["response"].startswith(
                "GLOBAL-ANSWER:GLOBAL-ONLY-93e2"
            )
            third_sources = _sources(third)
            assert any(item.get("kb_ref") == libs.ref_global for item in third_sources)
            assert "A-ONLY" not in json.dumps(third, ensure_ascii=False)
            assert "B-ONLY" not in json.dumps(third, ensure_ascii=False)

    # 模型确实发起了生产 rag 工具；调用参数含服务端 wire ref。
    assert any(
        json.dumps(call.get("messages") or [], ensure_ascii=False).find("GLOBAL-ONLY")
        >= 0
        for call in client.calls
    )


# ---------------------------------------------------------------------------
# W2 — 三态、会话隔离、冲突不创建 turn、regenerate 快照
# ---------------------------------------------------------------------------
def test_w2_ws_subject_three_state_and_session_isolation(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = helpers.make_subject(ws_env.root, "三态A")
    b = helpers.make_subject(ws_env.root, "三态B")
    _install_client(
        monkeypatch,
        [_final(f"W2-{index}") for index in range(8)],
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            first = _turn(
                websocket,
                {
                    "content": "explicit A",
                    "session_id": None,
                    "subject_id": a.subject_id,
                    "tools": [],
                    "config": {},
                },
            )
            session_id = _session_id(first)
            turns = [first]
            for content, subject in (
                ("omitted keeps A", "__omit__"),
                ("switch B", b.subject_id),
                ("null clears", None),
                ("omitted keeps clear", "__omit__"),
                ("empty clears", ""),
            ):
                payload: dict[str, Any] = {
                    "content": content,
                    "session_id": session_id,
                    "tools": [],
                    "config": {},
                }
                if subject != "__omit__":
                    payload["subject_id"] = subject
                turns.append(_turn(websocket, payload))

            fresh = _turn(
                websocket,
                {"content": "fresh session", "session_id": None, "tools": [], "config": {}},
            )
            fresh_session_id = _session_id(fresh)
            assert fresh_session_id != session_id

            before = len(_portal(test_client, _runtime().store.get_messages, session_id))
            conflict = _turn(
                websocket,
                {
                    "content": "conflict",
                    "session_id": session_id,
                    "subject_id": a.subject_id,
                    "tools": [],
                    "config": {"subject_id": b.subject_id},
                },
            )
            error = next(event for event in conflict if event.get("type") == "error")
            assert error["metadata"]["turn_terminal"] is True
            assert error["metadata"]["status"] == "rejected"
            assert error["metadata"]["error"]["code"] == "invalid_input"
            assert len(_portal(test_client, _runtime().store.get_messages, session_id)) == before
            websocket.send_json({"type": "ping"})
            assert _receive_until(websocket, ("pong",), limit=10)[-1]["type"] == "pong"

        session = _portal(test_client, _runtime().store.get_session_with_messages, session_id)
        assert session is not None
        preferences = session["preferences"]
        assert preferences["subject_id"] is None
        user_messages = [item for item in session["messages"] if item["role"] == "user"]
        snapshots = [
            (item.get("metadata") or {}).get("request_snapshot", {}).get("subject_id")
            for item in user_messages
        ]
        assert snapshots == [
            a.subject_id,
            a.subject_id,
            b.subject_id,
            None,
            None,
            None,
        ], snapshots
        assert [item["role"] for item in session["messages"]] == [
            "user",
            "assistant",
        ] * 6
        fresh = _portal(test_client, _runtime().store.get_session_with_messages, fresh_session_id)
        assert fresh is not None
        fresh_user = [item for item in fresh["messages"] if item["role"] == "user"]
        assert (fresh_user[0].get("metadata") or {}).get("request_snapshot", {}).get(
            "subject_id"
        ) is None
        assert fresh["preferences"]["subject_id"] is None


def test_w2_regenerate_uses_original_snapshot_and_keeps_old_assistant(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = helpers.make_subject(ws_env.root, "重放A")
    b = helpers.make_subject(ws_env.root, "重放B")
    _install_client(monkeypatch, [_final("ORIGINAL"), _final("AFTER-CLEAR")])

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            first = _turn(
                websocket,
                {
                    "content": "original question",
                    "session_id": None,
                    "subject_id": a.subject_id,
                    "tools": [],
                    "config": {},
                },
            )
            session_id = _session_id(first)
            original_messages = _portal(
                test_client, _runtime().store.get_messages, session_id
            )
            assistant_id = next(
                item["id"] for item in original_messages if item["role"] == "assistant"
            )
            # 之后把会话偏好改成 B，再删掉 A；重放必须继续使用快照 A。
            _portal(
                test_client,
                _runtime().store.update_session_preferences,
                session_id,
                {"subject_id": b.subject_id},
            )
            assert store.delete_subject(a.subject_id) is True

            websocket.send_json({"type": "regenerate", "session_id": session_id})
            refused = _receive_until(websocket, ("done", "error"))
            error = next(event for event in refused if event.get("type") == "error")
            assert error["metadata"]["error"]["code"] == "subject_not_found"
            assert error["metadata"]["status"] == "rejected"
            assert error["session_id"] == session_id
            assert "重放A" not in json.dumps(error, ensure_ascii=False)
            assert (
                _portal(test_client, _runtime().store.get_messages, session_id)
                == original_messages
            )
            assert next(item for item in original_messages if item["role"] == "assistant")["id"] == assistant_id

            # 显式清空后同一 socket 仍可继续；不能静默继承 B。
            recovered = _turn(
                websocket,
                {
                    "content": "clear and continue",
                    "session_id": session_id,
                    "subject_id": None,
                    "tools": [],
                    "config": {},
                },
            )
            assert _done(recovered)["metadata"]["status"] == "completed"
            assert _result(recovered)["metadata"]["response"] == "AFTER-CLEAR"
            websocket.send_json({"type": "ping"})
            assert _receive_until(websocket, ("pong",), limit=10)[-1]["type"] == "pong"


# ---------------------------------------------------------------------------
# W3 — 伪造作用域/越科/歧义/read_source + 未 ready 不退 global + 终端失败
# ---------------------------------------------------------------------------
def test_w3_ws_forged_scope_arguments_are_refused_and_never_read_other_trees(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    libs = _libraries(ws_env)
    attacker = "/tmp/s14-forged-base-6ad1"
    client = _install_client(
        monkeypatch,
        [
            # explore_context 真实 pre-pass：它拥有 read_source。
            _tool_round(
                "read_source",
                {"source_id": "at-does-not-exist"},
                text="检查附件。",
            ),
            _final("Investigation: forged source id was refused."),
            # 回答循环：三个 rag 作用域伪造/越科/歧义调用。
            [
                _chunk(content="准备并行检查。"),
                _chunk(
                    tool_calls=[
                        {
                            "id": "forged-base",
                            "name": "rag",
                            "arguments": json.dumps(
                                {
                                    "query": "forged",
                                    "kb_name": libs.ref_a,
                                    "kb_base_dir": attacker,
                                    "provider": "pageindex",
                                }
                            ),
                        },
                        {
                            "id": "cross-subject",
                            "name": "rag",
                            "arguments": json.dumps(
                                {"query": "cross", "kb_name": libs.ref_b}
                            ),
                        },
                        {
                            "id": "ambiguous",
                            "name": "rag",
                            "arguments": json.dumps({"query": "bare", "kb_name": KB_NAME}),
                        },
                    ]
                ),
            ],
            _final_from_tool("SCOPED:"),
        ],
    )
    monkeypatch.setattr(
        explorer_mod, "build_openai_client", lambda _config: client
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {
                    "content": "检查伪造参数",
                    "session_id": None,
                    "subject_id": libs.A.subject_id,
                    "knowledge_bases": [libs.ref_global],
                    "tools": ["rag"],
                    # 真实附件写入 source_index，使 explore_context 的 read_source
                    # 走到 ID 校验；模型随后伪造一个不存在的 id。
                    # 模型随后伪造一个不存在的 id。
                    "attachments": [
                        {
                            "type": "file",
                            "id": "valid-source-1",
                            "filename": "valid.txt",
                            "mime_type": "text/plain",
                            "base64": __import__("base64").b64encode(
                                b"valid attached source"
                            ).decode(),
                        }
                    ],
                    "config": {},
                },
            )
            assert _done(events)["metadata"]["status"] == "completed"
            assert _result(events)["metadata"]["response"].startswith("SCOPED:A-ONLY-71c0")
            blob = json.dumps(events, ensure_ascii=False)
            assert "scope_forbidden" in blob
            assert "invalid_input" in blob
            assert "unknown source_id" in blob
            assert "B-ONLY" not in blob
            assert attacker not in blob
            assert "sk-s14" not in blob
            tool_calls = [event for event in events if event.get("type") == "tool_call"]
            assert tool_calls
            assert all(attacker not in json.dumps(event) for event in tool_calls)
            assert len(_tool_results(events)) == 4
            names = {
                (item.get("function") or {}).get("name")
                for call in client.calls
                for item in (call.get("tools") or [])
                if isinstance(item, dict)
            }
            assert {"rag", "read_source"} <= names
            assert not any(name and "mcp" in name.lower() for name in names)


def test_w3_ws_not_ready_subject_does_not_fall_back_and_socket_recovers(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    libs = _libraries(ws_env)
    # 让 A 的源在索引后改变：mount 集合会带公开 warning，A 不再可查询。
    raw = Path(libs.kb_a) / "raw" / "A-ONLY-71c0.txt"
    raw.write_text("A-ONLY-71c0 changed after publish\n", encoding="utf-8")
    client = _install_client(
        monkeypatch,
        [
            _tool_round("rag", {"query": "A marker", "kb_name": libs.ref_a}),
            _final("NO-FALLBACK"),
            _final("RECOVERED"),
        ],
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {
                    "content": "A 的库未 ready",
                    "session_id": None,
                    "subject_id": libs.A.subject_id,
                    "tools": ["rag"],
                    "config": {},
                },
            )
            done = _done(events)
            assert done["metadata"]["status"] == "completed"
            warnings = done["metadata"].get("subject_kb_warnings") or []
            assert any(item.get("kb_ref") == libs.ref_a for item in warnings)
            assert any(item.get("code") == "kb_not_ready" for item in warnings)
            assert _result(events)["metadata"]["response"] == "NO-FALLBACK"
            blob = json.dumps(events, ensure_ascii=False)
            assert "GLOBAL-ONLY" not in blob and "B-ONLY" not in blob
            assert any(
                "scope_forbidden" in json.dumps(item, ensure_ascii=False)
                or "kb_not_ready" in json.dumps(item, ensure_ascii=False)
                for item in _tool_results(events)
            )

            # 同 socket 合法恢复请求（无工具、无科目）仍可完成。
            recovered = _turn(
                websocket,
                {
                    "content": "恢复",
                    "session_id": _session_id(events),
                    "subject_id": None,
                    "tools": [],
                    "config": {},
                },
            )
            assert _done(recovered)["metadata"]["status"] == "completed"
            assert _result(recovered)["metadata"]["response"] == "RECOVERED"
    assert client.calls


def test_w3_ws_terminal_failure_is_linked_and_socket_stays_usable(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _ExplodingClient:
        def __init__(self) -> None:
            owner = self
            self.calls = 0

            class _Completions:
                async def create(self, **_kwargs):
                    owner.calls += 1
                    raise subject_errors.subject_error(
                        subject_errors.ErrorCode.INTERNAL_ERROR
                    )

            class _Chat:
                completions = _Completions()

            self.chat = _Chat()

        async def aclose(self) -> None:
            return None

    exploding = _ExplodingClient()
    monkeypatch.setattr(AgenticChatPipeline, "_build_openai_client", lambda self: exploding)

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {
                    "content": "触发终端失败",
                    "session_id": None,
                    "subject_id": None,
                    "tools": [],
                    "config": {},
                },
            )
            error = next(event for event in events if event.get("type") == "error")
            done = _done(events)
            assert error["metadata"]["turn_terminal"] is True
            assert error["metadata"]["status"] == "failed"
            assert done["metadata"]["status"] == "failed"
            assert error["turn_id"] and done["turn_id"] == error["turn_id"]
            assert error["session_id"] == done["session_id"]
            assert error["content"] == subject_errors.ERROR_SPECS[
                subject_errors.ErrorCode.INTERNAL_ERROR
            ].message
            websocket.send_json({"type": "ping"})
            assert _receive_until(websocket, ("pong",), limit=10)[-1]["type"] == "pong"


def _runtime():
    from deeptutor.services.session import get_turn_runtime_manager

    return get_turn_runtime_manager()


# ---------------------------------------------------------------------------
# W4 — 真实图片描述文本节点、真实索引/检索、来源仍指原文档
# ---------------------------------------------------------------------------
def _png_payload(marker_color: tuple[int, int, int] = (20, 90, 160)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), marker_color).save(buffer, format="PNG", compress_level=0)
    data = buffer.getvalue()
    return data + b"\x00" * (1200 - len(data))


def _image_kb(ws_env):
    subject = helpers.make_subject(ws_env.root, "图片科目")
    kb_name = "image-kb"
    kb_dir = Path(subject.knowledge_bases) / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = Path(subject.materials) / "textbook"
    materials.mkdir(parents=True, exist_ok=True)
    for target in (raw / "figure.png", materials / "figure.png"):
        target.write_bytes(_png_payload())
    config = Path(subject.knowledge_bases) / "kb_config.json"
    config.write_text(
        json.dumps(
            {
                "knowledge_bases": {
                    kb_name: {
                        "path": kb_name,
                        "status": "ready",
                        "rag_provider": "llamaindex",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    files = material_manifest.source_files(raw)
    material_manifest.save_manifest(
        kb_dir,
        material_manifest.build_manifest(
            subject_id=subject.subject_id, kb_name=kb_name, files=files
        ),
    )
    material_manifest.save_index_state(
        kb_dir,
        {
            "schema_version": material_manifest.INDEX_STATE_SCHEMA_VERSION,
            "subject_id": subject.subject_id,
            "kb_name": kb_name,
            "status": "ready",
            "fingerprint": material_manifest.fingerprint(files),
            "shape": material_manifest.shape(files),
            "documents": len(files),
            "task_id": None,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": kb_name, "type": "textbook", "documents": 1, "status": "ready"},
    )
    _build_index(subject.knowledge_bases, kb_name, raw / "figure.png")
    return SimpleNamespace(
        subject=subject,
        kb_name=kb_name,
        kb_dir=kb_dir,
        ref=kb_scope.encode_subject_kb_ref(subject.subject_id, kb_name),
        marker="IMAGE-ONLY-3c7a91",
    )


def test_w4_image_description_is_indexed_and_retrieved_with_original_source(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.index_versioning import resolve_storage_dir_for_read
    from deeptutor.services.rag.pipelines.llamaindex import image_description as desc
    from deeptutor.services.rag.pipelines.llamaindex.image_description import (
        CONTENT_KIND,
        DESCRIPTION_PREFIX,
    )

    marker = "IMAGE-ONLY-3c7a91"
    vision = SimpleNamespace(
        model="s14-vision-stub",
        binding="openai",
        api_key="sk-s14-fake-only",
        base_url="http://127.0.0.1:9/v1",
        api_version=None,
        extra_headers=None,
    )
    ws_env.llm.response = f"图中文字为 {marker}，是一条测试曲线。"
    ws_env.llm.finish_reason = "stop"
    monkeypatch.setattr(desc, "get_vision_strategy", lambda: "auto")
    monkeypatch.setattr(desc, "resolve_llm_runtime_config", lambda *a, **k: None)
    monkeypatch.setattr(desc, "resolve_vision_runtime_config", lambda *a, **k: vision)
    monkeypatch.setattr(desc, "supports_vision", lambda *a, **k: False)

    image = _image_kb(ws_env)
    lib = image
    assert image.kb_dir.is_dir()
    # 真实 loader 确实把图片描述作为普通文本节点交给真实索引。
    storage_dir = resolve_storage_dir_for_read(image.kb_dir, None)
    assert storage_dir is not None
    seeded_nodes = llamaindex_storage.retrieve_nodes(storage_dir, marker, top_k=3)
    assert seeded_nodes
    assert any(
        node.node.metadata.get("content_kind") == CONTENT_KIND
        and node.node.metadata.get("file_name") == "figure.png"
        for node in seeded_nodes
    )

    client = _install_client(
        monkeypatch,
        [
            _tool_round("rag", {"query": marker, "kb_name": image.ref}),
            lambda messages: _final(
                "IMAGE-ANSWER:"
                + (
                    re.search(r"IMAGE-ONLY-[0-9a-f]+", json.dumps(messages, ensure_ascii=False))
                    .group(0)
                    if re.search(r"IMAGE-ONLY-[0-9a-f]+", json.dumps(messages, ensure_ascii=False))
                    else "NO-IMAGE-MARKER"
                )
            ),
        ],
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {
                    "content": "图里写了什么？",
                    "session_id": None,
                    "subject_id": image.subject.subject_id,
                    "tools": ["rag"],
                    "config": {},
                },
            )
            assert _done(events)["metadata"]["status"] == "completed"
            assert _result(events)["metadata"]["response"].startswith("IMAGE-ANSWER:IMAGE-ONLY-3c7a91")
            sources = _sources(events)
            image_sources = [
                source
                for source in sources
                if source.get("title") == "figure.png"
            ]
            assert image_sources
            source = image_sources[0]
            assert source.get("source") == "raw/figure.png"
            assert source.get("page") in ("", None)
            assert "asset" not in json.dumps(source, ensure_ascii=False).lower()
            assert str(image.kb_dir) not in json.dumps(events, ensure_ascii=False)
            tool_results = _tool_results(events)
            assert any((item.get("metadata") or {}).get("tool") == "rag" for item in tool_results)

    nodes = llamaindex_storage.retrieve_nodes(storage_dir, marker, top_k=3)
    hits = [
        node.node
        for node in nodes
        if node.node.metadata.get("content_kind") == CONTENT_KIND
    ]
    assert hits
    hit = hits[0]
    assert marker in hit.get_content()
    assert hit.get_content().startswith(DESCRIPTION_PREFIX)
    assert hit.metadata["file_name"] == "figure.png"
    assert hit.metadata["asset_ref"] == "figure.png"
    assert "page" not in hit.metadata
    assert "base64" not in json.dumps(hit.metadata)
    assert client.calls
    # 真实 loader 的 vision 路径确实发生了（不是只把现成文本塞进索引）。
    assert ws_env.llm.call_count >= 1


# ---------------------------------------------------------------------------
# W5 — PageIndex outline 与取消/重订阅生命周期
# ---------------------------------------------------------------------------
class _PageIndexFake:
    def __init__(self) -> None:
        self.submitted: list[str] = []
        self.get_calls: list[str] = []
        self.tree = {
            "title": "S14 Outline Root",
            "page_index": 1,
            "summary": "S14-OUTLINE-5d2e 这是目录摘要，不是检索到的正文段落。",
            "nodes": [
                {
                    "title": "S14 章节 A",
                    "page_index": 2,
                    "summary": "S14-OUTLINE-5d2e child outline",
                    "node_id": "node-a",
                }
            ],
        }

    async def submit_document(self, path) -> str:
        self.submitted.append(Path(path).name)
        return "doc-s14-outline"

    async def wait_until_ready(self, _doc_id: str):
        return {"status": "completed", "retrieval_ready": True}

    async def get_document(self, doc_id: str, *, summary: bool = False):
        self.get_calls.append(doc_id)
        return {"status": "completed", "result": self.tree}

    async def delete_document(self, _doc_id: str) -> bool:
        return True


def _outline_kb(ws_env):
    subject = helpers.make_subject(ws_env.root, "目录科目")
    kb_name = "outline-kb"
    kb_dir = Path(subject.knowledge_bases) / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = Path(subject.materials) / "textbook"
    materials.mkdir(parents=True, exist_ok=True)
    text = "S14-OUTLINE-5d2e 这是目录源文件。"
    for target in (raw / "paper.txt", materials / "paper.txt"):
        target.write_text(text, encoding="utf-8")
    (Path(subject.knowledge_bases) / "kb_config.json").write_text(
        json.dumps(
            {
                "knowledge_bases": {
                    kb_name: {
                        "path": kb_name,
                        "status": "ready",
                        "rag_provider": "pageindex",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    files = material_manifest.source_files(raw)
    material_manifest.save_manifest(
        kb_dir,
        material_manifest.build_manifest(
            subject_id=subject.subject_id, kb_name=kb_name, files=files
        ),
    )
    material_manifest.save_index_state(
        kb_dir,
        {
            "schema_version": material_manifest.INDEX_STATE_SCHEMA_VERSION,
            "subject_id": subject.subject_id,
            "kb_name": kb_name,
            "status": "ready",
            "fingerprint": material_manifest.fingerprint(files),
            "shape": material_manifest.shape(files),
            "documents": len(files),
            "task_id": None,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": kb_name, "type": "textbook", "documents": 1, "status": "ready"},
    )
    fake = _PageIndexFake()

    async def initialize() -> None:
        pipeline = PageIndexPipeline(
            kb_base_dir=str(subject.knowledge_bases), client=fake
        )
        assert await pipeline.initialize(kb_name, [str(raw / "paper.txt")]) is True
        assert pipeline.document_map(kb_name) == {"paper.txt": "doc-s14-outline"}

    asyncio.run(initialize())
    return SimpleNamespace(
        subject=subject,
        kb_name=kb_name,
        kb_dir=kb_dir,
        ref=kb_scope.encode_subject_kb_ref(subject.subject_id, kb_name),
        fake=fake,
    )


def test_w5_pageindex_outline_is_real_outline_not_mcp_or_passage(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    outline = _outline_kb(ws_env)
    fake = outline.fake
    monkeypatch.setattr(PageIndexPipeline, "_get_client", lambda self: fake)
    client = _install_client(
        monkeypatch,
        [
            _tool_round("rag", {"query": "outline", "kb_name": outline.ref}),
            lambda messages: _final(
                "OUTLINE-ANSWER:"
                + (
                    re.search(r"S14-OUTLINE-[0-9a-f]+", json.dumps(messages, ensure_ascii=False))
                    .group(0)
                    if re.search(
                        r"S14-OUTLINE-[0-9a-f]+", json.dumps(messages, ensure_ascii=False)
                    )
                    else "NO-OUTLINE"
                )
            ),
        ],
    )

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {
                    "content": "用目录库",
                    "session_id": None,
                    "subject_id": outline.subject.subject_id,
                    "tools": ["rag"],
                    "config": {},
                },
            )
            assert _done(events)["metadata"]["status"] == "completed"
            assert _result(events)["metadata"]["response"].startswith(
                "OUTLINE-ANSWER:S14-OUTLINE-5d2e"
            )
            sources = _sources(events)
            outline_sources = [
                source for source in sources if source.get("title") == "S14 Outline Root"
            ]
            assert outline_sources
            source = outline_sources[0]
            assert source.get("page") == 1
            assert source.get("source") == "paper.txt"
            assert "S14-OUTLINE-5d2e" in (source.get("content") or "")
            tool_results = _tool_results(events)
            outline_result = next(
                item
                for item in tool_results
                if (item.get("metadata") or {}).get("tool_metadata", {}).get("retrieval_kind")
                == "outline"
            )
            assert outline_result["metadata"]["tool_metadata"]["retrieval_kind"] == "outline"
            assert "passage" not in json.dumps(outline_result, ensure_ascii=False).lower()
            assert "mcp" not in json.dumps(outline_result, ensure_ascii=False).lower()
            names = {
                (item.get("function") or {}).get("name")
                for call in client.calls
                for item in (call.get("tools") or [])
                if isinstance(item, dict)
            }
            assert "rag" in names
            assert not any(name and "mcp" in name.lower() for name in names)
    assert fake.submitted == ["paper.txt"]
    assert fake.get_calls and set(fake.get_calls) == {"doc-s14-outline"}


class _BlockingClient:
    def __init__(self) -> None:
        self.calls = 0
        self.entered = threading.Event()

    async def _create(self, **_kwargs):
        self.calls += 1
        self.entered.set()
        await asyncio.sleep(3600)

    async def aclose(self) -> None:
        return None


def _blocking_client() -> _BlockingClient:
    client = _BlockingClient()

    class _Completions:
        async def create(self, **kwargs):
            return await client._create(**kwargs)

    class _Chat:
        completions = _Completions()

    client.chat = _Chat()
    return client


def test_w5_cancel_and_disconnect_resubscribe_have_one_terminal_and_no_leak(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = helpers.make_subject(ws_env.root, "生命周期科目")
    blocking = _blocking_client()
    monkeypatch.setattr(AgenticChatPipeline, "_build_openai_client", lambda self: blocking)

    with TestClient(_app()) as test_client:
        with test_client.websocket_connect(ROUTE) as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "开始一个会被取消的轮次",
                    "session_id": None,
                    "subject_id": helper.subject_id,
                    "tools": [],
                    "config": {},
                }
            )
            initial = _receive_until(websocket, ("session",))
            session_id = _session_id(initial)
            turn_id = next(
                event["turn_id"] for event in initial if event.get("turn_id")
            )
            assert turn_id
            assert blocking.entered.wait(timeout=5), "turn never reached the model boundary"

        # 断线不取消后端 turn；新 socket 从 seq 0 重订阅后显式取消。
        with test_client.websocket_connect(ROUTE) as websocket:
            websocket.send_json(
                {"type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0}
            )
            replay = _receive_until(websocket, ("session",), limit=30)
            assert any(event.get("turn_id") == turn_id for event in replay)
            websocket.send_json({"type": "cancel_turn", "turn_id": turn_id})
            cancelled = _receive_until(websocket, ("done", "error"))
            done_events = [event for event in cancelled if event.get("type") == "done"]
            assert len(done_events) == 1
            cancelled_done = done_events[0]
            assert cancelled_done["metadata"]["status"] == "cancelled"
            assert cancelled_done["turn_id"] == turn_id

        assert _portal(test_client, _runtime().has_live_execution, turn_id) is False
        before_replay = _portal(test_client, _runtime().store.get_messages, session_id)
        partial = [item for item in before_replay if item["role"] == "assistant"]
        # Cancellation preserves an existing process trace, even before the
        # blocked model has produced answer text. It must not duplicate it.
        assert len(partial) <= 1
        assert all(not item["content"] and item.get("events") for item in partial)

        # 终态后再订阅：只回放一份终态，seq 单调且无重复。
        with test_client.websocket_connect(ROUTE) as websocket:
            websocket.send_json(
                {"type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0}
            )
            replay2 = _receive_until(websocket, ("done", "error"))
            done2 = [event for event in replay2 if event.get("type") == "done"]
            assert len(done2) == 1
            assert done2[0]["seq"] == cancelled_done["seq"]
            seqs = [event["seq"] for event in replay2 if isinstance(event.get("seq"), int)]
            assert seqs == sorted(set(seqs))
            assert len([event for event in replay2 if event.get("type") == "done"]) == 1

        live = _portal(test_client, _runtime().has_live_execution, turn_id)
        assert live is False
        deadline = time.monotonic() + 3
        persisted_turn = None
        while time.monotonic() < deadline:
            persisted_turn = _portal(test_client, _runtime().store.get_turn, turn_id)
            if persisted_turn is not None and persisted_turn["status"] != "running":
                break
            time.sleep(0.02)
        assert persisted_turn is not None
        assert persisted_turn["status"] == "cancelled", (
            "cancelled turn is no longer live but its persisted row is still "
            f"{persisted_turn['status']!r}: cancellation cleanup did not reach "
            "update_turn_status"
        )
        messages = _portal(test_client, _runtime().store.get_messages, session_id)
        assert messages == before_replay

    assert blocking.calls == 1


def test_w5_cancel_after_done_keeps_completed_reply_and_one_terminal(
    ws_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()

    async def blocked_title(**_kwargs):
        entered.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(_runtime(), "_maybe_generate_session_title", blocked_title)
    _install_client(monkeypatch, [_final("S14-COMPLETED-BEFORE-TITLE")])
    with TestClient(_app()) as client:
        with client.websocket_connect(ROUTE) as websocket:
            events = _turn(
                websocket,
                {"content": "finish first", "session_id": None, "tools": [], "config": {}},
            )
            done = _done(events)
            assert done["metadata"]["status"] == "completed"
            turn_id, session_id = done["turn_id"], _session_id(events)
            assert entered.wait(timeout=5)
            before = _portal(client, _runtime().store.get_messages, session_id)
            assert _portal(client, _runtime().cancel_turn, turn_id) is True
        assert _portal(client, _runtime().store.get_turn, turn_id)["status"] == "completed"
        assert not _portal(client, _runtime().has_live_execution, turn_id)
        assert _portal(client, _runtime().store.get_messages, session_id) == before
        assistants = [item for item in before if item["role"] == "assistant"]
        assert len(assistants) == 1
        assert assistants[0]["content"] == "S14-COMPLETED-BEFORE-TITLE"
        persisted = _portal(client, _runtime().store.get_turn_events, turn_id)
        assert [event["seq"] for event in persisted if event["type"] == "done"] == [done["seq"]]


FORMAL_APP_PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
os.chdir(repo)
owner = tempfile.TemporaryDirectory(prefix="s14-formal-app-")
home = Path(owner.name)
for name in tuple(os.environ):
    if "API_KEY" in name or name.startswith(("OPENAI_", "ANTHROPIC_", "CODEBUDDY_", "DEEPTUTOR_CODEBUDDY_")):
        os.environ.pop(name, None)
os.environ["DEEPTUTOR_HOME"] = str(home)
os.environ["HOME"] = str(home)
os.environ["XDG_CONFIG_HOME"] = str(home / "xdg-config")
os.environ["XDG_CACHE_HOME"] = str(home / "xdg-cache")
os.environ["XDG_DATA_HOME"] = str(home / "xdg-data")
os.environ["DEEPTUTOR_CODEBUDDY_AUTH_FILE"] = str(home / "missing-auth.json")
result = {"home": str(home)}
try:
    from tests.phase1.helpers import block_external_network
    with block_external_network():
        from deeptutor.services.setup.init import init_user_directories
        from deeptutor.services.config import ensure_runtime_settings_files
        init_user_directories()
        ensure_runtime_settings_files()
        from fastapi.testclient import TestClient
        from deeptutor.api.main import app
        with TestClient(app) as client:
            from deeptutor.services.cron.service import get_cron_service
            from deeptutor.events.event_bus import get_event_bus
            cron, bus = get_cron_service(), get_event_bus()
            result["cron_under_tmp"] = cron.store_path.is_relative_to(home)
            response = client.get("/api/v1/subjects")
            result["subjects_status"] = response.status_code
            with client.websocket_connect("/api/v1/ws") as websocket:
                websocket.send_json({"type": "ping"})
                pong = websocket.receive_json()
                result["pong"] = pong.get("type") == "pong"
        result["shutdown_ok"] = (
            not cron._running and cron._timer_task is None
            and not bus._running and bus._processor_task.done()
        )
    result["ok"] = True
except Exception as exc:
    result["ok"] = False
    result["error"] = f"{type(exc).__name__}: {exc}"
finally:
    owner.cleanup()
result["home_removed"] = not home.exists()
print(json.dumps(result, ensure_ascii=False))
'''


def test_formal_app_registers_http_and_ws_with_real_lifespan() -> None:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-c", FORMAL_APP_PROBE, str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(repo),
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1]) if lines else {}
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert payload.get("ok") is True, payload
    assert payload.get("subjects_status") == 200
    assert payload.get("pong") is True
    assert payload.get("cron_under_tmp") is True
    assert payload.get("shutdown_ok") is True
    assert payload.get("home_removed") is True
