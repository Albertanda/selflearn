"""P1-27：文档图像索引与覆盖贯通（默认文本 embedding 路径）。

证据要求（START_S06 §三 P1-27）：

* 唯一标记只存在于图片里 → fake vision 返回该内容 → **真实 loader** → 普通文本
  ``Document`` → **真实 LlamaIndex 文本 index/retriever**（离线确定性 embedding）
  → 查询命中带来源的描述。不替换 index/search，不只断言 Document 构造。
* 原 multimodal ``ImageNode`` 真实向量路径仍然通过。
* coverage 与单次 load 绑定：多源、连续两次、并发隔离，不串来源。
* 部分失败守恒、``parser_no_assets`` 警告、零节点拒绝、失败不发布版本。
* pipeline → initializer → metadata.json / .progress.json / 任务事件的加法式投影。
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any

from llama_index.core import Settings
from llama_index.core.embeddings import BaseEmbedding
from PIL import Image
import pytest

from deeptutor.services.llm.types import TutorResponse
from deeptutor.services.rag.pipelines.llamaindex import document_loader as loader_module
from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_module
from deeptutor.services.rag.pipelines.llamaindex import storage as storage_module
from deeptutor.utils.document_images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_DOC,
    MIN_IMAGE_BYTES,
)
from tests.phase1 import helpers

_MARKER = "UNIQUE-MARKER-4271"

_DEDICATED = SimpleNamespace(
    model="dedicated-vision",
    binding="openai",
    api_key="ded-key",
    base_url="https://ded.invalid/v1",
    api_version=None,
    extra_headers=None,
)

_COVERAGE_KEYS = {
    "text_sources",
    "images_seen",
    "images_indexed",
    "images_skipped",
    "skip_reasons",
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _png(target_size: int = 1200, *, color: tuple[int, int, int] = (9, 90, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buffer, format="PNG", compress_level=0)
    data = buffer.getvalue()
    assert len(data) <= target_size
    return data + b"\x00" * (target_size - len(data))


def _response(content: str, finish_reason: str | None = "stop") -> TutorResponse:
    return TutorResponse(
        content=content,
        finish_reason=finish_reason,
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    )


class _VisionStub:
    """``factory.complete_response`` double: one outcome per call."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.entered: asyncio.Event | None = None

    async def complete_response(self, prompt: str = "", **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        if self.entered is not None:
            self.entered.set()
        outcome = self.outcomes.pop(0) if self.outcomes else f"描述 {_MARKER}"
        if outcome is None:
            await asyncio.sleep(3600)  # never answers: used for cancellation tests
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def vision_env(monkeypatch: pytest.MonkeyPatch):
    """Deterministic vision routing + a stub at the real factory seam."""

    def install(*outcomes: Any, dedicated: Any = _DEDICATED, main: Any = None) -> _VisionStub:
        stub = _VisionStub(*outcomes)
        helpers.install_provider_stubs(monkeypatch, llm=stub)
        from deeptutor.services.rag.pipelines.llamaindex import image_description as desc

        monkeypatch.setattr(desc, "get_vision_strategy", lambda: "auto")
        monkeypatch.setattr(desc, "resolve_llm_runtime_config", lambda *a, **k: main)
        monkeypatch.setattr(desc, "resolve_vision_runtime_config", lambda *a, **k: dedicated)
        monkeypatch.setattr(desc, "supports_vision", lambda binding, model=None: False)
        return stub

    return install


@pytest.fixture
def parse_service(monkeypatch: pytest.MonkeyPatch):
    """Stub the shared parse layer, keyed by source file name."""
    import deeptutor.services.parsing as parsing

    def install(results: dict[str, Any]) -> None:
        class _StubService:
            def parse(self, source_path, **_kwargs):
                outcome = results[Path(source_path).name]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        monkeypatch.setattr(parsing, "get_parse_service", lambda: _StubService())

    return install


@pytest.fixture(autouse=True)
def _clear_index_cache():
    storage_module.clear_index_cache()
    yield
    storage_module.clear_index_cache()


class _MarkerEmbed(BaseEmbedding):
    """Offline deterministic text embedding: the marker owns one direction."""

    _DIM = 8

    def _vec(self, text: str) -> list[float]:
        if _MARKER in text:
            return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._vec(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vec(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vec(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def marker_embed():
    Settings.embed_model = _MarkerEmbed()
    yield Settings.embed_model


def _coverage_of(documents: Any) -> dict[str, Any]:
    coverage = documents.image_coverage
    assert set(coverage) == _COVERAGE_KEYS, coverage
    for key in ("text_sources", "images_seen", "images_indexed", "images_skipped"):
        value = coverage[key]
        assert isinstance(value, int) and not isinstance(value, bool) and value >= 0
    assert coverage["images_seen"] == coverage["images_indexed"] + coverage["images_skipped"]
    assert isinstance(coverage["skip_reasons"], dict)
    return coverage


def _description_documents(documents: Any) -> list[Any]:
    return [
        document
        for document in documents
        if document.metadata.get("content_kind") == "image_description"
    ]


# ---------------------------------------------------------------------------
# 1. 真实 loader → 真实文本 index/retriever，唯一标记只来自图片
# ---------------------------------------------------------------------------
def test_real_text_index_retrieves_image_description_with_source(
    p1_runtime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parse_service,
    vision_env,
    marker_embed,
) -> None:
    from deeptutor.services.parsing.types import ParsedDocument

    pdf_path = tmp_path / "notes.pdf"
    pdf_path.write_bytes(b"stub")
    asset_dir = tmp_path / "assets"
    (asset_dir / "images").mkdir(parents=True)
    (asset_dir / "images" / "figure-1.png").write_bytes(_png())

    parse_service(
        {
            "notes.pdf": ParsedDocument(
                markdown="正文只讲概念，没有任何标记。",
                asset_dir=asset_dir,
                blocks=[
                    {
                        "type": "image",
                        "img_path": "images/figure-1.png",
                        "page_idx": 4,
                    }
                ],
            )
        }
    )
    # The only place the marker exists is the image itself.
    vision_env(_response(f"图中标注 {_MARKER}，是一条曲线。"))

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf_path)]))
    coverage = _coverage_of(documents)
    assert coverage == {
        "text_sources": 1,
        "images_seen": 1,
        "images_indexed": 1,
        "images_skipped": 0,
        "skip_reasons": {},
    }

    descriptions = _description_documents(documents)
    assert len(descriptions) == 1
    assert _MARKER in descriptions[0].text
    assert descriptions[0].metadata["file_name"] == "notes.pdf"
    assert descriptions[0].metadata["asset_ref"] == "images/figure-1.png"
    assert descriptions[0].metadata["page"] == 4
    assert _MARKER not in "".join(
        document.text for document in documents if document.metadata.get("content_kind") is None
    )

    # Real text index + real retrieval over the deterministic embedding.
    storage_dir = tmp_path / "kb" / "version-1"
    count = storage_module.create_index(list(documents), storage_dir, show_progress=False)
    assert count == len(documents)

    results = storage_module.retrieve_nodes(storage_dir, f"{_MARKER} 是什么", top_k=3)
    assert results, "the description node must be retrievable"
    top = results[0].node
    assert _MARKER in top.get_content()
    assert top.metadata["file_name"] == "notes.pdf"
    assert top.metadata["content_kind"] == "image_description"
    assert top.metadata["asset_ref"] == "images/figure-1.png"


