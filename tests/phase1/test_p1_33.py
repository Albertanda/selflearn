"""P1-33 行为测试：报告专用受限执行器与可信 worker。

目标：模型代码只能访问**本次 run**，没有网络、没有密钥、没有宿主回退；超时与输出
都有界；不合格 backend 固定 503。fake backend 只用来证明 policy 与受控进程边界，
真实 bwrap 只用于本机能力探测——**OS 隔离验收属于 S15/P50**，本文件不宣称已通过。

必证场景（对应卡片清单与 START_S08 第二节 P1-33 的"证据"）：

* 只一个当前 run 宿主可写、trusted worker 不可改写、字体/解释器只读；
* 测试 secret / 代理 / PYTHONPATH 都不进 request env；
* APPLICATION / shared runner / OFF 拒绝且**不调用**宿主执行；
* exit_code 非 0 即失败，即便 ``ExecResult.ok`` 为 True；
* health 非 0/超时拒绝；超时与取消终止整组并 reap；
* 输出洪泛有界（读取期间就限内存）；worker 在执行 body 前设置 hard limits；
* 模型伪造 limits/mounts/env 无效。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

import pytest

from deeptutor.services.pdf import chart_executor as ce
from deeptutor.services.pdf import report_inputs as ri
from deeptutor.services.pdf import report_store as rs
from deeptutor.services.sandbox.backends import (
    BwrapBackend,
    RestrictedSubprocessBackend,
    RunnerSidecarBackend,
)
from deeptutor.services.sandbox.config import SandboxSettings, build_backend
from deeptutor.services.sandbox.spec import ExecRequest, ExecResult
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from tests.phase1 import helpers

ODE_POINTS = [(-2.5, 1.0), (0.0, 0.5), (1.7, -2.0), (2.2, 2.5), (-0.8, -3.0)]

#: 本文件注入的假 secret：绝不允许出现在 request env / argv 里。
FAKE_SECRET = "p1-33-FAKE-SECRET-9d2c4f"
FAKE_KEY_NAME = "P1_33_FAKE_API_KEY"
FAKE_PROXY = "http://p1-33-fake-proxy.invalid:8888"

ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def p1_subject(p1_runtime: Path):
    rs._reset_active_runs_for_tests()
    try:
        yield helpers.make_subject(p1_runtime, "报告科目")
    finally:
        rs._reset_active_runs_for_tests()


@pytest.fixture
def p1_run(p1_subject) -> rs.ReportRun:
    return rs.create_report_run(p1_subject.subject_id)


# ---------------------------------------------------------------------------
# 受控边界用的 fake backend（只证明 policy：真实 worker + 真实执行器）
# ---------------------------------------------------------------------------
class _HostBackend:
    """把 worker 直接放到宿主跑的"受控进程边界"后端。

    它不是生产 backend：只用于证明执行器的策略、有界读取、超时清理与失败映射。
    """

    name = "controlled-host-boundary"

    def __init__(self, *, healthy: bool = True, proof: ce.ReportIsolationProof | None = None):
        self._healthy = healthy
        self._proof = proof or ce.ReportIsolationProof(
            per_task_namespaces=True,
            per_task_mounts=True,
            network_disabled=True,
            env_cleared=True,
            process_group_cleanup=True,
        )
        self.spawns: list[ce.ChartSandboxRequest] = []

    def isolation_proof(self) -> ce.ReportIsolationProof:
        return self._proof

    async def health(self) -> tuple[bool, str]:
        return self._healthy, "controlled boundary"

    def build_spawn(self, request: ce.ChartSandboxRequest) -> ce.SpawnCommand:
        self.spawns.append(request)
        return ce.SpawnCommand(argv=tuple(request.argv), cwd=request.workdir, env=dict(request.env))


class _NoProofBackend:
    """同名/同形状但没有本模块证明类型的 backend（例如共享 runner）。"""

    name = "shared-runner"
    level = "system"  # 可伪造的标签：不构成任何证明

    def __init__(self) -> None:
        self.called = False

    async def health(self) -> tuple[bool, str]:
        return True, "pretends to be fine"

    def build_spawn(self, request: ce.ChartSandboxRequest) -> ce.SpawnCommand:
        self.called = True
        return ce.SpawnCommand(argv=tuple(request.argv), cwd=request.workdir, env=dict(request.env))


def _policy(backend: object, **overrides: object) -> ce.ReportExecutionPolicy:
    return ce.ReportExecutionPolicy(backend=backend, **overrides)  # type: ignore[arg-type]


def _run(coro):
    return asyncio.run(coro)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 策略向量：mounts / env / argv / limits
# ---------------------------------------------------------------------------
def test_only_the_current_run_workdir_is_a_writable_mount(p1_run: rs.ReportRun) -> None:
    request = ce.plan_chart_request(p1_run, "chart_1.png")

    writable = [mount for mount in request.mounts if not mount.read_only]
    assert len(writable) == 1
    assert writable[0].host_path == str(p1_run.workdir)
    assert writable[0].sandbox_path == str(p1_run.workdir)
    assert request.workdir == p1_run.workdir

    worker = Path(ce.__file__).resolve().with_name(ce.WORKER_FILENAME)
    read_only = {mount.host_path for mount in request.mounts if mount.read_only}
    assert str(worker) in read_only
    assert str(p1_run.workdir) not in read_only
    repo_root = Path(helpers.__file__).resolve().parents[2]
    for mount in request.mounts:
        if mount.read_only:
            # 只读挂载不得**覆盖**仓库根/home/数据根/其他 run（可以是具体运行库子目录）。
            host = Path(mount.host_path)
            for blocked in (
                Path("/"),
                Path.home(),
                repo_root,
                p1_run.staging_dir,
                p1_run.public_dir,
            ):
                # 只读挂载不得**包含**敏感根（可以是被需要的具体运行库/worker 文件，
                # 它们本身位于 home/repo 之下，这是不可避免的）。
                assert host != blocked, (host, blocked)
                if blocked != Path("/"):
                    assert host not in blocked.parents, (host, blocked)
    assert "/etc" not in {mount.host_path for mount in request.mounts}


def test_unlisted_env_is_not_copied_from_os_environ(p1_run: rs.ReportRun, monkeypatch) -> None:
    monkeypatch.setenv(FAKE_KEY_NAME, FAKE_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_SECRET)
    monkeypatch.setenv("HTTPS_PROXY", FAKE_PROXY)
    monkeypatch.setenv("PYTHONPATH", "/tmp/p1-33-should-not-appear")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/p1-33-should-not-appear.so")

    request = ce.plan_chart_request(p1_run, "chart_1.png")

    assert set(request.env) <= set(ce.ENV_ALLOWLIST)
    for key in (FAKE_KEY_NAME, "OPENAI_API_KEY", "HTTPS_PROXY", "PYTHONPATH", "LD_PRELOAD"):
        assert key not in request.env
    joined = " ".join(request.env.values()) + " " + " ".join(request.argv)
    assert FAKE_SECRET not in joined
    assert FAKE_PROXY not in joined
    assert "p1-33-should-not-appear" not in joined
    # 缓存/配置目录限在本 run 内。
    assert request.env["HOME"] == str(p1_run.workdir / "home")
    assert request.env["MPLCONFIGDIR"] == str(p1_run.workdir / "mplconfig")
    assert request.env["TMPDIR"] == "/tmp"


def test_worker_argv_is_a_fixed_server_vector(p1_run: rs.ReportRun) -> None:
    request = ce.plan_chart_request(p1_run, "chart_2.png")

    argv = request.argv
    assert argv[0] == sys.executable
    assert argv[1:3] == ("-I", "-B")
    assert argv[3] == str(Path(ce.__file__).resolve().with_name(ce.WORKER_FILENAME))
    assert argv[4] == "--chart"
    spec = json.loads(argv[5])
    assert spec["script"] == ce.CHART_SCRIPT_NAME  # 服务端固定名字
    assert spec["expected_png"] == "chart_2.png"
    assert spec["cpu_seconds"] == 30 and spec["memory_mb"] == 1536
    assert spec["wall_clock_s"] == 60 and spec["max_file_bytes"] == 10 * 1024 * 1024
    # 没有 shell，也没有模型能拼命令的入口。
    for token in ("sh", "-c", "bash", "&&", ";", "|"):
        assert token not in argv[:3]

    limits = request.limits
    assert (limits.wall_clock_s, limits.cpu_seconds) == (60, 30)
    assert limits.memory_mb == 1536
    assert limits.max_output_chars == 10_000
    assert limits.max_artifact_bytes == 10 * 1024 * 1024
    assert request.describe()["env_keys"] == sorted(request.env)


def test_limits_mounts_env_cannot_come_from_the_model(p1_run: rs.ReportRun) -> None:
    signature = inspect.signature(ce.execute_chart_code)
    assert list(signature.parameters) == ["code", "run", "expected_png", "policy"]
    assert signature.parameters["policy"].default is ce.DEFAULT_POLICY

    # 控制参数只在服务端策略里；传入的 code 无法影响任何一项。
    hostile = "import os\nprint(os.environ)\n"
    request = ce.plan_chart_request(p1_run, "chart_1.png")
    assert ce.CHART_SCRIPT_NAME not in hostile
    assert request.env["PATH"].startswith(str(Path(sys.executable).parent))
    assert [mount.read_only for mount in request.mounts].count(False) == 1


def test_expected_png_must_be_a_server_allocated_name(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    for bad in (
        "../chart_1.png",
        "/etc/chart_1.png",
        "chart_0.png",
        "chart_9.png",
        "chart_10.png",
        "chart_1.PNG",
        "chart_1.png.png",
        "",
        7,
        None,
    ):
        with pytest.raises(json_store.InvalidInputError):
            _run(
                ce.execute_chart_code(
                    "print('x')", run=p1_run, expected_png=bad, policy=_policy(backend)
                )
            )
    assert backend.spawns == []
    assert list(p1_run.workdir.iterdir()) == []


def test_chart_code_must_be_a_non_empty_string(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    for bad in ("", "   ", "\n", None, ["print(1)"], {"code": "x"}, 5):
        with pytest.raises(json_store.InvalidInputError):
            _run(
                ce.execute_chart_code(
                    bad, run=p1_run, expected_png="chart_1.png", policy=_policy(backend)
                )
            )
    assert backend.spawns == []
    assert rs.read_run_manifest(p1_run).status == rs.STATUS_RUNNING


# ---------------------------------------------------------------------------
# backend 资格与 503
# ---------------------------------------------------------------------------
def test_application_shared_and_off_backends_are_refused_without_host_execution(
    p1_run: rs.ReportRun, monkeypatch, tmp_path: Path
) -> None:
    canary = tmp_path / "host-executed.txt"
    code = f"open({str(canary)!r}, 'w').write('ran')\nopen('chart_1.png','wb').write({ONE_PIXEL_PNG!r})\n"

    no_proof = _NoProofBackend()
    with pytest.raises(SubjectOperationError) as info:
        _run(
            ce.execute_chart_code(
                code, run=p1_run, expected_png="chart_1.png", policy=_policy(no_proof)
            )
        )
    assert info.value.code is ErrorCode.SANDBOX_POLICY_UNSUPPORTED
    assert info.value.http_status == 503
    assert no_proof.called is False

    # 真实共享 backend / sidecar runner：同样不被接受，也不启动任何进程。
    settings = SandboxSettings(runner_url="http://sandbox-runner:8900")
    shared = build_backend(settings)
    assert isinstance(shared, RunnerSidecarBackend)
    for candidate in (shared, RestrictedSubprocessBackend(), BwrapBackend()):
        with pytest.raises(SubjectOperationError) as info:
            _run(
                ce.execute_chart_code(
                    code, run=p1_run, expected_png="chart_1.png", policy=_policy(candidate)
                )
            )
        assert info.value.code is ErrorCode.SANDBOX_POLICY_UNSUPPORTED

    # 只给了部分证明（例如 application 级路径守卫）也不合格。
    partial = _HostBackend(proof=ce.ReportIsolationProof(per_task_mounts=True))
    with pytest.raises(SubjectOperationError) as info:
        _run(
            ce.execute_chart_code(
                code, run=p1_run, expected_png="chart_1.png", policy=_policy(partial)
            )
        )
    assert info.value.code is ErrorCode.SANDBOX_POLICY_UNSUPPORTED
    assert partial.spawns == []
    assert not canary.exists()
    assert not (p1_run.workdir / "chart_1.png").exists()


def test_missing_or_unhealthy_backend_is_a_fixed_503(p1_run: rs.ReportRun, monkeypatch) -> None:
    code = "print('never runs')\n"
    monkeypatch.setattr(ce.shutil, "which", lambda _name: None)
    with pytest.raises(SubjectOperationError) as info:
        _run(ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png"))
    assert info.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert info.value.http_status == 503

    unhealthy = _HostBackend(healthy=False)
    with pytest.raises(SubjectOperationError) as info:
        _run(
            ce.execute_chart_code(
                code, run=p1_run, expected_png="chart_1.png", policy=_policy(unhealthy)
            )
        )
    assert info.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert unhealthy.spawns == []

    class _BrokenHealth(_HostBackend):
        async def health(self) -> tuple[bool, str]:
            raise RuntimeError("health probe exploded")

    with pytest.raises(SubjectOperationError) as info:
        _run(
            ce.execute_chart_code(
                code,
                run=p1_run,
                expected_png="chart_1.png",
                policy=_policy(_BrokenHealth()),
            )
        )
    assert info.value.code is ErrorCode.SANDBOX_UNAVAILABLE


def test_selection_ignores_shared_sandbox_settings(p1_run: rs.ReportRun, monkeypatch) -> None:
    """报告路径不看共享 sandbox settings：没有 bwrap 就是 503，不会降级。"""
    monkeypatch.setenv("DEEPTUTOR_SANDBOX_RUNNER_URL", "http://sandbox-runner:8900")
    assert isinstance(ce.select_report_backend(), ce.BwrapReportBackend)
    monkeypatch.setattr(ce.shutil, "which", lambda _name: None)
    with pytest.raises(SubjectOperationError) as info:
        ce.select_report_backend()
    assert info.value.code is ErrorCode.SANDBOX_UNAVAILABLE


def test_real_backend_proof_and_health_are_behaviour_backed() -> None:
    """真实 bwrap 的能力探测（本机能力，不等于 S15 的 OS 隔离验收）。"""
    backend = ce.BwrapReportBackend()
    proof = backend.isolation_proof()
    assert proof.is_qualified() is True
    assert ce.bind_proof(proof) is proof
    assert ce.bind_proof({"per_task_namespaces": True}) is None
    assert ce._backend_proof(_NoProofBackend()) is None

    healthy, detail = _run(backend.health())
    assert healthy is True, detail
    assert "isolated" in detail


# ---------------------------------------------------------------------------
# 非 0 退出、超时、输出洪泛
# ---------------------------------------------------------------------------
def test_nonzero_exit_is_a_failure_even_when_exec_result_ok_is_true(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    code = "import sys\nsys.exit(3)\n"

    result = _run(
        ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png", policy=_policy(backend))
    )

    assert result.exit_code == 3
    assert result.error == ""
    assert result.ok is False
    assert ce.chart_failure_error(result) is not None
    assert ce.chart_failure_error(result).code is ErrorCode.CHART_FAILED

    # 这正是历史缺陷：ExecResult.ok 不看 exit_code。
    legacy = ExecResult(stdout="", stderr="", exit_code=3)
    assert legacy.ok is True
    assert ExecRequest(command="true").limits.timeout_s == 30
    assert ce.chart_failure_error(ce.ChartExecutionResult(3, False, "")) is not None


def test_worker_reported_ok_but_missing_artifact_is_not_success(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    result = _run(
        ce.execute_chart_code(
            "print('exit 0 but no artifact')\n",
            run=p1_run,
            expected_png="chart_1.png",
            policy=_policy(backend),
        )
    )
    assert result.exit_code == 0
    assert result.artifact is None
    assert "exit 0 but no artifact" in result.stdout
    record = ce.read_chart_attempt(p1_run, "chart_1.png")
    assert record is not None and record["finished"] is True and record["cleared"] is True


def test_engine_exception_is_reported_as_a_fixed_chart_failure(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    result = _run(
        ce.execute_chart_code(
            "raise RuntimeError('p1-33-raw-noise')\n",
            run=p1_run,
            expected_png="chart_1.png",
            policy=_policy(backend),
        )
    )
    error = ce.chart_failure_error(result)
    assert error is not None and error.code is ErrorCode.CHART_FAILED
    assert str(error) == "图表生成失败。"
    assert "p1-33-raw-noise" not in str(error)
    assert "p1-33-raw-noise" not in repr(error)


def test_timeout_kills_the_whole_process_group(p1_run: rs.ReportRun, tmp_path: Path) -> None:
    canary = p1_run.workdir / "grandchild-survived.txt"
    program = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', \"import time;time.sleep(3);"
        f"open({str(canary)!r},'w').write('x')\"])\n"
        "time.sleep(30)\n"
    )
    limits = ce.ReportResourceLimits(
        wall_clock_s=1,
        cpu_seconds=30,
        memory_mb=512,
        max_output_chars=1000,
        max_artifact_bytes=1 << 20,
    )
    spawn = ce.SpawnCommand(
        argv=(sys.executable, "-I", "-c", program),
        cwd=p1_run.workdir,
        env={"PATH": "/usr/bin:/bin"},
    )

    result = _run(ce.run_bounded_spawn(spawn, limits))

    assert result.timed_out is True
    assert result.exit_code == 124
    assert result.ok is False
    time.sleep(3.5)
    assert not canary.exists(), "超时后仍有子进程活着并写出了文件"
    assert ce.chart_failure_error(result).code is ErrorCode.CHART_FAILED


def test_cancellation_kills_the_group_and_reaps(p1_run: rs.ReportRun) -> None:
    canary = p1_run.workdir / "cancelled-grandchild.txt"
    program = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', \"import time;time.sleep(3);"
        f"open({str(canary)!r},'w').write('x')\"])\n"
        "time.sleep(30)\n"
    )
    limits = ce.ReportResourceLimits(
        wall_clock_s=60,
        cpu_seconds=30,
        memory_mb=512,
        max_output_chars=1000,
        max_artifact_bytes=1 << 20,
    )
    spawn = ce.SpawnCommand(
        argv=(sys.executable, "-I", "-c", program),
        cwd=p1_run.workdir,
        env={"PATH": "/usr/bin:/bin"},
    )

    async def scenario() -> None:
        task = asyncio.create_task(ce.run_bounded_spawn(spawn, limits))
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())
    time.sleep(3.5)
    assert not canary.exists(), "取消后仍有子进程活着"


def test_output_flood_stays_bounded_while_reading(p1_run: rs.ReportRun) -> None:
    program = (
        "import sys\n"
        "chunk = 'x' * 4096\n"
        "for _ in range(256):\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stderr.write(chunk)\n"
        "sys.stdout.flush(); sys.stderr.flush()\n"
    )
    limits = ce.ReportResourceLimits(
        wall_clock_s=30,
        cpu_seconds=30,
        memory_mb=512,
        max_output_chars=1000,
        max_artifact_bytes=1 << 20,
    )
    spawn = ce.SpawnCommand(
        argv=(sys.executable, "-I", "-c", program),
        cwd=p1_run.workdir,
        env={"PATH": "/usr/bin:/bin"},
    )

    result = _run(ce.run_bounded_spawn(spawn, limits))

    assert result.exit_code == 0
    assert result.timed_out is False
    assert len(result.stdout) + len(result.stderr) <= 1000
    assert result.output_truncated is True

    # 默认策略下同样是 10000 字符合计上限。
    default_limits = ce.DEFAULT_POLICY.limits()
    big = _run(ce.run_bounded_spawn(spawn, default_limits))
    assert len(big.stdout) + len(big.stderr) <= 10_000


# ---------------------------------------------------------------------------
# worker：硬限额、私有环境、真实沙箱边界
# ---------------------------------------------------------------------------
def test_worker_sets_hard_limits_before_running_the_model_body(p1_run: rs.ReportRun) -> None:
    code = (
        "import json, resource, sys\n"
        "cpu = resource.getrlimit(resource.RLIMIT_CPU)\n"
        "address = resource.getrlimit(resource.RLIMIT_AS)\n"
        "fsize = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
        "raised = None\n"
        "try:\n"
        "    resource.setrlimit(resource.RLIMIT_AS, (1 << 60, 1 << 60))\n"
        "except (ValueError, OSError) as exc:\n"
        "    raised = type(exc).__name__\n"
        "print(json.dumps({'cpu': cpu, 'address': address, 'fsize': fsize, 'raised': raised}))\n"
        "open('chart_1.png', 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n')\n"
    )
    backend = _HostBackend()
    result = _run(
        ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png", policy=_policy(backend))
    )

    assert result.error == "", result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["cpu"] == [30, 30]
    assert report["address"] == [1536 * 1024 * 1024, 1536 * 1024 * 1024]
    assert report["fsize"] == [10 * 1024 * 1024, 10 * 1024 * 1024]
    assert report["raised"] in ("ValueError", "OSError")  # hard limit 不可被模型抬高


def test_real_sandbox_boundary_probe(p1_run: rs.ReportRun) -> None:
    """真实 bwrap：在沙箱内探测挂载/环境/网络（受控边界，不是 OS 验收）。"""
    worker = Path(ce.__file__).resolve().with_name(ce.WORKER_FILENAME)
    repo_file = Path(ce.__file__).resolve()
    worker_before = _sha256(worker)
    probe = f"""
