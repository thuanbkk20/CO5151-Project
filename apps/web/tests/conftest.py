import os
from pathlib import Path

import pytest

# Importing chainlit reads (and, if missing, writes) `.chainlit/` in its app root; point it at apps/web, which has one.
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
