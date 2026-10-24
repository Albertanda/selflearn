#!/usr/bin/env python3
"""Run pytest with disposable settings, credentials and a Python network guard.

Usage: .venv/bin/python scripts/run_tests_isolated.py -q tests/phase1
Without arguments, pytest uses both configured testpaths. No real model/config
is copied into the disposable home. This does not claim OS sandbox isolation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.phase1_snapshot import compare_data, protect_data  # noqa: E402
from scripts.phase1_verify import BOOTSTRAP_CODE, NETWORK_GUARD, clean_env  # noqa: E402


def unchanged_since(before: dict, after: dict) -> bool:
    return all(
        compare_data({"roots": before[field]}, {"roots": after[field]})["ok"]
        for field in ("roots", "supplementary_roots")
    )


def main(args: list[str]) -> int:
    with tempfile.TemporaryDirectory(prefix="selflearn-tests-") as root_value:
        root = Path(root_value)
        env = clean_env(root)
        # User use after phase closure is legitimate. Preserve historical
        # receipts separately; guard this entire test run against its own
        # pre-bootstrap opaque snapshot, never a post-test replacement.
        before = protect_data(REPO)
        baseline = root / "data_before_tests.json"
        raw = json.dumps(before, sort_keys=True).encode()
        baseline.write_bytes(raw)
        env["SELFLEARN_TEST_DATA_BASELINE"] = str(baseline)
        env["SELFLEARN_TEST_DATA_BASELINE_SHA256"] = hashlib.sha256(raw).hexdigest()
        env["DEEPTUTOR_HOME"] = str(root / "runtime")
        Path(env["DEEPTUTOR_HOME"]).mkdir()
        guard = root / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
        env["S13_ENDPOINT_REGISTRY"] = str(guard / "endpoints.json")
        env["PYTHONPATH"] = str(guard) + os.pathsep + str(REPO)
        try:
            return run_pytest(args, env)
        finally:
            if not unchanged_since(before, protect_data(REPO)):
                raise RuntimeError("Real user data changed during isolated test run")


def run_pytest(args: list[str], env: dict[str, str]) -> int:
    bootstrap = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP_CODE],
        cwd=REPO,
        env=env,
        timeout=120,
        check=False,
    )
    if bootstrap.returncode:
        return bootstrap.returncode
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", *(args or ["-q"])],
        cwd=REPO,
        env=env,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=2400)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
