"""Smoke tests for the isolated UI-v2 desktop prototype."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

from PySide6.QtWidgets import QApplication, QMdiArea

from experimental.ui_v2.prototype import UIV2PrototypeWindow


class UIV2PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            widget.close()
        self.app.processEvents()

    def test_shell_has_expected_ribbon_and_two_documents(self):
        window = UIV2PrototypeWindow()
        window.show()
        self.app.processEvents()

        self.assertEqual(
            [window.ribbon_tabs.tabText(i) for i in range(window.ribbon_tabs.count())],
            ["Home", "Data", "Plot", "Process", "Analyze", "Annotate", "View", "Export"],
        )
        self.assertIsInstance(window.mdi, QMdiArea)
        self.assertEqual(set(window._subwindows), {"table", "plot"})
        self.assertEqual(len(window.mdi.subWindowList()), 2)

    def test_document_focus_changes_command_context(self):
        window = UIV2PrototypeWindow()
        window.show()
        self.app.processEvents()

        window.activate_document("table")
        self.app.processEvents()
        self.assertEqual(window.ribbon_tabs.tabText(window.ribbon_tabs.currentIndex()), "Data")
        self.assertIn("Raw Data", window.active_label.text())

        window.activate_document("plot")
        self.app.processEvents()
        self.assertEqual(window.ribbon_tabs.tabText(window.ribbon_tabs.currentIndex()), "Plot")
        self.assertIn("FT-IR Plot", window.active_label.text())

    def test_project_explorer_can_collapse_without_right_inspector(self):
        window = UIV2PrototypeWindow()
        window.show()
        self.app.processEvents()

        self.assertFalse(hasattr(window, "right_sidebar"))
        self.assertTrue(window.project_tree.isVisible())
        window.toggle_project_explorer()
        self.app.processEvents()
        self.assertFalse(window.project_tree.isVisible())
        self.assertLessEqual(window.project_panel.maximumWidth(), 34)


if __name__ == "__main__":
    unittest.main()
