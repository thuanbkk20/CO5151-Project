"""Evidence retrieval only: lexical ranking and bounded version/reference traversal."""

import hashlib
import json
import math
from collections import Counter, deque
from pathlib import Path

from .retrieve_regulations import scope_matches, tokens

TOPICS = (
    "hoc phi",
    "dang ky",
    "rut hoc phan",
    "tin chi",
    "diem",
    "gpa",
    "canh bao",
    "buoc thoi hoc",
    "bao luu",
    "mien",
    "chuyen nganh",
    "song nganh",
    "ren luyen",
    "hoc vu",
    "hoc lai",
    "chuyen doi",
    "thoi gian dao tao",
    "sinh vien",
    "hoc bong",
    "ky tuc xa",
)
RELATIONS = {"AMENDS", "REPLACES", "REPEALS", "REFERENCES"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class HandoffRetriever:
    def __init__(self, base):
        data = Path(base) / "data/processed"
        self.nodes = {}
        self.edges = []
        paths = [
            data / "versioned_regulations/provisions.json",
            data / "versioned_regulations/version_relations.json",
            data / "language_structured/evidence_graph.json",
            data / "corpus_expanded/corpus.json",
        ]
        self.version = hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()
        corpus = read(paths[3])
        units = {u["unit_id"]: u for u in corpus}
        if len(units) != len(corpus):
            raise ValueError("Duplicate corpus unit")
        for u in corpus:
            digest = u.get("text_sha256")
            if digest and hashlib.sha256(u["text"].encode()).hexdigest() != digest:
                raise ValueError("Corpus text hash mismatch")
        for p in read(paths[0]):
            if hashlib.sha256(p["source_text"].encode()).hexdigest() != p["source_text_sha256"]:
                raise ValueError("Provision hash mismatch")
            for f in p["fragments"]:
                u = units[f["unit_id"]]
                if u["source_id"] != p["source_id"] or u["pdf_page"] != f["pdf_page"]:
                    raise ValueError("Citation identity mismatch")
                if u["text"][f["start_char"] : f["end_char"]] != f["text"]:
                    raise ValueError("Fragment mismatch")
            self.add(p["provision_id"], p, "regulation")
        self.edges = read(paths[1])
        language = read(paths[2])
        for n in language["nodes"]:
            if n["type"] not in ("Provision", "Table"):
                continue
            p = dict(n["data"])
            p["pdf_pages"] = [p["pdf_page"]]
            # Language seed excerpts are exact source substrings; table rows are manual derivatives.
            if n["type"] == "Provision" and p["source_text"] not in units[p["unit_id"]]["text"]:
                raise ValueError("Language excerpt mismatch")
            self.add(
                n["id"],
                p,
                "regulation" if n["type"] == "Provision" else "derived_table",
            )
            self.edges.append(
                {
                    "source": n["id"],
                    "target": "QD2749-2026-APP1",
                    "relation": "REFERENCES",
                    "verified": False,
                    "note": "Source appendix context; not a new legal amendment.",
                }
            )
        self.edges.extend(e for e in language["edges"] if e["relation"] == "REFERENCES")
        self.edges.append(
            {
                "source": "HCMUT-2749-2026-A2-THESIS",
                "target": "QD1260-2026-CL5.5",
                "relation": "REFERENCES",
                "verified": False,
                "note": "Curated topic link: language prerequisite and registration conditions; not a legal amendment.",
            }
        )
        for u in corpus:
            if u.get("unit_type", "").startswith("docx") or "HANDBOOK" in u["file_name"].upper():
                if not u["text"].strip():
                    continue
                p = dict(u)
                p.update(
                    provision_id=u["unit_id"],
                    source_text=u["text"],
                    title=u["file_name"],
                    pdf_pages=[u["pdf_page"]] if u["pdf_page"] else [],
                )
                self.add(u["unit_id"], p, "supplemental")
        for e in self.edges:
            if e["source"] not in self.nodes or e["target"] not in self.nodes:
                raise ValueError("Dangling evidence edge")
            if e.get("evidence_provision_id") and e["evidence_provision_id"] not in self.nodes:
                raise ValueError("Missing relation evidence")
        self.index = {
            k: Counter(
                tokens(
                    p.get("title", "")
                    + " "
                    + p.get("source_text", "")
                    + " "
                    + json.dumps(p.get("rows", []), ensure_ascii=False)
                )
            )
            for k, p in self.nodes.items()
        }
        self.lengths = {k: sum(v.values()) for k, v in self.index.items()}
        self.avg_length = sum(self.lengths.values()) / max(1, len(self.index))
        self.df = Counter(t for doc in self.index.values() for t in doc)

    def add(self, key, data, role):
        if key in self.nodes:
            raise ValueError("Duplicate provision ID")
        self.nodes[key] = {**data, "evidence_role": role, "verified": False}

    def bundle(self, seeds, hops=2, context=None):
        chosen = list(dict.fromkeys(seeds))
        visited = set(chosen)
        queue = deque((s, 0) for s in chosen)
        paths = []
        used = set()
        truncated = False
        while queue:
            key, depth = queue.popleft()
            if depth >= hops:
                continue
            for i, e in enumerate(self.edges):
                if e["relation"] not in RELATIONS:
                    continue
                # REFERENCES follows the declared direction; version relations are explored both ways.
                other = (
                    e["target"]
                    if e["source"] == key
                    else (e["source"] if e["target"] == key and e["relation"] != "REFERENCES" else None)
                )
                if other is None:
                    continue
                targets = [other]
                if e.get("evidence_provision_id"):
                    targets.append(e["evidence_provision_id"])
                new = [t for t in dict.fromkeys(targets) if t not in visited]
                if len(chosen) + len(new) > 24:
                    truncated = True
                    continue
                if i not in used:
                    paths.append(dict(e))
                    used.add(i)
                for target in new:
                    visited.add(target)
                    chosen.append(target)
                    queue.append((target, depth + 1))
        results = []
        for key in chosen:
            p = self.nodes[key]
            results.append(
                {
                    "id": key,
                    "reason": "seed_match" if key in seeds else "graph_related",
                    "evidence_role": p["evidence_role"],
                    "verified": False,
                    "citation": {
                        k: p.get(k)
                        for k in (
                            "source_id",
                            "file_name",
                            "unit_id",
                            "pdf_pages",
                            "block_index",
                        )
                    },
                    "evidence": p,
                }
            )
        return {
            "status": "draft_evidence" if results else "no_evidence",
            "corpus_version": self.version,
            "retrieval_method": "lexical_bm25_bounded_graph",
            "results": results,
            "graph_paths": paths,
            "truncated": truncated,
            "provided_context": context or {},
            "applicability_resolved": False,
            "missing_context": [
                k for k in ("program", "cohort", "semester", "as_of_date") if not (context or {}).get(k)
            ],
            "answer": None,
            "eligibility_decision": None,
            "warnings": [
                "Unverified evidence; do not issue eligibility decisions.",
                "Context is recorded, not used to establish applicability.",
                "Handbook/FAQ are supplemental; manual tables require PDF checking.",
                "Coverage and graph references are incomplete; no_evidence is not proof of no rule.",
                "OCR artifacts are preserved in source_text; lexical search may miss merged words.",
            ],
        }

    def get(self, key, hops=2, context=None):
        if key not in self.nodes:
            raise KeyError(key)
        return self.bundle([key], hops, context)

    def search(self, query, top_k=3, hops=2, context=None):
        if query in self.nodes:
            return self.get(query, hops, context)
        normalized = " " + " ".join(tokens(query)) + " "
        topic = bool(scope_matches(query)) or any(" " + p + " " in normalized for p in TOPICS)
        if not topic:
            return self.bundle([], hops, context)
        terms = set(tokens(query))
        scores = {}
        for key, tf in self.index.items():
            score = 0.0
            for t in terms:
                f = tf[t]
                if f:
                    idf = math.log(1 + (len(self.index) - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    score += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * self.lengths[key] / (self.avg_length or 1)))
            if score > 0:
                # Supplemental sources are returned explicitly as such, not treated as binding rules.
                scores[key] = score
        seeds = sorted(scores, key=lambda k: (-scores[k], k))[:top_k]
        return self.bundle(seeds, hops, context)
