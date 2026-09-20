"""Calibration accuracy, image provenance and actual Qt drag/drop/paste routes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog

from config import state
from dataset_reader import SpectrumDataset
from image_digitizer import AxisCalibration, DigitizedCurve, color_trace
from launcher import WORKSPACES, WelcomeDashboard, resource_path
from qt_digitizer import ImageDigitizerDialog
from qt_general_plotter import GeneralPlotter
from qt_3d_plotter import Plot3D
from qt_fluid_plotter import FluidPlotter
from qt_multi_axis_plotter import MultiAxisPlotter
from qt_setup import DatasetSelectionDialog
from qt_shell import InlineImportPage


def curve():
    return DigitizedCurve("Image reference (digitized)", np.array([0., 1., 2.]), np.array([1., 3., 5.]),
                           "X", "Y", {"source_image": "synthetic.png", "approximate": True, "kind": "digitized image"})


class CalibrationTests(unittest.TestCase):
    def test_rotated_reversed_and_log_axes(self):
        calibration = AxisCalibration((10,90), (90,80), (20,10), 1000, 500, .1, 1000, False, True)
        pixels = np.array(calibration.origin) + .3*(np.array(calibration.x_point)-calibration.origin) + .7*(np.array(calibration.y_point)-calibration.origin)
        actual = calibration.convert([pixels])[0]
        np.testing.assert_allclose(actual, [850, 10**1.8])

    def test_degenerate_and_invalid_log_axes_rejected(self):
        for calibration in (AxisCalibration((0,0),(100,0),(50,0),0,1,0,1),
                            AxisCalibration((0,0),(100,0),(0,100),0,10,1,10,True),
                            AxisCalibration((0,0),(100,0),(0,100),1,1,0,1)):
            with self.assertRaises(ValueError):
                calibration.convert([(50,50)])

    def test_color_trace_matches_known_line_and_ignores_smaller_legend(self):
        rgb = np.full((101,101,3), 255, dtype=np.uint8)
        for x in range(15, 86):
            rgb[100-x, x] = [20, 60, 200]
        rgb[25, 20:30] = [20, 60, 200]
        calibration = AxisCalibration((10,90),(90,90),(10,10),0,10,0,10)
        pixels = color_trace(rgb, [20,60,200], calibration, tolerance=5, step=3)
        xy = calibration.convert(pixels)
        self.assertGreater(len(xy), 20)
        np.testing.assert_allclose(xy[:,0], xy[:,1], atol=.13)


class ImageAndDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def drop(self, widget, path):
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter = QDragEnterEvent(QPoint(10,10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(10,10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, drop)
        self.assertTrue(drop.isAccepted())

    def test_digitizer_click_calibration_preserves_source_and_coordinates(self):
        image = QImage(101,101,QImage.Format.Format_RGB32); image.fill(0xffffffff)
        dialog = ImageDigitizerDialog(image=image, source="synthetic.png")
        for x,y in ((10,90),(90,90),(10,10),(30,70),(70,30)):
            dialog.image_click(SimpleNamespace(inaxes=dialog.ax, xdata=x, ydata=y, button=1))
        result = dialog.curve()
        np.testing.assert_allclose(result.x, [.25,.75]); np.testing.assert_allclose(result.y, [.25,.75])
        self.assertTrue(result.metadata["approximate"])
        self.assertEqual(result.metadata["source_image"], "synthetic.png")
        self.assertEqual(len(result.metadata["image_sha256"]), 64)
        dialog.undo(); self.assertEqual(len(dialog.points), 1)

    def test_files_drop_on_2d_table_3d_canvas_fluid_and_multi_axis(self):
        with TemporaryDirectory() as folder:
            table = Path(folder)/"data.csv"
            table.write_text("X,Y,Z\n0,0,1\n0,1,2\n1,0,3\n1,1,4\n", encoding="utf-8")
            field = Path(folder)/"flow.plt"
            field.write_text('VARIABLES="X" "Y" "U"\nZONE I=2,J=2,F=POINT\n0 0 1\n1 0 2\n0 1 3\n1 1 4\n', encoding="utf-8")
            for kind in (GeneralPlotter, Plot3D, FluidPlotter, MultiAxisPlotter):
                with self.subTest(workspace=kind.__name__):
                    plotter = kind(); plotter.show(); self.app.processEvents()
                    target = plotter.table.viewport() if kind is GeneralPlotter else plotter.canvas
                    self.drop(target, field if kind is FluidPlotter else table)
                    if kind is FluidPlotter:
                        self.assertEqual(len(plotter.fields), 1)
                    else:
                        self.assertEqual(len(plotter.loaded_files), 1)

    def test_spectroscopy_import_and_open_plots_accept_drops_for_all_techniques(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/"spectrum.csv"
            x = np.arange(20.); y = x*x+1
            np.savetxt(path, np.column_stack((x,y)), delimiter=",")
            for key in ("ir", "xrd", "uvvis", "raman", "xps", "libs"):
                with self.subTest(workspace=key):
                    workspace = next(w for w in WORKSPACES if w.key == key)
                    page = InlineImportPage(workspace, resource_path); ready=[]; page.analysisReady.connect(ready.append)
                    page.show(); self.app.processEvents(); self.drop(page.file_list.viewport(), path)
                    self.assertEqual(len(ready), 1)
                    dashboard = WelcomeDashboard(); dashboard._open_spectroscopy(ready[0])
                    viewer = dashboard.document_tabs.currentWidget(); viewer.show(); self.app.processEvents()
                    def choose(picker):
                        picker.selected = picker.datasets[:1]; picker.mode="overlay"
                        return QDialog.DialogCode.Accepted
                    with patch.object(DatasetSelectionDialog, "exec", choose):
                        self.drop(viewer.canvas, path)
                    self.assertEqual(len(viewer.stems), 2)

    def test_image_drop_and_clipboard_image_open_digitizer_without_consuming_text_paste(self):
        plotter = GeneralPlotter(); plotter.show(); self.app.processEvents()
        image = QImage(50,50,QImage.Format.Format_RGB32); image.fill(0xffffffff)
        with TemporaryDirectory() as folder:
            path = Path(folder)/"graph.png"; image.save(str(path))
            with patch.object(plotter.import_support, "open_digitizer") as opener:
                self.drop(plotter.canvas, path)
                self.assertEqual(opener.call_count, 1)
                QApplication.clipboard().setImage(image)
                event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
                QApplication.sendEvent(plotter.table, event)
                self.assertEqual(opener.call_count, 2)
                QApplication.clipboard().setText("1\t2\n3\t4")
                event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
                QApplication.sendEvent(plotter.table, event)
                self.assertEqual(opener.call_count, 2)

    def test_digitized_curve_preserves_pending_zip_selection_and_reference(self):
        workspace = next(w for w in WORKSPACES if w.key == "libs")
        page = InlineImportPage(workspace, resource_path)
        ready = []; page.analysisReady.connect(ready.append)
        with TemporaryDirectory() as folder:
            archive = Path(folder) / "samples.zip"
            content = "\n".join(f"{i},{i*i+1}" for i in range(20))
            with zipfile.ZipFile(archive, "w") as bundle:
                for name in ("a_reference", "b_sample", "c_unselected"):
                    bundle.writestr(name + ".csv", content)
            page.add_paths([str(archive)])
            page.reference_combo.setCurrentIndex(1)
            page.dataset_list.item(1).setCheckState(Qt.CheckState.Checked)
            original_names = [dataset.name for dataset in page.datasets]
            page.import_digitized(curve())
            self.assertEqual(len(ready), 0)
            self.assertEqual([dataset.name for dataset in page.datasets], original_names + [curve().name])
            self.assertEqual(page.reference_combo.currentData(), 0)
            self.assertEqual([dataset.name for dataset in page._selected_datasets()], [original_names[1], curve().name])
            page.open_selected()
            self.assertEqual(ready[0]["reference"].name, original_names[0])
            self.assertTrue(ready[0]["digitization"][curve().name]["approximate"])
            page.clear_files()
            self.assertEqual(page.image_datasets, [])
            self.assertEqual(page.image_metadata, {})

    def test_image_comparison_preserves_native_points_and_does_not_extrapolate(self):
        plotter = GeneralPlotter()
        plotter._set_dataframe(pd.DataFrame({"X": [-1.,0.,.5,1.,2.,3.], "Measured": [1.,2.,3.,4.,5.,6.]}))
        with patch("qt_general_plotter.QInputDialog.getItem", return_value=("Compare on the current X grid",True)):
            plotter.import_digitized(curve())
        frame = plotter._dataframe(False)
        values = pd.to_numeric(frame[curve().name],errors="coerce").to_numpy(float)
        np.testing.assert_allclose(values, [np.nan,1,2,3,5,np.nan], equal_nan=True)
        self.assertEqual(plotter.digitized_sources[curve().name]["original_x"], [0,1,2])

    def test_digitized_spectra_have_no_automatic_processing_and_save_provenance(self):
        dashboard = WelcomeDashboard(); workspace = next(w for w in WORKSPACES if w.key == "raman")
        x = np.arange(20.); y = 10 + np.sin(x)
        dashboard._open_spectroscopy({"workspace": workspace, "datasets": [SpectrumDataset("measured",x,y,"test.txt")],
            "reference":None,"mode":"individual","smooth":0,"files":[]})
        viewer=dashboard.document_tabs.currentWidget(); viewer.import_digitized(curve())
        fs=state.file_set[curve().name]
        self.assertFalse(fs["do_baseline"]); self.assertEqual(fs["smooth"],0); self.assertFalse(fs["auto_clean_edges"])
        self.assertTrue(fs["digitization"]["approximate"])
        np.testing.assert_array_equal(viewer.get_processed_data_for_stem(curve().name)[1], curve().y)

    def test_3d_image_import_uses_explicit_reference_plane(self):
        plotter = Plot3D()
        with patch("qt_3d_plotter.QInputDialog.getDouble", return_value=(7.5,True)):
            plotter.import_digitized(curve())
        layer = plotter.layers[-1]
        np.testing.assert_allclose(plotter._numeric(layer["z"]), [7.5]*3)
        self.assertEqual(plotter.digitized_sources[curve().name]["user_supplied_z_plane"], 7.5)
