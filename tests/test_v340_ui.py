"""Regression coverage for the Version 3.4 interface and digitizer guidance."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from types import SimpleNamespace
import unittest

import numpy as np
from matplotlib.figure import Figure
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from image_digitizer import AxisCalibration, color_trace
from launcher import WelcomeDashboard
from qt_digitizer import ImageDigitizerDialog
from qt_export import ExportControls
from qt_theme import LIGHT_STYLE, apply_theme, set_theme, themed_stylesheet
from update_logic import is_newer_release


class Version340Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_theme("blue", persist=False)
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_accent_and_gradient_themes_apply_live(self):
        self.assertIn("#0f766e", themed_stylesheet(LIGHT_STYLE, "teal"))
        self.assertIn("qlineargradient", themed_stylesheet(LIGHT_STYLE, "ocean"))
        widget = QWidget()
        apply_theme(widget)
        set_theme("plum", persist=False)
        self.assertIn("#7e22ce", widget.styleSheet())
        self.assertNotIn("#2563eb", widget.styleSheet())

    def test_home_workspace_cards_are_compact(self):
        dashboard = WelcomeDashboard()
        self.assertTrue(all(button.width() == 235 for button in dashboard._buttons.values()))
        self.assertTrue(all(button.height() == 64 for button in dashboard._buttons.values()))
        dashboard._skip_close_prompt = True

    def test_digitizer_rejects_y_calibration_on_x_axis(self):
        image = QImage(101, 101, QImage.Format.Format_RGB32)
        image.fill(0xffffffff)
        dialog = ImageDigitizerDialog(image=image)
        def click(x, y):
            dialog.image_click(SimpleNamespace(
                inaxes=dialog.ax, xdata=x, ydata=y, button=1,
            ))
        click(10, 90)
        click(90, 90)
        click(60, 89)
        self.assertEqual(len(dialog.calibration_pixels), 2)
        self.assertIn("almost on the X axis", dialog.calibration_error)
        click(10, 10)
        self.assertEqual(len(dialog.calibration_pixels), 3)
        self.assertIn("Step 2", dialog.step_title.text())

    def test_color_trace_follows_component_nearest_click(self):
        rgb = np.full((101, 101, 3), 255, dtype=np.uint8)
        rgb[70, 10:91] = 0
        rgb[40, 25:76] = 0
        calibration = AxisCalibration((10, 90), (90, 90), (10, 10), 0, 1, 0, 1)
        chosen = color_trace(rgb, [0, 0, 0], calibration, tolerance=0, step=2,
                             seed=(50, 40))
        self.assertGreater(len(chosen), 10)
        self.assertAlmostEqual(float(np.median(chosen[:, 1])), 40, delta=0.5)

    def test_export_controls_are_readable_and_explain_margin_trimming(self):
        controls = ExportControls(Figure(figsize=(4, 3)))
        self.assertGreaterEqual(controls.format.minimumWidth(), 180)
        self.assertGreaterEqual(controls.preset.minimumWidth(), 230)
        self.assertEqual(controls.tight.text(), "Trim empty outer margins")
        self.assertIn("saved width and height", controls.tight.toolTip())

    def test_installed_rc2_recognizes_version_340_test_release(self):
        self.assertTrue(is_newer_release("v3.4.0-rc.1", "v3.3.0-rc.2"))


if __name__ == "__main__":
    unittest.main()
