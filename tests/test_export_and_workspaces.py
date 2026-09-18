"""Regression checks for exported documents and the new preview workspaces."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from config import state
from launcher import WORKSPACES, WelcomeDashboard
from plot_export import save_figure
from qt_export import FigureExportDialog
from qt_fluid_plotter import FluidPlotter
from qt_shell import InlineImportPage


class ExportRegressionTests(unittest.TestCase):
    def test_failed_export_preserves_existing_file_and_figure(self):
        figure = Figure(figsize=(4, 3))
        original_canvas = figure.canvas
        with TemporaryDirectory() as folder:
            output = Path(folder) / "figure.pdf"
            output.write_bytes(b"existing figure")
            def fail(path, **kwargs):
                Path(path).write_bytes(b"partial")
                raise RuntimeError("renderer failed")
            with patch.object(figure, "savefig", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "renderer failed"):
                    save_figure(figure, output, size_inches=(6, 4))
            self.assertEqual(output.read_bytes(), b"existing figure")
            self.assertEqual(list(Path(folder).iterdir()), [output])
        np.testing.assert_allclose(figure.get_size_inches(), [4, 3])
        self.assertIs(figure.canvas, original_canvas)

    def test_exact_png_dimensions_and_live_canvas_restoration(self):
        from PIL import Image
        figure = Figure(figsize=(4, 3))
        figure.add_subplot().plot([1, 2], [3, 4])
        canvas = figure.canvas
        with TemporaryDirectory() as folder:
            saved = save_figure(figure, Path(folder)/"figure.png", dpi=100,
                                size_inches=(3, 2), tight=False, transparent=True)
            with Image.open(saved) as image:
                self.assertEqual(image.size, (300, 200))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
        np.testing.assert_allclose(figure.get_size_inches(), [4, 3])
        self.assertIs(figure.canvas, canvas)


class PreviewWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_xps_libs_import_axes_pdf_and_session_round_trip(self):
        dashboard = WelcomeDashboard()
        x = np.linspace(200, 500, 301)
        y = 2 + np.exp(-((x-350)/3)**2)
        with TemporaryDirectory() as folder:
            data = Path(folder)/"spectrum.csv"
            np.savetxt(data, np.column_stack((x, y)), delimiter=",")
            for key in ("xps", "libs"):
                with self.subTest(workspace=key):
                    workspace = next(item for item in WORKSPACES if item.key == key)
                    with patch("qt_shell.QTimer.singleShot"):
                        dashboard.launch_workspace(workspace)
                    page = dashboard.document_tabs.currentWidget()
                    self.assertIsInstance(page, InlineImportPage)
                    self.assertEqual(page.smoothing.value(), 0)
                    page.add_paths([str(data)])
                    viewer = dashboard.document_tabs.currentWidget()
                    self.assertEqual(state.technique, key.upper())
                    axis = viewer.figure.axes[0]
                    self.assertEqual(axis.xaxis_inverted(), key == "xps")
                    np.testing.assert_allclose(viewer.get_processed_data_for_stem(viewer.current_stem)[1], y)
                    viewer.auto_find_peaks()
                    self.assertTrue(state.file_set[viewer.current_stem]["labels"])
                    save_figure(viewer.figure, Path(folder)/f"{key}.pdf")
                    session = str(Path(folder)/f"{key}.json")
                    with patch("qt_plot_viewer.QFileDialog.getSaveFileName", return_value=(session, "")), \
                         patch("qt_plot_viewer.QMessageBox.information"):
                        self.assertTrue(viewer.save_session(save_as=True))
                    with patch("qt_shell.QFileDialog.getOpenFileName", return_value=(session, "")):
                        dashboard.open_session()
                    self.assertEqual(state.technique, key.upper())
                    self.assertEqual(dashboard.document_tabs.currentWidget().figure.axes[0].xaxis_inverted(), key=="xps")

    def test_fluid_opens_in_shell_and_removal_keeps_selection_valid(self):
        dashboard = WelcomeDashboard()
        workspace = next(item for item in WORKSPACES if item.key == "fluid")
        dashboard.launch_workspace(workspace)
        plotter = dashboard.document_tabs.currentWidget()
        self.assertIsInstance(plotter, FluidPlotter)
        text = 'VARIABLES="X" "Y" "U"\nZONE I=2,J=2,F=POINT\n0 0 1\n1 0 2\n0 1 3\n1 1 4\n'
        with TemporaryDirectory() as folder:
            paths = [Path(folder)/f"field{i}.dat" for i in range(3)]
            for path in paths:
                path.write_text(text)
            plotter.load_paths(paths)
            self.assertTrue(plotter.figure.axes)
            plotter.file_list.selectAll()
            plotter.remove_selected()
            self.assertEqual(plotter.fields, [])
            self.assertEqual(plotter.file_list.count(), 0)
            self.assertEqual(len(plotter.figure.axes), 0)

    def test_figure_export_dimensions_and_jpeg_transparency(self):
        dialog = FigureExportDialog(Figure(figsize=(4, 3)))
        self.assertEqual(dialog.width.value(), 101.6)
        self.assertFalse(dialog.options()["tight"])
        dialog.transparent.setChecked(True)
        dialog.format.setCurrentText("JPG")
        self.assertFalse(dialog.options()["transparent"])
        self.assertFalse(dialog.transparent.isEnabled())