def test_text_embedding_path_produces_plain_documents_not_image_nodes(
    p1_runtime: Path,
    tmp_path: Path,
    vision_env,
) -> None:
    from llama_index.core.schema import ImageNode

    image_path = tmp_path / "standalone.png"
    image_path.write_bytes(_png())
    vision_env(_response(f"独立图片 {_MARKER}"))

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(image_path)]))
    assert len(documents) == 1
    assert not isinstance(documents[0], ImageNode)
    assert documents[0].metadata["content_kind"] == "image_description"
    assert documents[0].metadata["asset_ref"] == "standalone.png"
    from deeptutor.services.rag.pipelines.llamaindex.image_description import (
        DESCRIPTION_PREFIX,
    )

    assert documents[0].text.startswith(DESCRIPTION_PREFIX)


def test_multimodal_path_still_produces_real_image_nodes(
    p1_runtime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parse_service,
) -> None:
    """The legacy multimodal path keeps real vectors and provenance."""
    from llama_index.core.schema import ImageNode

    from deeptutor.services.parsing.types import ParsedDocument

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"stub")
    asset_dir = tmp_path / "paper-assets"
    asset_dir.mkdir()
    (asset_dir / "figure-1.png").write_bytes(_png())
    parse_service({"paper.pdf": ParsedDocument(markdown="Paper body", asset_dir=asset_dir)})

    class _MultimodalEmbedding:
        config = SimpleNamespace(binding="siliconflow", model="qwen3-vl")

        def __init__(self) -> None:
            self.contents: list[Any] = []

        def supports_multimodal_contents(self) -> bool:
            return True

        async def embed_contents(self, contents):
            self.contents = list(contents)
            return [[0.4, 0.5, 0.6] for _ in contents]

    class _VisionLLM(_VisionStub):
        """Multimodal main LLM double.

        The legacy path now describes through ``factory.complete_response`` (one
        strict wire attempt + the S02 truncation contract), so the double is
        installed at that seam rather than on the removed string wrapper.
        """

        config = SimpleNamespace(
            binding="openai",
            model="gpt-4o",
            api_key="test-key",
            base_url="https://example.invalid/v1",
            api_version=None,
            extra_headers=None,
        )

        def supports_multimodal_images(self) -> bool:
            return True

    embedding = _MultimodalEmbedding()
    llm = _VisionLLM(_response(f"Chart with {_MARKER}"))
    monkeypatch.setattr(loader_module, "get_embedding_client", lambda: embedding)
    monkeypatch.setattr(loader_module, "get_llm_client", lambda: llm)
    from deeptutor.services.llm import factory

    monkeypatch.setattr(factory, "complete_response", llm.complete_response)

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf_path)]))
    coverage = _coverage_of(documents)
    assert coverage["images_indexed"] == 1

    nodes = [document for document in documents if isinstance(document, ImageNode)]
    assert len(nodes) == 1
    assert nodes[0].embedding == [0.4, 0.5, 0.6]
    assert nodes[0].metadata["content_type"] == "image"
    assert nodes[0].metadata["file_name"] == "paper.pdf"
    assert nodes[0].metadata["asset_ref"] == "figure-1.png"
    assert embedding.contents and embedding.contents[0]["image"].startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# 2. coverage 绑定单次 load：多源 / 连续 / 并发 / 去重 / 预算 / 守恒
# ---------------------------------------------------------------------------
def _two_source_setup(tmp_path: Path, parse_service, *, second_image: bool = True):
    from deeptutor.services.parsing.types import ParsedDocument

    assets_a = tmp_path / "assets-a"
    assets_a.mkdir()
    (assets_a / "a-1.png").write_bytes(_png())
    assets_b = tmp_path / "assets-b"
    assets_b.mkdir()
    if second_image:
        (assets_b / "b-1.png").write_bytes(_png(color=(3, 3, 3)))

    pdf_a = tmp_path / "a.pdf"
    pdf_a.write_bytes(b"stub")
    pdf_b = tmp_path / "b.pdf"
    pdf_b.write_bytes(b"stub")
    notes = tmp_path / "notes.txt"
    notes.write_text("纯文本笔记", encoding="utf-8")

    parse_service(
        {
            "a.pdf": ParsedDocument(markdown="A 正文", asset_dir=assets_a),
            "b.pdf": ParsedDocument(markdown="B 正文", asset_dir=assets_b),
        }
    )
    return [str(pdf_a), str(pdf_b), str(notes)]


def test_coverage_counts_multi_source_and_keeps_origins_separate(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    stub = vision_env(
        _response("A 图描述"),
        _response("B 图描述"),
    )
    file_paths = _two_source_setup(tmp_path, parse_service)
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load(file_paths))
    coverage = _coverage_of(documents)
    assert coverage["text_sources"] == 3  # a.pdf + b.pdf + notes.txt
    assert coverage["images_seen"] == 2
    assert coverage["images_indexed"] == 2
    assert coverage["images_skipped"] == 0
    assert coverage["skip_reasons"] == {}

    by_source = {
        document.metadata["file_name"]: document.text
        for document in _description_documents(documents)
    }
    assert "A 图描述" in by_source["a.pdf"]
    assert "B 图描述" in by_source["b.pdf"]
    assert len(stub.calls) == 2


def test_repeated_asset_is_indexed_once(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    from deeptutor.services.parsing.types import ParsedDocument

    assets = tmp_path / "shared-assets"
    assets.mkdir()
    (assets / "logo.png").write_bytes(_png())
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"stub")
    # The parser names the same asset twice (running header on two pages).
    parse_service(
        {
            "doc.pdf": ParsedDocument(
                markdown="[图片 1: image-01.png]\n正文\n[图片 1: image-01.png]",
                asset_dir=assets,
                blocks=[
                    {"type": "image", "img_path": "logo.png", "page_idx": 0},
                    {"type": "image", "img_path": "logo.png", "page_idx": 2},
                ],
            )
        }
    )
    stub = vision_env(_response("同一个 logo"))
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert coverage["images_seen"] == 1
    assert coverage["images_indexed"] == 1
    assert len(_description_documents(documents)) == 1
    assert len(stub.calls) == 1, "one asset must be described once"
    # The parser's in-text position markers are preserved verbatim.
    body = [d for d in documents if d.metadata.get("content_kind") is None][0]
    assert body.text.count("[图片 1: image-01.png]") == 2
    assert _description_documents(documents)[0].metadata["page"] == 0


