"""Real report pagination, selected exports and non-mutating previews."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from pypdf import PdfReader
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from config import state
from dataset_reader import SpectrumDataset
from launcher import WORKSPACES, WelcomeDashboard
from plot_export import figure_bytes
from qt_export import BatchExportDialog, ExportControls
from qt_general_plotter import GeneralPlotter
from qt_3d_plotter import Plot3D
from report_export import ExportItem, export_batch, save_pdf_report


def sample_item(name="Sample alpha", many_results=False):
    x = np.linspace(300, 320, 101); y = 100 + np.exp(-((x-310)/.5)**2) * 900
    figure = Figure(figsize=(5, 3))
    axis = figure.add_subplot(); axis.plot(x, y); axis.set_xlabel("Wavelength (nm)"); axis.set_ylabel("Intensity (a.u.)")
    figure.tight_layout()
    results = [f"Peak {i}: wavelength 310 nm; height 1000; local area 79.5" for i in range(180 if many_results else 1)]
    return ExportItem(name, lambda: figure, pd.DataFrame({"Wavelength (nm)": x, "Intensity": y}), results,
                      {"smooth": 0, "baseline": {"enabled": False, "lambda": 1000}, "normalization": False}, "Synthetic test source")


class ExportEngineTests(unittest.TestCase):
    def test_pdf_report_paginates_results_and_contains_settings(self):
        item = sample_item(many_results=True)
        original = item.figure().get_size_inches().copy()
        with TemporaryDirectory() as folder:
            path = save_pdf_report([item], Path(folder)/"report.pdf", options={"size_inches": (3.5, 2.5), "tight": False})
            pdf = PdfReader(path)
            self.assertGreater(len(pdf.pages), 4)
            text = "\n".join(page.extract_text() for page in pdf.pages)
            for expected in ("Sample alpha", "Peak 179", "normalization: false", "lambda: 1000", "Results and processing settings"):
                self.assertIn(expected, text)
            self.assertTrue(all(abs(float(page.mediabox.width)-595.28) < 1 for page in pdf.pages))
        np.testing.assert_array_equal(item.figure().get_size_inches(), original)

    def test_only_selected_datasets_are_written_with_unique_portable_names(self):
        items = [sample_item("sample/a"), sample_item("sample:a")]
        items[0].extra_data = {"deconvolution_1": pd.DataFrame({"X": [1., 2.], "Total Fit": [5., 7.]})}
        with TemporaryDirectory() as folder:
            output = export_batch(items, folder, extension="png", options={"dpi": 80, "tight": False})
            manifest = json.loads((output/"manifest.json").read_text())
            self.assertEqual([d["name"] for d in manifest["datasets"]], ["sample/a", "sample:a"])
            self.assertEqual(len(list(output.glob("*_data.csv"))), 2)
            self.assertEqual(len(list(output.glob("*_plot.png"))), 2)
            self.assertEqual(len(PdfReader(output/"report.pdf").pages), 4)
            frame = pd.read_csv(next(output.glob("*_data.csv")))
            np.testing.assert_allclose(frame.iloc[:, 1], items[0].data.iloc[:, 1])
            fit_file = next(name for name in manifest["datasets"][0]["files"] if "deconvolution_1" in name)
            pd.testing.assert_frame_equal(pd.read_csv(output / fit_file), items[0].extra_data["deconvolution_1"])

    def test_batch_failure_and_report_failure_preserve_existing_files(self):
        good = sample_item()
        def fail():
            raise RuntimeError("render failure")
        bad = ExportItem("Bad", fail)
        with TemporaryDirectory() as folder:
            old = Path(folder)/"report.pdf"; old.write_bytes(b"existing")
            with self.assertRaisesRegex(RuntimeError, "render failure"):
                export_batch([good, bad], folder)
            self.assertEqual(list(Path(folder).iterdir()), [old])
            with self.assertRaisesRegex(RuntimeError, "render failure"):
                save_pdf_report([bad], old)
            self.assertEqual(old.read_bytes(), b"existing")

    def test_preview_restores_canvas_and_dimensions_even_after_failure(self):
        figure = sample_item().figure(); canvas = figure.canvas; size = figure.get_size_inches().copy()
        axis = figure.axes[0]
        position = axis.get_position().bounds
        original_position = axis.get_position(original=True).bounds
        in_layout = axis.get_in_layout()
        self.assertTrue(figure_bytes(figure, size_inches=(2, 1.5)).startswith(b"\x89PNG"))
        np.testing.assert_array_equal(figure.get_size_inches(), size); self.assertIs(figure.canvas, canvas)
        np.testing.assert_allclose(axis.get_position().bounds, position)
        np.testing.assert_allclose(axis.get_position(original=True).bounds, original_position)
        self.assertEqual(axis.get_in_layout(), in_layout)
        with patch.object(figure, "savefig", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                figure_bytes(figure, size_inches=(2, 1))
        np.testing.assert_array_equal(figure.get_size_inches(), size); self.assertIs(figure.canvas, canvas)
        np.testing.assert_allclose(axis.get_position().bounds, position)
        np.testing.assert_allclose(axis.get_position(original=True).bounds, original_position)
        self.assertEqual(axis.get_in_layout(), in_layout)


class ExportUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_size_preset_and_persistent_custom_preset(self):
        controls = ExportControls(Figure(figsize=(4, 3)))
        controls.preset.setCurrentIndex(1)
        self.assertAlmostEqual(controls.width.value(), 85)
        self.assertAlmostEqual(controls.height.value(), 63.75)
        controls.width.setValue(90)
        self.assertEqual(controls.preset.currentIndex(), 0)
        with TemporaryDirectory() as folder:
            controls.preferences = QSettings(str(Path(folder)/"export.ini"), QSettings.Format.IniFormat)
            with patch("qt_export.QInputDialog.getText", return_value=("My manuscript", True)):
                controls.save_preset()
            saved = json.loads(controls.preferences.value("presets"))
            self.assertEqual(saved["My manuscript"]["width"], 90)

    def test_batch_selection_and_complete_pdf_page_preview(self):
        dialog = BatchExportDialog([sample_item("One"), sample_item("Two")])
        dialog.check_all(False)
        from PySide6.QtCore import Qt
        dialog.dataset_list.item(1).setCheckState(Qt.CheckState.Checked)
        self.assertEqual([item.name for item in dialog.selected_items()], ["Two"])
        dialog.show(); self.app.processEvents(); dialog.refresh_preview()
        self.assertFalse(dialog.preview.pixmap().isNull())
        with patch("qt_export.QMessageBox.warning") as warning:
            dialog.preview_report()
            warning.assert_not_called()
        self.assertEqual(dialog.pdf.pageCount(), 2)
        dialog.report_page.setCurrentIndex(1)
        self.assertFalse(dialog.preview.pixmap().isNull())

    def test_pdf_preview_allows_replacement_and_cleanup_while_document_exists(self):
        from PySide6.QtCore import QSize
        dialog = BatchExportDialog([sample_item()])
        dialog.show(); self.app.processEvents(); dialog.preview_report()
        folder = Path(dialog._temporary.name)
        path = folder / "report.pdf"
        path.unlink()  # Windows rejects this if Qt still holds a file handle.
        self.assertFalse(dialog.pdf.render(0, QSize(200, 280)).isNull())
        dialog.preview_report()
        self.assertEqual(dialog.pdf.pageCount(), 2)
        dialog.reject()
        self.assertFalse(folder.exists())

    def test_spectra_export_preserves_live_selection_data_and_processing(self):
        dashboard = WelcomeDashboard(); workspace = next(w for w in WORKSPACES if w.key == "libs")
        x = np.linspace(300, 320, 101); y = np.sin(x) + 10
        datasets = [SpectrumDataset(f"s{i}", x, y+i, f"source{i}.txt") for i in range(2)]
        dashboard._open_spectroscopy({"workspace": workspace, "datasets": datasets, "reference": None, "mode": "overlay", "smooth": 0, "files": []})
        viewer = dashboard.document_tabs.currentWidget()
        old = (list(viewer.stems), viewer.current_stem, viewer.figure, len(viewer.cursors))
        state.file_set["s0"]["offset"] = 2
        items = viewer.export_items()
        figure = items[0].figure()
        np.testing.assert_allclose(figure.axes[0].lines[0].get_ydata(), y+2)
        self.assertEqual((list(viewer.stems), viewer.current_stem, viewer.figure, len(viewer.cursors)), old)
        np.testing.assert_array_equal(viewer.data_dict["s0"][1], y)
        with patch("qt_plot_viewer.process_spectrum", side_effect=ValueError("invalid processing")):
            with self.assertRaisesRegex(ValueError, "invalid processing"):
                viewer.export_items()

    def test_2d_and_3d_dataset_export_factories_preserve_current_plot(self):
        two = GeneralPlotter(); two._set_dataframe(pd.DataFrame({"X": [0,1,2,3], "A": [1,2,4,8], "B": [2,4,6,8]}))
        two._select_all_y(); two.plot_data()
        original = two.figure
        items = two.export_items(); self.assertEqual(len(items), 2)
        for item in items:
            self.assertEqual(len(item.figure().axes[0].lines), 1)
        self.assertIs(two.figure, original)
        three = Plot3D()
        three._set_dataframe(pd.DataFrame({"X": [0,0,1,1], "Y": [0,1,0,1], "Z": [1,2,3,4]}))
        three.plot_data(); before = three.figure
        items = three.export_items(); self.assertEqual(len(items), 1)
        self.assertEqual(items[0].figure().axes[0].name, "3d")
        self.assertIs(three.figure, before)

    def test_export_keeps_xrd_summary_and_valley_fit_curves(self):
        dashboard = WelcomeDashboard(); workspace = next(w for w in WORKSPACES if w.key == "xrd")
        x = np.linspace(10, 30, 101); y = np.full_like(x, 10.)
        dashboard._open_spectroscopy({"workspace": workspace, "datasets": [SpectrumDataset("sample", x, y, "sample.csv")],
                                     "reference": None, "mode": "individual", "smooth": 0, "files": []})
        viewer = dashboard.document_tabs.currentWidget()
        state.file_set["sample"]["xrd_peaks"] = [(15., 10., .2, 12.), (25., 10., .3, 28.)]
        state.file_set["sample"]["deconvs"] = [(10., 30., [10., 10.], [2., 20., 1.], 1, True)]
        item = viewer.export_items()[0]
        self.assertIn("Average crystallite size: 20 nm", item.results)
        self.assertIn("Standard deviation: 8 nm", item.results)
        fit = item.extra_data["deconvolution_1"]
        expected = 10 - 2 * np.exp(-((fit["X"].to_numpy() - 20)**2) / 2)
        np.testing.assert_allclose(fit["Total Fit"], expected)
        np.testing.assert_allclose(fit["Peak 1"], expected)
