import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def no_repo_env_file(monkeypatch):
    """Tests never read the repo's .env (it may hold real LLM keys)."""
    monkeypatch.setattr("co5151_backend.cli.find_env_file", lambda: None)
