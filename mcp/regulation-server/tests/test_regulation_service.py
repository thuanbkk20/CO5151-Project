import os
import sys
import unittest
from pathlib import Path

BASE = Path(os.environ.get("REGULATION_BASE", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(BASE / "src/regulation_server"))
from regulation_service import RegulationService  # noqa: E402 - bootstrap local src path before import

from co5151_contracts.envelope import ToolResult  # noqa: E402 - bootstrap local src path before import


class RegulationServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = BASE / "data/processed/language_structured/evidence_graph.json"
        cls.service = RegulationService(cls.path, allow_draft=True)

    def test_search_envelope(self):
        r = self.service.call("search_regulations", {"query": "chứng chỉ đầy đủ kỹ năng", "top_k": 1})
        self.assertTrue(r.ok)
        ToolResult.model_validate(r.model_dump())
        self.assertIsNone(r.data["eligibility_decision"])

    def test_get_provision(self):
        r = self.service.call("get_provision", {"provision_id": "HCMUT-2749-2026-A2-THESIS"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["citation"]["pdf_page"], 4)

    def test_extra_field_rejected(self):
        r = self.service.call("search_regulations", {"query": "test", "student_id": "2310001"})
        self.assertEqual(r.error.code.value, "INVALID_ARGUMENT")

    def test_wrong_type_rejected(self):
        r = self.service.call("search_regulations", {"query": "test", "top_k": "1"})
        self.assertEqual(r.error.code.value, "INVALID_ARGUMENT")

    def test_unknown_provision(self):
        r = self.service.call("get_provision", {"provision_id": "missing"})
        self.assertEqual(r.error.code.value, "NOT_FOUND")

    def test_draft_blocked(self):
        r = RegulationService(self.path).call("search_regulations", {"query": "test"})
        self.assertEqual(r.error.code.value, "FORBIDDEN")

    def test_schema_is_closed(self):
        d = self.service.describe()
        self.assertFalse(d["tools"][0]["input_schema"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
