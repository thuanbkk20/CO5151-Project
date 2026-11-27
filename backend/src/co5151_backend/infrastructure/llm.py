"""LLMs behind OpenAI-compatible endpoints. One `Provider` per vendor; keys and overrides come from the environment.

Parameters that not every provider accepts (`response_format` json_schema, `reasoning_effort`) are only sent when the
profile or an environment variable turns them on: an OpenAI-compatible endpoint may answer 400 to an unknown one.
One endpoint can serve several model families (Azure AI Foundry), so a `ModelProfile` may change them per model.
"""

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from ..application.ports import ChatTurn, Completion
from ..domain.errors import InvalidRequest, LLMError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    base_url: str
    # What users can pick in the chat settings; the first one is the default
    models: tuple[str, ...]
    key_env: str
    reasoning_effort: str | None = None
    # Accepts `response_format={"type": "json_schema", ...}` (structured output)
    json_schema: bool = False
    # Name of the output-token limit: OpenAI wants max_completion_tokens, most compatible endpoints max_tokens
    max_tokens_param: str = "max_tokens"
    # Variable holding the base URL when it depends on the customer's resource (Azure); it then replaces `base_url`
    base_url_env: str | None = None
    # Accepts `seed` (best-effort reproducible sampling); documented by OpenAI and Azure OpenAI, not tried elsewhere
    seed: bool = False

    @property
    def model(self) -> str:
        """The default model."""
        return self.models[0]


# Model lists are kept by hand: update them when a vendor adds or retires a model, or when a deployment changes
# (Azure: infra/azure/openai.tf, foundry.tf). A model that needs other parameters also goes into MODEL_PROFILES.
PROVIDERS: dict[str, Provider] = {
    # Names from GET /v1beta/models (27/11); gemini-2.5-flash is listed there but answers 404 "no longer available
    # to new users"
    "gemini": Provider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        models=("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"),
        key_env="GEMINI_API_KEY",
        json_schema=True,
    ),
    "openai": Provider(
        base_url="https://api.openai.com/v1",
        models=("gpt-4.1-mini", "gpt-5-mini"),
        key_env="OPENAI_API_KEY",
        json_schema=True,
        max_tokens_param="max_completion_tokens",
        seed=True,
    ),
    "kimi": Provider(
        base_url="https://opencode.ai/inference/openai/v1",
        models=("kimi-k3",),
        key_env="OPENCODE_API_KEY",
    ),
    # Azure OpenAI v1 endpoint (https://<resource>.openai.azure.com/openai/v1/); model = deployment name
    "azure": Provider(
        base_url="",
        models=("gpt-4.1-mini",),
        key_env="AZURE_OPENAI_API_KEY",
        json_schema=True,
        max_tokens_param="max_completion_tokens",
        base_url_env="AZURE_OPENAI_BASE_URL",
        seed=True,
    ),
    # Azure AI Foundry: several model families behind one v1 endpoint; MODEL_PROFILES adapts the parameters per model
    "foundry": Provider(
        base_url="",
        models=("gpt-5-mini", "gpt-oss-120b", "Llama-3.3-70B-Instruct", "Phi-4"),
        key_env="AZURE_FOUNDRY_API_KEY",
        json_schema=True,
        base_url_env="AZURE_FOUNDRY_BASE_URL",
    ),
}


@dataclass(frozen=True)
class ModelProfile:
    """What one model takes that differs from its provider's defaults; None keeps the provider's value."""

    # False: the model only accepts its default temperature (the gpt-5 family answers 400 to temperature=0)
    temperature: bool = True
    json_schema: bool | None = None
    max_tokens_param: str | None = None
    reasoning_effort: str | None = None
    # Reasoning tokens count against the output limit: a 32-token router call would come back empty without room
    reasoning_headroom: int = 0
    seed: bool | None = None


# Keyed by model (deployment) name, whatever the provider. Values from one probe call per model on Azure AI Foundry
# (docs/design/foundry-models.md).
MODEL_PROFILES: dict[str, ModelProfile] = {
    # Even at `minimal` it spent all of 1024 + 256 tokens reasoning on an answer prompt (finish_reason=length, 27/11)
    "gpt-5-mini": ModelProfile(temperature=False, max_tokens_param="max_completion_tokens",
                               reasoning_effort="minimal", reasoning_headroom=2048),
    "gpt-oss-120b": ModelProfile(max_tokens_param="max_completion_tokens", reasoning_effort="low",
                                 reasoning_headroom=512),
    "Phi-4": ModelProfile(json_schema=False),
}  # fmt: skip
DEFAULT_PROVIDER = "gemini"
DEFAULT_TIMEOUT_S = 60.0
MAX_RETRIES = 1


