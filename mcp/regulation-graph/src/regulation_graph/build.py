"""Build `data/graph.json` from the extracted texts: provisions, containment and amendment edges, concepts.

Concepts (`data/concepts.json`) are curated by hand: academic topics with the words students use for them ("ra trường",
"nhận bằng", "LVTN"), `ABOUT` edges to the provisions that rule them and `REQUIRES` edges between topics.

    uv run --package co5151-regulation-graph regulation-graph-build

Deterministic and offline (no LLM): provisions are split with rules on the headings ("Điều 17.", "17.1", "PHỤ LỤC 3"),
amendments are read from the "Sửa đổi, bổ sung khoản x Điều y" items of the amending decisions. QĐ 2933, 1260 and 2749
come from the regulation-server data (Đức's OCR and split) so that both engines cite the same provision ids.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from .documents import DATA, Document, Kind, TextMethod, load_documents

REPO = Path(__file__).resolve().parents[4]
REGULATION_SERVER = REPO / "mcp/regulation-server/data/processed/versioned_regulations"
ARTICLE = re.compile(r"^Điều\s*(\d+)\s*\.\s*(.*)$")
CLAUSE = re.compile(r"^(\d+)\.(\d+)\.?\s+(.*)$")
APPENDIX = re.compile(r"^PHỤ LỤC\.?\s*(\d*)\.?\s*(.*)$", re.I)
VERSION_RELATIONS = {"AMENDS", "REPLACES", "REPEALS"}
# Letterhead and page numbers repeated on every page of the docx / PDF text
NOISE = re.compile(
    r"^(\d{1,3}|www\.hcmut\.edu\.vn|268 Lý Thường Kiệt.*|ĐẠI HỌC QUỐC GIA TP\. HỒ CHÍ MINH TRƯỜNG ĐẠI HỌC BÁCH KHOA)$"
)


def provision(pid, doc, kind, number, title, text, pages=(), parent=None) -> dict:
    return {"id": pid, "doc": doc, "kind": kind, "number": number, "title": title.strip(),
            "text": text.strip(), "pages": sorted(set(pages)), "parent": parent}  # fmt: skip


# --- regulation-server data (QĐ 2933, 1260, 2749) -----------------------------------------------------------------


def from_regulation_server(docs: dict[str, Document]) -> tuple[list[dict], list[dict]]:
    items = json.loads((REGULATION_SERVER / "provisions.json").read_text("utf-8"))
    out = []
    for p in items:
        doc = re.match(r"^(QD\d+-\d{4})", p["provision_id"]).group(1)
        if doc not in docs:
            continue
        number = re.sub(r"^QD\d+-\d{4}-(CL|ART|APP|DECISION-ART)", "", p["provision_id"])
        parent = None
        if p["kind"] == "clause":
            parent = f"{doc}-ART{number.split('.')[0]}"
        out.append(provision(p["provision_id"], doc, p["kind"], number, p["title"], p["source_text"], p["pdf_pages"],
                             parent))  # fmt: skip
    edges = [
        {
            "source": e["source"],
            "relation": e["relation"],
            "target": e["target"],
            "evidence": e.get("evidence_provision_id"),
        }  # fmt: skip
        for e in json.loads((REGULATION_SERVER / "version_relations.json").read_text("utf-8"))
        if e["relation"] in VERSION_RELATIONS
    ]
    return out, edges


# --- docx / text regulations (QĐ 2931, QĐ 2932) ----------------------------------------------------------------------


def split_regulation(doc: str, lines: list[tuple[str, int | None]], start: str) -> list[dict]:
    """Articles, their clauses and the appendices of a regulation whose body starts at the line `start`."""
    out: list[dict] = []
    current: dict | None = None
    clause: dict | None = None
    begun = False
    for line, page in lines:
        if not begun:
            begun = line.startswith(start)
            continue
        if m := APPENDIX.match(line):
            number = m.group(1) or "1"
            current = provision(f"{doc}-APP{number}", doc, "appendix", number, f"Phụ lục {number}. {m.group(2)}", "")
            clause = None
            out.append(current)
        elif (m := ARTICLE.match(line)) and not (current and current["kind"] == "appendix"):
            number, rest = m.group(1), m.group(2)
            # A docx heading sometimes runs into its first clause: "Điều 11.An toàn ... 11.1 An toàn trong thí nghiệm"
            title = re.split(rf"\s{number}\.1\s", rest)[0]
            current = provision(f"{doc}-ART{number}", doc, "article", number, f"Điều {number}. {title}", "")
            clause = None
            out.append(current)
            if title != rest:
                line = rest[len(title) :].strip()
                clause = _clause(doc, current, line)
                if clause:
                    out.append(clause)
        elif current and current["kind"] == "article" and (m := CLAUSE.match(line)) and m.group(1) == current["number"]:
            clause = _clause(doc, current, line)
            out.append(clause)
        elif line.startswith(("Chương ", "CHƯƠNG ")):
            continue
        if current is None:
            continue
        current["text"] += line + "\n"
        if page:
            current["pages"] = sorted({*current["pages"], page})
        if clause is not None and current["kind"] == "article":
            clause["text"] += line + "\n"
            if page:
                clause["pages"] = sorted({*clause["pages"], page})
    for p in out:
        p["text"] = p["text"].strip()
    return [p for p in out if p["text"]]


def _clause(doc: str, article: dict, line: str) -> dict | None:
    m = CLAUSE.match(line)
    if not m:
        return None
    number = f"{m.group(1)}.{m.group(2)}"
    return provision(f"{doc}-CL{number}", doc, "clause", number, f"Khoản {number}", "", parent=article["id"])


def docx_lines(doc: str) -> list[tuple[str, int | None]]:
    record = json.loads((DATA / "text" / f"{doc}.json").read_text("utf-8"))
    lines = (" ".join(p.split()) for p in record["paragraphs"])
    return [(line, None) for line in lines if not NOISE.match(line)]


def vision_lines(doc: str) -> list[tuple[str, int | None]]:
    lines, page = [], None
    for raw in (DATA / "vision" / f"{doc}.md").read_text("utf-8").splitlines():
        if m := re.match(r"^## Trang (\d+)$", raw):
            page = int(m.group(1))
        elif raw.strip() and not raw.startswith("<!--"):
            lines.append((raw.strip(), page))
    return lines


def pdf_lines(doc: str) -> list[tuple[str, int]]:
    record = json.loads((DATA / "text" / f"{doc}.json").read_text("utf-8"))
    lines = ((" ".join(line.split()), p["page"]) for p in record["pages"] for line in p["text"].splitlines())
    return [(line, page) for line, page in lines if line and not NOISE.match(line)]


# --- amending decision (QĐ 1259) -----------------------------------------------------------------------------------

ITEM = re.compile(r"^(\d+)\.\s+((?:Sửa đổi|Bổ sung)[^“]*?như sau:?)\s*(.*)$")
TARGET_CLAUSES = re.compile(r"khoản\s+([\d., ]+?)\s+Điều\s+(\d+)")
TARGET_ARTICLE = re.compile(r"Điều\s+(\d+)")


def split_amendments(doc: str, target: str, lines: list[tuple[str, int]]) -> tuple[list[dict], list[dict]]:
    """Items "N. Sửa đổi, bổ sung khoản x Điều y như sau: “…”" of Điều 1, the replaced appendices, and their edges."""
    out, edges = [], []
    end = max(i for i, (line, _) in enumerate(lines) if line.startswith("Điều 3. Quyết định này có hiệu lực"))
    second = max(i for i, (line, _) in enumerate(lines[:end]) if line.startswith("Điều 2."))
    first = next(i for i, (line, _) in enumerate(lines) if line.startswith("Điều 1."))
    current = None
    for line, page in lines[first + 1 : second]:
        if m := ITEM.match(line):
            head = m.group(2)
            clauses = TARGET_CLAUSES.search(head)
            if clauses:
                numbers = [n for n in re.split(r"[,\s]+", clauses.group(1)) if n]
                targets = [f"{target}-CL{n}" for n in numbers]
                pid = f"{doc}-CL{'-'.join(numbers)}"
                title = f"Nội dung mới khoản {', '.join(numbers)}"
            else:
                number = TARGET_ARTICLE.search(head).group(1)
                targets, pid, title = [f"{target}-ART{number}"], f"{doc}-ART{number}", f"Nội dung mới Điều {number}"
            current = provision(pid, doc, "amended_clause", pid.split("-", 2)[2], title, "", [page])
            partial = head.lower().lstrip().startswith(("sửa đổi, bổ sung điểm", "bổ sung điểm")) or "điểm " in head
            edges += [{"source": pid, "relation": "AMENDS", "target": t, "partial": partial} for t in targets]
            out.append(current)
            line = m.group(3)
        if current is not None and line:
            current["text"] += line + "\n"
            current["pages"] = sorted({*current["pages"], page})
    title = "Quyết định: Điều 2 về thay thế và bãi bỏ"
    tail = lines[second:end]
    text = "\n".join(line for line, _ in tail)
    decision = provision(f"{doc}-DECISION-ART2", doc, "issuance_article", "2", title, text, [p for _, p in tail])
    out.append(decision)
    body = " ".join(decision["text"].split())
    for number in re.findall(r"thay thế Phụ lục ([\d, ]+)", body):
        for n in re.findall(r"\d+", number):
            edges.append({"source": f"{doc}-APP{n}", "relation": "REPLACES", "target": f"{target}-APP{n}",
                          "evidence": decision["id"]})  # fmt: skip
    for n in re.findall(r"bãi bỏ Phụ lục (\d+)", body):
        edges.append({"source": decision["id"], "relation": "REPEALS", "target": f"{target}-APP{n}",
                      "evidence": decision["id"]})  # fmt: skip
    # Appendices printed after the signature
    appendix = None
    for line, page in lines[end:]:
        if m := APPENDIX.match(line):
            appendix = provision(f"{doc}-APP{m.group(1)}", doc, "appendix", m.group(1),
                                 f"Phụ lục {m.group(1)} bản {doc.split('-')[0][2:]}. {m.group(2)}", "")  # fmt: skip
            out.append(appendix)
        if appendix is not None:
            appendix["text"] += line + "\n"
            appendix["pages"] = sorted({*appendix["pages"], page})
    for p in out:
        p["text"] = p["text"].strip().strip("“”").strip()
    return out, edges


# --- council conclusions --------------------------------------------------------------------------------------------

POINT = re.compile(r"^(\d+)\.\s+(.+)$")


def split_points(doc: Document, lines: list[tuple[str, int]]) -> list[dict]:
    out, current = [], None
    for line, page in lines:
        if (m := POINT.match(line)) and len(m.group(2)) > 8:
            n = m.group(1)
            title = f"{doc.title}, mục {n}: {m.group(2)}"[:200]
            current = provision(f"{doc.id}-P{n}", doc.id, "council_point", n, title, "", [page])
            out.append(current)
        if current is not None:
            current["text"] += line + "\n"
            current["pages"] = sorted({*current["pages"], page})
    for p in out:
        p["text"] = p["text"].strip()
    # The same point number twice means a sub-list restarted inside a point: keep the first, merge the rest into it
    merged: dict[str, dict] = {}
    for p in out:
        if p["id"] in merged:
            merged[p["id"]]["text"] += "\n" + p["text"]
            merged[p["id"]]["pages"] = sorted({*merged[p["id"]]["pages"], *p["pages"]})
        else:
            merged[p["id"]] = p
    return list(merged.values())


# --- graph ----------------------------------------------------------------------------------------------------------


def build() -> dict:
    docs = {d.id: d for d in load_documents()}
    provisions, edges = from_regulation_server(docs)
    provisions += split_regulation("QD2931-2021", docx_lines("QD2931-2021"), "QUY ĐỊNH CHUNG VỀ HỌC VỤ VÀ ĐÀO TẠO")
    provisions += split_regulation("QD2932-2021", vision_lines("QD2932-2021"), "Chương 1.")
    amended, amendment_edges = split_amendments("QD1259-2026", "QD2931-2021", pdf_lines("QD1259-2026"))
    provisions += amended
    edges += amendment_edges
    for doc in docs.values():
        if doc.kind is Kind.COUNCIL_CONCLUSION and doc.text_method is TextMethod.PDF_TEXT:
            provisions += split_points(doc, pdf_lines(doc.id))
    ids = {p["id"] for p in provisions}
    if len(ids) != len(provisions):
        dup = sorted({p["id"] for p in provisions if sum(q["id"] == p["id"] for q in provisions) > 1})
        raise ValueError(f"duplicate provision ids: {dup}")
    for p in provisions:
        if p["parent"] and p["parent"] in ids:
            edges.append({"source": p["parent"], "relation": "CONTAINS", "target": p["id"]})
    # An amendment of a clause that was not split out lands on its article
    for e in edges:
        if e["target"] not in ids and e["relation"] in VERSION_RELATIONS:
            article = re.sub(r"-CL(\d+)\.\d+$", r"-ART\1", e["target"])
            if article in ids:
                e.update(target=article, partial=True)
    concepts = json.loads((DATA / "concepts.json").read_text("utf-8"))
    concept_ids = {c["id"] for c in concepts}
    for c in concepts:
        edges += [{"source": pid, "relation": "ABOUT", "target": c["id"]} for pid in c["about"]]
        edges += [{"source": c["id"], "relation": "REQUIRES", "target": t} for t in c.get("requires", [])]
    nodes = ids | concept_ids
    dangling = [e for e in edges if e["source"] not in nodes or e["target"] not in nodes]
    if dangling:
        raise ValueError(f"dangling edges: {dangling[:5]}")
    payload = {"documents": [d.model_dump(mode="json") for d in docs.values() if d.kind is not Kind.CONSOLIDATED],
               "provisions": provisions, "concepts": concepts, "edges": edges}  # fmt: skip
    payload["version"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="regulation-graph-build")
    p.add_argument("--out", type=Path, default=DATA / "graph.json")
    a = p.parse_args(argv)
    graph = build()
    a.out.write_text(json.dumps(graph, ensure_ascii=False, indent=1) + "\n", "utf-8")
    kinds: dict[str, int] = {}
    for prov in graph["provisions"]:
        kinds[prov["kind"]] = kinds.get(prov["kind"], 0) + 1
    print(f"{len(graph['provisions'])} provisions {kinds}, {len(graph['edges'])} edges -> {a.out}")
    return 0
