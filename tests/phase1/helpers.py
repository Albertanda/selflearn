"""第一阶段测试支撑原语。

设计约束（rework01 后）：

* **只做测试支撑**——不改变任何生产行为，不读真实密钥，不调用真实供应商。
* **导入前先 bootstrap**：``deeptutor.api.main`` 在 import 期就执行
  ``ensure_runtime_settings_files()`` / ``export_runtime_settings_to_env()``，会读写设置并把
  约 20 个键写进 ``os.environ``。因此所有会做配置 I/O 的模块都只在
  :func:`ensure_bootstrap_home` 建立的**临时 bootstrap home** 下导入一次；真实
  ``data/user/settings`` 只允许 P1-00 工具做不透明字节哈希。
* **重定向是事务性的**：:func:`redirect_runtime` 保存完整可恢复状态，任何一步失败都会
  先回滚再抛错——包括导入中途抛异常的情况。
* **隔离覆盖对象身份**：roots、PathService、settings/catalog/KB 服务缓存、LLM/embedding/
  cron/EventBus 单例、provider/agentic 池、lru_cache 工厂。恢复按**原对象**写回，不克隆、
  不关闭隔离外实例；环境按整份 ``os.environ`` 还原。
* **网络默认拒绝**：:func:`isolated_runtime` 默认组合 :func:`block_external_network`，
  只有显式声明的 ``(host, port)`` 或 unix 路径可连通；未 stub 的 provider 会直接失败。
* 所有字节快照按不透明二进制流读取；目录遍历错误 fail closed。
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
import copy
from dataclasses import dataclass, field
import functools
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]

LEARNING_SUBPATH = ("user", "workspace", "subjects")
OUTPUTS_SUBPATH = ("user", "subjects")
GLOBAL_KB_SUBPATH = ("knowledge_bases",)

#: 回环主机名的等价写法（仅用于把 (host, port) 白名单归一化）。
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


class IsolationError(RuntimeError):
    """隔离设置或恢复不完整。"""


class ExternalNetworkBlocked(OSError):
    """测试中试图连接未声明的外部地址。"""


# ---------------------------------------------------------------------------
# bootstrap home：所有配置 I/O 模块的导入都在这里发生
# ---------------------------------------------------------------------------
#: 在 import 期做配置 I/O 或固化 PROJECT_ROOT / 默认路径的模块。
_WARM_MODULES = (
    "deeptutor.services.config.loader",
    "deeptutor.services.config.launch_settings",
    "deeptutor.services.config.model_catalog",
    "deeptutor.services.config.knowledge_base_config",
    "deeptutor.config.defaults",
    "deeptutor.services.llm.config",
    "deeptutor.api.main",
)

_BOOTSTRAP_LOCK = threading.RLock()
_BOOTSTRAP_HOME: Path | None = None
_BOOTSTRAP_OWNER: tempfile.TemporaryDirectory | None = None
_ACTIVE_ROOT: ContextVar[Path | None] = ContextVar("p1_active_root", default=None)


def _module(name: str):
    return importlib.import_module(name)


def _optional_module(name: str):
    """可选的重量级模块；只在 ImportError 时降级。"""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def seed_bootstrap_home(home: Path) -> Path:
    """在 ``home`` 里准备一份**可信默认**配置，绝不复制真实 settings。

    使用项目自身的初始化器（``init_user_directories`` / ``ensure_runtime_settings_files``），
    它们在空 home 上生成内置默认值（含 ``main.yaml`` / ``agents.yaml``）。

    **顺序很关键**：必须先把所有路径常量指向新 home，再调用初始化器。否则
    ``get_path_service()`` 会复用指向真实根的旧 ``PathService`` 实例，初始化就写进
    ``data/user/settings``。
    """
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    os.environ["DEEPTUTOR_HOME"] = str(home)
    _apply_redirect(home / "data", home, None)
    from deeptutor.services.config import ensure_runtime_settings_files
    from deeptutor.services.setup.init import init_user_directories

    init_user_directories()
    ensure_runtime_settings_files()
    return home


def _runtime_home_outside_repo() -> bool:
    """调用者是否已经把 ``DEEPTUTOR_HOME`` 指向仓库之外的目录。"""
    raw = os.environ.get("DEEPTUTOR_HOME")
    if not raw or not str(raw).strip():
        return False
    try:
        candidate = Path(raw).expanduser().resolve()
    except OSError:  # pragma: no cover - defensive
        return False
    repo = REPO_ROOT.resolve()
    return candidate != repo and repo not in candidate.parents


def ensure_bootstrap_home() -> Path:
    """在临时配置下导入一次，正常/失败返回都恢复调用者的状态。

    bootstrap 只负责安全导入；实际配置访问必须在 isolated_runtime 内。
    不把调用者的环境、已有缓存或路径永久改成临时根。
    """
    global _BOOTSTRAP_HOME, _BOOTSTRAP_OWNER
    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAP_HOME is not None:
            return _BOOTSTRAP_HOME
        from deeptutor.runtime.home import get_runtime_home

        # These two imports only resolve paths; neither reads configuration.
        _module("deeptutor.multi_user.paths")
        _module("deeptutor.services.path_service")
        outer_home = get_runtime_home()
        snap = snapshot_runtime(loaded_only=True)
        loaded_before = set(sys.modules)
        owner = tempfile.TemporaryDirectory(prefix="p1-bootstrap-home-")
        home = Path(owner.name)
        try:
            with block_external_network():
                seed_bootstrap_home(home)
                for name in _WARM_MODULES:
                    importlib.import_module(name)
        except BaseException:
            owner.cleanup()
            raise
        finally:
            try:
                _restore_new_imports(loaded_before, home, outer_home)
            finally:
                restore_runtime(snap)
        _BOOTSTRAP_OWNER = owner
        _BOOTSTRAP_HOME = home
        return home


def _restore_new_imports(loaded_before: set[str], home: Path, outer_home: Path) -> None:
    """新导入模块没有外部快照：恢复默认别名并清除 bootstrap 实例。"""
    for name in set(sys.modules) - loaded_before:
        if not name.startswith("deeptutor."):
            continue
        module = sys.modules[name]
        if getattr(module, "PROJECT_ROOT", None) == home:
            module.PROJECT_ROOT = outer_home
    fresh_paths = {
        ("deeptutor.config.defaults", "_project_root"): outer_home,
        ("deeptutor.services.config.model_catalog", "CATALOG_PATH"):
            outer_home / "data/user/settings/model_catalog.json",
        ("deeptutor.services.config.knowledge_base_config", "DEFAULT_CONFIG_PATH"):
            outer_home / "data/knowledge_bases/kb_config.json",
    }
    for (name, attr), value in fresh_paths.items():
        if name not in loaded_before and name in sys.modules:
            setattr(sys.modules[name], attr, value)
    for name, attr in _SINGLETON_TARGETS:
        if name not in loaded_before and name in sys.modules:
            _set_dotted(sys.modules[name], attr, False if attr.endswith("_initialized") else None)
    for name, dotted, _deep in _DICT_TARGETS:
        if name in loaded_before or name not in sys.modules:
            continue
        value = _resolve_dotted(sys.modules[name], dotted)
        if name == "deeptutor.config.defaults":
            value["paths"] = {
                "user_data_dir": str(outer_home / "data/user"),
                "knowledge_bases_dir": str(outer_home / "data/knowledge_bases"),
                "user_log_dir": str(outer_home / "data/user/logs"),
            }
        else:
            value.clear()
    for name, attr in _FUNC_TARGETS:
        if name not in loaded_before and name in sys.modules:
            getattr(sys.modules[name], attr).cache_clear()


# ---------------------------------------------------------------------------
# 可恢复状态
# ---------------------------------------------------------------------------
@dataclass
class RuntimeSnapshot:
    """重定向前的可恢复状态。

    ``attrs`` 保存模块级路径常量与单例（按**原对象**写回，不克隆、不关闭）；
    ``dicts`` 保存字典缓存；``funcs`` 保存被替换的 lru_cache 工厂。
    """

    env: dict[str, str] = field(default_factory=dict)
    attrs: dict[tuple[str, str], Any] = field(default_factory=dict)
    dicts: dict[tuple[str, str, bool], dict] = field(default_factory=dict)
    funcs: dict[tuple[str, str], Any] = field(default_factory=dict)


#: 路径常量：隔离时改写，恢复时写回原值。
_ATTR_TARGETS = (
    ("deeptutor.multi_user.paths", "PROJECT_ROOT"),
    ("deeptutor.multi_user.paths", "ADMIN_WORKSPACE_ROOT"),
    ("deeptutor.multi_user.paths", "USERS_ROOT"),
    ("deeptutor.multi_user.paths", "SYSTEM_ROOT"),
    ("deeptutor.multi_user.paths", "LEGACY_MULTI_USER_ROOT"),
    ("deeptutor.multi_user.paths", "_legacy_migration_done"),
    # PROJECT_ROOT 的实际使用别名：config 包重导出、loader、launch_settings、defaults
    ("deeptutor.services.config", "PROJECT_ROOT"),
    ("deeptutor.services.config.loader", "PROJECT_ROOT"),
    ("deeptutor.services.config.launch_settings", "PROJECT_ROOT"),
    ("deeptutor.config.defaults", "_project_root"),
    # import 期固化的默认配置文件路径
    ("deeptutor.services.config.model_catalog", "CATALOG_PATH"),
    ("deeptutor.services.config.knowledge_base_config", "DEFAULT_CONFIG_PATH"),
)

#: 隔离内置 None、恢复时写回原对象（绝不调用 reset/close）。
_SINGLETON_TARGETS = (
    ("deeptutor.services.llm.client", "_client"),
    ("deeptutor.services.embedding.client", "_client"),
    ("deeptutor.services.llm.config", "_LLM_CONFIG_CACHE"),
    ("deeptutor.services.cron.service", "_service"),
    ("deeptutor.events.event_bus", "_event_bus"),
    ("deeptutor.events.event_bus", "EventBus._instance"),
    ("deeptutor.events.event_bus", "EventBus._initialized"),
)

#: (module, dotted, deep)。deep 只用于纯数据字典，持有实例的缓存一律浅拷贝。
_DICT_TARGETS = (
    ("deeptutor.multi_user.paths", "_path_services", False),
    ("deeptutor.services.config.runtime_settings", "RuntimeSettingsService._instances", False),
    ("deeptutor.services.config.model_catalog", "ModelCatalogService._instances", False),
    ("deeptutor.services.config.knowledge_base_config", "KnowledgeBaseConfigService._instances", False),
    ("deeptutor.services.llm.provider_factory", "_provider_pool", False),
    ("deeptutor.core.agentic.client", "_agentic_client_pool", False),
    ("deeptutor.services.rag.pipelines.llamaindex.pipeline", "_INDEX_WORKERS", False),
    ("deeptutor.config.defaults", "DEFAULTS", True),
)

#: lru_cache 工厂：测试期换成全新 wrapper，退出时写回**原函数对象**。
_FUNC_TARGETS = (("deeptutor.multi_user.knowledge_access", "_manager_for"),)


def _resolve_dotted(root_module, dotted: str) -> Any:
    target = root_module
    parts = dotted.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    return getattr(target, parts[-1])


def _set_dotted(root_module, dotted: str, value: Any) -> None:
    target = root_module
    parts = dotted.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)


def snapshot_runtime(*, loaded_only: bool = False) -> RuntimeSnapshot:
    """记录当前可恢复状态（环境、单例身份、字典缓存键与值身份、lru 工厂）。"""
    snap = RuntimeSnapshot()
    snap.env = dict(os.environ)
    for module_name, attr in _ATTR_TARGETS + _SINGLETON_TARGETS:
        module = sys.modules.get(module_name) if loaded_only else _optional_module(module_name)
        if module is not None:
            with contextlib.suppress(AttributeError):
                snap.attrs[(module_name, attr)] = _resolve_dotted(module, attr)
    path_service = _module("deeptutor.services.path_service")
    snap.attrs[("deeptutor.services.path_service", "PathService._instance")] = (
        path_service.PathService._instance
    )
    for module_name, dotted, deep in _DICT_TARGETS:
        module = sys.modules.get(module_name) if loaded_only else _optional_module(module_name)
        if module is None:
            continue
        try:
            current = _resolve_dotted(module, dotted)
        except AttributeError:
            continue
        if not isinstance(current, dict):
            raise IsolationError(f"{module_name}.{dotted} is not a dict cache")
        snap.dicts[(module_name, dotted, deep)] = (
            copy.deepcopy(current) if deep else dict(current)
        )
    for module_name, attr in _FUNC_TARGETS:
        module = sys.modules.get(module_name) if loaded_only else _optional_module(module_name)
        if module is not None and hasattr(module, attr):
            snap.funcs[(module_name, attr)] = getattr(module, attr)
    return snap


def restore_runtime(snap: RuntimeSnapshot) -> None:
    """把 :func:`snapshot_runtime` 记录的状态按原对象写回。"""
    os.environ.clear()
    os.environ.update(snap.env)
    for (module_name, attr), value in snap.attrs.items():
        if module_name == "deeptutor.services.path_service" and attr == "PathService._instance":
            _module(module_name).PathService._instance = value
            continue
        module = sys.modules.get(module_name)
        if module is not None:
            _set_dotted(module, attr, value)
    for module_name, attr in _FUNC_TARGETS:
        module = sys.modules.get(module_name)
        if module is not None and (module_name, attr) in snap.funcs:
            setattr(module, attr, snap.funcs[(module_name, attr)])
    for (module_name, dotted, deep), value in snap.dicts.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        target = _resolve_dotted(module, dotted)
        target.clear()
        target.update(copy.deepcopy(value) if deep else value)


def _ref(value: Any) -> Any:
    """身份标记：实例按对象身份，纯数据容器按内容递归比较。

    只有"持有实例"的缓存才需要身份语义；``DEFAULTS`` 这类纯数据字典在恢复时会被
    重建为内容相等的新对象，按身份比较会误报漂移。不输出任何设置值以外的内容。
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _ref(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_ref(item) for item in value]
    return f"{type(value).__name__}@{id(value)}"


