#!/usr/bin/env python
"""Knowledge base initialization through the selected RAG provider."""

from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import datetime
import logging
from pathlib import Path
import shutil
from typing import Optional

from deeptutor.knowledge.naming import validate_knowledge_base_name
from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker
from deeptutor.services.config import resolve_llm_runtime_config
from deeptutor.services.file_io import atomic_write_json, atomic_write_text
from deeptutor.services.rag.factory import normalize_provider_name
from deeptutor.services.rag.file_routing import FileTypeRouter
from deeptutor.services.rag.service import RAGService
from deeptutor.subjects import json_store

logger = logging.getLogger(__name__)


class KnowledgeBaseInitializer:
    """Knowledge base initializer."""

    def __init__(
        self,
        kb_name: str,
        base_dir: str = "./data/knowledge_bases",
        api_key: str | None = None,
        base_url: str | None = None,
        progress_tracker: ProgressTracker | None = None,
        rag_provider: str | None = None,
    ):
        self.kb_name = validate_knowledge_base_name(kb_name)
        self.base_dir = Path(base_dir)
        self.kb_dir = self.base_dir / self.kb_name

        self.raw_dir = self.kb_dir / "raw"
        self.llamaindex_storage_dir = self.kb_dir / "llamaindex_storage"

        self.api_key = api_key
        self.base_url = base_url
        self.progress_tracker = progress_tracker or ProgressTracker(self.kb_name, self.base_dir)
        self.rag_provider = normalize_provider_name(rag_provider)
        #: This run's image coverage (P1-27), projected from the pipeline's
        #: load result into metadata.json, .progress.json and the task events.
        self.image_coverage: dict | None = None
        self.image_coverage_warning: str | None = None

    def record_image_coverage(self, coverage: dict | None, warning: str | None = None) -> None:
        """Store the coverage of *this* indexing run (never a previous one).

        The value is a deep copy: the pipeline may keep mutating its own
        accumulator after publishing, and a published status must not change
        under the reader's feet.
        """
        self.image_coverage = copy.deepcopy(coverage) if isinstance(coverage, dict) else None
        self.image_coverage_warning = warning or None

    def _reset_image_coverage(self) -> None:
        self.image_coverage = None
        self.image_coverage_warning = None
        reset = getattr(self.progress_tracker, "reset_image_coverage", None)
        if callable(reset):
            reset()

    def _register_to_config(self) -> None:
        """Register KB in kb_config.json with initializing state."""
        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager

            manager = KnowledgeBaseManager(base_dir=str(self.base_dir))
            manager.config = manager._load_config()
            if self.kb_name in manager.config.get("knowledge_bases", {}):
                return

            manager.update_kb_status(
                name=self.kb_name,
                status="initializing",
                progress={
                    "stage": "initializing",
                    "message": "Creating directory structure...",
                    "percent": 0,
                    "current": 0,
                    "total": 0,
                },
            )
            manager.config = manager._load_config()
            manager.config.setdefault("knowledge_bases", {}).setdefault(self.kb_name, {})[
                "rag_provider"
            ] = self.rag_provider
            manager._save_config()
        except Exception as e:
            logger.warning(f"Failed to register KB to config: {e}")

    def _update_metadata_with_provider(self, provider: str) -> None:
        """Merge this run's facts into ``metadata.json``, strictly.

        The existing file is read with the S03 strict object reader: a missing
        file is simply a missing file, while an existing file that is corrupt,
        not an object, or not readable raises the normal storage error and is
        left byte-for-byte alone — it is never "treated as empty" and then
        overwritten by a merged object that silently dropped the user's data.
        """
        metadata_file = self.kb_dir / "metadata.json"
        metadata = json_store.read_object(metadata_file, default={})

        metadata["rag_provider"] = provider
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata["last_updated"] = timestamp
        metadata["last_indexed_at"] = timestamp
        metadata["last_indexed_count"] = len(
            FileTypeRouter.collect_supported_files(self.raw_dir, recursive=True)
        )
        metadata["last_indexed_action"] = "create"
        # Additive coverage of the run that just finished: the merge above keeps
        # every pre-existing field. A successful run that measured nothing
        # *clears* the previous run's numbers instead of inheriting them — the
        # stable state must say "unverified", never a stale count.
        if self.image_coverage is not None:
            metadata["image_coverage"] = copy.deepcopy(self.image_coverage)
            metadata["image_coverage_warning"] = self.image_coverage_warning
        else:
            metadata.pop("image_coverage", None)
            metadata.pop("image_coverage_warning", None)

        atomic_write_json(metadata_file, metadata)

        try:
            # Scope the config write to *this* initializer's own KB root.
            # ``get_kb_config_service()`` is hard-wired to the caller's global
            # KB root, so using it here registered a subject-scoped KB in the
            # global registry as a phantom entry (no directory behind it) every
            # time a subject material finished indexing.
            from deeptutor.services.config.knowledge_base_config import (
                KnowledgeBaseConfigService,
            )

            service = KnowledgeBaseConfigService.get_instance(
                self.base_dir / "kb_config.json"
            )
            service.set_rag_provider(self.kb_name, provider)
            service.set_kb_config(self.kb_name, {"needs_reindex": False})
        except Exception as config_err:
            logger.warning(f"Failed to persist provider in centralized config: {config_err}")

    def create_directory_structure(self) -> None:
        """Create KB directory structure."""
        logger.info(f"Creating directory structure for knowledge base: {self.kb_name}")

        for dir_path in [
            self.raw_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

        metadata = {
            "name": self.kb_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": f"Knowledge base: {self.kb_name}",
            "version": "1.0",
            "rag_provider": self.rag_provider,
            "needs_reindex": False,
        }

        atomic_write_json(self.kb_dir / "metadata.json", metadata)

        self._register_to_config()

    def copy_documents(self, source_files: list[str]) -> list[str]:
        """Copy source documents into raw directory."""
        copied_files: list[str] = []
        for source in source_files:
            source_path = Path(source)
            if not source_path.exists() or not source_path.is_file():
                logger.warning(f"Source file not found: {source}")
                continue
            dest_path = self.raw_dir / source_path.name
            shutil.copy2(source_path, dest_path)
            copied_files.append(str(dest_path))
        return copied_files

    async def process_documents(
        self,
    ) -> bool:
        """Process documents with the KB's bound provider."""
        provider = self.rag_provider

        # This run starts here: drop the previous run's image coverage *before*
        # the first progress event, the file enumeration or anything else that
        # can fail, so no early event and no stable state can attribute the old
        # measurement to this run (the tracker's task id may be None on the CLI
        # path, so an id change is not a reliable boundary).
        self._reset_image_coverage()

        self.progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Starting to process documents with {provider} provider...",
            current=0,
            total=0,
        )

        # recursive=True so documents organized into folders are indexed too
        # (folders are display-only and don't otherwise affect retrieval).
        doc_files = FileTypeRouter.collect_supported_files(self.raw_dir, recursive=True)

        if not doc_files:
            self.progress_tracker.update(
                ProgressStage.ERROR,
                "No documents found to process",
                error="No documents found",
            )
            raise ValueError("No documents found to process")

        self.progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Found {len(doc_files)} documents, starting to process...",
            current=0,
            total=len(doc_files),
        )

        rag_service = RAGService(
            kb_base_dir=str(self.base_dir),
            provider=provider,
        )
        file_paths = [str(doc_file) for doc_file in doc_files]

        def _on_progress(batch_num, total_batches):
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Embedding batches: {batch_num}/{total_batches} complete",
                current=batch_num,
                total=total_batches,
            )

        def _on_image_coverage(coverage, warning=None):
            self.record_image_coverage(coverage, warning)

        commit_state = {"called": False, "rollback_needed": False, "original": None}
        metadata_file = self.kb_dir / "metadata.json"

        def _rollback_index_metadata() -> None:
            if not commit_state["rollback_needed"]:
                return
            original = commit_state["original"]
            if json_store._read_text(metadata_file) != original:
                if original is None:
                    metadata_file.unlink(missing_ok=True)
                else:
                    atomic_write_text(metadata_file, original)
            commit_state["rollback_needed"] = False

        def _commit_index_metadata() -> None:
            """The required metadata merge, inside the pipeline's publish step.

            The LlamaIndex pipeline runs this *before* the new index version
            becomes readable, so a metadata failure cannot leave a published
            version that the read path would already select.
            """
            commit_state["called"] = True
            # Preserve the exact bytes (including original whitespace) and the
            # absent-file case before a commit that may partially succeed.
            commit_state["original"] = json_store._read_text(metadata_file)
            commit_state["rollback_needed"] = True
            self._update_metadata_with_provider(provider)

        try:
            success = await rag_service.initialize(
                kb_name=self.kb_name,
                file_paths=file_paths,
                progress_callback=_on_progress,
                image_coverage_callback=_on_image_coverage,
                index_commit_callback=_commit_index_metadata,
                index_rollback_callback=_rollback_index_metadata,
            )
            if not success:
                self.progress_tracker.update(
                    ProgressStage.ERROR,
                    "Document processing failed",
                    error="RAG pipeline returned failure",
                    image_coverage=self.image_coverage,
                    image_coverage_warning=self.image_coverage_warning,
                )
                raise RuntimeError("RAG pipeline returned failure")

            if not commit_state["called"]:
                # A provider pipeline without the publish-boundary seam still
                # needs the metadata merge, exactly as before.
                _commit_index_metadata()
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                "Documents processed successfully",
                current=len(doc_files),
                total=len(doc_files),
                image_coverage=self.image_coverage,
                image_coverage_warning=self.image_coverage_warning,
            )
        except Exception as e:
            _rollback_index_metadata()
            error_msg = str(e)
            logger.error(f"Error processing documents: {error_msg}")
            self.progress_tracker.update(
                ProgressStage.ERROR,
                "Failed to process documents",
                error=error_msg,
                image_coverage=self.image_coverage,
                image_coverage_warning=self.image_coverage_warning,
            )
            raise

        await self.fix_structure()
        await self.display_statistics_generic()
        return True

    async def fix_structure(self) -> None:
        """No-op retained for compatibility with previous pipelines."""
        logger.info("Skipping legacy structure cleanup")

    async def display_statistics_generic(self) -> None:
        """Display basic statistics."""
        raw_files = list(self.raw_dir.glob("*")) if self.raw_dir.exists() else []
        from deeptutor.services.rag.index_probe import inspect_kb_versions

        index_versions = inspect_kb_versions(self.kb_dir, self.rag_provider)

        logger.info("=" * 50)
        logger.info("Knowledge Base Statistics")
        logger.info("=" * 50)
        logger.info(f"Raw documents: {len(raw_files)}")
        logger.info(f"Index versions: {len(index_versions)}")
        logger.info(f"Provider used: {self.rag_provider}")
        logger.info("=" * 50)


