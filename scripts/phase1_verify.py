#!/usr/bin/env python3
"""S13 P1-49 gate: full offline regression, evidence chain and data guards.

Every required subcommand is run for real and appended to the S13 execution log;
a non-zero required command makes the gate fail.  A temporary HOME /
DEEPTUTOR_HOME with generated default settings and a text-only fake model is
created before pytest imports the application; real credentials are removed.

Usage::

    ./.venv/bin/python scripts/phase1_verify.py
    ./.venv/bin/python scripts/phase1_verify.py --self-check
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
STAGE = REPO / ".phase1-evidence" / "stages" / "S13"
LOG = STAGE / "execution.log"
RESULT = STAGE / "verify_result.json"
SNAPSHOT = REPO / "scripts" / "phase1_snapshot.py"
S12_RECEIPT = REPO / ".phase1-evidence" / "reviews" / "S12-final" / "review.json"
ALLOWED_SCRIPTS = ("scripts/phase1_sandbox_acceptance.py", "scripts/phase1_verify.py")
EXPECTED_HEAD = "9723f953cb6ca56f13603f76c5d07e1e2f1f4473"
EXPECTED_DELETIONS = (
    "deeptutor_cli/book.py",
    "deeptutor_cli/partner.py",
    "requirements/matrix-e2e.txt",
    "requirements/matrix.txt",
    "requirements/partners.txt",
    "tests/agents/research/test_research_obsidian_tools.py",
    "web/tests/partner-chat-autoscroll.test.ts",
    "web/tests/partner-chat-stop.test.ts",
)
EXPECTED_SKIPS = (
    "IUTF8",
    "pymupdf4llm",
    "graphrag",
    "litellm",
    "lightrag",
    "RAG_INTEGRATION_TESTS",
    "public DNS check skipped",
)

BOOTSTRAP_CODE = """
import json, os
from pathlib import Path
from deeptutor.services.setup.init import init_user_directories
from deeptutor.services.config import ensure_runtime_settings_files

init_user_directories()
ensure_runtime_settings_files()
home = Path(os.environ["DEEPTUTOR_HOME"])
path = home / "data/user/settings/model_catalog.json"
catalog = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": 1, "services": {}}
catalog.setdefault("services", {})["llm"] = {
    "active_profile_id": "p1-s13-local",
    "active_model_id": "m1-s13-local",
    "profiles": [{
        "id": "p1-s13-local",
        "name": "S13 local text-only test model",
        "binding": "custom",
        "base_url": "http://127.0.0.1:9/v1",
        "api_key": "sk-s13-not-a-real-key",
        "models": [{
            "id": "m1-s13-local",
            "name": "S13 local text-only test model",
            "model": "s13-local-text-only",
        }],
    }],
}
path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
print("s13-bootstrap-ok")
"""


NETWORK_GUARD = """
# Installed before application imports in Python children; not an OS sandbox.
import fcntl, ipaddress, json, os, socket