def capture_runtime_fingerprint() -> dict[str, Any]:
    """可比较指纹：完整环境、路径别名、单例身份、缓存键**与值身份**。"""
    paths = _module("deeptutor.multi_user.paths")
    path_service = _module("deeptutor.services.path_service")
    environment = json.dumps(dict(os.environ), sort_keys=True, ensure_ascii=True)
    fingerprint: dict[str, Any] = {
        "env": hashlib.sha256(environment.encode()).hexdigest(),
        "attrs": {},
        "singletons": {},
    }
    for module_name, attr in _ATTR_TARGETS:
        module = _optional_module(module_name)
        if module is not None and hasattr(module, attr):
            fingerprint["attrs"][f"{module_name}.{attr}"] = str(getattr(module, attr))
    for module_name, attr in _SINGLETON_TARGETS:
        module = _optional_module(module_name)
        if module is not None:
            with contextlib.suppress(AttributeError):
                fingerprint["singletons"][f"{module_name}.{attr}"] = _ref(
                    _resolve_dotted(module, attr)
                )
    fingerprint["singletons"]["PathService._instance"] = _ref(path_service.PathService._instance)
    fingerprint["dicts"] = {}
    for module_name, dotted, _deep in _DICT_TARGETS:
        module = _optional_module(module_name)
        if module is None:
            continue
        try:
            current = _resolve_dotted(module, dotted)
        except AttributeError:
            continue
        if isinstance(current, dict):
            fingerprint["dicts"][f"{module_name}.{dotted}"] = {
                (hashlib.sha256(str(key).encode()).hexdigest()
                 if dotted in {"_provider_pool", "_agentic_client_pool"} else str(key)): _ref(value)
                for key, value in sorted(current.items(), key=lambda kv: str(kv[0]))
            }
    fingerprint["funcs"] = {}
    for module_name, attr in _FUNC_TARGETS:
        module = _optional_module(module_name)
        if module is not None and hasattr(module, attr):
            fingerprint["funcs"][f"{module_name}.{attr}"] = _ref(getattr(module, attr))
    fingerprint["paths.ADMIN_WORKSPACE_ROOT"] = str(paths.ADMIN_WORKSPACE_ROOT)
    return fingerprint


