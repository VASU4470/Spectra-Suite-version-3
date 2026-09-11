"""Cross-platform startup checks for SpectraSuite Version 3."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

import numpy as np
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QTableWidgetItem

from config import SessionState, state
from dataset_reader import SpectrumDataset
from launcher import WelcomeDashboard, startup_smoke_test, workspace_command
from qt_general_plotter import GeneralPlotter
from qt_plot_viewer import ExportOptionsDialog, PlotViewer, TextAnnotationDialog
from qt_setup import DatasetSelectionDialog, SetupDialog
from qt_widgets import AnnotationToolBar


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
        self.assertEqual(set(dashboard._buttons), {
            "ir", "xrd", "uvvis", "raman", "general", "plot3d",
            "multiaxis", "fluid", "xps",
        })
        self.assertEqual(
            list(dashboard._buttons),
            ["ir", "xrd", "uvvis", "raman", "general", "plot3d",
             "multiaxis", "fluid", "xps"],
        )
        self.assertTrue(all(not button.icon().isNull() for button in dashboard._buttons.values()))
        self.assertFalse(dashboard._buttons["multiaxis"].isEnabled())
        self.assertFalse(dashboard._buttons["fluid"].isEnabled())
        self.assertFalse(dashboard._buttons["xps"].isEnabled())
        self.assertIn("COMING SOON", dashboard._buttons["fluid"].text())
        dashboard.close()

    def test_annotation_tool_selector_is_horizontal_and_accessible(self):
        toolbar = AnnotationToolBar()
        toolbar.show()
        self.app.processEvents()
        self.assertEqual(len(toolbar._buttons), 6)
        self.assertEqual([button.toolTip() for button in toolbar._buttons], [
            "Select / move", "Text", "Arrow", "Line", "Rectangle", "Ellipse",
        ])
        self.assertTrue(all(button.width() == 44 and button.height() == 40
                            for button in toolbar._buttons))
        toolbar.setCurrentIndex(2)
        self.assertEqual(toolbar.currentData(), "arrow")
        toolbar.close()

    def test_rich_annotation_dialog_controls_remain_visible(self):
        reset_state("UVVIS")
        dialog = TextAnnotationDialog()
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.findChild(QScrollArea).widgetResizable())
        self.assertGreaterEqual(dialog.size_spin.minimumWidth(), 180)
        self.assertGreaterEqual(dialog.size_spin.minimumHeight(), 32)
        self.assertGreaterEqual(dialog.family_combo.minimumWidth(), 180)
        self.assertGreaterEqual(dialog.family_combo.minimumHeight(), 32)
        symbol_buttons = [
            button for button in dialog.findChildren(QPushButton)
            if button.text() in {label for label, _command in dialog.GREEK + dialog.SYMBOLS}
        ]
        self.assertEqual(len(symbol_buttons), len(dialog.GREEK) + len(dialog.SYMBOLS))
        self.assertTrue(all(button.width() == 44 and button.height() == 34
                            for button in symbol_buttons))
        dialog.reject()

    def test_setup_dialog_constructs_for_every_technique(self):
        for technique in ("FTIR", "XRD", "UVVIS", "RAMAN", "GENERAL"):
            with self.subTest(technique=technique):
                reset_state(technique)
                dialog = SetupDialog()
                dialog.show()
                self.app.processEvents()
                self.assertEqual(state.technique, technique)
                dialog.reject()

    def test_single_discovered_dataset_skips_selection_dialog(self):
        reset_state("UVVIS")
        dialog = SetupDialog()
        state.settings["files"] = ["one-spectrum.txt"]
        dataset = SpectrumDataset(
            "one-spectrum", np.arange(20.0), np.arange(20.0), "one-spectrum.txt"
        )
        with patch("qt_setup.discover_many", return_value=([dataset], [])):
            dialog.start()
        self.assertTrue(dialog.ready)
        self.assertEqual(len(state.pending_data), 1)
        self.assertEqual(state.settings["mode"], "individual")

    def test_embedded_baseline_is_excluded_from_selected_samples(self):
        reset_state("RAMAN")
        x = np.arange(20.0)
        datasets = [
            SpectrumDataset("sample", x, x + 3, "multi.txt"),
            SpectrumDataset("background", x, x + 1, "multi.txt"),
        ]
        dialog = DatasetSelectionDialog(datasets)
        dialog.list_widget.clearSelection()
        dialog.list_widget.item(0).setSelected(True)
        dialog.reference_combo.setCurrentIndex(2)
        dialog._choose(False)
        self.assertEqual([item.name for item in dialog.selected], ["sample"])
        self.assertEqual(dialog.reference_dataset.name, "background")

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
                self.assertTrue(viewer.legend_check.isChecked())
                self.assertTrue(viewer.auto_peak_threshold_check.isChecked())
                self.assertFalse(viewer.prominence_spin.isEnabled())
                self.assertGreater(viewer.maximum_peaks_spin.value(), 0)
                self.assertEqual(viewer.finish_button.text(), "Finish & Close")
                self.assertEqual(
                    viewer.xrd_height_label.isHidden(), technique != "XRD"
                )
                self.assertEqual(
                    viewer.xrd_height_spin.isHidden(), technique != "XRD"
                )
                self.assertLessEqual(viewer.toolbar.maximumHeight(), 32)
                viewer.controls_toggle.click()
                self.assertTrue(viewer.controls.isHidden())
                self.assertEqual(viewer.controls_toggle.text(), "▶")
                viewer.controls_toggle.click()
                self.assertFalse(viewer.controls.isHidden())
                self.assertEqual(viewer.controls_toggle.text(), "◀")
                viewer._skip_close_prompt = True
                viewer.close()

    def test_export_options_are_not_compressed(self):
        reset_state("XRD")
        dialog = ExportOptionsDialog()
        self.assertGreaterEqual(dialog.minimumWidth(), 430)
        self.assertGreaterEqual(dialog.format_combo.minimumWidth(), 190)
        self.assertGreaterEqual(dialog.dpi_combo.minimumWidth(), 190)
        dialog.reject()

    def test_peak_markers_point_correctly_and_labels_receive_space(self):
        x = np.linspace(200.0, 1000.0, 301)
        y = 1.0 + np.exp(-0.5 * ((x - 550.0) / 25.0) ** 2)
        for technique, expected_marker in (("FTIR", "v"), ("UVVIS", "^"), ("RAMAN", "^")):
            with self.subTest(technique=technique):
                reset_state(technique)
                state.all_data = [("sample", x.copy(), y.copy())]
                state.init_file_settings()
                state.file_set["sample"].update(
                    smooth=0,
                    do_baseline=False,
                    normalize=False,
                    derivative=0,
                    auto_clean_edges=False,
                    bg_sub=False,
                )
                index = int(np.argmin(y) if technique == "FTIR" else np.argmax(y))
                state.file_set["sample"]["labels"] = [(x[index], y[index], f"{x[index]:.1f}")]
                viewer = PlotViewer(state.all_data, "Peak label test")
                viewer.update_plot()
                markers = [line.get_marker() for line in viewer.ax.lines]
                self.assertIn(expected_marker, markers)
                if technique == "FTIR":
                    self.assertLess(viewer.ax.get_ylim()[0], float(np.min(y)))
                else:
                    self.assertGreater(viewer.ax.get_ylim()[1], float(np.max(y)))
                viewer._skip_close_prompt = True
                viewer.close()

    def test_xrd_fwhm_toggle_recalculates_label_margin(self):
        reset_state("XRD")
        x = np.linspace(20.0, 80.0, 301)
        y = 1.0 + 10.0 * np.exp(-0.5 * ((x - 40.0) / 0.4) ** 2)
        state.all_data = [("sample", x.copy(), y.copy())]
        state.init_file_settings()
        state.file_set["sample"]["xrd_peaks"] = [(40.0, 11.0, 0.9, 10.0)]
        viewer = PlotViewer(state.all_data, "XRD label test")
        with_details = viewer.ax.get_ylim()[1]
        viewer.show_fwhm_check.setChecked(False)
        without_details = viewer.ax.get_ylim()[1]
        self.assertGreater(with_details, without_details)
        viewer._skip_close_prompt = True
        viewer.close()

    def test_peak_labels_align_inward_at_horizontal_edges(self):
        reset_state("UVVIS")
        x = np.linspace(200.0, 800.0, 301)
        y = np.linspace(1.0, 2.0, 301)
        state.all_data = [("sample", x.copy(), y.copy())]
        state.init_file_settings()
        state.file_set["sample"].update(
            smooth=0, auto_clean_edges=False,
            labels=[(x[0], y[0], "left edge"), (x[-1], y[-1], "right edge")],
        )
        viewer = PlotViewer(state.all_data, "Edge label test")
        labels = {artist.get_text(): artist for artist in viewer.ax.texts}
        self.assertEqual(labels["left edge"].get_horizontalalignment(), "left")
        self.assertEqual(labels["right edge"].get_horizontalalignment(), "right")
        viewer._skip_close_prompt = True
        viewer.close()

    def test_legend_names_are_editable_without_renaming_source_data(self):
        reset_state("UVVIS")
        x = np.linspace(200.0, 800.0, 301)
        state.all_data = [
            ("sample.csv · Absorbance", x.copy(), np.sin(x)),
            ("sample.csv · Reference", x.copy(), np.cos(x)),
        ]
        state.settings["mode"] = "overlay"
        state.init_file_settings()
        viewer = PlotViewer(state.all_data, "Legend edit test")
        item = viewer.legend_name_list.item(0)
        item.setText("Ag sample")
        self.app.processEvents()
        self.assertEqual(state.file_set["sample.csv · Absorbance"]["custom_name"], "Ag sample")
        self.assertEqual(viewer.stems[0], "sample.csv · Absorbance")
        self.assertIn("Ag sample", [text.get_text() for text in viewer.ax.get_legend().texts])
        viewer._skip_close_prompt = True
        viewer.close()

    def test_xrd_peak_click_snaps_only_to_the_nearby_peak(self):
        reset_state("XRD")
        x = np.linspace(20.0, 80.0, 6001)
        nearby = 4.0 * np.exp(-0.5 * ((x - 30.0) / 0.08) ** 2)
        stronger_neighbour = 20.0 * np.exp(-0.5 * ((x - 30.8) / 0.08) ** 2)
        y = 1.0 + nearby + stronger_neighbour
        state.all_data = [("sample", x.copy(), y.copy())]
        state.init_file_settings()
        viewer = PlotViewer(state.all_data, "XRD snapping test")
        result = viewer.calculate_xrd_peak(30.0, x, y)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 30.0, places=2)
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
        self.assertLessEqual(plotter.toolbar.maximumHeight(), 32)
        self.assertEqual(plotter.y_columns.selectionMode().name, "ExtendedSelection")
        plotter.xlim_edit.setText("1, 2")
        plotter.ylim_edit.setText("2, 4")
        plotter.plot_data()
        self.assertEqual(tuple(round(value, 6) for value in plotter.figure.axes[0].get_xlim()), (1.0, 2.0))
        self.assertEqual(tuple(round(value, 6) for value in plotter.figure.axes[0].get_ylim()), (2.0, 4.0))
        plotter.table.selectColumn(1)
        plotter.set_selected_column_as_x()
        self.assertEqual(plotter.x_column.currentText(), "Y")
        plotter.x_column.setCurrentText("X")
        for chart in plotter.CHARTS:
            with self.subTest(chart=chart):
                plotter.chart_type.setCurrentText(chart)
                plotter.plot_data()
                self.assertEqual(len(plotter.figure.axes), 1)
        plotter.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