import json, os, socket, sys
findings = {{}}
findings["cwd"] = os.getcwd()
findings["env_keys"] = sorted(os.environ)
findings["fake_secret"] = {FAKE_SECRET!r} in json.dumps(dict(os.environ))
try:
    with open({str(worker)!r}, "a") as handle:
        handle.write("tamper")
    findings["worker_writable"] = True
except OSError as exc:
    findings["worker_writable"] = type(exc).__name__
for label, path in (("repo_source", {str(repo_file)!r}), ("host_etc_passwd", "/etc/passwd"),
                    ("host_home_root", {str(Path.home())!r})):
    try:
        with open(path, "rb") as handle:
            handle.read(16)
        findings[label] = "readable"
    except OSError as exc:
        findings[label] = type(exc).__name__
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.connect(("1.1.1.1", 53))
    findings["network"] = "reachable"
except OSError:
    findings["network"] = "noroute"
mounts = []
with open("/proc/self/mountinfo") as handle:
    for line in handle:
        fields = line.split()
        if len(fields) > 5 and "-" in fields:
            separator = fields.index("-")
            mounts.append([fields[4], fields[5], fields[separator + 1]])
findings["mounts"] = mounts
open("findings.json", "w").write(json.dumps(findings))
open("chart_1.png", "wb").write({ONE_PIXEL_PNG!r})
"""
    result = _run(ce.execute_chart_code(probe, run=p1_run, expected_png="chart_1.png"))

    assert result.error == "", result.stderr
    assert result.exit_code == 0
    assert result.backend == "bwrap-report"
    # R4 之后 worker 只回传很短的诊断尾巴；观测结果写进本 run 的 workdir 直接读。
    findings = json.loads((p1_run.workdir / "findings.json").read_text(encoding="utf-8"))
    assert findings["cwd"] == str(p1_run.workdir)
    assert findings["worker_writable"] in ("PermissionError", "OSError", "ReadOnlyFileError")
    assert findings["repo_source"] in ("FileNotFoundError", "PermissionError", "OSError")
    assert findings["host_etc_passwd"] == "FileNotFoundError"
    assert findings["network"] == "noroute"
    assert findings["fake_secret"] is False
    expected_env = ce.plan_chart_request(p1_run, "chart_1.png").env
    assert set(findings["env_keys"]) - set(expected_env) <= {"PWD"}  # bwrap 自己补的 cwd
    assert set(expected_env) - set(findings["env_keys"]) == set()
    assert not any(ce._SECRET_KEY_RE.search(key) for key in findings["env_keys"])

    # 真实挂载表：除沙箱自建的 /、/tmp、/proc、/dev、/sys 之外，唯一可写挂载点
    # 就是本次 run 的 workdir。
    internal_points = {"/", "/tmp", "/proc", "/dev", "/sys"}
    host_writable = [
        point
        for point, options, _fstype in findings["mounts"]
        if "rw" in options.split(",")
        and point not in internal_points
        and not point.startswith(("/proc/", "/dev/", "/sys/"))
    ]
    assert host_writable == [str(p1_run.workdir)], findings["mounts"]
    mounted_paths = {point for point, _options, _fstype in findings["mounts"]}
    assert str(worker) in mounted_paths
    worker_options = next(o for p, o, _f in findings["mounts"] if p == str(worker))
    assert "ro" in worker_options.split(",")
    assert str(Path.home()) not in mounted_paths
    assert str(Path(helpers.__file__).resolve().parents[2]) not in mounted_paths
    assert _sha256(worker) == worker_before
    assert (p1_run.workdir / "chart_1.png").read_bytes() == ONE_PIXEL_PNG


def test_real_sandbox_runs_matplotlib_and_reports_the_artifact(p1_run: rs.ReportRun) -> None:
    code = (
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [3, 2, 1])\n"
        "plt.title('P1-33')\n"
        "plt.savefig('chart_1.png', dpi=80)\n"
    )
    result = _run(ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png"))

    assert result.error == "", result.stderr
    assert result.ok is True
    target = p1_run.workdir / "chart_1.png"
    assert target.is_file() and target.stat().st_size > 1000
    assert result.artifact == {
        "name": "chart_1.png",
        "size": target.stat().st_size,
        "sha256": _sha256(target),
    }
    # worker 的 stdout 只能是那一个 JSON 对象：执行器严格解析成功即证明这一点。
    assert result.worker_payload["status"] == "ok"


def test_real_sandbox_ode_check_uses_the_same_executor(p1_run: rs.ReportRun) -> None:
    script = (
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "def f(x, y):\n    return x**2 - y\n"
        "open('chart_1.png', 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n')\n"
    )
    _run(ce.execute_chart_code(script, run=p1_run, expected_png="chart_1.png"))

    matched = _run(ce.execute_ode_check(p1_run, "x**2 - y", points=ODE_POINTS))
    assert matched.backend == "bwrap-report"
    assert matched.checks is not None and matched.checks["ok"] is True
    assert matched.checks["finite"] is True
    assert matched.checks["points"] == 5
    assert matched.checks["max_abs_error"] < 1e-6

    shifted = _run(ce.execute_ode_check(p1_run, "x**2 - y + 1", points=ODE_POINTS))
    assert shifted.checks is not None and shifted.checks["ok"] is True
    assert shifted.checks["max_abs_error"] > 0.9  # 阈值判定归 P34

    non_finite = _run(ce.execute_ode_check(p1_run, "1e308 * x", points=ODE_POINTS))
    assert non_finite.checks is not None and non_finite.checks["ok"] is False
    assert non_finite.checks["finite"] is False
    # 原因由可信父 worker 给出（服务端诊断），不依赖具体措辞。
    assert non_finite.checks["reason"]


def test_ode_check_rejects_hostile_expression_and_bad_points(p1_run: rs.ReportRun) -> None:
    backend = _HostBackend()
    policy = _policy(backend)
    for bad in ("__import__('os').system('true')", "x.real", "", "   ", 5, None):
        with pytest.raises(json_store.InvalidInputError):
            _run(ce.execute_ode_check(p1_run, bad, points=ODE_POINTS, policy=policy))
    for bad_points in ([], [(1.0, 2.0)] * 33, [[1.0]], ["xy"], [(1.0, "y")], "points", None):
        with pytest.raises(json_store.InvalidInputError):
            _run(ce.execute_ode_check(p1_run, "x - y", points=bad_points, policy=policy))
    assert backend.spawns == []


def test_ode_mode_requires_a_script_with_f(p1_run: rs.ReportRun) -> None:
    _run(
        ce.execute_chart_code(
            "open('chart_1.png','wb').write(b'\\x89PNG\\r\\n\\x1a\\n')\n",
            run=p1_run,
            expected_png="chart_1.png",
        )
    )
    missing = _run(ce.execute_ode_check(p1_run, "x - y", points=ODE_POINTS))
    assert missing.checks is not None
    assert missing.checks["ok"] is False and missing.checks["finite"] is False
    assert missing.checks["reason"]
    assert ce.chart_failure_error(missing) is not None


def test_each_attempt_clears_the_previous_artifact(p1_run: rs.ReportRun) -> None:
    first_code = "open('chart_1.png','wb').write(b'\\x89PNG\\r\\n\\x1a\\nfirst')\n"
    first = _run(ce.execute_chart_code(first_code, run=p1_run, expected_png="chart_1.png"))
    first_record = ce.read_chart_attempt(p1_run, "chart_1.png")
    target = p1_run.workdir / "chart_1.png"
    assert first.artifact is not None and target.is_file()

    second = _run(
        ce.execute_chart_code(
            "print('no artifact this time')\n", run=p1_run, expected_png="chart_1.png"
        )
    )
    second_record = ce.read_chart_attempt(p1_run, "chart_1.png")

    assert second.artifact is None
    assert not target.exists(), "本次 attempt 之前的旧图被当成了本次产物"
    assert second_record is not None
    assert first_record is not None
    assert second_record["attempt_id"] != first_record["attempt_id"]
    assert second_record["cleared"] is True and second_record["finished"] is True


def test_attempt_record_is_written_outside_the_model_writable_mount(
    p1_run: rs.ReportRun,
) -> None:
    record_path = ce.attempt_record_path(p1_run, "chart_1.png")
    _run(
        ce.execute_chart_code(
            "import os\nprint(os.path.exists(%r))\nopen('chart_1.png','wb').write(b'\\x89PNG')\n"
            % str(record_path),
            run=p1_run,
            expected_png="chart_1.png",
        )
    )
    assert record_path.is_file()
    assert record_path.parent == p1_run.attempts_dir
    assert p1_run.attempts_dir.parent == p1_run.staging_dir
    assert p1_run.workdir != p1_run.staging_dir


def test_run_result_and_policy_contract_for_p34_and_p35(p1_run: rs.ReportRun) -> None:
    policy = ce.ReportExecutionPolicy()
    assert policy.for_ode().limits(ode=True).wall_clock_s == 30
    assert policy.limits().wall_clock_s == 60
    assert policy.max_pixels == 20_000_000
    assert policy.max_charts == 8
    for bad in ({"wall_clock_s": 0}, {"wall_clock_s": 10_000}, {"memory_mb": 0}, {"max_charts": 9}):
        with pytest.raises(ValueError):
            ce.ReportExecutionPolicy(**bad)

    # R5：只有"exit 0 且没有产物"不再是 chart 成功——假正例改成完整成功结构。
    artifact = {"name": "chart_1.png", "size": 12, "sha256": "a" * 64}
    result = ce.ChartExecutionResult(
        exit_code=0, timed_out=False, error="", mode="chart", status="ok", artifact=artifact
    )
    assert result.ok is True
    assert ce.chart_failure_error(result) is None
    incomplete = ce.ChartExecutionResult(exit_code=0, timed_out=False, error="", mode="chart")
    assert ce.chart_failure_error(incomplete) is not None
    assert (
        ce.chart_failure_error(ce.ChartExecutionResult(0, False, "", mode="chart", status="ok"))
        is not None
    )
    assert (
        ce.chart_failure_error(ce.ChartExecutionResult(0, True, "")).code is ErrorCode.CHART_FAILED
    )
    assert (
        ce.chart_failure_error(ce.ChartExecutionResult(0, False, "worker_failed")).code
        is ErrorCode.CHART_FAILED
    )
    assert (
        ce.chart_failure_error(ce.ChartExecutionResult(127, False, "sandbox_spawn_failed")).code
        is ErrorCode.SANDBOX_UNAVAILABLE
    )


def test_executor_has_no_host_subprocess_fallback(p1_run: rs.ReportRun, monkeypatch) -> None:
    """执行器里唯一的进程启动点是 run_bounded_spawn，且只能由 backend 提供 argv。"""
    calls: list[str] = []
    real_exec = asyncio.create_subprocess_exec
    real_shell = asyncio.create_subprocess_shell

    async def spy_exec(*argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(str(argv[0]))
        return await real_exec(*argv, **kwargs)

    async def forbidden_shell(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("报告执行器不允许 shell 执行")

    monkeypatch.setattr(ce.asyncio, "create_subprocess_exec", spy_exec)
    monkeypatch.setattr(ce.asyncio, "create_subprocess_shell", forbidden_shell)

    result = _run(
        ce.execute_chart_code(
            "open('chart_1.png','wb').write(b'\\x89PNG')\n",
            run=p1_run,
            expected_png="chart_1.png",
        )
    )
    assert result.error == ""
    assert calls and all("bwrap" in item for item in calls)


def test_reports_never_see_raw_model_output_in_the_error_field(p1_run: rs.ReportRun) -> None:
    noise = "P1-33-RAW-MODEL-NOISE-4f8a"
    result = _run(
        ce.execute_chart_code(
            f"import sys\nsys.stderr.write({noise!r})\nraise SystemExit(9)\n",
            run=p1_run,
            expected_png="chart_1.png",
        )
    )
    error = ce.chart_failure_error(result)
    assert error is not None
    assert noise in result.stderr  # 服务端诊断保留
    assert noise not in str(error) and noise not in repr(error)  # 对外投影不保留
    assert ri.validate_ode_expression("x - y") == "x - y"


# ---------------------------------------------------------------------------
# R2：服务端身份门（执行器侧）
# ---------------------------------------------------------------------------
def test_executor_revalidates_server_owned_staging_path(
    p1_run: rs.ReportRun, tmp_path: Path
) -> None:
    """伪造 staging_dir 的 run 必须被拒绝，且不落任何文件。"""
    from dataclasses import replace

    fake = tmp_path / "foreign-staging"
    (fake / "work").mkdir(parents=True)
    forged = replace(p1_run, staging_dir=fake)

    with pytest.raises((json_store.InvalidInputError, SubjectOperationError)):
        ce.plan_chart_request(forged, "chart_1.png")
    with pytest.raises((json_store.InvalidInputError, SubjectOperationError)):
        _run(
            ce.execute_chart_code(
                "open('chart_1.png','wb').write(b'x')",
                run=forged,
                expected_png="chart_1.png",
                policy=_policy(_HostBackend()),
            )
        )

    assert sorted(p.name for p in (fake / "work").iterdir()) == []
    assert not (fake / "attempts").exists()
    assert not (fake / "metadata.json").exists()


def test_plan_chart_request_is_pure_and_creates_no_directories(p1_run: rs.ReportRun) -> None:
    """计划是纯计算：不建 cache/home，也不写 attempt。"""
    before = sorted(p.name for p in p1_run.workdir.iterdir())
    request = ce.plan_chart_request(p1_run, "chart_1.png")

    assert request.env["HOME"] == str(p1_run.workdir / "home")
    assert sorted(p.name for p in p1_run.workdir.iterdir()) == before
    assert before == []
    assert not (p1_run.attempts_dir / "chart_1.png.json").exists()


def test_execute_requires_a_running_run(p1_run: rs.ReportRun) -> None:
    """写入/执行还要求合法 running 状态：已失败的 run 不能再执行。"""
    _publish_failing = _run(
        ce.execute_chart_code(
            "open('chart_1.png','wb').write(b'not-a-png')",
            run=p1_run,
            expected_png="chart_1.png",
            policy=_policy(_HostBackend()),
        )
    )
    assert _publish_failing is not None
    rs.fail_report_run(p1_run)
    with pytest.raises((json_store.InvalidInputError, SubjectOperationError)):
        _run(
            ce.execute_chart_code(
                "open('chart_1.png','wb').write(b'x')",
                run=p1_run,
                expected_png="chart_1.png",
                policy=_policy(_HostBackend()),
            )
        )


# ---------------------------------------------------------------------------
# R4：全程 deadline、leader 退出后的组清理、低预算控制协议
# ---------------------------------------------------------------------------
def test_wall_clock_also_covers_wait_after_output_eof(tmp_path: Path) -> None:
    """EOF 不结束墙钟约束：进程关掉两个 fd 后继续睡也要被 deadline 收掉。"""

    async def scenario():
        spawn = ce.SpawnCommand(
            (sys.executable, "-I", "-c", "import os,time;os.close(1);os.close(2);time.sleep(2)"),
            tmp_path,
            {},
        )
        limits = ce.ReportResourceLimits(1, 5, 128, 1000, 1024)
        return await asyncio.wait_for(ce.run_bounded_spawn(spawn, limits), timeout=4)

    result = _run(scenario())
    assert result.timed_out, "EOF 结束了 deadline，进程越过 1 秒时限后仍返回成功"
    assert result.exit_code == 124


def test_exited_leader_does_not_leave_descendant_alive(tmp_path: Path) -> None:
    """组长先退出：仍要按创建时保存的 PGID 清理后代。"""
    pidfile = tmp_path / "leader.pid"
    canary = tmp_path / "survivor"
    program = (
        "import subprocess,sys,os;open(%r,'w').write(str(os.getpid()));"
        "subprocess.Popen([sys.executable,'-I','-c',%r])"
    ) % (
        str(pidfile),
        "import time;time.sleep(2);open(%r,'w').write('survived')" % str(canary),
    )
    limits = ce.ReportResourceLimits(1, 5, 128, 1000, 1024)
    try:
        result = _run(
            ce.run_bounded_spawn(
                ce.SpawnCommand((sys.executable, "-I", "-c", program), tmp_path, {}), limits
            )
        )
        assert result.timed_out
        time.sleep(1.4)
        assert not canary.exists(), "组长先退出后 killpg 未清理后代"
    finally:
        if pidfile.exists():
            with contextlib.suppress(ProcessLookupError, OSError, ValueError):
                os.killpg(int(pidfile.read_text()), signal.SIGKILL)


def test_low_diagnostic_budget_keeps_the_control_envelope_parseable(p1_run: rs.ReportRun) -> None:
    """控制协议有独立下限：诊断预算再小，唯一 JSON envelope 也不能被截成半对象。"""
    policy = ce.ReportExecutionPolicy(backend=_HostBackend(), max_output_chars=200)
    code = (
        "import sys\n"
        "sys.stdout.write('diagnostic-noise-' * 200)\n"
        "open('chart_1.png','wb').write(b'\\x89PNG\\r\\n\\x1a\\n')\n"
    )
    result = _run(
        ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png", policy=policy)
    )

    assert result.error == "", result.stdout
    assert result.status == "ok"
    assert result.worker_payload is not None
    assert len(result.stdout) + len(result.stderr) <= policy.max_output_chars


def test_a_timed_out_run_does_not_affect_another_run(p1_subject) -> None:
    """一个 run 超时/清理不得影响另一个 run 的正常执行。"""
    first = rs.create_report_run(p1_subject.subject_id)
    second = rs.create_report_run(p1_subject.subject_id)
    limits = ce.ReportResourceLimits(1, 5, 128, 1000, 1024)
    timeout_spawn = ce.SpawnCommand(
        (sys.executable, "-I", "-c", "import time;time.sleep(30)"), first.workdir, {}
    )
    timed = _run(ce.run_bounded_spawn(timeout_spawn, limits))
    assert timed.timed_out

    ok = _run(
        ce.execute_chart_code(
            "open('chart_1.png','wb').write(b'\\x89PNG\\r\\n\\x1a\\n')",
            run=second,
            expected_png="chart_1.png",
            policy=_policy(_HostBackend()),
        )
    )
    assert ok.error == "" and ok.status == "ok"


# ---------------------------------------------------------------------------
# R5：worker 控制协议
# ---------------------------------------------------------------------------
BAD_WORKER_PAYLOADS = [
    {},
    {"schema": 1, "mode": "chart", "status": "unknown", "exit_code": 0, "timed_out": False},
    {"schema": 1, "mode": "chart", "status": "ok", "exit_code": True, "timed_out": False},
    {"schema": 1, "mode": "chart", "status": "ok", "exit_code": "RAW_PRIVATE", "timed_out": False},
    {"schema": 1, "mode": "ode", "status": "ok", "exit_code": 0, "timed_out": False},
    {"schema": 2, "mode": "chart", "status": "ok", "exit_code": 0, "timed_out": False},
    {"schema": 1, "mode": "chart", "status": "ok", "exit_code": 0, "timed_out": "false"},
    {"schema": 1, "mode": "chart", "status": "ok", "exit_code": 0, "timed_out": False},
    {
        "schema": 1,
        "mode": "chart",
        "status": "ok",
        "exit_code": 0,
        "timed_out": False,
        "expected_png": "chart_2.png",
        "artifact": {"name": "chart_2.png", "size": 1, "sha256": "a" * 64},
    },
    {
        "schema": 1,
        "mode": "chart",
        "status": "ok",
        "exit_code": 0,
        "timed_out": False,
        "expected_png": "chart_1.png",
        "artifact": {"name": "chart_1.png", "size": 0, "sha256": "a" * 64},
    },
    {
        "schema": 1,
        "mode": "chart",
        "status": "ok",
        "exit_code": 0,
        "timed_out": False,
        "expected_png": "chart_1.png",
        "artifact": {"name": "chart_1.png", "size": 4, "sha256": "Z" * 64},
    },
    {
        "schema": 1,
        "mode": "chart",
        "status": "ok",
        "exit_code": 0,
        "timed_out": False,
        "expected_png": "chart_1.png",
        "artifact": {"name": "chart_1.png", "size": 4, "sha256": "a" * 64, "extra": 1},
    },
]


@pytest.mark.parametrize("payload", BAD_WORKER_PAYLOADS)
def test_incomplete_or_wrong_typed_worker_protocol_is_failure(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    """缺字段/未知 status/错类型/矛盾产物：只能是失败，且不裸抛异常。"""

    class Boundary:
        name = "controlled"

        def build_spawn(self, request):  # type: ignore[no-untyped-def]
            return ce.SpawnCommand(("not-executed",), request.workdir, {})

    async def qualified(*args):  # type: ignore[no-untyped-def]
        return Boundary()

    async def returned(*args, **kwargs):  # type: ignore[no-untyped-def]
        return ce.ChartExecutionResult(0, False, "", stdout=json.dumps(payload))

    monkeypatch.setattr(ce, "_qualified_backend", qualified)
    monkeypatch.setattr(ce, "run_bounded_spawn", returned)
    try:
        result = _run(ce.execute_chart_code("pass", run=p1_run, expected_png="chart_1.png"))
    except SubjectOperationError:
        return
    except Exception as exc:  # noqa: BLE001
        pytest.fail("worker 协议错误裸抛 " + type(exc).__name__)
    assert ce.chart_failure_error(result) is not None, "坏 worker payload 仍被提升为成功"
    assert "RAW_PRIVATE" not in str(ce.chart_failure_error(result))


def test_complete_worker_payload_is_accepted(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完整合法 payload 正例（名字/正 size/64 位 hash 都对得上）。"""
    digest = hashlib.sha256(b"payload").hexdigest()
    payload = {
        "schema": 1,
        "mode": "chart",
        "status": "ok",
        "exit_code": 0,
        "timed_out": False,
        "expected_png": "chart_1.png",
        "artifact": {"name": "chart_1.png", "size": 7, "sha256": digest},
        "stdout_tail": "noise",
        "stderr_tail": "",
    }

    class Boundary:
        name = "controlled"

        def build_spawn(self, request):  # type: ignore[no-untyped-def]
            return ce.SpawnCommand(("not-executed",), request.workdir, {})

    async def qualified(*args):  # type: ignore[no-untyped-def]
        return Boundary()

    async def returned(*args, **kwargs):  # type: ignore[no-untyped-def]
        return ce.ChartExecutionResult(0, False, "", stdout=json.dumps(payload))

    monkeypatch.setattr(ce, "_qualified_backend", qualified)
    monkeypatch.setattr(ce, "run_bounded_spawn", returned)
    result = _run(ce.execute_chart_code("pass", run=p1_run, expected_png="chart_1.png"))

    assert result.status == "ok"
    assert result.artifact == payload["artifact"]
    assert ce.chart_failure_error(result) is None


