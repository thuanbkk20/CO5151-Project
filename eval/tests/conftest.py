import pytest


@pytest.fixture(autouse=True)
def no_repo_env_file(monkeypatch):
    monkeypatch.setattr("co5151_eval.cli.find_env_file", lambda: None)