def test_per_document_image_budget_is_enforced(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    from deeptutor.utils.document_images import MAX_IMAGES_PER_DOC

    assets = tmp_path / "many-assets"
    assets.mkdir()
    for index in range(MAX_IMAGES_PER_DOC + 1):
        (assets / f"figure-{index:02d}.png").write_bytes(_png(color=(index, 1, 1)))
    pdf = tmp_path / "many.pdf"
    pdf.write_bytes(b"stub")
    parse_service({"many.pdf": _parsed(markdown="正文", asset_dir=assets)})
    stub = vision_env(*(_response(f"图 {index}") for index in range(MAX_IMAGES_PER_DOC + 1)))

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert coverage["images_seen"] == MAX_IMAGES_PER_DOC + 1
    assert coverage["images_indexed"] == MAX_IMAGES_PER_DOC
    assert coverage["images_skipped"] == 1
    assert coverage["skip_reasons"] == {"budget": 1}
    assert len(stub.calls) == MAX_IMAGES_PER_DOC


def _parsed(markdown: str, asset_dir: Path):
    from deeptutor.services.parsing.types import ParsedDocument

    return ParsedDocument(markdown=markdown, asset_dir=asset_dir)


def test_per_document_total_byte_budget_is_enforced(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    from deeptutor.utils.document_images import MAX_IMAGE_BYTES, MAX_TOTAL_IMAGE_BYTES_PER_DOC

    per_image = MAX_IMAGE_BYTES  # exactly 4 MiB: admitted
    assets = tmp_path / "big-assets"
    assets.mkdir()
    for index in range(4):
        (assets / f"big-{index}.png").write_bytes(_png(per_image, color=(index, 8, 8)))
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"stub")
    parse_service({"big.pdf": _parsed(markdown="正文", asset_dir=assets)})
    stub = vision_env(*(_response(f"大图 {index}") for index in range(4)))

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert coverage["images_seen"] == 4
    assert coverage["images_indexed"] == 3  # 3 × 4 MiB = 12 MiB
    assert coverage["images_skipped"] == 1
    assert coverage["skip_reasons"] == {"budget": 1}
    assert MAX_TOTAL_IMAGE_BYTES_PER_DOC == 3 * per_image
    assert len(stub.calls) == 3


def test_parser_without_assets_reports_unverified_not_zero(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    """No assets ⇒ "unverified", not "0 images and fully covered"."""
    stub = vision_env()
    pdf = tmp_path / "textonly.pdf"
    pdf.write_bytes(b"stub")
    parse_service({"textonly.pdf": _parsed(markdown="只有正文", asset_dir=tmp_path / "missing")})

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert coverage["images_seen"] == 0
    assert coverage["images_skipped"] == 0
    assert coverage["skip_reasons"] == {"parser_no_assets": 1}
    assert documents.image_coverage_warning == loader_module.IMAGE_COVERAGE_WARNING
    assert stub.calls == []


def test_partial_failure_conserves_counts_and_warns(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    stub = vision_env(_response("成功的图"), _response("被截断", finish_reason="length"))
    file_paths = _two_source_setup(tmp_path, parse_service)
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load(file_paths))
    coverage = _coverage_of(documents)
    assert coverage["text_sources"] == 3
    assert coverage["images_seen"] == 2
    assert coverage["images_indexed"] == 1
    assert coverage["images_skipped"] == 1
    assert coverage["skip_reasons"] == {"vision_failed": 1}
    assert documents.image_coverage_warning
    assert len(stub.calls) == 2


def test_vision_unavailable_still_indexes_text_with_warning(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    stub = vision_env(dedicated=None, main=None)
    pdf = tmp_path / "both.pdf"
    pdf.write_bytes(b"stub")
    assets = tmp_path / "both-assets"
    assets.mkdir()
    (assets / "fig.png").write_bytes(_png())
    parse_service({"both.pdf": _parsed(markdown="有正文", asset_dir=assets)})

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert coverage == {
        "text_sources": 1,
        "images_seen": 1,
        "images_indexed": 0,
        "images_skipped": 1,
        "skip_reasons": {"vision_unavailable": 1},
    }
    assert documents.image_coverage_warning == loader_module.IMAGE_COVERAGE_WARNING
    assert [d.metadata["file_name"] for d in documents] == ["both.pdf"]
    assert stub.calls == []


def test_two_consecutive_loads_do_not_share_coverage(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    vision_env(_response("第一次"), _response("第二次"))
    file_paths = _two_source_setup(tmp_path, parse_service)

    first = asyncio.run(loader_module.LlamaIndexDocumentLoader().load(file_paths))
    second = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([file_paths[0]]))

    assert _coverage_of(first)["images_seen"] == 2
    assert _coverage_of(second)["images_seen"] == 1
    assert _coverage_of(second)["text_sources"] == 1
    # Coverage lives on the returned object, never in a shared module field.
    assert first.image_coverage is not second.image_coverage


def test_concurrent_loads_are_isolated(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    from deeptutor.services.parsing.types import ParsedDocument

    assets_a = tmp_path / "con-a"
    assets_a.mkdir()
    (assets_a / "a.png").write_bytes(_png())
    assets_b = tmp_path / "con-b"
    assets_b.mkdir()
    for index in range(3):
        (assets_b / f"b{index}.png").write_bytes(_png(color=(index, 2, 2)))
    pdf_a = tmp_path / "ca.pdf"
    pdf_a.write_bytes(b"stub")
    pdf_b = tmp_path / "cb.pdf"
    pdf_b.write_bytes(b"stub")
    parse_service(
        {
            "ca.pdf": ParsedDocument(markdown="A", asset_dir=assets_a),
            "cb.pdf": ParsedDocument(markdown="B", asset_dir=assets_b),
        }
    )
    stub = vision_env(*(_response(f"并发 {index}") for index in range(4)))

    async def _both():
        loader = loader_module.LlamaIndexDocumentLoader()
        return await asyncio.gather(loader.load([str(pdf_a)]), loader.load([str(pdf_b)]))

    first, second = asyncio.run(_both())
    assert _coverage_of(first)["images_seen"] == 1
    assert _coverage_of(second)["images_seen"] == 3
    assert len(stub.calls) == 4


def test_load_cancellation_propagates(
    p1_runtime: Path, tmp_path: Path, vision_env
) -> None:
    stub = vision_env(None)  # the stub never answers
    image_path = tmp_path / "hang.png"
    image_path.write_bytes(_png())
    stub.entered = asyncio.Event()

    async def _exercise():
        task = asyncio.create_task(
            loader_module.LlamaIndexDocumentLoader().load([str(image_path)])
        )
        await asyncio.wait_for(stub.entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_exercise())


def test_coverage_warning_is_absent_for_a_complete_run(
    p1_runtime: Path, tmp_path: Path, vision_env
) -> None:
    vision_env(_response("完整覆盖"))
    image_path = tmp_path / "only.png"
    image_path.write_bytes(_png())
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(image_path)]))
    coverage = _coverage_of(documents)
    assert coverage["images_skipped"] == 0
    assert documents.image_coverage_warning is None


# ---------------------------------------------------------------------------
# 3. pipeline 投影 + 零节点拒绝 + S05 门禁
# ---------------------------------------------------------------------------
def _loaded(documents: list[Any], *, coverage: dict[str, Any] | None, warning: str | None = None):
    return loader_module.LoadedDocuments(
        documents, image_coverage=coverage, image_coverage_warning=warning
    )


class _StubLoader:
    def __init__(self, documents: Any) -> None:
        self.documents = documents
        self.calls = 0

    async def load(self, file_paths: Any) -> Any:
        self.calls += 1
        return self.documents


def _pipeline(tmp_path: Path, documents: Any, monkeypatch: pytest.MonkeyPatch, *, signature=None):
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as mod

    # These tests project coverage / exercise the gates, so the global
    # LlamaIndex settings configuration is stubbed out (it needs a real model
    # catalog); the embedding client double still stands in for every call.
    helpers.install_provider_stubs(monkeypatch, embedding=helpers.FakeEmbeddingClient())
    monkeypatch.setattr(mod, "configure_llamaindex_settings", lambda logger=None: None)
    return mod.LlamaIndexPipeline(
        kb_base_dir=str(tmp_path),
        signature_provider=(lambda: signature) if signature is not None else (lambda: None),
        document_loader=_StubLoader(documents),
    )


@pytest.mark.parametrize("shape", ["keyword", "two_positional", "one_positional"])
def test_pipeline_projects_this_runs_coverage_to_the_callback(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    from llama_index.core import Document

    coverage = {
        "text_sources": 1,
        "images_seen": 2,
        "images_indexed": 1,
        "images_skipped": 1,
        "skip_reasons": {"vision_failed": 1},
    }
    received: list[Any] = []

    if shape == "keyword":

        def callback(coverage, warning=None):
            received.append((coverage, warning))

    elif shape == "two_positional":

        def callback(coverage, warning):
            received.append((coverage, warning))

    else:

        def callback(coverage):
            received.append((coverage, None))

    documents = _loaded([Document(text="正文")], coverage=coverage, warning="警告文本")
    pipeline = _pipeline(tmp_path, documents, monkeypatch)

    async def _noop_verify() -> None:
        return None

    pipeline._verify_embedding_connectivity = _noop_verify  # type: ignore[assignment]
    recorded: dict[str, Any] = {}

    def _create_index(docs, storage_dir, *, show_progress=True):
        recorded["docs"] = list(docs)
        return len(docs)

    import deeptutor.services.rag.pipelines.llamaindex.pipeline as mod

    original_create = mod.storage.create_index
    try:
        mod.storage.create_index = _create_index  # type: ignore[assignment]
        ok = asyncio.run(
            pipeline.initialize(
                "kb", [str(tmp_path / "x.txt")], image_coverage_callback=callback
            )
        )
    finally:
        mod.storage.create_index = original_create  # type: ignore[assignment]

    assert ok is True
    # A one-argument callback cannot receive the warning; the documented two-arg
    # and keyword forms do.
    expected_warning = None if shape == "one_positional" else "警告文本"
    assert received == [(coverage, expected_warning)]
    assert recorded["docs"] and recorded["docs"][0].text == "正文"


def test_pipeline_rejects_zero_nodes_and_cleans_the_new_version_dir(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as mod

    coverage = {
        "text_sources": 0,
        "images_seen": 1,
        "images_indexed": 0,
        "images_skipped": 1,
        "skip_reasons": {"vision_failed": 1},
    }
    seen: list[Any] = []
    pipeline = _pipeline(tmp_path, _loaded([], coverage=coverage, warning="警告"), monkeypatch)

    async def _noop_verify() -> None:
        return None

    pipeline._verify_embedding_connectivity = _noop_verify  # type: ignore[assignment]

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - gate must stop here
        raise AssertionError("a zero-node run must not reach index creation")

    # Stub the index step so the assertion below tests *the gate* and not the
    # ambient LlamaIndex embedding configuration.
    original_create = mod.storage.create_index
    try:
        mod.storage.create_index = _must_not_run  # type: ignore[assignment]
        ok = asyncio.run(
            pipeline.initialize(
                "kb",
                [str(tmp_path / "x.txt")],
                image_coverage_callback=lambda c, w=None: seen.append(c),
            )
        )
    finally:
        mod.storage.create_index = original_create  # type: ignore[assignment]

    assert ok is False
    # The coverage is projected even though the run was rejected.
    assert seen == [coverage]
    kb_dir = tmp_path / "kb"
    assert not list(kb_dir.glob("version-*")), "a rejected run must not leave a version dir"
    assert mod.index_worker_state(kb_dir)["alive"] is False


def test_pipeline_image_only_failure_keeps_the_previous_ready_version(
    p1_runtime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parse_service,
    vision_env,
) -> None:
    """Only-image document with no vision: fail, publish nothing, keep the old one."""
    from deeptutor.services.rag import index_versioning
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as mod

    vision_env(dedicated=None, main=None)
    pdf = tmp_path / "kb" / "raw" / "only.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"stub")
    assets = pdf.parent / "only-assets"
    assets.mkdir()
    (assets / "fig.png").write_bytes(_png())
    parse_service({"only.pdf": _parsed(markdown="", asset_dir=assets)})

    from deeptutor.services.rag.index_versioning import EmbeddingSignature

    sig = EmbeddingSignature(
        binding="openai", model="m", dimension=8, base_url="", api_version=""
    )
    kb_dir = tmp_path / "kb"
    old_version = kb_dir / "version-1"
    old_version.mkdir(parents=True)
    (old_version / "docstore.json").write_text("{}", encoding="utf-8")
    (old_version / "index_store.json").write_text("{}", encoding="utf-8")
    (old_version / "meta.json").write_text(
        json.dumps({"version": "version-1", "signature": sig.hash()}),
        encoding="utf-8",
    )
    before = sorted(path.name for path in old_version.iterdir())

    helpers.install_provider_stubs(monkeypatch, embedding=helpers.FakeEmbeddingClient())
    monkeypatch.setattr(mod, "configure_llamaindex_settings", lambda logger=None: None)
    pipeline = mod.LlamaIndexPipeline(kb_base_dir=str(tmp_path), signature_provider=lambda: sig)

    async def _noop_verify() -> None:
        return None

    pipeline._verify_embedding_connectivity = _noop_verify  # type: ignore[assignment]
    ok = asyncio.run(pipeline.initialize("kb", [str(pdf)]))
    assert ok is False
    # The previously published version is untouched and still resolvable.
    assert sorted(path.name for path in old_version.iterdir()) == before
    preserved = index_versioning.find_matching_version(kb_dir, sig)
    assert preserved is not None
    assert Path(preserved["storage_path"]) == old_version
    # The failed attempt left no new published version behind.
    assert sorted(path.name for path in kb_dir.glob("version-*")) == ["version-1"]


def test_pipeline_still_refuses_a_live_same_kb_worker(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as mod

    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    marker = mod._claim_index_worker(str(kb_dir.resolve()))
    try:
        pipeline = _pipeline(tmp_path, _loaded([], coverage=None), monkeypatch)
        with pytest.raises(mod.IndexingStallError):
            asyncio.run(pipeline.initialize("kb", [str(tmp_path / "x.txt")]))
        assert list(kb_dir.glob("version-*")) == []
    finally:
        mod._release_index_worker(str(kb_dir.resolve()), marker)
    assert mod.index_worker_state(kb_dir)["alive"] is False


# ---------------------------------------------------------------------------
# 4. initializer / progress_tracker 投影
# ---------------------------------------------------------------------------
_COVERAGE = {
    "text_sources": 2,
    "images_seen": 3,
    "images_indexed": 2,
    "images_skipped": 1,
    "skip_reasons": {"vision_failed": 1},
}
_WARNING = loader_module.IMAGE_COVERAGE_WARNING


class _RecordingStreams:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def ensure_task(self, task_id: str) -> None:
        return None

    def emit(self, task_id: str, kind: str, payload: dict) -> None:
        self.events.append((task_id, kind, dict(payload)))


@pytest.fixture
def task_streams(monkeypatch: pytest.MonkeyPatch) -> _RecordingStreams:
    import deeptutor.api.utils.task_log_stream as stream_module

    recorder = _RecordingStreams()
    monkeypatch.setattr(stream_module, "get_task_stream_manager", lambda: recorder)
    return recorder


def _run_initializer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, coverage, warning, success=True):
    """Drive the real ``process_documents`` with a stub RAG service."""
    from deeptutor.knowledge import initializer as initializer_module
    from deeptutor.knowledge.progress_tracker import ProgressTracker

    base_dir = tmp_path / "knowledge_bases"
    kb_dir = base_dir / "kb"
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "notes.txt"
    source.write_text("正文", encoding="utf-8")

    class _StubRAG:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.calls: list[dict[str, Any]] = []

        async def initialize(self, kb_name, file_paths, **kwargs):
            self.calls.append({"kb_name": kb_name, "file_paths": list(file_paths), **kwargs})
            callback = kwargs.get("image_coverage_callback")
            if callback is not None and coverage is not None:
                callback(coverage, warning)
            return success

    stub = _StubRAG()
    monkeypatch.setattr(initializer_module, "RAGService", lambda **kwargs: stub)

    tracker = ProgressTracker("kb", base_dir)
    tracker.task_id = "task-1"
    initializer = initializer_module.KnowledgeBaseInitializer(
        kb_name="kb",
        base_dir=str(base_dir),
        progress_tracker=tracker,
        rag_provider="llamaindex",
    )
    initializer.create_directory_structure()
    initializer.copy_documents([str(source)])
    return initializer, tracker, stub, kb_dir


def test_initializer_projects_coverage_into_metadata_progress_and_events(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_streams
) -> None:
    from deeptutor.knowledge.manager import KnowledgeBaseManager
    from deeptutor.knowledge.progress_tracker import ProgressStage

    initializer, tracker, stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    # Pre-existing metadata fields must survive the coverage merge.
    metadata_file = kb_dir / "metadata.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata["description"] = "保留我"
    metadata["custom_field"] = 7
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    notifications: list[dict] = []
    tracker.set_callback(notifications.append)

    assert asyncio.run(initializer.process_documents()) is True

    # The pipeline really received the projection seam.
    assert callable(stub.calls[0]["image_coverage_callback"])

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["description"] == "保留我"
    assert metadata["custom_field"] == 7
    assert metadata["image_coverage"] == _COVERAGE
    assert metadata["image_coverage_warning"] == _WARNING

    saved = json.loads((kb_dir / ".progress.json").read_text(encoding="utf-8"))
    assert saved["image_coverage"] == _COVERAGE
    assert saved["image_coverage_warning"] == _WARNING

    # kb_config progress carries it while the KB is still processing.
    manager = KnowledgeBaseManager(base_dir=str(kb_dir.parent))
    status = manager.get_kb_status("kb") or {}
    assert status.get("progress", {}).get("image_coverage") == _COVERAGE

    # The subject task's final COMPLETED update is written by the caller and has
    # no coverage of its own: the tracker must keep this run's numbers.
    tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1, indexed_count=1)
    final = json.loads((kb_dir / ".progress.json").read_text(encoding="utf-8"))
    assert final["stage"] == "completed"
    assert final["image_coverage"] == _COVERAGE
    assert final["image_coverage_warning"] == _WARNING

    progress_events = [event for event in task_streams.events if event[1] == "progress"]
    assert progress_events, "the task stream must see progress events"
    assert progress_events[-1][2]["image_coverage"] == _COVERAGE
    assert progress_events[-1][2]["stage"] == "completed"
    assert notifications[-1]["image_coverage"] == _COVERAGE
    assert notifications[-1]["image_coverage_warning"] == _WARNING


def test_initializer_second_run_does_not_reuse_the_previous_coverage(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_streams
) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage

    initializer, tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    assert asyncio.run(initializer.process_documents()) is True
    assert json.loads((kb_dir / ".progress.json").read_text())["image_coverage"] == _COVERAGE

    # A second run whose pipeline reports nothing must not inherit run #1.
    from deeptutor.knowledge import initializer as initializer_module

    class _SilentRAG:
        def __init__(self, **kwargs) -> None:
            pass

        async def initialize(self, kb_name, file_paths, **kwargs):
            return True

    monkeypatch.setattr(initializer_module, "RAGService", lambda **kwargs: _SilentRAG())
    assert asyncio.run(initializer.process_documents()) is True

    saved = json.loads((kb_dir / ".progress.json").read_text())
    assert "image_coverage" not in saved
    assert "image_coverage_warning" not in saved
    tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1)
    assert "image_coverage" not in json.loads((kb_dir / ".progress.json").read_text())


def test_cli_convenience_final_progress_keeps_coverage(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.knowledge import initializer as initializer_module
    from deeptutor.knowledge import manager as manager_module

    recorded: list[dict[str, Any]] = []

    class _Manager:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def update_kb_status(self, name: str, status: str, progress: dict | None = None) -> None:
            recorded.append({"name": name, "status": status, "progress": progress})

    monkeypatch.setattr(manager_module, "KnowledgeBaseManager", _Manager)

    async def _fake_process(self) -> bool:
        self.record_image_coverage(_COVERAGE, _WARNING)
        return True

    monkeypatch.setattr(initializer_module.KnowledgeBaseInitializer, "process_documents", _fake_process)

    source = tmp_path / "doc.txt"
    source.write_text("正文", encoding="utf-8")
    ok = asyncio.run(
        initializer_module.initialize_knowledge_base(
            "kb", [str(source)], base_dir=str(tmp_path / "knowledge_bases")
        )
    )

    assert ok is True
    ready = [entry for entry in recorded if entry["status"] == "ready"]
    assert ready, recorded
    assert ready[-1]["progress"]["image_coverage"] == _COVERAGE
    assert ready[-1]["progress"]["image_coverage_warning"] == _WARNING


def test_progress_tracker_drops_coverage_when_the_task_changes(
    p1_runtime: Path, tmp_path: Path
) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker

    tracker = ProgressTracker("kb", tmp_path)
    tracker.task_id = "task-a"
    tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "run a", image_coverage=_COVERAGE)
    assert tracker.get_progress()["image_coverage"] == _COVERAGE

    tracker.task_id = "task-b"
    tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "run b")
    saved = tracker.get_progress()
    assert "image_coverage" not in saved, "another task's coverage must not leak"


