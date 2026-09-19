"""LIBS archive, column-selection and plot-session regression checks."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import numpy as np
from PySide6.QtWidgets import QApplication, QDialog

from config import state
from dataset_reader import discover_many, discover_spectra
from launcher import WORKSPACES, WelcomeDashboard, resource_path
from qt_setup import DatasetSelectionDialog
from qt_shell import InlineImportPage


def spectrum_text(offset=0):
    return "\n".join(f"{300 + i * .1:.1f},1,{i * i + offset}" for i in range(12))


class LIBSReaderTests(unittest.TestCase):
    def test_headerless_instrument_format_uses_third_column_only_in_libs(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "sample.Av3.0.txt"
            path.write_text(spectrum_text(), encoding="utf-8")
            datasets, errors = discover_many([path], technique="LIBS")
            generic = discover_spectra(path)
        self.assertFalse(errors)
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0].name, "sample.Av3.0")
        np.testing.assert_array_equal(datasets[0].y, np.arange(12)**2)
        self.assertEqual(len(generic), 2)
        np.testing.assert_array_equal(generic[0].y, np.ones(12))

    def test_named_shared_y_columns_are_not_reinterpreted_as_instrument_format(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "shared.csv"
            path.write_text("Wavelength,Control,Sample\n" + spectrum_text(), encoding="utf-8")
            datasets, errors = discover_many([path], technique="LIBS")
        self.assertFalse(errors)
        self.assertEqual(len(datasets), 2)
        np.testing.assert_array_equal(datasets[0].y, np.ones(12))

    def test_archive_provenance_unique_names_and_partial_failure_without_extraction(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "spectra.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("first/sample.txt", spectrum_text())
                archive.writestr("second/sample.txt", spectrum_text(100))
                archive.writestr("bad.txt", "No spectrum here")
                for name in ("../outside.txt", "/absolute.txt", "__MACOSX/._sample.txt", ".hidden.txt"):
                    archive.writestr(name, spectrum_text())
                link = ZipInfo("link.txt")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, "first/sample.txt")
            datasets, errors = discover_many([path], technique="LIBS")
            self.assertEqual(list(Path(folder).iterdir()), [path])
        self.assertEqual([d.name for d in datasets], ["sample", "sample (2)"])
        self.assertTrue(datasets[0].source.endswith("::first/sample.txt"))
        np.testing.assert_array_equal(datasets[1].y, np.arange(12)**2 + 100)
        self.assertEqual(len(errors), 1)
        self.assertIn("bad.txt", errors[0][0])

    def test_archive_limits_report_failures(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "spectra.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("sample.txt", spectrum_text())
            for limit in ("MAX_MEMBERS", "MAX_MEMBER_BYTES", "MAX_ARCHIVE_BYTES"):
                with self.subTest(limit=limit), patch(f"libs_reader.{limit}", 0):
                    datasets, errors = discover_many([path], technique="LIBS")
                    self.assertFalse(datasets)
                    self.assertEqual(len(errors), 1)
                    self.assertIn("limit", errors[0][1])


class LIBSImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.workspace = next(item for item in WORKSPACES if item.key == "libs")

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_zip_review_filter_preview_selection_and_clear(self):
        page = InlineImportPage(self.workspace, resource_path)
        payloads = []
        page.analysisReady.connect(payloads.append)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "spectra.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("first/sample.txt", spectrum_text())
                archive.writestr("second/sample.txt", spectrum_text(10))
            page.add_paths([str(path)])
        self.assertFalse(payloads)
        self.assertFalse(page.open_button.isEnabled())
        self.assertEqual(page.smoothing.value(), 0)
        page.dataset_search.setText("second/")
        self.assertTrue(page.dataset_list.item(0).isHidden())
        np.testing.assert_array_equal(page.preview_figure.axes[0].lines[0].get_ydata(), np.arange(12)**2 + 10)
        page._check_visible_datasets(True)
        page.dataset_search.setText("first/")
        self.assertEqual(len(page._selected_datasets()), 1)  # Filtering retains selections.
        page.open_ready()
        self.assertEqual(payloads[0]["mode"], "individual")
        self.assertTrue(payloads[0]["datasets"][0].source.endswith("::second/sample.txt"))
        page._check_visible_datasets(False)
        self.assertFalse(page.open_button.isEnabled())
        page.clear_files()
        self.assertFalse(page.preview_figure.axes)

    def test_single_spectrum_zip_requires_explicit_selection(self):
        page = InlineImportPage(self.workspace, resource_path)
        payloads = []
        page.analysisReady.connect(payloads.append)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "one.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("one.txt", spectrum_text())
            page.add_paths([str(path)])
        self.assertFalse(payloads)
        self.assertFalse(page.open_button.isEnabled())
        page._check_visible_datasets(True)
        page.open_ready()
        self.assertEqual(len(payloads), 1)

    def test_add_dialog_uses_checked_spectra_instead_of_preview_highlight(self):
        state.technique = "LIBS"
        with TemporaryDirectory() as folder:
            paths = [Path(folder) / f"sample{i}.txt" for i in range(2)]
            for path in paths:
                path.write_text(spectrum_text(), encoding="utf-8")
            datasets, _ = discover_many(paths, technique="LIBS")
        picker = DatasetSelectionDialog(datasets)
        picker.search.setText("sample1")
        picker._check_visible(True)
        picker.search.setText("sample0")
        picker._choose(False)
        self.assertEqual(picker.selected, [datasets[1]])
        self.assertEqual(picker.mode, "individual")

    def test_zip_plot_layouts_add_replace_and_session_provenance(self):
        dashboard = WelcomeDashboard()
        with patch("qt_shell.QTimer.singleShot"):
            dashboard.launch_workspace(self.workspace)
        page = dashboard.document_tabs.currentWidget()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "spectra.zip"
            with ZipFile(path, "w") as archive:
                for index in range(2):
                    archive.writestr(f"sample{index}.txt", spectrum_text(index * 10))
            page.add_paths([str(path)])
            page._check_visible_datasets(True)
            page.open_ready()
            viewer = dashboard.document_tabs.currentWidget()
            self.assertEqual(len(viewer.stems), 2)
            for mode, axes in (("overlay", 1), ("stack", 2), ("grid", 2)):
                viewer.plot_layout_combo.setCurrentIndex(viewer.plot_layout_combo.findData(mode))
                self.assertEqual(len(viewer.figure.axes), axes)
            for index, stem in enumerate(viewer.stems):
                np.testing.assert_array_equal(viewer.get_processed_data_for_stem(stem)[1], np.arange(12)**2 + index*10)
            extra = Path(folder) / "sample.Av3.0.txt"
            extra.write_text(spectrum_text(200), encoding="utf-8")
            def choose(dialog):
                dialog.selected = dialog.datasets[:1]
                dialog.mode = "overlay"
                return QDialog.DialogCode.Accepted
            with patch("qt_plot_viewer.QFileDialog.getOpenFileNames", return_value=([str(extra)], "")), \
                 patch.object(DatasetSelectionDialog, "exec", choose):
                viewer.add_files()
            self.assertIn("sample.Av3.0", viewer.stems)
            np.testing.assert_array_equal(viewer.data_dict["sample.Av3.0"][1], np.arange(12)**2 + 200)
            np.testing.assert_array_equal(viewer._read_data_file(extra)[1], np.arange(12)**2 + 200)
            with self.assertRaisesRegex(ValueError, "Add files"):
                viewer._read_data_file(path)
            expected_sources = {stem: state.file_set[stem]["source"] for stem in viewer.stems}
            session = str(Path(folder) / "libs.json")
            with patch("qt_plot_viewer.QFileDialog.getSaveFileName", return_value=(session, "")), \
                 patch("qt_plot_viewer.QMessageBox.information"):
                self.assertTrue(viewer.save_session(save_as=True))
            with patch("qt_shell.QFileDialog.getOpenFileName", return_value=(session, "")):
                dashboard.open_session()
            self.assertEqual(state.technique, "LIBS")
            self.assertEqual({stem: state.file_set[stem]["source"] for stem in expected_sources}, expected_sources)
            np.testing.assert_array_equal(state.all_data[0][2], np.arange(12)**2)
