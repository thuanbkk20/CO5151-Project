import unittest
from pathlib import Path

from regulation_server.regulation_service_v2 import INPUTS, RegulationServiceV2

BASE = Path(__file__).resolve().parents[1]


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = RegulationServiceV2(BASE, allow_draft=True)

    def data(self, name, args):
        r = self.s.call(name, args)
        self.assertTrue(r.ok)
        return r.data

    def ids(self, result):
        return {r["id"] for r in result["results"]}

    def test_default_denies(self):
        r = RegulationServiceV2(BASE).call("get_provision", {"provision_id": "QD2933-2021-CL5.5"})
        self.assertEqual(r.error.code, "FORBIDDEN")

    def test_schema_closed(self):
        for m in INPUTS.values():
            self.assertFalse(m.model_json_schema()["additionalProperties"])

    def test_invalid_arguments(self):
        for args in [
            {"query": " "},
            {"query": "test", "top_k": True},
            {"query": "test", "top_k": "1"},
            {"query": "test", "hops": 4},
            {"query": "test", "student_id": "1"},
            {"query": "test", "allow_draft": True},
            {"query": "test", "context": {"cohort": "2021"}},
            {"query": "test", "context": {"as_of_date": "2026-02-30"}},
            {"query": "test", "context": {"extra": "bad"}},
        ]:
            with self.subTest(args=args):
                self.assertEqual(
                    self.s.call("search_regulations", args).error.code,
                    "INVALID_ARGUMENT",
                )

    def test_unknown_tool(self):
        self.assertEqual(self.s.call("delete_all", {}).error.code, "NOT_FOUND")

    def test_missing_provision(self):
        self.assertEqual(
            self.s.call("get_provision", {"provision_id": "missing"}).error.code,
            "NOT_FOUND",
        )

    def test_amendment_both_directions(self):
        for key in ["QD2933-2021-CL5.5", "QD1260-2026-CL5.5"]:
            ids = self.ids(self.data("get_provision", {"provision_id": key}))
            self.assertTrue({"QD2933-2021-CL5.5", "QD1260-2026-CL5.5"} <= ids)

    def test_multihop_replacement(self):
        r = self.data("get_provision", {"provision_id": "QD1260-2026-APP1", "hops": 3})
        self.assertTrue({"QD2933-2021-APP1", "QD1260-2026-APP1", "QD2749-2026-APP1"} <= self.ids(r))
        self.assertEqual(len(r["results"]), len(self.ids(r)))

    def test_repeal_has_source(self):
        r = self.data("get_provision", {"provision_id": "QD2933-2021-CL5.4"})
        self.assertIn("QD1260-2026-DECISION-ART2", self.ids(r))
        self.assertTrue(any(p["relation"] == "REPEALS" for p in r["graph_paths"]))

    def test_zero_hops(self):
        r = self.data("get_provision", {"provision_id": "QD2933-2021-CL5.5", "hops": 0})
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["graph_paths"], [])

    def test_certificate_reference(self):
        r = self.data(
            "search_regulations",
            {
                "query": "Các chứng chỉ tiếng Anh gồm đầy đủ kỹ năng xét tốt nghiệp",
                "top_k": 1,
            },
        )
        self.assertIn("HCMUT-2749-2026-A31", self.ids(r))

    def test_thesis_with_language_and_registration(self):
        r = self.data(
            "search_regulations",
            {"query": "Điều kiện đăng ký khóa luận tốt nghiệp", "top_k": 1},
        )
        self.assertTrue({"HCMUT-2749-2026-A2-THESIS", "QD1260-2026-CL5.5", "QD2933-2021-CL5.5"} <= self.ids(r))

    def test_context_is_not_approval(self):
        r = self.data(
            "get_provision",
            {
                "provision_id": "QD1260-2026-CL5.5",
                "context": {
                    "program": "chinh quy",
                    "cohort": 2021,
                    "semester": "HK1 2026-2027",
                    "as_of_date": "2026-10-24",
                },
            },
        )
        self.assertFalse(r["applicability_resolved"])
        self.assertIsNone(r["eligibility_decision"])
        self.assertEqual(r["missing_context"], [])

    def test_negative_weather(self):
        r = self.data("search_regulations", {"query": "Thời tiết ngày mai"})
        self.assertEqual(r["status"], "no_evidence")

    def test_citations_and_raw_text(self):
        r = self.data("get_provision", {"provision_id": "QD1260-2026-CL5.5", "hops": 0})
        x = r["results"][0]
        self.assertEqual(x["citation"]["pdf_pages"], [3, 4])
        self.assertIn("82.5%", x["evidence"]["source_text"])
        self.assertFalse(x["verified"])

    def test_handbook_and_faq_indexed(self):
        supplemental = [p for p in self.s.engine.nodes.values() if p["evidence_role"] == "supplemental"]
        self.assertEqual(len(supplemental), 118)
        faq = next(p for p in supplemental if p.get("block_index"))
        r = self.data("get_provision", {"provision_id": faq["provision_id"], "hops": 0})
        self.assertEqual(r["results"][0]["citation"]["pdf_pages"], [])
        self.assertEqual(r["results"][0]["evidence_role"], "supplemental")


if __name__ == "__main__":
    unittest.main()