# ---------------------------------------------------------------------------
# 5. S06 返修：受约束资产根、两条路径共用单图门禁、有界受理额度、发布边界、
#    新 run 边界与 ready 状态的安全覆盖投影（独立探针 18 方法的永久化）
# ---------------------------------------------------------------------------
def _legacy_clients(monkeypatch: pytest.MonkeyPatch, *, embed_calls: list, description: Any = None):
    """Install the legacy multimodal doubles (embedding + main LLM).

    ``description`` is the factory outcome for the image request; ``None`` makes
    the request hang, which the shared timeout must bound.
    """
    from deeptutor.services.llm import factory

    class _Embedding:
        config = SimpleNamespace(binding="siliconflow", model="qwen3-vl")

        def supports_multimodal_contents(self) -> bool:
            return True

        async def embed_contents(self, contents):
            embed_calls.extend(contents)
            return [[0.1, 0.2, 0.3] for _ in contents]

    class _LLM(_VisionStub):
        config = SimpleNamespace(
            binding="openai",
            model="gpt-4o",
            provider_name="openai",
            reasoning_effort=None,
            api_key="fictional-key",
            base_url="https://review.invalid/v1",
            api_version=None,
            extra_headers=None,
        )

        def supports_multimodal_images(self) -> bool:
            return True

    llm = _LLM(description)
    monkeypatch.setattr(loader_module, "get_embedding_client", lambda: _Embedding())
    monkeypatch.setattr(loader_module, "get_llm_client", lambda: llm)
    monkeypatch.setattr(factory, "complete_response", llm.complete_response)
    return llm


