"""P1-01 行为测试（rework01）：隔离的分科修复测试夹具。

覆盖：

* **R1** 首次导入/初始化失败/嵌套/中途异常都能恢复，且从不语义读取真实 settings；
* **R2** manager/model/client 缓存的键**与对象身份**都隔离并恢复，含"同键不同对象"反例；
* **R3** HTTP 客户端与其数据根绑定在同一隔离作用域，并可反复建立；
* **R4** 供应商替身是异步且字段符合真实契约，并用真实消费者验证；
* **R5** 网络 guard 默认组合进隔离，只有显式声明的 (host, port) 可连通；
* 真实三棵树在整份测试前后不变。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import textwrap

import pytest

from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SETTINGS_DIR = (REPO_ROOT / "data" / "user" / "settings").resolve()

REAL_DATA_ROOTS = (
    REPO_ROOT / "data" / "user" / "workspace" / "subjects",
    REPO_ROOT / "data" / "user" / "subjects",
    REPO_ROOT / "data" / "user" / "settings",
)

REAL_SUBJECT_IDS = (
    "常微分方程",
    "线性代数",
    "概率论",
    "离散数学",
    "数值分析",
    "复变函数",
)

#: 真实 settings 的语义读取探针：命中即失败（负例里用来证明探针有效）。
_REAL_READ_HITS: list[str] = []


def _real_data_digest() -> dict[str, dict[str, str]]:
    return {str(root): helpers.tree_digest(root) for root in REAL_DATA_ROOTS}


def _fingerprint_diff(before: dict, after: dict, path: str = "") -> list[str]:
    """逐路径列出指纹差异，便于定位泄漏（不输出设置值之外的业务内容）。"""
    out: list[str] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key not in before:
                out.append(f"{path}/{key}: only-after")
            elif key not in after:
                out.append(f"{path}/{key}: only-before")
            else:
                out.extend(_fingerprint_diff(before[key], after[key], f"{path}/{key}"))
    elif before != after:
        out.append(f"{path}: before={before!r} after={after!r}")
    return out


@pytest.fixture()
def real_settings_read_spy(monkeypatch):
    """禁止任何模块对真实 settings 目录做语义读取（只允许不透明字节哈希）。"""
    from deeptutor.services.config.runtime_settings import RuntimeSettingsService

    original = RuntimeSettingsService._load_or_create
    hits: list[str] = []

    def guarded(self, *args, **kwargs):
        try:
            resolved = Path(self.settings_dir).resolve()
        except OSError:  # pragma: no cover - defensive
            resolved = None
        if resolved == REAL_SETTINGS_DIR:
            hits.append(str(resolved))
            raise AssertionError(
                "semantic read of the real settings directory was attempted: "
                f"{resolved}"
            )
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RuntimeSettingsService, "_load_or_create", guarded)
    _REAL_READ_HITS.clear()
    yield hits


# ---------------------------------------------------------------------------
# R1：首次导入 / 失败回滚 / 嵌套 / 中途异常
# ---------------------------------------------------------------------------
def test_bootstrap_preserves_the_callers_environment_and_loaded_roots():
    """Bootstrap is temporary, including its first call in a process."""
    import os

    paths = helpers._module("deeptutor.multi_user.paths")
    env_before = dict(os.environ)
    root_before = paths.ADMIN_WORKSPACE_ROOT
    helpers.ensure_bootstrap_home()
    changed = sorted(
        key for key in env_before.keys() | os.environ.keys()
        if env_before.get(key) != os.environ.get(key)
    )
    assert changed == []
    assert paths.ADMIN_WORKSPACE_ROOT == root_before


@pytest.mark.parametrize("home_mode", ["unset", "repo", "caller"])
@pytest.mark.parametrize("fail_import", [False, True])
def test_cold_bootstrap_restores_state_and_can_retry(tmp_path, home_mode, fail_import):
    """Snapshot BEFORE bootstrap; cover unset home and a mid-import failure."""
    script = textwrap.dedent(
        """
        import importlib, json, os, sys
        from pathlib import Path
        from unittest.mock import patch
        repo, tmp, mode, fail = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4] == "True"
        sys.path.insert(0, str(repo)); os.chdir(repo)
        for key in tuple(os.environ):
            if "API_KEY" in key or key.startswith(("OPENAI_", "ANTHROPIC_", "CODEBUDDY_", "DEEPTUTOR_CODEBUDDY_")):
                os.environ.pop(key, None)
        if mode == "unset": os.environ.pop("DEEPTUTOR_HOME", None)
        else: os.environ["DEEPTUTOR_HOME"] = str(repo if mode == "repo" else tmp / "caller")
        from tests.phase1 import helpers
        paths = importlib.import_module("deeptutor.multi_user.paths")
        from deeptutor.services.path_service import PathService
        sentinel = PathService(tmp / "outside")
        PathService._instance = sentinel
        old_root, old_env = paths.ADMIN_WORKSPACE_ROOT, dict(os.environ)
        read_text, real_import = Path.read_text, importlib.import_module
        hits = []
        def guarded_read(self, *args, **kwargs):
            if self.resolve().is_relative_to(repo / "data/user/settings"):
                hits.append(str(self)); raise AssertionError("real settings semantic read")
            return read_text(self, *args, **kwargs)
        def failing_import(name, *args, **kwargs):
            if fail and name == "deeptutor.api.main": raise RuntimeError("cold import failure")
            return real_import(name, *args, **kwargs)
        with patch.object(Path, "read_text", guarded_read):
            if fail:
                with patch.object(importlib, "import_module", failing_import):
                    try: helpers.ensure_bootstrap_home()
                    except RuntimeError as exc: assert str(exc) == "cold import failure"
                    else: raise AssertionError("fault did not fire")
                assert helpers._BOOTSTRAP_HOME is None
                assert paths.ADMIN_WORKSPACE_ROOT == old_root
                assert dict(os.environ) == old_env
                assert PathService._instance is sentinel
            helpers.ensure_bootstrap_home()
            assert paths.ADMIN_WORKSPACE_ROOT == old_root
            assert dict(os.environ) == old_env
            assert PathService._instance is sentinel
            with helpers.isolated_runtime(tmp / "scope") as admin:
                assert paths.ADMIN_WORKSPACE_ROOT == admin
                assert PathService._instance is None
                assert helpers._module("deeptutor.services.config").PROJECT_ROOT == admin.parent
                from deeptutor.services.config.model_catalog import ModelCatalogService
                ModelCatalogService.get_instance(admin / "user/settings/model_catalog.json").load()
            assert paths.ADMIN_WORKSPACE_ROOT == old_root
            assert dict(os.environ) == old_env
            assert PathService._instance is sentinel
        print(json.dumps({"ok": True, "real_read_hits": hits}))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT), str(tmp_path), home_mode, str(fail_import)],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {"ok": True, "real_read_hits": []}


