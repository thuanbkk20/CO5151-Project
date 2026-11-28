"""Grade a finished run again with the current scorer, without calling the agent (e.g. after a scorer fix).

The answers, tokens and costs of `results.jsonl` are kept; only the scores change. The agent's own outcome label is
kept when the run recorded it (`declared_outcome`); otherwise the text is classified again. Files written before
`declared_outcome` existed keep their recorded outcome.
"""

import dataclasses
import json
from pathlib import Path

from .agent import AgentResponse, RoleUsage, Usage
from .conversation_runner import TurnRecord, turn_record, write_conversation_report
from .conversations import load_conversations
from .runner import Record, _record, write_report
from .scoring import score
from .tasks import SUITES, Outcome, load_tasks


def _response(row: dict) -> AgentResponse:
    declared = row["declared_outcome"] if "declared_outcome" in row else row.get("outcome")
    usage = Usage(input_tokens=row.get("input_tokens", 0), output_tokens=row.get("output_tokens", 0))
    return AgentResponse(text=row.get("text", ""), outcome=Outcome(declared) if declared else None,
                         citations=row.get("citations", []), tool_calls=row.get("tool_calls", []), usage=usage,
                         usage_by_role=[RoleUsage(**u) for u in row.get("usage_by_role", [])],
                         verifier_rounds=row.get("verifier_rounds"))  # fmt: skip


def _keep(new, row: dict):
    """Latency and token total come from the run, not from the rebuilt response."""
    return dataclasses.replace(new, latency_s=row["latency_s"], tokens=row.get("tokens", new.tokens))


def rescore(results: Path, out: Path, *, conversations: str | None = None, tasks: str | None = None) -> dict:
    rows = [json.loads(line) for line in results.read_text("utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{results}: no records")
    meta_file = results.parent / "summary.json"
    meta = json.loads(meta_file.read_text("utf-8")) if meta_file.exists() else {}
    keep = {k: meta[k] for k in ("agent", "agent_config", "commit", "started") if k in meta}
    title = f"{meta.get('title', 'Kết quả')} (chấm lại)"
    keep["rescored_from"] = str(results)
    if "turn_id" in rows[0]:
        turns = {(c.id, t.id): (c, t) for c in load_conversations(conversations) for t in c.turns}
        records: list[TurnRecord] = []
        for row in rows:
            conv, turn = turns[(row["conversation_id"], row["turn_id"])]
            new = turn_record(conv, turn, row["seed"], row["latency_s"], _response(row), row.get("error"))
            records.append(_keep(new, row))
        return write_conversation_report(records, out, title, keep)
    known = {t.id: t for suite in SUITES for t in load_tasks(suite=suite)} if not tasks else {
        t.id: t for t in load_tasks(tasks)}  # fmt: skip
    records_: list[Record] = []
    for row in rows:
        task, resp = known[row["task_id"]], _response(row)
        new = _record(task, row["seed"], row["latency_s"], resp, score(task, resp), row.get("error"))
        records_.append(_keep(new, row))
    return write_report(records_, out, title, keep)
