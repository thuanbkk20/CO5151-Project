import json
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .agent import Agent, AgentResponse
from .gold import RecordOracle
from .scoring import Score, score
from .tasks import Group, Outcome, Task

AgentFactory = Callable[[int], Agent]


@dataclass
class Record:
    task_id: str
    group: str
    seed: int
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


def _record(task: Task, seed: int, latency: float, resp: AgentResponse, s: Score, error: str | None) -> Record:
    return Record(task.id, task.group.value, seed, round(latency, 4), resp.usage.total, s.outcome.value,
                  s.outcome_ok, s.facts_hit, s.facts_total, s.citations_hit, s.citations_total, s.forbidden_hits,
                  False if error else s.passed, resp.tool_calls, resp.text, error)  # fmt: skip


def run(
    make_agent: AgentFactory,
    tasks: Iterable[Task],
    seeds: Iterable[int] = (0,),
    oracle: RecordOracle | None = None,
    on_record: Callable[[Record], None] | None = None,
) -> list[Record]:
    oracle = oracle or RecordOracle()
    tasks = list(tasks)
    records = []
    for seed in seeds:
        agent = make_agent(seed)
        for task in tasks:
            token = oracle.token(task.user) if task.user else None
            start = time.perf_counter()
            try:
                resp, error = agent.answer(task.question, session_token=token, history=task.history), None
            except Exception as e:
                resp, error = AgentResponse(text=""), f"{type(e).__name__}: {e}"
            latency = time.perf_counter() - start
            rec = _record(task, seed, latency, resp, score(task, resp), error)
            records.append(rec)
            if on_record:
                on_record(rec)
    return records


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, round(q * (len(v) - 1)))], 4)


def _block(rs: list[Record]) -> dict:
    answerable = [r for r in rs if r.group in (Group.BASIC.value, Group.PERSONAL.value)]
    oos = [r for r in rs if r.group == Group.OUT_OF_SCOPE.value]
    missing = [r for r in rs if r.group == Group.MISSING_INFO.value]
    lat = [r.latency_s for r in rs if r.error is None]
    graded = [r for r in rs if r.passed is not None]
    return {
        "n": len(rs),
        "pass_rate": _rate(sum(bool(r.passed) for r in graded), len(graded)),
        "needs_human": len(rs) - len(graded),
        "outcome_accuracy": _rate(sum(r.outcome_ok for r in rs), len(rs)),
        "strict_refusal_rate": _rate(sum(r.outcome == Outcome.REFUSE.value for r in oos), len(oos)),
        "false_refusal_rate": _rate(sum(r.outcome == Outcome.REFUSE.value for r in answerable), len(answerable)),
        "clarification_rate": _rate(sum(r.outcome == Outcome.CLARIFY.value for r in missing), len(missing)),
        "fact_recall": _rate(sum(r.facts_hit for r in rs), sum(r.facts_total for r in rs)),
        "citation_recall": _rate(sum(r.citations_hit for r in rs), sum(r.citations_total for r in rs)),
        "leaks": sum(bool(r.forbidden_hits) for r in rs),
        "errors": sum(r.error is not None for r in rs),
        "latency_p50_s": _pct(lat, 0.5),
        "latency_p95_s": _pct(lat, 0.95),
        "tokens_mean": round(statistics.fmean(r.tokens for r in rs), 1) if rs else None,
    }


def summarize(records: list[Record]) -> dict:
    seeds = sorted({r.seed for r in records})
    per_seed = [_block([r for r in records if r.seed == s])["pass_rate"] or 0.0 for s in seeds]
    return {
        "seeds": seeds,
        "overall": _block(records),
        "by_group": {g.value: _block([r for r in records if r.group == g.value]) for g in Group},
        "pass_rate_by_seed": per_seed,
        "pass_rate_mean": round(statistics.fmean(per_seed), 4) if per_seed else None,
        "pass_rate_std": round(statistics.pstdev(per_seed), 4) if len(per_seed) > 1 else 0.0,
    }


_COLUMNS = [
    ("n", "N"),
    ("pass_rate", "Pass"),
    ("needs_human", "Chấm tay"),
    ("outcome_accuracy", "Outcome acc."),
    ("strict_refusal_rate", "Strict refusal"),
    ("false_refusal_rate", "False refusal"),
    ("clarification_rate", "Clarify"),
    ("fact_recall", "Fact recall"),
    ("citation_recall", "Citation recall"),
    ("leaks", "Leaks"),
    ("errors", "Errors"),
    ("latency_p50_s", "p50 (s)"),
    ("latency_p95_s", "p95 (s)"),
    ("tokens_mean", "Tokens/câu"),
]


def _cell(v) -> str:
    return "–" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def to_markdown(summary: dict, title: str) -> str:
    lines = [f"## {title}", "", "| Nhóm | " + " | ".join(h for _, h in _COLUMNS) + " |",
             "|---|" + "---|" * len(_COLUMNS)]  # fmt: skip
    rows = [*summary["by_group"].items(), ("**Tổng**", summary["overall"])]
    for name, block in rows:
        lines.append(f"| {name} | " + " | ".join(_cell(block[k]) for k, _ in _COLUMNS) + " |")
    lines += ["", f"Seeds: {summary['seeds']} · pass rate {summary['pass_rate_mean']} ± {summary['pass_rate_std']}",
              "", "`–`: không áp dụng. Chấm tay: câu chưa có đáp án kiểm được tự động (chưa có trích dẫn đã xác nhận),",
              "so với `reference_answer`; không tính vào Pass."]  # fmt: skip
    return "\n".join(lines) + "\n"


def write_report(records: list[Record], out_dir: Path, title: str, meta: dict | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = {"title": title, **(meta or {}), **summarize(records)}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    (out_dir / "summary.md").write_text(to_markdown(summary, title), "utf-8")
    return summary
