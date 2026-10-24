"""RAG query tool — thin wrapper around :class:`RAGService`.

The chat pipeline always passes an explicit ``kb_name`` selected by the user;
this module therefore never resolves aliases or falls back to a default KB. The
*scope* of a lookup (which subject tree, which mounted set, which provider) is
resolved by :func:`deeptutor.subjects.kb_scope.resolve_kb_ref`, so a subject
library and a global library with the same disk name can never be confused — and
a failed resolution never degrades into a same-named global library.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence

from deeptutor.services.rag.service import RAGService
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    SubjectStorageError,
    subject_error,
)

logger = logging.getLogger(__name__)

#: Trusted, server-owned scope of the last lookup, attached to the service result
#: under this key. The public tool layer pops it before the result becomes a
#: ``ToolResult`` (it carries the server-side KB directory, which must not reach
#: a model, a public message or a source metadata block).
SCOPE_KEY = "_subject_kb_scope"


async def rag_search(
    query: str,
    kb_name: str,
    provider: Optional[str] = None,
    kb_base_dir: Optional[str] = None,
    event_sink=None,
    *,
    subject_id: Optional[str] = None,
    mounted_refs: Optional[Sequence[str]] = None,
    _subject_id: Optional[str] = None,
    _mounted_refs: Optional[Sequence[str]] = None,
    **kwargs,
) -> dict:
    """Retrieve passages from ``kb_name`` and synthesise an answer.

    ``kb_base_dir`` stays available for trusted in-process callers (a caller that
    already owns a directory). It is **not** a model-facing parameter: the chat
    pipeline deletes it — together with every other scope carrier — from the
    model's arguments before calling, so the model cannot pick a directory.

    Without it, ``kb_name`` goes through the shared subject resolver: a subject
    wire id must belong to ``subject_id`` and be ready, a bare name is only
    accepted when the turn's ``mounted_refs`` matches it exactly once, and an
    explicit global reference keeps the original multi-user authorization.

    The underscore spellings are the pipeline's server-owned injections (the
    convention every other injected tool argument uses); the plain ones are the
    documented Python entry for trusted callers. An explicit ``[]`` mounted set
    is not the same request as ``None`` (no mount context at all), so the plain
    argument wins whenever it is not ``None``.
    """
    if subject_id is None:
        subject_id = _subject_id
    if mounted_refs is None:
        mounted_refs = _mounted_refs
    query = query.strip() if isinstance(query, str) else ""
    kb_name = kb_name.strip() if isinstance(kb_name, str) else ""
    if not query:
        raise ValueError("RAG query must be a non-empty string.")
    if not kb_name:
        raise ValueError("RAG requires an explicit kb_name.")

    scope: dict[str, Any] | None = None
    if kb_base_dir is None:
        from deeptutor.subjects import kb_scope

        resource = kb_scope.resolve_kb_ref(
            kb_name,
            expected_subject_id=subject_id,
            mounted_refs=mounted_refs,
            require_ready=True,
        )
        kb_base_dir = str(resource.base_dir)
        # The service addresses a library by its canonical *disk* name: the wire
        # id is an identity, never a directory name.
        kb_name = resource.name
        provider = provider or resource.provider
        scope = {
            "kb_ref": resource.kb_ref,
            "name": resource.name,
            "subject_id": resource.subject_id,
            "read_only": resource.read_only,
            "provider": resource.provider,
            "kb_dir": str(resource.kb_dir),
        }

    try:
        service = RAGService(kb_base_dir=kb_base_dir, provider=provider)
        result = await service.search(
            query=query,
            kb_name=kb_name,
            event_sink=event_sink,
            **kwargs,
        )
    except (SubjectOperationError, SubjectStorageError):
        # A scope/storage refusal is already a C02 error: let it through as-is.
        raise
    except Exception as exc:
        # Anything the engine raises is mapped here, at the narrow RAG boundary,
        # to the fixed C02 projection: the raw message (which can carry paths,
        # keys or engine internals) stays in the server log via ``cause`` and
        # never becomes a public tool result. The turn still sees a visible
        # failure with a stable code, and no other library is tried.
        logger.error("RAG engine call failed: %s", exc, exc_info=True)
        raise subject_error(ErrorCode.INTERNAL_ERROR, cause=exc) from exc
    # Some engines report failures in their result rather than raising. Never
    # promote their diagnostic answer to a successful, public response.
    if not isinstance(result, dict):
        raise subject_error(ErrorCode.INTERNAL_ERROR)
    if result.get("needs_reindex") is True:
        raise subject_error(ErrorCode.KB_NOT_READY)
    if result.get("error_type") or result.get("error") or result.get("success") is False:
        code = (
            ErrorCode.PROVIDER_UNAVAILABLE
            if result.get("error_type") == "not_configured"
            else ErrorCode.INTERNAL_ERROR
        )
        raise subject_error(code)
    if scope is not None and isinstance(result, dict):
        result[SCOPE_KEY] = scope
    return result


async def initialize_rag(
    kb_name: str,
    documents: List[str],
    provider: Optional[str] = None,
    kb_base_dir: Optional[str] = None,
    **kwargs,
) -> bool:
    """Index ``documents`` into ``kb_name`` using the configured RAG pipeline."""
    service = RAGService(kb_base_dir=kb_base_dir, provider=provider)
    return await service.initialize(kb_name=kb_name, file_paths=documents, **kwargs)


async def delete_rag(
    kb_name: str,
    provider: Optional[str] = None,
    kb_base_dir: Optional[str] = None,
) -> bool:
    """Delete the knowledge base ``kb_name``."""
    service = RAGService(kb_base_dir=kb_base_dir, provider=provider)
    return await service.delete(kb_name=kb_name)


def get_available_providers() -> List[Dict]:
    return RAGService.list_providers()


def get_current_provider() -> str:
    return RAGService.get_current_provider()


# Backward-compat aliases used by a few callers / tests
get_available_plugins = get_available_providers
list_providers = RAGService.list_providers


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("Available RAG Pipelines:")
    for provider in get_available_providers():
        print(f"  - {provider['id']}: {provider['description']}")
    print(f"\nCurrent provider: {get_current_provider()}\n")

    result = asyncio.run(
        rag_search(
            "What is the lookup table (LUT) in FPGA?",
            kb_name="DE-all",
        )
    )
    print(f"Query: {result['query']}")
    print(f"Answer: {result['answer']}")
    print(f"Provider: {result.get('provider', 'unknown')}")
