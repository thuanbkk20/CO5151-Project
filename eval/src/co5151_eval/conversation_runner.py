"""Runs the test conversations turn by turn and reports by turn, by conversation and by use case.

The runner keeps each conversation's history and passes it to `agent.answer`; the backend agent writes it to its
conversation store before asking, so the history goes through the use case as in the app (the question limit counts
it too). Prefilled turns are written, never asked: they cost no LLM call.
"""

import json
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .agent import AgentResponse
from .conversations import USE_CASES, Conversation, Turn
from .gold import RecordOracle
from .runner import AgentFactory, _cell, _pct, _rate
from .scoring import score
from .tasks import Outcome


@dataclass
class TurnRecord:
    conversation_id: str
    turn_id: str
    user: str
    use_cases: list[str]
    seed: int
    expected: str
    latency_s: float
    tokens: int
    outcome: str
    outcome_ok: bool
    facts_hit: int
    facts_total: int
    citations_hit: int
    citations_total: int
    forbidden_hits: list[str]
    passed: bool | None
    tool_calls: list[str] = field(default_factory=list)
    text: str = ""
    error: str | None = None
    citations: list[str] = field(default_factory=list)
    verifier_rounds: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def turn_record(conv: Conversation, turn: Turn, seed: int, latency: float, resp: AgentResponse,
                error: str | None) -> TurnRecord:  # fmt: skip
    s = score(turn, resp)
    return TurnRecord(conv.id, turn.id, conv.user, list(conv.use_cases), seed, turn.expected.value, round(latency, 4),
                      resp.usage.total, s.outcome.value, s.outcome_ok, s.facts_hit, s.facts_total, s.citations_hit,
                      s.citations_total, s.forbidden_hits, False if error else s.passed, resp.tool_calls, resp.text,
                      error, resp.citations, resp.verifier_rounds, resp.usage.input_tokens,
                      resp.usage.output_tokens)  # fmt: skip


def _history(conv: Conversation) -> list[dict[str, str]]:
    turns = [[{"role": "user", "content": p.question}, {"role": "assistant", "content": p.answer}]
             for p in conv.prefill_turns]  # fmt: skip
    return [m for pair in turns for m in pair]


def run_conversations(
    make_agent: AgentFactory,
    conversations: Iterable[Conversation],
    seeds: Iterable[int] = (0,),
    oracle: RecordOracle | None = None,
    on_record: Callable[[TurnRecord], None] | None = None,
) -> list[TurnRecord]:
    oracle = oracle or RecordOracle()
    conversations = list(conversations)
    records = []
    for seed in seeds:
        for conv in conversations:
            agent = make_agent(seed)
            token = oracle.token(conv.user)
            history = _history(conv)
            for turn in conv.turns:
                if turn.new_conversation:
                    history = []
                start = time.perf_counter()
                try:
                    resp, error = agent.answer(turn.question, session_token=token, history=list(history)), None
                except Exception as e:
                    resp, error = AgentResponse(text=""), f"{type(e).__name__}: {e}"
                rec = turn_record(conv, turn, seed, time.perf_counter() - start, resp, error)
                history += [{"role": "user", "content": turn.question}, {"role": "assistant", "content": resp.text}]
                records.append(rec)
                if on_record:
                    on_record(rec)
    return records


def conversation_passed(turns: list[TurnRecord]) -> bool | None:
    """False when a turn failed; True when every turn is gradable and passed; None when some need a human."""
    if any(t.passed is False for t in turns):
        return False
    return None if any(t.passed is None for t in turns) else True


def _turn_block(rs: list[TurnRecord]) -> dict:
    def expected(o: Outcome) -> list[TurnRecord]:
        return [r for r in rs if r.expected == o.value]

    answer, refuse, clarify, limit = (expected(o) for o in (Outcome.ANSWER, Outcome.REFUSE, Outcome.CLARIFY,
                                                            Outcome.LIMIT))  # fmt: skip
    graded = [r for r in rs if r.passed is not None]
    lat = [r.latency_s for r in rs if r.error is None]
    return {
        "turns": len(rs),
        "pass_rate": _rate(sum(bool(r.passed) for r in graded), len(graded)),
        "needs_human": len(rs) - len(graded),
        "outcome_accuracy": _rate(sum(r.outcome_ok for r in rs), len(rs)),
        "false_refusal_rate": _rate(sum(r.outcome == Outcome.REFUSE.value for r in answer), len(answer)),
        "strict_refusal_rate": _rate(sum(r.outcome == Outcome.REFUSE.value for r in refuse), len(refuse)),
        "clarification_rate": _rate(sum(r.outcome == Outcome.CLARIFY.value for r in clarify), len(clarify)),
        "limit_ok": _rate(sum(r.outcome_ok for r in limit), len(limit)),
        "fact_recall": _rate(sum(r.facts_hit for r in rs), sum(r.facts_total for r in rs)),
        "citation_recall": _rate(sum(r.citations_hit for r in rs), sum(r.citations_total for r in rs)),
        "leaks": sum(bool(r.forbidden_hits) for r in rs),
        "errors": sum(r.error is not None for r in rs),
        "latency_p50_s": _pct(lat, 0.5),
        "latency_p95_s": _pct(lat, 0.95),
        "tokens_mean": round(statistics.fmean(r.tokens for r in rs), 1) if rs else None,
        "verifier_rewrites": sum((r.verifier_rounds or 0) > 1 for r in rs),
        "verifier_refusals": sum(bool(r.verifier_rounds) and r.outcome == Outcome.REFUSE.value for r in rs),
    }


