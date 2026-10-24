"""Tests for dependency metadata shared by the published packages."""

from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "metadata_path",
    [
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "packaging" / "deeptutor-cli" / "pyproject.toml",
    ],
)
def test_typer_dependency_does_not_request_removed_all_extra(metadata_path: Path) -> None:
    with metadata_path.open("rb") as file:
        dependencies = tomllib.load(file)["project"]["dependencies"]

    typer_requirements = [item for item in dependencies if item.startswith("typer")]
    assert typer_requirements == ["typer>=0.9.0"]


@pytest.mark.parametrize(
    "metadata_path",
    [
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "packaging" / "deeptutor-cli" / "pyproject.toml",
    ],
)
def test_mcp_client_is_a_core_dependency(metadata_path: Path) -> None:
    """`mcp` stays a core dependency (compatibility pending review).

    The shared MCP modules still import it, so a plain install must be able to
    load them. This fork's PageIndex overview runs through the existing RAG
    outline pipeline; the metadata must not claim an auto-injected PageIndex
    MCP client.
    """
    with metadata_path.open("rb") as file:
        dependencies = tomllib.load(file)["project"]["dependencies"]

    mcp_requirements = [item for item in dependencies if item.split(">")[0].strip() == "mcp"]
    assert mcp_requirements == ["mcp>=1.26.0,<2.0.0"]


def test_retired_partner_and_matrix_extras_are_absent() -> None:
    """The partner runtime is gone, so its extra install surfaces are gone too."""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as file:
        extras = tomllib.load(file)["project"]["optional-dependencies"]

    assert {"partners", "tutorbot", "matrix", "matrix-e2e"}.isdisjoint(extras)
    assert extras["all"] == ["deeptutor[math-animator]", "deeptutor[dev]"]


def test_requirements_mirror_the_core_mcp_client() -> None:
    """Docker/CI installs read requirements/, which must agree with pyproject."""
    requirements = REPOSITORY_ROOT / "requirements"
    root_text = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")
    server_text = (requirements / "server.txt").read_text(encoding="utf-8")
    cli_text = (requirements / "cli.txt").read_text(encoding="utf-8")

    assert "-r requirements/server.txt" in root_text
    assert "-r cli.txt" in server_text
    assert "mcp>=1.26.0,<2.0.0" in cli_text
    # The one non-transitive mirror is gone; no retired file is referenced.
    assert not (requirements / "partners.txt").exists()
    assert "partners.txt" not in root_text + server_text + cli_text
