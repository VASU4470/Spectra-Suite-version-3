"""Cross-platform startup checks for the PySide6 migration."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

import numpy as np
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from config import SessionState, state
from launcher import WelcomeDashboard, startup_smoke_test, workspace_command
from qt_general_plotter import GeneralPlotter
from qt_plot_viewer import PlotViewer
from qt_setup import SetupDialog


def reset_state(technique: str) -> None:
    fresh = SessionState()
    state.__dict__.clear()
    state.__dict__.update(fresh.__dict__)
    state.technique = technique
    if technique == "XRD":
        state.global_set["xlabel"] = "2θ (°)"
        state.global_set["ylabel"] = "Intensity (a.u.)"
    elif technique == "GENERAL":
        state.global_set["xlabel"] = "X"
        state.global_set["ylabel"] = "Y"
    elif technique == "UVVIS":
        state.global_set["xlabel"] = "Wavelength (nm)"
        state.global_set["ylabel"] = "Absorbance"
    elif technique == "RAMAN":
        state.global_set["xlabel"] = "Raman shift (cm⁻¹)"
        state.global_set["ylabel"] = "Intensity (a.u.)"


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_dashboard_smoke_entry_point(self):
        self.assertEqual(startup_smoke_test(), 0)

    def test_workspace_commands_cover_source_and_frozen_builds(self):
        program, arguments = workspace_command("ir")
        self.assertEqual(program, sys.executable)
        self.assertEqual(arguments[-2:], ["--workspace", "ir"])
        self.assertTrue(arguments[0].endswith("launcher.py"))

        with patch.object(sys, "frozen", True, create=True):
            program, arguments = workspace_command("xrd")
        self.assertEqual(program, sys.executable)
        self.assertEqual(arguments, ["--workspace", "xrd"])

    def test_dashboard_contains_all_workspaces(self):
        dashboard = WelcomeDashboard()
        dashboard.show()
        self.app.processEvents()
        self.assertEqual(set(dashboard._buttons), {"ir", "xrd", "uvvis", "raman", "general"})
        dashboard.close()

    def test_setup_dialog_constructs_for_every_technique(self):
        for technique in ("FTIR", "XRD", "UVVIS", "RAMAN", "GENERAL"):
            with self.subTest(technique=technique):
                reset_state(technique)
                dialog = SetupDialog()
                dialog.show()
                self.app.processEvents()
                self.assertEqual(state.technique, technique)
                dialog.reject()

    def test_plot_viewer_constructs_for_every_technique(self):
        x = np.linspace(400.0, 4000.0, 101)
        y = np.sin(x / 180.0) + 2.0
        for technique in ("FTIR", "XRD", "UVVIS", "RAMAN", "GENERAL"):
            with self.subTest(technique=technique):
                reset_state(technique)
                stem = f"synthetic_{technique.lower()}"
                state.all_data = [(stem, x.copy(), y.copy())]
                state.init_file_settings()
                viewer = PlotViewer(state.all_data, f"{technique} smoke test")
                viewer.show()
                self.app.processEvents()
                self.assertIsNotNone(viewer.ax)
                self.assertEqual(viewer.current_stem, stem)
                self.assertEqual(viewer.finish_button.text(), "Finish & Close")
                self.assertEqual(
                    viewer.xrd_height_label.isHidden(), technique != "XRD"
                )
                self.assertEqual(
                    viewer.xrd_height_spin.isHidden(), technique != "XRD"
                )
                viewer._skip_close_prompt = True
                viewer.close()

    def test_general_spreadsheet_plotter_constructs_and_plots(self):
        plotter = GeneralPlotter()
        plotter.table.setItem(0, 0, QTableWidgetItem("1"))
        plotter.table.setItem(0, 1, QTableWidgetItem("2"))
        plotter.table.setItem(1, 0, QTableWidgetItem("2"))
        plotter.table.setItem(1, 1, QTableWidgetItem("4"))
        plotter.plot_data()
        self.assertEqual(plotter.table.columnCount(), 2)
        self.assertEqual(plotter.x_column.currentText(), "X")
        self.assertEqual([item.text() for item in plotter.y_columns.selectedItems()], ["Y"])
        self.assertGreaterEqual(plotter.style_series.minimumWidth(), 210)
        self.assertFalse(plotter.windowIcon().isNull())
        for chart in plotter.CHARTS:
            with self.subTest(chart=chart):
                plotter.chart_type.setCurrentText(chart)
                plotter.plot_data()
                self.assertEqual(len(plotter.figure.axes), 1)
        plotter.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
