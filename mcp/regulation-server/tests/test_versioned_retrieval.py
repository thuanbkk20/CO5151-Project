import json
import tempfile
import unittest
from pathlib import Path

from regulation_server.retrieve_versioned_regulations import retrieve


class VersionRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.items = [{"provision_id": x, "source_text": x, "verified": False} for x in ["old", "new", "later"]]
        self.edges = [
            dict(source="new", target="old", relation="AMENDS", evidence_provision_id="new"),
            dict(source="later", target="new", relation="REPLACES", evidence_provision_id="later"),
        ]
        self.write()

    def write(self):
        for name, data in [("provisions", self.items), ("version_relations", self.edges)]:
            (self.folder / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")

    def lookup(self, key):
        return retrieve(self.folder, key, allow_draft=True)

    def test_default_blocks_draft(self):
        self.assertEqual(retrieve(self.folder, "old")["status"], "draft_blocked")

    def test_old_finds_amendment(self):
        r = self.lookup("old")
        self.assertEqual({x["provision_id"] for x in r["evidence"]}, {"old", "new"})
        self.assertIsNone(r["eligibility_decision"])

    def test_new_finds_old_and_replacement(self):
        self.assertEqual(len(self.lookup("new")["evidence"]), 3)

    def test_preserves_original_evidence(self):
        self.assertEqual(self.lookup("old")["evidence"][0], self.items[1])

    def test_unknown(self):
        self.assertEqual(self.lookup("missing")["status"], "not_found")

    def test_dangling_is_rejected(self):
        self.edges[0]["target"] = "missing"
        self.write()
        with self.assertRaises(ValueError):
            self.lookup("old")

    def test_duplicate_is_rejected(self):
        self.items.append(self.items[0])
        self.write()
        with self.assertRaises(ValueError):
            self.lookup("old")

    def test_repeal(self):
        self.edges[0]["relation"] = "REPEALS"
        self.write()
        self.assertEqual(self.lookup("old")["relations"][0]["relation"], "REPEALS")


if __name__ == "__main__":
    unittest.main()
