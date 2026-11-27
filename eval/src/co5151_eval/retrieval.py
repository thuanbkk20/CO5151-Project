"""Regulation retrieval benchmark: recall and MRR of `search_regulations` on the test conversations, no LLM.

Each case is one turn of `docs/design/test-conversations.md` that needs regulations; follow-up turns are written as a
standalone question (what the router should produce). Expected ids are candidate provisions picked by title and are
not checked against the PDF yet (task A2), so the numbers compare engines, they are not ground truth.
"""

import json
import re
import statistics
from collections.abc import Callable
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from co5151_contracts.envelope import ToolResult

DATA = resources.files("co5151_eval") / "data"
# What the Advisor sends today (`RegulationSearch`) and what it keeps of each provision
TOP_K, HOPS, MAX_CHARS = 3, 1, 1500
CUTOFFS = (3, 8)


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^H[0-9]{2}-[0-9]+$")
    query: str
    expected: list[str] = Field(min_length=1)
    cohort: int | None = None


def load_cases(path: str | Path | None = None) -> list[RetrievalCase]:
    raw = Path(path).read_text("utf-8") if path else (DATA / "retrieval_cases.json").read_text("utf-8")
    cases = [RetrievalCase.model_validate(c) for c in json.loads(raw)]
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate retrieval case ids")
    return cases


def _text(result: dict) -> str:
    """The provision text the Advisor would put in the prompt (same rule as `RegulationSearch`)."""
    evidence = result.get("evidence") or {}
    text = (" ".join(f.get("text", "") for f in evidence.get("fragments") or []) or evidence.get("text")
            or evidence.get("source_text") or "")  # fmt: skip
    return " ".join(text.split())[:MAX_CHARS]


def article_of(pid: str) -> str:
    """The article a clause id belongs to: QD2933-2021-CL14.3 -> QD2933-2021-ART14 (other ids are their own)."""
    return re.sub(r"-CL(\d+)\.\d+$", r"-ART\1", pid)


def ranked_ids(results: list[dict]) -> list[set[str]]:
    """Ids per rank. A result also stands for the older versions it replaces (`superseded`), so an engine that
    returns only the version in force is not punished for leaving the old text out; and for its article, since an
    article holds the text of its clauses (a clause of an expected article, or the article of an expected clause,
    counts)."""
    out = []
    for r in results:
        ids = {r["id"], *(r.get("superseded") or [])}
        out.append(ids | {article_of(i) for i in ids})
    return out


def score_case(case: RetrievalCase, res: ToolResult) -> dict:
    results = (res.data or {}).get("results", []) if res.ok else []
    ranks = ranked_ids(results)
    expected = set(case.expected)
    ranks = [ids | {e for e in expected if article_of(e) in ids} for ids in ranks]
    row = {"id": case.id, "ok": res.ok, "returned": [r["id"] for r in results], "n": len(results),
           "chars": sum(len(_text(r)) for r in results)}  # fmt: skip
    first = next((i for i, ids in enumerate(ranks, 1) if ids & expected), None)
    row["rr"] = 1 / first if first else 0.0
    for k in CUTOFFS:
        found = set().union(*ranks[:k]) & expected if ranks else set()
        row[f"recall@{k}"] = len(found) / len(expected)
        row[f"hit@{k}"] = bool(found)
    return row


def run(call: Callable[[str, dict], ToolResult], cases: list[RetrievalCase]) -> list[dict]:
    rows = []
    for case in cases:
        args = {"query": case.query, "top_k": TOP_K, "hops": HOPS}
        if case.cohort:
            args["context"] = {"cohort": case.cohort}
        rows.append(score_case(case, call("search_regulations", args)))
    return rows


def summarize(rows: list[dict]) -> dict:
    def mean(key: str) -> float:
        return round(statistics.fmean(float(r[key]) for r in rows), 3) if rows else 0.0

    return {"cases": len(rows), "empty_rate": round(sum(r["n"] == 0 for r in rows) / max(1, len(rows)), 3),
            "mrr": mean("rr"), **{f"{m}@{k}": mean(f"{m}@{k}") for k in CUTOFFS for m in ("hit", "recall")},
            "results_mean": mean("n"), "chars_mean": mean("chars")}  # fmt: skip


def to_markdown(summary: dict, rows: list[dict], engine: str) -> str:
    keys = ["cases", "empty_rate", "mrr", "hit@3", "recall@3", "hit@8", "recall@8", "results_mean", "chars_mean"]
    lines = [f"## Truy xuất quy chế: {engine}", "", "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys),
             "| " + " | ".join(str(summary[k]) for k in keys) + " |", "", "| Câu | recall@3 | recall@8 | RR | Trả về |",
             "|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        shown = ", ".join(r["returned"][:8]) + (" …" if r["n"] > 8 else "")
        lines.append(f"| {r['id']} | {r['recall@3']:.2f} | {r['recall@8']:.2f} | {r['rr']:.2f} | {shown or '(rỗng)'} |")
    lines += ["", "Khoản mong đợi là ứng viên chọn theo tiêu đề, **chưa đối chiếu PDF** (task A2). `chars_mean`: số ký "
              "tự quy chế Advisor đưa vào prompt mỗi câu."]  # fmt: skip
    return "\n".join(lines) + "\n"