# ---------------------------------------------------------------------------
# 重定向 / 恢复
# ---------------------------------------------------------------------------
def _install_lru_wrappers() -> None:
    """把 lru_cache 工厂换成全新 wrapper，避免污染原函数缓存。"""
    for module_name, attr in _FUNC_TARGETS:
        module = _optional_module(module_name)
        if module is None or not hasattr(module, attr):
            continue
        original = getattr(module, attr)
        inner = getattr(original, "__wrapped__", original)
        setattr(module, attr, functools.lru_cache(maxsize=128)(inner))


def _apply_redirect(
    admin_root: Path, home: Path, legacy_root: Path | None, *, set_env: bool = True
) -> None:
    paths = _module("deeptutor.multi_user.paths")
    if set_env:
        os.environ["DEEPTUTOR_HOME"] = str(home)
    paths.PROJECT_ROOT = home
    paths.ADMIN_WORKSPACE_ROOT = admin_root
    paths.USERS_ROOT = admin_root / "users"
    paths.SYSTEM_ROOT = admin_root / "system"
    paths.LEGACY_MULTI_USER_ROOT = (
        Path(legacy_root) if legacy_root is not None else Path("/nonexistent/p1-legacy-multi-user")
    )
    paths._legacy_migration_done = True
    paths._path_services.clear()

    for module_name in (
        "deeptutor.services.config",
        "deeptutor.services.config.loader",
        "deeptutor.services.config.launch_settings",
    ):
        module = _optional_module(module_name)
        if module is not None and hasattr(module, "PROJECT_ROOT"):
            module.PROJECT_ROOT = home

    defaults = _optional_module("deeptutor.config.defaults")
    if defaults is not None and hasattr(defaults, "_project_root"):
        defaults._project_root = home
        paths_config = defaults.DEFAULTS.setdefault("paths", {})
        paths_config["user_data_dir"] = str(admin_root / "user")
        paths_config["knowledge_bases_dir"] = str(admin_root / "knowledge_bases")
        paths_config["user_log_dir"] = str(admin_root / "user" / "logs")

    catalog = _optional_module("deeptutor.services.config.model_catalog")
    if catalog is not None and hasattr(catalog, "CATALOG_PATH"):
        catalog.CATALOG_PATH = admin_root / "user" / "settings" / "model_catalog.json"

    kb_config = _optional_module("deeptutor.services.config.knowledge_base_config")
    if kb_config is not None and hasattr(kb_config, "DEFAULT_CONFIG_PATH"):
        kb_config.DEFAULT_CONFIG_PATH = admin_root / "knowledge_bases" / "kb_config.json"

    _module("deeptutor.services.path_service").PathService._instance = None
    for module_name, attr in _SINGLETON_TARGETS:
        module = _optional_module(module_name)
        if module is not None:
            with contextlib.suppress(AttributeError):
                _resolve_dotted(module, attr)
                _set_dotted(module, attr, False if attr.endswith("_initialized") else None)
    for module_name, dotted, _deep in _DICT_TARGETS:
        if module_name == "deeptutor.config.defaults":
            continue
        module = _optional_module(module_name)
        if module is None:
            continue
        try:
            target = _resolve_dotted(module, dotted)
        except AttributeError:
            continue
        if isinstance(target, dict):
            target.clear()
    _install_lru_wrappers()


