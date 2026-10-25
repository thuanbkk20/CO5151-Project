import os

import pytest

from co5151_contracts.env import find_env_file, load_env_file


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "uv.lock").write_text("")
    sub = tmp_path / "eval" / "src"
    sub.mkdir(parents=True)
    return tmp_path, sub


def test_finds_env_at_repo_root_from_a_subfolder(repo):
    root, sub = repo
    (root / ".env").write_text("X=1\n")
    assert find_env_file(sub) == root / ".env"


def test_does_not_look_above_the_repo_root(repo):
    root, sub = repo
    (root.parent / ".env").write_text("X=1\n")
    try:
        assert find_env_file(sub) is None
    finally:
        (root.parent / ".env").unlink()


def test_shell_wins_and_export_prefix_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("CO5151_TEST_SHELL", "from-shell")
    monkeypatch.delenv("CO5151_TEST_FILE", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comment\nCO5151_TEST_SHELL=from-file\nexport CO5151_TEST_FILE='quoted'\n")
    load_env_file(env)
    assert os.environ["CO5151_TEST_SHELL"] == "from-shell"
    assert os.environ["CO5151_TEST_FILE"] == "quoted"
    monkeypatch.delenv("CO5151_TEST_FILE")


def test_missing_file_is_ignored(tmp_path):
    load_env_file(tmp_path / "none")
    load_env_file(None)
