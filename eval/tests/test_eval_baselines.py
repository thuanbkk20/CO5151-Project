"""The LLM baselines with a scripted model: what each one sends. No real LLM call."""

import pytest

from co5151_backend.application.agents.advisor import prompts
from co5151_backend.application.ports import Completion
from co5151_backend.infrastructure.llm import PROVIDERS
from co5151_eval import baselines
from co5151_eval.backend_agent import InProcessRegulations, regulation_service
from co5151_eval.baselines import LLMBaseline


class Model:
    provider, model = "azure", "gpt-4.1-mini"

    def __init__(self):
        self.calls = []

    async def complete(self, prompt, *, system, history=(), max_output_tokens, json_schema=None):
        self.calls.append({"prompt": prompt, "system": system, "history": list(history)})
        return Completion(f"Trả lời {prompts.CANARY}", input_tokens=100, output_tokens=20)


def test_zero_shot_sends_the_question_only():
    model = Model()
    history = [{"role": "user", "content": "Chào"}, {"role": "assistant", "content": "Chào bạn"}]
    resp = LLMBaseline("zero_shot", model).answer("Điều kiện tốt nghiệp?", session_token="t", history=history)
    call = model.calls[0]
    assert call["system"] == prompts.SYSTEM_PROMPT and "<regulations>" not in call["prompt"]
    assert [t.content for t in call["history"]] == ["Chào", "Chào bạn"]
    assert resp.tool_calls == [] and resp.outcome is None and prompts.CANARY not in resp.text
    assert resp.usage_by_role[0].model == "azure/gpt-4.1-mini" and resp.usage.total == 120


def test_naive_rag_searches_once_with_the_question_as_asked():
    model = Model()
    agent = LLMBaseline("naive_rag", model, InProcessRegulations(regulation_service("graph")))
    resp = agent.answer("Điều kiện để được xét công nhận tốt nghiệp gồm những gì?", session_token=None, history=[])
    assert resp.tool_calls == ["search_regulations"] and resp.citations and len(model.calls) == 1
    assert "<regulations>" in model.calls[0]["prompt"] and resp.citations[0] in model.calls[0]["prompt"]
    assert agent.describe()["regulations"] is True


def test_llm_baselines_need_a_key(monkeypatch):
    for name in ["LLM_PROVIDER", "LLM_API_KEY"] + [p.key_env for p in PROVIDERS.values()]:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="no LLM key"):
        baselines.zero_shot(0)
