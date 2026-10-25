"""Read-only, one-hop version evidence lookup. No applicability decision."""

import argparse
import json
from pathlib import Path

VERSION_RELATIONS = {"AMENDS", "REPLACES", "REPEALS"}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def retrieve(folder, provision_id, *, allow_draft=False):
    if not allow_draft:
        return {"status": "draft_blocked", "evidence": [], "eligibility_decision": None}
    if not isinstance(provision_id, str) or not provision_id.strip():
        raise ValueError("provision_id must be a non-empty string")
    items = load_json(Path(folder) / "provisions.json")
    provisions = {item["provision_id"]: item for item in items}
    if len(provisions) != len(items):
        raise ValueError("Duplicate provision IDs")
    relations = load_json(Path(folder) / "version_relations.json")
    for edge in relations:
        for key in ("source", "target", "evidence_provision_id"):
            if edge.get(key) and edge[key] not in provisions:
                raise ValueError(f"Dangling relation: {edge[key]}")
    if provision_id not in provisions:
        return {"status": "not_found", "provision_id": provision_id, "evidence": []}
    related = [
        e for e in relations if e["relation"] in VERSION_RELATIONS and provision_id in (e["source"], e["target"])
    ]
    selected = {provision_id}
    for edge in related:
        selected.update((edge["source"], edge["target"]))
        if edge.get("evidence_provision_id"):
            selected.add(edge["evidence_provision_id"])
    return {
        "status": "draft_evidence",
        "requested_provision_id": provision_id,
        "relations": related,
        "evidence": [provisions[key] for key in sorted(selected)],
        "expansion_hops": 1,
        "applicability_resolved": False,
        "eligibility_decision": None,
        "warning": "Draft source versions; relations do not establish current applicability.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision-id", required=True)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        result = retrieve(
            args.base / "data/processed/versioned_regulations",
            args.provision_id,
            allow_draft=args.allow_draft,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Input/data error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "draft_evidence" else 1


if __name__ == "__main__":
    raise SystemExit(main())
