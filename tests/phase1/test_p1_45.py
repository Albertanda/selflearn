"""P1-45: the current CLI surface and active command documentation.

The command registration is exercised as a real Typer app in an isolated HOME,
not as a source-string assertion.  Docs checks only reject *active*
recommendations (`deeptutor partner ...`, `.[partners]` install lines); the
current-fork note that says those features are gone is expected to remain.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

from typer.testing import CliRunner

from deeptutor_cli.main import app

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "deeptutor_cli" / "README.md"
SKILL = ROOT / "SKILL.md"
AGENTS = ROOT / "AGENTS.md"

REMOVED_COMMANDS = {"book", "partner"}
SUPPORTED_GROUPS = {
    "chat",
    "kb",
    "skill",
    "skills",
    "memory",
    "plugin",
    "config",
    "session",
    "notebook",
    "provider",
}
SUPPORTED_COMMANDS = {"run", "start", "serve", "init"}


def isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "PYTHONPATH": str(ROOT),
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    return env


def test_real_typer_help_succeeds_in_an_isolated_home(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "deeptutor_cli.main", "--help"],
        cwd=tmp_path,
        env=isolated_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output = completed.stdout + completed.stderr
    for name in sorted(SUPPORTED_GROUPS | SUPPORTED_COMMANDS):
        assert re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", output), name
    for removed in REMOVED_COMMANDS:
        assert not re.search(rf"^\s*{removed}\s", output, re.MULTILINE), removed


def test_registered_commands_match_the_supported_surface() -> None:
    groups = {group.name for group in app.registered_groups}
    commands = {
        command.name or getattr(command.callback, "__name__", "")
        for command in app.registered_commands
    }

    assert SUPPORTED_GROUPS <= groups
    assert SUPPORTED_COMMANDS <= commands
    assert REMOVED_COMMANDS.isdisjoint(groups | commands)


def test_supported_subcommands_load_without_missing_modules() -> None:
    runner = CliRunner()
    for args in (
        ["kb", "--help"],
        ["memory", "--help"],
        ["start", "--help"],
        ["provider", "--help"],
        ["notebook", "--help"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.output)
        assert "Traceback" not in result.output


def test_removed_backing_modules_are_absent_and_not_imported(tmp_path: Path) -> None:
    for module in ("deeptutor_cli.book", "deeptutor_cli.partner"):
        assert importlib.util.find_spec(module) is None, module
        assert module not in sys.modules, module

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from deeptutor_cli.main import app; print(len(app.registered_groups))",
        ],
        cwd=tmp_path,
        env=isolated_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert int(completed.stdout.strip()) >= len(SUPPORTED_GROUPS)


def _active_command_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("deeptutor partner", "deeptutor book"))
    ]


def test_active_docs_do_not_recommend_removed_commands_or_extras() -> None:
    for path in (README, SKILL, AGENTS):
        text = path.read_text(encoding="utf-8")
        assert not _active_command_lines(text), path
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(".[partners]"), path
            assert not stripped.startswith(".[tutorbot]"), path
            assert not stripped.startswith(".[matrix]"), path
            assert not stripped.startswith(".[matrix-e2e]"), path
        assert ".[partners]" not in text or "removed" in text or "not part" in text, path


def test_active_docs_keep_the_supported_install_and_command_surface() -> None:
    readme = README.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")

    for text in (readme, skill):
        assert "deeptutor run" in text
        assert "deeptutor kb" in text
    assert "deeptutor serve" in readme
    assert "deeptutor memory" in skill
    assert ".[math-animator]" in readme
    assert ".[all]" in readme
    assert "server + math-animator" in readme.lower()

    assert "Current Fork Differences" in agents
    assert "not registered" in agents
    assert ".[math-animator]" in agents
    assert ".[server]" in agents
    assert "requirements/server.txt" in agents


def test_removed_features_are_explained_not_advertised() -> None:
    readme = README.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")

    assert "已移除 Partners" in readme
    assert "remove the Partner" in skill or "does not ship the Partner" in skill
    assert "上游 DeepTutor" in readme
    assert "upstream DeepTutor" in skill
