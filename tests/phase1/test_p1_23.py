"""P1-23 行为测试：rag 执行端强制作用域（C08/C02）。

目标：从模型工具调用到真实 ``rag_search``/``RAGService.search``，服务只收到
canonical name、服务端 base_dir、正确 provider；模型伪造的解析参数一律被覆盖。

必证场景（对应卡内清单）：

* A/B/global 三个同名库各自查到自己目录里的标记；
* 模型传 ``kb_base_dir``/``_subject_id``/``expected_subject_id``/``provider``/
  mounted 列表都被丢弃并改写为服务端作用域；
* 未挂载/越科/未 ready/查询失败都不回落全局同名库；
* 断言真实 ``RAGService`` 收到的确切参数与返回来源的 kb_ref/subject_id/provenance；
* 来源里伪造的 kb_ref/subject_id 不能覆盖服务端身份，公开来源不含宿主路径；
* 无科目的旧全局调用仍然可用。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.subjects import kb_scope, store, uploads
from deeptutor.subjects import material_manifest as manifest_mod
from tests.phase1 import helpers

KB_NAME = "shared-kb"
KB_TYPE = "assignment"
GLOBAL_KB = "global-kb"


# ---------------------------------------------------------------------------
# 服务边界替身：真实工具链，只有 RAGService 被替换
# ---------------------------------------------------------------------------
class _RecordingService:
    """记录真实 ``RAGService(...)``/``search(...)`` 收到的每一个参数。"""

    instances: list["_RecordingService"] = []
    #: 类级故障注入：每次调用都会新建一个 service 实例，所以"让下一个查询失败"
    #: 必须能作用在还没创建的实例上。
    class_error: BaseException | None = None

    def __init__(self, *, kb_base_dir, provider=None, **kwargs) -> None:
        self.base_dir = kb_base_dir
        self.provider = provider
        self.init_kwargs = kwargs
        self.calls: list[dict] = []
        self.error: BaseException | None = None
        _RecordingService.instances.append(self)

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        failure = self.error if self.error is not None else type(self).class_error
        if failure is not None:
            raise failure
        return {
            "answer": f"answer from {Path(self.base_dir).name}",
            "content": "content",
            "sources": [
                {
                    "title": "A note",
                    "content": "…marker…",
                    "source": str(Path(self.base_dir) / KB_NAME / "raw" / "A-only.txt"),
                    "page": 3,
                    "chunk_id": "chunk-1",
                    "score": 0.5,
                    # 伪造的身份/内部字段：不得覆盖服务端作用域，也不得外泄。
                    "kb_ref": "subject:kb:别的科:shared-kb",
                    "subject_id": "别的科",
                    "base_dir": str(self.base_dir),
                    "api_key": "sk-should-never-be-public",
                }
            ],
            "provider": self.provider,
        }


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    _RecordingService.instances = []
    _RecordingService.class_error = None
    monkeypatch.setattr("deeptutor.tools.rag_tool.RAGService", _RecordingService)
    uploads.reset_registry_for_tests()
    try:
        yield _RecordingService
    finally:
        uploads.reset_registry_for_tests()


# ---------------------------------------------------------------------------
# 夹具：production 形状的科目库
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
    subject, kb_name: str = KB_NAME, *, marker: str, kb_type: str = KB_TYPE
) -> Path:
    kb_dir = _publish_ready(subject, kb_name, marker=marker, kb_type=kb_type)
    _write_kb_config(subject, {kb_name: {"status": "ready", "rag_provider": "llamaindex"}})
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": kb_name, "type": kb_type, "documents": 1, "status": "ready"},
    )
    return kb_dir


def _register_global_kb(admin_root: Path, kb_name: str = GLOBAL_KB) -> Path:
    base = helpers.global_kb_root(admin_root)
    kb_dir = base / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "global.txt").write_text("global\n", encoding="utf-8")
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
# 真实 pipeline → builtin → rag_search 接缝
# ---------------------------------------------------------------------------
def _pipeline(monkeypatch: pytest.MonkeyPatch) -> AgenticChatPipeline:
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
    return AgenticChatPipeline(language="en")


def _context(*, subject_id: str | None, mounted: list[str]) -> UnifiedContext:
    return UnifiedContext(
        session_id="s1",
        user_message="question",
        enabled_tools=["rag"],
        knowledge_bases=list(mounted),
        language="en",
        metadata={"subject_id": subject_id, "turn_id": "t1"},
    )


async def _call_rag(pipeline, context, args: dict) -> dict:
    return await pipeline._execute_tool_call("rag", args, stream=None, context=context)


def _execute(monkeypatch, pipeline, context, args) -> dict:
    return asyncio.run(_call_rag(pipeline, context, args))


@pytest.fixture
def three_libraries(p1_runtime: Path):
    subject_a = helpers.make_subject(p1_runtime, "科目A")
    subject_b = helpers.make_subject(p1_runtime, "科目B")
    kb_a = _make_ready_kb(subject_a, marker="A-only")
    kb_b = _make_ready_kb(subject_b, marker="B-only")
    global_kb = _register_global_kb(p1_runtime)
    # 全局同名库也真实存在：这样"越科/未挂载回落到全局同名库"是可以真的发生的，
    # 断言才有意义（否则失败只是因为找不到库）。
    _register_global_kb(p1_runtime, KB_NAME)
    return SimpleNamespace(
        admin_root=p1_runtime,
        A=subject_a,
        B=subject_b,
        kb_a=kb_a,
        kb_b=kb_b,
        global_kb=global_kb,
        ref_a=kb_scope.encode_subject_kb_ref(subject_a.subject_id, KB_NAME),
        ref_b=kb_scope.encode_subject_kb_ref(subject_b.subject_id, KB_NAME),
    )


def test_each_same_name_library_is_queried_in_its_own_directory(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)

    result_a = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    instance_a = service.instances[-1]
    assert instance_a.base_dir == str(three_libraries.A.knowledge_bases)
    assert instance_a.calls[0]["kb_name"] == KB_NAME
    assert instance_a.provider == "llamaindex"
    assert result_a["success"] is not False
    assert result_a["sources"][0]["kb_ref"] == three_libraries.ref_a
    assert result_a["sources"][0]["subject_id"] == "科目a"
    assert result_a["sources"][0]["kb_name"] == KB_NAME

    result_b = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id=three_libraries.B.subject_id, mounted=[three_libraries.ref_b]),
        {"query": "q", "kb_name": three_libraries.ref_b},
    )
    instance_b = service.instances[-1]
    assert instance_b.base_dir == str(three_libraries.B.knowledge_bases)
    assert instance_b.base_dir != instance_a.base_dir
    assert result_b["sources"][0]["subject_id"] == three_libraries.B.subject_id


def test_forged_scope_arguments_are_all_discarded(monkeypatch, service, three_libraries):
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id="科目a", mounted=[three_libraries.ref_a])

    _execute(
        monkeypatch,
        pipeline,
        context,
        {
            "query": "q",
            "kb_name": three_libraries.ref_a,
            # 模型能想到的每一个解析入口，全部应被丢弃。
            "kb_base_dir": "/tmp/attacker",
            "base_dir": "/tmp/attacker",
            "kb_dir": "/tmp/attacker",
            "provider": "lightrag",
            "_subject_id": three_libraries.B.subject_id,
            "subject_id": three_libraries.B.subject_id,
            "expected_subject_id": three_libraries.B.subject_id,
            "mounted_refs": [three_libraries.ref_b],
            "_mounted_refs": [three_libraries.ref_b],
            "_kb_scope": {"kb_ref": three_libraries.ref_b},
        },
    )

    instance = service.instances[-1]
    assert instance.base_dir == str(three_libraries.A.knowledge_bases)
    assert instance.provider == "llamaindex"
    assert instance.calls[0]["kb_name"] == KB_NAME
    assert "/tmp/attacker" not in json.dumps(instance.calls[0])
    assert instance.calls[0].get("kb_base_dir") is None


def test_a_forged_cross_subject_reference_is_refused_and_never_queried(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id="科目a", mounted=[three_libraries.ref_a])

    result = _execute(
        monkeypatch,
        pipeline,
        context,
        {"query": "q", "kb_name": three_libraries.ref_b},
    )

    assert service.instances == [], "越科引用仍然调用了检索"
    assert result["success"] is False
    assert result["metadata"]["error"]["code"] == "scope_forbidden"
    assert result["metadata"]["error"]["retryable"] is False
    assert three_libraries.B.subject_id not in json.dumps(result, ensure_ascii=False)


def test_a_bare_name_is_only_accepted_when_the_mounted_set_is_unambiguous(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)

    # 本轮只挂 A 的库：裸名唯一匹配 → 查 A。
    _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": KB_NAME},
    )
    assert service.instances[-1].base_dir == str(three_libraries.A.knowledge_bases)

    # 本轮挂了 A+B 同名库：歧义必须拒绝，不能任选一个。
    ambiguous = _execute(
        monkeypatch,
        pipeline,
        _context(
            subject_id="科目a",
            mounted=[three_libraries.ref_a, three_libraries.ref_b],
        ),
        {"query": "q", "kb_name": KB_NAME},
    )
    assert ambiguous["success"] is False
    assert ambiguous["metadata"]["error"]["code"] == "invalid_input"
    assert len(service.instances) == 1


def test_not_ready_unmounted_and_broken_queries_never_fall_back_to_global(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)
    subject_a = three_libraries.A

    # 1) 本科库 stale：拒绝，不去查同名全局库。
    (Path(three_libraries.kb_a) / "raw" / "A-only.txt").write_text("changed\n", encoding="utf-8")
    stale = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    assert stale["success"] is False
    assert stale["metadata"]["error"]["code"] == "kb_not_ready"
    assert stale["metadata"]["error"]["retryable"] is True
    assert service.instances == []

    # 2) 未挂载的名字（只在全局存在）：404，不回落。
    unmounted = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[]),
        {"query": "q", "kb_name": GLOBAL_KB},
    )
    assert unmounted["success"] is False
    assert unmounted["metadata"]["error"]["code"] == "kb_not_found"
    assert service.instances == []

    # 2b) 显式 wire ref 不在本轮挂载集合：403（不是"换个库试试"）。
    not_mounted = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[]),
        {"query": "q", "kb_name": f"admin:kb:{GLOBAL_KB}"},
    )
    assert not_mounted["success"] is False
    assert not_mounted["metadata"]["error"]["code"] == "scope_forbidden"
    assert service.instances == []

    # 3) 检索本身失败：错误可见、不重试到别的目录。
    _publish_ready(subject_a, KB_NAME, marker="A-only")
    failing = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    assert failing["success"] is not False
    assert len(service.instances) == 1
    service.class_error = RuntimeError("engine exploded /host/secret-cache")
    failed = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    # 检索失败是可见的**固定投影**失败结果，而不是"再试一次别的库"，也不是把
    # 引擎原文（可能含路径/密钥）当作公开错误。
    assert failed["success"] is False
    assert failed["metadata"]["error"]["code"] == "internal_error"
    assert failed["metadata"]["error"]["message"]
    assert failed["metadata"]["error"]["retryable"] is False
    leaked = json.dumps(failed, ensure_ascii=False)
    assert "engine exploded" not in leaked
    assert "/host/secret-cache" not in leaked
    # 只多了一次调用，且仍然是本科目录：没有"失败后换全局库再试"。
    assert len(service.instances) == 2
    assert service.instances[1].base_dir == str(subject_a.knowledge_bases)
    assert not any(
        inst.base_dir == str(helpers.global_kb_root(three_libraries.admin_root))
        for inst in service.instances
    )


def test_sources_keep_real_provenance_and_never_leak_host_paths(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)

    result = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )

    source = result["sources"][0]
    # 服务端身份覆盖了来源里的伪造 kb_ref/subject_id。
    assert source["kb_ref"] == three_libraries.ref_a
    assert source["subject_id"] == "科目a"
    assert source["kb_name"] == KB_NAME
    # 真实 parser provenance 保留。
    assert source["title"] == "A note" and source["page"] == 3 and source["chunk_id"] == "chunk-1"
    # 宿主绝对路径被投影成库内相对路径；内部字段与密钥不外泄。
    assert source["source"] == "raw/A-only.txt"
    blob = json.dumps(result, ensure_ascii=False)
    assert str(three_libraries.admin_root) not in blob
    assert "sk-should-never-be-public" not in blob
    assert "base_dir" not in json.dumps(source, ensure_ascii=False)
    assert "别科" not in blob


def test_a_model_call_with_an_empty_mount_reads_no_global_library(
    monkeypatch, service, three_libraries
):
    """模型路径永远携带**实际**挂载集合；``[]`` 不是"回落到任意全局库"。"""
    pipeline = _pipeline(monkeypatch)

    result = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id=None, mounted=[]),
        {"query": "q", "kb_name": GLOBAL_KB},
    )

    assert result["success"] is False
    assert result["metadata"]["error"]["code"] == "kb_not_found"
    assert service.instances == []


def test_a_trusted_python_call_keeps_the_legacy_global_resolver(
    monkeypatch, service, three_libraries
):
    """可信 Python 入口（``mounted_refs=None``）保留原全局授权语义。

    这是与模型调用明确分开的边界：``None`` 表示"没有本轮挂载集合"，只有进程内
    调用方会用它；模型路径永远注入实际列表。
    """
    from deeptutor.tools.rag_tool import rag_search

    result = asyncio.run(
        rag_search(
            query="q",
            kb_name=GLOBAL_KB,
            mounted_refs=None,
            subject_id=None,
        )
    )

    from deeptutor.tools.rag_tool import SCOPE_KEY

    assert service.instances[-1].base_dir == str(
        helpers.global_kb_root(three_libraries.admin_root)
    )
    # 该层返回引擎结果 + 服务端私有 scope（公开投影由 builtin 完成）。
    assert result[SCOPE_KEY]["kb_ref"] == f"admin:kb:{GLOBAL_KB}"
    assert result[SCOPE_KEY]["subject_id"] is None
    assert result[SCOPE_KEY]["name"] == GLOBAL_KB


def test_an_explicit_global_reference_in_a_subject_turn_resolves_to_that_library(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)

    result = _execute(
        monkeypatch,
        pipeline,
        _context(subject_id="科目a", mounted=[f"admin:kb:{GLOBAL_KB}"]),
        {"query": "q", "kb_name": f"admin:kb:{GLOBAL_KB}"},
    )

    assert service.instances[-1].base_dir == str(
        helpers.global_kb_root(three_libraries.admin_root)
    )
    assert result["sources"][0]["kb_ref"] == f"admin:kb:{GLOBAL_KB}"
    assert result["sources"][0]["subject_id"] is None


# ---------------------------------------------------------------------------
# R5：公开结果的安全投影（Windows 路径 / 嵌套诊断）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["source", "file", "filename"])
def test_windows_absolute_provenance_does_not_leak_the_host_directory(field):
    from deeptutor.tools.builtin import _rag_sources

    result = {
        "answer": "safe",
        "sources": [{field: r"C:\Users\review-secret\cache\figure.pdf", "page": 2}],
    }
    sources = _rag_sources(
        result,
        query="q",
        kb_name="shared",
        scope={"kb_ref": "admin:kb:shared", "subject_id": None, "name": "shared", "kb_dir": ""},
    )
    blob = json.dumps(sources, ensure_ascii=False)
    assert "review-secret" not in blob
    assert sources[0][field] == "figure.pdf"
    assert sources[0]["page"] == 2


def test_unc_and_posix_paths_are_projected_too():
    from deeptutor.tools.builtin import _project_path

    assert _project_path(r"\\host\share\secret\a.pdf", "") == "a.pdf"
    assert _project_path("/host/cache/a.pdf", "/host/cache") == "a.pdf"
    assert _project_path("/host/other/a.pdf", "/host/cache") == "a.pdf"
    # 相对来源与 URL 原样保留。
    assert _project_path("raw/notes.txt", "/host/cache") == "raw/notes.txt"
    assert _project_path("https://example.test/a.pdf", "/host/cache") == "https://example.test/a.pdf"


def test_nested_engine_metadata_never_reaches_the_public_result():
    from deeptutor.tools.builtin import _public_rag_result

    raw = {
        "answer": "safe",
        "content": "safe",
        "retrieval_kind": "outline",
        "diagnostics": {"api_key": "fictional-secret-1749", "kb_base_dir": "/review/private"},
        "sources": [{"title": "t", "content": "c"}],
        "provider": "llamaindex",
    }
    projected = _public_rag_result(raw, [{"title": "t", "content": "c"}])

    blob = json.dumps(projected, ensure_ascii=False)
    assert "fictional-secret-1749" not in blob
    assert "/review/private" not in blob
    assert "diagnostics" not in projected
    # 合法字段与来源仍在（不是把结果清空当安全）。
    assert projected["answer"] == "safe"
    assert projected["retrieval_kind"] == "outline"
    assert projected["sources"] == [{"title": "t", "content": "c"}]


# ---------------------------------------------------------------------------
# R7：既有 question/research 调用端也只注入服务端作用域
# ---------------------------------------------------------------------------
def _nonchat_pipeline(capability: str, kb_ref: str | None):
    from deeptutor.agents.question.pipeline import QuestionPipeline
    from deeptutor.agents.research.pipeline import ResearchPipeline

    cls = QuestionPipeline if capability == "question" else ResearchPipeline
    pipeline = object.__new__(cls)
    pipeline.kb_name = kb_ref
    return pipeline


@pytest.mark.parametrize("capability", ["question", "research"])
@pytest.mark.parametrize("forged", [False, True])
def test_existing_nonchat_consumers_inject_the_same_server_scope(
    service, three_libraries, capability, forged
):
    """deep_question/deep_research 的 rag 调用与 chat 同一执行端作用域。"""
    from deeptutor.core.context import UnifiedContext
    from deeptutor.tools.builtin import RAGTool

    pipeline = _nonchat_pipeline(capability, three_libraries.ref_a)
    context = UnifiedContext(
        session_id="review",
        user_message="q",
        knowledge_bases=[three_libraries.ref_a],
        metadata={"subject_id": three_libraries.A.subject_id},
    )
    args = {"query": "q", "kb_name": three_libraries.ref_a}
    if forged:
        args.update(
            kb_base_dir="/review/forged",
            provider="lightrag",
            _subject_id=three_libraries.B.subject_id,
            _mounted_refs=[three_libraries.ref_b],
        )

    trusted = pipeline._augment_tool_kwargs("rag", args, context)
    assert trusted["_subject_id"] == three_libraries.A.subject_id
    assert trusted["_mounted_refs"] == [three_libraries.ref_a]
    assert trusted["kb_name"] == three_libraries.ref_a
    assert "kb_base_dir" not in trusted and "provider" not in trusted

    result = asyncio.run(RAGTool().execute(**trusted))
    assert result.success, result
    assert len(service.instances) == 1
    assert service.instances[0].base_dir == str(three_libraries.A.knowledge_bases)
    assert result.sources[0]["kb_ref"] == three_libraries.ref_a


@pytest.mark.parametrize("capability", ["question", "research"])
def test_nonchat_consumers_with_an_empty_mount_read_nothing(
    service, three_libraries, capability
):
    """没有挂载时，两个调用端也只能失败，不能借模型给的库名读全局。"""
    from deeptutor.core.context import UnifiedContext
    from deeptutor.tools.builtin import RAGTool

    pipeline = _nonchat_pipeline(capability, None)
    context = UnifiedContext(
        session_id="review",
        user_message="q",
        knowledge_bases=[],
        metadata={"subject_id": three_libraries.A.subject_id},
    )

    trusted = pipeline._augment_tool_kwargs("rag", {"query": "q", "kb_name": GLOBAL_KB}, context)
    assert trusted["_mounted_refs"] == []

    result = asyncio.run(RAGTool().execute(**trusted))
    assert result.success is False
    assert result.metadata["error"]["code"] in {"kb_not_found", "scope_forbidden"}
    assert service.instances == []


@pytest.mark.parametrize("field", ["source", "page", "title"])
def test_source_fields_cannot_embed_arbitrary_diagnostics(field):
    from deeptutor.tools.builtin import _rag_sources

    sources = _rag_sources(
        {"sources": [{field: {"api_key": "fictional-private-401", "path": "/private/cache"}}]},
        query="q",
        kb_name="kb",
    )
    assert "fictional-private-401" not in json.dumps(sources), sources
    assert "/private/cache" not in json.dumps(sources), sources


@pytest.mark.parametrize(
    "failure",
    [
        {"error_type": "not_configured"},
        {"error_type": "retrieval_error"},
        {"success": False},
        {"needs_reindex": True},
    ],
)
def test_explicit_failed_engine_result_is_a_safe_tool_failure(
    monkeypatch, service, three_libraries, failure
):
    async def failed(self, **kwargs):
        return {"answer": "fictional-private-402 /private/cache", "sources": [], **failure}

    monkeypatch.setattr(service, "search", failed)
    result = _execute(
        monkeypatch,
        _pipeline(monkeypatch),
        _context(subject_id=three_libraries.A.subject_id, mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    assert result["success"] is False, result
    assert "fictional-private-402" not in json.dumps(result), result
    assert result.get("metadata", {}).get("error", {}).get("code"), result
    assert len(service.instances) == 1


def test_service_construction_error_is_also_safely_projected(monkeypatch, three_libraries):
    class Broken:
        def __init__(self, **kwargs):
            raise RuntimeError("fictional-private-403 /private/cache")

    monkeypatch.setattr("deeptutor.tools.rag_tool.RAGService", Broken)
    result = _execute(
        monkeypatch,
        _pipeline(monkeypatch),
        _context(subject_id=three_libraries.A.subject_id, mounted=[three_libraries.ref_a]),
        {"query": "q", "kb_name": three_libraries.ref_a},
    )
    assert result["success"] is False
    assert "fictional-private-403" not in json.dumps(result), result
    assert result.get("metadata", {}).get("error", {}).get("code"), result
