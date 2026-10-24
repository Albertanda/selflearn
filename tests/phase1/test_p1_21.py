"""P1-21 行为测试：会话科目三态、原始轮次快照与运行投影（C08/C02）。

目标：省略沿用本 session、``null``/``""`` 明确清空、非空合法值设置；两个位置冲突
拒绝；校验发生在任何写入之前；retry/regenerate 用**原请求快照**而不是当前偏好；
拒绝路径不留伪轮次、不删旧 assistant。

必证场景（对应卡内清单）：

* 省略/null/""/值四种输入 → preferences、request_snapshot、运行 metadata 一致；
* 冲突（顶层 vs config）与非字符串/非法 slug 拒绝，且 turn/message/preferences 无写入；
* 新 session 不继承另一 session 的科目；
* 原快照 A/None 与"当前偏好 B"的 regenerate 仍按原 scope；
* 被删科目在删除旧 assistant/写偏好/建 turn 之前拒绝；
* SQLite 与另一个 store 实现投影相同的三态。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager, resolve_subject_scope
from deeptutor.subjects import json_store
from deeptutor.subjects import store as subject_store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers

CAPABILITY = "chat"


async def _noop_async(*_args, **_kwargs):
    return None


class _FakeContextBuilder:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def build(self, **_kwargs):
        return SimpleNamespace(
            conversation_history=[],
            conversation_summary="",
            context_text="",
            token_count=0,
            budget=0,
        )


class _CapturingOrchestrator:
    """记录真实 UnifiedContext 的运行 metadata，然后确定性地结束这一轮。"""

    captured: dict = {}

    async def handle(self, context):
        type(self).captured = {
            "metadata": dict(context.metadata or {}),
            "user_message": context.user_message,
            "knowledge_bases": list(context.knowledge_bases or []),
        }
        from deeptutor.core.stream import StreamEvent, StreamEventType

        yield StreamEvent(
            type=StreamEventType.CONTENT,
            source="chat",
            stage="responding",
            content="ok",
            metadata={"call_kind": "llm_final_response"},
        )
        yield StreamEvent(type=StreamEventType.DONE, source="chat")


def _fake_skill_service() -> SimpleNamespace:
    return SimpleNamespace(
        summary_entries=lambda: [],
        load_always_for_context=lambda: "",
        load_for_context=lambda _skills: "",
        list_skills=lambda: [],
    )


def _fake_persona_service() -> SimpleNamespace:
    return SimpleNamespace(load_for_context=lambda name: "")


@pytest.fixture
def runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, p1_runtime: Path):
    """真实 TurnRuntimeManager + 真实 SQLite store，只把外部服务换成替身。"""
    store = SQLiteSessionStore(db_path=tmp_path / "p1-21.db")
    runtime = TurnRuntimeManager(store)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        "deeptutor.services.session.context_builder.ContextBuilder", _FakeContextBuilder
    )
    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.ChatOrchestrator", _CapturingOrchestrator
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_store",
        lambda: SimpleNamespace(read_l3_concat=lambda: "", emit=_noop_async),
    )
    monkeypatch.setattr("deeptutor.services.skill.get_skill_service", _fake_skill_service)
    monkeypatch.setattr("deeptutor.services.persona.get_persona_service", _fake_persona_service)
    # 会话标题生成与本卡无关，而且会去碰真实模型配置；这一轮只验证 scope 投影。
    monkeypatch.setattr(
        runtime, "_maybe_generate_session_title", lambda *_a, **_k: _noop_async()
    )
    return SimpleNamespace(
        store=store, runtime=runtime, admin_root=p1_runtime, db_path=tmp_path / "p1-21.db"
    )


def _turn_count(runtime_env, session_id: str) -> int:
    """直接数真实 turns 表：证明被拒的请求没有留下"伪轮次"。"""
    with sqlite3.connect(runtime_env.db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)
        ).fetchone()
    return int(row[0])


async def _drain(runtime: TurnRuntimeManager, turn_id: str) -> list[dict]:
    events = []
    async for event in runtime.subscribe_turn(turn_id, after_seq=0):
        events.append(event)
    return events


async def _turn(runtime_env, payload: dict) -> tuple[dict, dict]:
    session, turn = await runtime_env.runtime.start_turn(payload)
    await _drain(runtime_env.runtime, turn["id"])
    return session, turn


#: 快照里根本没有 scope 键（旧历史）——与"明确 null"必须区分开。
_ABSENT = object()


async def _snapshot_subject(runtime_env, session_id: str) -> object:
    """**最后一条**用户消息快照里的 subject_id（regenerate 依据的那一条）。"""
    detail = await runtime_env.store.get_session_with_messages(session_id)
    for message in reversed(detail["messages"]):
        if message["role"] == "user":
            snapshot = (message.get("metadata") or {}).get("request_snapshot") or {}
            return snapshot.get("subject_id", _ABSENT)
    raise AssertionError("no user message")


async def _preference(runtime_env, session_id: str) -> object:
    session = await runtime_env.store.get_session(session_id)
    return (session.get("preferences") or {}).get("subject_id", "<missing>")


def _session_counts(detail: dict) -> tuple[int, int]:
    roles = [message["role"] for message in detail["messages"]]
    return roles.count("user"), roles.count("assistant")


# ---------------------------------------------------------------------------
# 三态
# ---------------------------------------------------------------------------
def test_omitted_keeps_null_clears_and_a_value_sets(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")
    subject_b = helpers.make_subject(runtime_env.admin_root, "科目B")
    a, b = subject_a.subject_id, subject_b.subject_id

    async def scenario() -> None:
        _session, turn = await _turn(
            runtime_env,
            {
                "content": "one",
                "capability": CAPABILITY,
                "subject_id": a,
                "config": {},
            },
        )
        session_id = turn["session_id"]
        assert await _preference(runtime_env, session_id) == a
        assert await _snapshot_subject(runtime_env, session_id) == a
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] == a

        # 省略：沿用本 session 的科目（不是 None，也不是别的科）。
        _session, turn2 = await _turn(
            runtime_env,
            {"content": "two", "capability": CAPABILITY, "session_id": session_id, "config": {}},
        )
        assert turn2["session_id"] == session_id
        assert await _preference(runtime_env, session_id) == a
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] == a

        # 兼容位置（config.subject_id）也能设置。
        _session, _turn3 = await _turn(
            runtime_env,
            {
                "content": "three",
                "capability": CAPABILITY,
                "session_id": session_id,
                "config": {"subject_id": b},
            },
        )
        assert await _preference(runtime_env, session_id) == b

        # null 明确清空。
        _session, _turn4 = await _turn(
            runtime_env,
            {
                "content": "four",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": None,
                "config": {},
            },
        )
        assert await _preference(runtime_env, session_id) is None
        assert await _snapshot_subject(runtime_env, session_id) is None
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] is None

        # 清空之后，再省略也仍然是"无科目"（不会被旧值复活）。
        _session, _turn5 = await _turn(
            runtime_env,
            {"content": "five", "capability": CAPABILITY, "session_id": session_id, "config": {}},
        )
        assert await _preference(runtime_env, session_id) is None
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] is None

        # 空字符串同样明确清空（显式空 = 用户选择了"无科目"）。
        _session, _turn6 = await _turn(
            runtime_env,
            {
                "content": "six",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": a,
                "config": {},
            },
        )
        _session, _turn7 = await _turn(
            runtime_env,
            {
                "content": "seven",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": "",
                "config": {},
            },
        )
        assert await _preference(runtime_env, session_id) is None
        assert await _snapshot_subject(runtime_env, session_id) is None

        # 运行 metadata 记录真实科目上下文 token 数（0 表示没有注入块）。
        assert "subject_context_tokens" in _CapturingOrchestrator.captured["metadata"]

    asyncio.run(scenario())


def test_a_new_session_does_not_inherit_another_sessions_subject(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")

    async def scenario() -> None:
        _session, turn_a = await _turn(
            runtime_env,
            {
                "content": "a",
                "capability": CAPABILITY,
                "subject_id": subject_a.subject_id,
                "config": {},
            },
        )
        assert await _preference(runtime_env, turn_a["session_id"]) == subject_a.subject_id

        _session, turn_b = await _turn(
            runtime_env,
            {"content": "b", "capability": CAPABILITY, "config": {}},
        )
        assert turn_b["session_id"] != turn_a["session_id"]
        assert await _preference(runtime_env, turn_b["session_id"]) is None
        assert await _snapshot_subject(runtime_env, turn_b["session_id"]) is None

    asyncio.run(scenario())


def test_conflicts_and_bad_values_are_refused_without_any_write(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")
    subject_b = helpers.make_subject(runtime_env.admin_root, "科目B")

    async def scenario() -> None:
        session = await runtime_env.store.create_session()
        session_id = session["id"]
        await runtime_env.store.update_session_preferences(
            session_id, {"subject_id": subject_a.subject_id}
        )
        before = await runtime_env.store.get_session_with_messages(session_id)
        turns_before = _turn_count(runtime_env, session_id)

        bad_payloads = [
            # 两个位置都给了不同的值：拒绝，不让其中一个悄悄胜出。
            {"subject_id": subject_a.subject_id, "config": {"subject_id": subject_b.subject_id}},
            {"subject_id": subject_b.subject_id, "config": {"subject_id": subject_a.subject_id}},
            # 非法类型。
            {"subject_id": 7, "config": {}},
            {"subject_id": ["a"], "config": {}},
            {"subject_id": {"id": "a"}, "config": {}},
            {"subject_id": True, "config": {}},
            # 非法 slug（分隔符/空白/百分号/控制符/大小写折叠不改写身份）。
            {"subject_id": "../科目a", "config": {}},
            {"subject_id": "科目 a", "config": {}},
            {"subject_id": "科目%41", "config": {}},
            {"subject_id": "科目a\x07", "config": {}},
            {"config": {"subject_id": 7}},
        ]
        for extra in bad_payloads:
            payload = {"content": "x", "capability": CAPABILITY, "session_id": session_id, **extra}
            with pytest.raises(SubjectOperationError) as excinfo:
                await runtime_env.runtime.start_turn(payload)
            assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value, extra
            assert excinfo.value.http_status == 400

        # 合法 slug 但不存在（或不属于当前用户）→ 404，且同样不写入。
        with pytest.raises(SubjectOperationError) as excinfo:
            await runtime_env.runtime.start_turn(
                {
                    "content": "x",
                    "capability": CAPABILITY,
                    "session_id": session_id,
                    "subject_id": "不存在的科目",
                    "config": {},
                }
            )
        assert excinfo.value.code.value == ErrorCode.SUBJECT_NOT_FOUND.value
        assert excinfo.value.http_status == 404

        after = await runtime_env.store.get_session_with_messages(session_id)
        assert _session_counts(after) == _session_counts(before) == (0, 0)
        assert after["messages"] == before["messages"]
        assert (after.get("preferences") or {}).get("subject_id") == subject_a.subject_id
        assert _turn_count(runtime_env, session_id) == turns_before == 0

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# regenerate / retry 按原快照
# ---------------------------------------------------------------------------
def test_regenerate_reuses_the_original_snapshot_scope_over_the_preference(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")
    subject_b = helpers.make_subject(runtime_env.admin_root, "科目B")

    async def scenario() -> None:
        _session, first = await _turn(
            runtime_env,
            {
                "content": "q1",
                "capability": CAPABILITY,
                "subject_id": subject_a.subject_id,
                "config": {},
            },
        )
        session_id = first["session_id"]
        assert await _snapshot_subject(runtime_env, session_id) == subject_a.subject_id

        # 偏好被改成 B（例如用户在输入框换了科目），但最后一轮用户消息仍是 A。
        await runtime_env.store.update_session_preferences(
            session_id, {"subject_id": subject_b.subject_id}
        )
        _session, regenerated = await runtime_env.runtime.regenerate_last_turn(session_id)
        await _drain(runtime_env.runtime, regenerated["id"])

        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] == subject_a.subject_id
        assert await _snapshot_subject(runtime_env, session_id) == subject_a.subject_id
        assert await _preference(runtime_env, session_id) == subject_a.subject_id

    asyncio.run(scenario())


def test_regenerate_keeps_an_explicit_null_snapshot(runtime_env):
    subject_b = helpers.make_subject(runtime_env.admin_root, "科目B")

    async def scenario() -> None:
        _session, first = await _turn(
            runtime_env,
            {"content": "q1", "capability": CAPABILITY, "config": {}},
        )
        session_id = first["session_id"]
        assert await _snapshot_subject(runtime_env, session_id) is None

        # 之后用户在同一个 session 选了 B。
        await runtime_env.store.update_session_preferences(
            session_id, {"subject_id": subject_b.subject_id}
        )
        _session, regenerated = await runtime_env.runtime.regenerate_last_turn(session_id)
        await _drain(runtime_env.runtime, regenerated["id"])
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] is None
        assert await _snapshot_subject(runtime_env, session_id) is None

        # 旧历史（快照里根本没有 scope 键）按"无科目"处理，也不猜当前偏好。
        legacy_session = await runtime_env.store.create_session()
        legacy_id = legacy_session["id"]
        await runtime_env.store.add_message(
            legacy_id,
            role="user",
            content="legacy",
            capability=CAPABILITY,
            metadata={"request_snapshot": {"content": "legacy", "capability": CAPABILITY}},
        )
        await runtime_env.store.update_session_preferences(
            legacy_id, {"subject_id": subject_b.subject_id}
        )
        _session, legacy_turn = await runtime_env.runtime.regenerate_last_turn(legacy_id)
        await _drain(runtime_env.runtime, legacy_turn["id"])
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] is None
        # 历史消息本身不被改写：它仍然没有 scope 键，但这一轮按"无科目"重放。
        assert await _snapshot_subject(runtime_env, legacy_id) is _ABSENT
        assert await _preference(runtime_env, legacy_id) is None

    asyncio.run(scenario())


def test_regenerate_refuses_a_deleted_subject_before_touching_history(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")

    async def scenario() -> None:
        _session, first = await _turn(
            runtime_env,
            {
                "content": "q1",
                "capability": CAPABILITY,
                "subject_id": subject_a.subject_id,
                "config": {},
            },
        )
        session_id = first["session_id"]
        before = await runtime_env.store.get_session_with_messages(session_id)
        user_before, assistant_before = _session_counts(before)
        assert (user_before, assistant_before) == (1, 1)
        assistant_id = [m["id"] for m in before["messages"] if m["role"] == "assistant"][0]

        assert subject_store.delete_subject(subject_a.subject_id) is True
        turns_before = _turn_count(runtime_env, session_id)

        with pytest.raises(SubjectOperationError) as excinfo:
            await runtime_env.runtime.regenerate_last_turn(session_id)
        assert excinfo.value.code.value == ErrorCode.SUBJECT_NOT_FOUND.value
        assert excinfo.value.http_status == 404

        after = await runtime_env.store.get_session_with_messages(session_id)
        ids_after = [m["id"] for m in after["messages"]]
        assert assistant_id in ids_after, "校验失败前删掉了旧 assistant"
        assert _session_counts(after) == (user_before, assistant_before)
        assert _turn_count(runtime_env, session_id) == turns_before
        assert await _preference(runtime_env, session_id) == subject_a.subject_id

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# store 无关的三态投影
# ---------------------------------------------------------------------------
class _MemoryStore:
    """最小 store 替身：只实现三态需要的读写，其余显式报错而不是静默。"""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._seq = 0

    def _row(self, session_id: str) -> dict:
        return self._sessions[session_id]

    async def create_session(self, **_kwargs) -> dict:
        self._seq += 1
        session_id = f"mem-{self._seq}"
        self._sessions[session_id] = {"id": session_id, "preferences": {}}
        return dict(self._sessions[session_id])

    async def ensure_session(self, session_id=None) -> dict:
        if session_id and session_id in self._sessions:
            return dict(self._row(session_id))
        return await self.create_session()

    async def get_session(self, session_id: str):
        row = self._sessions.get(session_id)
        return dict(row) if row is not None else None

    async def update_session_preferences(self, session_id: str, preferences: dict) -> dict:
        row = self._row(session_id)
        merged = dict(row.get("preferences") or {})
        merged.update(preferences)
        row["preferences"] = merged
        return dict(merged)

    async def create_turn(self, session_id: str, **kwargs):  # pragma: no cover - guard
        raise AssertionError("三态解析不应走到 create_turn")

    def __getattr__(self, name: str):  # pragma: no cover - guard
        raise AssertionError(f"fake store 未被授权的方法: {name}")


def test_both_stores_project_the_same_subject_scope(runtime_env):
    subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")
    a = subject_a.subject_id

    async def scenario() -> None:
        sqlite = runtime_env.store
        memory = _MemoryStore()
        sqlite_session = await sqlite.create_session()
        memory_session = await memory.create_session()
        requests = [None, "", "   ", a, "不存在的科目", "../x", 7]

        for request in requests:
            for store, session_id in (
                (sqlite, sqlite_session["id"]),
                (memory, memory_session["id"]),
            ):
                await store.update_session_preferences(
                    session_id, {"subject_id": request if request in (None, "", a) else None}
                )
            stored_sqlite = await _preference(runtime_env, sqlite_session["id"])
            stored_memory = (await memory.get_session(memory_session["id"]))["preferences"][
                "subject_id"
            ]
            assert stored_sqlite == stored_memory, request

            results = []
            for stored in (stored_sqlite, stored_memory):
                try:
                    results.append(("ok", resolve_subject_scope(request, stored)))
                except SubjectOperationError as exc:
                    results.append(("error", exc.code.value))
            assert results[0] == results[1], request

        # 真实 SQLite 也必须原样保存显式 None（不能被当成"没设置"丢掉）。
        await sqlite.update_session_preferences(sqlite_session["id"], {"subject_id": None})
        assert await _preference(runtime_env, sqlite_session["id"]) is None
        await memory.update_session_preferences(memory_session["id"], {"subject_id": None})
        assert (await memory.get_session(memory_session["id"]))["preferences"]["subject_id"] is None

        # 冲突在任何 store 上都在写入之前失败。
        for store in (sqlite, memory):
            with pytest.raises(SubjectOperationError) as excinfo:
                await runtime_env.runtime.start_turn(
                    {
                        "content": "x",
                        "capability": CAPABILITY,
                        "session_id": (
                            sqlite_session["id"] if store is sqlite else memory_session["id"]
                        ),
                        "subject_id": a,
                        "config": {"subject_id": "另一个科"},
                    }
                )
            assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value
        assert await _preference(runtime_env, sqlite_session["id"]) is None
        assert (await memory.get_session(memory_session["id"]))["preferences"]["subject_id"] is None

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# R2：两个显式位置的**原输入**比较
# ---------------------------------------------------------------------------
def _requested(top, nested):
    from deeptutor.services.session.turn_runtime import _requested_subject

    payload = {} if top is Ellipsis else {"subject_id": top}
    config = {} if nested is Ellipsis else {"subject_id": nested}
    return _requested_subject(payload, config)


@pytest.mark.parametrize(
    "top,nested",
    [
        (None, ""),
        ("", None),
        ("", "   "),
        ("   ", ""),
        ("科目a", "科目a "),
        (None, "科目a"),
    ],
)
def test_two_explicit_carriers_compare_their_raw_values(top, nested):
    """``None``/``""``/空白是**不同**的显式请求，不能归一化后掩盖冲突。"""
    with pytest.raises(json_store.InvalidInputError) as excinfo:
        _requested(top, nested)
    assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value


@pytest.mark.parametrize(
    "top,nested,expected",
    [
        (None, None, None),
        ("", "", None),
        ("   ", "   ", None),
        ("科目a", "科目a", "科目a"),
    ],
)
def test_identical_raw_carriers_are_accepted(top, nested, expected):
    """相同原输入是同一个请求（含两个显式清空 → 归一化为 None）。"""
    assert _requested(top, nested) == expected


def test_one_carrier_only_is_never_a_conflict():
    assert _requested("科目a", Ellipsis) == "科目a"
    assert _requested(Ellipsis, "科目a") == "科目a"
    assert _requested("", Ellipsis) is None
    assert _requested(None, Ellipsis) is None
    assert _requested(Ellipsis, Ellipsis) is not None  # ABSENT sentinel


# ---------------------------------------------------------------------------
# R2：regenerate 重放原挂载（而非当前偏好），并在破坏性操作前校验
# ---------------------------------------------------------------------------
def _global_kb(admin_root: Path, kb_name: str, marker: str) -> Path:
    base = helpers.global_kb_root(admin_root)
    kb_dir = base / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
    config = base / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if config.is_file():
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "llamaindex",
    }
    config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kb_dir


def test_regenerate_replays_the_original_explicit_mounts(runtime_env):
    """原快照里的显式挂载被重放；后来保存的偏好不能顶替它。"""

    async def scenario() -> None:
        admin_root = runtime_env.admin_root
        subject = helpers.make_subject(admin_root, "科目A")
        _global_kb(admin_root, "old-kb", "old")
        _global_kb(admin_root, "new-kb", "new")
        session = await runtime_env.store.create_session()
        session_id = session["id"]
        await _turn(
            runtime_env,
            {
                "content": "q1",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": subject.subject_id,
                "knowledge_bases": ["admin:kb:old-kb"],
                "config": {},
            },
        )
        # 偏好被改成另一个库（用户在输入框换了选择）。
        await runtime_env.store.update_session_preferences(
            session_id, {"knowledge_bases": ["admin:kb:new-kb"]}
        )
        _session, regenerated = await runtime_env.runtime.regenerate_last_turn(session_id)
        await _drain(runtime_env.runtime, regenerated["id"])

        mounted = _CapturingOrchestrator.captured["knowledge_bases"]
        assert "admin:kb:old-kb" in mounted
        assert "admin:kb:new-kb" not in mounted

    asyncio.run(scenario())


def test_regenerate_replays_an_explicit_empty_mount_list(runtime_env):
    """快照里的空列表是"本轮没挂库"，不是"沿用当前偏好"。"""

    async def scenario() -> None:
        admin_root = runtime_env.admin_root
        subject = helpers.make_subject(admin_root, "科目A")
        _global_kb(admin_root, "late-kb", "late")
        session = await runtime_env.store.create_session()
        session_id = session["id"]
        await _turn(
            runtime_env,
            {
                "content": "q1",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": subject.subject_id,
                "knowledge_bases": [],
                "config": {},
            },
        )
        await runtime_env.store.update_session_preferences(
            session_id, {"knowledge_bases": ["admin:kb:late-kb"]}
        )
        _session, regenerated = await runtime_env.runtime.regenerate_last_turn(session_id)
        await _drain(runtime_env.runtime, regenerated["id"])

        assert _CapturingOrchestrator.captured["knowledge_bases"] == []

    asyncio.run(scenario())


def test_regenerate_validates_the_replayed_mounts_before_deleting(runtime_env):
    """原挂载已不可用（库被删除）→ 在删除旧 assistant 之前拒绝，偏好不变。"""

    async def scenario() -> None:
        admin_root = runtime_env.admin_root
        subject = helpers.make_subject(admin_root, "科目A")
        kb_dir = _global_kb(admin_root, "gone-kb", "gone")
        session = await runtime_env.store.create_session()
        session_id = session["id"]
        await _turn(
            runtime_env,
            {
                "content": "q1",
                "capability": CAPABILITY,
                "session_id": session_id,
                "subject_id": subject.subject_id,
                "knowledge_bases": ["admin:kb:gone-kb"],
                "config": {},
            },
        )
        before = await runtime_env.store.get_session_with_messages(session_id)
        assert [m["role"] for m in before["messages"]].count("assistant") == 1
        preferences_before = dict(
            (await runtime_env.store.get_session(session_id)).get("preferences") or {}
        )

        # 库从盘上消失（并撤销登记），但请求快照仍指向它。
        import shutil

        shutil.rmtree(kb_dir)
        config = helpers.global_kb_root(admin_root) / "kb_config.json"
        payload = json.loads(config.read_text(encoding="utf-8"))
        payload["knowledge_bases"].pop("gone-kb", None)
        config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(SubjectOperationError) as excinfo:
            await runtime_env.runtime.regenerate_last_turn(session_id)
        assert excinfo.value.code.value in {
            ErrorCode.KB_NOT_FOUND.value,
            ErrorCode.KB_NOT_READY.value,
        }

        after = await runtime_env.store.get_session_with_messages(session_id)
        assert after["messages"] == before["messages"]
        preferences_after = dict(
            (await runtime_env.store.get_session(session_id)).get("preferences") or {}
        )
        assert preferences_after == preferences_before

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["legacy_mount", "invalid_config"])
def test_regenerate_rejection_preserves_history_and_preferences(runtime_env, failure):
    async def scenario():
        session = await runtime_env.store.create_session()
        sid = session["id"]
        if failure == "legacy_mount":
            await runtime_env.store.add_message(session_id=sid, role="user", content="old question")
            await runtime_env.store.add_message(
                session_id=sid, role="assistant", content="old answer"
            )
            await runtime_env.store.update_session_preferences(
                sid, {"knowledge_bases": ["subject:kb:other:kb"]}
            )
            overrides = {}
        else:
            await _turn(
                runtime_env,
                {"session_id": sid, "capability": "chat", "content": "hello", "config": {}},
            )
            overrides = {"config": {"unknown-public-field": "bad"}}
        before = await runtime_env.store.get_session_with_messages(sid)
        with pytest.raises((SubjectOperationError, RuntimeError)):
            await runtime_env.runtime.regenerate_last_turn(sid, overrides=overrides)
        after = await runtime_env.store.get_session_with_messages(sid)
        assert after["messages"] == before["messages"], (
            "a rejected regenerate removed the old assistant"
        )
        assert after.get("preferences") == before.get("preferences")

    asyncio.run(scenario())
