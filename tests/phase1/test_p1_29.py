"""P1-29 行为测试：索引 worker 生命周期与停滞守卫（C07）。

目标：守卫已经存在，先用行为证据证明它的真实生命周期，再只修证实的缺陷——
超时不伪装成"线程已结束"、同 key 未退出仍忙、真正退出后才可重试、报错后
callback 静默、异常/取消不留下未取回的异常或错误的释放。

测试全部用 ``threading.Event`` 控制，不睡眠 600 秒；每个用例在 finally 里释放
自己创建的线程并等待退出，并且隔离 ``_INDEX_WORKERS`` 与 subject 侧预留登记表。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import threading
import time
import warnings

import pytest

from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_mod
from deeptutor.subjects import uploads
from tests.phase1 import helpers

STALL = pipeline_mod.IndexingStallError


@pytest.fixture(autouse=True)
def _isolated_registries(monkeypatch):
    """隔离 worker 注册表、心跳栈与 subject 预留，避免污染目录回归。"""
    with pipeline_mod._INDEX_WORKERS_LOCK:
        saved_workers = dict(pipeline_mod._INDEX_WORKERS)
        pipeline_mod._INDEX_WORKERS.clear()
    monkeypatch.setattr(pipeline_mod, "_INDEX_STALL_POLL_SECONDS", 0.01)
    uploads.reset_registry_for_tests()
    try:
        yield
    finally:
        with pipeline_mod._INDEX_WORKERS_LOCK:
            pipeline_mod._INDEX_WORKERS.clear()
            pipeline_mod._INDEX_WORKERS.update(saved_workers)
        with pipeline_mod._PROGRESS_CALLBACK_LOCK:
            pipeline_mod._PROGRESS_CALLBACKS.clear()
        pipeline_mod.set_progress_callback(None)
        uploads.reset_registry_for_tests()


def _wait_for(predicate, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _wait_released(*keys: str, timeout: float = 5.0) -> None:
    """Wait for the *work* to be done.

    The default executor's pool thread stays alive (idle) after the callable
    returns, so joining the OS thread would be the wrong primitive: the marker
    being released is exactly "``fn`` returned and the key is free again".
    """
    assert _wait_for(
        lambda: all(
            not pipeline_mod.index_worker_state(key)["alive"] for key in keys
        ),
        timeout=timeout,
    ), f"worker for {keys} was still registered after the work finished"


# ---------------------------------------------------------------------------
# 正常生命周期
# ---------------------------------------------------------------------------
def test_a_successful_run_registers_then_releases_the_worker():
    seen: dict = {}

    def _work() -> str:
        seen["thread"] = threading.current_thread()
        seen["state"] = pipeline_mod.index_worker_state("kb-ok")
        return "indexed"

    result = asyncio.run(
        pipeline_mod._run_with_stall_guard(_work, worker_key="kb-ok", stall_timeout=5.0)
    )
    assert result == "indexed"
    # 运行期间 marker 确实存在（不是只靠调用方自己判断）
    assert seen["state"]["registered"] is True
    assert seen["state"]["alive"] is True

    after = pipeline_mod.index_worker_state("kb-ok")
    assert after == {"key": after["key"], "registered": False, "alive": False}
    # 守卫自己恢复心跳栈：跑完后没有残留 callback
    assert pipeline_mod.active_progress_callback() is None


def test_same_key_is_refused_while_running_and_a_different_key_runs(
    p1_runtime, tmp_path
):
    started = threading.Event()
    release = threading.Event()

    def _blocking() -> str:
        started.set()
        release.wait(10)
        return "first"

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _blocking, worker_key="kb-a", stall_timeout=30.0
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        assert pipeline_mod.index_worker_state("kb-a")["alive"] is True

        with pytest.raises(STALL):
            await pipeline_mod._run_with_stall_guard(
                lambda: "never", worker_key="kb-a", stall_timeout=30.0
            )

        # 不同 key 完全独立
        other = await pipeline_mod._run_with_stall_guard(
            lambda: "second", worker_key="kb-b", stall_timeout=30.0
        )
        assert other == "second"
        release.set()
        return await task

    try:
        assert asyncio.run(_scenario()) == "first"
    finally:
        release.set()
    _wait_released("kb-a")


# ---------------------------------------------------------------------------
# 停滞：报错但线程仍活着
# ---------------------------------------------------------------------------
def test_stall_raises_while_the_worker_is_still_alive(p1_runtime):
    started = threading.Event()
    release = threading.Event()

    def _blocking() -> str:
        started.set()
        release.wait(30)
        return "late"

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _blocking, worker_key="kb-stall", stall_timeout=0.02
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(STALL) as excinfo:
                await asyncio.wait_for(task, timeout=5)
        return str(excinfo.value)

    # 事件循环保持打开：不能靠 asyncio.run 的收尾来"等线程结束"
    loop = asyncio.new_event_loop()
    try:
        message = loop.run_until_complete(_scenario())
        assert "no progress" in message
        # 超时没有伪造"线程已经结束"
        assert pipeline_mod.index_worker_state("kb-stall")["alive"] is True
        with pytest.raises(STALL):
            loop.run_until_complete(
                pipeline_mod._run_with_stall_guard(
                    lambda: "never", worker_key="kb-stall", stall_timeout=30.0
                )
            )
    finally:
        release.set()
        _wait_released("kb-stall")
        # 真正退出后可以重试
        assert (
            loop.run_until_complete(
                pipeline_mod._run_with_stall_guard(
                    lambda: "retry", worker_key="kb-stall", stall_timeout=5.0
                )
            )
            == "retry"
        )
        loop.close()


def test_default_stall_timeout_comes_from_the_module_constant(monkeypatch):
    assert pipeline_mod._INDEX_STALL_TIMEOUT_SECONDS == 600.0
    assert pipeline_mod._INDEX_STALL_POLL_SECONDS == 0.01  # 本文件为提速而缩短

    monkeypatch.setattr(pipeline_mod, "_INDEX_STALL_TIMEOUT_SECONDS", 0.02)
    started = threading.Event()
    release = threading.Event()

    def _blocking() -> str:
        started.set()
        release.wait(30)
        return "late"

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(_blocking, worker_key="kb-def")
        )
        assert await asyncio.to_thread(started.wait, 5)
        with pytest.raises(STALL):
            await asyncio.wait_for(task, timeout=5)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_scenario())
    finally:
        release.set()
        _wait_released("kb-def")
        loop.close()


# ---------------------------------------------------------------------------
# 报错后的 callback 静默
# ---------------------------------------------------------------------------
def test_callback_is_silent_after_the_stall_is_reported(p1_runtime):
    started = threading.Event()
    release = threading.Event()
    forwarded: list[tuple] = []
    seen: dict = {}

    def _work() -> str:
        # R5：心跳按 worker 上下文归属，active_progress_callback 只是共享 dispatcher
        seen["heartbeat"] = pipeline_mod.current_worker_heartbeat()
        started.set()
        release.wait(10)
        return "late"

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _work,
                progress_callback=lambda *a, **k: forwarded.append((a, k)),
                worker_key="kb-cb",
                stall_timeout=0.03,
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        heartbeat = seen["heartbeat"]
        assert heartbeat is not None
        heartbeat(1, 2)
        assert forwarded, "heartbeat must forward while the run is live"
        before = len(forwarded)
        with pytest.raises(STALL):
            await asyncio.wait_for(task, timeout=5)
        # 报错之后同一个 heartbeat 立即静默
        heartbeat(3, 4)
        observed = (before, len(forwarded))
        release.set()
        return observed

    try:
        before, after = asyncio.run(_scenario())
        assert after == before
    finally:
        release.set()
        _wait_released("kb-cb")


def test_finished_runs_do_not_clobber_a_live_heartbeat(p1_runtime):
    started_a = threading.Event()
    started_b = threading.Event()
    release_a = threading.Event()
    release_b = threading.Event()
    forwarded_a: list[int] = []
    forwarded_b: list[int] = []
    seen: dict = {}

    def _work_a() -> str:
        started_a.set()
        release_a.wait(10)
        return "a"

    def _work_b() -> str:
        seen["heartbeat_b"] = pipeline_mod.current_worker_heartbeat()
        started_b.set()
        release_b.wait(10)
        return "b"

    async def _scenario():
        task_a = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _work_a,
                progress_callback=lambda *a, **k: forwarded_a.append(1),
                worker_key="kb-x",
                stall_timeout=30.0,
            )
        )
        assert await asyncio.to_thread(started_a.wait, 5)
        task_b = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _work_b,
                progress_callback=lambda *a, **k: forwarded_b.append(1),
                worker_key="kb-y",
                stall_timeout=30.0,
            )
        )
        assert await asyncio.to_thread(started_b.wait, 5)
        heartbeat_b = seen["heartbeat_b"]
        assert heartbeat_b is not None

        release_a.set()
        assert await asyncio.wait_for(task_a, timeout=5) == "a"
        # A 结束后 B 仍在运行：共享 dispatcher 仍然安装着（没有被 A 的 finally 清掉）
        assert pipeline_mod.active_progress_callback() is not None
        heartbeat_b(1, 2)
        assert forwarded_b, "the still-running run must keep its heartbeat"

        release_b.set()
        assert await asyncio.wait_for(task_b, timeout=5) == "b"
        # 全部结束后回到基线，没有残留的陈旧心跳
        assert pipeline_mod.active_progress_callback() is None
        forwarded_b_before = len(forwarded_b)
        heartbeat_b(3, 4)
        assert len(forwarded_b) == forwarded_b_before

    try:
        asyncio.run(_scenario())
    finally:
        release_a.set()
        release_b.set()
    _wait_released("kb-x", "kb-y")


# ---------------------------------------------------------------------------
# 异常、取消、identity 释放
# ---------------------------------------------------------------------------
def test_worker_exception_propagates_and_releases_the_key():

    def _boom() -> str:
        raise ValueError("worker exploded")

    with pytest.raises(ValueError):
        asyncio.run(
            pipeline_mod._run_with_stall_guard(_boom, worker_key="kb-err", stall_timeout=5.0)
        )
    _wait_released("kb-err")


def test_cancellation_keeps_the_key_busy_until_the_thread_exits():
    started = threading.Event()
    release = threading.Event()

    def _blocking() -> str:
        started.set()
        release.wait(30)
        return "late"

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _blocking, worker_key="kb-cancel", stall_timeout=30.0
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_scenario())
        # 取消不会让"线程还在跑"的 key 变成可用
        assert pipeline_mod.index_worker_state("kb-cancel")["alive"] is True
        with pytest.raises(STALL):
            loop.run_until_complete(
                pipeline_mod._run_with_stall_guard(
                    lambda: "never", worker_key="kb-cancel", stall_timeout=30.0
                )
            )
        assert pipeline_mod.active_progress_callback() is None
    finally:
        release.set()
        _wait_released("kb-cancel")
        loop.close()


def test_release_is_identity_checked():
    key = "kb-identity"
    first = pipeline_mod._claim_index_worker(key)
    assert first is not None
    # 新的 worker 接管同一 key（旧 marker 已 set）
    second_thread_marker = None
    pipeline_mod._release_index_worker(key, first)
    assert pipeline_mod.index_worker_state(key)["registered"] is False

    first = pipeline_mod._claim_index_worker(key)
    first.set()
    second_thread_marker = pipeline_mod._claim_index_worker(key)
    assert second_thread_marker is not None and second_thread_marker is not first
    # 迟到的旧 worker 释放不会摘掉新 worker 的 marker
    pipeline_mod._release_index_worker(key, first)
    state = pipeline_mod.index_worker_state(key)
    assert state["registered"] is True and state["alive"] is True
    pipeline_mod._release_index_worker(key, second_thread_marker)
    assert pipeline_mod.index_worker_state(key)["registered"] is False


def test_late_exception_is_consumed_and_not_reported(p1_runtime):
    """晚到的异常必须被取回：不能出现 'exception was never retrieved'。"""
    import gc

    started = threading.Event()
    release = threading.Event()

    def _blocking_then_boom() -> str:
        started.set()
        release.wait(30)
        raise RuntimeError("late failure after the stall was reported")

    async def _scenario():
        task = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _blocking_then_boom, worker_key="kb-late", stall_timeout=0.02
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        with pytest.raises(STALL):
            await asyncio.wait_for(task, timeout=5)

    asyncio_logger = logging.getLogger("asyncio")
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):  # noqa: D102 - test handler
            records.append(record.getMessage())

    handler = _Capture()
    asyncio_logger.addHandler(handler)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_scenario())
        # 让晚到的异常真正落地，并确认取回它（不是靠 gc 碰运气）
        release.set()
        _wait_released("kb-late")
        loop.run_until_complete(asyncio.sleep(0.05))
        gc.collect()
        assert not [item for item in records if "never retrieved" in item], records
    finally:
        release.set()
        asyncio_logger.removeHandler(handler)
        loop.close()

    # 坏对照：同一个探针能看见真正未取回的异常
    async def _leak():
        event_loop = asyncio.get_running_loop()
        future = event_loop.create_future()
        future.set_exception(RuntimeError("deliberately unretrieved"))
        del future
        gc.collect()

    control: list[str] = []

    class _Control(_Capture):
        def emit(self, record):  # noqa: D102 - test handler
            control.append(record.getMessage())

    control_handler = _Control()
    asyncio_logger.addHandler(control_handler)
    try:
        asyncio.run(_leak())
        gc.collect()
    finally:
        asyncio_logger.removeHandler(control_handler)
    assert [item for item in control if "never retrieved" in item], control


# ---------------------------------------------------------------------------
# subject 预留与 worker 不互相误判
# ---------------------------------------------------------------------------
def test_subject_reservation_and_pipeline_worker_are_separate(p1_runtime):
    kb_dir = Path(p1_runtime) / "kb-busy"
    kb_dir.mkdir(parents=True, exist_ok=True)

    uploads.reserve_index_task(
        kb_dir,
        task_id="task-1",
        subject_id="科目a",
        kb_name="assignment-kb",
        fingerprint="a" * 64,
        shape="b" * 64,
        documents=1,
        action="create",
    )
    state = uploads.busy_state(kb_dir)
    assert state["busy"] is True and state["queued"] is True
    assert state["worker_alive"] is False
    # 排队中的 subject 任务不会被守卫误认成"自己的 worker 还活着"
    worker = pipeline_mod.index_worker_state(kb_dir)
    assert worker["registered"] is False and worker["alive"] is False

    marker = pipeline_mod._claim_index_worker(str(kb_dir.resolve()))
    try:
        assert uploads.busy_state(kb_dir)["worker_alive"] is True
        assert uploads.clear_reservation(kb_dir, task_id="task-1") is True
        # 预留释放后仍因活线程而忙（终态/预留都不能证明线程已退出）
        assert uploads.busy_state(kb_dir)["busy"] is True
    finally:
        pipeline_mod._release_index_worker(str(kb_dir.resolve()), marker)
    assert uploads.busy_state(kb_dir)["busy"] is False


# ---------------------------------------------------------------------------
# R5（rework01）：真实 embedding 调用的进度必须归属它自己的 worker
# ---------------------------------------------------------------------------
def test_real_embedding_progress_belongs_to_its_worker(p1_runtime):
    """走真实 ``CustomEmbedding``/``Settings`` 链路，只替换 provider client。

    先证明合法单适配器对照会收到进度，再让 A/B 同时活跃：A 实际执行的
    ``_get_text_embeddings`` 只能刷新 A 的 heartbeat，B 保持为空。
    """
    from llama_index.core import Settings

    from deeptutor.services.rag.pipelines.llamaindex import embedding_adapter as ea

    client = helpers.FakeEmbeddingClient()
    client.config = None

    async def embed(texts, progress_callback=None, **kwargs):
        if progress_callback is not None:
            progress_callback(1, 1)
        return [[0.1] * 8 for _ in texts]

    client.embed = embed

    saved_model = getattr(Settings, "_embed_model", None)
    started_a = threading.Event()
    started_b = threading.Event()
    emit_a = threading.Event()
    emitted_a = threading.Event()
    release = threading.Event()
    forwarded: dict[str, list] = {"a": [], "b": []}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ea, "get_embedding_client", lambda *a, **k: client)
        model = ea.CustomEmbedding()
    Settings._embed_model = model

    def _work_a() -> str:
        started_a.set()
        if not emit_a.wait(10):
            raise RuntimeError("A emit timeout")
        model._get_text_embeddings(["owned-by-a"])
        emitted_a.set()
        release.wait(10)
        return "a"

    def _work_b() -> str:
        started_b.set()
        release.wait(10)
        return "b"

    async def _scenario() -> None:
        task_a = asyncio.ensure_future(
            pipeline_mod._run_with_stall_guard(
                _work_a,
                worker_key="real-a",
                stall_timeout=20,
                progress_callback=lambda *value: forwarded["a"].append(value),
            )
        )
        task_b = None
        try:
            assert await asyncio.to_thread(started_a.wait, 5)
            task_b = asyncio.ensure_future(
                pipeline_mod._run_with_stall_guard(
                    _work_b,
                    worker_key="real-b",
                    stall_timeout=20,
                    progress_callback=lambda *value: forwarded["b"].append(value),
                )
            )
            assert await asyncio.to_thread(started_b.wait, 5)
            emit_a.set()
            assert await asyncio.to_thread(emitted_a.wait, 5)
        finally:
            emit_a.set()
            release.set()
            await asyncio.gather(
                *[task for task in (task_a, task_b) if task is not None],
                return_exceptions=True,
            )

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ea, "get_embedding_client", lambda *a, **k: client)
            control: list = []
            model.set_progress_callback(lambda *value: control.append(value))
            assert len(model._get_text_embeddings(["valid-control"])) == 1
            assert control == [(1, 1)], "合法单适配器对照没有收到进度"
            asyncio.run(_scenario())
    finally:
        Settings._embed_model = saved_model

    assert forwarded == {"a": [(1, 1)], "b": []}, "A 的进度被别的 worker 抢走了"
    _wait_released("real-a", "real-b")
    assert pipeline_mod.active_progress_callback() is None
    assert pipeline_mod.current_worker_heartbeat() is None


def test_registry_and_adapter_callback_change_together(monkeypatch):
    def old(*args):
        return None

    def new(*args):
        return None

    paused = threading.Event()
    resume = threading.Event()
    started = threading.Event()
    installed = threading.Event()
    visible = {'callback': None}
    def setter(value):
        if value is None:
            paused.set()
            assert resume.wait(5)
        visible['callback'] = value
    def install():
        started.set()
        pipeline_mod._install_progress_callback(new)
        installed.set()
    monkeypatch.setattr(pipeline_mod, 'set_progress_callback', setter)
    pipeline_mod._PROGRESS_CALLBACKS[:] = [old]
    remover = threading.Thread(target=pipeline_mod._restore_progress_callback, args=(old,))
    installer = threading.Thread(target=install)
    try:
        remover.start()
        assert paused.wait(5)
        installer.start()
        assert started.wait(5)
        installed.wait(0.1)
    finally:
        resume.set()
        if remover.ident is not None:
            remover.join(5)
        if installer.ident is not None:
            installer.join(5)
    assert not remover.is_alive() and not installer.is_alive()
    assert visible['callback'] is pipeline_mod._dispatch_progress
