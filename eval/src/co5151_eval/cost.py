"""Cost of a run in USD, from the tokens of every LLM call by role and model and a price table.

Prices are per million tokens, by model name (the same model costs the same through openai or azure). A model
without a price is reported as such; its cost is never guessed.
"""

import json
from functools import cache

from .agent import RoleUsage
from .tasks import DATA

ROLES = ("router", "writer", "judge")


@cache
def prices() -> dict[str, dict[str, float]]:
    return json.loads((DATA / "prices.json").read_text("utf-8"))["models"]


def model_name(llm: str) -> str:
    """`azure/gpt-4.1-mini` -> `gpt-4.1-mini`."""
    return llm.rpartition("/")[2]


def cost_usd(usage: list[RoleUsage]) -> tuple[float | None, list[str]]:
    """The cost of these calls and the models without a price (then the cost is None)."""
    total, missing = 0.0, []
    for u in usage:
        if not u.input_tokens and not u.output_tokens:
            continue
        price = prices().get(model_name(u.model))
        if price is None:
            missing.append(u.model)
            continue
        total += (u.input_tokens * price["input"] + u.output_tokens * price["output"]) / 1_000_000
    return (None if missing else round(total, 6)), sorted(set(missing))


def by_role(usage: list[RoleUsage]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for u in usage:
        row = out.setdefault(u.role, {"input_tokens": 0, "output_tokens": 0})
        row["input_tokens"] += u.input_tokens
        row["output_tokens"] += u.output_tokens
    return out


def summarize_cost(records: list, per: str | None = None) -> dict:
    """Cost of a run from records with `usage_by_role` (dicts) and `cost_usd`; `per` names a grouping attribute
    (e.g. `conversation_id`) to also give the mean cost per group."""
    usage = [RoleUsage(**u) for r in records for u in r.usage_by_role]
    total, missing = cost_usd(usage)
    out = {
        "cost_usd": total,
        "models_without_price": missing,
        "tokens_by_role": by_role(usage),
        "cost_per_turn_usd": round(total / len(records), 6) if total is not None and records else None,
    }
    if per and total is not None:
        groups = {(r.seed, getattr(r, per)) for r in records}
        out[f"cost_per_{per.removesuffix('_id')}_usd"] = round(total / len(groups), 6) if groups else None
    return out


def cost_line(cost: dict) -> str:
    if cost["cost_usd"] is None:
        missing = ", ".join(cost["models_without_price"])
        return f"Chi phí: chưa có giá cho {missing} (xem `eval/src/co5151_eval/data/prices.json`)."
    roles = ", ".join(f"{role} {u['input_tokens']}+{u['output_tokens']}" for role, u in cost["tokens_by_role"].items())
    parts = [f"Chi phí: ${cost['cost_usd']:.4f} cả lần chạy", f"${cost['cost_per_turn_usd']:.5f}/lượt"]
    if cost.get("cost_per_conversation_usd") is not None:
        parts.append(f"${cost['cost_per_conversation_usd']:.4f}/hội thoại")
    return " · ".join(parts) + (f" · token vào+ra theo vai: {roles}" if roles else "")