def test_attempt_completion_is_cas_by_attempt_id(p1_run: rs.ReportRun) -> None:
    """旧 attempt 的收尾不能覆盖新代次（CAS on attempt_id）。"""
    old = ce.begin_chart_attempt(p1_run, "chart_1.png")
    new = ce.begin_chart_attempt(p1_run, "chart_1.png")
    assert ce.read_chart_attempt(p1_run, "chart_1.png")["generation"] > 1

    ce.finish_chart_attempt(old, ce.ChartExecutionResult(0, False, "", mode="chart", status="ok"))

    record = ce.read_chart_attempt(p1_run, "chart_1.png")
    assert record["attempt_id"] == new.attempt_id
    assert record["finished"] is False, "旧 attempt 收尾反向覆盖了新代次"


# ---------------------------------------------------------------------------
# R4/R7：真实 worker 内部有界（不是"外层捕获"）
# ---------------------------------------------------------------------------
ONE_PIXEL = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_worker_output_flood_is_drained_bounded_not_materialized(p1_run: rs.ReportRun) -> None:
    """真实隔离 worker：64MiB 地址空间下 128MiB 日志流必须有界读完而不是 OOM。"""
    policy = ce.ReportExecutionPolicy(memory_mb=64, cpu_seconds=5, wall_clock_s=8)
    control = _run(
        ce.execute_chart_code(
            "import os\nos.write(1,b'x'*4096)\nopen('chart_1.png','wb').write(%r)\n" % ONE_PIXEL,
            run=p1_run,
            expected_png="chart_1.png",
            policy=policy,
        )
    )
    assert control.ok and control.status == "ok", "相同 64MiB 策略的短输出正例必须先通过"

    code = (
        "import os\nfor i in range(32768): os.write(1,b'x'*4096)\n"
        "open('chart_1.png','wb').write(%r)\n" % ONE_PIXEL
    )
    result = _run(
        ce.execute_chart_code(code, run=p1_run, expected_png="chart_1.png", policy=policy)
    )

    assert result.ok and result.status == "ok", (
        "worker 先 communicate 整段日志导致自身 OOM/崩溃而非有界读取: "
        + repr((result.error, result.status, result.stdout, result.worker_payload))
    )
    assert len(result.stdout) + len(result.stderr) <= policy.max_output_chars


