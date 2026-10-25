"""Merge two extraction/OCR batches into a separate, unverified corpus.

Checks input identities and raw-file hashes. Rejects incomplete batches.
Amendment mentions are review candidates, never approved graph edges.
"""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

from build_corpus import atomic


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def merge(base):
    folder = base / "data/processed"
    metadata = base / "data/source_metadata"
    blank_reviews = (
        read(metadata / "blank_page_reviews.json") if (metadata / "blank_page_reviews.json").exists() else []
    )
    blank = {
        r["unit_id"]: r
        for r in blank_reviews
        if r.get("assessment") == "visually_blank" and r.get("review_method") == "rendered_pdf_visual_inspection"
    }
    provenance = (
        read(metadata / "official_sources_step11.json") if (metadata / "official_sources_step11.json").exists() else []
    )
    provenance = {r["sha256"]: r for r in provenance}
    sources, result = {}, {}
    errors = []
    batch_counts = {}
    for label, extraction, ocr_folder, raw_folder in [
        ("initial", "extraction", "ocr", "raw"),
        ("additional", "additional_extraction", "additional_ocr", "raw_additional"),
    ]:
        manifests = read(folder / extraction / "source_manifest.json")
        units = read(folder / extraction / "text_units.json")
        expected = {r["unit_id"]: r for r in units}
        if len(expected) != len(units):
            errors.append(f"{label}: duplicate extraction unit_id")
        local_sources = {r["source_id"]: r for r in manifests}
        if len(local_sources) != len(manifests):
            errors.append(f"{label}: duplicate source_id")
        for sid, s in local_sources.items():
            if sid in sources:
                errors.append(f"{label}: source repeated across batches: {sid}")
            if sid != "sha256:" + s["sha256"]:
                errors.append(f"{label}: source_id/hash mismatch: {s['file_name']}")
            path = (base / "data" / raw_folder / s["file_name"]).resolve()
            if not path.is_relative_to((base / "data" / raw_folder).resolve()):
                errors.append(f"{label}: source path outside raw folder")
            elif not path.is_file() or digest(path) != s["sha256"]:
                errors.append(f"{label}: raw file missing or changed: {s['file_name']}")
            records = [u for u in units if u["source_id"] == sid]
            if len(records) != s["unit_count"]:
                errors.append(f"{label}: source unit count mismatch: {s['file_name']}")
            if s.get("page_count") is not None:
                pages = [r["pdf_page"] for r in records]
                if sorted(pages) != list(range(1, s["page_count"] + 1)):
                    errors.append(f"{label}: missing or duplicate PDF pages: {s['file_name']}")
            s = dict(s, ingestion_batch=label, verified=False)
            if s["sha256"] in provenance:
                s["provenance"] = provenance[s["sha256"]]
            sources[sid] = s
        ocr = {}
        for path in sorted((folder / ocr_folder).glob("*_page_*.json")):
            try:
                r = read(path)
                key = r["unit_id"]
                if key in ocr:
                    raise ValueError("duplicate OCR unit_id")
                u = expected.get(key)
                if u is None or u["status"] != "needs_ocr":
                    raise ValueError("unexpected OCR record")
                if any(r.get(k) != u[k] for k in ("source_id", "file_name", "pdf_page")):
                    raise ValueError("OCR metadata mismatch")
                if r.get("ocr_completed") is not True or r.get("extraction_method") != "ocr":
                    raise ValueError("incomplete OCR record")
                ocr[key] = r
            except (ValueError, KeyError, OSError) as exc:
                errors.append(f"{label}/{path.name}: {exc}")
        for key, u in expected.items():
            if key in result:
                errors.append(f"{label}: unit repeated across batches: {key}")
            if u["source_id"] not in local_sources:
                errors.append(f"{label}: unknown unit source: {key}")
                continue
            if u["status"] == "needs_ocr":
                if key not in ocr:
                    errors.append(f"{label}: missing OCR: {key}")
                    continue
                r = dict(ocr[key])
            else:
                r = dict(u, extraction_method="native")
            if not isinstance(r.get("text"), str):
                errors.append(f"{label}: invalid text: {key}")
                continue
            r.update(
                ingestion_batch=label,
                verified=False,
                review_status="needs_review",
                text_sha256=hashlib.sha256(r["text"].encode()).hexdigest(),
            )
            if not r["text"].strip():
                review = blank.get(key)
                if (
                    not review
                    or review.get("source_id") != u["source_id"]
                    or review.get("pdf_page") != u.get("pdf_page")
                ):
                    errors.append(f"{label}: unresolved empty text: {key}")
                else:
                    r["review_status"] = "blank_page_visually_reviewed"
                    r["blank_page_review"] = review
            result[key] = r
        batch_counts[label] = {
            "sources": len(manifests),
            "extraction_units": len(units),
        }
    if errors:
        return (
            None,
            None,
            {
                "errors": errors,
                "corpus_written": False,
                "batch_counts": batch_counts,
                "note": "Any prior expanded corpus is unchanged; read this report before using it.",
            },
        )
    rows = list(result.values())
    report = {
        "errors": [],
        "corpus_written": True,
        "source_count": len(sources),
        "unit_count": len(rows),
        "batch_counts": batch_counts,
        "methods": dict(Counter(r["extraction_method"] for r in rows)),
        "reviewed_blank_pages": [
            {"unit_id": r["unit_id"], "pdf_page": r.get("pdf_page")} for r in rows if "blank_page_review" in r
        ],
        "all_content_unverified": True,
        "ready_for_content_review": True,
        "active_mcp_graph_updated": False,
    }
    return rows, list(sources.values()), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = parser.parse_args()
    base = a.base.resolve()
    out = base / "data/processed/corpus_expanded"
    out.mkdir(parents=True, exist_ok=True)
    try:
        corpus, sources, report = merge(base)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        corpus = sources = None
        report = {"errors": [str(exc)], "corpus_written": False}
    if corpus is not None:
        candidates = []
        for record in corpus:
            if record["extraction_method"] != "native" or record["unit_type"] != "pdf_page":
                continue
            if record["ingestion_batch"] != "additional" and "2749" not in record["text"]:
                continue
            for line in record["text"].splitlines():
                if re.search(r"Sửa đổi, bổ sung|[Tt]hay thế|[Bb]ãi bỏ", line):
                    candidates.append(
                        {
                            "candidate_id": f"AMEND-MENTION-{len(candidates) + 1:03d}",
                            "source_id": record["source_id"],
                            "unit_id": record["unit_id"],
                            "pdf_page": record["pdf_page"],
                            "source_line": line,
                            "mentioned_articles": re.findall(r"[Đđ]iều\s+(\d+)", line),
                            "relation": None,
                            "target_provision_id": None,
                            "review_status": "candidate_only",
                            "verified": False,
                            "note": (
                                "Line may be a heading/citation; inspect full page and continuation. "
                                "Article numbers mentioned are not automatically amendment targets."
                            ),
                        }
                    )
        for name, value in [
            ("corpus.json", corpus),
            ("source_manifest.json", sources),
            ("amendment_candidates.json", candidates),
        ]:
            atomic(out / name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "unit_id",
                "file_name",
                "pdf_page",
                "block_index",
                "review_status",
                "reviewer",
                "notes",
            ]
        )
        for r in corpus:
            writer.writerow(
                [
                    r["unit_id"],
                    r["file_name"],
                    r.get("pdf_page"),
                    r.get("block_index"),
                    r["review_status"],
                    "",
                    "",
                ]
            )
        atomic(out / "review_queue.csv", "\ufeff" + stream.getvalue())
        report["amendment_mentions_for_review"] = len(candidates)
    atomic(
        out / "merge_report.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Output:", out)
    return int(corpus is None)


if __name__ == "__main__":
    raise SystemExit(main())
