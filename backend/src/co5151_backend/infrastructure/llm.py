"""LLMs behind OpenAI-compatible endpoints. One `Provider` per vendor; keys and overrides come from the environment.

Parameters that not every provider accepts (`response_format` json_schema, `reasoning_effort`) are only sent when the
profile or an environment variable turns them on: an OpenAI-compatible endpoint may answer 400 to an unknown one.
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
    model: str
    key_env: str
    reasoning_effort: str | None = None
    # Accepts `response_format={"type": "json_schema", ...}` (structured output)
    json_schema: bool = False
    # Name of the output-token limit: OpenAI wants max_completion_tokens, most compatible endpoints max_tokens
    max_tokens_param: str = "max_tokens"


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.5-flash-lite",
        key_env="GEMINI_API_KEY",
        json_schema=True,
    ),
    "openai": Provider(
        base_url="https://api.openai.com/v1",
        model="gpt-4.1-mini",
        key_env="OPENAI_API_KEY",
        json_schema=True,
        max_tokens_param="max_completion_tokens",
    ),
    "kimi": Provider(base_url="https://opencode.ai/inference/openai/v1", model="kimi-k3", key_env="OPENCODE_API_KEY"),
}
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
    ):
        self.provider = provider
        self.model = model or profile.model
        self.base_url = base_url or profile.base_url
        self._profile = profile
        self._reasoning_effort = reasoning_effort or profile.reasoning_effort
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=api_key, timeout=timeout, max_retries=MAX_RETRIES)

    def options(self, max_output_tokens: int, json_schema: dict[str, Any] | None) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": 0.0, self._profile.max_tokens_param: max_output_tokens}
        if self._reasoning_effort:
            options["reasoning_effort"] = self._reasoning_effort
        if json_schema and self._profile.json_schema:
            options["response_format"] = json_schema
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
        text = (response.choices[0].message.content or "").strip() if response.choices else ""
        if not text:
            raise LLMError("empty reply")
        usage = response.usage
        return Completion(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class ProviderChatModels:
    """The providers that have a key in the environment.

    `LLM_PROVIDER` is the default. `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_REASONING_EFFORT` override
    the profile of that default provider only, e.g. to point it at a local OpenAI-compatible server.
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
        if self._overrides["api_key"]:
            self._keys[self._default] = self._overrides["api_key"]
        self._timeout = float(get("LLM_TIMEOUT") or DEFAULT_TIMEOUT_S)

    def providers(self) -> list[str]:
        return [name for name in PROVIDERS if self._keys[name]]

    def default_provider(self) -> str:
        available = self.providers()
        return self._default if self._default in available or not available else available[0]

    def create(self, provider: str | None, model: str | None) -> OpenAICompatibleChatModel | None:
        name = (provider or self.default_provider()).lower()
        if name not in PROVIDERS:
            raise InvalidRequest(f"Unknown LLM provider {name!r}; choose one of {sorted(PROVIDERS)}")
        if not self._keys[name]:
            return None
        overrides = self._overrides if name == self._default else {}
        return OpenAICompatibleChatModel(
            name,
            PROVIDERS[name],
            api_key=self._keys[name],
            model=model or overrides.get("model"),
            base_url=overrides.get("base_url"),
            reasoning_effort=overrides.get("reasoning_effort"),
            timeout=self._timeout,
        )
