"""P1-47: the fixed-home start wrapper (fake CLI in temporary copies only).

Every scenario builds a disposable repository copy, installs a fake
``.venv/bin/deeptutor`` that records its real cwd/home/argv, and invokes the
copied wrapper as a subprocess.  The real checkout's CLI is never executed and
no real service/data tree is touched.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "start_selflearn.sh"

FAKE_CLI = """#!/usr/bin/env bash
set -u
{
    printf 'cwd=%s\\n' "$PWD"
    printf 'home=%s\\n' "${DEEPTUTOR_HOME-<unset>}"
    for arg in "$@"; do
        printf 'arg=%s\\n' "$arg"
    done
} > "$FAKE_CAPTURE"
exit "${FAKE_EXIT:-0}"
"""


def make_repo(
    base: Path,
    *,
    name: str = "repo with space",
    venv: bool = True,
    cli: bool = True,
    executable: bool = True,
) -> Path:
    repo = base / name
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(WRAPPER, scripts / "start_selflearn.sh")
    if venv:
        bin_dir = repo / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        python = bin_dir / "python"
        python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python.chmod(0o755)
    if cli:
        cli_path = repo / ".venv" / "bin" / "deeptutor"
        cli_path.write_text(FAKE_CLI, encoding="utf-8")
        cli_path.chmod(0o755 if executable else 0o644)
    return repo


def run_wrapper(
    tmp_path: Path,
    repo: Path,
    *,
    wrapper: Path | None = None,
    args: list[str] | None = None,
    inherited_home: Path | None = None,
    fake_exit: int = 0,
    cwd: Path | None = None,
    path_prefix: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, str], list[str]]:
    capture = tmp_path / "fake-cli-capture.txt"
    if capture.exists():
        capture.unlink()
    working = cwd or (tmp_path / "unrelated-cwd")
    working.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("DEEPTUTOR_HOME", None)
    if inherited_home is not None:
        env["DEEPTUTOR_HOME"] = str(inherited_home)
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_CAPTURE"] = str(capture)
    env["FAKE_EXIT"] = str(fake_exit)
    executable = wrapper or (repo / "scripts" / "start_selflearn.sh")
    completed = subprocess.run(
        [str(executable), *(args or [])],
        cwd=working,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    values: dict[str, str] = {}
    recorded: list[str] = []
    if capture.is_file():
        for line in capture.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key == "arg":
                recorded.append(value)
            else:
                values[key] = value
    return completed, capture, values, recorded


def assert_no_data_tree(repo: Path) -> None:
    assert not (repo / "data").exists(), "wrapper created a runtime data tree"


def test_wrapper_runs_the_local_cli_with_the_checkout_as_home(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    completed, capture, values, args = run_wrapper(tmp_path, repo)

    assert completed.returncode == 0, completed.stderr
    assert capture.is_file()
    assert values["cwd"] == str(repo.resolve())
    assert values["home"] == str(repo.resolve())
    assert args == ["start", "--home", str(repo.resolve())]
    assert_no_data_tree(repo)


def test_inherited_wrong_home_is_overridden_and_dev_is_forwarded(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    wrong = tmp_path / "inherited-wrong-home"
    wrong.mkdir()
    marker = wrong / "must-not-be-touched"
    marker.write_text("keep\n", encoding="utf-8")

    completed, _, values, args = run_wrapper(
        tmp_path,
        repo,
        args=["--dev"],
        inherited_home=wrong,
    )

    assert completed.returncode == 0, completed.stderr
    assert values["home"] == str(repo.resolve())
    assert values["home"] != str(wrong)
    assert args == ["start", "--home", str(repo.resolve()), "--dev"]
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert not (wrong / "data").exists()
    assert_no_data_tree(repo)


def test_symlinked_wrapper_resolves_the_real_checkout(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    link = tmp_path / "start-selflearn-link"
    link.symlink_to(repo / "scripts" / "start_selflearn.sh")

    completed, _, values, args = run_wrapper(tmp_path, repo, wrapper=link)

    assert completed.returncode == 0, completed.stderr
    assert values["cwd"] == str(repo.resolve())
    assert values["home"] == str(repo.resolve())
    assert args == ["start", "--home", str(repo.resolve())]


@pytest.mark.parametrize("via_link", [False, True])
def test_inherited_cdpath_cannot_redirect_relative_launcher_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_link: bool
) -> None:
    repo = make_repo(tmp_path)
    decoy = make_repo(tmp_path, name="decoy-checkout")
    monkeypatch.setenv("CDPATH", str(decoy))
    wrapper = Path("scripts/start_selflearn.sh")
    if via_link:
        (repo / "launchers").mkdir()
        (decoy / "launchers").mkdir()
        (repo / "launchers/start").symlink_to("../scripts/start_selflearn.sh")
        wrapper = Path("launchers/start")

    completed, capture, values, args = run_wrapper(
        tmp_path, repo, wrapper=wrapper, cwd=repo
    )

    assert completed.returncode == 0, completed.stderr
    assert capture.is_file()
    assert values["cwd"] == values["home"] == str(repo.resolve())
    assert args == ["start", "--home", str(repo.resolve())]
    assert_no_data_tree(repo)
    assert_no_data_tree(decoy)


def test_cli_exit_code_is_passed_through_unchanged(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    completed, capture, values, args = run_wrapper(tmp_path, repo, fake_exit=7)

    assert completed.returncode == 7
    assert capture.is_file()
    assert values["home"] == str(repo.resolve())
    assert args == ["start", "--home", str(repo.resolve())]


def test_missing_venv_is_named_and_creates_no_data_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, venv=False, cli=False)

    completed, capture, _, _ = run_wrapper(tmp_path, repo)

    assert completed.returncode != 0
    assert "missing virtualenv" in completed.stderr
    assert not capture.exists()
    assert_no_data_tree(repo)


def test_missing_local_cli_is_named_and_creates_no_data_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, cli=False)

    completed, capture, _, _ = run_wrapper(tmp_path, repo)

    assert completed.returncode != 0
    assert "missing local CLI" in completed.stderr
    assert not capture.exists()
    assert_no_data_tree(repo)


def test_non_executable_local_cli_is_named_and_creates_no_data_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, executable=False)

    completed, capture, _, _ = run_wrapper(tmp_path, repo)

    assert completed.returncode != 0
    assert "not executable" in completed.stderr
    assert not capture.exists()
    assert_no_data_tree(repo)


@pytest.mark.parametrize(
    "args",
    [
        ["--home", "/tmp/elsewhere"],
        ["--home=/tmp/elsewhere"],
        ["--dev", "--home", "/tmp/elsewhere"],
        ["--dev", "--home=/tmp/elsewhere"],
    ],
)
def test_caller_home_is_rejected_before_the_cli_runs(
    tmp_path: Path, args: list[str]
) -> None:
    repo = make_repo(tmp_path)

    completed, capture, _, _ = run_wrapper(tmp_path, repo, args=args)

    assert completed.returncode != 0
    assert "refusing caller-supplied --home" in completed.stderr
    assert not capture.exists()
    assert_no_data_tree(repo)


def test_path_cli_cannot_shadow_the_checkout_cli(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    hostile = tmp_path / "hostile-path"
    hostile.mkdir()
    shim = hostile / "deeptutor"
    shim.write_text("#!/bin/sh\necho hostile > \"$HOSTILE_MARKER\"\nexit 3\n", encoding="utf-8")
    shim.chmod(0o755)
    marker = tmp_path / "hostile-marker"
    old_marker = os.environ.get("HOSTILE_MARKER")
    os.environ["HOSTILE_MARKER"] = str(marker)
    try:
        completed, capture, values, args = run_wrapper(
            tmp_path,
            repo,
            path_prefix=hostile,
        )
    finally:
        if old_marker is None:
            os.environ.pop("HOSTILE_MARKER", None)
        else:
            os.environ["HOSTILE_MARKER"] = old_marker

    assert completed.returncode == 0, completed.stderr
    assert capture.is_file()
    assert values["home"] == str(repo.resolve())
    assert args == ["start", "--home", str(repo.resolve())]
    assert not marker.exists(), "wrapper executed a PATH deeptutor"


def test_wrapper_is_executable_and_syntactically_valid() -> None:
    assert WRAPPER.is_file()
    assert os.access(WRAPPER, os.X_OK)
    completed = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


# ---------------------------------------------------------------------------
# Active docs / historical archives / Compose comments
# ---------------------------------------------------------------------------
def test_readme_promotes_the_wrapper_and_documents_real_boundaries() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "./scripts/start_selflearn.sh" in text
    assert 'DEEPTUTOR_HOME="$PWD"' in text
    assert "从任意 cwd" in text
    assert "拒绝调用者传入 `--home`" in text
    assert "PageIndex" in text and "outline" in text
    assert "不会自动建立索引" in text
    assert "未评估" in text
    assert "不含聊天历史" in text and "不提供导入恢复" in text
    assert "报告专用受限执行器" in text and "503" in text
    assert "S13/P50" in text and "S14" in text and "S15" in text

    for line in text.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("deeptutor partner")
        assert not stripped.startswith("deeptutor book")
        assert not stripped.startswith('pip install -e ".[partners]"')
        assert not stripped.startswith('pip install -e ".[matrix]')
        assert not stripped.startswith('pip install -e ".[tutorbot]')


def test_environment_document_records_actual_versions_and_unverified_gaps() -> None:
    text = (ROOT / "plans" / "phase1" / "ENVIRONMENT.md").read_text(encoding="utf-8")

    assert "3.12.14" in text
    assert re.search(r"\| Node\.js \| `v\d+\.\d+\.\d+`", text)
    assert "environment_observation.json" in text
    assert "environment-observation" in text
    assert "typst 0.15.1 (9dfd3a08)" in text
    assert "29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237" in text
    assert "1,000" not in text  # no fabricated byte counts
    assert "live llm" in text.lower() and "not verified" in text.lower()
    assert "S13/P50" in text and "S14" in text and "S15" in text


def test_upstream_archive_files_are_byte_unchanged() -> None:
    expected = {
        "UPSTREAM.md": "cf9bfada3bee8ef3f52cfa43ae4751f393ebe8d22c8fc3f4e07ded1e46b29cff",
        "assets/README/README_CN.md": "8be05c64626c790daca7202a5dfa381f6f92b7fa44f759a8ab379491f301266e",
    }
    for rel, digest in expected.items():
        actual = __import__("hashlib").sha256((ROOT / rel).read_bytes()).hexdigest()
        assert actual == digest, rel


def test_compose_runtime_data_is_identical_and_only_comments_changed() -> None:
    import difflib
    import subprocess

    import yaml

    for rel in ("docker-compose.yml", "docker-compose.ghcr.yml"):
        before = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        after = (ROOT / rel).read_text(encoding="utf-8")
        assert yaml.safe_load(before) == yaml.safe_load(after), rel
        for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm=""
        ):
            if line.startswith(("+++", "---", "@@")):
                continue
            if line.startswith(("+", "-")):
                content = line[1:].strip()
                assert not content or content.startswith("#"), (rel, line)


def test_handover_keeps_history_and_adds_s12_entry() -> None:
    text = (ROOT / "HANDOVER.md").read_text(encoding="utf-8")

    assert "S12" in text
    assert ".phase1-evidence/stages/S12/" in text
    assert "S11" in text
    assert "3843" in text  # historical S11 test number preserved
    assert "S13" in text and "S15" in text
    assert "start_selflearn.sh" in text
