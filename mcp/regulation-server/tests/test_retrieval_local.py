"""Small synthetic tests: retrieval behavior, not regulation correctness."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/regulation_server"))
from retrieve_regulations import RegulationRetriever, tokens


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "graph.json"

        def data(text, page):
            return {"title": "", "source_text": text, "source_id": "doc", "unit_id": f"page:{page}", "pdf_page": page}

        self.graph = {
            "nodes": [
                {"id": "doc", "type": "Document", "document_number": "TEST"},
                {"id": "a", "type": "Provision", "data": data("Chứng chỉ ngoại ngữ", 3)},
                {"id": "b", "type": "Table", "data": dict(data("", 4), rows=[{"test": "conversion"}])},
                {"id": "c", "type": "Provision", "data": data("Học phí", 5)},
            ],
            "edges": [
                {"source": "a", "relation": "REFERENCES", "target": "b"},
                {"source": "doc", "relation": "CONTAINS", "target": "c"},
            ],
        }
        self.path.write_text(json.dumps(self.graph), encoding="utf-8")
        self.engine = RegulationRetriever(self.path)

    def test_draft_is_blocked_by_default(self):
        r = self.engine.search("chứng chỉ")
        self.assertEqual(r["status"], "draft_blocked")
        self.assertEqual(r["results"], [])

    def test_graph_adds_reference_beyond_top_k(self):
        r = self.engine.search("chứng chỉ", top_k=1, allow_draft=True)
        self.assertEqual([x["id"] for x in r["results"]], ["a", "b"])
        self.assertEqual(r["results"][1]["reason"], "graph_reference")
        self.assertEqual(r["results"][1]["citation"]["pdf_page"], 4)
        self.assertIsNone(r["eligibility_decision"])

    def test_zero_hops_disables_expansion(self):
        r = self.engine.search("chứng chỉ", top_k=1, hops=0, allow_draft=True)
        self.assertEqual([x["id"] for x in r["results"]], ["a"])

    def test_no_match_returns_no_evidence(self):
        r = self.engine.search("quantumxyz", allow_draft=True)
        self.assertEqual(r["status"], "no_evidence")
        self.assertEqual(r["graph_paths"], [])

    def test_accent_normalization(self):
        self.assertEqual(tokens("Chứng chỉ"), tokens("chung chi"))

    def test_invalid_input(self):
        for query, k, hops in [("", 1, 1), ("abc", 0, 1), ("abc", 1, 3)]:
            with self.assertRaises(ValueError):
                self.engine.search(query, k, hops)

    def test_dangling_graph_is_rejected(self):
        self.graph["edges"][0]["target"] = "missing"
        self.path.write_text(json.dumps(self.graph), encoding="utf-8")
        with self.assertRaises(ValueError):
            RegulationRetriever(self.path)


if __name__ == "__main__":
    unittest.main()
