"""Regression tests for the conservative lexical topic gate, not semantic accuracy."""

import unittest

import test_retrieval_local as fixtures

from regulation_server.retrieve_regulations import scope_matches


class ScopeTests(unittest.TestCase):
    def test_weather_has_no_topic_cue(self):
        self.assertEqual(scope_matches("Dự báo thời tiết ngày mai"), [])

    def test_unaccented_language_query(self):
        self.assertIn("chung chi", scope_matches("Chung chi con han bao lau?"))

    def test_accented_thesis_query(self):
        self.assertIn("khoa luan", scope_matches("Ngoại ngữ đăng ký khóa luận"))

    def test_token_boundaries(self):
        self.assertEqual(scope_matches("myieltsword"), [])

    def test_generic_question_is_conservatively_unresolved(self):
        self.assertEqual(scope_matches("Ngày nào hết hạn?"), [])

    def test_gate_does_not_prove_answerability(self):
        # A lexical cue can occur in an irrelevant question. Do not claim a
        # complete OOD classifier based on this small regression fix.
        self.assertIn("quyet dinh", scope_matches("Quyết định giá xăng ngày mai?"))


class ScopeIntegrationTests(unittest.TestCase):
    def setUp(self):
        fixtures.RetrievalTests.setUp(self)

    def test_weather_does_not_match_generic_date_word(self):
        r = self.engine.search("Dự báo thời tiết ngày mai", allow_draft=True)
        self.assertEqual(r["status"], "no_evidence")
        self.assertEqual(r["results"], [])
        self.assertEqual(r["scope_check"]["reason"], "insufficient_topic_context")


if __name__ == "__main__":
    unittest.main()
