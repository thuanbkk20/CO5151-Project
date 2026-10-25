"""Local evidence retrieval: lexical BM25 + outgoing REFERENCES expansion.

Prototype only: no embeddings, LLM generation or eligibility decisions.
Draft evidence requires explicit allow_draft=True (CLI --allow-draft).
"""

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

STOP = {
    "cua",
    "la",
    "nhieu",
    "cho",
    "trong",
    "do",
    "nao",
    "mot",
    "khi",
    "voi",
    "khong",
    "bao",
    "nhung",
    "de",
    "thi",
    "hoi",
    "co",
    "duoc",
    "nay",
    "ve",
    "cac",
    "va",
    "nhu",
    "the",
    "em",
    "minh",
    "toi",
}

# Conservative development policy for this small foreign-language corpus.
# This is topic routing, not a semantic classifier or a security boundary.
SCOPE_PHRASES = (
    "ngoai ngu",
    "tieng anh",
    "anh van",
    "chung chi",
    "ielts",
    "toeic",
    "toefl",
    "aptis",
    "linguaskill",
    "pte",
    "jlpt",
    "delf",
    "tcf",
    "tieng nhat",
    "tieng phap",
    "khoa luan",
    "tot nghiep",
    "quyet dinh",
    "phu luc",
)


def scope_matches(query):
    text = unicodedata.normalize("NFD", query.lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = " " + " ".join(re.findall(r"[a-z0-9]+", text)) + " "
    return [phrase for phrase in SCOPE_PHRASES if " " + phrase + " " in text]


def tokens(text):
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP]


class RegulationRetriever:
    def __init__(self, graph_path):
        raw = Path(graph_path).read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()
        self.graph = json.loads(raw)
        nodes = self.graph["nodes"]
        self.nodes = {n["id"]: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("Duplicate graph node IDs")
        self.edges = self.graph["edges"]
        if any(e["source"] not in self.nodes or e["target"] not in self.nodes for e in self.edges):
            raise ValueError("Graph has dangling edges")
        self.docs = {}
        for n in nodes:
            if n["type"] not in ("Provision", "Table"):
                continue
            d = n["data"]
            # Do not index whole-page table text: it includes unrelated clauses.
            body = (
                d.get("source_text", "")
                if n["type"] == "Provision"
                else json.dumps(d.get("rows", []), ensure_ascii=False)
            )
            self.docs[n["id"]] = Counter(tokens(d.get("title", "") + " " + body))

    def search(self, query, top_k=3, hops=1, allow_draft=False):
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError("Query must contain 1-2000 characters")
        if type(top_k) is not int or not 1 <= top_k <= 5 or type(hops) is not int or not 0 <= hops <= 2:
            raise ValueError("top_k must be 1-5; hops must be 0-2")
        out = {
            "status": "draft_blocked",
            "corpus_version": self.version,
            "retrieval_policy": "bm25_topic_gate_v1",
            "answer": None,
            "eligibility_decision": None,
            "results": [],
            "graph_paths": [],
            "missing_context": ["program", "cohort", "purpose", "as_of_date"],
            "warnings": [
                "Evidence is unapproved; no eligibility conclusion is produced.",
                "Program/cohort/date filtering is not implemented.",
                "Prototype covers only selected foreign-language provisions.",
                "Related exceptions may be outside the current graph.",
            ],
        }
        # This prototype remains blocked for advising, even if a graph flag is edited.
        if not allow_draft:
            return out
        matches = scope_matches(query)
        out["scope_check"] = {
            "method": "lexical_topic_gate_v1",
            "matched_phrases": matches,
            "applicability_verified": False,
        }
        if not matches:
            out["status"] = "no_evidence"
            out["scope_check"]["reason"] = "insufficient_topic_context"
            out["warnings"].append(
                "No recognized topic cue for the current foreign-language corpus. "
                "Clarify the question; this does not prove the university has no relevant regulation."
            )
            return out
        terms = set(tokens(query))
        lengths = {k: sum(v.values()) for k, v in self.docs.items()}
        count = len(self.docs)
        avg = sum(lengths.values()) / count if count else 1
        scores = {}
        for key, tf in self.docs.items():
            score = 0.0
            for term in terms:
                freq = tf[term]
                if not freq:
                    continue
                df = sum(term in doc for doc in self.docs.values())
                idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
                score += idf * freq * 2.5 / (freq + 1.5 * (0.25 + 0.75 * lengths[key] / (avg or 1)))
            if score > 0:
                scores[key] = score
        selected = sorted(scores, key=lambda k: (-scores[k], k))[:top_k]
        chosen = {key: {"reason": "lexical_match", "score": round(scores[key], 6)} for key in selected}
        frontier = selected
        for _ in range(hops):
            following = []
            for key in frontier:
                for edge in self.edges:
                    if edge["source"] != key or edge["relation"] != "REFERENCES":
                        continue
                    target = edge["target"]
                    out["graph_paths"].append(dict(edge))
                    if target not in chosen and target in self.docs:
                        chosen[target] = {"reason": "graph_reference", "score": None}
                        following.append(target)
            frontier = following
        for key, match in chosen.items():
            n = self.nodes[key]
            d = n["data"]
            source = self.nodes.get(d["source_id"], {})
            out["results"].append(
                {
                    "id": key,
                    "type": n["type"],
                    **match,
                    "citation": {
                        "source_id": d["source_id"],
                        "unit_id": d["unit_id"],
                        "document_number": source.get("document_number"),
                        "pdf_page": d["pdf_page"],
                    },
                    "verified": False,
                    "evidence": d,
                }
            )
        out["status"] = "draft_evidence" if chosen else "no_evidence"
        return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--hops", type=int, default=1)
    p.add_argument("--allow-draft", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    try:
        engine = RegulationRetriever(a.base / "data/processed/language_structured/evidence_graph.json")
        result = engine.search(a.query, a.top_k, a.hops, a.allow_draft)
    except (ValueError, OSError, KeyError) as exc:
        p.error(str(exc))
    if a.out:
        from build_corpus import atomic

        # Output cannot overwrite any existing input/data file accidentally.
        if a.out.exists():
            p.error("--out already exists; select a new output filename")
        a.out.parent.mkdir(parents=True, exist_ok=True)
        atomic(a.out, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Status:", result["status"])
    for r in result["results"]:
        print(f"{r['id']} | {r['reason']} | PDF page {r['citation']['pdf_page']}")
        print(r["evidence"].get("source_text", r["evidence"].get("title", "")))
    print("Graph paths:", len(result["graph_paths"]))
    print("No eligibility decision. Draft evidence only.")


if __name__ == "__main__":
    main()
