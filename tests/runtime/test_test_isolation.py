"""Prevent accidental real settings/provider access before pytest collection."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("wrong_environment", ["missing_marker", "escaped_home"])
def test_unisolated_collection_is_rejected_without_touching_settings(tmp_path, wrong_environment):
    base = tmp_path / "isolated"
    base.mkdir()
    catalog = base / "runtime/data/user/settings/model_catalog.json"
    catalog.parent.mkdir(parents=True)
    original = b'{"sentinel":"FAKE-DO-NOT-CHANGE"}\n'
    catalog.write_bytes(original)
    env = os.environ.copy()
    env.update(SELFLEARN_TEST_ROOT=str(base), SELFLEARN_ISOLATED_TEST_RUN="1")
    for key in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "DEEPTUTOR_HOME",
    ):
        env[key] = str(base / "runtime")
    if wrong_environment == "missing_marker":
        env.pop("SELFLEARN_ISOLATED_TEST_RUN")
    else:
        env["HOME"] = str(tmp_path / "outside")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/tools/test_rag_tool.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "Unisolated pytest collection refused" in result.stderr
    assert catalog.read_bytes() == original


def test_isolated_runner_collects_with_no_parent_provider_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE-PARENT-KEY")
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path / "must-not-be-used"))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_tests_isolated.py"),
            "--collect-only",
            "-q",
            "tests/logging/test_process_logs.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_async_log_callback_from_worker_runs_on_owning_loop" in result.stdout
    assert not (tmp_path / "must-not-be-used").exists()
    assert "FAKE-PARENT-KEY" not in result.stdout + result.stderr


@pytest.mark.parametrize("field", ["roots", "supplementary_roots"])
def test_runner_rejects_real_data_mutation_even_when_pytest_passes(tmp_path, monkeypatch, field):
    from copy import deepcopy
    import importlib.util
    import types

    # Full collection also imports tests/scripts, a regular package that can
    # shadow the repository's namespace package. Load this CLI explicitly.
    spec = importlib.util.spec_from_file_location(
        "isolated_runner_under_test", ROOT / "scripts/run_tests_isolated.py"
    )
    runner = importlib.util.module_from_spec(spec)
    namespace = types.ModuleType("scripts")
    namespace.__path__ = [str(ROOT / "scripts")]
    with monkeypatch.context() as imports:
        imports.setitem(sys.modules, "scripts", namespace)
        spec.loader.exec_module(runner)

    snapshot = {
        "roots": {"primary": {"exists": False}},
        "supplementary_roots": {"extra": {"exists": False}},
    }
    after = deepcopy(snapshot)
    after[field][next(iter(after[field]))] = {
        "exists": True,
        "kind": "file",
        "sha256": "a" * 64,
        "size": 1,
        "mode": 384,
    }
    assert runner.unchanged_since(snapshot, snapshot)
    assert not runner.unchanged_since(snapshot, after)
    values = iter([snapshot, after])
    monkeypatch.setattr(runner, "protect_data", lambda root: next(values))
    monkeypatch.setattr(runner, "run_pytest", lambda args, env: 0)
    with pytest.raises(RuntimeError, match="Real user data changed"):
        runner.main(["--collect-only"])