def test_setup_failure_rolls_back_changed_state(tmp_path, monkeypatch):
    """初始化中途抛异常时必须先回滚，再向外抛。

    注意：注入必须用 ``monkeypatch.context()``。直接调用 ``monkeypatch.undo()``
    会把根 conftest 中 autouse 夹具（共享同一个 monkeypatch 实例）的补丁一并撤销，
    从而制造与本次回滚无关的"差异"。
    """
    helpers.ensure_bootstrap_home()
    before = helpers.capture_runtime_fingerprint()
    original_optional = helpers._optional_module

    def injected_import(name):
        if name == "deeptutor.services.config.launch_settings":
            raise RuntimeError("injected setup failure")
        return original_optional(name)

    with monkeypatch.context() as injection:
        injection.setattr(helpers, "_optional_module", injected_import)
        with pytest.raises(RuntimeError, match="injected setup failure"):
            with helpers.isolated_runtime(tmp_path):
                pytest.fail("setup should have failed before yielding")

    after_state = helpers.capture_runtime_fingerprint()
    assert after_state == before, _fingerprint_diff(before, after_state)


def test_exception_inside_scope_and_nested_scopes_restore(tmp_path):
    helpers.ensure_bootstrap_home()
    before = helpers.capture_runtime_fingerprint()

    with pytest.raises(ValueError, match="boom"):
        with helpers.isolated_runtime(tmp_path / "outer") as outer:
            helpers.make_subject(outer, "外层科目")
            with helpers.isolated_runtime(tmp_path / "inner") as inner:
                assert inner != outer
                helpers.make_subject(inner, "内层科目")
                raise ValueError("boom")

    after_state = helpers.capture_runtime_fingerprint()
    assert after_state == before, _fingerprint_diff(before, after_state)


