"""Document loading for the LlamaIndex RAG pipeline.

Parser-backed files (PDF / Office / e-book) are converted through the shared
document-parse bridge (``deeptutor/services/parsing``), so the engine the user
picked in Settings → Document Parsing (text-only, MinerU, Docling, markitdown,
PyMuPDF4LLM) owns extraction. This is the same seam LightRAG and GraphRAG use;
routing LlamaIndex through it too means the parse-engine choice is honored by
every local retrieval engine.

Two image paths, one coverage report (C09)
------------------------------------------
* **Legacy multimodal path** — kept for the installations that already have a
  multimodal embedding model *and* a multimodal main LLM: every admitted image
  becomes an ``ImageNode`` with a real embedding.
* **Text description path** — the default: each admitted image is described by
  the vision model chosen by the existing vision strategy (P1-26
  ``describe_image_for_index``) and the description becomes an ordinary text
  ``Document`` in the normal text index. No image vector is fabricated and the
  embedding model/signature never changes.

Either way the load returns a ``LoadedDocuments`` — a real ``list`` subclass —
whose ``image_coverage`` describes *this one* load: ``text_sources``,
``images_seen``, ``images_indexed``, ``images_skipped`` and ``skip_reasons``.
Coverage is bound to the returned object, never to a module-level "last run"
field, so two concurrent loads cannot read each other's numbers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import mimetypes
import os
from pathlib import Path
import stat as stat_module
from typing import Any, Iterable

from llama_index.core import Document
from llama_index.core.schema import ImageNode

from deeptutor.services.embedding import get_embedding_client
from deeptutor.services.llm.client import get_llm_client
from deeptutor.services.rag.file_routing import FileTypeRouter
from deeptutor.services.rag.pipelines.llamaindex.image_description import (
    SKIP_BUDGET,
    SKIP_PARSER_NO_ASSETS,
    SKIP_REASONS,
    SKIP_UNSUPPORTED_IMAGE,
    SKIP_VISION_FAILED,
    asset_ref_from_root,
    confined_image_root,
    describe_image_for_index,
    describe_image_text,
    failure_kind,
    image_payload,
    inspect_image_file,
    is_regular_file_leaf,
    standalone_asset_ref,
)
from deeptutor.utils.document_images import ImageBudget

IMAGE_DESCRIPTION_SYSTEM_PROMPT = (
    "You describe images for a retrieval-augmented knowledge base. "
    "Be factual, concise, and include any visible text, labels, diagrams, "
    "tables, logos, or important visual relationships. Do not invent details."
)

IMAGE_DESCRIPTION_PROMPT = (
    "Describe this image so that a text-only answer generator can understand "
    "and cite it later. Include visible text/OCR if present, the main subject, "
    "and any educational or technical meaning. Keep the answer under 180 words."
)

#: Fixed, safe, outer-level note for a load that did not cover every image. It
#: is never folded into the five-field ``ImageCoverage`` object (that would
#: break the schema) and it never contains a path or provider message.
IMAGE_COVERAGE_WARNING = (
    "本次索引未覆盖文档中的全部图片：部分图片因视觉模型不可用、识别失败、"
    "格式不支持或超出预算被跳过，另有部分文档未能提取到可核实的图片。"
    "这些图片的内容不会出现在检索结果中。"
)

#: Parser block keys that carry a *real* page/location. Nothing here is derived
#: from a file name: a missing key stays ``None`` (C09: never guess a page).
_BLOCK_PAGE_KEYS = ("page_idx", "page", "page_number", "page_no")
_BLOCK_ASSET_KEYS = ("img_path", "image_path", "path", "image")
_BLOCK_LOCATION_KEYS = ("location", "position")


class LoadedDocuments(list):
    """The documents of one ``load()`` plus that load's image coverage.

    A plain ``list`` in every other respect, so existing callers and test
    doubles that expect a list keep working unchanged.
    """

    __slots__ = ("image_coverage", "image_coverage_warning")

    def __init__(
        self,
        documents: Iterable[Any] = (),
        *,
        image_coverage: dict[str, Any] | None = None,
        image_coverage_warning: str | None = None,
    ) -> None:
        super().__init__(documents)
        self.image_coverage = image_coverage
        self.image_coverage_warning = image_coverage_warning


class _ImageCoverage:
    """Mutable accumulator for one load; ``finish()`` freezes it to a dict."""

    def __init__(self) -> None:
        self.text_sources = 0
        self.parser_no_assets = 0
        #: (origin, asset_ref) → final reason (``None`` means "indexed").
        self._reasons: dict[tuple[str, str], str | None] = {}
        self._anonymous = 0

    def note_parser_without_assets(self) -> None:
        """A parser document whose images we cannot verify at all."""
        self.parser_no_assets += 1

    def _anonymous_ref(self) -> str:
        self._anonymous += 1
        return f"asset-{self._anonymous:03d}"

    def observe(self, origin: Any, asset_ref: str | None, reason: str | None) -> None:
        """Record one *observed* asset exactly once (first reason wins)."""
        key = (str(origin), asset_ref or self._anonymous_ref())
        if key in self._reasons:
            return
        self._reasons[key] = reason

    def indexed(self, origin: Any, asset_ref: str) -> None:
        self.observe(origin, asset_ref, None)

    @property
    def images_indexed(self) -> int:
        return sum(1 for reason in self._reasons.values() if reason is None)

    @property
    def images_skipped(self) -> int:
        return sum(1 for reason in self._reasons.values() if reason is not None)

    def finish(self) -> tuple[dict[str, Any], str | None]:
        counts = {reason: 0 for reason in SKIP_REASONS}
        for reason in self._reasons.values():
            if reason is not None:
                counts[reason] = counts.get(reason, 0) + 1
        counts[SKIP_PARSER_NO_ASSETS] += self.parser_no_assets
        coverage = {
            "text_sources": self.text_sources,
            "images_seen": len(self._reasons),
            "images_indexed": self.images_indexed,
            "images_skipped": self.images_skipped,
            "skip_reasons": {
                reason: counts[reason] for reason in SKIP_REASONS if counts[reason]
            },
        }
        warning = (
            IMAGE_COVERAGE_WARNING
            if self.images_skipped or self.parser_no_assets
            else None
        )
        return coverage, warning


@dataclass(frozen=True)
class _ImageSource:
    """An image to index, plus the provenance its citation needs.

    ``path`` is the image file on disk (what gets read and, on the legacy
    multimodal path, embedded and served). ``origin`` is the document it belongs
    to: the image itself for a standalone image file, or the source PDF/e-book
    for an image extracted during parsing — so retrieval cites the source
    document rather than an opaque cache asset. ``asset_ref`` is the constrained
    *relative* asset id and ``source_file`` the trusted original file name.
    """

    path: Path
    origin: Path
    asset_ref: str
    source_file: str
    page: int | None = None
    location: str | None = None


def _is_regular_leaf(path: Path) -> bool:
    """True only for a regular file that is *not* a symlink."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat_module.S_ISREG(info.st_mode)


