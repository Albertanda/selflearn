"""P1-24 行为测试：清单、工具枚举与来源身份一致（C08/C13）。

目标：``rag``、``kb_files``、prompt manifest 使用同一套资源与挂载身份；显示友好
名称的同时保留 wire id；同名库不会被列成别科/global 的文件；``read_source`` 仍然
只读 server ``source_index``。

必证场景（对应卡内清单）：

* A 的 kb_files 清单只含 A 的文件（B/global 同名库不出现）；
* schema enum = 本轮实际可调用的 wire refs（rag 集合与 manifest 集合分别一致），
  且 additionalProperties=false、描述同时给出 wire id 与友好名称；
* prompt 标签与引用是同一身份；来源里伪造的 kb_ref/subject_id 不生效；
* 未知 source_id / 路径伪装不能被 read_source 读取，且工具没有 path 参数；
* PageIndex-only turn：既有 rag outline 可调用，prompt 如实说明且不虚构 MCP；
* 无科目的旧 kb_files 全局行为保持。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.subjects import kb_scope, uploads
from deeptutor.tools.builtin import KbFilesTool, ReadSourceTool
from tests.phase1 import helpers
from tests.phase1.test_p1_23 import (
    GLOBAL_KB,
    KB_NAME,
    _make_ready_kb,
    _register_global_kb,
)


@pytest.fixture(autouse=True)
def _isolated_registries():
    uploads.reset_registry_for_tests()
    try:
        yield
    finally:
        uploads.reset_registry_for_tests()


def _pipeline(monkeypatch: pytest.MonkeyPatch, *, language: str = "en") -> AgenticChatPipeline:
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
    return AgenticChatPipeline(language=language)


def _context(
    *, subject_id: str | None, mounted: list[str], tools: list[str] | None = None
) -> UnifiedContext:
    return UnifiedContext(
        session_id="s1",
        user_message="how many files?",
        enabled_tools=tools or ["rag", "kb_files"],
        knowledge_bases=list(mounted),
        language="en",
        metadata={"subject_id": subject_id, "turn_id": "t1"},
    )


@pytest.fixture
def libraries(p1_runtime: Path) -> SimpleNamespace:
    subject_a = helpers.make_subject(p1_runtime, "科目A")
    subject_b = helpers.make_subject(p1_runtime, "科目B")
    kb_a = _make_ready_kb(subject_a, marker="A-only")
    kb_b = _make_ready_kb(subject_b, marker="B-only")
    global_kb = _register_global_kb(p1_runtime)
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


def _schema_for(pipeline, context, name: str) -> dict:
    schemas = pipeline._build_llm_tool_schemas(["rag", "kb_files"], context)
    for schema in schemas:
        function = schema.get("function") or {}
        if function.get("name") == name:
            return function
    raise AssertionError(f"{name} schema missing: {schemas}")


# ---------------------------------------------------------------------------
# kb_files 清单身份
# ---------------------------------------------------------------------------
def test_the_file_listing_contains_only_the_current_subjects_files(libraries):
    tool = KbFilesTool()

    scoped = asyncio.run(
        tool.execute(
            kb_name=libraries.ref_a,
            _subject_id="科目a",
            _mounted_refs=[libraries.ref_a],
        )
    )
    assert scoped.success is not False
    assert scoped.metadata["kb_ref"] == libraries.ref_a
    assert scoped.metadata["subject_id"] == "科目a"
    assert scoped.metadata["kb_name"] == KB_NAME
    assert scoped.metadata["listed"] == ["A-only.txt"], scoped.metadata
    assert "B-only" not in scoped.content

    other = asyncio.run(
        tool.execute(
            kb_name=libraries.ref_b,
            _subject_id=libraries.B.subject_id,
            _mounted_refs=[libraries.ref_b],
        )
    )
    assert other.metadata["listed"] == ["B-only.txt"]
    assert other.metadata["kb_ref"] == libraries.ref_b


def test_a_bare_name_in_a_subject_turn_is_only_accepted_from_the_mounted_set(libraries):
    tool = KbFilesTool()

    mounted = asyncio.run(
        tool.execute(kb_name=KB_NAME, _subject_id="科目a", _mounted_refs=[libraries.ref_a])
    )
    assert mounted.metadata["kb_ref"] == libraries.ref_a
    assert mounted.metadata["listed"] == ["A-only.txt"]

    # 同名库同时挂载 → 歧义拒绝，不猜 A/B/global 任一个。
    ambiguous = asyncio.run(
        tool.execute(
            kb_name=KB_NAME,
            _subject_id="科目a",
            _mounted_refs=[libraries.ref_a, libraries.ref_b],
        )
    )
    assert ambiguous.success is False
    assert ambiguous.metadata["error"]["code"] == "invalid_input"

    # 未挂载的名字 → 拒绝，不回落到全局同名库。
    unmounted = asyncio.run(
        tool.execute(kb_name=GLOBAL_KB, _subject_id="科目a", _mounted_refs=[])
    )
    assert unmounted.success is False
    assert unmounted.metadata["error"]["code"] == "kb_not_found"


def test_a_not_ready_library_is_a_visible_failure_not_a_listing(libraries):
    raw = Path(libraries.kb_a) / "raw" / "A-only.txt"
    raw.write_text("changed after publish\n", encoding="utf-8")

    result = asyncio.run(
        KbFilesTool().execute(
            kb_name=libraries.ref_a,
            _subject_id="科目a",
            _mounted_refs=[libraries.ref_a],
        )
    )
    assert result.success is False
    assert result.metadata["error"]["code"] == "kb_not_ready"
    assert "A-only" not in result.content


def test_a_global_call_without_a_turn_scope_keeps_the_legacy_seam(libraries):
    """无注入作用域的旧调用（直接 Python/SDK）仍走原 access-checked 语义。"""
    legacy = asyncio.run(KbFilesTool().execute(kb_name=GLOBAL_KB))
    assert legacy.metadata["kb_name"] == GLOBAL_KB
    assert legacy.metadata["listed"] == ["global.txt"]
    assert "kb_ref" not in legacy.metadata  # 没有服务端作用域可保留


# ---------------------------------------------------------------------------
# 工具枚举与 prompt 身份
# ---------------------------------------------------------------------------
def test_the_tool_enums_match_the_mounted_identities(monkeypatch, libraries):
    pipeline = _pipeline(monkeypatch)
    context = _context(
        subject_id="科目a",
        mounted=[libraries.ref_a, f"admin:kb:{GLOBAL_KB}"],
    )

    rag_schema = _schema_for(pipeline, context, "rag")
    kb_files_schema = _schema_for(pipeline, context, "kb_files")
    expected = [libraries.ref_a, f"admin:kb:{GLOBAL_KB}"]

    assert rag_schema["parameters"]["properties"]["kb_name"]["enum"] == expected
    assert kb_files_schema["parameters"]["properties"]["kb_name"]["enum"] == expected
    assert rag_schema["parameters"]["additionalProperties"] is False
    assert kb_files_schema["parameters"]["additionalProperties"] is False

    # 描述里既有 wire id，也有友好名称；枚举值本身就是可调用身份。
    description = rag_schema["parameters"]["properties"]["kb_name"]["description"]
    assert libraries.ref_a in description
    assert KB_NAME in description
    assert f"admin:kb:{GLOBAL_KB}" in description
    assert GLOBAL_KB in description


def test_the_prompt_note_uses_the_same_identity(monkeypatch, libraries):
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id="科目a", mounted=[libraries.ref_a])

    note = pipeline._kb_system_note(context)

    assert libraries.ref_a in note
    assert KB_NAME in note
    assert libraries.ref_b not in note


def test_the_prompt_inventory_is_scoped_to_the_resolved_resource(monkeypatch, libraries):
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id="科目a", mounted=[libraries.ref_a])

    asyncio.run(pipeline._prepare_kb_manifests(context))
    note = pipeline._kb_manifest_system_note()

    assert [manifest.name for manifest in pipeline._kb_manifests] == [KB_NAME]
    assert "A-only.txt" in note
    assert "B-only" not in note


def test_sources_cannot_re_label_their_scope(monkeypatch, libraries):
    """来源里伪造的 kb_ref/subject_id 被服务端身份覆盖（P1-23 的公开投影）。

    走**真实**执行链（pipeline → builtin → rag_search → 解析器），只在
    ``RAGService`` 边界放替身，并让它回一个带伪造身份与宿主路径的来源。
    """
    pipeline = _pipeline(monkeypatch)

    class ForgedService:
        def __init__(self, *, kb_base_dir, provider=None, **_kwargs) -> None:
            self.base_dir = kb_base_dir
            self.provider = provider

        async def search(self, **_kwargs):
            return {
                "answer": "a",
                "content": "a",
                "sources": [
                    {
                        "title": "t",
                        "content": "c",
                        "source": f"{self.base_dir}/{KB_NAME}/raw/A-only.txt",
                        "kb_ref": libraries.ref_b,
                        "subject_id": libraries.B.subject_id,
                        "kb_name": "另一个库",
                        "base_dir": str(self.base_dir),
                    }
                ],
            }

    monkeypatch.setattr("deeptutor.tools.rag_tool.RAGService", ForgedService)
    context = _context(subject_id="科目a", mounted=[libraries.ref_a], tools=["rag"])
    result = asyncio.run(
        pipeline._execute_tool_call(
            "rag", {"query": "q", "kb_name": libraries.ref_a}, context=context
        )
    )

    source = result["sources"][0]
    assert source["kb_ref"] == libraries.ref_a
    assert source["subject_id"] == "科目a"
    assert source["kb_name"] == KB_NAME
    assert source["source"] == "raw/A-only.txt"
    blob = json.dumps(result, ensure_ascii=False)
    assert libraries.ref_b not in blob
    assert str(libraries.admin_root) not in blob
    assert "另一个库" not in blob


# ---------------------------------------------------------------------------
# read_source 仍然只读 server source_index
# ---------------------------------------------------------------------------
def test_read_source_only_reads_the_server_source_index(tmp_path):
    tool = ReadSourceTool()
    parameters = tool.get_definition().parameters
    assert [parameter.name for parameter in parameters] == ["source_id"]

    secret = tmp_path / "secret.txt"
    secret.write_text("top secret\n", encoding="utf-8")
    index = {"at-1": "the attached text"}

    known = asyncio.run(tool.execute(source_id="at-1", source_index=index))
    assert known.success is not False
    assert known.content == "the attached text"

    for candidate in ("at-2", "../../etc/passwd", "/etc/passwd", str(secret), "at-1/../at-1"):
        refused = asyncio.run(tool.execute(source_id=candidate, source_index=index))
        assert refused.success is False, candidate
        assert "top secret" not in refused.content
        assert "unknown source_id" in refused.content


# ---------------------------------------------------------------------------
# PageIndex：既有 outline 可达，且不再虚构 MCP
# ---------------------------------------------------------------------------
def _make_pageindex_kb(subject, kb_name: str = "pageindex-kb") -> Path:
    from deeptutor.subjects import store

    kb_dir = Path(subject.knowledge_bases) / kb_name
    (kb_dir / "raw").mkdir(parents=True, exist_ok=True)
    (kb_dir / "raw" / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    config = Path(subject.knowledge_bases) / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if config.is_file():
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "pageindex",
    }
    config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": kb_name, "type": "textbook", "documents": 1}
    )
    return kb_dir


def test_a_pageindex_turn_reaches_the_existing_outline_without_inventing_mcp(
    monkeypatch, p1_runtime
):
    from deeptutor.subjects import kb_scope as scope

    subject = helpers.make_subject(p1_runtime, "科目A")
    _make_pageindex_kb(subject)
    ref = scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id=subject.subject_id, mounted=[ref], tools=["rag"])

    asyncio.run(pipeline._prepare_deferred_tools(context))

    # 既有 rag outline 路径可达：这个库没有被排除在 rag 之外。
    assert pipeline._coexisting_rag_kbs(context) == [ref]
    assert _schema_for(pipeline, context, "rag")["parameters"]["properties"]["kb_name"][
        "enum"
    ] == [ref]
    assert ref in pipeline._pageindex_docs

    note = pipeline._pageindex_system_note()
    assert "retrieval_kind=outline" in note
    assert "pageindex-kb" in note and ref in note
    # 如实说明能力边界：既不虚构 MCP 工具，也不出现任何 mcp_* 工具名。
    assert "mcp" not in note.lower()
    assert "no additional deep-retrieval tool" in note


# ---------------------------------------------------------------------------
# R6：真实 PageIndex search 的实际结果必须声明 retrieval_kind
# ---------------------------------------------------------------------------
def test_a_real_pageindex_search_result_declares_its_retrieval_kind(p1_runtime):
    """fake 只放在 PageIndex client 边界；``search`` 本身是真实实现。"""
    from deeptutor.services.rag.pipelines.pageindex.pipeline import PageIndexPipeline

    pipe = object.__new__(PageIndexPipeline)
    pipe.document_map = lambda _name: {"paper.pdf": "doc-1"}

    async def get_document(*_args, **_kwargs):
        return {
            "result": {
                "title": "A review outline",
                "page_index": 1,
                "summary": "outline only",
            }
        }

    pipe._get_client = lambda: SimpleNamespace(get_document=get_document)
    result = asyncio.run(pipe.search("q", "kb"))

    assert result["content"]
    assert result["retrieval_kind"] == "outline"
    assert result["sources"]


def test_the_outline_marking_reaches_the_real_rag_tool(p1_runtime, monkeypatch):
    """真实 search → 真实 RAGTool 结果：调用方能从公开结果辨认"只有概览"。"""
    from deeptutor.services.rag.pipelines.pageindex.pipeline import PageIndexPipeline
    from deeptutor.subjects import kb_scope, store
    from deeptutor.tools.builtin import RAGTool
    from tests.phase1.test_p1_22 import _publish_ready

    subject = helpers.make_subject(p1_runtime, "科目A")
    _publish_ready(subject, "pageindex-kb", marker="paper", kb_type="textbook")
    config = Path(subject.knowledge_bases) / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if config.is_file():
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"]["pageindex-kb"] = {
        "path": "pageindex-kb",
        "status": "ready",
        "rag_provider": "pageindex",
    }
    config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": "pageindex-kb", "type": "textbook", "documents": 1}
    )
    ref = kb_scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")

    def fake_map(self, _kb_name):
        return {"paper.pdf": "doc-1"}

    async def get_document(*_args, **_kwargs):
        return {"result": {"title": "Outline", "page_index": 1, "summary": "only outline"}}

    monkeypatch.setattr(PageIndexPipeline, "document_map", fake_map)
    monkeypatch.setattr(PageIndexPipeline, "_get_client", lambda self: SimpleNamespace(
        get_document=get_document
    ))
    # 只替换工具层里的服务类？不：这里让真实 RAGService 选真实的 PageIndex pipeline。
    result = asyncio.run(
        RAGTool().execute(query="q", kb_name=ref, _subject_id=subject.subject_id, _mounted_refs=[ref])
    )

    assert result.success, result
    assert result.metadata["retrieval_kind"] == "outline"
    assert result.metadata["provider"] == "pageindex"
    assert result.sources
