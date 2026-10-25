"""Offline Learning Center resource contract tests."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "learn" / "topics.json"

class LearningContentTests(unittest.TestCase):
    def test_offline_manifest_and_stable_ids(self):
        data = json.loads(DOC.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        topics = data["topics"]
        self.assertGreaterEqual(len(topics), 15)
        ids = [topic["id"] for topic in topics]
        self.assertEqual(len(ids), len(set(ids)))
        for required in ("manual.getting_started","technique.ftir","technique.xrd",
                         "technique.uvvis","technique.raman","technique.xps",
                         "technique.libs","analysis.scherrer","analysis.tauc",
                         "processing.baseline","processing.smoothing"):
            self.assertIn(required, ids)
        for topic in topics:
            for key in ("id","title","category","html"):
                self.assertTrue(topic[key].strip())

if __name__ == "__main__":
    unittest.main()
