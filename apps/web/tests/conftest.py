import os
from pathlib import Path

import pytest

# Importing chainlit has two side effects, both blocked before any test module imports it:
# - it loads `<current directory>/.env`, i.e. the developer's real LLM keys when pytest runs from the repo root,
#   for the whole test session (other packages' tests would then call the LLM with that key);
# - it reads, and writes if missing, `.chainlit/` in its app root; apps/web already has one.
os.environ["CHAINLIT_ENV_FILE"] = os.devnull
os.environ.setdefault("CHAINLIT_APP_ROOT", str(Path(__file__).resolve().parents[1]))

from co5151_advisor.llm import PROVIDERS

LLM_ENV = ["LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_REASONING_EFFORT", "LLM_TIMEOUT"]


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    for name in LLM_ENV + [p.key_env for p in PROVIDERS.values()]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"
