"""报告专用**受限执行器**（P1-33）。

这是报告流水线唯一的执行边界：模型图表代码与 ODE 数值检查都只能经过这里，绝不
退回宿主 ``subprocess``，也不使用普通 sandbox service/settings 的宽松策略。

职责划分（谁证明什么）：

* **本模块**：策略数值（墙钟/CPU/内存/输出/产物上限）、挂载与环境白名单的组装、
  不变量断言（只有一个可写挂载、只读挂载不得包含仓库/home/数据根/其他 run）、
  worker argv、有界输出读取、超时/取消时的**整组**终止与 reap、失败到 C02 的映射。
* **backend**：把 :class:`ChartSandboxRequest` 变成一个真实进程。报告路径默认只
  接受 :class:`BwrapReportBackend`（``--unshare-all`` 逐任务 namespace + 显式
  mounts + ``--clearenv``）；它必须返回 :class:`ReportIsolationProof` 全真的证明
  并通过**看真实退出码/超时**的健康探测，否则固定 503，不做任何宿主回退。
* **trusted worker**（``chart_worker.py``）：先 ``setrlimit`` 再运行模型脚本，并把
  结果作为 stdout 上**唯一**的 JSON 对象回传。

进程内/文件边界如实记录：活跃 run 只看本进程登记表；执行期只信任本进程写下的
attempt 记录（它在 staging 里，不在模型可写挂载内）。真实 OS 隔离验收属于 S15/P50，
本阶段只用真实 bwrap 与受控进程边界证明策略、限额与失败路径，不宣称已通过 OS 门。
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import threading
import time
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
import uuid

from deeptutor.services.pdf import report_inputs, report_store
from deeptutor.services.pdf.report_inputs import validate_ode_expression
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    SubjectStorageError,
    subject_error,
)

#: 可信 worker 的文件名（与本模块同目录，单独只读挂载）。
WORKER_FILENAME = "chart_worker.py"

#: 模型脚本文件名由服务端固定，模型不能指定。
CHART_SCRIPT_NAME = "_chart.py"

#: 服务端预分配的期望产物名。
CHART_NAME_RE = re.compile(r"^chart_([1-9])\.png$")

#: ODE 检查点数量的硬边界（服务端固定用 5 个点，见 P34）。
MAX_ODE_POINTS = 32

#: attempt 记录 schema 版本，以及绑定产物时允许读取的最大字节数。
CHART_ATTEMPT_SCHEMA = 1
MAX_ATTEMPT_ARTIFACT_BYTES = 16 * 1024 * 1024

#: 沙箱内环境变量白名单：只允许这些键，且绝不含凭据/代理。
ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "PYTHONHASHSEED",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONNOUSERSITE",
    "PYTHONSAFEPATH",
    "MPLBACKEND",
    "MPLCONFIGDIR",
    "XDG_CACHE_HOME",
)

#: 任何命中这些片段的 env 键都不许进入沙箱（即使是白名单键名）。
_SECRET_KEY_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|PROXY|COOKIE|SESSION|SIGNATURE)",
    re.IGNORECASE,
)

#: ``/etc`` 只允许这些**具体**项，绝不整目录挂载。
NARROW_ETC_ENTRIES = ("/etc/ld.so.cache", "/etc/fonts", "/etc/localtime")

#: 常规只读系统目录（存在才挂）。
SYSTEM_READ_ONLY_DIRS = ("/usr", "/usr/local", "/bin", "/lib", "/lib64", "/sbin")

_OUTPUT_READ_CHUNK = 4096
_REAP_GRACE_S = 5.0
#: 等待"进程组变空"的轮询间隔（leader 退出后仍可能有后代）。
_GROUP_POLL_S = 0.05
#: 控制协议的最小读取预算：唯一 JSON envelope 不能被诊断预算截成半对象。
CONTROL_PROTOCOL_FLOOR_BYTES = 8192


# ---------------------------------------------------------------------------
# 策略与请求
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReportResourceLimits:
    """一次执行的实际限额（由服务端策略推出，模型无法提供）。"""

    wall_clock_s: int
    cpu_seconds: int
    memory_mb: int
    max_output_chars: int
    max_artifact_bytes: int


@dataclass(frozen=True)
class ReportMount:
    host_path: str
    sandbox_path: str
    read_only: bool = True


@dataclass(frozen=True)
class ChartSandboxRequest:
    """沙箱请求：argv/挂载/环境/限额全部由本模块算出。"""

    argv: tuple[str, ...]
    workdir: Path
    mounts: tuple[ReportMount, ...]
    env: Mapping[str, str]
    limits: ReportResourceLimits

    @property
    def writable_mounts(self) -> tuple[ReportMount, ...]:
        return tuple(mount for mount in self.mounts if not mount.read_only)

    def describe(self) -> dict[str, Any]:
        """服务端诊断用的向量描述（env 只列键名，不回显取值）。"""
        return {
            "argv": list(self.argv),
            "workdir": str(self.workdir),
            "mounts": [
                {"host": m.host_path, "sandbox": m.sandbox_path, "read_only": m.read_only}
                for m in self.mounts
            ],
            "env_keys": sorted(self.env),
            "limits": {
                "wall_clock_s": self.limits.wall_clock_s,
                "cpu_seconds": self.limits.cpu_seconds,
                "memory_mb": self.limits.memory_mb,
                "max_output_chars": self.limits.max_output_chars,
                "max_artifact_bytes": self.limits.max_artifact_bytes,
            },
        }


@dataclass(frozen=True)
class SpawnCommand:
    """backend 交给执行器的真实进程向量（argv + cwd + env）。"""

    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]


@dataclass(frozen=True)
class ReportIsolationProof:
    """backend 自证能力；**每一项都必须为真**才可能被报告路径接受。"""

    per_task_namespaces: bool = False
    per_task_mounts: bool = False
    network_disabled: bool = False
    env_cleared: bool = False
    process_group_cleanup: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "per_task_namespaces": self.per_task_namespaces,
            "per_task_mounts": self.per_task_mounts,
            "network_disabled": self.network_disabled,
            "env_cleared": self.env_cleared,
            "process_group_cleanup": self.process_group_cleanup,
        }

    def is_qualified(self) -> bool:
        return all(self.as_dict().values())


@dataclass(frozen=True)
class ChartExecutionResult:
    """一次图表/ODE 执行的结果（字段与 DATA_CONTRACTS 附录 A 一致并扩展）。

    :attr:`error` 是**固定的机器标记**（``""`` 表示没有基础设施错误），绝不回显
    脚本内容/表达式/路径/环境；``stdout``/``stderr`` 是服务端诊断用的有界尾巴，
    调用方不得把它们投影给客户端。
    """

    exit_code: int
    timed_out: bool
    error: str
    stdout: str = ""
    stderr: str = ""
    artifact: Mapping[str, Any] | None = None
    checks: Mapping[str, Any] | None = None
    output_truncated: bool = False
    backend: str = ""
    elapsed_s: float = 0.0
    worker_payload: Mapping[str, Any] | None = None
    #: ``"chart"`` / ``"ode"``，以及 worker 报告的固定状态标记（``ok``/``no_artifact``/…）。
    mode: str = "chart"
    status: str = ""

    @property
    def ok(self) -> bool:
        """成功 = 没有基础设施错误 + 没超时 + 退出码为 0。

        刻意不复用 ``ExecResult.ok``：那个属性不看 ``exit_code``，用它判断成功会把
        "脚本以非 0 退出" 当成成功。
        """
        return self.error == "" and not self.timed_out and self.exit_code == 0


@dataclass(frozen=True)
class ReportExecutionPolicy:
    """报告执行的固定策略（服务端构造；模型/工具参数都进不来）。"""

    wall_clock_s: int = 60
    ode_wall_clock_s: int = 30
    cpu_seconds: int = 30
    memory_mb: int = 1536
    max_output_chars: int = 10_000
    max_artifact_bytes: int = 10 * 1024 * 1024
    max_pixels: int = 20_000_000
    max_charts: int = 8
    #: 服务端 DI/测试接缝：显式注入的 backend 仍须通过证明 + 健康检查。
    #: 这是 Python 对象，不是可序列化参数，任何模型输入都到不了这里。
    backend: "ReportSandboxBackend | None" = None

    def __post_init__(self) -> None:
        for name in ("wall_clock_s", "ode_wall_clock_s", "cpu_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 600:
                raise ValueError(f"{name} 必须是 1..600 的整数秒")
        for name in ("memory_mb", "max_output_chars", "max_artifact_bytes", "max_pixels"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} 必须是正整数")
        if not 1 <= self.max_charts <= 8:
            raise ValueError("max_charts 必须在 1..8")

    def limits(self, *, ode: bool = False) -> ReportResourceLimits:
        return ReportResourceLimits(
            wall_clock_s=self.ode_wall_clock_s if ode else self.wall_clock_s,
            cpu_seconds=self.cpu_seconds,
            memory_mb=self.memory_mb,
            max_output_chars=self.max_output_chars,
            max_artifact_bytes=self.max_artifact_bytes,
        )

    def for_ode(self) -> "ReportExecutionPolicy":
        return replace(self, wall_clock_s=self.ode_wall_clock_s)


DEFAULT_POLICY = ReportExecutionPolicy()

# One run shares _chart.py. Refuse overlapping execution before writing it;
# independent runs keep running concurrently, including across event loops.
_EXECUTING_RUNS: set[str] = set()
_EXECUTING_RUNS_LOCK = threading.Lock()


@contextlib.contextmanager
def _exclusive_run_execution(run: report_store.ReportRun):
    key = str(run.staging_dir)
    with _EXECUTING_RUNS_LOCK:
        if key in _EXECUTING_RUNS:
            raise subject_error(ErrorCode.CHART_FAILED)
        _EXECUTING_RUNS.add(key)
    try:
        yield
    finally:
        with _EXECUTING_RUNS_LOCK:
            _EXECUTING_RUNS.discard(key)


# ---------------------------------------------------------------------------
# backend 契约
# ---------------------------------------------------------------------------
@runtime_checkable
class ReportSandboxBackend(Protocol):
    """报告沙箱后端：只负责证明能力、健康探测与给出进程向量。"""

    name: str

    def isolation_proof(self) -> ReportIsolationProof: ...

    async def health(self) -> tuple[bool, str]: ...

    def build_spawn(self, request: ChartSandboxRequest) -> SpawnCommand: ...


class BwrapReportBackend:
    """报告专用 bubblewrap 后端（窄派生，不修改共享 ``BwrapBackend``）。"""

    name = "bwrap-report"

    def __init__(self, bwrap_path: str | Path | None = None) -> None:
        self._bwrap = str(bwrap_path or shutil.which("bwrap") or "bwrap")

    # -- 证明 ---------------------------------------------------------------
    def isolation_proof(self) -> ReportIsolationProof:
        return ReportIsolationProof(
            per_task_namespaces=True,  # --unshare-all（含 pid/net/user/...）
            per_task_mounts=True,  # 只挂本模块算出的 mounts
            network_disabled=True,  # --unshare-all 含 --unshare-net
            env_cleared=True,  # --clearenv + 白名单 --setenv
            process_group_cleanup=True,  # killpg + --die-with-parent + pid namespace
        )

    # -- 进程向量 -----------------------------------------------------------
    def build_spawn(self, request: ChartSandboxRequest) -> SpawnCommand:
        argv = [
            self._bwrap,
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",  # nosec B108 - 沙箱内私有 tmpfs，不是宿主 /tmp
        ]
        for mount in request.mounts:
            flag = "--ro-bind" if mount.read_only else "--bind"
            argv += [flag, mount.host_path, mount.sandbox_path]
        # 环境：先清空，再逐项设置白名单键；宿主 env 一个字节都不继承。
        argv += ["--clearenv"]
        for key, value in request.env.items():
            argv += ["--setenv", key, value]
        argv += ["--chdir", str(request.workdir)]
        argv += ["--", *request.argv]
        # bwrap 自身只需要能找到自己的绝对路径；它的宿主 env 与沙箱内 env 无关。
        return SpawnCommand(argv=tuple(argv), cwd=request.workdir, env={"PATH": "/usr/bin:/bin"})

    # -- 健康 ---------------------------------------------------------------
    async def health(self) -> tuple[bool, str]:
        """真实探测：bwrap 能起、退出码为 0，且沙箱内**没有外网路由**。

        只看 ``error`` 不看退出码的历史做法被明确替换：这里的每个判断都读真实
        ``exit_code``/``timed_out``/stdout。网络判定用 UDP ``connect``：它只做路由
        查找、不发包；在 ``--unshare-net`` 里必然失败（fail-closed：一旦连得上就
        判为不合格）。
        """
        resolved = shutil.which(self._bwrap) or (
            self._bwrap if Path(self._bwrap).exists() else None
        )
        if resolved is None:
            return False, "bwrap not installed"
        limits = ReportResourceLimits(
            wall_clock_s=15,
            cpu_seconds=10,
            memory_mb=512,
            max_output_chars=2000,
            max_artifact_bytes=1 << 20,
        )
        probe = (
            "import socket\n"
            "s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
            "s.settimeout(2)\n"
            "try:\n"
            "    s.connect(('1.1.1.1', 53))\n"
            "except OSError:\n"
            "    print('NOROUTE')\n"
            "else:\n"
            "    print('ROUTE')\n"
        )
        request = ChartSandboxRequest(
            argv=(str(sys.executable), "-I", "-c", probe),
            workdir=Path("/"),
            mounts=_runtime_read_only_mounts(),
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            limits=limits,
        )
        result = await run_bounded_spawn(self.build_spawn(request), limits, backend_name=self.name)
        if result.error or result.timed_out:
            return False, f"probe failed: {result.error or 'timeout'}"
        if result.exit_code != 0:
            return False, f"probe exit {result.exit_code}"
        if result.stdout.strip() != "NOROUTE":
            return False, "sandbox network is reachable"
        return True, "bwrap functional, network namespace isolated"


def bind_proof(proof: ReportIsolationProof | None) -> ReportIsolationProof | None:
    """接受 :class:`ReportIsolationProof` 实例，其它一律当作"没有证明"。"""
    return proof if isinstance(proof, ReportIsolationProof) else None


def _backend_proof(backend: object) -> ReportIsolationProof | None:
    """只接受**本模块的证明类型**；同名类、``level`` 字段或裸 ``True`` 都不算。"""
    getter = getattr(backend, "isolation_proof", None)
    if not callable(getter):
        return None
    try:
        return bind_proof(getter())
    except Exception:  # noqa: BLE001 - 证明拿不到就等于没有证明
        return None


def select_report_backend(policy: ReportExecutionPolicy = DEFAULT_POLICY) -> ReportSandboxBackend:
    """报告路径的 backend 选择：显式注入优先，否则只接受真实 bwrap 后端。

    这里**不看**共享 sandbox settings：``RunnerSidecarBackend``/``APPLICATION``/
    ``OFF`` 都不满足逐任务隔离要求，绝不能因为"配置里有别的 backend"就降级执行。
    """
    if policy.backend is not None:
        return policy.backend
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise subject_error(ErrorCode.SANDBOX_UNAVAILABLE)
    return BwrapReportBackend(bwrap)


# ---------------------------------------------------------------------------
# 挂载与环境
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _add_unique(paths: list[Path], candidate: Path) -> None:
    """加入 *candidate*，且跳过已经被更上层目录覆盖的路径（更少挂载面）。"""
    try:
        resolved = candidate if candidate.exists() else None
    except OSError:  # pragma: no cover - 极端权限
        resolved = None
    if resolved is None:
        return
    for existing in paths:
        with contextlib.suppress(ValueError):
            resolved.relative_to(existing)
            return
    paths.append(resolved)


def _python_runtime_mount_pairs() -> tuple[tuple[Path, Path], ...]:
    """解释器运行时需要的 ``(宿主源, 沙箱目标)`` 对。

    uv/pyenv 管理的 venv 会把 ``bin/python`` 链到**别名**运行时目录
    （``cpython-3.12-…`` → ``cpython-3.12.14-…``）。只挂解析后的真实目录，沙箱里
    execvp 别名路径会 ``ENOENT``，所以别名与真实路径都要挂。这与既有
    ``BwrapBackend._detect_python_runtime_mounts`` 同思路：只挂具体运行时根，
    从不挂它们的共享 manager/home 父目录。
    """
    pairs: list[tuple[Path, Path]] = []

    def add(source: Path, destination: Path) -> None:
        if not source.is_dir() or source == Path("/"):
            return
        if source == Path.home().resolve():
            return
        if len(source.parts) < 3:  # pragma: no cover - 防御：不挂 /usr 这类过短根
            return
        binding = (source, destination)
        if binding not in pairs:
            pairs.append(binding)

    for prefix in (sys.base_prefix, sys.base_exec_prefix, sys.prefix, sys.exec_prefix):
        path = Path(prefix)
        add(path.resolve(), path.absolute())
    base_executable = Path(getattr(sys, "_base_executable", sys.executable))
    runtime_root = base_executable.parent.parent
    add(runtime_root.resolve(), runtime_root.absolute())
    executable = Path(sys.executable)
    add(executable.resolve(), executable.resolve())
    return tuple(pairs)


def _runtime_read_only_mounts() -> tuple[ReportMount, ...]:
    """解释器/运行库/字体/trusted worker 的只读挂载（最小集合）。

    ``/etc`` 只取 :data:`NARROW_ETC_ENTRIES` 里的具体项；仓库源码目录、home 根、
    用户数据根、settings 与科目数据都不在列表里。
    """
    paths: list[Path] = []
    worker = Path(__file__).resolve().with_name(WORKER_FILENAME)
    fonts = _repo_root() / "tools" / "fonts"
    _add_unique(paths, worker)
    _add_unique(paths, fonts)
    for entry in NARROW_ETC_ENTRIES:
        _add_unique(paths, Path(entry))
    for system_dir in SYSTEM_READ_ONLY_DIRS:
        _add_unique(paths, Path(system_dir))
    mounts = [ReportMount(str(path), str(path), True) for path in paths]
    destinations = {mount.sandbox_path for mount in mounts}
    for source, destination in _python_runtime_mount_pairs():
        if str(destination) in destinations:
            continue
        destinations.add(str(destination))
        mounts.append(ReportMount(str(source), str(destination), True))
    return tuple(mounts)


def report_read_only_mounts() -> tuple[ReportMount, ...]:
    """诊断用投影：本模块实际会挂的只读集合。"""
    return _runtime_read_only_mounts()


def _report_mounts(run: report_store.ReportRun) -> tuple[ReportMount, ...]:
    """唯一可写挂载 = 本次 run 的 workdir；其余全部只读。"""
    workdir = run.workdir
    mounts = [ReportMount(str(workdir), str(workdir), False)]
    mounts.extend(_runtime_read_only_mounts())
    return tuple(mounts)


def _prepare_runtime_dirs(run: report_store.ReportRun) -> None:
    """真正执行前的准备：本 run 内的 HOME/字体缓存目录（**只在执行路径**调用）。

    计划（``plan_chart_request``）必须是纯计算：它只算出 env 取值，不创建任何目录。
    """
    workdir = run.workdir
    for name in ("home", "mplconfig", "cache"):
        json_store.make_directory(workdir / name)


def _report_env(run: report_store.ReportRun) -> dict[str, str]:
    """固定白名单 env；缓存/配置目录全部限在本 run 内（纯计算，不建目录）。"""
    workdir = run.workdir
    venv_bin = str(Path(sys.executable).parent)
    env = {
        "PATH": os.pathsep.join([venv_bin, "/usr/local/bin", "/usr/bin", "/bin"]),
        "HOME": str(workdir / "home"),
        "TMPDIR": "/tmp",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(workdir / "mplconfig"),
        "XDG_CACHE_HOME": str(workdir / "cache"),
    }
    return env


def _assert_env_is_safe(env: Mapping[str, str]) -> None:
    unknown = sorted(set(env) - set(ENV_ALLOWLIST))
    if unknown:
        raise subject_error(ErrorCode.INTERNAL_ERROR)  # 服务端 bug：白名单外键
    for key, value in env.items():
        if _SECRET_KEY_RE.search(key):
            raise subject_error(ErrorCode.INTERNAL_ERROR)
        if not isinstance(value, str) or "\0" in value:
            raise subject_error(ErrorCode.INTERNAL_ERROR)


def _assert_mounts_are_narrow(run: report_store.ReportRun, mounts: Sequence[ReportMount]) -> None:
    """不变量：只有一个可写挂载，且只读挂载不覆盖敏感根。"""
    writable = [mount for mount in mounts if not mount.read_only]
    expected = str(run.workdir)
    if len(writable) != 1 or writable[0].host_path != expected:
        raise subject_error(ErrorCode.INTERNAL_ERROR)

    forbidden: list[Path] = []
    for candidate in (
        Path("/"),
        Path.home(),
        _repo_root(),
        _repo_root() / "data",
        run.staging_dir,
        run.staging_dir.parent,
        run.public_dir,
    ):
        with contextlib.suppress(OSError):
            forbidden.append(candidate.resolve())
    for mount in mounts:
        if mount.read_only is False:
            continue
        host = Path(mount.host_path)
        if host.as_posix().rstrip("/") == "/etc":
            raise subject_error(ErrorCode.INTERNAL_ERROR)  # 不允许整目录 /etc
        try:
            resolved = host.resolve()
        except OSError:  # pragma: no cover - 极端权限
            continue
        for blocked in forbidden:
            if resolved == blocked or resolved in blocked.parents:
                # 只读挂载不得**包含**敏感根（可以是被需要的具体运行库子目录）。
                raise subject_error(ErrorCode.INTERNAL_ERROR)


def _build_request(
    run: report_store.ReportRun, policy: ReportExecutionPolicy, argv: Sequence[str], *, ode: bool
) -> ChartSandboxRequest:
    # 身份先验证：任何伪造 staging/workdir 的 run 在这里被拒，且不落任何文件。
    report_store.require_report_run(run)
    mounts = _report_mounts(run)
    env = _report_env(run)
    _assert_env_is_safe(env)
    _assert_mounts_are_narrow(run, mounts)
    return ChartSandboxRequest(
        argv=tuple(argv),
        workdir=run.workdir,
        mounts=mounts,
        env=env,
        limits=policy.limits(ode=ode),
    )


# ---------------------------------------------------------------------------
# 有界进程运行器（唯一真正启动进程的地方）
# ---------------------------------------------------------------------------
class _OutputBudget:
    """stdout/stderr **合计**有界；读取期间就丢弃超额字节，不会先全部读进内存。"""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.truncated = False
        self._parts: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
        self._lock = asyncio.Lock()

    async def take(self, name: str, chunk: bytes) -> None:
        async with self._lock:
            if self.used >= self.limit:
                self.truncated = True
                return
            room = self.limit - self.used
            if len(chunk) > room:
                chunk = chunk[:room]
                self.truncated = True
            self.used += len(chunk)
            self._parts[name].append(chunk)

    def text(self, name: str) -> str:
        return b"".join(self._parts[name]).decode("utf-8", errors="replace")


async def _pump(stream: asyncio.StreamReader | None, budget: _OutputBudget, name: str) -> None:
    if stream is None:  # pragma: no cover - 防御
        return
    while True:
        chunk = await stream.read(_OUTPUT_READ_CHUNK)
        if not chunk:
            return
        await budget.take(name, chunk)


def _kill_group(pgid: int, process: asyncio.subprocess.Process | None = None) -> None:
    """按**创建时保存的 PGID**终止整个执行进程组。

    组长可能已经退出：``os.getpgid(已退出 pid)`` 会失败，因此绝不在 kill 的时候再
    去查 PGID；``start_new_session=True`` 让子进程成为组长，``PGID == pid`` 在创建
    瞬间就已固定。
    """
    killed = False
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, signal.SIGKILL)
        killed = True
    if not killed and process is not None:
        with contextlib.suppress(ProcessLookupError, OSError):
            process.kill()


def _group_is_alive(pgid: int) -> bool:
    """进程组里是否还有成员（leader 退出后仍可能有后代）。"""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - 组还在但无权限
        return True
    except OSError:  # pragma: no cover - 保守：当作还在
        return True
    return True


async def _reap(process: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=_REAP_GRACE_S)
    if process.returncode is None:  # pragma: no cover - 需要内核级异常
        with contextlib.suppress(ProcessLookupError, OSError):
            process.kill()
        with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError, OSError):
            await asyncio.wait_for(process.wait(), timeout=_REAP_GRACE_S)


async def _stop_spawn(
    process: asyncio.subprocess.Process,
    pgid: int,
    waiter: asyncio.Future[Any],
    pumps: Sequence[asyncio.Task[None]],
) -> None:
    """Abort readers, reap the group, and finish pipe ownership before returning.

    Process.wait() can return as soon as the leader has exited, while a descendant
    still owns stdout/stderr. Drain those pipes in bounded chunks after killpg;
    never materialize their remaining contents with communicate().
    """
    _kill_group(pgid, process)
    waiter.cancel()
    for pump in pumps:
        pump.cancel()
    await asyncio.gather(waiter, *pumps, return_exceptions=True)

    async def drain(stream: asyncio.StreamReader | None) -> None:
        if stream is not None:
            while await stream.read(_OUTPUT_READ_CHUNK):
                pass

    finished = False
    try:
        await asyncio.wait_for(
            asyncio.gather(_reap(process), drain(process.stdout), drain(process.stderr)),
            timeout=_REAP_GRACE_S,
        )
        finished = True
    except (OSError, RuntimeError, asyncio.TimeoutError):
        # Preserve the original execution failure even if an escaped descendant
        # retains a pipe or the stream itself failed.
        pass
    finally:
        if not finished:
            # asyncio.Process has no public close/wait_closed API. This fallback
            # only closes our transport; it never signals an unrelated process.
            transport = getattr(process, "_transport", None)
            if transport is not None:
                transport.close()


def _read_budget(limits: ReportResourceLimits) -> int:
    """读取期间允许保留的字节数：控制协议有下限，诊断内容另有更小的暴露上限。"""
    return max(CONTROL_PROTOCOL_FLOOR_BYTES, int(limits.max_output_chars))


def _trim_outputs(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool]:
    """把两个流压到**合计**不超过 *limit* 个字符。"""
    if len(stdout) + len(stderr) <= limit:
        return stdout, stderr, False
    room = max(0, limit - len(stderr))
    if len(stdout) > room:
        stdout = stdout[:room]
    remaining = max(0, limit - len(stdout))
    if len(stderr) > remaining:
        stderr = stderr[:remaining]
    return stdout, stderr, True


async def run_bounded_spawn(
    spawn: SpawnCommand,
    limits: ReportResourceLimits,
    *,
    backend_name: str = "",
    env: Mapping[str, str] | None = None,
    protocol_stdout_bytes: int | None = None,
) -> ChartExecutionResult:
    """启动 *spawn* 并在有界内存内读取输出；超时/取消/读取异常终止整组。

    这是本模块唯一的进程启动点：``start_new_session=True`` 让子进程成为新进程组
    组长（PGID 在创建时固定），deadline 覆盖"读 stdout/stderr + wait + 组内后代"，
    超时/取消/读取异常都会 ``killpg`` 整组终止并 reap。

    ``protocol_stdout_bytes``：当 stdout 承载**控制协议**（唯一 JSON envelope）时，
    它的暴露上限用这个下限而不是诊断预算；诊断内容（stderr 与最终投影的尾巴）仍按
    ``limits.max_output_chars`` 压。这样小诊断预算不会把 envelope 截成半对象。
    """
    started = time.monotonic()
    argv = tuple(spawn.argv)
    if not argv:
        raise subject_error(ErrorCode.INTERNAL_ERROR)
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(spawn.cwd),
            env=dict(spawn.env if env is None else env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return ChartExecutionResult(
            exit_code=127,
            timed_out=False,
            error="sandbox_spawn_failed",
            backend=backend_name,
            elapsed_s=round(time.monotonic() - started, 3),
        )

    budget = _OutputBudget(_read_budget(limits))
    pumps = [
        asyncio.create_task(_pump(process.stdout, budget, "stdout")),
        asyncio.create_task(_pump(process.stderr, budget, "stderr")),
    ]
    readers = asyncio.gather(*pumps)
    waiter = asyncio.gather(readers, process.wait())
    # PGID 在创建时固定：leader 先退出也不会让清理失效。
    pgid = process.pid
    timed_out = False
    deadline = started + limits.wall_clock_s
    try:
        await asyncio.wait_for(waiter, timeout=limits.wall_clock_s)
        # EOF/leader 退出都不结束墙钟约束：只要进程组里还有后代，就继续等到 deadline。
        while _group_is_alive(pgid):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            await asyncio.sleep(min(_GROUP_POLL_S, remaining))
    except asyncio.TimeoutError:
        timed_out = True
    except asyncio.CancelledError:
        await _stop_spawn(process, pgid, waiter, pumps)
        raise
    except BaseException:
        # 读取异常（reader 崩溃等）同样必须清理自己拥有的进程组并 reap。
        await _stop_spawn(process, pgid, waiter, pumps)
        raise
    if timed_out:
        await _stop_spawn(process, pgid, waiter, pumps)

    raw_stdout = budget.text("stdout")
    raw_stderr = budget.text("stderr")
    stdout_cap = limits.max_output_chars
    if protocol_stdout_bytes is not None:
        stdout_cap = max(int(protocol_stdout_bytes), limits.max_output_chars)
    stdout = raw_stdout[:stdout_cap]
    stderr = raw_stderr[: limits.max_output_chars]
    trimmed = budget.truncated or len(stdout) < len(raw_stdout) or len(stderr) < len(raw_stderr)
    exit_code = process.returncode if process.returncode is not None else 124
    return ChartExecutionResult(
        exit_code=124 if timed_out else int(exit_code),
        timed_out=timed_out,
        error="",
        stdout=stdout,
        stderr=stderr,
        output_truncated=budget.truncated or trimmed,
        backend=backend_name,
        elapsed_s=round(time.monotonic() - started, 3),
    )


# ---------------------------------------------------------------------------
# attempt 记录（服务端私有，模型可写挂载之外）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChartAttempt:
    run: report_store.ReportRun
    basename: str
    attempt_id: str
    started_at: float
    target: Path
    record_path: Path


def chart_target_name(
    expected_png: object, *, policy: ReportExecutionPolicy = DEFAULT_POLICY
) -> str:
    """服务端预分配名校验：``chart_N.png``（N 1..max_charts）。

    与 ``report_inputs.chart_target_basename`` 共用同一份 fullmatch 正则；这里额外
    应用本次策略的 ``max_charts`` 上限（≤8）。
    """
    name = report_inputs.chart_target_basename(expected_png, what="期望产物名")
    match = CHART_NAME_RE.fullmatch(name)
    if match is None or int(match.group(1)) > policy.max_charts:
        raise json_store.invalid_input("期望产物名超出本次运行的图表数量上限")
    return name


def chart_target_path(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> Path:
    name = chart_target_name(expected_png, policy=policy)
    return json_store.confined(run.workdir, run.workdir / name)


def attempt_record_path(run: report_store.ReportRun, basename: str) -> Path:
    return run.attempts_dir / f"{basename}.json"


def begin_chart_attempt(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartAttempt:
    """开始"本次 attempt"：清除该名字的旧产物并写入可核查的代次记录。

    旧产物**先删**再执行，因此执行后还在那个路径上的文件只可能来自本次 attempt；
    记录写在 staging（不在模型可写挂载里），模型无法伪造。``generation`` 单调递增，
    用来防止旧 attempt 的收尾反向覆盖新代次。
    """
    report_store.require_report_run(run, require_running=True)
    name = chart_target_name(expected_png, policy=policy)
    target = chart_target_path(run, name, policy=policy)
    if target.is_symlink():
        # 旧符号链接直接删除（删除链接本身不动目标），随后再校验。
        target.unlink()
    if target.exists() and not target.is_file():
        raise json_store.invalid_input("期望产物路径不是普通文件")
    if target.exists():
        target.unlink()
    if target.exists() or target.is_symlink():
        raise subject_error(ErrorCode.STORAGE_IO)
    json_store.make_directory(run.attempts_dir)
    record_path = attempt_record_path(run, name)
    with json_store.json_transaction(run.attempts_dir):
        previous = read_chart_attempt(run, name) or {}
        generation = previous.get("generation")
        generation = (
            generation + 1
            if isinstance(generation, int) and not isinstance(generation, bool)
            else 1
        )
        attempt = ChartAttempt(
            run=run,
            basename=name,
            attempt_id=uuid.uuid4().hex,
            started_at=time.time(),
            target=target,
            record_path=record_path,
        )
        json_store.atomic_write_object(
            record_path,
            {
                "schema": CHART_ATTEMPT_SCHEMA,
                "run_id": run.report_id,
                "staging_dir": str(run.staging_dir),
                "basename": name,
                "attempt_id": attempt.attempt_id,
                "generation": generation,
                "started_at": attempt.started_at,
                "pid": os.getpid(),
                "cleared": True,
                "finished": False,
                "succeeded": False,
                "status": "",
                "exit_code": None,
                "timed_out": False,
                "error": "",
                "artifact": None,
                "finished_at": None,
            },
        )
    return attempt


def _artifact_binding(run: report_store.ReportRun, name: str) -> dict[str, Any] | None:
    """从**真实字节**算出本次产物的 size/sha256（缺失/链接/目录都算没有产物）。"""
    try:
        target = chart_target_path(run, name)
    except (SubjectStorageError, SubjectOperationError):
        return None
    if target.is_symlink() or not target.is_file():
        return None
    try:
        info = target.lstat()
        size, digest = _artifact_hash(target, limit=MAX_ATTEMPT_ARTIFACT_BYTES)
    except (OSError, SubjectOperationError, SubjectStorageError):
        return None
    if size <= 0 or size != info.st_size:
        return None
    return {"name": name, "size": size, "sha256": digest}


def _attempt_succeeded(
    result: ChartExecutionResult | None, binding: Mapping[str, Any] | None
) -> bool:
    """只有**完整成功**的执行结果才允许后续 PNG 验证（finished ≠ 成功）。"""
    if result is None:
        return False
    if result.mode != "chart":
        return False
    if result.status != "ok" or result.timed_out or result.error != "" or result.exit_code != 0:
        return False
    if binding is None:
        return False
    claimed = result.artifact
    return isinstance(claimed, Mapping) and _validate_artifact_payload(
        claimed, str(binding["name"])
    ) == dict(binding)


def finish_chart_attempt(
    attempt: ChartAttempt, result: ChartExecutionResult | None
) -> dict[str, Any]:
    """按 ``attempt_id`` CAS 收尾本次 attempt：旧代次不能覆盖新代次。

    成功与否由结果 + **真实产物字节**共同决定，并把 size/sha256 绑定进记录；P34 之后
    用真实文件重新比对这份绑定，执行完成后被替换的 PNG 无法冒充 worker 产物。
    """
    record_path = attempt.record_path
    with json_store.json_transaction(attempt.run.attempts_dir):
        current = read_chart_attempt(attempt.run, attempt.basename)
        if current is None or current.get("attempt_id") != attempt.attempt_id:
            # 已经被更新的一次 attempt 收尾：旧收尾无权改写。
            return current or {}
        if current.get("finished") is True:
            return current
        binding = _artifact_binding(attempt.run, attempt.basename)
        record = {
            **current,
            "finished": True,
            "finished_at": time.time(),
            "exit_code": None
            if result is None
            else (int(result.exit_code) if not isinstance(result.exit_code, bool) else None),
            "timed_out": bool(result.timed_out) if result is not None else True,
            "error": "" if result is None else str(result.error),
            "status": "" if result is None else str(result.status),
            "succeeded": _attempt_succeeded(result, binding),
            "artifact": binding,
        }
        json_store.atomic_write_object(record_path, record)
    return record


def read_chart_attempt(run: report_store.ReportRun, expected_png: object) -> dict[str, Any] | None:
    """读本次 attempt 记录；不存在返回 ``None``，损坏则明确 ``storage_corrupt``。"""
    report_store.require_report_run(run)
    name = expected_png if isinstance(expected_png, str) else ""
    if not CHART_NAME_RE.fullmatch(name):
        return None
    path = attempt_record_path(run, name)
    if not path.is_file():
        return None
    payload = json_store.read_object(path, default={})
    if not payload:
        return None
    if payload.get("basename") != name or payload.get("staging_dir") != str(run.staging_dir):
        return None
    if payload.get("run_id") != run.report_id:
        return None
    if not isinstance(payload.get("attempt_id"), str) or not payload["attempt_id"]:
        raise json_store.corrupt_error(path.name, "attempt_id 非法")
    return payload


# ---------------------------------------------------------------------------
# 执行入口
# ---------------------------------------------------------------------------
async def _qualified_backend(
    policy: ReportExecutionPolicy,
) -> ReportSandboxBackend:
    """取 backend 并完成证明 + 健康检查；不合格一律 503，不做宿主回退。"""
    backend = select_report_backend(policy)
    proof = _backend_proof(backend)
    if proof is None or not proof.is_qualified():
        raise subject_error(ErrorCode.SANDBOX_POLICY_UNSUPPORTED)
    build_spawn = getattr(backend, "build_spawn", None)
    if not callable(build_spawn):
        raise subject_error(ErrorCode.SANDBOX_POLICY_UNSUPPORTED)
    try:
        healthy, _detail = await backend.health()
    except Exception as exc:  # noqa: BLE001 - 健康探测异常等于不健康
        raise subject_error(ErrorCode.SANDBOX_UNAVAILABLE, cause=exc) from exc
    if not healthy:
        raise subject_error(ErrorCode.SANDBOX_UNAVAILABLE)
    return backend


def _worker_path() -> Path:
    return Path(__file__).resolve().with_name(WORKER_FILENAME)


def _spec_payload(name: str, *, limits: ReportResourceLimits, **extra: Any) -> dict[str, Any]:
    return {
        "script": CHART_SCRIPT_NAME,
        "cpu_seconds": limits.cpu_seconds,
        "memory_mb": limits.memory_mb,
        "max_file_bytes": limits.max_artifact_bytes,
        "wall_clock_s": limits.wall_clock_s,
        **extra,
    }


def _worker_argv(mode: str, spec: Mapping[str, Any]) -> tuple[str, ...]:
    """argv 全部由服务端生成；没有 shell，模型也无法拼 command。"""
    return (
        str(sys.executable),
        "-I",
        "-B",
        str(_worker_path()),
        mode,
        json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
    )


def _write_model_script(run: report_store.ReportRun, code: str) -> Path:
    """把模型代码写成工作目录里的 ``_chart.py``（O_NOFOLLOW，拒绝被换链接）。"""
    target = json_store.confined(run.workdir, run.workdir / CHART_SCRIPT_NAME)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        with contextlib.suppress(OSError):
            target.unlink()
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(code)
    except OSError as exc:  # pragma: no cover - 磁盘错误
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    return target


def _artifact_hash(path: Path, *, limit: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            total += len(chunk)
            if total > limit:
                raise json_store.invalid_input("产物超过大小上限")
            digest.update(chunk)
    return total, digest.hexdigest()


#: worker envelope 允许的固定状态；未知状态一律不是成功。
WORKER_STATUSES = frozenset(
    {"ok", "script_failed", "no_artifact", "timed_out", "ode_failed", "worker_error"}
)
_ENVELOPE_BASE_KEYS = frozenset({"schema", "mode", "status", "exit_code", "timed_out"})
_ENVELOPE_CHART_KEYS = _ENVELOPE_BASE_KEYS | {
    "expected_png",
    "artifact",
    "stdout_tail",
    "stderr_tail",
}
_ENVELOPE_ODE_KEYS = _ENVELOPE_BASE_KEYS | {"checks", "stdout_tail", "stderr_tail"}


def _strict_int(value: object) -> int | None:
    """严格整数：bool 不是 int（``int(True) == 1`` 不能把坏字段变成合法）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _validate_artifact_payload(value: object, expected_png: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    if set(value) != {"name", "size", "sha256"}:
        return None
    if value.get("name") != expected_png:
        return None
    size = _strict_int(value.get("size"))
    digest = value.get("sha256")
    if size is None or size <= 0 or not isinstance(digest, str):
        return None
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return {"name": expected_png, "size": size, "sha256": digest}


def _validate_worker_envelope(
    payload: object, *, ode: bool, expected_png: str
) -> dict[str, Any] | None:
    """固定 schema/mode/status/类型 + 交叉一致性；任何偏差返回 ``None``（fail-closed）。

    这里**不做** ``int()``/``bool()``/``str()`` 隐式转换：坏字段只能让整个结果失败，
    不能被"修"成合法值。
    """
    if not isinstance(payload, Mapping):
        return None
    mode = "ode" if ode else "chart"
    allowed_keys = _ENVELOPE_ODE_KEYS if ode else _ENVELOPE_CHART_KEYS
    if set(payload) - allowed_keys:
        return None
    if not _ENVELOPE_BASE_KEYS <= set(payload):
        return None
    if _strict_int(payload.get("schema")) != 1:
        return None
    if payload.get("mode") != mode:
        return None
    status = payload.get("status")
    if not isinstance(status, str) or status not in WORKER_STATUSES:
        return None
    exit_code = _strict_int(payload.get("exit_code"))
    if exit_code is None or not 0 <= exit_code <= 255:
        return None
    if not isinstance(payload.get("timed_out"), bool):
        return None
    if (status == "timed_out") != payload["timed_out"]:
        return None
    if status == "ok" and exit_code != 0:
        return None
    if status == "script_failed" and exit_code == 0:
        return None
    for key in ("stdout_tail", "stderr_tail"):
        if key in payload and not isinstance(payload[key], str):
            return None
    if ode:
        if status not in {"ok", "ode_failed", "timed_out", "worker_error"}:
            return None
        checks = payload.get("checks")
        if checks is not None and not isinstance(checks, Mapping):
            return None
        if status == "ok" and (not isinstance(checks, Mapping) or checks.get("ok") is not True):
            return None
        if status != "ok" and isinstance(checks, Mapping) and checks.get("ok") is True:
            return None
    else:
        if status == "ode_failed":
            return None
        if payload.get("expected_png") != expected_png:
            return None
        if (
            status == "ok"
            and _validate_artifact_payload(payload.get("artifact"), expected_png) is None
        ):
            # "ok" 却没有可信产物结构：不是成功。
            return None
    return dict(payload)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate control key")
        value[key] = item
    return value


def _parse_worker_payload(
    result: ChartExecutionResult, *, ode: bool = False, expected_png: str = ""
) -> tuple[ChartExecutionResult, dict | None]:
    """严格解析 worker 的**唯一** stdout 对象；任何多余内容都 fail-closed。"""
    if result.error or result.timed_out:
        return result, None
    if result.exit_code != 0:
        return replace(result, error="worker_failed"), None
    raw = result.stdout.strip()
    try:
        payload = json.loads(
            raw,
            parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)),
            object_pairs_hook=_unique_json_object,
        )
    except (json.JSONDecodeError, ValueError):
        return replace(result, error="worker_failed"), None
    validated = _validate_worker_envelope(payload, ode=ode, expected_png=expected_png)
    if validated is None:
        return replace(result, error="worker_failed"), None
    if validated.get("status") == "worker_error":
        return replace(result, error="worker_failed"), None
    return result, validated