def test_symlinked_parser_asset_root_is_never_read(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    """A symlinked asset root is unverified — never enumerated around the link."""
    outside = tmp_path / "other-owner-assets"
    outside.mkdir()
    (outside / "private.png").write_bytes(_png())
    link = tmp_path / "parser-assets"
    link.symlink_to(outside, target_is_directory=True)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"stub")
    parse_service({"source.pdf": _parsed(markdown="正文", asset_dir=link)})

    stub = vision_env()
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))

    coverage = _coverage_of(documents)
    assert coverage["images_seen"] == 0, "the outside tree must not be enumerated"
    assert coverage["images_indexed"] == 0
    assert coverage["skip_reasons"] == {"parser_no_assets": 1}
    assert documents.image_coverage_warning == loader_module.IMAGE_COVERAGE_WARNING
    assert stub.calls == [], "outside-root bytes reached the vision request"


def test_symlinked_parent_component_of_the_asset_root_is_refused(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    real_parent = tmp_path / "real-parent"
    (real_parent / "assets").mkdir(parents=True)
    (real_parent / "assets" / "figure.png").write_bytes(_png())
    link_parent = tmp_path / "linked-parent"
    link_parent.symlink_to(real_parent, target_is_directory=True)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"stub")
    parse_service(
        {"source.pdf": _parsed(markdown="正文", asset_dir=link_parent / "assets")}
    )

    stub = vision_env()
    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    assert _coverage_of(documents)["images_indexed"] == 0
    assert stub.calls == []


