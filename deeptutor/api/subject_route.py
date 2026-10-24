"""Subject-only HTTP error boundary (C02).

The subject routes are the fork's learner-data API. Once the storage layer
started raising explicit errors (``StorageCorruptError`` / ``StorageIOError``)
and the domain layer started raising named operations errors
(:class:`~deeptutor.subjects.errors.SubjectOperationError`), a route that did not
catch them returned a bare 500 traceback, and a route that caught them by hand
returned a different shape on every endpoint.

:class:`SubjectRoute` wraps **this router only** — nothing is registered
globally, so every other upstream router keeps its own exception mechanics:

* a typed storage/domain/LLM failure is projected by
  :func:`~deeptutor.subjects.errors.map_subject_exception` into the fixed C02
  ``{detail, error}`` payload with the table's status code;
* an unknown internal exception becomes ``internal_error`` with a safe fixed
  message — the real exception is kept as ``cause`` and recorded in the server
  log, never in the response;
* authentication HTTP 401/403 with their ``WWW-Authenticate`` headers, native
  validation 422, and historical HTTPExceptions without a recognized business
  cause keep their framework shapes; other HTTPExceptions with an explicit
  domain/storage/LLM cause use the same safe C02 projection.

Because the wrapper replaces the *whole* route handler, failures raised while
resolving dependencies are covered too — not only the endpoint body.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from deeptutor.subjects.errors import (
    SubjectOperationError,
    SubjectStorageError,
    map_subject_exception,
    to_http_payload,
)

logger = logging.getLogger(__name__)

#: Statuses whose framework shape (body + headers) always wins, even when the
#: HTTPException was raised ``from`` a recognisable business error: authentication
#: 401/403 and the native validation 422 must not be re-projected.
FRAMEWORK_PRIORITY_STATUSES = frozenset({401, 403, 422})

#: How far the explicit ``__cause__`` chain is followed. Deliberately tiny: this
#: covers ``raise HTTPException(...) from exc`` without building an exception
#: graph, and never inspects ``__context__`` (which can hold unrelated errors).
CAUSE_CHAIN_DEPTH = 4


def _llm_error_types() -> tuple[type[BaseException], ...]:
    """Provider-side error base (imported lazily to keep this module light)."""
    from deeptutor.services.llm.exceptions import LLMError

    return (LLMError,)


def _timeout_cause_types() -> tuple[type[BaseException], ...]:
    """Real timeout types (by inheritance), mirroring the C02 mapper's set."""
    import asyncio

    types: list[type[BaseException]] = [TimeoutError, asyncio.TimeoutError]
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx is an existing dependency
        pass
    else:
        types.append(httpx.TimeoutException)
    return tuple(dict.fromkeys(types))


def _is_business_cause(value: object) -> bool:
    """Whether *value* is a named domain/storage/LLM/timeout error.

    Only real types count: a generic ``ValueError``/``RuntimeError`` is *not* a
    provider problem and must never be mapped by guessing.
    """
    if isinstance(value, (SubjectOperationError, SubjectStorageError)):
        return True
    if isinstance(value, _llm_error_types()):
        return True
    return isinstance(value, _timeout_cause_types())


def _business_cause(exc: HTTPException) -> BaseException | None:
    """The explicit business cause of *exc*, following ``__cause__`` only."""
    cause = exc.__cause__
    for _ in range(CAUSE_CHAIN_DEPTH):
        if cause is None:
            return None
        if _is_business_cause(cause):
            return cause
        cause = cause.__cause__
    return None


def _diagnostics(error: Any, exc: BaseException, wrapped: HTTPException | None) -> str:
    """Controlled server-side diagnostics (never the client-facing message)."""
    detail: dict[str, Any] = {
        "code": error.code.value,
        "exc_type": type(exc).__name__,
    }
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason:
        # ModelOutputError's server-side rejection reason (e.g. verdict_unknown).
        detail["reason"] = reason
    if error.cause is not None:
        detail["cause_type"] = type(error.cause).__name__
    if wrapped is not None:
        detail["http_exception_status"] = wrapped.status_code
    return json.dumps(detail, ensure_ascii=False)


def _log_failure(
    request: Request,
    error: Any,
    exc: BaseException,
    *,
    wrapped: HTTPException | None = None,
) -> None:
    """Record the failure with its **real** exception/traceback server-side.

    ``exc_info`` carries the live exception object (and therefore its cause
    chain and traceback), so the diagnostics survive for the operator instead of
    just the class name. Nothing here reaches the JSON response.
    """
    logger.warning(
        "subject route %s: %s %s (%s)",
        error.code.value,
        request.method,
        request.url.path,
        _diagnostics(error, exc, wrapped),
        exc_info=exc,
    )


class SubjectRoute(APIRoute):
    """``APIRoute`` that turns subject/storage/LLM failures into C02 payloads."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def subject_error_boundary(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                # 原生参数校验：保持框架 422。
                raise
            except HTTPException as exc:
                # 认证 / 原生 401/403/422 优先保留（含 WWW-Authenticate 等 headers）。
                if exc.status_code in FRAMEWORK_PRIORITY_STATUSES:
                    raise
                cause = _business_cause(exc)
                if cause is None:
                    # 没有明确业务 cause 的历史 HTTPException：仍是框架行为，
                    # 不按 detail 文本或类名猜分类。
                    raise
                error = map_subject_exception(cause)
                _log_failure(request, error, cause, wrapped=exc)
                return JSONResponse(
                    status_code=error.http_status, content=to_http_payload(error)
                )
            except Exception as exc:  # noqa: BLE001 - C02 统一安全出口
                error = map_subject_exception(exc)
                _log_failure(request, error, exc)
                return JSONResponse(
                    status_code=error.http_status, content=to_http_payload(error)
                )

        return subject_error_boundary


__all__ = ("CAUSE_CHAIN_DEPTH", "FRAMEWORK_PRIORITY_STATUSES", "SubjectRoute")
