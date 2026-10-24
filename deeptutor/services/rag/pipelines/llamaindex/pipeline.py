"""LlamaIndex-backed RAG pipeline orchestration."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import logging
from pathlib import Path
import shutil
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from deeptutor.runtime.home import get_runtime_data_root
from deeptutor.services.embedding import get_embedding_config
from deeptutor.services.rag.embedding_signature import signature_from_embedding_config
from deeptutor.services.rag.index_versioning import (
    EmbeddingSignature,
    resolve_storage_dir_for_read,
    resolve_storage_dir_for_rebuild,
    write_version_meta,
)
from deeptutor.services.rag.kb_paths import resolve_kb_dir

from . import storage
from .config import default_top_k
from .document_loader import LlamaIndexDocumentLoader
from .embedding_adapter import (
    configure_llamaindex_settings,
    set_progress_callback,
    verify_embedding_connectivity,
)
from .errors import search_error_result

DEFAULT_KB_BASE_DIR = str(get_runtime_data_root() / "knowledge_bases")

# ---- Indexing stall guard (ported from upstream v1.5.17) -------------------
# How long an indexing step may run without reporting any progress before it is
# treated as stalled (see _run_with_stall_guard).
_INDEX_STALL_TIMEOUT_SECONDS = 600.0
# How often the stall guard checks the progress heartbeat.
_INDEX_STALL_POLL_SECONDS = 5.0
_INDEX_WORKERS: dict[str, threading.Event] = {}
_INDEX_WORKERS_LOCK = threading.Lock()

#: Heartbeats of the guard runs that are currently live. The adapter itself is
#: given **one stable dispatcher** (see :func:`_dispatch_progress`), never a
#: per-run closure: an embedding call must update the heartbeat of the worker
#: that actually made it, not "whichever run installed a callback last".
_PROGRESS_CALLBACKS: list[Any] = []
_PROGRESS_CALLBACK_LOCK = threading.Lock()

#: The heartbeat belonging to the *current worker context*. Each guarded call
#: sets it inside its own copied context (``contextvars.copy_context().run``),
#: so it follows the work into its worker thread and into any event loop that
#: thread creates — while staying invisible to every other worker.
_CURRENT_HEARTBEAT: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "deeptutor_index_heartbeat", default=None
)

SignatureProvider = Callable[[], EmbeddingSignature | None]

_LOGGER = logging.getLogger(__name__)


class IndexingStallError(RuntimeError):
    """Raised when an indexing operation makes no progress for too long."""


def _worker_busy_error() -> IndexingStallError:
    return IndexingStallError(
        "A previous indexing worker for this knowledge base is still running. "
        "Wait for it to finish or restart DeepTutor before retrying."
    )


def _worker_key(key: str | Path) -> str:
    """The single controlled worker identity: the resolved KB directory."""
    return str(Path(key).expanduser().resolve())


def index_worker_state(key: str | Path) -> dict:
    """Read-only busy view for one KB, using the same controlled key.

    ``key`` is normalized exactly like the claim/release path (the resolved KB
    directory), so a caller may pass either a ``Path`` or the same string the
    guard was given. A *terminal task status* is deliberately not consulted
    here: a task can be marked ``error`` while its synchronous worker thread is
    still running, and that thread still owns the source it is indexing.
    """
    resolved = _worker_key(key)
    with _INDEX_WORKERS_LOCK:
        marker = _INDEX_WORKERS.get(resolved)
        if marker is None:
            return {"key": resolved, "registered": False, "alive": False}
        return {
            "key": resolved,
            "registered": True,
            "alive": not marker.is_set(),
        }


def current_worker_heartbeat() -> Any:
    """The heartbeat registered for the **calling** worker context (or ``None``).

    Inside a guarded worker this is that run's own heartbeat; anywhere else
    (including another KB's worker) it is ``None``, which is exactly the
    attribution the progress dispatcher relies on.
    """
    return _CURRENT_HEARTBEAT.get(None)


def active_progress_callback() -> Any:
    """The callback installed on the embedding adapter (or ``None``).

    While any guarded run is live this is the shared dispatcher, not one run's
    heartbeat: reading it can never tell you "which task" is progressing.
    """
    with _PROGRESS_CALLBACK_LOCK:
        return _dispatch_progress if _PROGRESS_CALLBACKS else None


def _dispatch_progress(*args: Any, **kwargs: Any) -> None:
    """Forward one progress event to the heartbeat of the calling worker.

    No worker context (or a finished one) means the event is dropped: progress
    is never broadcast to every live run, and the newest installed run is never
    used as a stand-in for the others.
    """
    heartbeat = _CURRENT_HEARTBEAT.get(None)
    if heartbeat is None:
        return
    heartbeat(*args, **kwargs)


def _install_progress_callback(callback: Callable[..., Any]) -> None:
    """Register *callback* and make sure the shared dispatcher is installed."""
    with _PROGRESS_CALLBACK_LOCK:
        _PROGRESS_CALLBACKS.append(callback)
        set_progress_callback(_dispatch_progress)


def _restore_progress_callback(callback: Callable[..., Any]) -> None:
    """Drop *callback*; only still-live runs keep the dispatcher installed."""
    with _PROGRESS_CALLBACK_LOCK:
        if callback in _PROGRESS_CALLBACKS:
            _PROGRESS_CALLBACKS.remove(callback)
        if not _PROGRESS_CALLBACKS:
            # Keep the adapter update inside the registry lock. A concurrent
            # installation must not be cleared after it installs a live run.
            set_progress_callback(None)


def _ensure_index_worker_available(key: str) -> None:
    with _INDEX_WORKERS_LOCK:
        marker = _INDEX_WORKERS.get(_worker_key(key))
        if marker is not None and not marker.is_set():
            raise _worker_busy_error()


def _claim_index_worker(key: str | None) -> threading.Event | None:
    if not key:
        return None
    resolved = _worker_key(key)
    event = threading.Event()
    with _INDEX_WORKERS_LOCK:
        existing = _INDEX_WORKERS.get(resolved)
        if existing is not None and not existing.is_set():
            raise _worker_busy_error()
        _INDEX_WORKERS[resolved] = event
    return event


def _release_index_worker(key: str | None, marker: threading.Event | None) -> None:
    if not key or marker is None:
        return
    marker.set()
    resolved = _worker_key(key)
    with _INDEX_WORKERS_LOCK:
        if _INDEX_WORKERS.get(resolved) is marker:
            _INDEX_WORKERS.pop(resolved, None)


async def _run_with_stall_guard(
    fn: Callable[[], Any],
    *,
    progress_callback: Optional[Callable[..., Any]] = None,
    stall_timeout: Optional[float] = None,
    worker_key: str | None = None,
    on_abandoned_worker_exit: Optional[Callable[[], None]] = None,
) -> Any:
    """Run a synchronous indexing step in the executor, failing if it stalls.

    Indexing steps (chunking + embedding) run in a worker thread via
    ``run_in_executor``. A provider that accepts a request but never completes
    it (e.g. a blackholed keep-alive connection) can block that thread
    indefinitely: per-request HTTP timeouts only bound a single attempt, and
    provider retries extend the wait far beyond any reasonable budget. Instead
    of hanging forever, watch the embedding progress heartbeat and fail with a
    clear error once no progress has been reported for ``stall_timeout``
    seconds.

    The sync function keeps running in its thread after a stall is raised —
    Python cannot interrupt arbitrary synchronous code. Its callback becomes
    silent and a same-KB retry is rejected until that thread actually exits.
    """
    if stall_timeout is None:
        stall_timeout = _INDEX_STALL_TIMEOUT_SECONDS

    worker_marker = _claim_index_worker(worker_key)
    progress_live = threading.Event()
    progress_live.set()
    last_progress = {"at": time.monotonic()}
    abandoned = threading.Event()
    worker_finished = threading.Event()

    def _cleanup_abandoned() -> None:
        if on_abandoned_worker_exit is not None:
            try:
                on_abandoned_worker_exit()
            except Exception:
                _LOGGER.exception("Could not clean up abandoned index attempt")

    def _heartbeat(*args: Any, **kwargs: Any) -> None:
        if not progress_live.is_set():
            return
        last_progress["at"] = time.monotonic()
        if progress_callback is not None:
            progress_callback(*args, **kwargs)

    def _work() -> Any:
        # Bind this run's heartbeat to the worker's own context: every progress
        # event raised by work done here resolves back to this heartbeat only.
        token = _CURRENT_HEARTBEAT.set(_heartbeat)
        try:
            return fn()
        finally:
            _CURRENT_HEARTBEAT.reset(token)
            worker_finished.set()
            _release_index_worker(worker_key, worker_marker)
            if abandoned.is_set():
                _cleanup_abandoned()

    _install_progress_callback(_heartbeat)
    try:
        future = asyncio.get_running_loop().run_in_executor(
            None, contextvars.copy_context().run, _work
        )
    except BaseException:
        progress_live.clear()
        _restore_progress_callback(_heartbeat)
        _release_index_worker(worker_key, worker_marker)
        raise

    def _consume_terminal_exception(fut: "asyncio.Future[Any]") -> None:
        # The stalled thread may finish after we raise; retrieve its exception
        # so it is not reported as "exception was never retrieved".
        if not fut.cancelled():
            fut.exception()
        # Covers the race where the thread's finally ran just before the
        # coroutine marked it abandoned. Never remove a live thread's output.
        if worker_finished.is_set():
            _cleanup_abandoned()

    try:
        while True:
            done, _ = await asyncio.wait({future}, timeout=_INDEX_STALL_POLL_SECONDS)
            if done:
                return future.result()
            stalled_for = time.monotonic() - last_progress["at"]
            if stalled_for > stall_timeout:
                raise IndexingStallError(
                    f"Indexing made no progress for {stalled_for:.0f}s while "
                    "embedding documents. Check the embedding endpoint; wait "
                    "for the worker to finish or restart DeepTutor before retrying."
                )
    except BaseException:
        abandoned.set()
        future.add_done_callback(_consume_terminal_exception)
        raise
    finally:
        progress_live.clear()
        _restore_progress_callback(_heartbeat)


def _emit_image_coverage(callback: Any, coverage: Any, warning: Any) -> None:
    """Forward this run's image coverage to ``callback``, if one was supplied.

    ``callback(coverage, warning)`` is the documented shape; the keyword form and
    a simpler one-argument callback are accepted too, because the callback is an
    internal projection seam (P1-27) rather than a public API. The call shape is
    chosen from the signature, so a callback is never invoked twice and a
    ``TypeError`` raised *inside* it is still a real error. A failing callback
    never fails indexing: the coverage already travelled with the load result
    and the warning is in the log either way.
    """
    if callback is None or coverage is None:
        return
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        parameters = {}
    kinds = {parameter.kind for parameter in parameters.values()}
    positional = [
        parameter
        for parameter in parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    accepts_kwargs = inspect.Parameter.VAR_KEYWORD in kinds
    accepts_varargs = inspect.Parameter.VAR_POSITIONAL in kinds
    coverage_keyword = next(
        (name for name in ("coverage", "image_coverage") if name in parameters), None
    )
    try:
        if coverage_keyword is not None and (
            accepts_kwargs or "warning" in parameters
        ):
            callback(**{coverage_keyword: coverage, "warning": warning})
        elif accepts_kwargs or len(positional) >= 2 or accepts_varargs:
            callback(coverage, warning)
        elif coverage_keyword is not None:
            callback(**{coverage_keyword: coverage})
        else:
            callback(coverage)
    except Exception:  # pragma: no cover - defensive
        _LOGGER.warning("Image coverage callback failed", exc_info=True)


class LlamaIndexPipeline:
    """Pipeline that indexes and retrieves KB content via LlamaIndex."""

    def __init__(
        self,
        kb_base_dir: Optional[str] = None,
        *,
        signature_provider: SignatureProvider | None = None,
        document_loader: LlamaIndexDocumentLoader | None = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR
        self._signature_provider = signature_provider or signature_from_embedding_config
        self.document_loader = document_loader or LlamaIndexDocumentLoader(self.logger)
        self._configure_settings()

    def _configure_settings(self) -> None:
        configure_llamaindex_settings(self.logger)

    async def _verify_embedding_connectivity(self) -> None:
        await verify_embedding_connectivity(self.logger)

    def _current_signature(self) -> EmbeddingSignature | None:
        return self._signature_provider()

    def _rollback_failed_attempt(
        self,
        kb_dir: Path,
        storage_dir: Path,
        signature: Optional[Any],
        *,
        fresh: bool,
        worker_finished: bool = False,
    ) -> None:
        """Undo a failed initialization attempt without touching anything else.

        ``fresh`` means the version directory was created *empty for this run*
        (``resolve_storage_dir_for_rebuild`` always reserves the next number), so
        the attempt owns every byte in it — including a persisted ``docstore``
        that the read paths would otherwise accept as a ready version. Deleting
        only ``meta.json`` is not enough: the no-signature read path treats any
        non-empty version directory as ready. A directory this run did not
        create is only cleaned when it is still empty, and a previous published
        version is never removed.
        """
        if not worker_finished and index_worker_state(kb_dir)["alive"]:
            return
        if fresh:
            try:
                if (
                    storage_dir.is_dir()
                    and storage_dir.name.startswith("version-")
                    and storage_dir.parent == kb_dir
                ):
                    shutil.rmtree(storage_dir)
                    self.logger.info(
                        f"Removed failed initialization attempt dir: {storage_dir}"
                    )
                    return
            except OSError as exc:  # pragma: no cover - best effort
                self.logger.warning(
                    f"Could not remove failed attempt dir {storage_dir}: {exc}"
                )
        self._cleanup_failed_version_dir(storage_dir, signature)

    def _cleanup_failed_version_dir(self, storage_dir: Path, signature: Optional[Any]) -> None:
        _ = signature
        try:
            if storage.cleanup_failed_version_dir(storage_dir):
                self.logger.info(
                    f"Removed empty version dir after failed pipeline run: {storage_dir}"
                )
        except Exception as cleanup_exc:  # pragma: no cover - best-effort
            self.logger.warning(
                f"Could not clean up failed version dir for {storage_dir}: {cleanup_exc}"
            )

    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        progress_callback = kwargs.get("progress_callback")
        image_coverage_callback = kwargs.get("image_coverage_callback")
        self._configure_settings()

        self.logger.info(
            f"Initializing KB '{kb_name}' with {len(file_paths)} files using LlamaIndex"
        )

        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        _ensure_index_worker_available(str(kb_dir.resolve()))
        signature = self._current_signature()
        storage_dir = resolve_storage_dir_for_rebuild(kb_dir, signature)
        # ``resolve_storage_dir_for_rebuild`` reserves the next flat version and
        # creates it empty, so an empty directory here is owned by this attempt.
        try:
            fresh_attempt = storage_dir.is_dir() and not any(storage_dir.iterdir())
        except OSError:  # pragma: no cover - defensive
            fresh_attempt = False
        #: Optional required commit (e.g. the KB metadata merge) that must
        #: succeed *before* the new version becomes readable.
        index_commit = kwargs.get("index_commit_callback")
        index_rollback = kwargs.get("index_rollback_callback")

        try:
            await self._verify_embedding_connectivity()
            documents = await self.document_loader.load(file_paths)
            # This run's image coverage travels with the load result. Project it
            # before the zero-node decision so a rejected initialization still
            # reports *why* the images are missing.
            coverage = getattr(documents, "image_coverage", None)
            coverage_warning = getattr(documents, "image_coverage_warning", None)
            if coverage is not None:
                self.logger.info(
                    f"Image coverage for KB '{kb_name}': {coverage}"
                    + (f" (warning: {coverage_warning})" if coverage_warning else "")
                )
            _emit_image_coverage(image_coverage_callback, coverage, coverage_warning)
            if not documents:
                self.logger.error("No valid documents found")
                # Nothing indexable: drop the version dir created for this
                # attempt so a failed run cannot look like a published version.
                self._rollback_failed_attempt(
                    kb_dir, storage_dir, signature, fresh=fresh_attempt
                )
                return False

            self.logger.info(
                f"Creating VectorStoreIndex with {len(documents)} documents "
                f"(chunking + embedding)..."
            )

            # Bounded instead of unbounded: an embedding endpoint that accepts a
            # request and never answers used to block this thread forever, so
            # the whole indexing task hung with no error. The guard fails once
            # the progress heartbeat goes quiet for too long.
            await _run_with_stall_guard(
                lambda: storage.create_index(documents, storage_dir, show_progress=True),
                progress_callback=progress_callback,
                worker_key=str(kb_dir.resolve()),
                on_abandoned_worker_exit=lambda: self._rollback_failed_attempt(
                    kb_dir, storage_dir, signature, fresh=fresh_attempt, worker_finished=True
                ),
            )

            self.logger.info(f"Index persisted to {storage_dir}")

            # The caller's required commit runs *before* the version is
            # published: if it fails, the attempt is rolled back and the read
            # path keeps selecting the previous successful version.
            if callable(index_commit):
                index_commit()
            if signature is not None:
                write_version_meta(kb_dir, signature, storage_dir=storage_dir)

            self.logger.info(f"KB '{kb_name}' initialized successfully with LlamaIndex")
            return True

        except BaseException as exc:
            self.logger.error(f"Failed to initialize KB: {exc}")
            self.logger.error(traceback.format_exc())
            try:
                if callable(index_rollback):
                    index_rollback()
            finally:
                self._rollback_failed_attempt(
                    kb_dir, storage_dir, signature, fresh=fresh_attempt
                )
            raise

    async def search(
        self,
        query: str,
        kb_name: str,
        **kwargs,
    ) -> Dict[str, Any]:
        kwargs.pop("mode", None)
        self._configure_settings()
        self.logger.info(f"Searching KB '{kb_name}' with query: {query[:50]}...")

        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        signature = self._current_signature()
        storage_dir = resolve_storage_dir_for_read(kb_dir, signature)

        if storage_dir is None or not (storage_dir / "docstore.json").exists():
            self.logger.warning(
                f"No matching index found for KB '{kb_name}' at signature "
                f"{signature.hash() if signature else 'n/a'}"
            )
            return {
                "query": query,
                "answer": (
                    "This knowledge base has no index for the active embedding "
                    "model. Re-index it (or switch back to a previously-used "
                    "embedding model) before querying."
                ),
                "content": "",
                "provider": "llamaindex",
                "needs_reindex": True,
            }

        embedding_mismatch_warning = self._embedding_mismatch_warning(kb_name)

        try:
            loop = asyncio.get_running_loop()
            top_k = kwargs.get("top_k") or default_top_k()
            nodes = await loop.run_in_executor(
                None,
                lambda: storage.retrieve_nodes(storage_dir, query, top_k=top_k),
            )

            result = self._nodes_to_result(query, nodes)
            if embedding_mismatch_warning:
                result["warning"] = embedding_mismatch_warning
            return result

        except Exception as exc:
            result = search_error_result(query, exc)
            if result.get("error_type"):
                log_message = result.get("log_message") or str(exc)
                self.logger.warning(f"Search failed ({result['error_type']}): {log_message}")
            else:
                self.logger.error(f"Search failed: {exc}")
                self.logger.error(traceback.format_exc())
            return result

    def _embedding_mismatch_warning(self, kb_name: str) -> str:
        try:
            cfg_path = Path(self.kb_base_dir) / "kb_config.json"
            if not cfg_path.exists():
                return ""
            with open(cfg_path, encoding="utf-8") as handle:
                kb_entry = json.load(handle).get("knowledge_bases", {}).get(kb_name, {})
            if not kb_entry.get("embedding_mismatch"):
                return ""
            stored = kb_entry.get("embedding_model", "unknown")
            current = get_embedding_config().model
            warning = (
                f"Warning: KB '{kb_name}' was indexed with '{stored}' "
                f"but current model is '{current}'. Re-index recommended."
            )
            self.logger.warning(warning)
            return warning
        except Exception:
            return ""

    def _nodes_to_result(self, query: str, nodes: list[Any]) -> Dict[str, Any]:
        context_parts: list[str] = []
        sources: list[dict[str, Any]] = []
        for i, node in enumerate(nodes):
            context_parts.append(node.node.text)
            meta = node.node.metadata or {}
            sources.append(
                {
                    "title": meta.get("file_name", meta.get("title", f"Document {i + 1}")),
                    "content": node.node.text[:200],
                    "source": meta.get("file_path", meta.get("file_name", "")),
                    "page": meta.get("page_label", meta.get("page", "")),
                    "chunk_id": node.node.node_id or str(i),
                    "score": round(node.score, 4) if node.score is not None else "",
                }
            )

        content = "\n\n".join(context_parts) if context_parts else ""
        return {
            "query": query,
            "answer": content,
            "content": content,
            "sources": sources,
            "provider": "llamaindex",
        }

    async def add_documents(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        progress_callback = kwargs.get("progress_callback")
        self._configure_settings()

        self.logger.info(f"Adding {len(file_paths)} documents to KB '{kb_name}' using LlamaIndex")

        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        signature = self._current_signature()
        plan = storage.resolve_add_storage_plan(kb_dir, signature)

        _ensure_index_worker_available(str(kb_dir.resolve()))

        try:
            await self._verify_embedding_connectivity()

            documents = await self.document_loader.load(file_paths)
            if not documents:
                self.logger.warning("No valid documents to add")
                return False

            # Same bounded-run treatment as ``initialize``: both branches below
            # embed documents, so both can hang on a blackholed endpoint.
            if plan.existing_storage is not None:
                self.logger.info(f"Loading existing index from {plan.existing_storage}...")
                num_added = await _run_with_stall_guard(
                    lambda: storage.insert_documents(
                        plan.existing_storage, plan.storage_dir, documents
                    ),
                    progress_callback=progress_callback,
                    worker_key=str(kb_dir.resolve()),
                )
                self.logger.info(f"Added {num_added} documents to existing index")
                if signature is not None and plan.storage_dir != plan.existing_storage:
                    write_version_meta(kb_dir, signature, storage_dir=plan.storage_dir)
            else:
                self.logger.info(f"Creating new index with {len(documents)} documents...")
                plan.storage_dir.mkdir(parents=True, exist_ok=True)
                num_added = await _run_with_stall_guard(
                    lambda: storage.create_index(
                        documents, plan.storage_dir, show_progress=True
                    ),
                    progress_callback=progress_callback,
                    worker_key=str(kb_dir.resolve()),
                )
                self.logger.info(f"Created new index with {num_added} documents")
                if signature is not None:
                    write_version_meta(kb_dir, signature, storage_dir=plan.storage_dir)

            self.logger.info(f"Successfully added documents to KB '{kb_name}'")
            return True

        except Exception as exc:
            self.logger.error(f"Failed to add documents: {exc}")
            self.logger.error(traceback.format_exc())
            if plan.existing_storage is None or plan.storage_dir != plan.existing_storage:
                self._cleanup_failed_version_dir(plan.storage_dir, signature)
            raise

    async def delete(self, kb_name: str) -> bool:
        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        deleted = storage.delete_kb_dir(kb_dir)
        if deleted:
            self.logger.info(f"Deleted KB '{kb_name}'")
        return deleted
