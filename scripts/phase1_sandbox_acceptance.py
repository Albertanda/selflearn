#!/usr/bin/env python3
"""S13 P1-50 gate: real bwrap report-sandbox acceptance.

This script runs the production chart executor with its default qualified bwrap
backend.  It does not inject a fake backend and does not fall back to the host.
Only the report-pipeline LLM is replaced with deterministic text; execution,
Matplotlib, PNG validation, ODE checking and publication remain real.

Run with::

    ./.venv/bin/python scripts/phase1_sandbox_acceptance.py
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
STAGE = REPO / ".phase1-evidence" / "stages" / "S13"
RESULT = STAGE / "sandbox_result.json"
REQUIRED_CASES = {
    "A_valid_png_cjk",
    "B_host_isolation",
    "C_network_isolation",
    "D_timeout_process_cleanup",
    "E_resource_limits",
    "F_ode_trusted_five_points",
    "G_report_failure_publication",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port_listener() -> tuple[socket.socket, int, list[int], threading.Event]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.settimeout(0.2)
    port = int(listener.getsockname()[1])
    counts: list[int] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except (socket.timeout, OSError):
                continue
            counts.append(1)
            try:
                connection.close()
            except OSError:
                pass

    threading.Thread(target=serve, daemon=True).start()
    return listener, port, counts, stop


def tree_hash(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--check-result", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.check_result is not None:
        return audit_result(args.check_result)
    global STAGE, RESULT
    if args.evidence_dir is not None:
        STAGE = args.evidence_dir.resolve()
    if args.evidence_dir is None:
        STAGE = REPO / ".phase1-evidence/runs/S13" / uuid.uuid4().hex
    RESULT = STAGE / "sandbox_result.json"
    if STAGE.exists() and any(STAGE.iterdir()):
        parser.error("use a new empty evidence directory; sealed evidence must stay unchanged")
    STAGE.mkdir(parents=True, exist_ok=True)
    if RESULT.exists():
        shutil.copy2(RESULT, STAGE / f"sandbox_result.previous-{int(time.time())}.json")
    started = now()
    report: dict = {
        "schema_version": 1,
        "stage_id": "S13",
        "unit_id": "P1-50",
        "status": "failed",
        "goal_met": False,
        "started_at_utc": started,
        "finished_at_utc": "",
        "cases": [],
        "commands": [],
        "limitations": [],
        "_self_check": args.self_check,
    }

    def add_case(case_id: str, expected: str, actual: dict, ok: bool) -> None:
        report["cases"].append(
            {
                "id": case_id,
                "expected": expected,
                "actual": actual,
                "status": "passed" if ok else "failed",
                "evidence_refs": ["s13-p50-gate"],
            }
        )

    temp_root = Path(tempfile.mkdtemp(prefix="s13-p50-home-"))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from scripts.phase1_verify import clean_env

    env = clean_env(temp_root)
    env.update(
        {
            "HOME": str(temp_root / "home"),
            "XDG_CONFIG_HOME": str(temp_root / "config"),
            "XDG_DATA_HOME": str(temp_root / "data"),
            "XDG_CACHE_HOME": str(temp_root / "cache"),
            "TMPDIR": str(temp_root / "tmp"),
            "DEEPTUTOR_CODEBUDDY_AUTH_FILE": str(temp_root / "missing-auth.json"),
            "DEEPTUTOR_HOME": str(temp_root / "deeptutor-home"),
            "PYTHONPYCACHEPREFIX": str(temp_root / "pycache"),
            "NO_COLOR": "1",
        }
    )
    for key in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "DEEPTUTOR_HOME",
        "PYTHONPYCACHEPREFIX",
    ):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    os.environ.clear()
    os.environ.update(env)
    stage_log = StageLog(
        STAGE / "execution.log", [sys.executable, str(Path(__file__)), *(argv or [])], REPO
    )
    stage_log.start()
    artifacts: list[dict] = []
    try:
        if args.self_check:
            add_case("self_check", "script imports and lints", {"argv": sys.argv}, True)
            report["status"], report["goal_met"] = "partial", False
            return finish(report, stage_log, artifacts)
        # Set the temporary roots and remove provider credentials before any
        # application import.  The helper re-applies PathService isolation.
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from tests.phase1 import helpers

        with helpers.isolated_runtime(temp_root / "runtime", guard_network=True) as admin_root:
            from deeptutor.services.pdf import chart_executor as ce
            from deeptutor.services.pdf import chart_validation as cv
            from deeptutor.services.pdf import report as report_mod
            from deeptutor.services.pdf import report_store as rs
            from deeptutor.subjects.errors import ErrorCode, SubjectOperationError

            if shutil.which("bwrap") is None:
                report["status"] = "blocked_environment"
                report["limitations"].append(
                    "bwrap is not installed; required OS sandbox proof cannot run."
                )
                return finish(report, stage_log, artifacts)
            if not (REPO / "tools" / "fonts" / "msyh.ttc").is_file():
                report["status"] = "blocked_environment"
                report["limitations"].append("CJK font tools/fonts/msyh.ttc is missing.")
                return finish(report, stage_log, artifacts)

            if not (REPO / "tools/bin/typst").is_file():
                report["status"] = "blocked_environment"
                report["limitations"].append(
                    "Typst is missing; required publication proof cannot run."
                )
                return finish(report, stage_log, artifacts)
            backend = ce.select_report_backend()
            healthy = asyncio.run(backend.health())
            if not healthy[0]:
                report["status"] = "blocked_environment"
                report["limitations"].append(
                    "bwrap qualification/namespace health failed: " + str(healthy[1])
                )
                return finish(report, stage_log, artifacts)
            subject_a = helpers.make_subject(admin_root, "S13-A")
            subject_b = helpers.make_subject(admin_root, "S13-B")
            host_root = Path(tempfile.mkdtemp(prefix="s13-host-", dir=str(REPO.parent)))
            host_secret = host_root / "fake-host-secret.txt"
            host_canary = host_root / "host-canary.txt"
            host_secret.write_text("FAKE-HOST-SECRET-DO-NOT-READ\n", encoding="utf-8")
            host_canary.write_text("HOST-CANARY-UNCHANGED\n", encoding="utf-8")
            env_secret_name = "S13_FAKE_ENV_SECRET"
            env_secret_value = "s13-fake-env-secret-value"
            os.environ[env_secret_name] = env_secret_value

            def new_run(subject_id: str):
                return rs.create_report_run(subject_id)

            def dispose(run) -> None:
                try:
                    rs.fail_report_run(run, detail="S13 acceptance probe")
                except BaseException:
                    pass

            # A: real Matplotlib PNG + CJK font + real validation + mount vector.
            run_a = new_run(subject_a.subject_id)
            try:
                cjk = (
                    "import matplotlib\nmatplotlib.use('Agg')\n"
                    "import matplotlib.pyplot as plt\n"
                    "from matplotlib import font_manager\n"
                    f"font_manager.fontManager.addfont({str(REPO / 'tools/fonts/msyh.ttc')!r})\n"
                    "plt.rcParams['font.family'] = 'Microsoft YaHei'\n"
                    "fig, ax = plt.subplots(figsize=(4, 3))\n"
                    "ax.plot([1, 2, 3], [3, 1, 2])\n"
                    "ax.set_title('中文图表验收')\n"
                    "fig.savefig('chart_1.png', dpi=100)\n"
                )
                worker = Path(ce.__file__).with_name(ce.WORKER_FILENAME)
                worker_before = sha256(worker)
                cjk += (
                    "import json, os\n"
                    "from matplotlib.ft2font import FT2Font\n"
                    f"chars = FT2Font({str(REPO / 'tools/fonts/msyh.ttc')!r}).get_charmap()\n"
                    "observed = {'glyphs_present': all(ord(c) in chars for c in '中文图表验收'), 'env_keys': sorted(os.environ)}\n"
                    "mounts = []\n"
                    "for line in open('/proc/self/mountinfo'):\n"
                    "    fields = line.split(); sep = fields.index('-')\n"
                    "    mounts.append([fields[4], fields[5], fields[sep+1]])\n"
                    "observed['mounts'] = mounts\n"
                    "try:\n"
                    f"    handle = open({str(worker)!r}, 'ab'); handle.close()\n"
                    "    observed['worker_open_writable'] = True\n"
                    "except OSError:\n"
                    "    observed['worker_open_writable'] = False\n"
                    "open('isolation.json', 'w').write(json.dumps(observed))\n"
                )
                request = ce.plan_chart_request(run_a, "chart_1.png")
                backend = ce.select_report_backend()
                proof = backend.isolation_proof().as_dict()
                healthy = asyncio.run(backend.health())
                result = asyncio.run(
                    ce.execute_chart_code(cjk, run=run_a, expected_png="chart_1.png")
                )
                entry = cv.validate_chart_output(run_a, "chart_1.png")
                from PIL import Image

                target = run_a.workdir / "chart_1.png"
                with Image.open(target) as image:
                    width, height = image.size
                    image.verify()
                writable = [m for m in request.mounts if not m.read_only]
                mount_ok = len(writable) == 1 and writable[0].host_path == str(run_a.workdir)
                no_sensitive_mount = all(
                    (not m.read_only)
                    or not str(Path(m.host_path).resolve()).startswith(str(REPO / "data"))
                    for m in request.mounts
                )
                observed_mounts = json.loads((run_a.workdir / "isolation.json").read_text())
                internal_points = {"/", "/tmp", "/proc", "/dev", "/sys"}
                host_writable = [
                    point
                    for point, options, _ in observed_mounts["mounts"]
                    if "rw" in options.split(",")
                    and point not in internal_points
                    and not point.startswith(("/proc/", "/dev/", "/sys/"))
                ]
                worker_ro = any(
                    point == str(worker) and "ro" in options.split(",")
                    for point, options, _ in observed_mounts["mounts"]
                )
                actual_mounts_ok = (
                    host_writable == [str(run_a.workdir)]
                    and worker_ro
                    and observed_mounts["worker_open_writable"] is False
                    and sha256(worker) == worker_before
                )
                env_ok = set(observed_mounts["env_keys"]) - set(request.env) <= {"PWD"}
                cjk_ok = observed_mounts["glyphs_present"] and not any(
                    token in result.stderr for token in ("Glyph", "missing from font")
                )
                a_ok = (
                    result.ok
                    and result.status == "ok"
                    and result.backend == "bwrap-report"
                    and all(proof.values())
                    and healthy[0]
                    and mount_ok
                    and actual_mounts_ok
                    and env_ok
                    and no_sensitive_mount
                    and entry["size"] == result.artifact["size"]
                    and entry["sha256"] == result.artifact["sha256"]
                    and width > 0
                    and height > 0
                    and cjk_ok
                )
                add_case(
                    "A_valid_png_cjk",
                    "real bwrap Matplotlib PNG with CJK glyphs, strict PNG validation, attempt binding, only current workdir writable",
                    {
                        "result_ok": result.ok,
                        "status": result.status,
                        "backend": result.backend,
                        "proof": proof,
                        "healthy": healthy,
                        "writable_mounts": [m.host_path for m in writable],
                        "sensitive_mount_absent": no_sensitive_mount,
                        "actual_mounts_ok": actual_mounts_ok,
                        "worker_sha256": worker_before,
                        "observed_isolation": observed_mounts,
                        "glyphs_present": observed_mounts["glyphs_present"],
                        "env_whitelist_ok": env_ok,
                        "png": {
                            "width": width,
                            "height": height,
                            "size": entry["size"],
                            "sha256": entry["sha256"],
                        },
                        "cjk_stderr_clean": cjk_ok,
                        "stderr": result.stderr[-1000:],
                    },
                    a_ok,
                )
                artifacts.append(
                    {
                        "case": "A",
                        "png": target.name,
                        "size": target.stat().st_size,
                        "sha256": sha256(target),
                    }
                )
            finally:
                dispose(run_a)

            # B: host secrets, other subject/run, absolute/.. /symlink writes, env secret.
            other_run = new_run(subject_a.subject_id)
            other_subject_run = new_run(subject_b.subject_id)
            (other_run.workdir / "marker.txt").write_text("FAKE-OTHER-RUN")
            (other_subject_run.workdir / "marker.txt").write_text("FAKE-OTHER-SUBJECT")
            run_b = new_run(subject_a.subject_id)
            try:
                escape_host = (host_root / f"escape-{uuid.uuid4().hex}.txt").resolve()
                dotdot_target = run_b.workdir / ".." / f"dotdot-{uuid.uuid4().hex}.txt"
                public_target = run_b.public_dir / f"rogue-{uuid.uuid4().hex}.txt"
                probe_code = (
                    "import json, os, pathlib\n"
                    "results = {}\n"
                    "def attempt(name, fn):\n"
                    "    try:\n"
                    "        fn()\n"
                    "        results[name] = 'allowed'\n"
                    "    except BaseException as exc:\n"
                    "        results[name] = 'denied:' + type(exc).__name__\n"
                    f"attempt('host_secret_read', lambda: open({str(host_secret)!r}).read())\n"
                    f"attempt('other_subject_read', lambda: open({str(other_subject_run.workdir / 'marker.txt')!r}).read())\n"
                    f"attempt('other_run_read', lambda: open({str(other_run.workdir / 'marker.txt')!r}).read())\n"
                    f"attempt('absolute_write', lambda: open({str(host_canary)!r}, 'w').write('changed'))\n"
                    f"attempt('dotdot_write', lambda: open({str(dotdot_target)!r}, 'w').write('x'))\n"
                    f"pathlib.Path('link-to-host').symlink_to({str(host_canary)!r})\n"
                    "attempt('symlink_write', lambda: open('link-to-host', 'w').write('changed'))\n"
                    f"pathlib.Path('link-to-secret').symlink_to({str(host_secret)!r})\n"
                    "attempt('symlink_read', lambda: open('link-to-secret').read())\n"
                    f"attempt('escaped_absolute_write', lambda: open({str(escape_host)!r}, 'w').write('x'))\n"
                    f"attempt('public_write', lambda: open({str(public_target)!r}, 'w').write('x'))\n"
                    f"results['fake_env_secret'] = os.environ.get({env_secret_name!r})\n"
                    f"open('probe.json', 'w', encoding='utf-8').write(json.dumps(results))\n"
                )
                canary_before = sha256(host_canary)
                secret_before = sha256(host_secret)
                secret_before_text = host_secret.read_text(encoding="utf-8")
                result = asyncio.run(
                    ce.execute_chart_code(probe_code, run=run_b, expected_png="chart_1.png")
                )
                probe = json.loads((run_b.workdir / "probe.json").read_text(encoding="utf-8"))
                canary_ok = (
                    sha256(host_canary) == canary_before
                    and host_canary.read_text() == "HOST-CANARY-UNCHANGED\n"
                )
                secret_ok = (
                    sha256(host_secret) == secret_before
                    and host_secret.read_text() == secret_before_text
                )
                no_public = (
                    not public_target.exists()
                    and not dotdot_target.exists()
                    and not escape_host.exists()
                )
                escape_host_absent = not escape_host.exists()
                env_ok = probe.get("fake_env_secret") is None
                b_ok = (
                    result.status in {"no_artifact", "script_failed"}
                    and canary_ok
                    and secret_ok
                    and no_public
                    and escape_host_absent
                    and env_ok
                    and all(
                        probe.get(k, "").startswith("denied:")
                        for k in (
                            "host_secret_read",
                            "other_subject_read",
                            "other_run_read",
                            "symlink_read",
                            "absolute_write",
                            "symlink_write",
                            "escaped_absolute_write",
                            "public_write",
                        )
                    )
                    and probe.get("absolute_write", "").startswith("denied:")
                    and probe.get("symlink_write", "").startswith("denied:")
                )
                add_case(
                    "B_host_isolation",
                    "fake host secret/other run/other subject/absolute, .., symlink/public writes cannot alter host; fake env secret never enters worker",
                    {
                        "probe": probe,
                        "canary_unchanged": canary_ok,
                        "host_secret_unchanged": secret_ok,
                        "public_artifact_absent": no_public,
                        "escape_host_absent": escape_host_absent,
                        "fake_env_secret_none": env_ok,
                        "worker_status": result.status,
                    },
                    b_ok,
                )
            finally:
                for run in (run_b, other_run, other_subject_run):
                    dispose(run)

            # C: host listener has a real positive; sandbox cannot reach it.
            listener, port, counts, stop = free_port_listener()
            host_positive = False
            try:
                with helpers.block_external_network(allow_endpoints=[("127.0.0.1", port)]):
                    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
                        sock.sendall(b"hello")
                deadline = time.monotonic() + 2
                while not counts and time.monotonic() < deadline:
                    time.sleep(0.01)
                host_positive = bool(counts)
                before_count = len(counts)
                run_c = new_run(subject_a.subject_id)
                try:
                    network_code = (
                        "import json, socket\n"
                        f"try:\n"
                        f"    s = socket.create_connection(('127.0.0.1', {port}), timeout=2)\n"
                        f"except BaseException as exc:\n"
                        f"    connected, detail = False, type(exc).__name__\n"
                        f"else:\n"
                        f"    connected, detail = True, 'connected'\n"
                        f"    s.close()\n"
                        f"open('network.json', 'w', encoding='utf-8').write(json.dumps({{'connected': connected, 'detail': detail}}))\n"
                    )
                    result = asyncio.run(
                        ce.execute_chart_code(network_code, run=run_c, expected_png="chart_1.png")
                    )
                    data = json.loads((run_c.workdir / "network.json").read_text(encoding="utf-8"))
                    time.sleep(0.2)
                    after_count = len(counts)
                    c_ok = (
                        host_positive
                        and before_count > 0
                        and after_count == before_count
                        and data.get("connected") is False
                    )
                    add_case(
                        "C_network_isolation",
                        "controlled localhost host request succeeds; the sandbox's same endpoint attempt increments the listener by 0",
                        {
                            "host_positive": host_positive,
                            "count_before_sandbox": before_count,
                            "count_after_sandbox": after_count,
                            "sandbox": data,
                            "worker_status": result.status,
                        },
                        c_ok,
                    )
                finally:
                    dispose(run_c)
            finally:
                stop.set()
                listener.close()

            # D: wall timeout kills the bounded process group and delayed child.
            run_d = new_run(subject_a.subject_id)
            unrelated = subprocess.Popen(["sleep", "30"])
            observed: list[dict] = []
            monitor_stop = threading.Event()

            def monitor() -> None:
                import psutil

                while not monitor_stop.is_set():
                    try:
                        for process in psutil.process_iter(["pid", "cmdline"]):
                            cmdline = process.info.get("cmdline") or []
                            joined = " ".join(cmdline)
                            if str(run_d.workdir) in joined and (
                                "bwrap" in joined or "chart_worker" in joined
                            ):
                                try:
                                    pgid = os.getpgid(process.info["pid"])
                                except OSError:
                                    continue
                                for candidate in [process, *process.children(recursive=True)]:
                                    try:
                                        entry = {
                                            "pid": candidate.pid,
                                            "pgid": os.getpgid(candidate.pid),
                                            "created": candidate.create_time(),
                                        }
                                        if entry not in observed:
                                            observed.append(entry)
                                    except (OSError, psutil.Error):
                                        pass
                    except BaseException:
                        pass
                    time.sleep(0.02)

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()
            delayed_name = f"delayed-{uuid.uuid4().hex}.txt"
            try:
                grandchild = (
                    "import time; open('grandchild-started', 'w').write('yes'); time.sleep(7); open("
                    + repr(delayed_name)
                    + ", 'w').write('escaped')"
                )
                child = (
                    "import subprocess, sys, time; open('child-started', 'w').write('yes'); subprocess.Popen([sys.executable, '-c', "
                    + repr(grandchild)
                    + "]); time.sleep(30)"
                )
                timeout_code = (
                    "import subprocess, sys, time\nopen('parent-started', 'w').write('yes')\nsubprocess.Popen([sys.executable, '-c', "
                    + repr(child)
                    + "])\nwhile True: time.sleep(0.1)\n"
                )
                policy = ce.ReportExecutionPolicy(wall_clock_s=5, cpu_seconds=10, memory_mb=512)
                result = asyncio.run(
                    ce.execute_chart_code(
                        timeout_code, run=run_d, expected_png="chart_1.png", policy=policy
                    )
                )
                time.sleep(7.2)
                monitor_stop.set()
                monitor_thread.join(timeout=2)
                delayed = (run_d.workdir / delayed_name).exists()
                alive = []
                import psutil

                for item in observed:
                    try:
                        process = psutil.Process(item["pid"])
                        if (
                            process.create_time() == item["created"]
                            and process.is_running()
                            and process.status() != psutil.STATUS_ZOMBIE
                        ):
                            alive.append(item)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                unrelated_alive = unrelated.poll() is None
                started_markers = all(
                    (run_d.workdir / name).is_file()
                    for name in ("parent-started", "child-started", "grandchild-started")
                )
                d_ok = (
                    result.timed_out
                    and started_markers
                    and not delayed
                    and not alive
                    and unrelated_alive
                    and len(observed) >= 4
                )
                add_case(
                    "D_timeout_process_cleanup",
                    "short wall timeout kills the bounded child/descendant group; delayed host canary absent; unrelated process untouched",
                    {
                        "started_markers": started_markers,
                        "timed_out": result.timed_out,
                        "worker_status": result.status,
                        "host_pids": observed,
                        "alive_after": alive,
                        "delayed_canary_absent": not delayed,
                        "unrelated_alive": unrelated_alive,
                    },
                    d_ok,
                )
            finally:
                monitor_stop.set()
                monitor_thread.join(timeout=2)
                unrelated.terminate()
                try:
                    unrelated.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    unrelated.kill()
                    unrelated.wait(timeout=5)
                dispose(run_d)

            # E: real hard limits, small legal control, bounded failures.
            run_e = new_run(subject_a.subject_id)
            limits_policy = ce.ReportExecutionPolicy(
                wall_clock_s=10,
                cpu_seconds=5,
                memory_mb=128,
                max_artifact_bytes=4096,
                max_output_chars=2000,
            )
            try:

                def execute(code: str) -> object:
                    return asyncio.run(
                        ce.execute_chart_code(
                            code, run=run_e, expected_png="chart_1.png", policy=limits_policy
                        )
                    )

                limits_code = (
                    "import json, resource\n"
                    "data = {name: list(resource.getrlimit(getattr(resource, name))) for name in ('RLIMIT_CPU','RLIMIT_AS','RLIMIT_FSIZE','RLIMIT_CORE')}\n"
                    "open('limits.json', 'w', encoding='utf-8').write(json.dumps(data))\n"
                )
                legal = execute(limits_code)
                limits = json.loads((run_e.workdir / "limits.json").read_text(encoding="utf-8"))
                expected_limits = {
                    "RLIMIT_CPU": [5, 5],
                    "RLIMIT_AS": [128 * 1024 * 1024, 128 * 1024 * 1024],
                    "RLIMIT_FSIZE": [4096, 4096],
                    "RLIMIT_CORE": [0, 0],
                }
                memory_code = (
                    "import json\ntry:\n    block = bytearray(192 * 1024 * 1024)\n"
                    "except MemoryError:\n    open('memory-error.json', 'w').write(json.dumps({'error': 'MemoryError'}))\n    raise SystemExit(9)\n"
                )
                memory = execute(memory_code)
                file_code = (
                    "with open('oversize.bin', 'wb') as handle:\n"
                    "    written = handle.write(b'x' * 8192)\n"
                    "    handle.flush()\n"
                    "if written != 8192:\n"
                    "    raise SystemExit(7)\n"
                )
                file_result = execute(file_code)
                flood_code = "for _ in range(3000):\n    print('x' * 200)\nprint('FLOOD_DONE')\n"
                flood = execute(flood_code)
                tail = str((flood.worker_payload or {}).get("stdout_tail") or "")
                e_ok = (
                    legal.status == "no_artifact"
                    and limits == expected_limits
                    and memory.status == "script_failed"
                    and memory.exit_code != 0
                    and (run_e.workdir / "memory-error.json").is_file()
                    and file_result.status == "script_failed"
                    and file_result.exit_code != 0
                    and (
                        not (run_e.workdir / "oversize.bin").exists()
                        or (run_e.workdir / "oversize.bin").stat().st_size <= 4096
                    )
                    and len(tail) <= 600
                    and flood.status == "no_artifact"
                    and (flood.worker_payload or {}).get("exit_code") == 0
                    and tail.rstrip().endswith("FLOOD_DONE")
                )
                add_case(
                    "E_resource_limits",
                    "RLIMIT_CPU/AS/FSIZE/CORE match policy; small legal workload succeeds; memory/file overflow fail bounded; flood output tail <=600",
                    {
                        "legal_status": legal.status,
                        "limits": limits,
                        "expected_limits": expected_limits,
                        "memory_status": memory.status,
                        "memory_error_observed": (run_e.workdir / "memory-error.json").is_file(),
                        "file_status": file_result.status,
                        "file_exit_code": file_result.exit_code,
                        "oversize_size": (run_e.workdir / "oversize.bin").stat().st_size
                        if (run_e.workdir / "oversize.bin").exists()
                        else None,
                        "flood_status": flood.status,
                        "flood_tail_chars": len(tail),
                    },
                    e_ok,
                )
            finally:
                dispose(run_e)

            # F: trusted-parent five-point ODE plus wrong/non-finite negatives.
            run_f = new_run(subject_a.subject_id)
            try:
                ode_good = (
                    "import matplotlib\nmatplotlib.use('Agg')\ndef f(x, y):\n    return x**2 - y\n"
                )
                asyncio.run(ce.execute_chart_code(ode_good, run=run_f, expected_png="chart_1.png"))
                passed = asyncio.run(cv.check_ode_numeric(run_f, "x**2 - y"))
                wrong = "def f(x, y):\n    return x + y\n"
                asyncio.run(ce.execute_chart_code(wrong, run=run_f, expected_png="chart_1.png"))
                wrong_error = None
                try:
                    asyncio.run(cv.check_ode_numeric(run_f, "x**2 - y"))
                except SubjectOperationError as exc:
                    wrong_error = exc.code.value
                nonfinite = "def f(x, y):\n    return float('nan')\n"
                asyncio.run(ce.execute_chart_code(nonfinite, run=run_f, expected_png="chart_1.png"))
                nonfinite_error = None
                try:
                    asyncio.run(cv.check_ode_numeric(run_f, "x**2 - y"))
                except SubjectOperationError as exc:
                    nonfinite_error = exc.code.value
                f_ok = (
                    passed.get("status") == rs.VERIFICATION_PASSED
                    and passed.get("points") == 5
                    and wrong_error == ErrorCode.CHART_FAILED.value
                    and nonfinite_error == ErrorCode.CHART_FAILED.value
                )
                add_case(
                    "F_ode_trusted_five_points",
                    "real backend ODE passes at five points; wrong and non-finite samples are rejected by the trusted parent",
                    {
                        "passed": passed,
                        "wrong_error": wrong_error,
                        "nonfinite_error": nonfinite_error,
                    },
                    f_ok,
                )
                artifacts.append({"case": "F", "ode_checks": passed})
            finally:
                dispose(run_f)

            # G: a real chart failure enters report.generate_report, publishes no
            # PDF/URL, leaves the old report untouched and releases active state.
            original_llm = report_mod._llm
            try:

                async def fake_llm(prompt: str, system: str) -> str:
                    if "## 报告题目" in prompt:
                        if "S13 baseline" in prompt:
                            return "# 基线报告\n\n正文。\n"
                        return "# 失败报告\n{CHART:失败图}\n"
                    return json.dumps({"code": "raise RuntimeError('intentional chart failure')\n"})

                report_mod._llm = fake_llm
                first = asyncio.run(
                    report_mod.generate_report(
                        subject_a.subject_id, title="S13 baseline", requirements="基线报告"
                    )
                )
                old_manifest = rs.resolve_report_for_review(subject_a.subject_id)
                old_hash = tree_hash(old_manifest.public_dir)
                failed_before = sum(
                    1
                    for path in (subject_a.root / "_report_runs").glob("*/metadata.json")
                    if json.loads(path.read_text(encoding="utf-8")).get("status") == "failed"
                )
                failure = None
                try:
                    asyncio.run(
                        report_mod.generate_report(
                            subject_a.subject_id, title="S13 failure", requirements="失败报告"
                        )
                    )
                except SubjectOperationError as exc:
                    failure = exc.code.value
                new_manifest = rs.resolve_report_for_review(subject_a.subject_id)
                new_hash = tree_hash(new_manifest.public_dir)
                public_dirs = (
                    [p for p in (subject_a.outputs / "reports").iterdir() if p.is_dir()]
                    if (subject_a.outputs / "reports").is_dir()
                    else []
                )
                failed_metadata = []
                for path in (subject_a.root / "_report_runs").glob("*/metadata.json"):
                    try:
                        metadata = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if metadata.get("status") == "failed":
                        failed_metadata.append(metadata)
                g_ok = (
                    first.get("status") == "completed"
                    and str(first.get("url", "")).startswith(
                        f"/api/outputs/subjects/{subject_a.subject_id}/reports/"
                    )
                    and failure == ErrorCode.CHART_FAILED.value
                    and old_hash == new_hash
                    and new_manifest.report_id == old_manifest.report_id
                    and len(public_dirs) == 1
                    and failed_metadata
                    and len(failed_metadata) > failed_before
                    and all(item.get("files") == [] for item in failed_metadata)
                    and rs.active_report_runs() == ()
                )
                add_case(
                    "G_report_failure_publication",
                    "real report pipeline publishes a Typst PDF on success; a real chart failure yields no new PDF/URL, old bytes unchanged and a failed manifest with active state released",
                    {
                        "first": {"status": first.get("status"), "url": first.get("url")},
                        "failure": failure,
                        "old_hash_unchanged": old_hash == new_hash,
                        "public_dirs": len(public_dirs),
                        "failed_metadata_count": len(failed_metadata),
                        "failed_before": failed_before,
                        "active_runs": rs.active_report_runs(),
                    },
                    g_ok,
                )
                artifacts.append(
                    {
                        "case": "G",
                        "old_report_id": old_manifest.report_id,
                        "public_dirs": len(public_dirs),
                    }
                )
            finally:
                report_mod._llm = original_llm
    except BaseException as exc:  # noqa: BLE001 - record the failure, never fake success
        report["status"] = "failed"
        report["limitations"].append(f"gate raised {type(exc).__name__}: {exc}")
        add_case(
            "gate_exception",
            "all required OS scenarios complete without an unhandled exception",
            {"error": f"{type(exc).__name__}: {exc}"},
            False,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        if "host_root" in locals():
            shutil.rmtree(host_root, ignore_errors=True)

    return finish(report, stage_log, artifacts)


class StageLog:
    def __init__(self, path: Path, argv: list[str], cwd: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.argv = argv
        self.cwd = cwd
        self.start_line = 0
        self.start_time = ""

    def start(self) -> None:
        import fcntl

        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            with self.path.open("r", encoding="utf-8") as reader:
                before = sum(1 for _ in reader)
            self.start_time = now()
            text = (
                "-" * 78 + "\n"
                f"[s13-p50-gate] {self.start_time}\n"
                f"cwd: {self.cwd}\n"
                f"argv: {json.dumps(self.argv, ensure_ascii=False)}\n"
                f"$ {' '.join(self.argv)}\n"
            )
            handle.write(text)
            handle.flush()
            self.start_line = before + 2
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def finish(self, text: str, code: int) -> int:
        import fcntl

        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(text + f"exit={code}\n")
            handle.flush()
            with self.path.open("r", encoding="utf-8") as reader:
                end = sum(1 for _ in reader)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return end


def observation_valid(case_id: str, actual: object) -> bool:
    """Recheck observations, rather than trusting a case's supplied status."""
    if not isinstance(actual, dict) or not actual:
        return False
    try:
        if case_id == "A_valid_png_cjk":
            return (
                actual["result_ok"] is True
                and actual["backend"] == "bwrap-report"
                and len(actual["proof"]) == 5
                and all(actual["proof"].values())
                and actual["healthy"][0] is True
                and actual["actual_mounts_ok"] is True
                and actual["env_whitelist_ok"] is True
                and actual["glyphs_present"] is True
                and actual["cjk_stderr_clean"] is True
                and actual["png"]["width"] > 0
                and actual["png"]["height"] > 0
            )
        if case_id == "B_host_isolation":
            keys = (
                "host_secret_read",
                "other_subject_read",
                "other_run_read",
                "symlink_read",
                "absolute_write",
                "symlink_write",
                "escaped_absolute_write",
                "public_write",
            )
            return all(actual["probe"][k].startswith("denied:") for k in keys) and all(
                actual[k] is True
                for k in (
                    "canary_unchanged",
                    "host_secret_unchanged",
                    "public_artifact_absent",
                    "escape_host_absent",
                    "fake_env_secret_none",
                )
            )
        if case_id == "C_network_isolation":
            return (
                actual["host_positive"] is True
                and actual["count_before_sandbox"] > 0
                and actual["count_before_sandbox"] == actual["count_after_sandbox"]
                and actual["sandbox"]["connected"] is False
            )
        if case_id == "D_timeout_process_cleanup":
            return (
                all(
                    actual[k] is True
                    for k in (
                        "started_markers",
                        "timed_out",
                        "delayed_canary_absent",
                        "unrelated_alive",
                    )
                )
                and len(actual["host_pids"]) >= 4
                and actual["alive_after"] == []
            )
        if case_id == "E_resource_limits":
            return (
                actual["legal_status"] == "no_artifact"
                and actual["limits"] == actual["expected_limits"]
                and actual["memory_status"] == "script_failed"
                and actual["memory_error_observed"] is True
                and actual["file_status"] == "script_failed"
                and actual["file_exit_code"] != 0
                and actual["oversize_size"] <= 4096
                and actual["flood_status"] == "no_artifact"
                and 0 < actual["flood_tail_chars"] <= 600
            )
        if case_id == "F_ode_trusted_five_points":
            return (
                actual["passed"]["status"] == "passed"
                and actual["passed"]["points"] == 5
                and actual["wrong_error"] == actual["nonfinite_error"] == "chart_failed"
            )
        if case_id == "G_report_failure_publication":
            return (
                actual["first"]["status"] == "completed"
                and actual["failure"] == "chart_failed"
                and actual["old_hash_unchanged"] is True
                and actual["public_dirs"] == 1
                and actual["failed_metadata_count"] > actual["failed_before"]
                and actual["active_runs"] in ([], ())
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return False


def audit_result(path: Path) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {case.get("id") for case in payload.get("cases", []) if case.get("status") == "passed"}
    missing = sorted(REQUIRED_CASES - ids)
    ok = (
        payload.get("unit_id") == "P1-50"
        and payload.get("status") == "verified_local"
        and payload.get("goal_met") is True
        and not missing
        and len(payload.get("cases", [])) == len(REQUIRED_CASES)
        and all(
            case.get("status") == "passed" and observation_valid(case["id"], case.get("actual"))
            for case in payload.get("cases", [])
        )
    )
    print(json.dumps({"valid": ok, "missing": missing}, ensure_ascii=False))
    return 0 if ok else 1


def finish(report: dict, stage_log: StageLog, artifacts: list[dict]) -> int:
    # The parent block is opened early; finish it and expose its real span.
    if not stage_log.start_time:
        stage_log.start()
    if not report.get("_self_check"):
        present = {case["id"] for case in report["cases"] if case["status"] == "passed"}
        missing = sorted(REQUIRED_CASES - present)
        if missing:
            report["cases"].append(
                {
                    "id": "required_cases_missing",
                    "expected": "all A-G OS scenarios passed",
                    "actual": f"missing={missing}",
                    "status": "failed",
                    "evidence_refs": ["s13-p50-gate"],
                }
            )
    for case in report["cases"]:
        if case["id"] in REQUIRED_CASES and not observation_valid(case["id"], case.get("actual")):
            case["status"] = "failed"
    failed = [case for case in report["cases"] if case["status"] != "passed"]
    self_check_ok = report.get("_self_check") and not failed
    if report["status"] != "blocked_environment":
        report["status"] = (
            "partial" if self_check_ok else ("verified_local" if not failed else "failed")
        )
        report["goal_met"] = not failed and not self_check_ok
    exit_code = 0 if report["goal_met"] or self_check_ok else 1
    report["finished_at_utc"] = now()
    report["artifacts"] = artifacts
    if report["status"] == "verified_local":
        report["limitations"].extend(
            [
                "This is a local OS acceptance probe; final deployment/browser gates remain S14/S15.",
                "The report LLM was deterministic fake text; executor, PNG, ODE and publication were real.",
            ]
        )
    report["commands"] = [
        {
            "id": "s13-p50-gate",
            "argv": stage_log.argv,
            "command": " ".join(stage_log.argv),
            "cwd": str(stage_log.cwd),
            "start": stage_log.start_time,
            "end": now(),
            "exit_code": exit_code,
            "log_start_line": stage_log.start_line,
            "log_end_line": stage_log.start_line + 1,
        }
    ]
    result_path = STAGE / "sandbox_result.json"
    try:
        result_label = str(result_path.relative_to(REPO))
    except ValueError:
        result_label = str(result_path)
    case_summary = "\n".join(f"case {case['id']}: {case['status']}" for case in report["cases"])
    report["commands"][0]["log_end_line"] = stage_log.finish(
        f"{case_summary}\nP1-50 {report['status']}: {len(report['cases'])} cases, {len(failed)} failed; result={result_label}\n",
        exit_code,
    )
    result_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"P1-50 {report['status']}: {len(report['cases'])} cases, {len(failed)} failed; result={result_label}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
