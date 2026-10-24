"""OCR pending PDF pages. Run beside ingest_documents.py. Outputs remain unverified."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

import fitz
from ingest_documents import write_json


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    base = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=base)
    p.add_argument("--pages", help="Physical PDF pages, e.g. 10-12 or 10,12")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--download-models", action="store_true")
    p.add_argument("--dpi", type=int, default=300)
    a = p.parse_args()
    if not 72 <= a.dpi <= 600:
        p.error("--dpi must be between 72 and 600")
    base = a.base.resolve()
    models = base / "data" / "ocr_models"
    models.mkdir(parents=True, exist_ok=True)
    for lang in ("vie", "eng"):
        target = models / (lang + ".traineddata")
        if not target.exists():
            if not a.download_models:
                p.error("Missing OCR models. Run again with --download-models")
            print("Downloading language model: " + lang, flush=True)
            # Official Tesseract fast models; model hashes are recorded in outputs.
            url = (
                "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/"
                + target.name
            )
            temporary = target.with_suffix(".part")
            try:
                with (
                    urllib.request.urlopen(url, timeout=60) as src,
                    temporary.open("wb") as dst,
                ):
                    while chunk := src.read(1048576):
                        dst.write(chunk)
                if temporary.stat().st_size < 10000:
                    raise ValueError("Downloaded model is unexpectedly small")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    config = {
        "dpi": a.dpi,
        "language": "vie+eng",
        "pymupdf": fitz.VersionBind,
        "model_sha256": {
            lang: sha(models / (lang + ".traineddata")) for lang in ("vie", "eng")
        },
    }
    chosen = None
    if a.pages:
        chosen = set()
        try:
            for part in a.pages.split(","):
                limits = [int(x) for x in part.split("-")]
                if (
                    len(limits) not in (1, 2)
                    or min(limits) < 1
                    or limits[-1] < limits[0]
                ):
                    raise ValueError()
                chosen.update(range(limits[0], limits[-1] + 1))
        except ValueError:
            p.error("Invalid --pages; use 10-12 or 10,12")
    units = json.loads(
        (base / "data/processed/extraction/text_units.json").read_text(encoding="utf-8")
    )
    pending = [
        u
        for u in units
        if u["status"] == "needs_ocr" and (chosen is None or u["pdf_page"] in chosen)
    ]
    if not pending:
        p.error("No matching needs_ocr pages")
    output = base / "data/processed/ocr"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    completed = skipped = 0
    hashes = {}
    for unit in pending:
        page_number = unit["pdf_page"]
        digest = unit["source_id"].removeprefix("sha256:")
        source = base / "data/raw" / unit["file_name"]
        destination = output / f"{digest}_page_{page_number:03d}.json"
        try:
            if source not in hashes:
                hashes[source] = sha(source)
            if hashes[source] != digest:
                raise ValueError("Source changed since ingestion; run ingestion again")
            if a.resume and destination.exists():
                old = json.loads(destination.read_text(encoding="utf-8"))
                if (
                    old.get("unit_id") == unit["unit_id"]
                    and old.get("ocr_config") == config
                    and old.get("text", "").strip()
                ):
                    skipped += 1
                    print(f"SKIP {unit['file_name']} page {page_number}", flush=True)
                    continue
            with fitz.open(source) as document:
                page = document[page_number - 1]
                tp = page.get_textpage_ocr(
                    language="vie+eng", dpi=a.dpi, full=True, tessdata=str(models)
                )
                text = page.get_text("text", textpage=tp, sort=True)
            record = dict(unit)
            record.update(
                text=text,
                extraction_method="ocr",
                status="needs_review",
                ocr_completed=True,
                verified=False,
                ocr_config=config,
                non_whitespace_characters=len("".join(text.split())),
            )
            write_json(destination, record)
            completed += 1
            print(
                f"OK page {page_number}: {len(text)} characters; needs_review",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - retain per-document failure reports
            errors.append({"unit_id": unit["unit_id"], "error": str(exc)})
            print(f"ERROR page {page_number}: {exc}", flush=True)
    write_json(
        output / "last_run_report.json",
        {
            "selected": len(pending),
            "completed": completed,
            "skipped": skipped,
            "errors": errors,
            "note": "All OCR pages require manual review; tables are not normalized.",
        },
    )
    print(
        f"Completed={completed}, skipped={skipped}, errors={len(errors)}; output={output}"
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
