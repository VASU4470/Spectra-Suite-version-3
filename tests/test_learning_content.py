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
        self.assertGreaterEqual(len(topics), 26)
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

class LearningCenterGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_topic_ids_and_search(self):
        from qt_learning_center import LearningCenterDialog
        dlg = LearningCenterDialog(initial_topic="analysis.scherrer")
        self.assertIn("Scherrer", dlg.content.toPlainText())
        dlg.search.setText("Kubelka")
        visible = [
            dlg.topic_list.item(i).text()
            for i in range(dlg.topic_list.count())
            if not dlg.topic_list.item(i).isHidden()
            and dlg.topic_list.item(i).data(256) is not None
        ]
        self.assertTrue(any("Kubelka" in item for item in visible))
        dlg.close()

if __name__ == "__main__":
    unittest.main()
