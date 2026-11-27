"""Hybrid retrieval over the regulation graph.

1. Concepts: the query's words are matched against each concept's synonyms (accent-insensitive); the provisions
   `ABOUT` a matched concept are ranked by the concept's place.
2. BM25 over provisions, on syllables and syllable bigrams. OCR glued syllables ("kỳchính", "sốtín") are split back
   with the syllables of the clean texts.
3. The two rankings are fused with reciprocal rank fusion. Council conclusions weigh less than regulations, and
   double-degree rules only count when the query is about a double degree.
4. Versions: a provision replaced or fully amended by a newer one gives its place to the newer one, which carries the
   old ids in `superseded`; a partly amended provision stays and its amendment follows it; a repealed one is dropped.
5. A matched concept that `REQUIRES` another adds the main provision of that one (graduation pulls the language
   standard), after the top results.

Out of scope = no concept matched and the best BM25 score is under `MIN_BM25`.
"""

import json
import math
import re
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path

from .documents import DATA

RRF_K = 60
MIN_BM25 = 4.0
COUNCIL_WEIGHT = 0.5
MAX_RELATED = 2
# Function words only: "bao" (bao nhiêu / bảo lưu) and "toi" (tối đa) carry meaning once accents are gone
STOP = set(
    "la cua va cac nhung mot nay do ma voi em anh chi a o thi ve cho trong khi nhu the co khong duoc nao gi hoi minh"
    " ban u vay".split()
)
WORD = re.compile(r"[^\W\d_]+|\d+(?:[.,]\d+)?", re.UNICODE)
VERSION = ("AMENDS", "REPLACES", "REPEALS")