async def _execute(
    run: report_store.ReportRun,
    policy: ReportExecutionPolicy,
    *,
    mode: str,
    spec: Mapping[str, Any],
    ode: bool,
) -> ChartExecutionResult:
    report_store.require_report_run(run, require_running=True)
    backend = await _qualified_backend(policy)
    argv = _worker_argv(mode, spec)
    request = _build_request(run, policy, argv, ode=ode)
    # 准备阶段（创建本 run 的 cache/home）发生在身份与状态验证之后。
    _prepare_runtime_dirs(run)
    spawn = backend.build_spawn(request)
    raw = await run_bounded_spawn(
        spawn,
        request.limits,
        backend_name=str(getattr(backend, "name", "backend")),
        protocol_stdout_bytes=CONTROL_PROTOCOL_FLOOR_BYTES,
    )
    expected_png = str(spec.get("expected_png") or "")
    parsed, payload = _parse_worker_payload(raw, ode=ode, expected_png=expected_png)
    if payload is None:
        return replace(
            parsed,
            artifact=None,
            checks=None,
            mode="ode" if ode else "chart",
            status="",
        )
    stdout = str(payload.get("stdout_tail") or "")
    stderr = str(payload.get("stderr_tail") or "")
    stdout, stderr, trimmed = _trim_outputs(stdout, stderr, request.limits.max_output_chars)
    artifact = (
        _validate_artifact_payload(payload.get("artifact"), expected_png) if not ode else None
    )
    checks = payload.get("checks") if ode else None
    return replace(
        parsed,
        exit_code=_strict_int(payload.get("exit_code")) or 0,
        timed_out=bool(payload.get("timed_out")),
        error="",
        stdout=stdout,
        stderr=stderr,
        artifact=artifact,
        checks=checks if isinstance(checks, Mapping) else None,
        output_truncated=parsed.output_truncated or trimmed,
        worker_payload=payload,
        mode="ode" if ode else "chart",
        status=str(payload.get("status") or ""),
    )


