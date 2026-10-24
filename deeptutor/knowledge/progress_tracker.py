"""
Progress Tracker - Tracks knowledge base initialization progress
"""

import asyncio
from collections.abc import Callable
import copy
from datetime import datetime
from enum import Enum
import json
import logging
from pathlib import Path

from deeptutor.services.file_io import atomic_write_json

# Use unified logging system

_logger = logging.getLogger(__name__)


def _logger_instance():
    return _logger


class ProgressStage(Enum):
    """Initialization stage"""

    INITIALIZING = "initializing"  # Initializing
    PROCESSING_DOCUMENTS = "processing_documents"  # Processing documents
    PROCESSING_FILE = "processing_file"  # Processing single file
    COMPLETED = "completed"  # Completed
    ERROR = "error"  # Error


class ProgressTracker:
    """Progress tracker"""

    def __init__(self, kb_name: str, base_dir: Path):
        self.kb_name = kb_name
        self.base_dir = base_dir
        self.kb_dir = base_dir / kb_name
        self.progress_file = self.kb_dir / ".progress.json"
        self._callbacks: list = []  # Support multiple callbacks
        self.task_id: str | None = None  # Task ID (for log identification)
        # This run's image coverage (P1-27), remembered so the *later* updates of
        # the same run — including the final COMPLETED event written by the
        # caller — keep it instead of overwriting it with a coverage-less dict.
        self._image_coverage: dict | None = None
        self._image_coverage_warning: str | None = None
        self._image_coverage_task: str | None = None

    def set_callback(self, callback: Callable[[dict], None]):
        """Set progress callback function (can be called multiple times to add multiple callbacks)"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[dict], None]):
        """Remove progress callback function"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def record_image_coverage(self, coverage: dict | None, warning: str | None = None) -> None:
        """Remember this run's image coverage for its later progress updates."""
        self._image_coverage = copy.deepcopy(coverage) if isinstance(coverage, dict) else None
        self._image_coverage_warning = warning or None
        self._image_coverage_task = self.task_id

    def reset_image_coverage(self) -> None:
        """Forget any remembered coverage — called when a new run starts."""
        self._image_coverage = None
        self._image_coverage_warning = None
        self._image_coverage_task = self.task_id

    def _remembered_image_coverage(self) -> tuple[dict, str | None] | None:
        if self._image_coverage is None:
            return None
        if self._image_coverage_task != self.task_id:
            # Another task owns this tracker now; its numbers must never be
            # attributed to the previous run.
            self.reset_image_coverage()
            return None
        return copy.deepcopy(self._image_coverage), self._image_coverage_warning

    def _notify(self, progress: dict):
        """Notify progress update (call all callbacks)"""
        from deeptutor.runtime.mode import is_server

        if is_server():
            try:
                from deeptutor.api.utils.progress_broadcaster import ProgressBroadcaster

                broadcaster = ProgressBroadcaster.get_instance()

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(broadcaster.broadcast(self.kb_name, progress))
                except RuntimeError:
                    pass
            except (ImportError, Exception):
                pass

        for callback in self._callbacks:
            try:
                callback(progress)
            except Exception as e:
                _logger_instance().debug("Progress callback error: %s", e)

    def _save_progress(self, progress: dict):
        """Save progress to kb_config.json and local .progress.json file"""
        # Save to kb_config.json (centralized config)
        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager

            manager = KnowledgeBaseManager(base_dir=str(self.base_dir))

            # Determine status based on stage
            stage = progress.get("stage", "")
            if stage == "completed":
                status = "ready"
            elif stage == "error":
                status = "error"
            elif stage in [
                "initializing",
                "processing_documents",
                "processing_file",
            ]:
                status = "processing"
            else:
                status = "initializing"

            # Update kb_config.json with status and progress
            manager.update_kb_status(
                name=self.kb_name,
                status=status,
                progress={
                    "stage": progress.get("stage"),
                    "message": progress.get("message"),
                    "percent": progress.get("progress_percent", 0),
                    "current": progress.get("current", 0),
                    "total": progress.get("total", 0),
                    "file_name": progress.get("file_name"),
                    "error": progress.get("error"),
                    "error_code": progress.get("error_code"),
                    "retryable": progress.get("retryable"),
                    "timestamp": progress.get("timestamp"),
                    "task_id": progress.get("task_id"),
                    "indexed_count": progress.get("indexed_count"),
                    "index_changed": progress.get("index_changed"),
                    "index_action": progress.get("index_action"),
                    "image_coverage": progress.get("image_coverage"),
                    "image_coverage_warning": progress.get("image_coverage_warning"),
                },
            )
        except Exception as e:
            _logger_instance().warning("Failed to save progress to kb_config.json: %s", e)

        # Persist the last seen progress snapshot so websocket subscribers and
        # page reloads can recover the live state without relying on in-memory callbacks.
        try:
            atomic_write_json(self.progress_file, progress)
        except Exception as e:
            _logger_instance().warning(
                "Failed to persist progress snapshot for '%s': %s", self.kb_name, e
            )

    def update(
        self,
        stage: ProgressStage,
        message: str = "",
        current: int = 0,
        total: int = 0,
        file_name: str = "",
        error: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        indexed_count: int | None = None,
        index_changed: bool | None = None,
        index_action: str | None = None,
        image_coverage: dict | None = None,
        image_coverage_warning: str | None = None,
    ):
        """Update progress"""
        progress = {
            "kb_name": self.kb_name,
            "task_id": self.task_id,
            "stage": stage.value,
            "message": message,
            "current": current,
            "total": total,
            "file_name": file_name,
            "progress_percent": int(current / total * 100) if total > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }
        if indexed_count is not None:
            progress["indexed_count"] = indexed_count
        if index_changed is not None:
            progress["index_changed"] = index_changed
        if index_action:
            progress["index_action"] = index_action

        # Additive image coverage (P1-27): a supplied value becomes this run's
        # memory, and every following update of the same task re-attaches it so
        # the final COMPLETED snapshot/event cannot silently drop it.
        if image_coverage is not None or image_coverage_warning is not None:
            self.record_image_coverage(image_coverage, image_coverage_warning)
        remembered = self._remembered_image_coverage()
        if remembered is not None:
            progress["image_coverage"] = remembered[0]
            if remembered[1]:
                progress["image_coverage_warning"] = remembered[1]

        if error:
            progress["error"] = error
            progress["stage"] = ProgressStage.ERROR.value
        if error_code:
            progress["error_code"] = error_code
        if retryable is not None:
            progress["retryable"] = retryable

        # Output to logger (terminal and log file)
        try:
            logger = _logger_instance()
            prefix = f"[{self.task_id}]" if self.task_id else ""

            if total > 0:
                percent = progress["progress_percent"]
                progress_msg = f"{prefix} {message} ({current}/{total}, {percent}%)"
                if file_name:
                    progress_msg += f" - File: {file_name}"
            else:
                progress_msg = f"{prefix} {message}"
                if file_name:
                    progress_msg += f" - File: {file_name}"

            if error:
                logger.error(f"{progress_msg} - Error: {error}")
            else:
                logger.info(progress_msg)
        except Exception:
            # If unified logging fails unexpectedly, use stdlib logger as fallback.
            fallback_logger = logging.getLogger("deeptutor.ProgressTracker")
            prefix = f"[{self.task_id}]" if self.task_id else ""
            fallback_logger.warning(
                "%s [ProgressTracker] %s (%s/%s)",
                prefix,
                message,
                current,
                total if total > 0 else "?",
            )
            if error:
                fallback_logger.error("%s [ProgressTracker] Error: %s", prefix, error)

        self._save_progress(progress)

        if self.task_id:
            try:
                from deeptutor.api.utils.task_log_stream import get_task_stream_manager

                get_task_stream_manager().emit(self.task_id, "progress", progress)
            except Exception as e:
                _logger_instance().debug("Failed to emit task progress event: %s", e)

        self._notify(progress)

    def get_progress(self) -> dict | None:
        """Get current progress"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _logger_instance().debug(f"Failed to read progress file for '{self.kb_name}': {e}")

        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager

            manager = KnowledgeBaseManager(base_dir=str(self.base_dir))
            status = manager.get_kb_status(self.kb_name)
            if status and status.get("progress"):
                return status.get("progress")
        except Exception as e:
            _logger_instance().debug(
                "Failed to recover progress snapshot from kb_config for '%s': %s",
                self.kb_name,
                e,
            )

        return None

    def clear(self):
        """Clear progress file"""
        if self.progress_file.exists():
            try:
                self.progress_file.unlink()
            except Exception as e:
                _logger_instance().debug(f"Failed to clear progress file for '{self.kb_name}': {e}")
