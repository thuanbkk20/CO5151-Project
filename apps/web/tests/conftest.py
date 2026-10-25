import pytest

from co5151_advisor.llm import PROVIDERS

LLM_ENV = ["LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_REASONING_EFFORT", "LLM_TIMEOUT"]


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    for name in LLM_ENV + [p.key_env for p in PROVIDERS.values()]:
        monkeypatch.delenv(name, raising=False)