def test_multimodal_path_uses_the_same_single_image_gates(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The legacy path is not an exemption from the byte/format gates."""
    embed_calls: list = []
    _legacy_clients(monkeypatch, embed_calls=embed_calls, description=_response("legacy"))
    cases = [
        ("small.png", _png(MIN_IMAGE_BYTES - 1), "budget"),
        ("large.png", _png(MAX_IMAGE_BYTES + 1), "budget"),
        ("invalid.png", b"not-an-image" * 120, "unsupported_image"),
    ]
    for name, body, reason in cases:
        embed_calls.clear()
        path = tmp_path / name
        path.write_bytes(body)
        documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(path)]))
        coverage = _coverage_of(documents)
        assert coverage["images_indexed"] == 0, coverage
        assert coverage["skip_reasons"] == {reason: 1}, coverage
        assert embed_calls == [], f"{name} reached the embedding request"
        assert not _description_documents(documents)


def test_multimodal_description_is_bounded_and_rejects_truncation(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same timeout and same empty/truncation contract as the text path."""
    image = tmp_path / "figure.png"
    image.write_bytes(_png())

    embed_calls: list = []
    _legacy_clients(monkeypatch, embed_calls=embed_calls, description=None)
    monkeypatch.setattr(
        "deeptutor.services.rag.pipelines.llamaindex.image_description.DESCRIBE_TIMEOUT_SECONDS",
        0.005,
    )
    timed_out = asyncio.run(
        asyncio.wait_for(
            loader_module.LlamaIndexDocumentLoader().load([str(image)]), timeout=1
        )
    )
    assert _coverage_of(timed_out)["images_indexed"] == 0
    assert _coverage_of(timed_out)["skip_reasons"] == {"vision_failed": 1}
    assert embed_calls == []

    _legacy_clients(
        monkeypatch,
        embed_calls=embed_calls,
        description=_response("HALF-DESCRIPTION", finish_reason="length"),
    )
    truncated = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(image)]))
    coverage = _coverage_of(truncated)
    assert coverage["images_indexed"] == 0, "truncated image text was promoted to a node"
    assert coverage["skip_reasons"] == {"vision_failed": 1}


def test_failed_descriptions_consume_the_image_attempt_budget(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    """Attempts — not successes — are bounded: 13 failing images mean 12 calls."""
    stub = vision_env(*[RuntimeError("fictional provider rejection")] * 20)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"stub")
    assets = tmp_path / "assets"
    assets.mkdir()
    for index in range(MAX_IMAGES_PER_DOC + 1):
        (assets / f"figure-{index:02d}.png").write_bytes(_png(color=(index, 1, 1)))
    parse_service({"source.pdf": _parsed(markdown="正文", asset_dir=assets)})

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert len(stub.calls) == MAX_IMAGES_PER_DOC, f"{len(stub.calls)} requests"
    assert coverage["skip_reasons"] == {"vision_failed": MAX_IMAGES_PER_DOC, "budget": 1}


def test_failed_descriptions_consume_the_byte_attempt_budget(
    p1_runtime: Path, tmp_path: Path, parse_service, vision_env
) -> None:
    """Four failing 4 MiB images still must not exceed the 12 MiB allowance."""
    stub = vision_env(*[RuntimeError("fictional provider rejection")] * 8)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"stub")
    assets = tmp_path / "assets"
    assets.mkdir()
    for index in range(4):
        (assets / f"big-{index}.png").write_bytes(_png(MAX_IMAGE_BYTES, color=(index, 2, 2)))
    parse_service({"source.pdf": _parsed(markdown="正文", asset_dir=assets)})

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(pdf)]))
    coverage = _coverage_of(documents)
    assert len(stub.calls) <= 3, "more than 12MiB was offered to vision for one document"
    assert coverage["skip_reasons"].get("budget") == 1