def redirect_runtime(
    tmp_path: Path,
    *,
    home_name: str = "deeptutor-home",
    legacy_root: Path | None = None,
) -> tuple[RuntimeSnapshot, Path]:
    """把运行数据根指向 ``tmp_path``，返回 (恢复令牌, admin root)。

    事务性：先 :func:`ensure_bootstrap_home`（配置 I/O 模块已在一个 tmp home 下导入），
    再快照，再逐项重定向；**任何一步失败都先回滚**再抛错。
    """
    ensure_bootstrap_home()
    snap = snapshot_runtime()
    try:
        home = Path(tmp_path) / home_name
        admin_root = home / "data"
        for path in (
            admin_root / "users",
            admin_root / "system",
            admin_root / "user" / "workspace" / "subjects",
            admin_root / "user" / "subjects",
            admin_root / "knowledge_bases",
            admin_root / "user" / "settings",
        ):
            path.mkdir(parents=True, exist_ok=True)
        _apply_redirect(admin_root, home, legacy_root)
    except BaseException:
        restore_runtime(snap)
        raise
    return snap, admin_root


@contextlib.contextmanager
def isolated_runtime(
    tmp_path: Path,
    *,
    guard_network: bool = True,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
    **kwargs: Any,
) -> Iterator[Path]:
    """重定向到 tmp 并在退出时无条件恢复；默认同时启用网络 guard。"""
    snap, admin_root = redirect_runtime(tmp_path, **kwargs)
    active_token = _ACTIVE_ROOT.set(admin_root)
    try:
        if guard_network:
            with block_external_network(
                allow_endpoints=allow_endpoints, allow_unix_paths=allow_unix_paths
            ):
                yield admin_root
        else:
            yield admin_root
    finally:
        try:
            restore_runtime(snap)
        finally:
            _ACTIVE_ROOT.reset(active_token)


# ---------------------------------------------------------------------------
# 临时科目 / 知识库
# ---------------------------------------------------------------------------
def learning_root(admin_root: Path) -> Path:
    return Path(admin_root).joinpath(*LEARNING_SUBPATH)


def outputs_root(admin_root: Path) -> Path:
    return Path(admin_root).joinpath(*OUTPUTS_SUBPATH)


def global_kb_root(admin_root: Path) -> Path:
    return Path(admin_root).joinpath(*GLOBAL_KB_SUBPATH)


