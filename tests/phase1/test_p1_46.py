"""P1-46: PageIndex only through the existing RAG outline, with honest copy.

The tests exercise the real tool assembly (``_prepare_deferred_tools`` +
schemas), the real PageIndex pipeline ``search``/REST writer, and the failure
branches.  No MCP client/transport is created; no live PageIndex service is
called (the client boundary is faked, the pipeline itself is real).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.services.rag.pipelines.pageindex.config import PageIndexNotConfiguredError
from deeptutor.services.rag.pipelines.pageindex.pipeline import (
    SUPPORTED_EXTENSIONS,
    PageIndexPipeline,
    is_supported_file,
)
from deeptutor.subjects import kb_scope, store, uploads
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
        user_message="outline this library",
        enabled_tools=tools or ["rag"],
        knowledge_bases=list(mounted),
        language="en",
        metadata={"subject_id": subject_id, "turn_id": "t1"},
    )


def _make_pageindex_kb(subject, kb_name: str = "pageindex-kb") -> Path:
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


def _schema_for(pipeline, context, name: str) -> dict:
    schemas = pipeline._build_llm_tool_schemas(["rag", "kb_files"], context)
    for schema in schemas:
        function = schema.get("function") or {}
        if function.get("name") == name:
            return function
    raise AssertionError(f"{name} schema missing: {schemas}")


def test_pageindex_only_mounts_the_existing_rag_outline(monkeypatch, p1_runtime):
    subject = helpers.make_subject(p1_runtime, "科目A")
    _make_pageindex_kb(subject)
    ref = kb_scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id=subject.subject_id, mounted=[ref])

    asyncio.run(pipeline._prepare_deferred_tools(context))
    enabled = pipeline._compose_enabled_tools(context)

    assert "rag" in enabled
    assert pipeline._coexisting_rag_kbs(context) == [ref]
    assert _schema_for(pipeline, context, "rag")["parameters"]["properties"]["kb_name"][
        "enum"
    ] == [ref]
    assert ref in pipeline._pageindex_docs

    note = pipeline._kb_system_note(context)
    assert "retrieval_kind=outline" in note
    assert "no additional deep-retrieval tool" in note
    assert "mcp" not in note.lower()
    tool_names = {
        (schema.get("function") or {}).get("name")
        for schema in pipeline._build_llm_tool_schemas(["rag", "kb_files"], context)
    }
    assert not any(str(name or "").lower().startswith("mcp") for name in tool_names)


def test_mixed_global_subject_and_llamaindex_mounts_stay_separate(
    monkeypatch, p1_runtime
):
    subject = helpers.make_subject(p1_runtime, "科目A")
    pageindex_dir = _make_pageindex_kb(subject)
    _make_ready_kb(subject, KB_NAME, marker="A-only")
    _register_global_kb(p1_runtime)
    pageindex_ref = kb_scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")
    llamaindex_ref = kb_scope.encode_subject_kb_ref(subject.subject_id, KB_NAME)
    global_ref = f"admin:kb:{GLOBAL_KB}"
    pipeline = _pipeline(monkeypatch)
    context = _context(
        subject_id=subject.subject_id,
        mounted=[pageindex_ref, llamaindex_ref, global_ref],
    )

    asyncio.run(pipeline._prepare_deferred_tools(context))

    assert pipeline._coexisting_rag_kbs(context) == [
        pageindex_ref,
        llamaindex_ref,
        global_ref,
    ]
    assert pageindex_ref in pipeline._pageindex_docs
    assert llamaindex_ref not in pipeline._pageindex_docs
    assert global_ref not in pipeline._pageindex_docs
    enum = _schema_for(pipeline, context, "rag")["parameters"]["properties"]["kb_name"][
        "enum"
    ]
    assert enum == [pageindex_ref, llamaindex_ref, global_ref]

    pageindex_note = pipeline._pageindex_system_note()
    assert pageindex_ref in pageindex_note
    assert llamaindex_ref not in pageindex_note
    assert global_ref not in pageindex_note
    assert pageindex_dir.is_dir()


def test_real_outline_result_has_no_passage_or_query_grounded_hit():
    pipeline = object.__new__(PageIndexPipeline)
    pipeline.document_map = lambda _name: {"paper.pdf": "doc-1"}

    async def get_document(*_args, **_kwargs):
        return {
            "result": {
                "title": "A review outline",
                "page_index": 7,
                "summary": "section one",
                "nodes": [
                    {"title": "Section one", "page_index": 8, "summary": "detail"}
                ],
            }
        }

    pipeline._get_client = lambda: SimpleNamespace(get_document=get_document)
    result = asyncio.run(pipeline.search("anything", "kb"))

    assert result["retrieval_kind"] == "outline"
    assert result["provider"] == "pageindex"
    assert result["content"] == result["answer"]
    assert "A review outline" in result["content"]
    assert "p.7" in result["content"]
    assert result["sources"][0]["title"] == "A review outline"
    assert "passage" not in json.dumps(result).lower()


def test_missing_directory_returns_an_honest_empty_outline(tmp_path):
    pipeline = PageIndexPipeline(kb_base_dir=str(tmp_path))

    assert pipeline.document_map("absent-kb") == {}
    result = asyncio.run(pipeline.search("q", "absent-kb"))

    assert result["retrieval_kind"] == "outline"
    assert result["needs_reindex"] is True
    assert result["content"] == ""
    assert result["sources"] == []
    assert "no indexed documents" in result["answer"]


def test_service_failure_is_named_and_never_fabricates_a_source():
    pipeline = PageIndexPipeline()
    pipeline.document_map = lambda _name: {"paper.pdf": "doc-1"}

    async def fail(*_args, **_kwargs):
        raise RuntimeError("upstream unavailable")

    pipeline._get_client = lambda: SimpleNamespace(get_document=fail)
    result = asyncio.run(pipeline.search("q", "kb"))

    assert result["retrieval_kind"] == "outline"
    assert result["error_type"] == "retrieval_error"
    assert result["content"] == ""
    assert result["sources"] == []
    assert "upstream unavailable" in result["answer"]


def test_not_configured_is_a_named_outline_error():
    pipeline = object.__new__(PageIndexPipeline)
    pipeline.document_map = lambda _name: {"paper.pdf": "doc-1"}
    pipeline._get_client = lambda: (_ for _ in ()).throw(
        PageIndexNotConfiguredError("PageIndex API key is not configured")
    )

    result = asyncio.run(pipeline.search("q", "kb"))

    assert result["retrieval_kind"] == "outline"
    assert result["error_type"] == "not_configured"
    assert result["content"] == ""
    assert result["sources"] == []


def test_rest_upload_and_document_map_stay_available(tmp_path):
    calls: list[tuple[str, str]] = []

    counter = 0

    class FakeClient:
        async def submit_document(self, path: Path) -> str:
            nonlocal counter
            counter += 1
            calls.append(("submit", Path(path).name))
            return f"doc-{counter}"

        async def wait_until_ready(self, doc_id: str) -> None:
            calls.append(("wait", doc_id))

    pipeline = PageIndexPipeline(kb_base_dir=str(tmp_path), client=FakeClient())
    first = tmp_path / "paper.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second = tmp_path / "notes.md"
    second.write_text("# notes\n", encoding="utf-8")

    assert SUPPORTED_EXTENSIONS >= {".pdf", ".md", ".docx", ".pptx"}
    assert is_supported_file(first)
    assert is_supported_file(second)
    assert asyncio.run(pipeline.initialize("kb", [str(first)])) is True
    assert pipeline.document_map("kb") == {"paper.pdf": "doc-1"}

    assert asyncio.run(pipeline.add_documents("kb", [str(second)])) is True
    assert pipeline.document_map("kb") == {
        "paper.pdf": "doc-1",
        "notes.md": "doc-2",
    }
    assert ("submit", "paper.pdf") in calls
    assert ("submit", "notes.md") in calls
    assert ("wait", "doc-1") in calls


def test_the_stale_mcp_wording_is_gone_from_the_two_wired_modules():
    pipeline_source = Path(
        "deeptutor/services/rag/pipelines/pageindex/pipeline.py"
    ).read_text(encoding="utf-8")
    agent_source = Path(
        "deeptutor/agents/chat/agentic_pipeline.py"
    ).read_text(encoding="utf-8")

    pipeline_text = " ".join(pipeline_source.split())
    agent_text = " ".join(agent_source.split())
    assert "deep retrieval is agentic" not in pipeline_text
    assert "through the PageIndex MCP server" not in pipeline_text
    assert "preloaded MCP tools, not rag" not in agent_text
    assert "doc_ids its MCP tools need" not in agent_text
    assert "no PageIndex MCP transport" in pipeline_text
    assert "Every attached KB, including a PageIndex library" in agent_text
    assert "doc_ids the rag outline references" in agent_text


def test_provider_picker_describes_the_actual_pageindex_outline(monkeypatch, p1_runtime):
    from deeptutor.services.rag.factory import KNOWN_PROVIDERS, list_pipelines

    monkeypatch.setattr(
        "deeptutor.services.rag.pipelines.pageindex.config.is_pageindex_configured",
        lambda: True,
    )
    catalog = list_pipelines()
    assert {row["id"] for row in catalog} == KNOWN_PROVIDERS
    pageindex = next(row for row in catalog if row["id"] == "pageindex")
    assert pageindex["configured"] is True and pageindex["requires_api_key"] is True
    assert "outline" in pageindex["description"].lower()
    assert "passage" in pageindex["description"].lower()
    assert "mcp" not in pageindex["description"].lower()