async def initialize_knowledge_base(
    kb_name: str,
    source_files: list[str],
    base_dir: str = "./data/knowledge_bases",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    rag_provider: Optional[str] = None,
) -> bool:
    """Convenience initializer used by CLI wrappers."""
    from deeptutor.knowledge.manager import KnowledgeBaseManager

    manager = KnowledgeBaseManager(base_dir=base_dir)
    initializer = KnowledgeBaseInitializer(
        kb_name=kb_name,
        base_dir=base_dir,
        api_key=api_key,
        base_url=base_url,
        rag_provider=rag_provider,
    )
    try:
        initializer.create_directory_structure()
        copied_files = initializer.copy_documents(source_files)
        await initializer.process_documents()
        manager.update_kb_status(
            name=kb_name,
            status="ready",
            progress={
                "stage": "completed",
                "message": "Knowledge base initialization complete!",
                "percent": 100,
                "current": 1,
                "total": 1,
                "file_name": "",
                "error": None,
                "timestamp": datetime.now().isoformat(),
                "indexed_count": len(copied_files),
                "index_changed": True,
                "index_action": "create",
                # This convenience entry point writes its own final progress, so
                # it has to carry the coverage too instead of dropping it.
                **(
                    {
                        "image_coverage": initializer.image_coverage,
                        "image_coverage_warning": initializer.image_coverage_warning,
                    }
                    if initializer.image_coverage is not None
                    else {}
                ),
            },
        )
        return True
    except Exception as exc:
        manager.update_kb_status(
            name=kb_name,
            status="error",
            progress={
                "stage": "error",
                "message": "Knowledge base initialization failed",
                "percent": 0,
                "current": 0,
                "total": 1,
                "file_name": "",
                "error": str(exc),
                "timestamp": datetime.now().isoformat(),
                **(
                    {
                        "image_coverage": initializer.image_coverage,
                        "image_coverage_warning": initializer.image_coverage_warning,
                    }
                    if initializer.image_coverage is not None
                    else {}
                ),
            },
        )
        raise