@dataclass
class SubjectPaths:
    subject_id: str
    admin_root: Path
    root: Path
    outputs: Path
    marker: str

    @property
    def knowledge_bases(self) -> Path:
        return self.root / "knowledge_bases"

    @property
    def materials(self) -> Path:
        return self.root / "materials"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _register_subject(admin_root: Path, record: dict) -> None:
    index = learning_root(admin_root) / "index.json"
    records: list[dict] = []
    if index.is_file():
        loaded = json.loads(index.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            records = loaded
    records = [item for item in records if item.get("id") != record["id"]]
    records.append(record)
    _write_json(index, records)


def make_subject(
    admin_root: Path,
    subject_id: str,
    *,
    term: str = "2026春",
    marker: str | None = None,
    description: str = "",
) -> SubjectPaths:
    """建合法的临时科目；展示标签保留，实际 id 按生产 slug 规则生成。

    后续消费者使用返回值的 subject_id，不能把展示标签当作路径 id。
    非法记录反例应从这个合法基准单独修改目标字段。
    """
    from deeptutor.subjects.store import slugify

    name = subject_id.strip()
    if not name:
        raise IsolationError("subject fixture label must be nonempty")
    subject_id = slugify(name)
    admin_root = Path(admin_root)
    marker = marker or f"marker-{subject_id}"
    root = learning_root(admin_root) / subject_id
    outputs = outputs_root(admin_root) / subject_id
    for path in (root / "knowledge_bases", root / "materials" / "lecture", outputs):
        path.mkdir(parents=True, exist_ok=True)
    _write_json(root / "profile.json", {"subject_id": subject_id, "facts": [], "marker": marker})
    _write_json(root / "knowledge.json", [])
    _write_json(root / "wrong_book.json", [])
    _write_json(root / "exam_points.json", [])
    _write_json(root / "knowledge_points.json", [])
    (root / "materials" / "lecture" / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
    _register_subject(
        admin_root,
        {
            "id": subject_id,
            "name": name,
            "description": description,
            "term": term,
            "marker": marker,
            "created_at": 1791000000,
        },
    )
    return SubjectPaths(subject_id, admin_root, root, outputs, marker)


def make_kb(base: Path, kb_name: str, marker: str, *, documents: int = 1) -> Path:
    """在 ``base/<kb_name>`` 建一个带唯一标记的知识库目录。"""
    kb_dir = Path(base) / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for index in range(documents):
        (raw / f"{marker}-{index}.txt").write_text(f"{marker}\n", encoding="utf-8")
    _write_json(
        kb_dir / "kb_config.json",
        {"name": kb_name, "documents": documents, "marker": marker, "status": "ready"},
    )
    return kb_dir


def make_same_name_kbs(
    admin_root: Path,
    *,
    kb_name: str = "shared-kb",
    subject_ids: tuple[str, ...] = ("科目A", "科目B"),
    with_global: bool = True,
) -> dict[str, SubjectPaths | Path]:
    """在 A / B / global 三处建**同名**知识库，各自带互不相同的标记。"""
    admin_root = Path(admin_root)
    result: dict[str, SubjectPaths | Path] = {}
    for subject_id in subject_ids:
        subject = make_subject(admin_root, subject_id)
        make_kb(subject.knowledge_bases, kb_name, f"{subject_id}-only")
        result[subject_id] = subject
    if with_global:
        result["global"] = make_kb(global_kb_root(admin_root), kb_name, "global-only")
    return result


def kb_markers(kb_dir: Path) -> set[str]:
    """读回一个知识库 raw 目录里出现的标记（仅用于断言隔离）。"""
    raw = Path(kb_dir) / "raw"
    if not raw.is_dir():
        return set()
    return {entry.read_text(encoding="utf-8").strip() for entry in sorted(raw.glob("*.txt"))}


# ---------------------------------------------------------------------------
# 供应商替身（R4：协程形态与真实契约一致）
# ---------------------------------------------------------------------------
@dataclass
class StubCall:
    kind: str
    payload: dict[str, Any]


class RecordingStub:
    """记录调用并返回确定性响应的基类；不触网、不读密钥。"""

    kind = "stub"

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[StubCall] = []
        self._lock = threading.Lock()

    def _record(self, **payload: Any) -> None:
        with self._lock:
            self.calls.append(StubCall(self.kind, payload))

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _tutor_response(content: str, finish_reason: str | None, usage: dict[str, int] | None):
    """构造真实 ``TutorResponse``——``factory.complete_response`` 的实际返回类型。"""
    from deeptutor.services.llm.types import TutorResponse

    return TutorResponse(
        content=content,
        finish_reason=finish_reason,
        usage=usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )


class FakeLLMClient(RecordingStub):
    """``LLMClient`` / ``factory.complete_response`` 的异步替身。

    与生产一致：

    * ``await complete(prompt, ...) -> str``（``services/llm/client.py``）
    * ``await complete_response(...) -> TutorResponse``（``services/llm/factory.py``；
      消费者读 ``.content`` / ``.finish_reason`` / ``.usage``）
    """

    kind = "llm"

    def __init__(
        self,
        text: str = "stub-llm-response",
        finish_reason: str | None = "stop",
        *,
        binding: str = "stub-binding",
        model: str = "stub-model",
        supports_multimodal: bool = False,
        usage: dict[str, int] | None = None,
    ) -> None:
        super().__init__(text)
        self.finish_reason = finish_reason
        self.usage = usage
        self.config = type("StubLLMConfig", (), {"binding": binding, "model": model})()
        self._supports_multimodal = supports_multimodal

    def supports_multimodal_images(self) -> bool:
        return self._supports_multimodal

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> str:
        self._record(prompt=prompt, system_prompt=system_prompt, history=history, **kwargs)
        return str(self.response)

    async def complete_response(self, prompt: str = "", **kwargs: Any):
        self._record(prompt=prompt, **kwargs)
        return _tutor_response(str(self.response), self.finish_reason, self.usage)


class FakeEmbeddingClient(RecordingStub):
    """``EmbeddingClient.embed`` 的异步替身：同输入必得同向量，维度固定。"""

    kind = "embedding"

    def __init__(self, dimensions: int = 8, *, multimodal: bool = False) -> None:
        super().__init__(None)
        self.dimensions = dimensions
        self._multimodal = multimodal
        self.config = type(
            "StubEmbeddingConfig", (), {"binding": "stub-binding", "model": "stub-embedding"}
        )()

    def supports_multimodal_contents(self) -> bool:
        return self._multimodal

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i] / 255.0 for i in range(self.dimensions)]

    async def embed(
        self,
        texts: list[str],
        progress_callback: Any = None,
        *,
        input_type: str | None = None,
    ) -> list[list[float]]:
        batch = [texts] if isinstance(texts, str) else list(texts)
        self._record(texts=batch, input_type=input_type)
        return [self._vector(text) for text in batch]


