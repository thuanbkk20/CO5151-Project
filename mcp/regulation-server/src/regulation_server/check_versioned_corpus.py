"""Validate source-substring provenance and graph structure, not legal correctness."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    folder = a.base.resolve() / "data/processed"
    raw = json.loads(
        (folder / "corpus_expanded/corpus.json").read_text(encoding="utf-8")
    )
    pages = {r["unit_id"]: r for r in raw}
    items = json.loads(
        (folder / "versioned_regulations/provisions.json").read_text(encoding="utf-8")
    )
    graph = json.loads(
        (folder / "versioned_regulations/version_graph.json").read_text(
            encoding="utf-8"
        )
    )
    errors = []
    ids = {r["provision_id"] for r in items}
    if len(ids) != len(items):
        errors.append("Duplicate provision IDs")
    if len(pages) != len(raw):
        errors.append("Duplicate corpus unit IDs")
    for r in items:
        for fragment in r["fragments"]:
            original = pages.get(fragment["unit_id"])
            if original is None:
                errors.append(r["provision_id"] + ": missing source unit")
                continue
            lo, hi = fragment["start_char"], fragment["end_char"]
            if (
                not (0 <= lo < hi <= len(original["text"]))
                or original["text"][lo:hi] != fragment["text"]
            ):
                errors.append(r["provision_id"] + ": source substring mismatch")
            if (
                original["source_id"] != r["source_id"]
                or original["pdf_page"] != fragment["pdf_page"]
            ):
                errors.append(r["provision_id"] + ": citation mismatch")
        combined = "\n".join(f["text"] for f in r["fragments"])
        if (
            combined != r["source_text"]
            or hashlib.sha256(combined.encode()).hexdigest() != r["source_text_sha256"]
        ):
            errors.append(r["provision_id"] + ": joined text/hash mismatch")
        if r["verified"] is not False:
            errors.append(r["provision_id"] + ": unexpected approval")
    node_ids = {n["id"] for n in graph["nodes"]}
    if len(node_ids) != len(graph["nodes"]):
        errors.append("Duplicate graph node IDs")
    for e in graph["edges"]:
        if e["source"] not in node_ids or e["target"] not in node_ids:
            errors.append("Dangling graph edge")
        if e.get("evidence_provision_id") and e["evidence_provision_id"] not in ids:
            errors.append("Missing relation evidence")
    by_id = {r["provision_id"]: r for r in items}
    changed = by_id.get("QD1260-2026-CL5.5", {})
    if changed.get("pdf_pages") != [3, 4]:
        errors.append("Amended clause 5.5 must preserve both source pages")
    result = {
        "errors": errors,
        "segments_checked": len(items),
        "fragments_checked": sum(len(r["fragments"]) for r in items),
        "edge_types": dict(Counter(e["relation"] for e in graph["edges"])),
        "source_integrity_pass": not errors,
        "legal_content_verified": False,
        "applicability_resolved": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
