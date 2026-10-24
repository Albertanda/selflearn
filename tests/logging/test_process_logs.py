import asyncio
import logging
import threading

import pytest

from deeptutor.logging import (
    PROCESS_LOG_PRIVATE_ATTR,
    ProcessLogEvent,
    bind_log_context,
    capture_process_logs,
)


def test_capture_process_logs_emits_structured_event_for_matching_task():
    events: list[ProcessLogEvent] = []
    logger = logging.getLogger("deeptutor.tests.process")
    original_level = logger.level
    logger.setLevel(logging.INFO)

    try:
        with bind_log_context(task_id="task-1", capability="knowledge", stage="indexing"):
            with capture_process_logs(events.append, task_id="task-1"):
                logger.info("Embedding batches: %s/%s", 2, 8)
    finally:
        logger.setLevel(original_level)

    assert len(events) == 1
    event = events[0].to_dict()
    assert event["type"] == "process_log"
    assert event["level"] == "INFO"
    assert event["message"] == "Embedding batches: 2/8"
    assert event["logger"] == "deeptutor.tests.process"
    assert event["context"] == {
        "task_id": "task-1",
        "capability": "knowledge",
        "stage": "indexing",
    }


def test_capture_process_logs_filters_other_tasks():
    events: list[ProcessLogEvent] = []
    logger = logging.getLogger("deeptutor.tests.process")

    with capture_process_logs(events.append, task_id="task-1"):
        with bind_log_context(task_id="task-2"):
            logger.warning("wrong task")

    assert events == []


@pytest.mark.asyncio
async def test_async_log_callback_from_worker_runs_on_owning_loop():
    owner = threading.get_ident()
    received = asyncio.Event()
    events = []

    async def sink(event):
        events.append((event.message, threading.get_ident()))
        received.set()

    with capture_process_logs(sink):
        await asyncio.to_thread(logging.getLogger("deeptutor.tests.worker").warning, "worker event")
        await asyncio.wait_for(received.wait(), 2)
    assert events == [("worker event", owner)]


def test_async_log_callback_without_loop_is_closed():
    from deeptutor.logging.process_stream import ProcessLogHandler

    created = []

    async def sink(event):
        pass

    def callback(event):
        result = sink(event)
        created.append(result)
        return result

    handler = ProcessLogHandler(callback)
    try:
        handler.handle(logging.makeLogRecord({"msg": "outside loop", "levelno": logging.WARNING}))
        assert created and created[0].cr_frame is None
    finally:
        handler.close()
        for result in created:
            result.close()


@pytest.mark.asyncio
async def test_closed_handler_does_not_deliver_queued_worker_callback():
    from deeptutor.logging.process_stream import ProcessLogHandler

    received = []
    handler = ProcessLogHandler(received.append)
    worker = threading.Thread(
        target=handler.handle,
        args=(logging.makeLogRecord({"msg": "late", "levelno": logging.WARNING}),),
    )
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    handler.close()
    await asyncio.sleep(0)
    assert received == []


def test_capture_process_logs_excludes_server_only_diagnostics():
    events: list[ProcessLogEvent] = []
    logger = logging.getLogger("deeptutor.tests.process")

    with bind_log_context(task_id="task-1", capability="knowledge"):
        with capture_process_logs(events.append, task_id="task-1"):
            logger.error(
                "Stack trace contains sk-secret-must-not-leak",
                extra={PROCESS_LOG_PRIVATE_ATTR: True},
            )

    assert events == []