class FakeSTT(RecordingStub):
    """``services/asr/transcribe.transcribe`` 的异步替身。"""

    kind = "stt"

    def __init__(
        self,
        text: str = "stub-transcript",
        model: str = "stub-stt",
        base_url: str = "https://stub.invalid/v1",
        *,
        error: str | None = None,
    ) -> None:
        super().__init__(text)
        self.model = model
        self.base_url = base_url
        self.error = error

    async def transcribe(self, audio_path: Path, *, language: str = "zh") -> dict[str, Any]:
        self._record(audio_path=str(audio_path), language=language)
        payload: dict[str, Any] = {
            "text": "" if self.error else str(self.response),
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def install_stub(monkeypatch, module_name: str, attribute: str, stub: Any) -> Any:
    """把一个替身装到实际被调用的模块属性上。

    替身 fixture 只**返回**可安装对象；安装必须显式完成，否则生产调用点仍会走真实
    provider。
    """
    module = _module(module_name)
    monkeypatch.setattr(module, attribute, stub)
    return stub


def install_provider_stubs(
    monkeypatch,
    *,
    llm: "FakeLLMClient | None" = None,
    embedding: "FakeEmbeddingClient | None" = None,
    stt: "FakeSTT | None" = None,
) -> dict[str, Any]:
    """把替身装到真实被调用的模块上；返回已安装的替身。"""
    ensure_bootstrap_home()
    installed: dict[str, Any] = {}

    def replace_callable(module_name: str, name: str, replacement: Any) -> None:
        original = getattr(_module(module_name), name)
        # Packages re-export these functions; loaded consumers may already have
        # imported the same function. Patch those identities as well.
        for loaded_name, module in tuple(sys.modules.items()):
            if (loaded_name.startswith("deeptutor.")
                    and getattr(module, "__dict__", {}).get(name) is original):
                monkeypatch.setattr(module, name, replacement)
    if llm is not None:
        replace_callable("deeptutor.services.llm.client", "get_llm_client", lambda *a, **k: llm)
        replace_callable("deeptutor.services.llm.factory", "complete_response", llm.complete_response)
        installed["llm"] = llm
    if embedding is not None:
        replace_callable("deeptutor.services.embedding.client", "get_embedding_client",
                         lambda *a, **k: embedding)
        installed["embedding"] = embedding
    if stt is not None:
        replace_callable("deeptutor.services.asr.transcribe", "transcribe", stt.transcribe)
        installed["stt"] = stt
    return installed


# ---------------------------------------------------------------------------
# 外网拦截（R5：默认组合进隔离；仅显式 (host, port) 放行）
# ---------------------------------------------------------------------------
def _normalize_host(host: Any) -> str | None:
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return None
    stripped = host.strip("[]")
    if stripped in ("", "0.0.0.0", "::"):
        return None
    return "localhost" if stripped in LOOPBACK_HOSTS else stripped


def _endpoint_allowed(address: Any, allowed: frozenset[tuple[str, int]]) -> bool:
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host = _normalize_host(address[0])
    if host is None:
        return False
    try:
        port = int(address[1])
    except (TypeError, ValueError):
        return False
    return (host, port) in allowed


@contextlib.contextmanager
def block_external_network(
    *,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
) -> Iterator[frozenset[tuple[str, int]]]:
    """拦截未声明的 TCP/UDP/DNS 出口。

    覆盖 ``connect`` / ``connect_ex`` / ``sendto`` / ``sendmsg`` /
    ``create_connection`` 与 DNS 解析。只有白名单里的 ``(host, port)`` 与显式
    ``allow_unix_paths`` 可用；``0.0.0.0``、空 host、任意回环端口默认拒绝。
    """
    endpoints = list(allow_endpoints)
    for host, port in endpoints:
        if host not in LOOPBACK_HOSTS or type(port) is not int or not 1 <= port <= 65535:
            raise IsolationError("only explicit localhost endpoints with valid ports are allowed")
    allowed = frozenset((_normalize_host(h), p) for h, p in endpoints)
    allowed_hosts = frozenset(host for host, _port in allowed)
    allowed_unix = frozenset(str(p) for p in allow_unix_paths)

    previous = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "sendto": socket.socket.sendto,
        "sendmsg": socket.socket.sendmsg,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
        "gethostbyname": socket.gethostbyname,
        "gethostbyname_ex": socket.gethostbyname_ex,
    }
    # Nested explicit localhost stubs must work under p1_runtime's default
    # guard. Delegate to the underlying transport, then restore the outer guard.
    real = {name: getattr(fn, "_p1_transport", fn) for name, fn in previous.items()}

    def _deny(what: str, address: Any) -> ExternalNetworkBlocked:
        return ExternalNetworkBlocked(
            f"external network blocked by phase-1 test isolation ({what}): {address!r}; "
            "declare it via allow_endpoints/allow_unix_paths"
        )

    def _unix_ok(address: Any) -> bool:
        return str(address) in allowed_unix

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        if self.family == socket.AF_UNIX:
            if _unix_ok(address):
                return real["connect"](self, address)
            raise _deny("AF_UNIX connect", address)
        if not _endpoint_allowed(address, allowed):
            raise _deny("connect", address)
        return real["connect"](self, address)

    def guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
        if self.family == socket.AF_UNIX:
            if _unix_ok(address):
                return real["connect_ex"](self, address)
            raise _deny("AF_UNIX connect_ex", address)
        if not _endpoint_allowed(address, allowed):
            raise _deny("connect_ex", address)
        return real["connect_ex"](self, address)

    def guarded_sendto(self, data, *args):  # type: ignore[no-untyped-def]
        address = args[-1] if args else None
        if getattr(self, "family", None) == socket.AF_UNIX:
            if _unix_ok(address):
                return real["sendto"](self, data, *args)
            raise _deny("AF_UNIX sendto", address)
        if not _endpoint_allowed(address, allowed):
            raise _deny("sendto", address)
        return real["sendto"](self, data, *args)

    def guarded_sendmsg(self, data, ancdata=(), flags=0, address=None):  # type: ignore[no-untyped-def]
        if address is None:
            address = self.getpeername()
        if getattr(self, "family", None) == socket.AF_UNIX:
            if _unix_ok(address):
                return real["sendmsg"](self, data, ancdata, flags, address)
            raise _deny("AF_UNIX sendmsg", address)
        if not _endpoint_allowed(address, allowed):
            raise _deny("sendmsg", address)
        return real["sendmsg"](self, data, ancdata, flags, address)

    def guarded_hostname(host, *, extended=False):
        if _normalize_host(host) not in allowed_hosts:
            raise _deny("DNS resolution", host)
        return real["gethostbyname_ex" if extended else "gethostbyname"](host)

    def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not _endpoint_allowed(address, allowed):
            raise _deny("create_connection", address)
        return real["create_connection"](address, *args, **kwargs)

    def guarded_getaddrinfo(host, port=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        normalized = _normalize_host(host)
        if normalized is None or normalized not in allowed_hosts:
            raise _deny("DNS resolution", (host, port))
        if port is not None:
            try:
                numeric = int(port)
            except (TypeError, ValueError):
                numeric = None
            if numeric is not None and (normalized, numeric) not in allowed:
                raise _deny("DNS resolution", (host, port))
        return real["getaddrinfo"](host, port, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[assignment]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[assignment]
    socket.socket.sendto = guarded_sendto  # type: ignore[assignment]
    socket.socket.sendmsg = guarded_sendmsg  # type: ignore[assignment]
    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.gethostbyname = guarded_hostname
    socket.gethostbyname_ex = lambda host: guarded_hostname(host, extended=True)
    for name in previous:
        target = socket.socket if name in {"connect", "connect_ex", "sendto", "sendmsg"} else socket
        getattr(target, name)._p1_transport = real[name]
    try:
        yield allowed
    finally:
        socket.socket.connect = previous["connect"]  # type: ignore[assignment]
        socket.socket.connect_ex = previous["connect_ex"]  # type: ignore[assignment]
        socket.socket.sendto = previous["sendto"]  # type: ignore[assignment]
        socket.socket.sendmsg = previous["sendmsg"]  # type: ignore[assignment]
        socket.create_connection = previous["create_connection"]  # type: ignore[assignment]
        socket.getaddrinfo = previous["getaddrinfo"]  # type: ignore[assignment]
        socket.gethostbyname = previous["gethostbyname"]
        socket.gethostbyname_ex = previous["gethostbyname_ex"]


# ---------------------------------------------------------------------------
# 字节快照与失败注入
# ---------------------------------------------------------------------------
def _raise_walk_error(error: OSError) -> None:
    raise error


def tree_digest(root: Path) -> dict[str, str]:
    """``{相对路径: 摘要}``；符号链接记为目标，不跟随。

    目录遍历错误 **fail closed**（``os.walk(onerror=...)``）：读不到的子树抛错，而不是被
    当成"没有变化"。它只用于测试期对比，不替代 P1-00 官方工具的模式/目录/完整保护清单。
    """
    root = Path(root)
    digest: dict[str, str] = {}
    if not root.exists():
        return digest
    for dirpath, dirnames, filenames in os.walk(
        root, followlinks=False, onerror=_raise_walk_error
    ):
        here = Path(dirpath)
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames) + sorted(d for d in dirnames if (here / d).is_symlink()):
            full = here / name
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                digest[rel] = "link:" + os.readlink(full)
            elif full.is_file():
                hasher = hashlib.sha256()
                with open(full, "rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        hasher.update(block)
                digest[rel] = hasher.hexdigest()
    return digest


class FailureInjector:
    """在第 ``at`` 次匹配调用时抛一次指定异常，用于故障注入。

    ``when="before"``（默认）在委托前失败；``when="after"`` 在副作用发生后才失败。
    """

    def __init__(
        self,
        exc_factory: Callable[[], BaseException] = lambda: RuntimeError("injected failure"),
        *,
        at: int = 1,
        when: str = "before",
    ) -> None:
        if when not in {"before", "after"}:
            raise ValueError("when must be 'before' or 'after'")
        self.exc_factory = exc_factory
        self.at = at
        self.when = when
        self.calls = 0

    def wrap(self, func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any):
            self.calls += 1
            if self.calls == self.at and self.when == "before":
                raise self.exc_factory()
            result = func(*args, **kwargs)
            if self.calls == self.at and self.when == "after":
                raise self.exc_factory()
            return result

        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        return wrapper

    @property
    def fired(self) -> bool:
        return self.calls >= self.at


# ---------------------------------------------------------------------------
# 冻结时钟
# ---------------------------------------------------------------------------
class FrozenClock:
    """可替代模块级 ``time`` 的冻结时钟；只实现被调用的 ``time()``。"""

    def __init__(self, now: float) -> None:
        self._now = float(now)

    def time(self) -> float:
        return self._now

    def set(self, now: float) -> None:
        self._now = float(now)

    def advance(self, seconds: float) -> None:
        self._now += float(seconds)


@contextlib.contextmanager
def frozen_time(module_name: str, now: float) -> Iterator[FrozenClock]:
    """把 ``module_name`` 模块内的 ``time`` 换成 :class:`FrozenClock`，退出写回。"""
    module = _module(module_name)
    if not hasattr(module, "time"):
        raise IsolationError(f"{module_name} has no module-level 'time' to freeze")
    saved = module.time
    clock = FrozenClock(now)
    module.time = clock
    try:
        yield clock
    finally:
        module.time = saved


# ---------------------------------------------------------------------------
# HTTP（R3：客户端与其数据根绑定在同一个隔离作用域内）
# ---------------------------------------------------------------------------
ROUTE_PREFIX = "/api/v1/subjects"


def build_route_app():
    """构造只含真实科目路由的轻量 app，**不挂**后台 lifespan。

    用带完整 lifespan 的 ``deeptutor.api.main.app`` 做普通路由测试，会把 EventBus/cron/
    LLM 锚定在启动时的根上并跨隔离作用域存活。完整 lifespan 的验收放在独立子进程里
    （:func:`full_lifespan_probe`）。
    """
    from fastapi import FastAPI

    from deeptutor.api.routers import subjects

    app = FastAPI()
    app.include_router(subjects.router, prefix=ROUTE_PREFIX)
    return app


@contextlib.contextmanager
def route_client() -> Iterator[Any]:
    """在当前隔离作用域内创建并**关闭**一个真实路由客户端。"""
    if _ACTIVE_ROOT.get() is None:
        raise IsolationError("route_client requires an active isolated_runtime scope")
    from fastapi.testclient import TestClient

    with TestClient(build_route_app()) as client:
        yield client


def shared_http_client() -> Any:
    """已移除：进程级共享客户端会把 lifespan 状态锚定到启动根。"""
    raise IsolationError(
        "shared_http_client() was removed in S01 rework01: a process-wide TestClient keeps "
        "lifespan state (cron/EventBus/LLM) anchored to the root it started in. "
        "Use route_client() inside an isolated_runtime scope."
    )


def _close_shared_client() -> None:
    """兼容历史调用点（含旧回归启动器）：现在没有常驻客户端需要关闭。"""


FULL_LIFESPAN_PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
os.chdir(repo)

owner = tempfile.TemporaryDirectory(prefix="p1-full-lifespan-")
home = owner.name
for name in tuple(os.environ):
    if "API_KEY" in name or name.startswith(("OPENAI_", "ANTHROPIC_", "CODEBUDDY_", "DEEPTUTOR_CODEBUDDY_")):
        os.environ.pop(name, None)
os.environ["DEEPTUTOR_HOME"] = home
os.environ["DEEPTUTOR_CODEBUDDY_AUTH_FILE"] = str(Path(home) / "missing-auth.json")

result = {"home": home}
try:
    from tests.phase1.helpers import block_external_network
    with block_external_network():
        from deeptutor.services.setup.init import init_user_directories
        from deeptutor.services.config import ensure_runtime_settings_files
        init_user_directories()
        ensure_runtime_settings_files()
        from fastapi.testclient import TestClient
        from deeptutor.api.main import app
        with TestClient(app) as client:
            from deeptutor.services.cron.service import get_cron_service
            from deeptutor.events.event_bus import get_event_bus
            cron, bus = get_cron_service(), get_event_bus()
            result["cron_store"] = str(cron.store_path)
            result["cron_under_tmp"] = cron.store_path.is_relative_to(Path(home))
            response = client.get("/api/v1/subjects")
            result["subjects_status"] = response.status_code
            result["subjects_body"] = response.text[:4000]
        result["shutdown_ok"] = (
            not cron._running and cron._timer_task is None
            and not bus._running and bus._processor_task.done()
        )
    result["ok"] = True
except Exception as exc:
    result["ok"] = False
    result["error"] = f"{type(exc).__name__}: {exc}"
finally:
    owner.cleanup()
result["home_removed"] = not Path(home).exists()
print(json.dumps(result, ensure_ascii=False))
'''


def full_lifespan_probe(timeout: float = 60.0) -> dict[str, Any]:
    """在独立子进程中用 tmp home 启停真实 lifespan，返回诊断字典。

    子进程在 import/startup **之前**就设定 ``DEEPTUTOR_HOME`` 与假配置；不写
    ``HOME``/``CODEX_HOME``，不读取真实凭证。
    """
    proc = subprocess.run(
        [sys.executable, "-c", FULL_LIFESPAN_PROBE, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    payload: dict[str, Any] = {}
    if lines:
        with contextlib.suppress(json.JSONDecodeError):
            payload = json.loads(lines[-1])
    payload["exit_code"] = proc.returncode
    payload["stderr_tail"] = proc.stderr[-2000:]
    return payload


def assert_within(child: Path, parent: Path) -> None:
    """``child`` 必须位于 ``parent`` 之内（解析后比较）。"""
    child_resolved = Path(child).resolve()
    parent_resolved = Path(parent).resolve()
    if child_resolved != parent_resolved and parent_resolved not in child_resolved.parents:
        raise AssertionError(f"{child_resolved} is not inside {parent_resolved}")
