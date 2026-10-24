"""P1-22 行为测试：本轮实际挂载的科目库与学期摘要（C08/C06）。

目标：``UnifiedContext.knowledge_bases`` 是"用户显式合法全局 refs + 当前科目全部
ready 的 subject refs"，稳定去重；未 ready 的本科库不挂载但以有界 warning 告知；
学期摘要只包含当前学期；空科目不补默认全局库。

必证场景（对应卡内清单）：

* A 只挂 A 库（B/global 同名库都不出现）；
* 显式 global ref 与 subject ref 可共存、不重复（两种写法同一个库只挂一次）；
* 空科目/无挂载不追加默认全局库；
* 多个 ready 库全部挂入（不只第一个）；
* 未 ready 库不挂载、warning 含 kb_ref/status 且出现在 DONE metadata；
* term 只过滤当前学期；term 为空时不注入"本学期"摘要并说明未设置学期；
* 显式引用不存在/越科 → 拒绝（不回落到同名库）；坏 kb_config → 固定安全错误。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.subjects import exam_points, kb_scope, store, uploads
from deeptutor.subjects import material_manifest as manifest_mod
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers

CAPABILITY = "chat"
KB_NAME = "shared-kb"
KB_TYPE = "assignment"
GLOBAL_KB = "global-kb"


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
    """把真实 UnifiedContext 的挂载集合/上下文块/metadata 记下来。"""

    captured: dict = {}

    async def handle(self, context):
        from deeptutor.core.stream import StreamEvent, StreamEventType

        type(self).captured = {
            "knowledge_bases": list(context.knowledge_bases),
            "metadata": dict(context.metadata or {}),
            "history": list(context.conversation_history),
        }
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


@pytest.fixture
def runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, p1_runtime: Path):
    uploads.reset_registry_for_tests()
    store_double = SQLiteSessionStore(db_path=tmp_path / "p1-22.db")
    runtime = TurnRuntimeManager(store_double)
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
    monkeypatch.setattr(
        "deeptutor.services.persona.get_persona_service",
        lambda: SimpleNamespace(load_for_context=lambda _name: ""),
    )
    monkeypatch.setattr(
        runtime, "_maybe_generate_session_title", lambda *_a, **_k: _noop_async()
    )
    try:
        yield SimpleNamespace(store=store_double, runtime=runtime, admin_root=p1_runtime)
    finally:
        uploads.reset_registry_for_tests()


async def _run_turn(runtime_env, payload: dict) -> list[dict]:
    _session, turn = await runtime_env.runtime.start_turn(
        {"capability": CAPABILITY, "content": "hello", "config": {}, **payload}
    )
    events = []
    async for event in runtime_env.runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
    return events


def _turn(runtime_env, payload: dict) -> list[dict]:
    """一个用例只允许一个事件循环：store 的锁绑定在创建它的 loop 上。"""
    return asyncio.run(_run_turn(runtime_env, payload))


def _scenario(coro_factory) -> None:
    asyncio.run(coro_factory())


def _done(events: list[dict]) -> dict:
    return next(event for event in events if event["type"] == "done")


def _subject_block(runtime_env) -> str:
    for message in _CapturingOrchestrator.captured["history"]:
        if message.get("role") == "system":
            return str(message.get("content") or "")
    return ""


# ---------------------------------------------------------------------------
# 夹具：production 形状的 ready 科目库 / 全局库
# ---------------------------------------------------------------------------
def _write_kb_config(subject, entries: dict[str, dict]) -> Path:
    path = Path(subject.knowledge_bases) / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"].update(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _publish_ready(subject, kb_name: str, *, marker: str, kb_type: str = KB_TYPE) -> Path:
    kb_dir = Path(subject.knowledge_bases) / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = Path(subject.materials) / kb_type
    materials.mkdir(parents=True, exist_ok=True)
    name = f"{marker}.txt"
    (raw / name).write_text(f"{marker}\n", encoding="utf-8")
    (materials / name).write_text(f"{marker}\n", encoding="utf-8")
    files = manifest_mod.source_files(raw)
    manifest_mod.save_manifest(
        kb_dir,
        manifest_mod.build_manifest(subject_id=subject.subject_id, kb_name=kb_name, files=files),
    )
    manifest_mod.save_index_state(
        kb_dir,
        {
            "schema_version": manifest_mod.INDEX_STATE_SCHEMA_VERSION,
            "subject_id": subject.subject_id,
            "kb_name": kb_name,
            "status": "ready",
            "fingerprint": manifest_mod.fingerprint(files),
            "shape": manifest_mod.shape(files),
            "documents": len(files),
            "task_id": None,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    return kb_dir


def _make_ready_kb(
    subject, kb_name: str = KB_NAME, *, marker: str | None = None, kb_type: str = KB_TYPE
) -> Path:
    """一个 production 形状的 ready 库。

    每个类型只有一个库（``type`` 决定库名与 materials 子目录），所以同一个科目里
    并存多个 ready 库时必须给它们不同的类型 —— 这也是真实上传路径的形状。
    """
    marker = marker or f"{subject.subject_id}-only"
    kb_dir = _publish_ready(subject, kb_name, marker=marker, kb_type=kb_type)
    _write_kb_config(subject, {kb_name: {"status": "ready", "rag_provider": "llamaindex"}})
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": kb_name, "type": kb_type, "documents": 1, "status": "ready"},
    )
    return kb_dir


def _register_global_kb(admin_root: Path, kb_name: str = GLOBAL_KB, *, marker: str = "global") -> Path:
    base = helpers.global_kb_root(admin_root)
    kb_dir = base / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
    path = base / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "llamaindex",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kb_dir


# ---------------------------------------------------------------------------
# 挂载集合
# ---------------------------------------------------------------------------
def test_a_subject_turn_mounts_only_its_own_same_name_library(runtime_env):
    admin_root = runtime_env.admin_root
    subject_a = helpers.make_subject(admin_root, "科目A")
    subject_b = helpers.make_subject(admin_root, "科目B")
    _make_ready_kb(subject_a, marker="A-only")
    _make_ready_kb(subject_b, marker="B-only")
    _register_global_kb(admin_root, KB_NAME, marker="global-only")

    events = _turn(runtime_env, {"subject_id": subject_a.subject_id})

    expected = [kb_scope.encode_subject_kb_ref(subject_a.subject_id, KB_NAME)]
    assert _CapturingOrchestrator.captured["knowledge_bases"] == expected
    assert kb_scope.encode_subject_kb_ref(subject_b.subject_id, KB_NAME) not in (
        _CapturingOrchestrator.captured["knowledge_bases"]
    )
    assert not any("global" in ref for ref in _CapturingOrchestrator.captured["knowledge_bases"])
    assert _done(events)["metadata"].get("subject_kb_warnings") in (None, [])


def test_every_ready_subject_library_is_mounted_not_just_the_first(runtime_env):
    subject = helpers.make_subject(runtime_env.admin_root, "科目A")
    for name, kb_type in (
        ("kb-one", "assignment"),
        ("kb-two", "textbook"),
        ("kb-three", "ppt"),
    ):
        _make_ready_kb(subject, name, marker=name, kb_type=kb_type)

    _turn(runtime_env, {"subject_id": subject.subject_id})

    mounted = _CapturingOrchestrator.captured["knowledge_bases"]
    assert mounted == [
        kb_scope.encode_subject_kb_ref(subject.subject_id, name)
        for name in ("kb-one", "kb-three", "kb-two")
    ], mounted


def test_explicit_global_and_subject_refs_coexist_without_duplicates(runtime_env):
    admin_root = runtime_env.admin_root
    subject = helpers.make_subject(admin_root, "科目A")
    _make_ready_kb(subject, marker="A-only")
    _register_global_kb(admin_root)

    # 同一全局库的两种写法（裸名与 wire id）都出现时只挂一次。
    _turn(
        runtime_env,
        {
            "subject_id": subject.subject_id,
            "knowledge_bases": [GLOBAL_KB, f"admin:kb:{GLOBAL_KB}"],
        },
    )

    mounted = _CapturingOrchestrator.captured["knowledge_bases"]
    assert mounted == [
        f"admin:kb:{GLOBAL_KB}",
        kb_scope.encode_subject_kb_ref(subject.subject_id, KB_NAME),
    ], mounted
    assert len(mounted) == len(set(mounted))


def test_an_empty_subject_mounts_nothing_and_never_a_default_global(runtime_env):
    admin_root = runtime_env.admin_root
    empty = helpers.make_subject(admin_root, "空科目")
    _register_global_kb(admin_root)  # 存在全局库，但空科目不得自动挂它

    async def scenario() -> None:
        await _run_turn(runtime_env, {"subject_id": empty.subject_id})
        assert _CapturingOrchestrator.captured["knowledge_bases"] == []

        # 完全无科目、无显式挂载：同样什么都不挂。
        await _run_turn(runtime_env, {})
        assert _CapturingOrchestrator.captured["knowledge_bases"] == []
        assert _CapturingOrchestrator.captured["metadata"]["subject_id"] is None

        # 无科目但显式选了全局库：仍然挂载（用户显式选择不受科目影响）。
        await _run_turn(runtime_env, {"knowledge_bases": [GLOBAL_KB]})
        assert _CapturingOrchestrator.captured["knowledge_bases"] == [f"admin:kb:{GLOBAL_KB}"]

    asyncio.run(scenario())


def test_a_not_ready_library_is_not_mounted_and_the_warning_is_visible(runtime_env):
    admin_root = runtime_env.admin_root
    subject = helpers.make_subject(admin_root, "科目A")
    ready_dir = _make_ready_kb(subject, "kb-ready", marker="ready", kb_type="assignment")
    stale_dir = _make_ready_kb(subject, "kb-stale", marker="stale", kb_type="textbook")
    # 让 stale 库的已发布索引落后于当前源：真实 stale，不是"状态缺失"。
    (Path(stale_dir) / "raw" / "stale.txt").write_text("stale changed\n", encoding="utf-8")
    assert ready_dir.exists()

    # 另有一个 registry 说 ready、但没有任何测量结果的库：同样不算 ready。
    _publish_ready(subject, "kb-unknown", marker="unknown", kb_type="ppt")
    manifest_mod.index_state_path(Path(subject.knowledge_bases) / "kb-unknown").unlink()
    _write_kb_config(subject, {"kb-unknown": {"status": "ready"}})
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": "kb-unknown", "type": "ppt", "documents": 1}
    )

    events = _turn(runtime_env, {"subject_id": subject.subject_id})

    mounted = _CapturingOrchestrator.captured["knowledge_bases"]
    assert mounted == [kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-ready")], mounted

    warnings = _done(events)["metadata"]["subject_kb_warnings"]
    by_ref = {item["kb_ref"]: item for item in warnings}
    assert set(by_ref) == {
        kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-stale"),
        kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-unknown"),
    }
    assert by_ref[kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-stale")]["status"] == "stale"
    assert (
        by_ref[kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-unknown")]["status"]
        == "rebuilding"
    )
    for item in warnings:
        assert item["code"] == ErrorCode.KB_NOT_READY.value
        assert item["message"]
    # 上下文里也能核验（不只 DONE）。
    assert _CapturingOrchestrator.captured["metadata"]["subject_kb_warnings"] == warnings
    assert _CapturingOrchestrator.captured["metadata"]["knowledge_bases_mounted"] == mounted


def test_explicit_references_that_cannot_be_used_are_refused(runtime_env):
    admin_root = runtime_env.admin_root
    subject_a = helpers.make_subject(admin_root, "科目A")
    subject_b = helpers.make_subject(admin_root, "科目B")
    _make_ready_kb(subject_b, marker="B-only")

    async def scenario() -> None:
        # 不存在的全局库：拒绝（不静默丢掉、不回落同名库）。
        with pytest.raises(SubjectOperationError) as excinfo:
            await _run_turn(runtime_env, {"knowledge_bases": ["ghost-kb"]})
        assert excinfo.value.code.value == ErrorCode.KB_NOT_FOUND.value

        # 越科的 subject ref：403。
        with pytest.raises(SubjectOperationError) as excinfo:
            await _run_turn(
                runtime_env,
                {
                    "subject_id": subject_a.subject_id,
                    "knowledge_bases": [
                        kb_scope.encode_subject_kb_ref(subject_b.subject_id, KB_NAME)
                    ],
                },
            )
        assert excinfo.value.code.value == ErrorCode.SCOPE_FORBIDDEN.value

        # 同名裸名同时命中显式裸名与本科库：歧义必须拒绝，不能猜来源。
        _make_ready_kb(subject_a, KB_NAME, marker="A-only")
        with pytest.raises(SubjectOperationError) as excinfo:
            await _run_turn(
                runtime_env, {"subject_id": subject_a.subject_id, "knowledge_bases": [KB_NAME]}
            )
        assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value

    asyncio.run(scenario())


def test_a_corrupt_subject_kb_config_is_a_fixed_storage_error(runtime_env):
    from deeptutor.subjects.errors import SubjectStorageError, map_subject_exception

    subject = helpers.make_subject(runtime_env.admin_root, "科目A")
    config = _write_kb_config(subject, {KB_NAME: {"status": "ready"}})
    config.write_text("{not json", encoding="utf-8")
    before = config.read_bytes()

    with pytest.raises(SubjectStorageError) as excinfo:
        asyncio.run(_run_turn(runtime_env, {"subject_id": subject.subject_id}))
    mapped = map_subject_exception(excinfo.value)
    assert mapped.code.value == ErrorCode.STORAGE_CORRUPT.value
    assert str(subject.subject_id) not in mapped.message
    assert str(runtime_env.admin_root) not in mapped.message
    # 损坏文件保持原样（没有被"修复"成空科目继续跑）。
    assert config.read_bytes() == before


# ---------------------------------------------------------------------------
# 学期摘要
# ---------------------------------------------------------------------------
def test_only_the_current_terms_exam_points_reach_the_summary(runtime_env):
    subject = helpers.make_subject(runtime_env.admin_root, "科目A", term="2026春")
    for term, content in (
        ("2026春", "本学期考点-甲"),
        ("2025秋", "上学期考点-乙"),
        ("", "无学期考点-丙"),
    ):
        exam_points.add_point(
            subject.subject_id, content=content, term=term, level="explicit", confirmed=True
        )

    _turn(runtime_env, {"subject_id": subject.subject_id})

    block = _subject_block(runtime_env)
    assert "本学期考点-甲" in block
    assert "上学期考点-乙" not in block
    assert "无学期考点-丙" not in block
    assert "【本学期期末考点】" in block
    assert _CapturingOrchestrator.captured["metadata"]["subject_term"] == "2026春"
    assert _CapturingOrchestrator.captured["metadata"]["subject_context_tokens"] > 0


def test_a_subject_without_a_term_gets_no_term_summary_block(runtime_env):
    subject = helpers.make_subject(runtime_env.admin_root, "科目A", term="")
    exam_points.add_point(
        subject.subject_id, content="未设学期考点-丁", term="2026春", level="explicit", confirmed=True
    )

    _turn(runtime_env, {"subject_id": subject.subject_id})

    block = _subject_block(runtime_env)
    assert "未设学期考点-丁" not in block
    assert "本学期期末考点" not in block
    assert "未设置学期" in block
    assert _CapturingOrchestrator.captured["metadata"]["subject_term"] == ""


def test_switching_subjects_does_not_leak_another_subjects_points(runtime_env):
    admin_root = runtime_env.admin_root
    subject_a = helpers.make_subject(admin_root, "科目A", term="2026春")
    subject_b = helpers.make_subject(admin_root, "科目B", term="2026春")
    exam_points.add_point(
        subject_a.subject_id, content="甲的考点", term="2026春", level="explicit", confirmed=True
    )
    exam_points.add_point(
        subject_b.subject_id, content="乙的考点", term="2026春", level="explicit", confirmed=True
    )

    async def scenario() -> None:
        await _run_turn(runtime_env, {"subject_id": subject_a.subject_id})
        assert "甲的考点" in _subject_block(runtime_env)
        assert "乙的考点" not in _subject_block(runtime_env)

        await _run_turn(runtime_env, {"subject_id": subject_b.subject_id})
        assert "乙的考点" in _subject_block(runtime_env)
        assert "甲的考点" not in _subject_block(runtime_env)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# R4：降级警告必须真正到达模型上下文（不只停在 metadata）
# ---------------------------------------------------------------------------
def _loop_messages(runtime_env, monkeypatch):
    """用真实 chat pipeline 从本轮真实 context 构造 loop messages。"""
    from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
    from deeptutor.core.context import UnifiedContext

    captured = _CapturingOrchestrator.captured
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
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="q",
        knowledge_bases=captured["knowledge_bases"],
        conversation_history=captured["history"],
        metadata=captured["metadata"],
        language="en",
    )
    return pipeline._build_loop_messages(context=context, enabled_tools=[])


def test_the_mount_warning_reaches_the_model_context(runtime_env, monkeypatch):
    """未 ready 的库不仅不挂载，模型也必须被告知它不可检索。"""
    subject = helpers.make_subject(runtime_env.admin_root, "科目A")
    _make_ready_kb(subject, "kb-ready", marker="ready", kb_type="assignment")
    stale = _make_ready_kb(subject, "kb-stale", marker="stale", kb_type="textbook")
    (Path(stale) / "raw" / "stale.txt").write_text("changed\n", encoding="utf-8")

    events = _turn(runtime_env, {"subject_id": subject.subject_id})
    warnings = _done(events)["metadata"]["subject_kb_warnings"]
    assert warnings

    messages = _loop_messages(runtime_env, monkeypatch)
    blob = json.dumps(messages, ensure_ascii=False)
    for item in warnings:
        assert item["kb_ref"] in blob, "警告没有进入模型上下文"
        assert item["message"] in blob, "固定文案没有进入模型上下文"
    assert "Unavailable knowledge bases" in blob


def test_a_fully_ready_subject_produces_no_warning(runtime_env, monkeypatch):
    """正常 ready 场景不误报：没有警告块，也没有虚构的不可用库。"""
    subject = helpers.make_subject(runtime_env.admin_root, "科目A")
    _make_ready_kb(subject, "kb-ready", marker="ready", kb_type="assignment")

    events = _turn(runtime_env, {"subject_id": subject.subject_id})
    assert _done(events)["metadata"].get("subject_kb_warnings") in (None, [])
    blob = json.dumps(_loop_messages(runtime_env, monkeypatch), ensure_ascii=False)
    assert "Unavailable knowledge bases" not in blob
    assert "不可检索的知识库" not in blob


def test_a_recorded_error_status_is_not_mounted_even_with_a_published_index(runtime_env):
    """registry 记录 error：即便已发布索引看起来一致，也不挂载并给出 warning。"""
    subject = helpers.make_subject(runtime_env.admin_root, "科目A")
    _make_ready_kb(subject, "kb-ready", marker="ready", kb_type="assignment")
    _make_ready_kb(subject, "kb-error", marker="err", kb_type="textbook")
    config = Path(subject.knowledge_bases) / "kb_config.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["knowledge_bases"]["kb-error"]["status"] = "error"
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    events = _turn(runtime_env, {"subject_id": subject.subject_id})

    mounted = _CapturingOrchestrator.captured["knowledge_bases"]
    assert mounted == [kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-ready")], mounted
    warnings = _done(events)["metadata"]["subject_kb_warnings"]
    by_ref = {item["kb_ref"]: item for item in warnings}
    error_ref = kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-error")
    assert error_ref in by_ref
    assert by_ref[error_ref]["status"] == "error", by_ref[error_ref]
    assert by_ref[error_ref]["code"] == ErrorCode.KB_NOT_READY.value