def test_real_settings_are_never_semantically_read(tmp_path, real_settings_read_spy):
    """正向：bootstrap + 隔离期间没有任何对真实 settings 的语义读取。"""
    from deeptutor.services.config.model_catalog import ModelCatalogService
    from deeptutor.services.config.runtime_settings import load_system_settings

    helpers.ensure_bootstrap_home()
    assert real_settings_read_spy == []

    with helpers.isolated_runtime(tmp_path) as admin:
        load_system_settings()
        ModelCatalogService.get_instance(admin / "user" / "settings" / "model_catalog.json").load()
    assert real_settings_read_spy == []


def test_real_settings_read_spy_actually_catches_a_read(real_settings_read_spy):
    """反向：探针确实能拦住对真实 settings 的读取，否则上一条是空洞的。"""
    from deeptutor.services.config.runtime_settings import RuntimeSettingsService

    service = RuntimeSettingsService(REAL_SETTINGS_DIR)
    with pytest.raises(AssertionError, match="semantic read of the real settings"):
        service.load_system()
    assert real_settings_read_spy == [str(REAL_SETTINGS_DIR)]


# ---------------------------------------------------------------------------
# R2：manager / model / client 缓存与身份
# ---------------------------------------------------------------------------
def test_caches_and_singletons_are_isolated_and_restored_by_identity(tmp_path):
    llm_client = helpers._module("deeptutor.services.llm.client")
    embed_client = helpers._module("deeptutor.services.embedding.client")
    catalog = helpers._module("deeptutor.services.config.model_catalog")
    kb_config = helpers._module("deeptutor.services.config.knowledge_base_config")
    knowledge_access = helpers._module("deeptutor.multi_user.knowledge_access")
    cron = helpers._module("deeptutor.services.cron.service")

    outer_llm = object()
    outer_embed = object()
    catalog_key = "/tmp/p1-sentinel/model_catalog.json"
    kb_key = "/tmp/p1-sentinel/kb_config.json"
    outer_catalog = object()
    outer_kb = object()

    llm_client._client = outer_llm
    embed_client._client = outer_embed
    catalog.ModelCatalogService._instances[catalog_key] = outer_catalog
    kb_config.KnowledgeBaseConfigService._instances[kb_key] = outer_kb
    cron_store = Path("/tmp/p1-sentinel/cron/jobs.json")
    cron._service = type("Sentinel", (), {"store_path": cron_store})()
    manager_cache_before = knowledge_access._manager_for.cache_info().currsize

    try:
        before = helpers.capture_runtime_fingerprint()

        with helpers.isolated_runtime(tmp_path) as admin:
            assert llm_client._client is None, "outer LLM singleton visible inside isolation"
            assert embed_client._client is None, "outer embedding singleton visible inside"
            assert catalog_key not in catalog.ModelCatalogService._instances
            assert kb_key not in kb_config.KnowledgeBaseConfigService._instances
            assert cron._service is None

            # 隔离内创建 tmp 实例
            catalog.ModelCatalogService.get_instance(
                admin / "user" / "settings" / "model_catalog.json"
            )
            kb_config.KnowledgeBaseConfigService.get_instance(
                admin / "knowledge_bases" / "kb_config.json"
            )
            knowledge_access._manager_for(str(admin / "knowledge_bases"))
            assert len(catalog.ModelCatalogService._instances) == 1
            assert len(kb_config.KnowledgeBaseConfigService._instances) == 1

        assert llm_client._client is outer_llm
        assert embed_client._client is outer_embed
        assert catalog.ModelCatalogService._instances[catalog_key] is outer_catalog
        assert kb_config.KnowledgeBaseConfigService._instances[kb_key] is outer_kb
        assert cron._service.store_path == cron_store
        assert knowledge_access._manager_for.cache_info().currsize == manager_cache_before
        after_state = helpers.capture_runtime_fingerprint()
        assert after_state == before, _fingerprint_diff(before, after_state)
    finally:
        llm_client._client = None
        embed_client._client = None
        catalog.ModelCatalogService._instances.pop(catalog_key, None)
        kb_config.KnowledgeBaseConfigService._instances.pop(kb_key, None)
        cron._service = None


