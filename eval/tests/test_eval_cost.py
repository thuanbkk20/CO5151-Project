"""Cost logging: tokens by role and model from the spans of an answer, USD from the price table. No LLM."""

from types import SimpleNamespace

from co5151_backend.domain.trace import Span, Trace, Usage
from co5151_eval.agent import RoleUsage
from co5151_eval.backend_agent import usage_by_role
from co5151_eval.cost import cost_line, cost_usd, prices, summarize_cost


def test_every_price_has_input_and_output():
    assert prices() and all(set(p) == {"input", "output"} for p in prices().values())


def test_cost_by_model_name_and_unknown_models_are_not_guessed():
    usage = [RoleUsage(role="writer", model="azure/gpt-4.1-mini", input_tokens=1_000_000, output_tokens=0),
             RoleUsage(role="judge", model="openai/gpt-4.1-mini", input_tokens=0, output_tokens=500_000)]  # fmt: skip
    assert cost_usd(usage) == (1.2, [])
    unknown = [*usage, RoleUsage(role="router", model="gemini/gemini-3.1-flash-lite", input_tokens=10)]
    assert cost_usd(unknown) == (None, ["gemini/gemini-3.1-flash-lite"])
    assert cost_usd([RoleUsage(role="router", model="gemini/x")]) == (0.0, [])  # no tokens, nothing to price


def test_usage_by_role_from_the_spans_with_the_judges_own_model():
    trace = Trace(trace_id="t", conversation_id="c", user_message_id="m", llm="azure/gpt-4.1-mini")
    judge = {"checks": {"judge": {"provider": "foundry", "model": "gpt-5-mini"}}}
    spans = [Span("planner", "rules+llm", usage=Usage(100, 20)), Span("planner", "rewrite", usage=Usage(50, 10)),
             Span("regulation", "search_regulations"), Span("writer", "draft", usage=Usage(1000, 200)),
             Span("verifier", "round 1", input=judge, usage=Usage(800, 30))]  # fmt: skip
    rows = {(u.role, u.model): (u.input_tokens, u.output_tokens) for u in usage_by_role(trace, spans)}
    assert rows == {("router", "azure/gpt-4.1-mini"): (150, 30), ("writer", "azure/gpt-4.1-mini"): (1000, 200),
                    ("judge", "foundry/gpt-5-mini"): (800, 30)}  # fmt: skip


def test_run_cost_per_turn_and_conversation():
    def rec(conv, model="azure/gpt-4.1-mini"):
        usage = {"role": "writer", "model": model, "input_tokens": 500_000, "output_tokens": 0}
        return SimpleNamespace(seed=0, conversation_id=conv, usage_by_role=[usage])

    cost = summarize_cost([rec("H01"), rec("H01"), rec("H02")], per="conversation_id")
    assert (cost["cost_usd"], cost["cost_per_turn_usd"], cost["cost_per_conversation_usd"]) == (0.6, 0.2, 0.3)
    assert cost["tokens_by_role"] == {"writer": {"input_tokens": 1_500_000, "output_tokens": 0}}
    assert "$0.6000 cả lần chạy" in cost_line(cost)
    missing = summarize_cost([rec("H01", "gemini/x")], per="conversation_id")
    assert missing["cost_usd"] is None and "chưa có giá cho gemini/x" in cost_line(missing)
