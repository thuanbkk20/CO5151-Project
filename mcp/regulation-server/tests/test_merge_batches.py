"""Synthetic integrity tests, not OCR or regulation-accuracy tests."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from regulation_server.merge_regulation_batches import merge


class MergeBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for label, raw, extracted, ocr in [
            ("a", "raw", "extraction", "ocr"),
            ("b", "raw_additional", "additional_extraction", "additional_ocr"),
        ]:
            root = self.base / "data"
            (root / raw).mkdir(parents=True)
            (root / "processed" / extracted).mkdir(parents=True)
            (root / "processed" / ocr).mkdir(parents=True)
            payload = ("synthetic fixture " + label).encode()
            (root / raw / (label + ".pdf")).write_bytes(payload)
            h = hashlib.sha256(payload).hexdigest()
            sid = "sha256:" + h
            unit = {
                "unit_id": sid + ":page:1",
                "source_id": sid,
                "file_name": label + ".pdf",
                "unit_type": "pdf_page",
                "pdf_page": 1,
                "text": "synthetic native" if label == "a" else "",
                "status": "extracted" if label == "a" else "needs_ocr",
            }
            source = {"source_id": sid, "sha256": h, "file_name": label + ".pdf", "unit_count": 1, "page_count": 1}
            (root / "processed" / extracted / "text_units.json").write_text(json.dumps([unit]))
            (root / "processed" / extracted / "source_manifest.json").write_text(json.dumps([source]))
            if label == "b":
                self.ocr_path = root / "processed" / ocr / "b_page_001.json"
                self.ocr = dict(unit, text="synthetic OCR", extraction_method="ocr", ocr_completed=True)
                self.save_ocr()

    def save_ocr(self):
        self.ocr_path.write_text(json.dumps(self.ocr))

    def test_complete_merge_keeps_identity_and_unverified(self):
        corpus, sources, report = merge(self.base)
        self.assertEqual((len(corpus), len(sources)), (2, 2))
        self.assertEqual(report["errors"], [])
        self.assertTrue(all(r["verified"] is False for r in corpus))
        self.assertFalse(report["active_mcp_graph_updated"])

    def test_missing_ocr_blocks_merge(self):
        self.ocr_path.unlink()
        self.assertIsNone(merge(self.base)[0])

    def test_wrong_raw_hash_blocks_merge(self):
        (self.base / "data/raw/a.pdf").write_bytes(b"changed fixture")
        self.assertIsNone(merge(self.base)[0])

    def test_duplicate_ocr_blocks_merge(self):
        self.ocr_path.with_name("duplicate_page_001.json").write_text(json.dumps(self.ocr))
        self.assertIsNone(merge(self.base)[0])

    def test_wrong_page_blocks_merge(self):
        self.ocr["pdf_page"] = 2
        self.save_ocr()
        self.assertIsNone(merge(self.base)[0])

    def test_unresolved_empty_blocks_merge(self):
        self.ocr["text"] = ""
        self.save_ocr()
        self.assertIsNone(merge(self.base)[0])

    def test_reviewed_blank_is_kept(self):
        self.ocr["text"] = ""
        self.save_ocr()
        folder = self.base / "data/source_metadata"
        folder.mkdir()
        review = {k: self.ocr[k] for k in ["unit_id", "source_id", "pdf_page"]}
        review.update(
            assessment="visually_blank", review_method="rendered_pdf_visual_inspection", note="synthetic fixture review"
        )
        (folder / "blank_page_reviews.json").write_text(json.dumps([review]))
        corpus, _, report = merge(self.base)
        self.assertEqual(len(corpus), 2)
        self.assertEqual(len(report["reviewed_blank_pages"]), 1)
        self.assertEqual(corpus[1]["text"], "")


if __name__ == "__main__":
    unittest.main()