def test_manager_lru_cache_keeps_the_original_function_object(tmp_path):
    knowledge_access = helpers._module("deeptutor.multi_user.knowledge_access")
    original = knowledge_access._manager_for
    original.cache_clear()
    assert original.cache_info().currsize == 0

    with helpers.isolated_runtime(tmp_path) as admin:
        inside = knowledge_access._manager_for
        assert inside is not original, "isolation must swap in a fresh lru wrapper"
        inside(str(admin / "knowledge_bases"))

    assert knowledge_access._manager_for is original
    assert original.cache_info().currsize == 0, "original lru cache was polluted"


def test_key_only_fingerprint_would_miss_a_same_key_object_swap(tmp_path):
    """坏对照：同键不同对象——键视图相同，身份视图必须不同。"""
    catalog = helpers._module("deeptutor.services.config.model_catalog")
    cache_name = (
        "deeptutor.services.config.model_catalog.ModelCatalogService._instances"
    )
    key = "/tmp/p1-identity/model_catalog.json"
    sentinel = object()
    catalog.ModelCatalogService._instances[key] = sentinel
    try:
        before = helpers.capture_runtime_fingerprint()
        identity_before = before["dicts"][cache_name][key]

        with helpers.isolated_runtime(tmp_path):
            catalog.ModelCatalogService._instances[key] = object()  # 同键，不同对象
            during = helpers.capture_runtime_fingerprint()
            identity_during = during["dicts"][cache_name][key]
            # 键视图完全相同：只看"有没有这个键"的旧指纹无法分辨
            assert key in catalog.ModelCatalogService._instances
            assert key in before["dicts"][cache_name]
            # 身份视图不同：新指纹能发现
            assert identity_during != identity_before

        assert catalog.ModelCatalogService._instances[key] is sentinel
        after_state = helpers.capture_runtime_fingerprint()
        assert after_state == before, _fingerprint_diff(before, after_state)
    finally:
        catalog.ModelCatalogService._instances.pop(key, None)


def test_event_bus_module_and_class_singletons_restore_together(tmp_path, monkeypatch):
    module = helpers._module("deeptutor.events.event_bus")
    outer = object()
    with monkeypatch.context() as patch:
        patch.setattr(module, "_event_bus", outer)
        patch.setattr(module.EventBus, "_instance", outer)
        patch.setattr(module.EventBus, "_initialized", True)
        before = helpers.capture_runtime_fingerprint()
        with helpers.isolated_runtime(tmp_path):
            assert module._event_bus is None
            assert module.EventBus._instance is None
            assert module.EventBus._initialized is False
            inner = module.get_event_bus()
            assert inner is not outer
            assert module.EventBus._instance is inner
        assert module._event_bus is outer
        assert module.EventBus._instance is outer
        assert module.EventBus._initialized is True
        assert helpers.capture_runtime_fingerprint() == before