def test_worker_ode_flood_is_bounded(p1_run: rs.ReportRun) -> None:
    """ODE 的不可信子进程同样被有界读取（父 worker 不整段物化）。"""
    policy = ce.ReportExecutionPolicy(memory_mb=64, cpu_seconds=5, wall_clock_s=8)
    script = (
        "import os,sys\n"
        "if __name__ != '__main__':\n"
        "    for i in range(32768): os.write(1, b'y'*4096)\n"
        "    sys.exit(0)\n"
        "def f(x, y):\n"
        "    return x - y\n"
    )
    (p1_run.workdir / ce.CHART_SCRIPT_NAME).write_text(script, encoding="utf-8")
    result = _run(ce.execute_ode_check(p1_run, "x - y", points=ODE_POINTS, policy=policy))
    assert result.error == ""
    assert result.checks is not None
    assert result.checks["ok"] is False  # 洪泛把采样流打乱 → 拒绝（不是 OOM/成功）
    assert len(result.stdout) + len(result.stderr) <= policy.max_output_chars


def test_reader_failure_still_cleans_the_group(p1_run: rs.ReportRun, monkeypatch) -> None:
    """读取异常也必须清理自己拥有的进程组并 reap。"""
    canary = p1_run.workdir / "reader-error-canary.txt"
    program = (
        "import subprocess, sys, time\n"
        + "subprocess.Popen([sys.executable,'-I','-c',"
        + repr("import time;time.sleep(2);open(%r,'w').write('x')" % str(canary))
        + "])\n"
        + "time.sleep(30)\n"
    )
    limits = ce.ReportResourceLimits(1, 5, 128, 1000, 1024)

    async def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("reader exploded")

    monkeypatch.setattr(ce, "_pump", boom)
    try:
        _run(
            ce.run_bounded_spawn(
                ce.SpawnCommand((sys.executable, "-I", "-c", program), p1_run.workdir, {}),
                limits,
            )
        )
    except BaseException:  # noqa: BLE001 - 读取异常允许向上传播
        pass
    time.sleep(2.6)
    assert not canary.exists(), "读取异常后子进程仍在运行"