def _local(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False

def _endpoint(address, family):
    if family == socket.AF_UNIX:
        return ['unix', str(address)]
    if not isinstance(address, tuple) or len(address) < 2 or not _local(address[0]):
        return None
    return ['loopback', int(address[1])]

def _registry(add=None):
    path = os.environ.get('S13_ENDPOINT_REGISTRY')
    if not path:
        return []
    with open(path, 'a+', encoding='utf-8') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        rows = json.loads(raw) if raw else []
        if add is not None and add not in rows:
            rows.append(add)
            handle.seek(0); handle.truncate(); json.dump(rows, handle); handle.flush()
        return rows

_bind = socket.socket.bind
def _guard_bind(self, address):
    result = _bind(self, address)
    actual = self.getsockname()
    if self.family in (socket.AF_INET, socket.AF_INET6) and actual[0] in ('0.0.0.0', '::'):
        actual = ('127.0.0.1', actual[1])
    key = _endpoint(actual, self.family)
    if key is not None:
        _registry(key)
    return result

def _check(self, address):
    key = _endpoint(address, self.family)
    if key is None or key not in _registry():
        raise PermissionError('S13 network guard: undeclared endpoint blocked')

_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex
_sendto, _sendmsg = socket.socket.sendto, socket.socket.sendmsg
def _guard_connect(self, address):
    _check(self, address)
    return _connect(self, address)
def _guard_connect_ex(self, address):
    _check(self, address)
    return _connect_ex(self, address)
def _guard_sendto(self, data, *args):
    _check(self, args[-1] if args else None)
    return _sendto(self, data, *args)
def _guard_sendmsg(self, data, ancdata=(), flags=0, address=None):
    _check(self, self.getpeername() if address is None else address)
    return _sendmsg(self, data, ancdata, flags, address)

_getaddrinfo = socket.getaddrinfo
_gethostbyname, _gethostbyname_ex = socket.gethostbyname, socket.gethostbyname_ex
def _dns(host):
    if not _local(host):
        raise PermissionError('S13 network guard: external DNS blocked')
def _guard_getaddrinfo(host, *args, **kwargs):
    if host is not None: _dns(host)
    return _getaddrinfo(host, *args, **kwargs)
def _guard_gethostbyname(host):
    _dns(host)
    return _gethostbyname(host)
def _guard_gethostbyname_ex(host):
    _dns(host)
    return _gethostbyname_ex(host)

socket.socket.bind = _guard_bind
socket.socket.connect, socket.socket.connect_ex = _guard_connect, _guard_connect_ex
socket.socket.sendto, socket.socket.sendmsg = _guard_sendto, _guard_sendmsg
socket.getaddrinfo = _guard_getaddrinfo
socket.gethostbyname, socket.gethostbyname_ex = _guard_gethostbyname, _guard_gethostbyname_ex
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.previous-{int(time.time())}"))
        path.unlink()


def count_lines() -> int:
    with LOG.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


class StageLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, text: str) -> tuple[int, int]:
        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            before = count_lines()
            handle.write(text)
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return before + 1, count_lines()

    def start(self, label: str, argv: list[str], cwd: Path) -> int:
        text = (
            "-" * 78 + "\n"
            f"[{label}] {now()}\n"
            f"cwd: {cwd}\n"
            f"argv: {json.dumps(argv, ensure_ascii=False)}\n"
            f"$ {' '.join(argv)}\n"
        )
        first, _ = self._append(text)
        return first + 1  # header is the line after the separator

    def run(
        self, label: str, argv: list[str], cwd: Path, env: dict[str, str], timeout: int = 2400
    ) -> dict:
        started = now()
        start = self.start(label, argv, cwd)
        t0 = time.monotonic()
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=10)
        code = 124 if timed_out else proc.returncode
        elapsed = round(time.monotonic() - t0, 3)
        text = ""
        if stdout:
            text += stdout if stdout.endswith("\n") else stdout + "\n"
        if stderr:
            text += "--- stderr ---\n" + (stderr if stderr.endswith("\n") else stderr + "\n")
        text += f"exit={code}\n"
        _, end = self._append(text)
        return {
            "id": label,
            "argv": argv,
            "command": " ".join(argv),
            "cwd": str(cwd),
            "start": started,
            "end": now(),
            "elapsed_s": elapsed,
            "exit_code": code,
            "timed_out": timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "log_start_line": start,
            "log_end_line": end,
        }

    def close_parent(self, text: str, code: int) -> None:
        self._append(text + f"exit={code}\n")