# ---------------------------------------------------------------------------
# R3：HTTP 作用域
# ---------------------------------------------------------------------------
def test_default_subject_fixtures_are_valid_for_strict_storage(p1_subjects):
    from deeptutor.subjects.store import is_valid_subject_id

    for name in ("科目A", "科目B"):
        subject = p1_subjects[name]
        assert is_valid_subject_id(subject.subject_id)
        registry = json.loads((helpers.learning_root(subject.admin_root) / "index.json").read_text())
        record = next(item for item in registry if item["id"] == subject.subject_id)
        assert record["name"] == name
        assert type(record["created_at"]) is int
        assert json.loads((subject.root / "knowledge.json").read_text()) == []


def test_route_client_requires_an_isolated_scope():
    with pytest.raises(helpers.IsolationError, match="active isolated_runtime"):
        with helpers.route_client():
            pytest.fail("client was opened outside isolation")


def test_route_client_follows_the_active_scope_and_writes_only_to_tmp(tmp_path):
    with helpers.isolated_runtime(tmp_path / "a") as root_a:
        helpers.make_subject(root_a, "隔离科目A")
        with helpers.route_client() as client:
            body_a = client.get("/api/v1/subjects").text
            created = client.post(
                "/api/v1/subjects",
                data={"name": "路由写入科目", "term": "2026春"},
            )
        assert created.status_code in (200, 201), created.text
        written = list(helpers.learning_root(root_a).glob("路由写入科目"))
        assert written, "route write did not land in the isolated learning root"

    with helpers.isolated_runtime(tmp_path / "b") as root_b:
        helpers.make_subject(root_b, "隔离科目B")
        with helpers.route_client() as client:
            body_b = client.get("/api/v1/subjects").text

    assert "隔离科目A" in body_a and "隔离科目B" not in body_a
    assert "隔离科目B" in body_b and "隔离科目A" not in body_b
    for real_subject in REAL_SUBJECT_IDS:
        assert real_subject not in body_a
        assert real_subject not in body_b


def test_route_client_can_be_recreated_and_does_not_leak_between_scopes(tmp_path):
    with helpers.isolated_runtime(tmp_path / "one") as root:
        helpers.make_subject(root, "第一轮科目")
        with helpers.route_client() as first:
            assert "第一轮科目" in first.get("/api/v1/subjects").text
    # 第二次独立上下文必须可用，且看不到上一轮内容
    with helpers.isolated_runtime(tmp_path / "two") as root2:
        helpers.make_subject(root2, "第二轮科目")
        with helpers.route_client() as second:
            body = second.get("/api/v1/subjects").text
    assert "第二轮科目" in body
    assert "第一轮科目" not in body


def test_shared_process_wide_client_is_gone():
    with pytest.raises(helpers.IsolationError, match="removed in S01 rework01"):
        helpers.shared_http_client()


def test_full_lifespan_subprocess_starts_and_stops_under_tmp():
    """完整 lifespan 放在独立子进程里验收：cron 等后台资源锚定在 tmp home。"""
    result = helpers.full_lifespan_probe()
    assert result.get("ok") is True, result
    assert result["cron_under_tmp"] is True, result
    assert result["subjects_status"] == 200, result
    # 真实六科不得出现在 tmp home 的响应里
    for real_subject in REAL_SUBJECT_IDS:
        assert real_subject not in result["subjects_body"], real_subject
    assert result["exit_code"] == 0
    assert result["shutdown_ok"] is True
    assert result["home_removed"] is True


# ---------------------------------------------------------------------------
# R4：供应商替身契约
# ---------------------------------------------------------------------------
def test_provider_stubs_match_the_async_production_contracts():
    llm = helpers.FakeLLMClient(text="stub-answer", finish_reason="stop")
    embedding = helpers.FakeEmbeddingClient(dimensions=4)
    stt = helpers.FakeSTT(text="stub-transcript")

    async def scenario():
        text = await llm.complete("q1")
        response = await llm.complete_response("q2")
        vectors_a = await embedding.embed(["同一条文本"])
        vectors_b = await embedding.embed("同一条文本")
        transcript = await stt.transcribe(Path("/tmp/fake.wav"))
        return text, response, vectors_a, vectors_b, transcript

    text, response, vectors_a, vectors_b, transcript = asyncio.run(scenario())

    assert text == "stub-answer"
    # 真实契约：complete_response 返回 TutorResponse，消费者读 .content
    from deeptutor.services.llm.types import TutorResponse

    assert isinstance(response, TutorResponse)
    assert response.content == "stub-answer"
    assert response.finish_reason == "stop"
    assert response.usage["completion_tokens"] == 0

    assert vectors_a == vectors_b
    assert len(vectors_a[0]) == 4

    assert transcript["text"] == "stub-transcript"
    assert transcript["model"] == "stub-stt"
    assert "base_url" in transcript
    assert "error" not in transcript

    assert [call.payload["prompt"] for call in llm.calls] == ["q1", "q2"]
    assert stt.call_count == 1