def _leaf_size(path: Path) -> int | None:
    """Size of a safely readable regular leaf, or ``None`` when it is not one."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if stat_module.S_ISLNK(info.st_mode) or not stat_module.S_ISREG(info.st_mode):
        return None
    return info.st_size


def _source_mimetype(path: Path) -> str:
    """The MIME type of an *already inspected* image leaf."""
    inspection = inspect_image_file(path)
    return inspection.mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _normalise_asset_path(raw: str) -> str | None:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


class LlamaIndexDocumentLoader:
    """Convert source files into LlamaIndex ``Document`` / ``ImageNode`` objects."""

    def __init__(self, logger=None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def load(self, file_paths: Iterable[str]) -> LoadedDocuments:
        documents: list[Any] = []
        coverage = _ImageCoverage()
        image_sources: list[_ImageSource] = []
        #: Per-source-document byte/count budget: reused across every image of
        #: one document so a single load cannot admit more than the C09 caps.
        budgets: dict[str, ImageBudget] = {}
        classification = FileTypeRouter.classify_files(list(file_paths))

        for file_path_str in classification.parser_files:
            file_path = Path(file_path_str)
            self.logger.info(f"Parsing document: {file_path.name}")
            # MinerU cloud parsing blocks end to end (upload + 300s polling +
            # archive download) on a synchronous httpx.Client — running it on
            # the event loop stalls every other request for the whole PDF
            # (same class of bug as upstream #761/#777). Hand it to a thread.
            text, extracted_images = await asyncio.to_thread(
                self._parse_document, file_path, coverage
            )
            if self._append_if_nonempty(documents, file_path, text):
                coverage.text_sources += 1
            if extracted_images:
                image_sources.extend(extracted_images)
            else:
                # The parser produced no verifiable asset: record "images of
                # this document are unverified", never "this document has no
                # images" (C09).
                coverage.note_parser_without_assets()

        for file_path_str in classification.text_files:
            file_path = Path(file_path_str)
            self.logger.info(f"Parsing text: {file_path.name}")
            text = await FileTypeRouter.read_text_file(str(file_path))
            if self._append_if_nonempty(documents, file_path, text):
                coverage.text_sources += 1

        for file_path_str in classification.image_files:
            path = Path(file_path_str)
            source = self._standalone_source(path, coverage)
            if source is not None:
                image_sources.append(source)

        if image_sources:
            documents.extend(
                await self._index_images(image_sources, coverage=coverage, budgets=budgets)
            )

        for file_path_str in classification.unsupported:
            self.logger.warning(f"Skipped unsupported file: {Path(file_path_str).name}")

        image_coverage, image_coverage_warning = coverage.finish()
        if image_coverage_warning:
            self.logger.warning(
                "Image coverage for this load: %s (warning=%s)",
                image_coverage,
                image_coverage_warning,
            )
        else:
            self.logger.info(f"Image coverage for this load: {image_coverage}")
        return LoadedDocuments(
            documents,
            image_coverage=image_coverage,
            image_coverage_warning=image_coverage_warning,
        )

    # -- parsing ----------------------------------------------------------
    def _parse_document(
        self, file_path: Path, coverage: _ImageCoverage
    ) -> tuple[str, list[_ImageSource]]:
        """Parse a document through the shared, engine-pluggable parse layer.

        Returns ``(text, extracted_images)``. A parse failure (engine
        unavailable, unsupported format for the active engine, or models not
        ready) is logged and the file is skipped — matching the sibling
        LightRAG/GraphRAG pipelines — rather than aborting the whole batch.
        """
        from deeptutor.services.parsing import ParserError, get_parse_service

        try:
            parsed = get_parse_service().parse(file_path)
        except ParserError as exc:
            self.logger.warning(
                f"Skipped {file_path.name}: the active document-parsing engine could "
                f"not handle it ({exc}). Change the engine in Settings → Document Parsing."
            )
            return "", []

        text = parsed.markdown.strip() or self._text_from_blocks(parsed.blocks)
        images = self._collect_asset_images(
            parsed.asset_dir, origin=file_path, coverage=coverage, blocks=parsed.blocks
        )
        return text, images

    @staticmethod
    def _text_from_blocks(blocks: list[dict] | None) -> str:
        """Fall back to concatenating block text when an engine emits no markdown."""
        if not blocks:
            return ""
        parts = [
            str(block.get("text") or block.get("content") or "").strip()
            for block in blocks
            if isinstance(block, dict)
        ]
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _block_positions(blocks: list[dict] | None) -> dict[str, tuple[int | None, str | None]]:
        """Asset path → ``(page, location)`` **as reported by the parser**.

        Only fields the parse engine actually emitted are used, and the page is
        passed through unchanged (MinerU's ``page_idx`` stays 0-based). A block
        without a page key yields ``None`` — the loader never invents one and
        never reads a page out of an asset file name.
        """
        positions: dict[str, tuple[int | None, str | None]] = {}
        for block in blocks or []:
            if not isinstance(block, dict):
                continue
            page: int | None = None
            for key in _BLOCK_PAGE_KEYS:
                value = block.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    page = value
                    break
            location: str | None = None
            for key in _BLOCK_LOCATION_KEYS:
                value = block.get(key)
                if isinstance(value, str) and value.strip():
                    location = value.strip()
                    break
            for key in _BLOCK_ASSET_KEYS:
                raw = block.get(key)
                if not isinstance(raw, str):
                    continue
                relative = _normalise_asset_path(raw)
                if relative:
                    positions.setdefault(relative, (page, location))
                break
        return positions

    @staticmethod
    def _position_for(
        asset_ref: str, positions: dict[str, tuple[int | None, str | None]]
    ) -> tuple[int | None, str | None]:
        if not positions:
            return None, None
        if asset_ref in positions:
            return positions[asset_ref]
        # The engine sometimes writes the cache-absolute path; accept only a
        # real path-boundary suffix match, never a bare file-name guess.
        for key, value in positions.items():
            if key.endswith("/" + asset_ref):
                return value
        return None, None

    def _collect_asset_images(
        self,
        asset_dir: Path | None,
        *,
        origin: Path,
        coverage: _ImageCoverage,
        blocks: list[dict] | None = None,
    ) -> list[_ImageSource]:
        """Gather images the parse engine extracted into ``asset_dir``.

        Engines that don't extract images (text-only, markitdown) leave
        ``asset_dir`` empty, so this returns nothing and the document is indexed
        as text alone. The walk is constrained to the asset root: it never
        follows a symlink and never yields a leaf outside the root, and a leaf
        that cannot be safely named is reported as an unreadable asset instead
        of being silently dropped.
        """
        if not asset_dir:
            return []
        # The root itself must be a real directory chain: a symlinked root (or a
        # symlinked parent component) would hand us a tree that belongs to
        # somebody else, so it is refused *before* any is_dir/walk/read and the
        # document is reported as unverified instead of enumerated around it.
        root = confined_image_root(asset_dir)
        if root is None:
            self.logger.warning(
                "Parsing asset root for %s is not a real directory chain; "
                "reporting its images as unverified",
                origin.name,
            )
            return []

        positions = self._block_positions(blocks)
        images: list[_ImageSource] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for filename in sorted(filenames):
                child = Path(dirpath) / filename
                if child.suffix.lower() not in FileTypeRouter.IMAGE_EXTENSIONS:
                    continue
                if not is_regular_file_leaf(child):
                    coverage.observe(origin, None, SKIP_UNSUPPORTED_IMAGE)
                    self.logger.warning(
                        "Skipped image asset that is not a regular file inside the "
                        "parsing asset root: %s",
                        child.name,
                    )
                    continue
                try:
                    asset_ref = asset_ref_from_root(child, root)
                except ValueError:
                    coverage.observe(origin, None, SKIP_UNSUPPORTED_IMAGE)
                    self.logger.warning(
                        "Skipped image asset outside the parsing asset root: %s",
                        child.name,
                    )
                    continue
                page, location = self._position_for(asset_ref, positions)
                images.append(
                    _ImageSource(
                        path=child,
                        origin=origin,
                        asset_ref=asset_ref,
                        source_file=origin.name,
                        page=page,
                        location=location,
                    )
                )
        if images:
            self.logger.info(
                f"Extracted {len(images)} image(s) from {origin.name} for indexing"
            )
        return images

    def _standalone_source(self, path: Path, coverage: _ImageCoverage) -> _ImageSource | None:
        """A directly uploaded image file; its own name is its asset id."""
        if not is_regular_file_leaf(path):
            coverage.observe(path, None, SKIP_UNSUPPORTED_IMAGE)
            self.logger.warning(
                "Skipped image that is not a regular file: %s", path.name
            )
            return None
        try:
            asset_ref = standalone_asset_ref(path)
            source_file = path.name
        except ValueError:
            coverage.observe(path, None, SKIP_UNSUPPORTED_IMAGE)
            self.logger.warning("Skipped image with an unsafe file name for citation")
            return None
        return _ImageSource(
            path=path, origin=path, asset_ref=asset_ref, source_file=source_file
        )

    # -- image indexing ---------------------------------------------------
    def _legacy_image_node_clients(self) -> tuple[Any, Any] | None:
        """``(embedding, llm)`` when the multimodal ``ImageNode`` path applies.

        The path needs *both* a multimodal embedding model and a multimodal main
        LLM. Anything less (including a model catalog that cannot resolve the
        main LLM at all) falls back to the text-description path rather than
        dropping the images.
        """
        try:
            embedding_client = get_embedding_client()
        except Exception as exc:
            self.logger.info(
                "Embedding client unavailable for the multimodal image path (%s); "
                "using text descriptions instead.",
                type(exc).__name__,
            )
            return None
        if not embedding_client.supports_multimodal_contents():
            return None
        try:
            llm_client = get_llm_client()
        except Exception as exc:
            self.logger.info(
                "Main LLM unavailable for the multimodal image path (%s); "
                "using text descriptions instead.",
                type(exc).__name__,
            )
            return None
        if not llm_client.supports_multimodal_images():
            return None
        return embedding_client, llm_client

    async def _index_images(
        self,
        sources: list[_ImageSource],
        *,
        coverage: _ImageCoverage,
        budgets: dict[str, ImageBudget],
    ) -> list[Any]:
        """Index every observed asset exactly once, recording one final reason."""
        candidates: list[_ImageSource] = []
        processed: set[tuple[str, str]] = set()
        for source in sources:
            key = (str(source.origin), source.asset_ref)
            if key in processed:  # the same asset listed twice for one origin
                continue
            processed.add(key)
            if _leaf_size(source.path) is None:
                # Vanished, replaced by a symlink or otherwise not a regular
                # leaf any more: a named skip, never a silent drop.
                coverage.observe(source.origin, source.asset_ref, SKIP_UNSUPPORTED_IMAGE)
                continue
            candidates.append(source)

        clients = self._legacy_image_node_clients()
        if clients is not None:
            return await self._load_image_nodes(
                candidates, coverage=coverage, budgets=budgets, clients=clients
            )
        return await self._load_text_descriptions(
            candidates, coverage=coverage, budgets=budgets
        )

    def _accept_image(self, source: _ImageSource, budgets: dict[str, ImageBudget]) -> bool:
        """Accept one image against its document's attempt budget.

        Acceptance happens **before** the attempt and is charged even when the
        attempt then fails: the caps bound how many images one document may
        offer to vision (12 images / 12 MiB), not how many succeed. Otherwise a
        provider that rejects everything would be asked about every image in the
        document. A duplicate asset is deduplicated before this point, so one
        real image consumes exactly one slot, and an ``auto`` main→dedicated
        retry stays inside the same accepted slot.
        """
        budget = budgets.setdefault(str(source.origin), ImageBudget())
        size = _leaf_size(source.path) or 0
        if (
            budget.count >= budget.max_images
            or budget.total_bytes + size > budget.max_total_bytes
        ):
            return False
        budget.count += 1
        budget.total_bytes += size
        return True

    def _skip_over_budget(self, source: _ImageSource, coverage: _ImageCoverage) -> None:
        coverage.observe(source.origin, source.asset_ref, SKIP_BUDGET)
        self.logger.warning(
            "Skipped image beyond the per-document attempt budget: %s", source.asset_ref
        )

    async def _load_text_descriptions(
        self,
        sources: list[_ImageSource],
        *,
        coverage: _ImageCoverage,
        budgets: dict[str, ImageBudget],
    ) -> list[Document]:
        """Default path: vision description → ordinary text ``Document``."""
        documents: list[Document] = []
        for source in sources:
            if not self._accept_image(source, budgets):
                self._skip_over_budget(source, coverage)
                continue
            try:
                description = await describe_image_for_index(
                    source.path,
                    source_file=source.source_file,
                    page=source.page,
                    location=source.location,
                    asset_ref=source.asset_ref,
                )
            except Exception as exc:
                # The helper names its own failures; reaching this point means
                # something unexpected happened for this one asset. It must not
                # lose the rest of the document.
                self.logger.error(
                    "Image description raised for %s of %s (%s)",
                    source.asset_ref,
                    source.source_file,
                    type(exc).__name__,
                    exc_info=True,
                )
                coverage.observe(source.origin, source.asset_ref, SKIP_VISION_FAILED)
                continue
            if description.skip_reason is not None:
                coverage.observe(source.origin, source.asset_ref, description.skip_reason)
                self.logger.warning(
                    "Skipped image %s of %s: %s",
                    source.asset_ref,
                    source.source_file,
                    description.skip_reason,
                )
                continue
            coverage.indexed(source.origin, source.asset_ref)
            documents.append(
                Document(
                    text=description.text,
                    metadata=_description_metadata(source, description),
                )
            )
        if documents:
            self.logger.info(
                f"Indexed {len(documents)} image description(s) as text documents"
            )
        return documents

    async def _load_image_nodes(
        self,
        sources: list[_ImageSource],
        *,
        coverage: _ImageCoverage,
        budgets: dict[str, ImageBudget],
        clients: tuple[Any, Any],
    ) -> list[ImageNode]:
        embedding_client, llm_client = clients

        embedded: list[_ImageSource] = []
        descriptions: list[str] = []
        contents = []
        for source in sources:
            if not self._accept_image(source, budgets):
                self._skip_over_budget(source, coverage)
                continue
            # The legacy path enforces exactly the same single-image gate as the
            # text path — leaf, 1200..4 MiB and real format — so "keep the old
            # path" is never an exemption from the C09 limits.
            inspection = await asyncio.to_thread(inspect_image_file, source.path)
            if inspection.skip_reason is not None:
                coverage.observe(source.origin, source.asset_ref, inspection.skip_reason)
                self.logger.warning(
                    "Skipped image %s of %s: %s",
                    source.asset_ref,
                    source.source_file,
                    inspection.skip_reason,
                )
                continue
            try:
                payload = image_payload(inspection)
                description = (
                    await describe_image_text(
                        llm_client.config,
                        image_base64=payload["base64"],
                        mime_type=payload["mime_type"],
                        image_filename=source.source_file,
                    )
                ).strip()
                if not description:
                    self.logger.warning(
                        "Skipped image because the configured multimodal LLM "
                        f"returned no description: {source.path.name}"
                    )
                    coverage.observe(source.origin, source.asset_ref, SKIP_VISION_FAILED)
                    continue
                contents.append({"image": payload["data_uri"]})
                embedded.append(source)
                descriptions.append(description)
            except Exception as exc:
                self.logger.warning(
                    "Failed to describe image %s with configured multimodal LLM "
                    "(binding=%s, model=%s, reason=%s)",
                    source.path.name,
                    getattr(getattr(llm_client, "config", None), "binding", ""),
                    getattr(getattr(llm_client, "config", None), "model", ""),
                    failure_kind(exc),
                )
                coverage.observe(source.origin, source.asset_ref, SKIP_VISION_FAILED)

        if not contents:
            return []

        try:
            embeddings = await embedding_client.embed_contents(contents)
        except Exception as exc:
            self.logger.error(
                "Failed to embed image contents with configured multimodal embedding "
                "provider/model (binding=%s, model=%s): %s",
                embedding_client.config.binding,
                embedding_client.config.model,
                exc,
            )
            for source in embedded:
                coverage.observe(source.origin, source.asset_ref, SKIP_VISION_FAILED)
            return []
        nodes: list[ImageNode] = []
        for source, description, embedding in zip(embedded, descriptions, embeddings):
            mimetype = _source_mimetype(source.path)
            nodes.append(
                ImageNode(
                    text=f"[Image] {source.source_file}\n\n{description}",
                    image_path=str(source.path),
                    image_mimetype=mimetype,
                    metadata={
                        "file_name": source.source_file,
                        "file_path": str(source.origin),
                        "content_type": "image",
                        "image_description": description,
                        "asset_ref": source.asset_ref,
                    },
                    embedding=embedding,
                )
            )
            coverage.indexed(source.origin, source.asset_ref)
            self.logger.info(f"Loaded image: {source.path.name} ({len(embedding)}D vector)")
        return nodes

    def _append_if_nonempty(self, documents: list[Any], file_path: Path, text: str) -> bool:
        """Append a text ``Document``; returns whether body text was indexed."""
        if text.strip():
            documents.append(
                Document(
                    text=text,
                    metadata={
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                    },
                )
            )
            self.logger.info(f"Loaded: {file_path.name} ({len(text)} chars)")
            return True
        self.logger.warning(f"Skipped empty document: {file_path.name}")
        return False


def _description_metadata(source: _ImageSource, description: Any) -> dict[str, Any]:
    """Document metadata for one image description.

    Carries the citation facts (source file, relative asset id, the parser's own
    page/location when it reported one) and nothing else: no base64, no cache
    path, no provider text.
    """
    metadata: dict[str, Any] = {
        "file_name": source.source_file,
        "file_path": str(source.origin),
        "content_kind": description.content_kind,
        "asset_ref": source.asset_ref,
    }
    if description.page is not None:
        metadata["page"] = description.page
    if description.location:
        metadata["location"] = description.location
    return metadata


__all__ = [
    "IMAGE_COVERAGE_WARNING",
    "IMAGE_DESCRIPTION_PROMPT",
    "IMAGE_DESCRIPTION_SYSTEM_PROMPT",
    "LlamaIndexDocumentLoader",
    "LoadedDocuments",
]