async def main() -> None:
    try:
        llm_config = resolve_llm_runtime_config()
        default_api_key = llm_config.api_key
        default_base_url = llm_config.effective_url
    except Exception:
        default_api_key = ""
        default_base_url = ""

    parser = argparse.ArgumentParser(description="Initialize a new knowledge base from documents")
    parser.add_argument("name", help="Knowledge base name")
    parser.add_argument("--docs", nargs="+", help="Document files to process")
    parser.add_argument("--docs-dir", help="Directory containing documents to process")
    parser.add_argument("--base-dir", default="./knowledge_bases")
    parser.add_argument("--api-key", default=default_api_key)
    parser.add_argument("--base-url", default=default_base_url)
    parser.add_argument("--skip-processing", action="store_true")

    args = parser.parse_args()

    doc_files: list[str] = []
    if args.docs:
        doc_files.extend(args.docs)
    if args.docs_dir:
        docs_dir = Path(args.docs_dir)
        if docs_dir.exists() and docs_dir.is_dir():
            doc_files.extend(str(f) for f in FileTypeRouter.collect_supported_files(docs_dir))

    initializer = KnowledgeBaseInitializer(
        kb_name=args.name,
        base_dir=args.base_dir,
        api_key=args.api_key,
        base_url=args.base_url,
    )
    initializer.create_directory_structure()

    if doc_files:
        initializer.copy_documents(doc_files)

    if not args.skip_processing:
        await initializer.process_documents()


if __name__ == "__main__":
    asyncio.run(main())
