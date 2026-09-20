"""Regression coverage for release channels and narrow, embedded plot workspaces."""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRASUITE_DISABLE_UPDATE_CHECK", "1")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication, QToolButton

from launcher import WelcomeDashboard, WORKSPACES
from qt_updates import UpdateController, PrivacyPreferencesDialog
from update_logic import is_newer_release, select_release


def release(tag, prerelease=False, draft=False):
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft,
            "html_url": "https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/" + tag}


class ReleaseChannelTests(unittest.TestCase):
    def test_release_candidates_compare_and_stable_supersedes_rc(self):
        self.assertTrue(is_newer_release("v3.3.0-rc.2", "v3.3.0-rc.1"))
        self.assertTrue(is_newer_release("v3.3.0-rc.10", "v3.3.0-rc.2"))
        self.assertTrue(is_newer_release("v3.3.0", "v3.3.0-rc.2"))
        self.assertFalse(is_newer_release("v3.3.0-rc.2", "3.3.0"))
        self.assertFalse(is_newer_release("v3.3.0-rc.2", "v3.3.0-rc.2"))

    def test_selects_highest_eligible_version_not_github_list_order(self):
        payload = [release("v3.1.0"), release("v3.3.0-rc.2", True),
                   release("v3.2.0"), release("v9.0.0", draft=True), release("junk")]
        self.assertEqual(select_release(payload)["tag"], "v3.2.0")
        self.assertEqual(select_release(payload, include_prereleases=True)["tag"], "v3.3.0-rc.2")
        self.assertIsNone(select_release([release("v3.3.0-rc.1", True)]))
        with self.assertRaises(ValueError):
            select_release({"message": "rate limit"})


class RefinementGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
        self.app.processEvents()

    def test_controller_reports_test_release_inside_preferences(self):
        with TemporaryDirectory() as folder:
            presented = []
            controller = UpdateController(update_handler=presented.append)
            controller.settings = QSettings(str(Path(folder)/"settings.ini"), QSettings.Format.IniFormat)
            controller.set_include_test_releases(True)
            dialog = PrivacyPreferencesDialog(controller)
            class Reply:
                def error(self): return QNetworkReply.NetworkError.NoError
                def readAll(self): return json.dumps([release("v3.3.0-rc.1", True)]).encode()
                def deleteLater(self): pass
            controller._reply = Reply()
            controller._request_include_tests = True
            controller._request_identity = controller._check_identity()
            with patch("qt_updates.is_newer_release", side_effect=lambda tag: is_newer_release(tag, "3.2.0")):
                controller._handle_reply()
            self.assertEqual(presented[0]["tag"], "v3.3.0-rc.1")
            self.assertIn("Update available", dialog.update_status.text())
            self.assertEqual(dialog.available_release["tag"], "v3.3.0-rc.1")
            with patch.object(controller, "automatic_runtime_enabled", return_value=True):
                self.assertFalse(controller.should_check_automatically())
                controller.set_include_test_releases(False)
                self.assertTrue(controller.should_check_automatically())
            controller._initial_timer.stop(); controller._periodic_timer.stop()

    def test_manual_check_during_automatic_request_is_not_silenced(self):
        controller = UpdateController()
        class Reply:
            def isRunning(self): return True
        controller._reply = Reply()
        controller.check(silent=False)
        self.assertFalse(controller._silent)
        self.assertIn("Checking", controller.status_text)
        controller._reply = None

    def test_embedded_2d_and_3d_drop_multiple_files_and_restore_panel_width(self):
        dashboard = WelcomeDashboard(); dashboard.resize(1280, 800); dashboard.show()
        with TemporaryDirectory() as folder:
            paths = []
            for i in range(2):
                path = Path(folder)/f"sample{i}.csv"
                path.write_text("X,Y,Z\n0,0,1\n0,1,2\n1,0,3\n1,1,4\n")
                paths.append(path)
            for key in ("general", "plot3d"):
                dashboard.launch_workspace(next(w for w in WORKSPACES if w.key == key))
                plotter = dashboard.document_tabs.currentWidget()
                self.app.processEvents()
                for target, path in zip((plotter.table.viewport(), plotter.canvas), paths):
                    mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
                    enter = QDragEnterEvent(QPoint(10,10), Qt.DropAction.CopyAction, mime,
                                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                    QApplication.sendEvent(target, enter)
                    self.assertTrue(enter.isAccepted())
                    event = QDropEvent(QPointF(10,10), Qt.DropAction.CopyAction, mime,
                                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                    QApplication.sendEvent(target, event)
                    self.assertTrue(event.isAccepted())
                self.assertEqual(len(plotter.loaded_files), 2)
                if key == "plot3d": self.assertEqual(len(plotter.layers), 2)
                plotter.splitter.setSizes([255, 640, 290]); self.app.processEvents()
                before = plotter.splitter.sizes()[0]
                self.assertLessEqual(plotter.data_tools.height(), 34)
                extension = plotter.data_tools.findChild(QToolButton, "qt_toolbar_ext_button")
                if extension.isVisible():
                    self.assertLessEqual(extension.geometry().right(), plotter.data_tools.width() + 1)
                self.assertLessEqual(plotter.data_panel.minimumSizeHint().width(), 270)
                plotter.data_toggle.click(); self.app.processEvents()
                self.assertTrue(plotter.data_panel.isHidden())
                plotter.data_toggle.click(); self.app.processEvents()
                self.assertFalse(plotter.data_panel.isHidden())
                self.assertAlmostEqual(plotter.splitter.sizes()[0], before, delta=12)
                self.assertFalse(plotter.data_toggle.isChecked())