def test_stt_failure_payload_keeps_production_semantics():
    async def scenario():
        return await helpers.FakeSTT(error="STT 服务未配置").transcribe(Path("/tmp/fake.wav"))

    payload = asyncio.run(scenario())
    assert payload["text"] == ""
    assert payload["error"] == "STT 服务未配置"


def test_complete_response_drives_a_real_consumer(monkeypatch):
    """用真实生产消费者 ``complete_subject_text`` 验证 content/finish_reason。"""
    from deeptutor.services.llm import factory
    from deeptutor.subjects.generation import complete_subject_text

    fake = helpers.FakeLLMClient(text="  真实消费者拿到的正文  ")
    monkeypatch.setattr(factory, "complete_response", fake.complete_response)

    text = asyncio.run(
        complete_subject_text(
            prompt="p", system_prompt="s", model="m", api_key="fake-key", base_url="https://stub.invalid"
        )
    )
    assert text == "真实消费者拿到的正文"
    assert fake.call_count == 1


def test_truncated_response_drives_the_real_consumer_error(monkeypatch):
    from deeptutor.services.llm import factory
    from deeptutor.services.llm.exceptions import LLMReasoningBudgetExhausted
    from deeptutor.subjects.generation import complete_subject_text

    fake = helpers.FakeLLMClient(text="", finish_reason="length")
    monkeypatch.setattr(factory, "complete_response", fake.complete_response)

    with pytest.raises(LLMReasoningBudgetExhausted):
        asyncio.run(
            complete_subject_text(
                prompt="p", system_prompt="s", model="m", api_key="fake-key",
                base_url="https://stub.invalid",
            )
        )


def test_provider_stubs_install_at_the_real_seams(monkeypatch):
    """安装后，真实调用点取到的就是替身（而不是"只调用 fake 自己"）。"""
    llm = helpers.FakeLLMClient()
    embedding = helpers.FakeEmbeddingClient()
    stt = helpers.FakeSTT()
    # Load a real consumer BEFORE installing stubs to exercise imported aliases.
    loader = helpers._module("deeptutor.services.rag.pipelines.llamaindex.document_loader")
    helpers.install_provider_stubs(monkeypatch, llm=llm, embedding=embedding, stt=stt)

    from deeptutor.services import embedding as embedding_package
    from deeptutor.services import llm as llm_package
    from deeptutor.services.asr.transcribe import transcribe
    from deeptutor.services.embedding.client import get_embedding_client
    from deeptutor.services.llm.client import get_llm_client

    assert get_llm_client() is llm
    assert get_embedding_client() is embedding
    assert llm_package.get_llm_client() is llm
    assert embedding_package.get_embedding_client() is embedding
    assert loader.get_llm_client() is llm
    assert loader.get_embedding_client() is embedding

    async def scenario():
        return await transcribe(Path("/tmp/fake.wav"))

    assert asyncio.run(scenario())["text"] == "stub-transcript"
    assert stt.call_count == 1