def fold(text: str) -> str:
    """Lowercase without diacritics: "Tốt nghiệp" -> "tot nghiep"."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def phrase(text: str) -> str:
    """Folded words separated and surrounded by single spaces, to match whole phrases: " xet tot nghiep "."""
    return f" {' '.join(re.findall(r'[a-z0-9+]+', fold(text)))} "


def words(text: str) -> list[str]:
    return WORD.findall(unicodedata.normalize("NFC", text.lower()))


class Syllables:
    """Splits OCR-glued Vietnamese syllables using the syllables seen in clean text."""

    def __init__(self, clean_texts: list[str]):
        counts = Counter(w for t in clean_texts for w in words(t))
        self.known = {w for w, n in counts.items() if n >= 2 and len(w) <= 7}

    @cache  # noqa: B019 - one instance per graph, lives as long as the process
    def split(self, word: str) -> tuple[str, ...]:
        if word in self.known or len(word) <= 3 or word.isdigit():
            return (word,)
        # Fewest known syllables covering the whole word (at most 4), else the word itself
        best: list[tuple[str, ...] | None] = [()] + [None] * len(word)
        for end in range(1, len(word) + 1):
            for start in range(max(0, end - 7), end):
                head = best[start]
                if head is not None and word[start:end] in self.known and len(head) < 4:
                    cand = (*head, word[start:end])
                    if best[end] is None or len(cand) < len(best[end]):
                        best[end] = cand
        return best[-1] if best[-1] and len(best[-1]) > 1 else (word,)


class GraphRetriever:
    def __init__(self, graph_path: Path | None = None):
        graph = json.loads((graph_path or DATA / "graph.json").read_text("utf-8"))
        self.version = graph["version"]
        self.documents = {d["id"]: d for d in graph["documents"]}
        self.provisions = {p["id"]: p for p in graph["provisions"]}
        self.concepts = {c["id"]: c for c in graph["concepts"]}
        self.edges = graph["edges"]
        clean = [p["text"] for p in graph["provisions"] if not p["doc"].startswith("QD2933")]
        self.syllables = Syllables(clean)
        self._index()
        self._links()

    # --- indexing -------------------------------------------------------------------------------------------------

    def tokens(self, text: str) -> list[str]:
        syl = [fold(s) for w in words(text) for s in self.syllables.split(w)]
        syl = [s for s in syl if s not in STOP]
        return syl + [f"{a}_{b}" for a, b in zip(syl, syl[1:], strict=False)]

    def _index(self) -> None:
        self.tf = {pid: Counter(self.tokens(p["title"] + " " + p["text"])) for pid, p in self.provisions.items()}
        self.length = {pid: sum(tf.values()) for pid, tf in self.tf.items()}
        self.avg = sum(self.length.values()) / max(1, len(self.length))
        self.df = Counter(t for tf in self.tf.values() for t in tf)
        self.synonyms = {cid: [phrase(s) for s in c["synonyms"]] for cid, c in self.concepts.items()}

    def _links(self) -> None:
        self.about: dict[str, list[str]] = {}
        self.concepts_of: dict[str, set[str]] = {}
        self.requires: dict[str, list[str]] = {}
        self.children: dict[str, list[str]] = {}
        self.newer: dict[str, list[tuple[str, str, bool]]] = {}
        for e in self.edges:
            rel, src, dst = e["relation"], e["source"], e["target"]
            if rel == "ABOUT":
                self.about.setdefault(dst, []).append(src)
                self.concepts_of.setdefault(src, set()).add(dst)
            elif rel == "REQUIRES":
                self.requires.setdefault(src, []).append(dst)
            elif rel == "CONTAINS":
                self.children.setdefault(src, []).append(dst)
            elif rel in VERSION:
                self.newer.setdefault(dst, []).append((src, rel, bool(e.get("partial"))))

    # --- ranking --------------------------------------------------------------------------------------------------

    def bm25(self, query: str) -> dict[str, float]:
        terms = set(self.tokens(query))
        n = len(self.tf)
        scores = {}
        for pid, tf in self.tf.items():
            s = 0.0
            for t in terms:
                if f := tf.get(t):
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.length[pid] / self.avg))
            if s > 0:
                scores[pid] = s
        return scores

    def matched_concepts(self, query: str) -> list[str]:
        q = phrase(query)
        spans: dict[str, list[tuple[int, int]]] = {}
        for cid, syns in self.synonyms.items():
            for s in syns:
                start = q.find(s)
                while start >= 0:
                    spans.setdefault(cid, []).append((start, start + len(s)))
                    start = q.find(s, start + 1)

        # A concept whose every match lies inside a longer match of another one is not meant: "luận văn tốt nghiệp"
        # is about the thesis, not about graduation
        def covered(span, cid):
            return any(o != cid and a <= span[0] and span[1] <= b and (b - a) > (span[1] - span[0])
                       for o, other in spans.items() for a, b in other)  # fmt: skip

        kept = {cid: sp for cid, sp in spans.items() if not all(covered(x, cid) for x in sp)}
        # Longer phrases are more specific: "do an chuyen nganh" beats "chuyen nganh"
        return sorted(kept, key=lambda cid: (-max(b - a for a, b in kept[cid]), cid))

    def _weight(self, pid: str, concepts: list[str]) -> float:
        p = self.provisions[pid]
        w = COUNCIL_WEIGHT if p["kind"] == "council_point" else 1.0
        if "song_nganh" in self.concepts_of.get(pid, ()) and "song_nganh" not in concepts:
            w *= 0.3
        return w

    def rank(self, query: str) -> tuple[list[str], list[str], float]:
        concepts = self.matched_concepts(query)
        lexical = self.bm25(query)
        best = max(lexical.values(), default=0.0)
        if not concepts and best < MIN_BM25:
            return [], concepts, best
        fused: dict[str, float] = {}
        for rank, pid in enumerate(sorted(lexical, key=lambda k: (-lexical[k], k))[:40], 1):
            fused[pid] = fused.get(pid, 0) + 1 / (RRF_K + rank)
        concept_rank = [pid for cid in concepts for pid in self.about.get(cid, [])]
        for rank, pid in enumerate(dict.fromkeys(concept_rank), 1):
            # Concept links are curated: one counts like a top lexical hit
            fused[pid] = fused.get(pid, 0) + 1.5 / (RRF_K + rank)
        ordered = sorted(fused, key=lambda k: (-fused[k] * self._weight(k, concepts), k))
        return ordered, concepts, best

    # --- versions -------------------------------------------------------------------------------------------------

    def current(self, pid: str, seen: frozenset = frozenset()) -> tuple[list[str], list[str], list[str]]:
        """(provisions in force that stand for `pid`, ids they supersede, partial amendments of `pid`)."""
        newer = [(src, rel, partial) for src, rel, partial in self.newer.get(pid, []) if src not in seen]
        full = [src for src, rel, partial in newer if not partial]
        partial = [src for src, rel, p in newer if p]
        repealed = any(rel == "REPEALS" for _, rel, _ in newer)
        if repealed:
            return [], [pid], []
        if not full:
            return [pid], [], partial
        in_force, superseded = [], [pid]
        for src in full:
            if src.endswith("DECISION-ART2"):
                continue
            cur, sup, _ = self.current(src, seen | {pid})
            in_force += cur
            superseded += sup
        return (list(dict.fromkeys(in_force)) or [pid]), list(dict.fromkeys(superseded)), partial

    def amendments_inside(self, pid: str) -> list[str]:
        """Amendments of the clauses of an article: the article's own text is partly outdated."""
        out = []
        for child in self.children.get(pid, []):
            out += [src for src, rel, _ in self.newer.get(child, []) if rel != "REPEALS" and "DECISION" not in src]
        return out

    # --- search ---------------------------------------------------------------------------------------------------

    def search(self, query: str, top_k: int = 3, hops: int = 1, context: dict | None = None) -> dict:
        if query in self.provisions:
            return self.get(query, hops, context)
        ordered, concepts, best = self.rank(query)
        chosen: dict[str, dict] = {}
        for pid in ordered:
            if len(chosen) >= top_k:
                break
            in_force, superseded, partial = self.current(pid)
            for cur in in_force:
                entry = chosen.setdefault(cur, {"reason": "match", "superseded": []})
                entry["superseded"] = sorted({*entry["superseded"], *(s for s in superseded if s != cur)})
            for amendment in [*partial, *self.amendments_inside(pid)]:
                if len(chosen) < top_k + MAX_RELATED and amendment not in chosen:
                    chosen[amendment] = {"reason": "amends_part_of", "of": pid, "superseded": []}
        # An article and one of its clauses: the clause is enough
        for pid in list(chosen):
            if any(c in chosen for c in self.children.get(pid, [])):
                chosen.pop(pid)
        if hops > 0:
            added = 0
            for cid in concepts[:2]:
                for req in self.requires.get(cid, []):
                    main = next((p for p in self.about.get(req, []) if self.current(p)[0] == [p]), None)
                    if main and main not in chosen and added < MAX_RELATED:
                        chosen[main] = {"reason": f"requires:{cid}->{req}", "superseded": []}
                        added += 1
        return self._bundle(chosen, concepts, context, best)

    def get(self, pid: str, hops: int = 1, context: dict | None = None) -> dict:
        if pid not in self.provisions:
            raise KeyError(pid)
        in_force, superseded, partial = self.current(pid)
        chosen = {pid: {"reason": "requested", "superseded": []}}
        for cur in in_force:
            if cur != pid:
                chosen[cur] = {"reason": "newer_version", "superseded": [pid]}
        for amendment in partial:
            chosen[amendment] = {"reason": "amends_part_of", "of": pid, "superseded": []}
        return self._bundle(chosen, [], context, None)

    def _result(self, pid: str, info: dict) -> dict:
        p = self.provisions[pid]
        doc = self.documents[p["doc"]]
        in_force, superseded, partial = self.current(pid)
        status = "in_force" if in_force == [pid] and not partial else ("partly_amended" if partial else "superseded")
        if not in_force:
            status = "repealed"
        label = doc["number"] or doc["title"]
        year = (doc["issued"] or "")[:4]
        title = f"{p['title']} — {label}{f' ({year})' if year else ''}"
        return {
            "id": pid,
            "reason": info["reason"],
            "evidence_role": "council_conclusion" if p["kind"] == "council_point" else "regulation",
            "verified": False,
            "superseded": info.get("superseded", []),
            "amended_by": partial,
            "status": status,
            "citation": {"document": doc["id"], "file_name": doc["file_name"], "pdf_pages": p["pages"]},
            "evidence": {
                "provision_id": pid,
                "title": title,
                "source_text": p["text"],
                "kind": p["kind"],
                "document_title": doc["title"],
                "issued": doc["issued"],
            },  # fmt: skip
        }

    def _bundle(self, chosen: dict[str, dict], concepts: list[str], context: dict | None, best: float | None) -> dict:
        results = [self._result(pid, info) for pid, info in chosen.items()]
        return {
            "status": "draft_evidence" if results else "no_evidence",
            "corpus_version": self.version,
            "retrieval_method": "graph_hybrid",
            "concepts": [{"id": c, "label": self.concepts[c]["label"]} for c in concepts],
            "results": results,
            "provided_context": context or {},
            "applicability_resolved": False,
            "notes": [
                "Mỗi kết quả là bản đang có hiệu lực; id bản cũ nằm ở `superseded`.",
                "Điều kiện theo khóa / chương trình nằm ngay trong câu chữ của khoản; đối chiếu với hồ sơ sinh viên.",
                "Kết luận Hội đồng học vụ là quyết định theo học kỳ, thứ bậc thấp hơn quy định.",
            ],
            "best_lexical_score": round(best, 3) if best is not None else None,
        }