def test_corrupt_metadata_is_not_silently_replaced_by_coverage_merge(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.subjects.errors import SubjectStorageError

    initializer, _tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    path = kb_dir / "metadata.json"
    path.write_bytes(b"{broken")
    initializer.record_image_coverage(dict(_COVERAGE), _WARNING)

    with pytest.raises(SubjectStorageError):
        initializer._update_metadata_with_provider("llamaindex")
    assert path.read_bytes() == b"{broken", "the corrupt file must stay byte-identical"


@pytest.mark.parametrize("failure", ["before_metadata", "after_new_metadata", "after_old_metadata", "after_version"])
def test_failed_metadata_commit_does_not_publish_a_new_version(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A metadata failure must not leave a readable new index version."""
    from llama_index.core import Document

    from deeptutor.services.rag import index_versioning
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipe
    from deeptutor.subjects.errors import StorageIOError, SubjectStorageError

    initializer, _tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    sig = index_versioning.EmbeddingSignature(
        binding="openai", model="review-embed", dimension=2, base_url="", api_version=""
    )
    old = kb_dir / "version-1"
    old.mkdir()
    (old / "docstore.json").write_text("{}", encoding="utf-8")
    index_versioning.write_version_meta(kb_dir, sig, storage_dir=old)
    old_meta = (old / "meta.json").read_bytes()

    class _Loader:
        async def load(self, paths):
            return _loaded([Document(text="review body")], coverage=dict(_COVERAGE), warning=_WARNING)

    monkeypatch.setattr(pipe, "configure_llamaindex_settings", lambda *_a: None)
    pipeline = pipe.LlamaIndexPipeline(
        str(initializer.base_dir), signature_provider=lambda: sig, document_loader=_Loader()
    )

    async def _verified() -> None:
        return None

    pipeline._verify_embedding_connectivity = _verified  # type: ignore[assignment]

    def _create(docs, storage_dir, **kwargs):
        path = Path(storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "docstore.json").write_text("{}", encoding="utf-8")
        return len(docs)

    monkeypatch.setattr(pipe.storage, "create_index", _create)

    class _RAG:
        async def initialize(self, **kwargs):
            return await pipeline.initialize(**kwargs)

    from deeptutor.knowledge import initializer as initializer_module

    monkeypatch.setattr(initializer_module, "RAGService", lambda **_k: _RAG())
    metadata = kb_dir / "metadata.json"
    original = b'{"custom": 7, "description": "preserve"}\r\n'
    if failure == "after_new_metadata":
        metadata.unlink()
        original = None
    else:
        metadata.write_bytes(original)
    real_update = initializer._update_metadata_with_provider
    real_publish = pipe.write_version_meta

    def fail_metadata(*args, **kwargs):
        if failure != "before_metadata":
            real_update(*args, **kwargs)
        raise StorageIOError("fictional metadata failure")

    def fail_publish(*args, **kwargs):
        real_publish(*args, **kwargs)
        raise StorageIOError("fictional post-publication failure")

    if failure == "after_version":
        monkeypatch.setattr(pipe, "write_version_meta", fail_publish)
    else:
        monkeypatch.setattr(initializer, "_update_metadata_with_provider", fail_metadata)

    with pytest.raises(SubjectStorageError):
        asyncio.run(initializer.process_documents())

    assert (old / "meta.json").read_bytes() == old_meta
    selected = index_versioning.find_matching_version(kb_dir, sig)
    assert selected is not None and Path(selected["storage_path"]) == old
    assert sorted(path.name for path in kb_dir.glob("version-*")) == ["version-1"]
    assert (metadata.read_bytes() if metadata.exists() else None) == original


def test_a_new_run_resets_coverage_before_its_first_progress_event(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initializer, tracker, _stub, _kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    assert asyncio.run(initializer.process_documents()) is True

    from deeptutor.knowledge import initializer as initializer_module

    class _SilentRAG:
        def __init__(self, **kwargs) -> None:
            pass

        async def initialize(self, kb_name, file_paths, **kwargs):
            return True

    monkeypatch.setattr(initializer_module, "RAGService", lambda **kwargs: _SilentRAG())
    events: list[dict] = []
    tracker.set_callback(lambda payload: events.append(dict(payload)))

    assert asyncio.run(initializer.process_documents()) is True
    assert events, "the run must emit progress"
    assert "image_coverage" not in events[0], events[0]
    assert "image_coverage_warning" not in events[0], events[0]


def test_success_without_coverage_never_preserves_old_metadata_coverage(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initializer, _tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    assert asyncio.run(initializer.process_documents()) is True
    metadata = json.loads((kb_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["image_coverage"] == _COVERAGE

    from deeptutor.knowledge import initializer as initializer_module

    class _SilentRAG:
        def __init__(self, **kwargs) -> None:
            pass

        async def initialize(self, kb_name, file_paths, **kwargs):
            return True

    monkeypatch.setattr(initializer_module, "RAGService", lambda **kwargs: _SilentRAG())
    assert asyncio.run(initializer.process_documents()) is True

    metadata = json.loads((kb_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata.get("image_coverage") is None, metadata
    assert metadata.get("image_coverage_warning") is None, metadata


def test_ready_keeps_coverage_in_registry_and_real_subject_http(
    p1_runtime: Path, tmp_path: Path
) -> None:
    """A ready KB still shows the last measured coverage to a real GET."""
    from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker
    from deeptutor.subjects import store

    subject = store.create_subject("review-subject", term="2026秋")
    subject_id = subject["id"]
    kb_name = "assignment-kb"
    base = store.subject_kb_base_dir(subject_id)
    raw = base / kb_name / "raw"
    raw.mkdir(parents=True)
    (raw / "source.txt").write_text("review body", encoding="utf-8")
    materials = store.subject_dir(subject_id) / "materials" / "assignment"
    materials.mkdir(parents=True, exist_ok=True)
    (materials / "source.txt").write_text("review body", encoding="utf-8")
    store.upsert_knowledge_record(
        subject_id, {"kb_name": kb_name, "type": "assignment", "documents": 1}
    )

    tracker = ProgressTracker(kb_name, base)
    tracker.update(
        ProgressStage.PROCESSING_DOCUMENTS,
        "processing",
        image_coverage=dict(_COVERAGE),
        image_coverage_warning=_WARNING,
    )
    tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1)

    entry = json.loads((base / "kb_config.json").read_text(encoding="utf-8"))[
        "knowledge_bases"
    ][kb_name]
    assert entry.get("image_coverage") == _COVERAGE, entry
    assert "progress" not in entry, "ready keeps its stable-resource semantics"

    with helpers.route_client() as client:
        response = client.get(f"{helpers.ROUTE_PREFIX}/{subject_id}/knowledge/{kb_name}/status")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready", payload
    assert payload.get("image_coverage") == _COVERAGE, payload
    assert payload.get("image_coverage_warning") == _WARNING, payload


def test_public_projection_refuses_bad_coverage_and_huge_warning(
    p1_runtime: Path, tmp_path: Path
) -> None:
    """Untrustworthy stored coverage is reported as unverified, never echoed."""
    from deeptutor.subjects import store

    subject = store.create_subject("bad-coverage", term="2026秋")
    subject_id = subject["id"]
    kb_name = "assignment-kb"
    base = store.subject_kb_base_dir(subject_id)
    raw = base / kb_name / "raw"
    raw.mkdir(parents=True)
    (raw / "source.txt").write_text("body", encoding="utf-8")
    store.upsert_knowledge_record(subject_id, {"kb_name": kb_name, "type": "assignment"})

    marker = "SECRET-MARKER-9137"
    bad_entries = [
        {**_COVERAGE, "images_seen": True},
        {**_COVERAGE, "images_indexed": -1},
        {**_COVERAGE, "images_seen": 99},  # seen != indexed + skipped
        {**_COVERAGE, "skip_reasons": {"unknown_reason": 1}},
        {**_COVERAGE, "skip_reasons": {"budget": True}},
        {**_COVERAGE, "extra_field": 1},
    ]
    config_path = base / "kb_config.json"
    for bad in bad_entries:
        config_path.write_text(
            json.dumps(
                {
                    "knowledge_bases": {
                        kb_name: {
                            "status": "ready",
                            "image_coverage": bad,
                            "image_coverage_warning": f"{marker} " * 4000,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with helpers.route_client() as client:
            response = client.get(
                f"{helpers.ROUTE_PREFIX}/{subject_id}/knowledge/{kb_name}/status"
            )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("image_coverage") is None, payload
        assert payload.get("image_coverage_warning") is None, payload
        assert marker not in response.text
    assert len(response.text) < 4000


def test_same_name_kbs_in_two_subjects_keep_their_own_coverage(p1_runtime: Path) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker
    from deeptutor.subjects import store

    coverages = []
    for index in range(2):
        subject_id = store.create_subject(f"same-name-{index}", term="2026秋")["id"]
        base = store.subject_kb_base_dir(subject_id)
        (base / "assignment-kb" / "raw").mkdir(parents=True)
        (base / "assignment-kb" / "raw" / "source.txt").write_text("body", encoding="utf-8")
        coverage = {
            "text_sources": index + 1,
            "images_seen": 1,
            "images_indexed": 1,
            "images_skipped": 0,
            "skip_reasons": {},
        }
        coverages.append((subject_id, coverage))
        tracker = ProgressTracker("assignment-kb", base)
        tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "processing", image_coverage=coverage)
        tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1)

    for subject_id, coverage in coverages:
        with helpers.route_client() as client:
            response = client.get(
                f"{helpers.ROUTE_PREFIX}/{subject_id}/knowledge/assignment-kb/status"
            )
        assert response.status_code == 200, response.text
        assert response.json().get("image_coverage") == coverage, response.text


def test_public_and_loader_coverage_warning_stay_in_step() -> None:
    """The fixed public copy and the loader's log copy are the same sentence."""
    from deeptutor.subjects import material_manifest

    assert material_manifest.IMAGE_COVERAGE_WARNING == loader_module.IMAGE_COVERAGE_WARNING
    coverage = {
        "text_sources": 0,
        "images_seen": 1,
        "images_indexed": 1,
        "images_skipped": 0,
        "skip_reasons": {},
    }
    assert material_manifest.image_coverage_warning(coverage) is None
    assert material_manifest.sanitize_image_coverage(coverage) == coverage
    assert material_manifest.sanitize_image_coverage({**coverage, "images_seen": 2}) is None


@pytest.mark.parametrize("cancel", [False, True])
def test_abandoned_index_attempt_is_cleaned_only_after_worker_exit(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    """A terminal task status cannot authorize deleting a live writer's files."""
    from llama_index.core import Document

    pipe = pipeline_module
    pipeline = _pipeline(tmp_path, _loaded([Document(text="body")], coverage=None), monkeypatch)
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    paths = []

    async def verify():
        pass

    pipeline._verify_embedding_connectivity = verify

    def create(docs, storage_dir, **kwargs):
        path = Path(storage_dir)
        paths.append(path)
        (path / "work.marker").write_text("active", encoding="utf-8")
        entered.set()
        try:
            assert release.wait(3)
            (path / "docstore.json").write_text("{}", encoding="utf-8")
        finally:
            exited.set()

    monkeypatch.setattr(pipe.storage, "create_index", create)
    monkeypatch.setattr(pipe, "_INDEX_STALL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(pipe, "_INDEX_STALL_POLL_SECONDS", 0.001)

    async def scenario():
        task = asyncio.create_task(pipeline.initialize("kb", ["source.txt"]))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else pipe.IndexingStallError):
                await task
            assert pipe.index_worker_state(tmp_path / "kb")["alive"]
            assert (paths[0] / "work.marker").exists()
        finally:
            release.set()
        assert await asyncio.to_thread(exited.wait, 1)
        deadline = asyncio.get_running_loop().time() + 1
        while paths[0].exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        assert not paths[0].exists()
        assert not pipe.index_worker_state(tmp_path / "kb")["alive"]

    try:
        asyncio.run(scenario())
    finally:
        release.set()


@pytest.mark.parametrize("task_id", [None, "same-task"])
def test_reset_explicitly_clears_registry_coverage_for_reused_task_ids(
    p1_runtime: Path, tmp_path: Path, task_id: str | None
) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker

    tracker = ProgressTracker("kb", tmp_path)
    tracker.task_id = task_id
    tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "old", image_coverage=copy.deepcopy(_COVERAGE))
    tracker.reset_image_coverage()
    tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "new")
    status = json.loads((tmp_path / "kb_config.json").read_text())["knowledge_bases"]["kb"]
    assert status.get("image_coverage") is None
    assert status.get("image_coverage_warning") is None


def test_tracker_copies_nested_input_and_published_coverage(p1_runtime: Path, tmp_path: Path) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker

    tracker = ProgressTracker("kb", tmp_path)
    coverage = copy.deepcopy(_COVERAGE)
    tracker.update(ProgressStage.PROCESSING_DOCUMENTS, "start", image_coverage=coverage)
    coverage["skip_reasons"]["vision_failed"] = 77
    tracker.get_progress()["image_coverage"]["skip_reasons"]["vision_failed"] = 88
    tracker.update(ProgressStage.COMPLETED, "done")
    assert tracker.get_progress()["image_coverage"] == _COVERAGE


@pytest.mark.parametrize("changes", [
    {"images_seen": 1, "images_indexed": 1, "images_skipped": 0, "skip_reasons": {"vision_failed": 1}},
    {"images_seen": 2, "images_indexed": 0, "images_skipped": 2, "skip_reasons": {}},
])
def test_public_coverage_requires_a_reason_for_each_skipped_image(changes) -> None:
    from deeptutor.subjects.material_manifest import sanitize_image_coverage

    assert sanitize_image_coverage({**_COVERAGE, **changes}) is None
