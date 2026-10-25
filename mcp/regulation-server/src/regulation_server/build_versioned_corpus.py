"""Segment the reviewed five-source batch and build a draft version graph.

Preserves exact page substrings. Amendment edges describe source assertions;
they do not approve applicability, reconstruct consolidated law, or update MCP.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from .build_corpus import atomic

HASHES = {
    "2933": "8ed72d2173aee3dabb7f78a3b9f153fe91608fef703f31ee60cf13cd8dc4efcb",
    "1260": "71883b7763e49e17fbffba9f0d80667d0cee71933165c758c80fbcf0d460bfb1",
    "2749": "173ee609c71c9da3a1f5ecbb4c1d5a6ada2e965ce08b1c29c2ac642a55252c30",
}


class Builder:
    def __init__(self, corpus):
        self.corpus = corpus
        self.pages = {
            key: sorted(
                [r for r in corpus if r["source_id"] == "sha256:" + digest],
                key=lambda r: r["pdf_page"],
            )
            for key, digest in HASHES.items()
        }
        self.items, self.edges, self.issues = {}, [], []
        for key, count in [("2933", 48), ("1260", 21), ("2749", 6)]:
            if [r["pdf_page"] for r in self.pages[key]] != list(range(1, count + 1)):
                raise ValueError("Unexpected source/pages for QD " + key)

    def joined(self, key, start_page, end_page):
        text, spans = "", []
        for page in self.pages[key]:
            if start_page <= page["pdf_page"] <= end_page:
                start = len(text)
                text += page["text"]
                spans.append((start, len(text), page))
                text += "\n"
        return text, spans

    def add(self, pid, key, kind, text, spans, start=0, end=None, title=None):
        end = len(text) if end is None else end
        fragments = []
        for left, right, page in spans:
            lo, hi = max(start, left), min(end, right)
            if hi > lo:
                fragments.append(
                    {
                        "unit_id": page["unit_id"],
                        "pdf_page": page["pdf_page"],
                        "start_char": lo - left,
                        "end_char": hi - left,
                        "text": page["text"][lo - left : hi - left],
                    }
                )
        if not fragments or pid in self.items:
            raise ValueError("Empty or duplicate segment: " + pid)
        value = {
            "provision_id": pid,
            "kind": kind,
            "title": title or pid,
            "source_id": "sha256:" + HASHES[key],
            "file_name": self.pages[key][0]["file_name"],
            "unit_id": fragments[0]["unit_id"],
            "pdf_page": fragments[0]["pdf_page"],
            "pdf_pages": sorted({r["pdf_page"] for r in fragments}),
            "fragments": fragments,
            "source_text": "\n".join(r["text"] for r in fragments),
            "verified": False,
            "review_status": "needs_review",
            "applicability": None,
            "valid_from": None,
            "valid_to": None,
            "warning": "Original source version; not a consolidated or approved rule.",
        }
        value["source_text_sha256"] = hashlib.sha256(value["source_text"].encode()).hexdigest()
        self.items[pid] = value
        return value

    def page_block(self, pid, key, kind, first, last, title):
        text, spans = self.joined(key, first, last)
        return self.add(pid, key, kind, text, spans, title=title)

    def relation(self, source, relation, target, evidence_id, note=""):
        if source not in self.items or target not in self.items or evidence_id not in self.items:
            raise ValueError("Unresolved edge: " + source + " -> " + target)
        e = self.items[evidence_id]
        self.edges.append(
            {
                "source": source,
                "relation": relation,
                "target": target,
                "evidence_provision_id": evidence_id,
                "source_unit_ids": [f["unit_id"] for f in e["fragments"]],
                "verified": False,
                "applicability_resolved": False,
                "note": note,
            }
        )

    def build(self):
        # Only the attached regulation body, excluding the separate issuance decision.
        text, spans = self.joined("2933", 3, 15)
        headings = list(re.finditer(r"(?m)^[ \t]*Điều\s+(\d+)\s*\.?[^\n]*", text))
        if [int(m[1]) for m in headings] != list(range(1, 15)):
            raise ValueError("Base regulation article headings need manual review")
        for index, match in enumerate(headings):
            article = int(match[1])
            start = match.start()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            pid = f"QD2933-2021-ART{article}"
            self.add(pid, "2933", "article", text, spans, start, end, match[0].strip())
            markers = []
            for m in re.finditer(r"(?m)^[ \t]*(\d{1,2}\.\d+|81|§\.3)\b", text[start:end]):
                raw = m[1]
                canonical = raw
                if article == 5 and raw == "3.4":
                    canonical = "5.4"
                if article == 8 and raw == "81":
                    canonical = "8.1"
                if article == 8 and raw == "§.3":
                    canonical = "8.3"
                if canonical.split(".")[0] != str(article):
                    continue
                markers.append((start + m.start(), canonical, raw))
            for pos, (left, label, raw) in enumerate(markers):
                right = markers[pos + 1][0] if pos + 1 < len(markers) else end
                cid = f"QD2933-2021-CL{label}"
                record = self.add(cid, "2933", "clause", text, spans, left, right, "Khoản " + label)
                if raw != label:
                    record["heading_label_review"] = {
                        "ocr_label": raw,
                        "normalized_label": label,
                        "basis": "Compared rendered original PDF; source text has not been edited.",
                    }
                    self.issues.append(
                        {
                            "id": cid,
                            "issue": "OCR heading label differs from PDF",
                            "ocr_label": raw,
                            "pdf_label": label,
                        }
                    )
                self.relation(pid, "CONTAINS", cid, pid)
        for number, first, last in [
            (1, 16, 21),
            (2, 22, 24),
            (3, 25, 25),
            (4, 26, 30),
            (5, 31, 37),
            (6, 38, 39),
            (7, 40, 42),
            (8, 43, 47),
        ]:
            self.page_block(
                f"QD2933-2021-APP{number}",
                "2933",
                "appendix",
                first,
                last,
                "Phụ lục " + str(number),
            )
        # Quoted replacement/addition bodies, preserving multi-page content.
        text, spans = self.joined("1260", 2, 6)
        targets = [
            "3.1",
            "5.2",
            "5.3",
            "5.5",
            "7.1",
            "8.1",
            "8.2",
            "10.1",
            "12.2",
            "14.3",
        ]
        for clause in targets:
            found = list(re.finditer(r"“" + re.escape(clause) + r"\s", text))
            if len(found) != 1:
                raise ValueError("Expected one quoted amendment for " + clause)
            start = found[0].start()
            end = text.find("”", start + 1)
            if end < 0:
                raise ValueError("Unclosed amendment quote " + clause)
            pid = "QD1260-2026-CL" + clause
            item = self.add(
                pid,
                "1260",
                "amended_clause",
                text,
                spans,
                start,
                end + 1,
                "Nội dung mới khoản " + clause,
            )
            item["document_issue_date"] = "2026-03-16"
            item["application_warning"] = (
                "Check application semester/cohort in the clause; issue date alone is insufficient."
            )
            self.relation(
                pid,
                "AMENDS",
                "QD2933-2021-CL" + clause,
                pid,
                "Source uses sửa đổi/bổ sung. Preserve both versions; do not auto-select by issue date.",
            )
        start = text.index("Điều 2.")
        end = text.index("Điều 3.", start)
        admin = self.add(
            "QD1260-2026-DECISION-ART2",
            "1260",
            "issuance_article",
            text,
            spans,
            start,
            end,
            "Quyết định: Điều 2 về thay thế và bãi bỏ",
        )
        for number, first, last in [(1, 7, 11), (3, 12, 13), (4, 14, 18), (6, 19, 21)]:
            pid = f"QD1260-2026-APP{number}"
            self.page_block(
                pid,
                "1260",
                "appendix",
                first,
                last,
                "Phụ lục " + str(number) + " bản 1260",
            )
            self.relation(pid, "REPLACES", f"QD2933-2021-APP{number}", admin["provision_id"])
        for target in ["QD2933-2021-ART4", "QD2933-2021-CL5.4", "QD2933-2021-APP2"]:
            self.relation(admin["provision_id"], "REPEALS", target, admin["provision_id"])
        text, spans = self.joined("2749", 1, 1)
        start = text.index("Điều 1.")
        end = text.index("Điều 2.", start)
        self.add(
            "QD2749-2026-DECISION-ART1",
            "2749",
            "issuance_article",
            text,
            spans,
            start,
            end,
            "Quyết định: Điều 1 thay thế Phụ lục 1",
        )
        self.page_block("QD2749-2026-APP1", "2749", "appendix", 2, 6, "Phụ lục 1 bản 2749")
        for target in ["QD2933-2021-APP1", "QD1260-2026-APP1"]:
            self.relation("QD2749-2026-APP1", "REPLACES", target, "QD2749-2026-DECISION-ART1")
        # Source declarations also mention term replacement. Flag it separately;
        # do not rewrite historical source text or ignore the simultaneous repeal.
        self.issues.append(
            {
                "id": "TERM-REPLACEMENT",
                "source_provision_id": admin["provision_id"],
                "issue": (
                    "Review terminology replacement at clauses 4.1/4.2 and Appendix 6 together "
                    "with repeal of Article 4; no automatic historical text rewrite."
                ),
            }
        )
        self.issues.append(
            {
                "id": "COVERAGE",
                "issue": (
                    "Only selected changes in the supplied documents are mapped. General "
                    "regulation, other amendments and handbook/FAQ clause segmentation are not "
                    "complete."
                ),
            }
        )
        self.issues.append(
            {
                "id": "TRANSITION",
                "issue": (
                    "Original Appendix 8 contains cohort/semester transitional rules; must "
                    "review before resolving applicability."
                ),
            }
        )
        return list(self.items.values()), self.edges, self.issues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    folder = a.base.resolve() / "data/processed"
    corpus = json.loads((folder / "corpus_expanded/corpus.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "corpus_expanded/source_manifest.json").read_text(encoding="utf-8"))
    try:
        items, relations, issues = Builder(corpus).build()
    except (ValueError, KeyError) as exc:
        p.error(str(exc))
    nodes = [{"id": s["source_id"], "type": "Document", "data": s, "verified": False} for s in manifest]
    nodes += [{"id": r["provision_id"], "type": "Provision", "data": r} for r in items]
    edges = [
        {
            "source": r["source_id"],
            "relation": "CONTAINS",
            "target": r["provision_id"],
            "verified": False,
        }
        for r in items
    ] + relations
    graph = {
        "status": "draft_version_graph",
        "applicability_resolved": False,
        "ready_for_production_advising": False,
        "nodes": nodes,
        "edges": edges,
    }
    ids = {n["id"] for n in nodes}
    assert len(ids) == len(nodes) and all(e["source"] in ids and e["target"] in ids for e in edges)
    report = {
        "source_documents": len(manifest),
        "segmented_regulation_documents": 3,
        "segments": len(items),
        "base_articles": 14,
        "version_relations": sum(e["relation"] in ["AMENDS", "REPLACES", "REPEALS"] for e in relations),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "ocr_heading_label_reviews": sum("heading_label_review" in r for r in items),
        "all_content_unverified": True,
        "active_mcp_graph_updated": False,
    }
    out = folder / "versioned_regulations"
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("provisions.json", items),
        ("version_relations.json", relations),
        ("review_issues.json", issues),
        ("version_graph.json", graph),
        ("structure_report.json", report),
    ]:
        atomic(out / name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Output:", out)


if __name__ == "__main__":
    main()
