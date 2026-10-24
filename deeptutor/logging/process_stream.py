"""Process-log event capture for user-visible operational logs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import inspect
import logging
from typing import Any

from .context import LOG_CONTEXT_FIELDS
from .formatters import ContextFilter

PROCESS_LOG_PRIVATE_ATTR = "deeptutor_process_log_private"


@dataclass(frozen=True)
class ProcessLogEvent:
    type: str = "process_log"
    level: str = "INFO"
    message: str = ""
    logger: str = ""
    timestamp: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: logging.LogRecord) -> "ProcessLogEvent":
        context = dict(getattr(record, "log_context", {}) or {})
        for key in LOG_CONTEXT_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                context[key] = value
        return cls(
            level=record.levelname,
            message=record.getMessage(),
            logger=record.name,
            timestamp=record.created,
            context=context,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "level": self.level,
            "message": self.message,
            "logger": self.logger,
            "timestamp": self.timestamp,
            "context": self.context,
        }


class ProcessLogHandler(logging.Handler):
    """Emit structured process-log events from matching records."""

    def __init__(
        self,
        emit: Callable[[ProcessLogEvent], Any],
        *,
        task_id: str | None = None,
        turn_id: str | None = None,
        min_level: int = logging.INFO,
    ) -> None:
        super().__init__(level=min_level)
        self._emit = emit
        self._task_id = task_id
        self._turn_id = turn_id
        self.addFilter(ContextFilter())
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._closed:
                return
            if getattr(record, PROCESS_LOG_PRIVATE_ATTR, False):
                return
            event = ProcessLogEvent.from_record(record)
            if self._task_id and event.context.get("task_id") != self._task_id:
                return
            if self._turn_id and event.context.get("turn_id") != self._turn_id:
                return
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if self._loop is not None and current_loop is not self._loop:
                if self._loop.is_running() and not self._loop.is_closed():
                    # Create the awaitable on its owner loop. A queued callback
                    # discarded during shutdown then owns no leaked coroutine.
                    self._loop.call_soon_threadsafe(self._deliver, event, record)
                return
            self._deliver(event, record)
        except Exception:
            self.handleError(record)

    def _deliver(self, event: ProcessLogEvent, record: logging.LogRecord) -> None:
        if self._closed:
            return
        try:
            result = self._emit(event)
            if not inspect.isawaitable(result):
                return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                if inspect.iscoroutine(result):
                    result.close()
                return
            task = asyncio.ensure_future(result, loop=loop)

            def finished(future: asyncio.Future) -> None:
                if future.cancelled():
                    return
                try:
                    future.result()
                except Exception:
                    self.handleError(record)

            task.add_done_callback(finished)
        except Exception:
            if "result" in locals() and inspect.iscoroutine(result):
                result.close()
            self.handleError(record)


@contextmanager
def capture_process_logs(
    emit: Callable[[ProcessLogEvent], Any],
    *,
    task_id: str | None = None,
    turn_id: str | None = None,
    min_level: int = logging.INFO,
) -> Iterator[ProcessLogHandler]:
    """Capture matching stdlib log records and emit ``ProcessLogEvent`` objects."""
    handler = ProcessLogHandler(
        emit,
        task_id=task_id,
        turn_id=turn_id,
        min_level=min_level,
    )
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        handler.close()
