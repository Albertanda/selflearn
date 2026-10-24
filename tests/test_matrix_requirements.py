"""The retired partner/Matrix install surfaces stay absent.

The partner runtime and both Matrix mirrors were removed by P1-44.  These
assertions replace the old positive tests that encoded those files: no install
profile may pull the retired IM SDKs, while the supported server profile keeps
its real dependencies.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_retired_matrix_and_partner_mirrors_are_gone() -> None:
    for name in ("matrix.txt", "matrix-e2e.txt", "partners.txt"):
        assert not (ROOT / "requirements" / name).exists()
        assert not (ROOT / "requirements" / name).is_symlink()


def test_default_server_requirements_do_not_pull_matrix_or_im_sdks() -> None:
    chain = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("requirements.txt", "requirements/server.txt", "requirements/cli.txt")
    )

    for dependency in (
        "matrix-nio",
        "mistune",
        "nh3",
        "python-telegram-bot",
        "wecom-aibot-sdk",
        "lark-oapi",
        "dingtalk-stream",
        "slack-sdk",
        "qq-botpy",
        "zulip",
    ):
        assert dependency not in chain


def test_supported_server_requirements_keep_their_real_dependencies() -> None:
    root_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    server_text = (ROOT / "requirements" / "server.txt").read_text(encoding="utf-8")
    cli_text = (ROOT / "requirements" / "cli.txt").read_text(encoding="utf-8")

    assert "-r requirements/server.txt" in root_text
    assert "-r cli.txt" in server_text
    for dependency in ("fastapi>=", "uvicorn[standard]>=", "websockets>=", "python-multipart>="):
        assert dependency in server_text
    assert "mcp>=1.26.0,<2.0.0" in cli_text