def clean_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in tuple(env):
        upper = key.upper()
        if (
            any(
                token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
            )
            or upper.startswith(
                (
                    "OPENAI_",
                    "ANTHROPIC_",
                    "CODEBUDDY_",
                    "DEEPTUTOR_CODEBUDDY_",
                    "AWS_",
                    "GOOGLE_",
                    "AZURE_",
                )
            )
            or upper
            in {
                "PYTEST_ADDOPTS",
                "PYTEST_PLUGINS",
                "PYTHONPATH",
                "PYTHONHOME",
                "NODE_OPTIONS",
                "NODE_PATH",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
            }
        ):
            env.pop(key, None)
    env.pop("DEEPTUTOR_HOME", None)
    env.update(
        {
            "HOME": str(root / "home"),
            "CODEX_HOME": str(root / "codex"),
            "CLAUDE_CONFIG_DIR": str(root / "claude"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "TMPDIR": str(root / "tmp"),
            "DEEPTUTOR_CODEBUDDY_AUTH_FILE": str(root / "missing-auth.json"),
            "PYTHONPYCACHEPREFIX": str(root / "pycache"),
            "PIP_NO_INDEX": "1",
            "NO_COLOR": "1",
            "TERM": "dumb",
            "SELFLEARN_TEST_ROOT": str(root),
            "SELFLEARN_ISOLATED_TEST_RUN": "1",
        }
    )
    for key in (
        "HOME",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "PYTHONPYCACHEPREFIX",
    ):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO / path


def add_case(
    report: dict, case_id: str, expected: str, actual: str, ok: bool, refs: list[str] | None = None
) -> None:
    report["cases"].append(
        {
            "id": case_id,
            "expected": expected,
            "actual": actual,
            "status": "passed" if ok else "failed",
            "evidence_refs": refs or [],
        }
    )


def check_history(report: dict) -> None:
    problems = []
    rows = []
    latest = json.loads(S12_RECEIPT.read_text())
    latest_source = json.loads(resolve(latest["source_baseline"]).read_text())
    superseded = []
    for stage in [f"S{i:02d}" for i in range(13)]:
        pointer_path = REPO / ".phase1-evidence" / "stages" / stage / "review.json"
        if not pointer_path.is_file():
            problems.append(f"{stage}: missing pointer")
            continue
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if pointer.get("status") != "accepted":
            problems.append(f"{stage}: not accepted")
        row = {"stage": stage, "pointer_sha256": sha256(pointer_path)}
        if pointer.get("evidence"):
            legacy = (pointer_path.parent / pointer["evidence"]).resolve()
            if not legacy.is_file() or sha256(legacy) != pointer["evidence_sha256"]:
                problems.append(f"{stage}: legacy evidence seal mismatch")
        if pointer.get("receipt"):
            receipt_path = resolve(str(pointer["receipt"]))
            if not receipt_path.is_file():
                problems.append(f"{stage}: missing receipt")
                continue
            digest = sha256(receipt_path)
            if pointer.get("receipt_sha256") and digest != pointer["receipt_sha256"]:
                problems.append(f"{stage}: receipt hash mismatch")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("status") != "accepted":
                problems.append(f"{stage}: receipt not accepted")
            row.update({"receipt": str(receipt_path), "receipt_sha256": digest})
            for field, key in (
                ("executor_report", "executor_report_sha256"),
                ("executor_closing_manifest", "executor_closing_manifest_sha256"),
                ("archive", "archive_sha256"),
            ):
                value = receipt.get(field)
                if not value:
                    continue
                target = resolve(str(value))
                if not target.is_file():
                    problems.append(f"{stage}: missing {field}")
                elif receipt.get(key) and sha256(target) != receipt[key]:
                    problems.append(f"{stage}: {field} hash mismatch")
            for field in ("evidence_hashes", "dispatch_document_hashes"):
                for value, expected in receipt.get(field, {}).items():
                    target = (
                        resolve(value)
                        if field == "dispatch_document_hashes"
                        or Path(value).is_absolute()
                        or "/" in value
                        else receipt_path.parent / value
                    )
                    if not target.is_file() or sha256(target) != expected:
                        # Early dispatch maps included living planning documents.
                        # Only a later sealed source snapshot can supersede them;
                        # immutable evidence itself never uses this exception.
                        entry = latest_source["archived_files"].get(value, {})
                        if (
                            field == "dispatch_document_hashes"
                            and target.is_file()
                            and entry.get("sha256") == sha256(target)
                        ):
                            superseded.append(
                                {"stage": stage, "path": value, "basis": str(S12_RECEIPT)}
                            )
                            continue
                        problems.append(f"{stage}: sealed {field} mismatch: {value}")
        rows.append(row)
    report["history_chain"] = {
        "stages": rows,
        "problems": problems,
        "superseded_dispatch_sources": superseded,
    }
    add_case(
        report,
        "history_chain",
        "S00–S12 accepted pointers; receipt/report/closing/archive seals match",
        f"checked {len(rows)} stages; problems={problems}",
        not problems,
    )


def check_latest(report: dict) -> None:
    receipt = json.loads(S12_RECEIPT.read_text(encoding="utf-8"))
    artifacts = receipt["source_artifacts"]
    changed = sorted(
        rel
        for rel, digest in artifacts.items()
        if not (REPO / rel).is_file() or sha256(REPO / rel) != digest
    )
    report["latest_source"] = {"count": len(artifacts), "changed": changed, "violations": changed}
    add_case(
        report,
        "latest_source_145",
        "all 145 accepted source artifacts stay byte-identical; S13 only adds two scripts",
        f"count={len(artifacts)}; changed={changed}",
        not changed,
    )
    expected = receipt.get("dispatch_document_hashes", {})
    dispatch_changed = sorted(
        rel
        for rel, digest in expected.items()
        if not (REPO / rel).is_file() or sha256(REPO / rel) != digest
    )
    report["dispatch"] = {"expected": expected, "changed": dispatch_changed}
    add_case(
        report,
        "dispatch_hashes",
        "S13 dispatch documents match the accepted S12 receipt",
        f"changed={dispatch_changed}",
        not dispatch_changed,
    )


def collection_nodes(stdout: str) -> list[str]:
    """One complete pytest node ID per line, including class/parameter separators."""
    return [
        line
        for line in stdout.splitlines()
        if line.startswith(("tests/", "deeptutor/learning/tests/")) and "::" in line
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--baseline-receipt", type=Path, default=None)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    global STAGE, LOG, RESULT, S12_RECEIPT
    if args.baseline_receipt is not None:
        S12_RECEIPT = args.baseline_receipt.resolve()
    else:
        pointer = REPO / ".phase1-evidence/stages/S13/review.json"
        if pointer.is_file():
            payload = json.loads(pointer.read_text())
            if payload.get("status") == "accepted":
                S12_RECEIPT = resolve(payload["receipt"])
                if sha256(S12_RECEIPT) != payload["receipt_sha256"]:
                    parser.error("accepted S13 receipt seal mismatch")
    STAGE = (
        args.evidence_dir.resolve()
        if args.evidence_dir is not None
        else REPO / ".phase1-evidence/runs/S13" / uuid.uuid4().hex
    )
    LOG, RESULT = STAGE / "execution.log", STAGE / "verify_result.json"
    if STAGE.exists() and any(STAGE.iterdir()):
        parser.error("use a new empty evidence directory; sealed evidence must stay unchanged")
    STAGE.mkdir(parents=True, exist_ok=True)
    log = StageLog(LOG)
    report: dict = {
        "schema_version": 1,
        "stage_id": "S13",
        "unit_id": "P1-49",
        "status": "failed",
        "goal_met": False,
        "started_at_utc": now(),
        "finished_at_utc": "",
        "cases": [],
        "commands": [],
        "limitations": [],
    }
    temp_root = Path(tempfile.mkdtemp(prefix="s13-p49-home-"))
    env = clean_env(temp_root)
    guard_dir = temp_root / "guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    (guard_dir / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
    env["DEEPTUTOR_HOME"] = str(temp_root / "deeptutor-home")
    Path(env["DEEPTUTOR_HOME"]).mkdir(parents=True, exist_ok=True)
    env["S13_ENDPOINT_REGISTRY"] = str(guard_dir / "endpoints.json")
    env["PYTHONPATH"] = str(guard_dir) + os.pathsep + str(REPO)
    commands: list[dict] = []

    def record(item: dict) -> None:
        commands.append(item)
        report["commands"].append(
            {
                k: item[k]
                for k in (
                    "id",
                    "argv",
                    "command",
                    "cwd",
                    "start",
                    "end",
                    "elapsed_s",
                    "exit_code",
                    "log_start_line",
                    "log_end_line",
                )
            }
        )

    try:
        check_history(report)
        check_latest(report)
        guard_hash = sha256(guard_dir / "sitecustomize.py")
        add_case(
            report,
            "network_guard",
            "pytest runs with a sitecustomize guard that denies external sockets/DNS while allowing loopback",
            f"guard={guard_dir / 'sitecustomize.py'}; sha256={guard_hash}",
            True,
        )
        if not args.self_check:
            receipt = json.loads(S12_RECEIPT.read_text())
            baseline = resolve(receipt["source_baseline"])
            include = sorted(set(receipt["source_artifacts"]) | set(ALLOWED_SCRIPTS))
            capture_argv = [
                sys.executable,
                str(SNAPSHOT),
                "capture",
                "--label",
                "S13 gate after",
                "--out",
                str(STAGE / "source_after.json"),
                *[a for path in include for a in ("--include", path)],
            ]
            scope_argv = [
                sys.executable,
                str(SNAPSHOT),
                "compare",
                "--before",
                str(baseline),
                "--after",
                str(STAGE / "source_after.json"),
                "--out",
                str(STAGE / "scope_report.json"),
                *[a for path in ALLOWED_SCRIPTS for a in ("--allow", glob.escape(path))],
            ]
            record(
                log.run(
                    "s13-p49-data-before",
                    [
                        sys.executable,
                        str(SNAPSHOT),
                        "protect-data",
                        "--out",
                        str(STAGE / "data_before.json"),
                    ],
                    REPO,
                    env,
                    120,
                )
            )
            record(
                log.run("s13-p49-bootstrap", [sys.executable, "-c", BOOTSTRAP_CODE], REPO, env, 120)
            )
            pytest_argv = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-rs",
                "-W",
                "error::RuntimeWarning",
                "-W",
                "error::pytest.PytestUnraisableExceptionWarning",
                "tests",
                "deeptutor/learning/tests",
            ]
            pytest = log.run("s13-p49-pytest", pytest_argv, REPO, env, 2400)
            record(pytest)
            counts = {}
            for key in ("passed", "failed", "skipped", "errors"):
                found = re.findall(rf"(\d+) {key}\b", pytest["stdout"])
                if found:
                    counts[key] = int(found[-1])
            skips = [line for line in pytest["stdout"].splitlines() if line.startswith("SKIPPED [")]
            pytest_ok = (
                counts.get("passed", 0) > 0
                and pytest["exit_code"] == 0
                and counts.get("failed", 0) == 0
                and counts.get("errors", 0) == 0
            )
            skip_ok = len(skips) == 20 and all(
                any(reason in line for reason in EXPECTED_SKIPS) for line in skips
            )
            report["pytest"] = {"counts": counts, "skip_lines": skips}
            add_case(
                report,
                "full_pytest",
                "tests + deeptutor/learning/tests: zero failed/errors; 20 existing conditional skips; RuntimeWarning treated as error",
                f"exit={pytest['exit_code']}; counts={counts}; skips={len(skips)}",
                pytest_ok and skip_ok,
                [pytest["id"]],
            )
            collect = log.run(
                "s13-p49-collect",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--collect-only",
                    "-q",
                    "tests",
                    "deeptutor/learning/tests",
                ],
                REPO,
                env,
                900,
            )
            record(collect)
            node_list = collection_nodes(collect["stdout"])
            nodes = len(node_list)
            report["collection"] = {"count": nodes, "node_ids": node_list}
            executed = sum(counts.get(k, 0) for k in ("passed", "skipped", "xfailed", "xpassed"))
            add_case(
                report,
                "pytest_collection",
                "collect-only succeeds and reports the full node list",
                f"exit={collect['exit_code']}; nodes={nodes}",
                collect["exit_code"] == 0
                and nodes == executed
                and nodes > 4000
                and any(n.startswith("deeptutor/learning/tests/") for n in node_list),
                [collect["id"]],
            )

            node_bin = (
                Path("/usr/bin/node")
                if Path("/usr/bin/node").is_file()
                else Path(shutil.which("node") or "node")
            )
            node_env = dict(env)
            node_env["PATH"] = "/usr/bin:/bin"
            version = log.run(
                "s13-p49-node-version", [str(node_bin), "--version"], REPO, node_env, 30
            )
            record(version)
            node = log.run(
                "s13-p49-node",
                [str(node_bin), "./scripts/run-node-tests.mjs"],
                REPO / "web",
                node_env,
                900,
            )
            record(node)
            node_counts = {
                key: int(value)
                for key, value in re.findall(
                    r"^# (tests|pass|fail|skipped) (\d+)$", node["stdout"], re.M
                )
            }
            node_ok = (
                version["exit_code"] == 0
                and node["exit_code"] == 0
                and node_counts.get("fail", 1) == 0
                and node_counts.get("pass", 0) >= 477
            )
            report["node"] = {
                "executable": str(node_bin),
                "version": version["stdout"].strip(),
                "counts": node_counts,
            }
            add_case(
                report,
                "node_tests",
                "recursive Node tests via /usr/bin/node v22: >=477 passed, 0 failed",
                f"version={version['stdout'].strip()}; exit={node['exit_code']}; counts={node_counts}",
                node_ok,
                [version["id"], node["id"]],
            )
            tsc = log.run(
                "s13-p49-tsc",
                ["./node_modules/.bin/tsc", "--noEmit", "-p", "."],
                REPO / "web",
                node_env,
                900,
            )
            record(tsc)
            add_case(
                report,
                "typescript",
                "full-site tsc --noEmit exits 0",
                f"exit={tsc['exit_code']}",
                tsc["exit_code"] == 0,
                [tsc["id"]],
            )

            ruff = log.run(
                "s13-p49-ruff",
                [str(REPO / ".venv/bin/ruff"), "check", "deeptutor", "deeptutor_cli"],
                REPO,
                env,
                300,
            )
            record(ruff)
            add_case(
                report,
                "ruff_business",
                "business-directory Ruff exits 0",
                f"exit={ruff['exit_code']}",
                ruff["exit_code"] == 0,
                [ruff["id"]],
            )
            script_paths = [str(REPO / name) for name in ALLOWED_SCRIPTS if (REPO / name).is_file()]
            if str(REPO / "scripts/phase1_verify.py") not in script_paths:
                script_paths.append(str(REPO / "scripts/phase1_verify.py"))
            ruff_scripts = log.run(
                "s13-p49-ruff-scripts",
                [str(REPO / ".venv/bin/ruff"), "check", *script_paths],
                REPO,
                env,
                300,
            )
            record(ruff_scripts)
            both = all((REPO / name).is_file() for name in ALLOWED_SCRIPTS)
            add_case(
                report,
                "ruff_gate_scripts",
                "both S13 scripts exist and pass Ruff",
                f"scripts={script_paths}; exit={ruff_scripts['exit_code']}; both_present={both}",
                ruff_scripts["exit_code"] == 0 and both,
                [ruff_scripts["id"]],
            )
            diff = log.run("s13-p49-diff", ["git", "diff", "--check"], REPO, env, 120)
            record(diff)
            add_case(
                report,
                "git_diff_check",
                "git diff --check exits 0",
                f"exit={diff['exit_code']}",
                diff["exit_code"] == 0,
                [diff["id"]],
            )

            source_after = STAGE / "source_after.json"
            preserve(source_after)
            preserve(STAGE / "scope_report.json")
            capture = log.run("s13-p49-source-after", capture_argv, REPO, env, 600)
            record(capture)
            scope = log.run("s13-p49-scope", scope_argv, REPO, env, 600)
            record(scope)
            scope_data = json.loads((STAGE / "scope_report.json").read_text(encoding="utf-8"))
            report["scope_check"] = {
                "ok": scope_data["ok"],
                "outside_changes": scope_data["outside_changes"],
            }
            add_case(
                report,
                "source_scope",
                "only the two new gate scripts differ",
                f"ok={scope_data['ok']}; outside={scope_data['outside_changes']}; changes={scope_data['change_count']}",
                scope["exit_code"] == 0 and scope_data["ok"],
                [capture["id"], scope["id"]],
            )

            data_after = STAGE / "data_after.json"
            if data_after.exists():
                data_after = STAGE / f"data_after-{int(time.time())}.json"
            protect = log.run(
                "s13-p49-data-after",
                [sys.executable, str(SNAPSHOT), "protect-data", "--out", str(data_after)],
                REPO,
                env,
                600,
            )
            record(protect)
            preserve(STAGE / "data_comparison.json")
            compare = log.run(
                "s13-p49-data-compare",
                [
                    sys.executable,
                    str(SNAPSHOT),
                    "compare-data",
                    "--before",
                    str(STAGE / "data_before.json"),
                    "--after",
                    str(data_after),
                    "--out",
                    str(STAGE / "data_comparison.json"),
                ],
                REPO,
                env,
                600,
            )
            record(compare)
            before_data = json.loads((STAGE / "data_before.json").read_text())
            after_data = json.loads(data_after.read_text())
            data_ok = (
                protect["exit_code"] == 0
                and compare["exit_code"] == 0
                and all(
                    before_data[field] == after_data[field]
                    for field in ("roots", "supplementary_roots")
                )
            )
            report["six_roots_unchanged"] = data_ok
            add_case(
                report,
                "real_data_protection",
                "six opaque real-data roots unchanged",
                f"protect={protect['exit_code']}; compare={compare['exit_code']}; ok={data_ok}",
                data_ok,
                [protect["id"], compare["id"]],
            )

            archive = STAGE / "source_recovery_s13.tar.gz"
            preserve(archive)
            preserve(STAGE / "source_recovery_s13.tar.gz.manifest.json")
            preserve(STAGE / "archive_verification.json")
            build = log.run(
                "s13-p49-archive",
                [
                    sys.executable,
                    str(SNAPSHOT),
                    "archive",
                    "--baseline",
                    str(source_after),
                    "--out",
                    str(archive),
                    "--archive-info",
                    str(STAGE / "source_recovery_s13.tar.gz.manifest.json"),
                ],
                REPO,
                env,
                1200,
            )
            record(build)
            rebuild_dir = Path(tempfile.mkdtemp(prefix="s13-p49-rebuild-"))
            verify = log.run(
                "s13-p49-verify-rebuild",
                [
                    sys.executable,
                    str(SNAPSHOT),
                    "verify-rebuild",
                    "--baseline",
                    str(source_after),
                    "--archive",
                    str(archive),
                    "--workdir",
                    str(rebuild_dir),
                    "--out",
                    str(STAGE / "archive_verification.json"),
                    "--archive-info",
                    str(STAGE / "source_recovery_s13.tar.gz.manifest.json"),
                ],
                REPO,
                env,
                1200,
            )
            record(verify)
            verification = json.loads(
                (STAGE / "archive_verification.json").read_text(encoding="utf-8")
            )
            shutil.rmtree(rebuild_dir)
            report["archive"] = verification
            add_case(
                report,
                "archive_rebuild",
                "archive rebuilds every member with matching hashes",
                f"build={build['exit_code']}; verify={verify['exit_code']}; rebuilt={verification.get('rebuilt_count')}; mismatches={verification.get('hash_mismatches')}",
                build["exit_code"] == 0
                and verify["exit_code"] == 0
                and bool(verification.get("ok")),
                [build["id"], verify["id"]],
            )

            import tarfile

            prior_archive = resolve(receipt["archive"])
            with tarfile.open(prior_archive, "r:gz") as prior_tar:
                prior_members = [m.name for m in prior_tar.getmembers()]
            with tarfile.open(archive, "r:gz") as current_tar:
                current_members = [m.name for m in current_tar.getmembers()]
            added = sorted(set(current_members) - set(prior_members))
            removed = sorted(set(prior_members) - set(current_members))
            membership_ok = (
                not removed
                and set(added) <= set(ALLOWED_SCRIPTS)
                and len(current_members) == len(set(current_members))
            )
            report["archive_membership"] = {
                "prior_members": len(prior_members),
                "current_members": len(current_members),
                "added": added,
                "removed": removed,
            }
            add_case(
                report,
                "archive_membership",
                "S13 archive retains all 1907 S12-accepted members and adds exactly the two gate scripts",
                json.dumps(report["archive_membership"], ensure_ascii=False),
                membership_ok,
            )

            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
            ).stdout.strip()
            present = [rel for rel in EXPECTED_DELETIONS if (REPO / rel).exists()]
            guard_ok = head == receipt["head"] and not present and data_ok
            report["host_guards"] = {
                "head": head,
                "deletions_present": present,
                "six_roots_unchanged": data_ok,
            }
            add_case(
                report,
                "host_guards",
                "HEAD, eight deletions and all six inventories/locks stay unchanged",
                json.dumps(report["host_guards"]),
                guard_ok,
            )
        else:
            ruff_self = log.run(
                "s13-p49-self-ruff",
                [str(REPO / ".venv/bin/ruff"), "check", str(REPO / "scripts/phase1_verify.py")],
                REPO,
                env,
                120,
            )
            record(ruff_self)
            add_case(
                report,
                "self_ruff",
                "phase1_verify.py passes Ruff",
                f"exit={ruff_self['exit_code']}",
                ruff_self["exit_code"] == 0,
                [ruff_self["id"]],
            )
            report["limitations"].append(
                "--self-check skips full pytest/Node/tsc/snapshot/archive."
            )
    except BaseException as exc:  # noqa: BLE001 - gate must record failures
        report["limitations"].append(f"gate raised {type(exc).__name__}: {exc}")
        add_case(
            report,
            "gate_exception",
            "gate completes without an unhandled exception",
            f"{type(exc).__name__}: {exc}",
            False,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    bad_commands = [c["id"] for c in commands if c["exit_code"] != 0]
    add_case(
        report,
        "required_command_exits",
        "every required child command exits zero",
        str(bad_commands),
        not bad_commands,
    )
    failed = [case for case in report["cases"] if case["status"] != "passed"]
    report["status"] = (
        "partial"
        if args.self_check and not failed
        else ("verified_local" if not failed else "failed")
    )
    report["goal_met"] = not failed and not args.self_check
    report["finished_at_utc"] = now()
    if not failed:
        report["limitations"].extend(
            [
                "Python guard and this gate are not the P1-50 OS isolation proof.",
                "No real provider, index, service, upload/export/delete or deployment was used.",
            ]
        )
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        result_label = str(RESULT.relative_to(REPO))
    except ValueError:
        result_label = str(RESULT)
    summary = f"P1-49 {report['status']}: {len(report['cases'])} cases, {len(failed)} failed; result={result_label}\n"
    print(summary, end="")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