class OpenAICompatibleChatModel:
    def __init__(
        self,
        provider: str,
        profile: Provider,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        seed: int | None = None,
    ):
        self.provider = provider
        self.model = model or profile.model
        self.base_url = base_url or profile.base_url
        self._profile = profile
        self._model_profile = MODEL_PROFILES.get(self.model, ModelProfile())
        self._reasoning_effort = reasoning_effort or self._model_profile.reasoning_effort or profile.reasoning_effort
        supports_seed = profile.seed if self._model_profile.seed is None else self._model_profile.seed
        # The seed actually sent (None: not asked for, or the model does not take one); traces record it
        self.seed = seed if supports_seed else None
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=api_key, timeout=timeout, max_retries=MAX_RETRIES)

    def options(self, max_output_tokens: int, json_schema: dict[str, Any] | None) -> dict[str, Any]:
        provider, model = self._profile, self._model_profile
        limit = max_output_tokens + model.reasoning_headroom
        options: dict[str, Any] = {model.max_tokens_param or provider.max_tokens_param: limit}
        if model.temperature:
            options["temperature"] = 0.0
        if self._reasoning_effort:
            options["reasoning_effort"] = self._reasoning_effort
        supports_schema = provider.json_schema if model.json_schema is None else model.json_schema
        if json_schema and supports_schema:
            options["response_format"] = json_schema
        if self.seed is not None:
            options["seed"] = self.seed
        return options

    async def complete(
        self,
        prompt: str,
        *,
        system: str,
        history: Sequence[ChatTurn] = (),
        max_output_tokens: int,
        json_schema: dict[str, Any] | None = None,
    ) -> Completion:
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t.role, "content": t.content} for t in history if t.role in ("user", "assistant")]
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self.model, messages=messages, **self.options(max_output_tokens, json_schema)
            )
        except Exception as e:
            logger.warning("LLM call to %s/%s failed: %s", self.provider, self.model, e)
            raise LLMError(f"{type(e).__name__}: {e}") from e
        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "").strip() if choice else ""
        if not text:
            # "length": the output limit was used up (reasoning tokens count too); "content_filter": blocked
            reason = getattr(choice, "finish_reason", None) if choice else "no choices"
            used = getattr(response.usage, "completion_tokens", None)
            raise LLMError(f"empty reply (finish_reason={reason}, output_tokens={used})")
        usage = response.usage
        return Completion(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class ProviderChatModels:
    """The providers that have a key (and a base URL, for Azure) in the environment, and the models to pick from.

    `LLM_PROVIDER` is the default. `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_REASONING_EFFORT` override
    the profile of that default provider only, e.g. to point it at a local OpenAI-compatible server; `LLM_MODEL` also
    goes first in that provider's model list.
    """

    def __init__(self, env: Mapping[str, str] | None = None):
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            return (env.get(name) or "").strip() or None

        self._default = (get("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()
        if self._default not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER {self._default!r}; choose one of {sorted(PROVIDERS)}")
        self._overrides = {k: get(f"LLM_{k.upper()}") for k in ("model", "base_url", "api_key", "reasoning_effort")}
        self._keys = {name: get(p.key_env) for name, p in PROVIDERS.items()}
        self._base_urls = {name: (get(p.base_url_env) if p.base_url_env else None) or p.base_url
                           for name, p in PROVIDERS.items()}  # fmt: skip
        if self._overrides["api_key"]:
            self._keys[self._default] = self._overrides["api_key"]
        if self._overrides["base_url"]:
            self._base_urls[self._default] = self._overrides["base_url"]
        self._timeout = float(get("LLM_TIMEOUT") or DEFAULT_TIMEOUT_S)
        seed = get("LLM_SEED")
        self._seed = int(seed) if seed else None

    def providers(self) -> list[str]:
        return [name for name in PROVIDERS if self._keys[name] and self._base_urls[name]]

    def default_provider(self) -> str:
        available = self.providers()
        return self._default if self._default in available or not available else available[0]

    def models(self, provider: str) -> list[str]:
        if provider not in PROVIDERS:
            return []
        listed = list(PROVIDERS[provider].models)
        override = self._overrides["model"] if provider == self._default else None
        return [override, *(m for m in listed if m != override)] if override else listed

    def create(self, provider: str | None, model: str | None) -> OpenAICompatibleChatModel | None:
        name = (provider or self.default_provider()).lower()
        if name not in PROVIDERS:
            raise InvalidRequest(f"Unknown LLM provider {name!r}; choose one of {sorted(PROVIDERS)}")
        if name not in self.providers():
            return None
        overrides = self._overrides if name == self._default else {}
        return OpenAICompatibleChatModel(
            name,
            PROVIDERS[name],
            api_key=self._keys[name],
            model=model or self.models(name)[0],
            base_url=self._base_urls[name],
            reasoning_effort=overrides.get("reasoning_effort"),
            timeout=self._timeout,
            seed=self._seed,
        )
