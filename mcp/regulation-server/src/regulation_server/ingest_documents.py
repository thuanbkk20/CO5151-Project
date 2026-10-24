"""Inventory PDF/DOCX sources without modifying them. Requires PyMuPDF."""

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def write_json(path, value):
    # Replace only complete outputs; never truncate an existing output on error.
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def word_text(element):
    return "".join(node.text or "" for node in element.iter(W + "t"))


def extract(path, digest):
    source_id = "sha256:" + digest
    records = []
    info = {
        "source_id": source_id,
        "file_name": path.name,
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "source_url": None,
        "document_number": None,
        "effective_from": None,
        "applicability": None,
        "verified": False,
    }
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as document:
            if document.needs_pass:
                raise ValueError("PDF requires a password")
            info["page_count"] = len(document)
            for index, page in enumerate(document, 1):
                text = page.get_text("text", sort=True)
                count = len("".join(text.split()))
                # Heuristic only: not a quality or OCR accuracy assessment.
                status = (
                    "needs_ocr"
                    if count == 0
                    else "needs_review"
                    if count < 30
                    else "extracted"
                )
                records.append(
                    {
                        "source_id": source_id,
                        "file_name": path.name,
                        "unit_id": f"{source_id}:page:{index}",
                        "unit_type": "pdf_page",
                        "pdf_page": index,
                        "status": status,
                        "text": text,
                        "non_whitespace_characters": count,
                        "verified": False,
                    }
                )
    else:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        body = root.find(W + "body")
        if body is None:
            raise ValueError("DOCX has no document body")
        info["page_count"] = None
        info["page_note"] = (
            "DOCX pagination is not inferred; block order follows document.xml"
        )
        for index, element in enumerate(body, 1):
            if element.tag not in {W + "p", W + "tbl"}:
                continue
            table = element.tag == W + "tbl"
            rows = (
                [
                    [word_text(cell) for cell in row.findall(W + "tc")]
                    for row in element.findall(W + "tr")
                ]
                if table
                else None
            )
            text = (
                "\n".join(" | ".join(row) for row in rows)
                if table
                else word_text(element)
            )
            if not text.strip():
                continue
            record = {
                "source_id": source_id,
                "file_name": path.name,
                "unit_id": f"{source_id}:block:{index}",
                "unit_type": "docx_table" if table else "docx_paragraph",
                "block_index": index,
                "pdf_page": None,
                "status": "needs_review" if table else "extracted",
                "text": text,
                "verified": False,
            }
            if table:
                record["rows"] = rows
            records.append(record)
    if not records:
        raise ValueError("No text units found")
    info["unit_count"] = len(records)
    info["status_counts"] = {
        s: sum(r["status"] == s for r in records)
        for s in ("extracted", "needs_review", "needs_ocr")
    }
    return info, records


def main():
    base = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw")
    parser.add_argument(
        "--out", type=Path, default=base / "data" / "processed" / "extraction"
    )
    args = parser.parse_args()
    raw, out = args.raw.resolve(), args.out.resolve()
    if not raw.is_dir():
        parser.error(f"Input directory not found: {raw}")
    if out == raw or raw in out.parents:
        parser.error("Output must be outside the raw directory")
    files = sorted(
        p
        for p in raw.iterdir()
        if p.is_file()
        and p.suffix.lower() in {".pdf", ".docx"}
        and not p.name.startswith("~$")
    )
    if not files:
        parser.error("No PDF/DOCX input files found")
    out.mkdir(parents=True, exist_ok=True)
    manifest, units, errors = [], [], []
    for path in files:
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            info, records = extract(path, digest)
            manifest.append(info)
            units.extend(records)
            print(f"OK {path.name}: {len(records)} units; {info['status_counts']}")
        except Exception as exc:  # noqa: BLE001 - retain per-document failure reports
            errors.append(
                {"file_name": path.name, "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"ERROR {path.name}: {type(exc).__name__}: {exc}")
    report = {
        "input_files": len(files),
        "successful_files": len(manifest),
        "errors": errors,
        "unit_count": len(units),
        "needs_ocr_pdf_pages": [
            {"file_name": r["file_name"], "pdf_page": r["pdf_page"]}
            for r in units
            if r["status"] == "needs_ocr"
        ],
        "limitations": [
            "No OCR performed",
            "No provision segmentation or table validation",
            "PDF page numbers are 1-based physical pages, not printed labels",
            "PDF table layout and reading order require human review",
            "DOCX headers, footers, text boxes and embedded images are not extracted",
            "All outputs are unverified; source metadata must be supplied separately",
        ],
    }
    write_json(out / "source_manifest.json", manifest)
    write_json(out / "text_units.json", units)
    write_json(out / "extraction_report.json", report)
    print(f"Output: {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