def _by_conversation(rs: list[TurnRecord]) -> dict[tuple[int, str], bool | None]:
    groups: dict[tuple[int, str], list[TurnRecord]] = {}
    for r in rs:
        groups.setdefault((r.seed, r.conversation_id), []).append(r)
    return {key: conversation_passed(turns) for key, turns in groups.items()}


def _conversation_block(rs: list[TurnRecord]) -> dict:
    verdicts = list(_by_conversation(rs).values())
    graded = [v for v in verdicts if v is not None]
    return {"conversations": len(verdicts), "pass_rate": _rate(sum(graded), len(graded)),
            "needs_human": len(verdicts) - len(graded)}  # fmt: skip


def _use_case_block(rs: list[TurnRecord]) -> dict:
    turns, convs = _turn_block(rs), _conversation_block(rs)
    return {"conversations": convs["conversations"], "conversation_pass_rate": convs["pass_rate"],
            "turns": turns["turns"], "turn_pass_rate": turns["pass_rate"], "leaks": turns["leaks"]}  # fmt: skip


def summarize_conversations(records: list[TurnRecord]) -> dict:
    seeds = sorted({r.seed for r in records})
    per_seed = [_conversation_block([r for r in records if r.seed == s])["pass_rate"] or 0.0 for s in seeds]
    verdicts = _by_conversation(records)
    return {
        "seeds": seeds,
        "conversations": _conversation_block(records),
        "turns": _turn_block(records),
        "by_use_case": {
            uc: _use_case_block(rs) for uc in USE_CASES if (rs := [r for r in records if uc in r.use_cases])
        },  # fmt: skip
        "by_conversation": {
            cid: [verdicts.get((s, cid)) for s in seeds] for cid in dict.fromkeys(r.conversation_id for r in records)
        },  # fmt: skip
        "conversation_pass_rate_by_seed": per_seed,
        "conversation_pass_rate_mean": round(statistics.fmean(per_seed), 4) if per_seed else None,
        "conversation_pass_rate_std": round(statistics.pstdev(per_seed), 4) if len(per_seed) > 1 else 0.0,
    }


_TURN_COLUMNS = [
    ("turns", "Lượt"), ("pass_rate", "Pass"), ("needs_human", "Chấm tay"), ("outcome_accuracy", "Outcome acc."),
    ("false_refusal_rate", "False refusal"), ("strict_refusal_rate", "Strict refusal"),
    ("clarification_rate", "Clarify"), ("limit_ok", "Limit"), ("fact_recall", "Fact recall"),
    ("citation_recall", "Citation recall"), ("leaks", "Leaks"), ("errors", "Errors"), ("latency_p50_s", "p50 (s)"),
    ("latency_p95_s", "p95 (s)"), ("tokens_mean", "Tokens/lượt"), ("verifier_rewrites", "Verifier viết lại"),
    ("verifier_refusals", "Verifier từ chối"),
]  # fmt: skip
_MARK = {True: "đạt", False: "trượt", None: "chấm tay"}


def conversations_markdown(summary: dict, title: str) -> str:
    c = summary["conversations"]
    lines = [f"## {title}", "",
             f"**Hội thoại đạt:** {_cell(c['pass_rate'])} ({c['conversations']} hội thoại × seed, {c['needs_human']} "
             f"cần chấm tay) · seeds {summary['seeds']}: {summary['conversation_pass_rate_mean']} ± "
             f"{summary['conversation_pass_rate_std']}", "", "### Theo lượt", "",
             "| | " + " | ".join(h for _, h in _TURN_COLUMNS) + " |", "|---|" + "---|" * len(_TURN_COLUMNS),
             "| Tổng | " + " | ".join(_cell(summary["turns"][k]) for k, _ in _TURN_COLUMNS) + " |", "",
             "### Theo use case", "", "| Use case | Hội thoại | Hội thoại đạt | Lượt | Lượt đạt | Leaks |",
             "|---|---|---|---|---|---|"]  # fmt: skip
    for uc, b in summary["by_use_case"].items():
        lines.append(f"| {uc} | {b['conversations']} | {_cell(b['conversation_pass_rate'])} | {b['turns']} | "
                     f"{_cell(b['turn_pass_rate'])} | {b['leaks']} |")  # fmt: skip
    lines += ["", "### Theo hội thoại", "", "| Hội thoại | " + " | ".join(f"seed {s}" for s in summary["seeds"]) + " |",
              "|---|" + "---|" * len(summary["seeds"])]  # fmt: skip
    for cid, verdicts in summary["by_conversation"].items():
        lines.append(f"| {cid} | " + " | ".join(_MARK[v] for v in verdicts) + " |")
    if summary.get("agent_config"):
        lines += ["", f"Cấu hình: `{json.dumps(summary['agent_config'], ensure_ascii=False)}`"]
    lines += ["", "Hội thoại đạt khi không lượt nào trượt và mọi lượt chấm tự động được. `Chấm tay`: lượt `answer` "
              "chưa có đáp án kiểm được tự động (không có facts, trích dẫn chưa đối chiếu)."]  # fmt: skip
    return "\n".join(lines) + "\n"


def write_conversation_report(records: list[TurnRecord], out_dir: Path, title: str, meta: dict | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = {"title": title, "suite": "conversations", **(meta or {}), **summarize_conversations(records)}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    (out_dir / "summary.md").write_text(conversations_markdown(summary, title), "utf-8")
    return summary
