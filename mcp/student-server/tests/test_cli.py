import os

import pytest

from student_server.auth import TokenSigner
from student_server.cli import load_env_file, main


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("STUDENT_MCP_TOKEN_SECRET", "cli-secret")


def test_issue_token_prints_verifiable_token(capsys, tmp_path):
    assert main(["--env-file", str(tmp_path / "none"), "issue-token", "sv003"]) == 0
    claims = TokenSigner(b"cli-secret").verify(capsys.readouterr().out.strip())
    assert claims.student_id == "2310003"


def test_issue_token_bad_password(capsys, tmp_path):
    assert main(["--env-file", str(tmp_path / "none"), "issue-token", "sv003", "--password", "x"]) == 1
    assert "invalid credentials" in capsys.readouterr().err


def test_accounts_lists_demo_users(capsys, tmp_path):
    assert main(["--env-file", str(tmp_path / "none"), "accounts"]) == 0
    out = capsys.readouterr().out
    assert "sv001" in out and "cvht01" in out and "pbkdf2" not in out


def test_env_file_does_not_override_shell(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nSTUDENT_MCP_TOKEN_SECRET=from-file\nSTUDENT_MCP_PORT='9100'\n")
    monkeypatch.delenv("STUDENT_MCP_PORT", raising=False)
    load_env_file(env)
    assert os.environ["STUDENT_MCP_TOKEN_SECRET"] == "cli-secret"
    assert os.environ["STUDENT_MCP_PORT"] == "9100"
    monkeypatch.delenv("STUDENT_MCP_PORT")


def test_stdio_requires_identity(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("STUDENT_MCP_SESSION_TOKEN", raising=False)
    assert main(["--env-file", str(tmp_path / "none"), "serve", "--stdio"]) == 2
