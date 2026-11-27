import json
import zipfile

from regulation_graph.documents import DATA, TextMethod, load_documents
from regulation_graph.extract import docx_paragraphs


def test_registry_loads_and_amendments_point_to_known_documents():
    docs = {d.id: d for d in load_documents()}
    assert "QD2933-2021" in docs
    assert docs["QD1260-2026"].amends == ["QD2933-2021"]


def test_every_extracted_text_matches_its_source_file():
    for doc in load_documents():
        if doc.text_method not in (TextMethod.PDF_TEXT, TextMethod.DOCX):
            continue
        record = json.loads((DATA / "text" / f"{doc.id}.json").read_text("utf-8"))
        assert record["sha256"] == doc.sha256, doc.id
        assert record.get("pages") or record.get("paragraphs"), doc.id


def test_docx_paragraphs_keep_text_runs_and_drop_empty_paragraphs(tmp_path):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    xml = (f"<w:document {w}><w:body><w:p><w:r><w:t>Điều 17.</w:t></w:r><w:r><w:t> Học lại</w:t></w:r></w:p>"
           "<w:p></w:p><w:p><w:r><w:t>17.1 Nội dung</w:t></w:r></w:p></w:body></w:document>")  # fmt: skip
    path = tmp_path / "a.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    assert docx_paragraphs(path) == ["Điều 17. Học lại", "17.1 Nội dung"]
