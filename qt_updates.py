"""Non-blocking GitHub release checks for the desktop application."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox

from app_version import APP_NAME, APP_VERSION, RELEASE_API_URL
from update_logic import is_newer_release, release_summary


class UpdateController(QObject):
    """Check GitHub asynchronously and show a result without blocking startup."""

    CHECK_INTERVAL_SECONDS = 24 * 60 * 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.settings = QSettings("SpectraSuite", "SpectraSuite")
        self.network = QNetworkAccessManager(self)
        self._reply = None
        self._silent = True

    def automatic_enabled(self):
        value = self.settings.value("updates/automatic", True)
        if isinstance(value, str):
            return value.casefold() not in {"0", "false", "no", "off"}
        return bool(value)

    def set_automatic_enabled(self, enabled):
        self.settings.setValue("updates/automatic", bool(enabled))

    def should_check_automatically(self):
        if not self.automatic_enabled():
            return False
        if os.environ.get("SPECTRASUITE_DISABLE_UPDATE_CHECK") == "1":
            return False
        # GUI tests use the off-screen platform and must never depend on a network.
        if os.environ.get("QT_QPA_PLATFORM", "").casefold() == "offscreen":
            return False
        last_value = str(self.settings.value("updates/last_success_utc", ""))
        try:
            last = datetime.fromisoformat(last_value)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - last).total_seconds() >= self.CHECK_INTERVAL_SECONDS

    def schedule_automatic_check(self):
        if self.should_check_automatically():
            QTimer.singleShot(1800, lambda: self.check(silent=True))

    def check(self, *, silent=False):
        if self._reply is not None and self._reply.isRunning():
            return
        self._silent = bool(silent)
        request = QNetworkRequest(QUrl(RELEASE_API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"{APP_NAME}/{APP_VERSION}".encode("ascii"))
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(6000)
        self._reply = self.network.get(request)
        self._reply.finished.connect(self._handle_reply)

    def _handle_reply(self):
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        error = reply.error()
        data = bytes(reply.readAll())
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            if not self._silent:
                QMessageBox.information(
                    self.parent_window,
                    "Update check",
                    "SpectraSuite could not reach GitHub. The application remains fully usable offline.",
                )
            return
        try:
            release = release_summary(json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exception:
            if not self._silent:
                QMessageBox.warning(self.parent_window, "Update check", str(exception))
            return
        self.settings.setValue("updates/last_success_utc", datetime.now(timezone.utc).isoformat())
        if not is_newer_release(release["tag"]):
            if not self._silent:
                QMessageBox.information(
                    self.parent_window,
                    "No update available",
                    f"You are using {APP_NAME} {APP_VERSION}, the latest published version.",
                )
            return
        box = QMessageBox(self.parent_window)
        box.setWindowTitle("SpectraSuite update available")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"{release['name']} is available. You are using Version {APP_VERSION}.")
        notes = release["notes"].strip()
        if len(notes) > 1200:
            notes = notes[:1200].rstrip() + "…"
        box.setInformativeText(notes)
        open_button = box.addButton("Open download page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == open_button:
            QDesktopServices.openUrl(QUrl(release["url"]))


def show_about(parent=None):
    QMessageBox.about(
        parent,
        f"About {APP_NAME}",
        f"<b>{APP_NAME} Version {APP_VERSION}</b><br><br>"
        "Scientific plotting and analysis for FT-IR, XRD, UV-Vis, Raman, and general data."
        "<br><br>The application works offline. If automatic update checks are enabled, it "
        "contacts only the public GitHub Releases API; no installation identifier or "
        "scientific data is sent.",
    )
