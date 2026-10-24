"""第一阶段共享夹具。

夹具是**显式**的（非 autouse），因此 ``tests/phase1/test_p1_00.py`` 等既有测试不受影响；
但一旦使用 :func:`p1_runtime`，隔离、**网络 guard** 与缓存/单例恢复会一起生效，测试作者
不需要另外记得申请 guard。

用法::

    def test_something(p1_runtime, p1_route_client):
        assert p1_runtime.is_dir()      # 已重定向的 tmp admin root

退出时 :mod:`tests.phase1.helpers` 会把 roots、单例、字典缓存、lru 工厂与整份
``os.environ`` 按原对象写回；需要直接证明这一点的测试应使用
``helpers.redirect_runtime`` / ``helpers.restore_runtime`` 并比较指纹。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from tests.phase1 import helpers


@pytest.fixture
def p1_runtime(tmp_path: Path) -> Iterator[Path]:
    """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root


@pytest.fixture
def p1_subjects(p1_runtime: Path) -> dict:
    """在隔离根下建 A / B / global 三处**同名**知识库，各带独立标记。"""
    subjects = helpers.make_same_name_kbs(p1_runtime)
    subjects["_admin_root"] = p1_runtime
    return subjects


@pytest.fixture
def p1_llm() -> helpers.FakeLLMClient:
    """可 await 的 LLM 替身（未安装；见 :func:`p1_providers`）。"""
    return helpers.FakeLLMClient()


@pytest.fixture
def p1_embedding() -> helpers.FakeEmbeddingClient:
    return helpers.FakeEmbeddingClient()


@pytest.fixture
def p1_stt() -> helpers.FakeSTT:
    return helpers.FakeSTT()


@pytest.fixture
def p1_providers(
    monkeypatch: pytest.MonkeyPatch,
    p1_runtime: Path,
    p1_llm: helpers.FakeLLMClient,
    p1_embedding: helpers.FakeEmbeddingClient,
    p1_stt: helpers.FakeSTT,
) -> dict:
    """把三个替身装到真实被调用的模块上，避免任何真实供应商调用。"""
    return helpers.install_provider_stubs(
        monkeypatch, llm=p1_llm, embedding=p1_embedding, stt=p1_stt
    )


@pytest.fixture
def p1_route_client(p1_runtime: Path) -> Iterator[object]:
    """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
    with helpers.route_client() as client:
        yield client