# Coordinator acceptance: remaining boundary failures, 2026-10-17.


def test_duplicate_worker_json_keys_are_not_last_value_wins():
    artifact = {"name": "chart_1.png", "size": 1, "sha256": "a" * 64}
    raw = (
        '{"schema":1,"mode":"chart","status":"script_failed","status":"ok","exit_code":0,"timed_out":false,"expected_png":"chart_1.png","artifact":'
        + json.dumps(artifact)
        + "}"
    )
    result, payload = ce._parse_worker_payload(
        ce.ChartExecutionResult(0, False, "", stdout=raw), expected_png="chart_1.png"
    )
    assert payload is None and result.error, "重复key控制对象被最后一个值覆盖而接受"


def test_contradictory_ode_envelope_is_not_success():
    raw = json.dumps(
        {
            "schema": 1,
            "mode": "ode",
            "status": "ode_failed",
            "exit_code": 0,
            "timed_out": False,
            "checks": {"ok": True, "finite": True, "max_abs_error": 0, "points": 5},
        }
    )
    result, payload = ce._parse_worker_payload(
        ce.ChartExecutionResult(0, False, "", stdout=raw), ode=True
    )
    assert payload is None and result.error, "ode_failed与ok:true同时出现仍通过结构门"


def test_same_run_concurrent_execution_cannot_overwrite_shared_script(p1_run, monkeypatch):
    run = p1_run
    observed = []

    async def boundary(current, *args, **kwargs):
        await asyncio.sleep(0.03)
        code = (current.workdir / ce.CHART_SCRIPT_NAME).read_text()
        observed.append(code)
        name = kwargs["spec"]["expected_png"]
        p = current.workdir / name
        p.write_bytes(ONE_PIXEL)
        return ce.ChartExecutionResult(
            0,
            False,
            "",
            status="ok",
            artifact={
                "name": name,
                "size": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            },
        )

    monkeypatch.setattr(ce, "_execute", boundary)

    async def scenario():
        return await asyncio.gather(
            ce.execute_chart_code("# FIRST", run=run, expected_png="chart_1.png"),
            ce.execute_chart_code("# SECOND", run=run, expected_png="chart_2.png"),
            return_exceptions=True,
        )

    results = asyncio.run(scenario())
    if all(isinstance(x, ce.ChartExecutionResult) for x in results):
        assert sorted(observed) == ["# FIRST", "# SECOND"], "两个执行都读到了后写的共享_chart.py"
    else:
        assert len(observed) == 1 and all(
            isinstance(x, (ce.ChartExecutionResult, SubjectOperationError)) for x in results
        )


