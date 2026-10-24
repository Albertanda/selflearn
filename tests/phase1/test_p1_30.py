"""P1-30 行为测试：embedding 进程共享锁初始化（C07）。

目标：不同线程/event loop 真正共享**同一把**锁；首次并发不会各建一把 guard；
异常与取消都在 finally 释放；``batch_delay=0`` 只是"不额外加配置延时"，
发帖仍然串行；provider 请求字段（dimensions / input_type / 模型）保持原样。

必证场景（对应卡内清单）：

* 多个真实线程通过 barrier 首次获取同一个 lock（identity 相同），且 guard 不再被重建；
* 跨线程、跨 event loop 互斥（最大并发为 1）；
* embed 抛异常、任务被取消后下一个请求仍能进入；
* delay=0 没有额外配置延时，但两次 post 不重叠；
* 现有 ``tests/services/embedding/test_client_runtime.py`` 继续通过（阶段命令）。
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from deeptutor.services.embedding.client import EmbeddingClient
from deeptutor.services.embedding.config import EmbeddingConfig


class _ConcurrencyAdapter:
    """记录并发进入的假 adapter；不触网、不读配置。"""

    SUPPORTS_INPUT_TYPE = False
    instances: list["_ConcurrencyAdapter"] = []

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.calls: list[Any] = []
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.entered: list[float] = []
        self.left: list[float] = []
        _ConcurrencyAdapter.instances.append(self)

    async def embed(self, request):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.entered.append(time.monotonic())
        try:
            await asyncio.sleep(0.05)
            self.calls.append(request)
        finally:
            with self.lock:
                self.active -= 1
                self.left.append(time.monotonic())
        return type(
            "Resp",
            (),
            {"embeddings": [[0.5] * (request.dimensions or 2) for _ in request.texts]},
        )()


def _build_config(*, delay: float = 0.0, dim: int = 4, batch_size: int = 8) -> EmbeddingConfig:
    return EmbeddingConfig(
        model="stub-embedding-model",
        api_key="sk-test",
        base_url="https://stub.invalid/v1/embeddings",
        effective_url="https://stub.invalid/v1/embeddings",
        binding="openai",
        provider_name="openai",
        provider_mode="standard",
        dim=dim,
        send_dimensions=None,
        batch_size=batch_size,
        request_timeout=30,
        batch_delay=delay,
    )


def _build_client(monkeypatch, **kwargs) -> EmbeddingClient:
    _ConcurrencyAdapter.instances = []
    monkeypatch.setattr(
        "deeptutor.services.embedding.client._resolve_adapter_class",
        lambda _b: _ConcurrencyAdapter,
    )
    return EmbeddingClient(_build_config(**kwargs))


@pytest.fixture(autouse=True)
def _reset_shared_lock(monkeypatch):
    """本文件会刻意把进程共享锁重置成"首次使用"状态，退出时还原。"""
    monkeypatch.setattr(EmbeddingClient, "_spacing_lock", None)
    monkeypatch.setattr(EmbeddingClient, "_last_request_monotonic", 0.0)
    _ConcurrencyAdapter.instances = []
    yield
    EmbeddingClient._spacing_lock = None
    EmbeddingClient._last_request_monotonic = 0.0


# ---------------------------------------------------------------------------
# 首次并发只建立一把锁
# ---------------------------------------------------------------------------
def test_concurrent_first_use_builds_exactly_one_shared_lock():
    threads = 12
    barrier = threading.Barrier(threads)
    locks: list[int] = []
    guards: list[int] = []
    errors: list[BaseException] = []
    guard_before = EmbeddingClient._thread_guard

    def _first_use() -> None:
        try:
            barrier.wait(5)
            locks.append(id(EmbeddingClient._global_spacing_lock()))
            guards.append(id(EmbeddingClient._thread_guard))
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    workers = [threading.Thread(target=_first_use) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)

    assert not errors, errors
    assert len(locks) == threads
    assert len(set(locks)) == 1, "线程各自建立了不同的共享锁"
    # guard 也在类定义时建立一次，不再被每次调用重建
    assert set(guards) == {id(guard_before)}
    assert EmbeddingClient._thread_guard is guard_before
    assert EmbeddingClient._spacing_lock is not None


def test_the_detector_can_see_the_pre_fix_race():
    """坏对照：复现"每次调用重建 guard"的旧写法，探针必须能发现两把锁。"""

    class _Legacy:
        _spacing_lock: Any = None
        _thread_guard: Any = None

        @classmethod
        def global_lock(cls):
            if cls._spacing_lock is None:
                cls._thread_guard = threading.Lock()  # ← 旧实现的缺陷
                with cls._thread_guard:
                    if cls._spacing_lock is None:
                        time.sleep(0.01)
                        cls._spacing_lock = threading.Lock()
            return cls._spacing_lock

    threads = 8
    barrier = threading.Barrier(threads)
    seen: list[int] = []
    lock = threading.Lock()

    def _race() -> None:
        barrier.wait(5)
        value = id(_Legacy.global_lock())
        with lock:
            seen.append(value)

    workers = [threading.Thread(target=_race) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)

    assert len(set(seen)) > 1, "对照应当观察到多把锁；否则本用例证明不了探针有效"


# ---------------------------------------------------------------------------
# 跨线程 / 跨 event loop 互斥
# ---------------------------------------------------------------------------
def test_two_event_loops_in_two_threads_are_mutually_exclusive(monkeypatch):
    client = _build_client(monkeypatch, delay=0.0)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _run_in_own_loop() -> None:
        async def _scenario() -> None:
            barrier.wait(5)
            await client.embed(["alpha", "beta"])

        try:
            asyncio.run(_scenario())
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    workers = [threading.Thread(target=_run_in_own_loop) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)

    assert not errors, errors
    adapter = _ConcurrencyAdapter.instances[0]
    assert len(adapter.calls) == 2
    assert adapter.max_active == 1, "两个 event loop 的 post 发生了重叠"
    # 串行而不是并发：第二次进入晚于第一次离开
    assert adapter.entered[1] >= adapter.left[0]


def test_a_second_client_shares_the_same_lock(monkeypatch):
    first = _build_client(monkeypatch)
    second = EmbeddingClient(_build_config())
    assert first._global_spacing_lock() is second._global_spacing_lock()
    assert first._global_spacing_lock() is EmbeddingClient._spacing_lock


# ---------------------------------------------------------------------------
# 释放：异常 / 取消
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exception_releases_the_shared_lock():
    async def _boom() -> None:
        async with EmbeddingClient._hold_spacing_lock():
            raise RuntimeError("inside the throttle")

    with pytest.raises(RuntimeError):
        await _boom()

    await asyncio.wait_for(_acquire_and_release(), timeout=2)
    assert not EmbeddingClient._spacing_lock.locked()


@pytest.mark.asyncio
async def test_cancellation_releases_the_shared_lock():
    entered = asyncio.Event()

    async def _hold_forever() -> None:
        async with EmbeddingClient._hold_spacing_lock():
            entered.set()
            await asyncio.sleep(60)

    task = asyncio.ensure_future(_hold_forever())
    await asyncio.wait_for(entered.wait(), timeout=2)
    assert EmbeddingClient._spacing_lock.locked()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.wait_for(_acquire_and_release(), timeout=2)
    assert not EmbeddingClient._spacing_lock.locked()


@pytest.mark.asyncio
async def test_a_failing_embed_does_not_wedge_the_throttle(monkeypatch):
    class _Failing(_ConcurrencyAdapter):
        async def embed(self, request):
            raise RuntimeError("provider exploded")

    monkeypatch.setattr(
        "deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _Failing
    )
    client = EmbeddingClient(_build_config())
    with pytest.raises(RuntimeError):
        await client.embed(["x"])
    assert not EmbeddingClient._spacing_lock.locked()


async def _acquire_and_release() -> None:
    async with EmbeddingClient._hold_spacing_lock():
        return None


# ---------------------------------------------------------------------------
# delay=0 仍然串行，配置行为不变
# ---------------------------------------------------------------------------
class _GateAdapter:
    """事件驱动的假 adapter：谁在 post 里、谁在等锁，全部由 Event 决定。"""

    SUPPORTS_INPUT_TYPE = False
    instances: list["_GateAdapter"] = []

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.calls: list[Any] = []
        self.entered: list[int] = []
        self.left: list[int] = []
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.first_entered = threading.Event()
        self.release_first = threading.Event()
        _GateAdapter.instances.append(self)

    async def embed(self, request):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            index = len(self.entered)
            self.entered.append(index)
        try:
            if index == 0:
                self.first_entered.set()
                # 第一发一直占着锁，直到测试放行：第二发如果没被锁挡住就会立刻进入
                assert await asyncio.to_thread(self.release_first.wait, 10)
            self.calls.append(request)
        finally:
            with self._lock:
                self.active -= 1
                self.left.append(index)
        return type(
            "Resp",
            (),
            {"embeddings": [[0.5] * (request.dimensions or 2) for _ in request.texts]},
        )()


def _build_gate_client(monkeypatch, *, delay: float) -> EmbeddingClient:
    _GateAdapter.instances = []
    monkeypatch.setattr(
        "deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _GateAdapter
    )
    return EmbeddingClient(_build_config(delay=delay))


class _InstantAdapter(_ConcurrencyAdapter):
    """无内部 sleep 的假 adapter：让可控 clock 只观察到 client 自己的等待。"""

    async def embed(self, request):
        self.calls.append(request)
        return type(
            "Resp",
            (),
            {"embeddings": [[0.5] * (request.dimensions or 2) for _ in request.texts]},
        )()


def _build_instant_client(monkeypatch, *, delay: float) -> EmbeddingClient:
    _InstantAdapter.instances = []
    monkeypatch.setattr(
        "deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _InstantAdapter
    )
    return EmbeddingClient(_build_config(delay=delay))


def _record_sleeps(monkeypatch) -> list[float]:
    """把 ``asyncio.sleep`` 换成记录器（不真正等待），并冻结 ``time.monotonic``。

    锁未被争用时 ``_hold_spacing_lock`` 的 poll 不会执行，因此记录到的每一次
    sleep 都只能是"配置延时"分支发出的。
    """
    sleeps: list[float] = []

    async def _record(duration, *args, **kwargs):
        sleeps.append(duration)

    monkeypatch.setattr(asyncio, "sleep", _record)
    # 时钟从 0 开始：`_last_request_monotonic` 也被重置为 0，第一次调用必须等待
    # 完整的配置间隔（时钟越大反而"已经等够"，观测不到配置分支）。
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    return sleeps


def test_delay_zero_serializes_posts_without_extra_config_delay(monkeypatch):
    """真实线程 + Event 证明互斥；可控 clock 证明零 delay 不加配置 sleep。

    没有任何 wall-clock 差值断言：第二发能不能进入由第一发持有的 Event 决定。
    """
    client = _build_gate_client(monkeypatch, delay=0.0)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _run(index: int) -> None:
        async def _scenario() -> None:
            barrier.wait(5)
            await client.embed([f"chunk-{index}"])

        try:
            asyncio.run(_scenario())
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    workers = [threading.Thread(target=_run, args=(index,)) for index in range(2)]
    for worker in workers:
        worker.start()
    adapter = _GateAdapter.instances[0]
    try:
        assert adapter.first_entered.wait(5), "first post never entered"
        # 第一发仍占着锁（它要等 release_first）：第二发必须还没进入
        assert adapter.left == []
        assert adapter.calls == []
    finally:
        adapter.release_first.set()
        for worker in workers:
            worker.join(20)

    assert not errors, errors
    assert adapter.max_active == 1
    assert adapter.entered == [0, 1]
    assert adapter.left == [0, 1]
    assert len(adapter.calls) == 2

    # 零 delay：配置延时分支根本不执行（锁空闲，poll 也不会执行）
    instant = _build_instant_client(monkeypatch, delay=0.0)
    monkeypatch.setattr(EmbeddingClient, "_spacing_lock", None)
    monkeypatch.setattr(EmbeddingClient, "_last_request_monotonic", 0.0)
    sleeps = _record_sleeps(monkeypatch)
    asyncio.run(instant.embed(["no-delay"]))
    assert sleeps == [], sleeps

    # 正对照：同一记录器能看见非零 delay 的等待，证明上面的 [] 不是记录器失灵
    monkeypatch.setattr(EmbeddingClient, "_spacing_lock", None)
    monkeypatch.setattr(EmbeddingClient, "_last_request_monotonic", 0.0)
    delayed = _build_instant_client(monkeypatch, delay=0.2)
    sleeps.clear()
    asyncio.run(delayed.embed(["with-delay"]))
    assert sleeps == [pytest.approx(0.2)], sleeps


def test_configured_delay_is_applied_through_the_clock(monkeypatch):
    """非零 delay 必须真的等待"剩余间隔"，用冻结时钟直接读出睡眠时长。"""
    client = _build_instant_client(monkeypatch, delay=0.2)
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    sleeps: list[float] = []

    async def _record_sleep(duration, *args, **kwargs):
        sleeps.append(duration)

    monkeypatch.setattr(asyncio, "sleep", _record_sleep)

    asyncio.run(client.embed(["first"]))
    assert len(sleeps) == 1 and sleeps[0] == pytest.approx(0.2), sleeps

    # 时钟前进 0.15s：剩余间隔必须正好是 0.05s
    clock["now"] += 0.15
    sleeps.clear()
    asyncio.run(client.embed(["second"]))
    assert len(sleeps) == 1 and sleeps[0] == pytest.approx(0.05), sleeps

    # 时钟前进超过间隔：不再等待
    clock["now"] += 5.0
    sleeps.clear()
    asyncio.run(client.embed(["third"]))
    assert sleeps == [], sleeps
    assert len(_ConcurrencyAdapter.instances) == 1


@pytest.mark.asyncio
async def test_request_fields_are_unchanged(monkeypatch):
    class _RoleAware(_ConcurrencyAdapter):
        SUPPORTS_INPUT_TYPE = True

    _ConcurrencyAdapter.instances = []
    monkeypatch.setattr(
        "deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _RoleAware
    )
    client = EmbeddingClient(_build_config(dim=6, batch_size=2))
    await client.embed(["a", "b", "c"], input_type="search_query")

    adapter = _RoleAware.instances[0]
    assert [request.dimensions for request in adapter.calls] == [6, 6]
    assert [request.model for request in adapter.calls] == [
        "stub-embedding-model",
        "stub-embedding-model",
    ]
    assert [request.input_type for request in adapter.calls] == ["search_query", "search_query"]
    # adapter 仍拿到原始配置；本阶段没有给请求加 encoding_format 之类的新字段
    assert adapter.config["dimensions"] == 6
    assert adapter.config["model"] == "stub-embedding-model"
    assert set(adapter.config) == {
        "api_key",
        "base_url",
        "api_version",
        "model",
        "dimensions",
        "send_dimensions",
        "request_timeout",
        "extra_headers",
    }