def plan_chart_request(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartSandboxRequest:
    """给出一次图表执行**将会**使用的 argv/挂载/环境/限额向量（诊断与不变量检查）。

    纯计算：不启动进程、不写文件、不解析 backend。P33 的验收需要能看到真实向量
    （而不是只断言"某个 helper 被调用过"），P35 也可以用它做服务端诊断。
    """
    report_store.require_report_run(run)
    name = chart_target_name(expected_png, policy=policy)
    limits = policy.limits(ode=False)
    spec = _spec_payload(name, limits=limits, expected_png=name)
    return _build_request(run, policy, _worker_argv("--chart", spec), ode=False)


async def execute_chart_code(
    code: str,
    *,
    run: report_store.ReportRun,
    expected_png: str,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
    """在报告沙箱里运行模型图表代码，并返回结构化结果。

    * ``code`` 必须先通过 P31 输入契约（非空字符串）；本函数把它写成工作目录里的
      ``_chart.py``（服务端固定名字）。
    * 执行前清除 ``expected_png`` 的旧产物并写下 attempt 记录，因此执行结束后该路径
      上的文件只可能来自本次 attempt。
    * 无合格 backend → ``sandbox_unavailable``/``sandbox_policy_unsupported``（503），
      **绝不**退回宿主 ``subprocess``。
    """
    if not isinstance(code, str) or not code.strip():
        raise json_store.invalid_input("图表代码必须是非空字符串")
    # 与 P31 同一输入门：非 UTF-8 可编码的源码不能走到写文件。
    try:
        code.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise json_store.invalid_input("图表代码必须是 UTF-8 可编码的文本") from exc
    report_store.require_report_run(run, require_running=True)
    name = chart_target_name(expected_png, policy=policy)
    with _exclusive_run_execution(run):
        attempt = begin_chart_attempt(run, name, policy=policy)
        result: ChartExecutionResult | None = None
        try:
            _write_model_script(run, code)
            limits = policy.limits(ode=False)
            spec = _spec_payload(name, limits=limits, expected_png=name)
            result = await _execute(run, policy, mode="--chart", spec=spec, ode=False)
            return result
        finally:
            finish_chart_attempt(attempt, result)


def _require_points(points: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(points, (list, tuple)) or not 1 <= len(points) <= MAX_ODE_POINTS:
        raise json_store.invalid_input("ODE 检查点必须是 1..%d 个点" % MAX_ODE_POINTS)
    collected: list[tuple[float, float]] = []
    for point in points:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in point)
        ):
            raise json_store.invalid_input("ODE 检查点必须是 [x, y] 数值对")
        collected.append((float(point[0]), float(point[1])))
    return tuple(collected)


async def execute_ode_check(
    run: report_store.ReportRun,
    expression: object,
    *,
    points: object,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
    """用**同一个**受限执行器与 trusted worker 做 5 点 ODE 数值检查。

    表达式先过 P31 的 AST 白名单（拒绝即 ``invalid_input``，不会进入执行器）；
    检查在隔离环境内读取当前脚本的 ``f``，结果放在 :attr:`ChartExecutionResult.checks`。
    """
    report_store.require_report_run(run, require_running=True)
    validated = validate_ode_expression(expression)
    if not validated:
        raise json_store.invalid_input("ODE 检查需要非空表达式")
    checked_points = _require_points(points)
    limits = policy.for_ode().limits(ode=True)
    spec = _spec_payload(
        CHART_SCRIPT_NAME,
        limits=limits,
        expression=validated,
        points=[[x, y] for x, y in checked_points],
    )
    with _exclusive_run_execution(run):
        return await _execute(run, policy.for_ode(), mode="--ode", spec=spec, ode=True)


def chart_failure_error(result: ChartExecutionResult) -> SubjectOperationError | None:
    """把执行结果映射成 C02 固定错误；**完整成功**才返回 ``None``。

    * 基础设施错误 → 对应的 503/502 固定错误；
    * 非 0 退出码或超时 → ``chart_failed``（即使某个 ``ExecResult.ok`` 说成功）；
    * chart 模式：必须 ``status == "ok"`` 且带**严格结构**的产物（名字/正 size/64 位
      hash）；"exit 0 但没图"不是成功；
    * ODE 模式：必须给出可信父 worker 计算出的 ``checks.ok is True``。
    """
    if result.error:
        if result.error in {"sandbox_spawn_failed", "sandbox_unavailable"}:
            return subject_error(ErrorCode.SANDBOX_UNAVAILABLE)
        if result.error == "sandbox_policy_unsupported":
            return subject_error(ErrorCode.SANDBOX_POLICY_UNSUPPORTED)
        return subject_error(ErrorCode.CHART_FAILED)
    if result.timed_out or result.exit_code != 0:
        return subject_error(ErrorCode.CHART_FAILED)
    if result.mode == "ode":
        checks = result.checks
        if not isinstance(checks, Mapping) or checks.get("ok") is not True:
            return subject_error(ErrorCode.CHART_FAILED)
        return None
    if result.status != "ok":
        return subject_error(ErrorCode.CHART_FAILED)
    if (
        _validate_artifact_payload(result.artifact, str((result.artifact or {}).get("name", "")))
        is None
    ):
        return subject_error(ErrorCode.CHART_FAILED)
    return None


__all__ = [
    "CHART_NAME_RE",
    "CHART_SCRIPT_NAME",
    "DEFAULT_POLICY",
    "ENV_ALLOWLIST",
    "MAX_ODE_POINTS",
    "NARROW_ETC_ENTRIES",
    "SYSTEM_READ_ONLY_DIRS",
    "WORKER_FILENAME",
    "BwrapReportBackend",
    "ChartAttempt",
    "ChartExecutionResult",
    "ChartSandboxRequest",
    "ReportExecutionPolicy",
    "ReportIsolationProof",
    "ReportMount",
    "ReportResourceLimits",
    "ReportSandboxBackend",
    "SpawnCommand",
    "attempt_record_path",
    "begin_chart_attempt",
    "bind_proof",
    "WORKER_STATUSES",
    "chart_failure_error",
    "chart_target_name",
    "chart_target_path",
    "execute_chart_code",
    "execute_ode_check",
    "finish_chart_attempt",
    "plan_chart_request",
    "read_chart_attempt",
    "report_read_only_mounts",
    "run_bounded_spawn",
    "select_report_backend",
]