# ---------------------------------------------------------------------------
# R5：网络 guard 默认生效
# ---------------------------------------------------------------------------
def test_network_guard_is_composed_into_the_isolation_fixture(p1_runtime, tmp_path):
    """p1_runtime 未另行申请 guard 时，未声明出口也必须被阻断。"""
    with pytest.raises(helpers.ExternalNetworkBlocked):
        socket.create_connection(("192.0.2.1", 9999), timeout=1)

    with pytest.raises(helpers.ExternalNetworkBlocked):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.sendto(b"review", ("192.0.2.1", 9999))
        finally:
            probe.close()

    with pytest.raises(helpers.ExternalNetworkBlocked):
        socket.getaddrinfo("example.invalid", 80)

    with pytest.raises(helpers.ExternalNetworkBlocked):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.connect(("127.0.0.1", 31999))
        finally:
            probe.close()


def test_only_explicitly_declared_localhost_endpoint_is_allowed(tmp_path):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        with helpers.isolated_runtime(
            tmp_path, allow_endpoints=[("127.0.0.1", port)]
        ):
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                assert client.getpeername()[1] == port
            other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(helpers.ExternalNetworkBlocked):
                    other.connect(("127.0.0.1", port + 1))
            finally:
                other.close()
    finally:
        server.close()


def test_socket_functions_are_restored_after_isolation(tmp_path):
    originals = {
        "connect": socket.socket.connect,
        "sendto": socket.socket.sendto,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
    }
    with helpers.isolated_runtime(tmp_path):
        assert socket.socket.connect is not originals["connect"]
    assert socket.socket.connect is originals["connect"]
    assert socket.socket.sendto is originals["sendto"]
    assert socket.create_connection is originals["create_connection"]
    assert socket.getaddrinfo is originals["getaddrinfo"]


def test_udp_sendmsg_uses_its_destination_argument_and_declared_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        endpoint = server.getsockname()
        with helpers.block_external_network(allow_endpoints=[endpoint]):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                assert sender.sendmsg([b"approved"], [], 0, endpoint) == 8
                assert server.recv(32) == b"approved"
                with pytest.raises(helpers.ExternalNetworkBlocked):
                    sender.sendmsg([b"denied"], [], 0, ("192.0.2.1", 80))


def test_hostname_resolvers_are_guarded_and_restored(monkeypatch):
    from unittest.mock import Mock

    original = Mock(side_effect=AssertionError("DNS transport was reached"))
    monkeypatch.setattr(socket, "gethostbyname", original)
    monkeypatch.setattr(socket, "gethostbyname_ex", original)
    with helpers.block_external_network():
        for resolver in (socket.gethostbyname, socket.gethostbyname_ex):
            with pytest.raises(helpers.ExternalNetworkBlocked):
                resolver("example.invalid")
    assert original.call_count == 0
    assert socket.gethostbyname is original
    assert socket.gethostbyname_ex is original


def test_remote_endpoint_cannot_be_declared_as_a_local_stub():
    with pytest.raises(helpers.IsolationError, match="localhost"):
        with helpers.block_external_network(allow_endpoints=[("192.0.2.1", 80)]):
            pytest.fail("remote allowlist was accepted")


def test_nested_local_stub_can_be_declared_inside_p1_runtime(p1_runtime):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(2)
        endpoint = server.getsockname()
        outer_connect = socket.socket.connect
        with helpers.block_external_network(allow_endpoints=[endpoint]):
            with socket.create_connection(endpoint, timeout=2):
                accepted, _ = server.accept()
                accepted.close()
        assert socket.socket.connect is outer_connect
        with pytest.raises(helpers.ExternalNetworkBlocked):
            socket.create_connection(endpoint, timeout=2)


# ---------------------------------------------------------------------------
# 科目 / 知识库隔离与真实数据不变
# ---------------------------------------------------------------------------
def test_fixture_data_is_written_and_deleted_only_under_tmp(p1_runtime):
    """可观测的 tmp 写入/删除 + 真实三棵树不变（替代原恒真断言）。"""
    real_before = _real_data_digest()
    scratch = p1_runtime.parents[1]

    subject = helpers.make_subject(p1_runtime, "隔离科目A")
    helpers.make_kb(helpers.global_kb_root(p1_runtime), "隔离库", "global-only")

    created = sorted(p for p in scratch.rglob("*") if p.is_file())
    assert created
    for path in created:
        helpers.assert_within(path, scratch)

    subject_file = subject.root / "profile.json"
    assert subject_file.is_file()
    subject_file.unlink()
    assert not subject_file.exists()
    assert helpers.tree_digest(subject.root)

    assert _real_data_digest() == real_before


