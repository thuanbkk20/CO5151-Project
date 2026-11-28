"""Extract the text of the source documents into `data/text/<id>.json`.

The PDFs and docx files are not in git (they are large); pass the folder that holds them. Files are found by sha256,
so a renamed file still matches and a changed file is reported instead of silently read.

    uv run --extra extract --package co5151-regulation-graph regulation-graph-extract --sources "quy chế tham khảo"
"""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .documents import DATA, TextMethod, load_documents

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_pages(path: Path) -> list[dict]:
    from pypdf import PdfReader

    return [{"page": i, "text": page.extract_text() or ""} for i, page in enumerate(PdfReader(path).pages, 1)]


def docx_paragraphs(path: Path) -> list[str]:
    root = ElementTree.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    paragraphs = ("".join(t.text or "" for t in p.iter(W + "t")).strip() for p in root.iter(W + "p"))
    return [p for p in paragraphs if p]


def extract(sources: Path, out: Path) -> list[str]:
    by_hash = {sha256(p): p for p in sources.iterdir() if p.is_file()}
    problems = []
    out.mkdir(parents=True, exist_ok=True)
    for doc in load_documents():
        if doc.text_method not in (TextMethod.PDF_TEXT, TextMethod.DOCX):
            continue
        path = by_hash.get(doc.sha256)
        if path is None:
            problems.append(f"{doc.id}: no file with sha256 {doc.sha256[:12]}… in {sources} ({doc.file_name})")
            continue
        body = {"pages": pdf_pages(path)} if doc.text_method is TextMethod.PDF_TEXT else {
            "paragraphs": docx_paragraphs(path)}  # fmt: skip
        record = {"id": doc.id, "sha256": doc.sha256, "text_method": doc.text_method.value, **body}
        (out / f"{doc.id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="regulation-graph-extract")
    p.add_argument("--sources", type=Path, required=True, help="thư mục chứa PDF/docx gốc")
    p.add_argument("--out", type=Path, default=DATA / "text")
    a = p.parse_args(argv)
    problems = extract(a.sources, a.out)
    for line in problems:
        print(line, file=sys.stderr)
    return 1 if problems else 0
