"""Merge extracted units with OCR; never mark content as legally verified.

Standard library only. Structural errors produce a report and leave any prior
corpus unchanged. Missing/empty OCR produces a draft corpus and exit code 1.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from pathlib import Path


def atomic(path, text):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    root = a.base.resolve() / "data/processed"
    out = root / "corpus"
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        units = read(root / "extraction/text_units.json")
        sources = read(root / "extraction/source_manifest.json")
        if not isinstance(units, list) or not isinstance(sources, list):
            raise TypeError("Extraction inputs must be JSON arrays")
        source_map = {s["source_id"]: s for s in sources}
        by_id = {u["unit_id"]: u for u in units}
        if len(source_map) != len(sources) or len(by_id) != len(units):
            raise ValueError("Duplicate source_id or unit_id in extraction")
        for source_id, source in source_map.items():
            records = [u for u in units if u["source_id"] == source_id]
            if len(records) != source["unit_count"]:
                errors.append("Unit count mismatch: " + source["file_name"])
            if source.get("page_count") is not None:
                pages = [u["pdf_page"] for u in records]
                if sorted(pages) != list(range(1, source["page_count"] + 1)):
                    errors.append("Missing/duplicate PDF pages: " + source["file_name"])
        ocr = {}
        for path in sorted((root / "ocr").glob("*_page_*.json")):
            try:
                r = read(path)
                key = r["unit_id"]
                if key in ocr:
                    raise ValueError("Duplicate OCR unit_id")
                original = by_id.get(key)
                if original is None:
                    raise ValueError(
                        "OCR has no matching extraction unit; stale source?"
                    )
                for field in ("source_id", "file_name", "pdf_page"):
                    if r[field] != original[field]:
                        raise ValueError("OCR metadata mismatch: " + field)
                if (
                    original["status"] != "needs_ocr"
                    or r.get("extraction_method") != "ocr"
                ):
                    raise ValueError("Unexpected OCR record")
                if r.get("ocr_completed") is not True or not isinstance(
                    r.get("text"), str
                ):
                    raise ValueError("Incomplete OCR record")
                ocr[key] = r
            except Exception as exc:  # noqa: BLE001 - retain per-document failure reports
                errors.append(f"{path.name}: {exc}")
        corpus, review = [], []
        missing = []
        for u in units:
            if u["source_id"] not in source_map:
                errors.append("Unknown source: " + u["unit_id"])
                continue
            r = dict(u)
            needed = u["status"] == "needs_ocr"
            if needed and u["unit_id"] in ocr:
                r = dict(ocr[u["unit_id"]])
            r["extraction_method"] = r.get(
                "extraction_method", "pending_ocr" if needed else "native"
            )
            if not isinstance(r.get("text"), str):
                errors.append("Invalid text: " + u["unit_id"])
                continue
            if needed and (u["unit_id"] not in ocr or not r["text"].strip()):
                missing.append(u["unit_id"])
            # Verification must happen in a separate, explicit review workflow.
            r.update(
                verified=False,
                review_status="needs_review",
                text_sha256=hashlib.sha256(r["text"].encode("utf-8")).hexdigest(),
            )
            reasons = ["manual_source_comparison_required"]
            if needed:
                reasons.append("ocr_text_requires_review")
            if u["unit_id"] in missing:
                reasons.append("missing_or_empty_ocr")
            if r["unit_type"] == "pdf_page":
                reasons.append("check_reading_order_and_tables")
            corpus.append(r)
            review.append(
                {
                    "unit_id": r["unit_id"],
                    "file_name": r["file_name"],
                    "pdf_page": r.get("pdf_page"),
                    "block_index": r.get("block_index"),
                    "reasons": "; ".join(reasons),
                    "review_status": "needs_review",
                    "reviewer": "",
                    "notes": "",
                }
            )
        report = {
            "structural_errors": errors,
            "missing_or_empty_ocr": missing,
            "unit_count": len(corpus),
            "source_count": len(sources),
            "methods": dict(Counter(r["extraction_method"] for r in corpus)),
            "corpus_written": not bool(errors),
            "all_content_unverified": True,
            "ready_for_manual_review": not errors and not missing,
        }
    except Exception as exc:  # noqa: BLE001 - retain per-document failure reports
        report = {"structural_errors": [str(exc)], "corpus_written": False}
        errors = report["structural_errors"]
        missing = []
    if not errors:
        atomic(
            out / "corpus.json", json.dumps(corpus, ensure_ascii=False, indent=2) + "\n"
        )
        table = io.StringIO(newline="")
        fields = [
            "unit_id",
            "file_name",
            "pdf_page",
            "block_index",
            "reasons",
            "review_status",
            "reviewer",
            "notes",
        ]
        writer = csv.DictWriter(table, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review)
        atomic(out / "review_queue.csv", "\ufeff" + table.getvalue())
    atomic(
        out / "corpus_report.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Output:", out)
    return int(bool(errors or missing))


if __name__ == "__main__":
    raise SystemExit(main())
