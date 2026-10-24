"""Validate OCR completeness/identity for the additional ingestion batch."""

import argparse
import json
from pathlib import Path

from build_corpus import atomic


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    folder = a.base.resolve() / "data/processed"
    review_path = a.base.resolve() / "data/source_metadata/blank_page_reviews.json"
    blank_reviews = {}
    if review_path.exists():
        for review in json.loads(review_path.read_text(encoding="utf-8")):
            if (
                review.get("assessment") == "visually_blank"
                and review.get("review_method") == "rendered_pdf_visual_inspection"
            ):
                blank_reviews[review["unit_id"]] = review
    units = json.loads(
        (folder / "additional_extraction/text_units.json").read_text(encoding="utf-8")
    )
    expected = {u["unit_id"]: u for u in units if u["status"] == "needs_ocr"}
    if not expected:
        p.error("No pages requiring OCR in the additional extraction batch")
    errors, empty, reviewed_blank = [], [], []
    seen = set()
    for path in sorted((folder / "additional_ocr").glob("*_page_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            key = record["unit_id"]
            if key in seen:
                raise ValueError("Duplicate unit_id")
            if key not in expected:
                raise ValueError(
                    "Unexpected OCR unit; stale source or wrong output directory"
                )
            original = expected[key]
            if any(
                record.get(k) != original[k]
                for k in ("source_id", "file_name", "pdf_page")
            ):
                raise ValueError("OCR metadata does not match extraction")
            if (
                record.get("ocr_completed") is not True
                or record.get("extraction_method") != "ocr"
            ):
                raise ValueError("OCR is not marked completed")
            if not isinstance(record.get("text"), str):
                raise TypeError("Invalid text field")
            seen.add(key)
            if not record["text"].strip():
                entry = {
                    "file_name": record["file_name"],
                    "pdf_page": record["pdf_page"],
                    "unit_id": key,
                }
                empty.append(entry)
                review = blank_reviews.get(key)
                if (
                    review
                    and review.get("source_id") == original["source_id"]
                    and review.get("pdf_page") == original["pdf_page"]
                ):
                    reviewed_blank.append(
                        {
                            **entry,
                            "assessment": review["assessment"],
                            "note": review["note"],
                        }
                    )
        except (ValueError, KeyError, OSError) as exc:
            errors.append({"file_name": path.name, "error": str(exc)})
    missing = [
        {"file_name": expected[k]["file_name"], "pdf_page": expected[k]["pdf_page"]}
        for k in sorted(
            expected.keys() - seen,
            key=lambda key: (expected[key]["file_name"], expected[key]["pdf_page"]),
        )
    ]
    acknowledged = {r["unit_id"] for r in reviewed_blank}
    unresolved = [r for r in empty if r["unit_id"] not in acknowledged]
    report = {
        "expected_pages": len(expected),
        "matched_pages": len(seen),
        "missing_pages": missing,
        "empty_pages": empty,
        "errors": errors,
        "reviewed_blank_pages": reviewed_blank,
        "unresolved_empty_pages": unresolved,
        "ready_for_content_review": not bool(missing or unresolved or errors),
        "content_accuracy_verified": False,
    }
    output = folder / "additional_ocr"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "validation_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(not report["ready_for_content_review"])


if __name__ == "__main__":
    raise SystemExit(main())
