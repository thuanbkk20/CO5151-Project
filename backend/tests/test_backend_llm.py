"""LLM adapter: what is sent to each provider. The OpenAI client is mocked: no test calls a real LLM."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from co5151_backend.application.ports import ChatTurn
from co5151_backend.domain.errors import InvalidRequest, LLMError
from co5151_backend.infrastructure.llm import MODEL_PROFILES, PROVIDERS, ProviderChatModels

pytestmark = pytest.mark.anyio
SCHEMA = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}


def _reply(text="ok", prompt_tokens=7, completion_tokens=3):
    message = SimpleNamespace(content=text)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _mocked(model, reply=None, error=None):
    create = AsyncMock(return_value=reply or _reply(), side_effect=error)
    model._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return create


def test_only_providers_with_a_key_are_offered():
    models = ProviderChatModels({"OPENAI_API_KEY": "o"})
    assert models.providers() == ["openai"] and models.default_provider() == "openai"
    assert models.create("gemini", None) is None
    assert ProviderChatModels({}).providers() == [] and ProviderChatModels({}).default_provider() == "gemini"
    with pytest.raises(InvalidRequest):
        models.create("gpt5-typo", None)
    with pytest.raises(ValueError):
        ProviderChatModels({"LLM_PROVIDER": "typo"})


async def test_request_carries_history_limit_and_schema_only_where_supported():
    models = ProviderChatModels({"GEMINI_API_KEY": "g", "OPENCODE_API_KEY": "k", "OPENAI_API_KEY": "o"})
    gemini = models.create(None, None)
    assert (gemini.provider, gemini.model) == ("gemini", PROVIDERS["gemini"].model)
    create = _mocked(gemini)
    history = [ChatTurn("user", "hỏi"), ChatTurn("assistant", "đáp"), ChatTurn("system", "bỏ qua")]
    done = await gemini.complete("câu hỏi", system="sys", history=history, max_output_tokens=50, json_schema=SCHEMA)
    sent = create.call_args.kwargs
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "user"]
    assert sent["max_tokens"] == 50 and sent["response_format"] == SCHEMA and "reasoning_effort" not in sent
    assert (done.text, done.input_tokens, done.output_tokens) == ("ok", 7, 3)

    kimi = models.create("kimi", "kimi-x")
    create = _mocked(kimi)
    await kimi.complete("q", system="s", max_output_tokens=10, json_schema=SCHEMA)
    assert "response_format" not in create.call_args.kwargs and kimi.model == "kimi-x"

    openai = models.create("openai", None)
    create = _mocked(openai)
    await openai.complete("q", system="s", max_output_tokens=10)
    assert create.call_args.kwargs["max_completion_tokens"] == 10


async def test_azure_needs_its_resource_url_and_calls_the_deployment():
    assert "azure" not in ProviderChatModels({"AZURE_OPENAI_API_KEY": "a"}).providers()
    url = "https://x.openai.azure.com/openai/v1/"
    models = ProviderChatModels({"LLM_PROVIDER": "azure", "AZURE_OPENAI_API_KEY": "a", "AZURE_OPENAI_BASE_URL": url})
    assert models.providers() == ["azure"] and models.default_provider() == "azure"
    azure = models.create(None, None)
    assert (azure.base_url, azure.model) == (url, "gpt-4.1-mini")
    create = _mocked(azure)
    await azure.complete("q", system="s", max_output_tokens=10, json_schema=SCHEMA)
    sent = create.call_args.kwargs
    assert sent["model"] == "gpt-4.1-mini" and sent["max_completion_tokens"] == 10 and sent["response_format"] == SCHEMA


async def test_model_profile_changes_parameters_per_model():
    url = "https://x.openai.azure.com/openai/v1/"
    models = ProviderChatModels({"AZURE_OPENAI_API_KEY": "a", "AZURE_OPENAI_BASE_URL": url})

    reasoning = models.create("azure", "gpt-5-mini")
    create = _mocked(reasoning)
    await reasoning.complete("q", system="s", max_output_tokens=32, json_schema=SCHEMA)
    sent = create.call_args.kwargs
    assert "temperature" not in sent and sent["reasoning_effort"] == "minimal" and sent["response_format"] == SCHEMA
    assert sent["max_completion_tokens"] == 32 + MODEL_PROFILES["gpt-5-mini"].reasoning_headroom

    no_schema = models.create("azure", "Phi-4")
    create = _mocked(no_schema)
    await no_schema.complete("q", system="s", max_output_tokens=10, json_schema=SCHEMA)
    sent = create.call_args.kwargs
    assert "response_format" not in sent and sent["temperature"] == 0.0 and sent["max_completion_tokens"] == 10


def test_every_provider_has_a_model_list_and_its_default_comes_first():
    for name, provider in PROVIDERS.items():
        assert provider.models and provider.model == provider.models[0], name
        assert len(set(provider.models)) == len(provider.models), name


async def test_foundry_offers_its_deployments():
    url = "https://x.openai.azure.com/openai/v1/"
    models = ProviderChatModels({"AZURE_FOUNDRY_API_KEY": "f", "AZURE_FOUNDRY_BASE_URL": url})
    assert models.providers() == ["foundry"] and models.models("foundry") == list(PROVIDERS["foundry"].models)
    assert models.models("typo") == []
    default = models.create("foundry", None)
    assert (default.base_url, default.model) == (url, PROVIDERS["foundry"].model)
    assert models.create("foundry", "Phi-4").model == "Phi-4"


def test_llm_model_goes_first_in_the_default_providers_list():
    models = ProviderChatModels({"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-2.5-flash", "GEMINI_API_KEY": "g"})
    assert models.models("gemini")[0] == "gemini-2.5-flash"
    assert models.models("gemini").count("gemini-2.5-flash") == 1
    assert models.models("openai") == list(PROVIDERS["openai"].models)


async def test_overrides_apply_to_the_default_provider_only():
    env = {"LLM_PROVIDER": "openai", "LLM_API_KEY": "local", "LLM_BASE_URL": "http://localhost:11434/v1",
           "LLM_MODEL": "my-model", "LLM_REASONING_EFFORT": "low", "GEMINI_API_KEY": "g"}  # fmt: skip
    models = ProviderChatModels(env)
    local = models.create(None, None)
    assert (local.provider, local.model, local.base_url) == ("openai", "my-model", "http://localhost:11434/v1")
    create = _mocked(local)
    await local.complete("q", system="s", max_output_tokens=10)
    assert create.call_args.kwargs["reasoning_effort"] == "low"
    gemini = models.create("gemini", None)
    assert (gemini.model, gemini.base_url) == (PROVIDERS["gemini"].model, PROVIDERS["gemini"].base_url)


async def test_failures_and_empty_replies_raise():
    model = ProviderChatModels({"GEMINI_API_KEY": "g"}).create(None, None)
    _mocked(model, error=RuntimeError("429 quota"))
    with pytest.raises(LLMError, match="quota"):
        await model.complete("q", system="s", max_output_tokens=10)
    _mocked(model, reply=_reply(text="  "))
    with pytest.raises(LLMError, match="empty"):
        await model.complete("q", system="s", max_output_tokens=10)
    cut = _reply(text=None, completion_tokens=10)
    cut.choices[0].finish_reason = "length"
    _mocked(model, reply=cut)
    with pytest.raises(LLMError, match=r"finish_reason=length, output_tokens=10"):
        await model.complete("q", system="s", max_output_tokens=10)


def test_timeout_and_retries_are_bounded():
    model = ProviderChatModels({"GEMINI_API_KEY": "g", "LLM_TIMEOUT": "5"}).create(None, None)
    assert (model._client.timeout, model._client.max_retries) == (5.0, 1)