@pytest.mark.parametrize("stop", ["timeout", "cancel", "reader_error"])
def test_exited_leader_cleanup_closes_pipes_before_return(tmp_path, monkeypatch, stop):
    """组长退出不等于管道关闭；各失败出口不能把transport遗留给已关闭loop。"""
    processes = []
    real_spawn = ce.asyncio.create_subprocess_exec
    ready = tmp_path / "child-ready"

    async def spy(*args, **kwargs):
        process = await real_spawn(*args, **kwargs)
        processes.append(process)
        return process

    async def broken_pump(*args, **kwargs):
        while not ready.exists() or processes[0].returncode is None:
            await asyncio.sleep(0.01)
        raise RuntimeError("reader exploded")

    monkeypatch.setattr(ce.asyncio, "create_subprocess_exec", spy)
    if stop == "reader_error":
        monkeypatch.setattr(ce, "_pump", broken_pump)
    child = f"import time;open({str(ready)!r},'w').write('ready');time.sleep(30)"
    program = f"import subprocess,sys;subprocess.Popen([sys.executable,'-I','-c',{child!r}])"
    spawn = ce.SpawnCommand((sys.executable, "-I", "-c", program), tmp_path, {})
    limits = ce.ReportResourceLimits(1, 5, 128, 1000, 1024)

    async def scenario():
        task = asyncio.create_task(ce.run_bounded_spawn(spawn, limits))
        if stop == "cancel":
            async with asyncio.timeout(3):
                while not ready.exists() or processes[0].returncode is None:
                    await asyncio.sleep(0.01)
            task.cancel()
        if stop == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        elif stop == "reader_error":
            with pytest.raises(RuntimeError, match="reader exploded"):
                await task
        else:
            assert (await task).timed_out
        # CPython transport状态只用作测试证据，生产使用StreamReader分块排空。
        assert all(processes[0]._transport.get_pipe_transport(i).is_closing() for i in (1, 2))

    _run(scenario())