def test_same_name_kbs_have_independent_markers(p1_subjects):
    subject_a = p1_subjects["科目A"]
    subject_b = p1_subjects["科目B"]
    kb_a = subject_a.knowledge_bases / "shared-kb"
    kb_b = subject_b.knowledge_bases / "shared-kb"

    assert helpers.kb_markers(kb_a) == {"科目A-only"}
    assert helpers.kb_markers(kb_b) == {"科目B-only"}
    assert helpers.kb_markers(Path(p1_subjects["global"])) == {"global-only"}
    assert helpers.kb_markers(kb_a).isdisjoint(helpers.kb_markers(kb_b))


def test_kb_lookup_stays_inside_its_own_subject_root(p1_subjects):
    subject_a = p1_subjects["科目A"]
    tree_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in subject_a.root.rglob("*")
        if path.is_file() and path.suffix in {".json", ".txt"}
    )
    assert "科目B-only" not in tree_text
    assert "global-only" not in tree_text
    assert "科目A-only" in tree_text


def test_tree_digest_fails_closed_on_unreadable_subtree(tmp_path):
    """R7：目录遍历错误必须抛错，而不是被当成没有变化。"""
    tree = tmp_path / "tree"
    (tree / "locked").mkdir(parents=True)
    (tree / "locked" / "hidden.txt").write_text("x\n", encoding="utf-8")

    baseline = helpers.tree_digest(tree)
    assert "locked/hidden.txt" in baseline

    original = helpers.os.walk

    def failing_walk(root, **kwargs):
        onerror = kwargs.get("onerror")

        def walker(top, topdown=True, onerror=None, followlinks=False):  # noqa: ARG001
            if onerror is not None:
                onerror(PermissionError(f"simulated unreadable subtree: {top}"))
            return iter(())

        return walker(root, onerror=onerror)

    helpers.os.walk = failing_walk
    try:
        with pytest.raises(PermissionError, match="simulated unreadable subtree"):
            helpers.tree_digest(tree)
    finally:
        helpers.os.walk = original


def test_tree_digest_detects_added_removed_and_modified(tmp_path):
    tree = tmp_path / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "sub" / "a.txt").write_text("a\n", encoding="utf-8")
    (tree / "b.txt").write_text("b\n", encoding="utf-8")

    baseline = helpers.tree_digest(tree)
    assert helpers.tree_digest(tree) == baseline

    (tree / "b.txt").write_text("b-changed\n", encoding="utf-8")
    assert helpers.tree_digest(tree)["b.txt"] != baseline["b.txt"]
    (tree / "c.txt").write_text("c\n", encoding="utf-8")
    assert "c.txt" in helpers.tree_digest(tree)
    (tree / "sub" / "a.txt").unlink()
    assert "sub/a.txt" not in helpers.tree_digest(tree)
    assert helpers.tree_digest(tmp_path / "absent") == {}


def test_failure_injector_fires_once_at_the_requested_call():
    def explode():
        return ValueError("injected at the commit point")

    calls: list[int] = []

    def operation(value: int) -> int:
        calls.append(value)
        return value * 2

    guarded = helpers.FailureInjector(explode, at=2).wrap(operation)
    assert guarded(1) == 2
    with pytest.raises(ValueError, match="injected at the commit point"):
        guarded(2)
    assert guarded(3) == 6
    assert calls == [1, 3]

    after_calls: list[int] = []

    def side_effect(value: int) -> int:
        after_calls.append(value)
        return value

    injector = helpers.FailureInjector(explode, at=1, when="after")
    with pytest.raises(ValueError, match="injected at the commit point"):
        injector.wrap(side_effect)(7)
    assert after_calls == [7]
    with pytest.raises(ValueError):
        helpers.FailureInjector(when="sideways")
