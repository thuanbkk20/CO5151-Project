"""Evaluate lexical retrieval versus REFERENCES expansion on a development set.

Measures local retrieval only, without MCP, model generation or network time.
Writes every case, including failures; never changes the graph or gold labels.
"""

import argparse
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from build_corpus import atomic
from retrieve_regulations import RegulationRetriever


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--top-k", type=int, default=1, choices=range(1, 6))
    a = p.parse_args()
    base = a.base.resolve()
    dataset = json.loads(
        (base / "data/evaluation/retrieval_cases_v1.json").read_text(encoding="utf-8")
    )
    engine = RegulationRetriever(
        base / "data/processed/language_structured/evidence_graph.json"
    )
    ids = [c["id"] for c in dataset["cases"]]
    if len(set(ids)) != len(ids):
        p.error("Duplicate case IDs")
    for case in dataset["cases"]:
        for expected in case.get("expected_ids", []) + case.get("related_ids", []):
            if expected not in engine.nodes:
                p.error("Gold ID missing from graph: " + expected)
    records = []
    durations = []
    for case in dataset["cases"]:
        start = time.perf_counter()
        lexical = engine.search(case["query"], top_k=a.top_k, hops=0, allow_draft=True)
        lexical_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        expanded = engine.search(case["query"], top_k=a.top_k, hops=1, allow_draft=True)
        graph_ms = (time.perf_counter() - start) * 1000
        durations.append(graph_ms)
        before = {r["id"] for r in lexical["results"]}
        after = {r["id"] for r in expanded["results"]}
        gold = set(case["expected_ids"])
        related = set(case.get("related_ids", []))
        negative = case.get("expect_no_evidence", False)
        row = {
            "id": case["id"],
            "query": case["query"],
            "expected_ids": sorted(gold),
            "related_ids": sorted(related),
            "lexical_ids": sorted(before),
            "expanded_ids": sorted(after),
            "negative_case": negative,
            "lexical_hit": bool(gold & before) if gold else None,
            "expanded_hit": bool(gold & after) if gold else None,
            "related_before": len(related & before),
            "related_after": len(related & after),
            "no_evidence_pass": expanded["status"] == "no_evidence"
            if negative
            else None,
            "local_lexical_ms": lexical_ms,
            "local_graph_ms": graph_ms,
        }
        records.append(row)
    positives = [r for r in records if not r["negative_case"]]
    negatives = [r for r in records if r["negative_case"]]
    related_count = sum(len(r["related_ids"]) for r in records)

    def ratio(n, d):
        return n / d if d else None

    metrics = {
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "lexical_hit_at_k": ratio(
            sum(r["lexical_hit"] for r in positives), len(positives)
        ),
        "expanded_evidence_hit": ratio(
            sum(r["expanded_hit"] for r in positives), len(positives)
        ),
        "related_evidence_recall_before": ratio(
            sum(r["related_before"] for r in records), related_count
        ),
        "related_evidence_recall_after": ratio(
            sum(r["related_after"] for r in records), related_count
        ),
        "no_evidence_rate_on_negative_cases": ratio(
            sum(r["no_evidence_pass"] for r in negatives), len(negatives)
        ),
        "local_graph_p50_ms": statistics.median(durations) if durations else None,
        "local_graph_p95_ms": sorted(durations)[
            max(0, math.ceil(0.95 * len(durations)) - 1)
        ]
        if durations
        else None,
    }
    report = {
        "dataset_version": dataset["dataset_version"],
        "dataset_note": dataset["usage"],
        "corpus_version": engine.version,
        "retrieval_policy": "bm25_topic_gate_v1",
        "top_k": a.top_k,
        "hops": 1,
        "run_time_utc": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "limitations": [
            "Development set, not held-out evaluation",
            "Local one-pass timings exclude startup, MCP, LLM and network",
            "Graph expansion may return more than k results; not a fixed-budget comparison",
            "Does not evaluate program/cohort/date applicability or legal correctness",
            "Small negative set cannot establish reliable out-of-scope refusal",
        ],
        "cases": records,
    }
    out = base / "data/processed/evaluation"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    prefix = f"retrieval_k{a.top_k}_{stamp}"
    atomic(
        out / (prefix + ".json"),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    lines = [
        "# Retrieval development evaluation",
        "",
        dataset["usage"],
        "",
        f"Top-k: {a.top_k}; graph hops: 1",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    lines += [f"| {key} | {value} |" for key, value in metrics.items()]
    lines += [
        "",
        "| Case | Lexical hit | Expanded hit | Negative pass |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r['id']} | {r['lexical_hit']} | {r['expanded_hit']} | {r['no_evidence_pass']} |"
        for r in records
    ]
    lines += ["", "## Limitations", ""] + [
        "- " + note for note in report["limitations"]
    ]
    atomic(out / (prefix + ".md"), "\n".join(lines) + "\n")
    print(json.dumps(metrics, indent=2))
    print("Reports:", out / (prefix + ".json"), out / (prefix + ".md"))


if __name__ == "__main__":
    main()
