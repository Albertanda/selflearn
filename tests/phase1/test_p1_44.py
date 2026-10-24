"""P1-44: retired partner/Matrix packaging surfaces and the retained MCP SDK.

These are metadata-graph assertions over the real files (tomllib + recursive
``-r`` resolution), not string replacement checks: the install graph must have
no broken include and no path from root/server/all to a retired IM SDK, while
CLI/server/manim/parse/MCP and shared runtime dependencies stay intact.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements"

RETIRED_EXTRAS = {"partners", "tutorbot", "matrix", "matrix-e2e"}
RETIRED_PACKAGES = {
    "python-telegram-bot",
    "wecom-aibot-sdk",
    "lark-oapi",
    "dingtalk-stream",
    "slack-sdk",
    "slackify-markdown",
    "qq-botpy",
    "python-socketio",
    "msgpack",
    "python-socks",
    "socksio",
    "websocket-client",
    "zulip",
    "matrix-nio",
    "mistune",
    "nh3",
    "pyjwt",
    "qrcode",
}


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def project_metadata(path: Path) -> dict:
    return load_toml(path)["project"]


def distribution_extras(path: Path) -> dict[str, list[str]]:
    return project_metadata(path).get("optional-dependencies", {})


def requirement_name(spec: str) -> str:
    """Canonical distribution name from one requirement line."""
    token = spec.split(";", 1)[0].strip()
    token = re.split(r"[<>=!~\[\s@]", token, maxsplit=1)[0]
    return token.strip().lower().replace("_", "-")


def resolve_requirements(path: Path) -> tuple[list[str], set[Path]]:
    """Recursively resolve ``-r`` includes; fail on any missing target."""
    specs: list[str] = []
    seen: set[Path] = set()

    def visit(current: Path) -> None:
        resolved = current.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        assert resolved.is_file(), f"missing requirements include: {resolved}"
        for raw in resolved.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-r "):
                visit(resolved.parent / line[3:].strip())
                continue
            if line.startswith("-"):
                continue
            specs.append(line)

    visit(path)
    return specs, seen


def extra_closure(
    extras: dict[str, list[str]], name: str, seen: set[str] | None = None
) -> list[str]:
    """Resolve local ``deeptutor[extra]`` references inside one extra."""
    if seen is None:
        seen = set()
    if name in seen:
        return []
    seen.add(name)
    assert name in extras, f"missing extra: {name}"
    specs: list[str] = []
    for spec in extras[name]:
        match = re.fullmatch(r"deeptutor\[([^\]]+)\]", spec.strip())
        if match:
            for nested in match.group(1).split(","):
                specs.extend(extra_closure(extras, nested.strip(), seen))
        else:
            specs.append(spec)
    return specs


def names(specs: list[str]) -> set[str]:
    return {requirement_name(spec) for spec in specs}


def test_retired_extras_are_gone_and_all_only_composes_retained_extras() -> None:
    extras = distribution_extras(ROOT / "pyproject.toml")

    assert RETIRED_EXTRAS.isdisjoint(extras)
    assert extras["all"] == ["deeptutor[math-animator]", "deeptutor[dev]"]
    referenced = re.findall(r"deeptutor\[([^\]]+)\]", " ".join(extras["all"]))
    assert referenced
    for name in referenced:
        assert name in extras, f"all references missing extra {name}"


def test_all_and_server_graphs_contain_no_retired_im_sdk() -> None:
    metadata = project_metadata(ROOT / "pyproject.toml")
    extras = metadata["optional-dependencies"]
    core = metadata["dependencies"]

    for profile in ("all", "server", "cli", "dev", "parse", "math-animator"):
        specs = core + extra_closure(extras, profile)
        assert names(specs).isdisjoint(RETIRED_PACKAGES), profile


def test_root_requirements_resolve_recursively_to_the_server_profile() -> None:
    root_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    specs, files = resolve_requirements(ROOT / "requirements.txt")

    assert "-r requirements/server.txt" in root_text
    assert files == {
        (ROOT / "requirements.txt").resolve(),
        (REQUIREMENTS / "server.txt").resolve(),
        (REQUIREMENTS / "cli.txt").resolve(),
    }
    assert names(specs).isdisjoint(RETIRED_PACKAGES)
    assert {"mcp", "fastapi", "uvicorn", "websockets", "anthropic"} <= names(specs)


def test_retired_mirrors_are_absent_and_no_broken_include_remains() -> None:
    for name in ("partners.txt", "matrix.txt", "matrix-e2e.txt"):
        assert not (REQUIREMENTS / name).exists()

    for path in REQUIREMENTS.glob("*.txt"):
        resolve_requirements(path)

    root_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "partners.txt" not in root_text
    assert "matrix.txt" not in root_text


def test_cli_server_manim_parse_and_mcp_surfaces_stay_intact() -> None:
    metadata = project_metadata(ROOT / "pyproject.toml")
    extras = metadata["optional-dependencies"]
    core_names = names(metadata["dependencies"])

    assert {"cli", "server", "math-animator", "parse"} <= set(extras)
    assert {"parse-markitdown", "parse-docling", "parse-pymupdf4llm", "parse-liteparse"} <= set(
        extras
    )
    assert "mcp" in core_names

    packaging = project_metadata(ROOT / "packaging" / "deeptutor-cli" / "pyproject.toml")
    packaging_names = names(packaging["dependencies"])
    assert "mcp" in packaging_names
    assert "typer" in packaging_names
    assert "llama-index" in packaging_names

    cli_text = (REQUIREMENTS / "cli.txt").read_text(encoding="utf-8")
    server_text = (REQUIREMENTS / "server.txt").read_text(encoding="utf-8")
    manim_text = (REQUIREMENTS / "math-animator.txt").read_text(encoding="utf-8")
    assert "mcp>=1.26.0,<2.0.0" in cli_text
    assert "websockets>=12.0" in server_text
    assert "manim>=0.19.0" in manim_text
    assert "manim>=0.19.0" in extras["math-animator"]


def test_requirement_versions_agree_with_pyproject_for_shared_dependencies() -> None:
    metadata = project_metadata(ROOT / "pyproject.toml")
    extras = metadata["optional-dependencies"]
    packaging = project_metadata(ROOT / "packaging" / "deeptutor-cli" / "pyproject.toml")

    cli_specs, _ = resolve_requirements(REQUIREMENTS / "cli.txt")
    cli_by_name = {requirement_name(spec): spec.split(";")[0].strip() for spec in cli_specs}

    mcp_versions = {
        spec.split(";")[0].strip()
        for spec in metadata["dependencies"] + packaging["dependencies"]
        if requirement_name(spec) == "mcp"
    }
    assert mcp_versions == {"mcp>=1.26.0,<2.0.0"}
    assert cli_by_name["mcp"] == "mcp>=1.26.0,<2.0.0"

    server_specs = extras["server"]
    websockets = [spec for spec in server_specs if requirement_name(spec) == "websockets"]
    assert websockets == ["websockets>=12.0"]
    assert "websockets>=12.0" in (REQUIREMENTS / "server.txt").read_text(encoding="utf-8")


def test_docker_default_install_uses_root_profile_without_retired_mirrors() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY requirements.txt ./" in dockerfile
    assert "pip install -r requirements.txt" in dockerfile
    for retired in ("partners.txt", "matrix.txt", "matrix-e2e.txt"):
        assert retired not in dockerfile


def test_mcp_comments_are_compatibility_pending_not_false_injection_claims() -> None:
    paths = (
        ROOT / "pyproject.toml",
        REQUIREMENTS / "cli.txt",
        ROOT / "packaging" / "deeptutor-cli" / "pyproject.toml",
    )
    stale = (
        "injected whenever",
        "built-in PageIndex MCP server",
        "pageindex server whenever",
        "自动注入",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "mcp>=1.26.0,<2.0.0" in text, path
        assert "compatibility pending review" in text.lower(), path
        for phrase in stale:
            assert phrase not in text, f"{path}: {phrase}"
