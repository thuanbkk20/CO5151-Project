import json
from unittest.mock import MagicMock

import pytest

from co5151_advisor.llm import PROVIDERS, LLMClient

LLM_ENV = ["LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_REASONING_EFFORT", "LLM_TIMEOUT"]


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    for name in LLM_ENV + [p.key_env for p in PROVIDERS.values()]:
        monkeypatch.delenv(name, raising=False)


def _sent_options(client: LLMClient, **kwargs) -> dict:
    api = MagicMock()
    api.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="ok"))]
    client._client = api
    client.generate("prompt", **kwargs)
    return api.chat.completions.create.call_args.kwargs


def test_gemini_is_the_default_and_never_sends_seed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    client = LLMClient()
    assert client.describe() == {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }
    assert client.is_available
    sent = _sent_options(client, seed=7)
    assert "seed" not in sent
    assert "reasoning_effort" not in sent


def test_openai_reads_its_own_key_and_sends_seed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    client = LLMClient()
    assert (client.provider, client.api_key, client.base_url) == ("openai", "o-key", "https://api.openai.com/v1")
    sent = _sent_options(client, seed=7)
    assert sent["seed"] == 7
    assert "reasoning_effort" not in sent


def test_seed_is_not_sent_unless_given(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert "seed" not in _sent_options(LLMClient(api_key="o-key"))


def test_generic_overrides_point_any_provider_elsewhere(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "my-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_API_KEY", "local")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    client = LLMClient()
    assert (client.model, client.base_url, client.api_key) == ("my-model", "http://localhost:11434/v1", "local")
    assert _sent_options(client)["reasoning_effort"] == "low"


def test_arguments_win_over_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    client = LLMClient(provider="kimi", model="kimi-x", api_key="k")
    assert (client.provider, client.model, client.base_url) == ("kimi", "kimi-x", PROVIDERS["kimi"].base_url)


def test_empty_values_in_env_fall_back_to_the_profile(monkeypatch):
    for name in LLM_ENV:
        monkeypatch.setenv(name, "")
    client = LLMClient()
    assert (client.provider, client.model, client.timeout) == ("gemini", "gemini-3.5-flash-lite", 60.0)
    assert not client.is_available


def test_unknown_provider_fails_loudly():
    with pytest.raises(ValueError, match="gemini"):
        LLMClient(provider="gpt5-typo")


def test_timeout_and_retries_are_bounded(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "5")
    client = LLMClient(api_key="k")
    assert (client._client.timeout, client._client.max_retries) == (5.0, 1)


def test_eval_report_records_the_llm_configuration(tmp_path, monkeypatch):
    from co5151_eval import cli

    monkeypatch.setattr(cli, "find_env_file", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert cli.main(["run", "--agent", "co5151_advisor.eval_adapter:make_agent", "--only", "P08",
                     "--out", str(tmp_path)]) == 0  # fmt: skip
    config = json.loads((tmp_path / "summary.json").read_text())["agent_config"]
    assert config["llm"]["provider"] == "openai"
    assert config["regulation_source"] == "ToolRegulationSource"
    assert "Cấu hình:" in (tmp_path / "summary.md").read_text()
