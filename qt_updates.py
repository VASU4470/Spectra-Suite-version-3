"""Non-blocking GitHub release checks for the desktop application."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app_version import (
    APP_NAME,
    APP_VERSION,
    PRIVACY_POLICY_URL,
    RELEASE_API_URL,
    UPDATE_SIGNUP_URL,
)
from update_logic import is_newer_release, release_summary


def _open_https_page(value, parent, title, failure_message):
    """Open one configured HTTPS page and report a missing browser cleanly."""
    url = QUrl(value)
    if not url.isValid() or url.scheme().casefold() != "https":
        QMessageBox.warning(
            parent,
            title,
            "This page is not configured with a valid secure address.",
        )
        return False
    if QDesktopServices.openUrl(url):
        return True
    QMessageBox.information(
        parent,
        title,
        failure_message,
    )
    return False


def open_update_signup(parent=None):
    """Open the optional email-update form without sharing application data."""
    return _open_https_page(
        UPDATE_SIGNUP_URL,
        parent,
        "Email updates",
        "SpectraSuite could not open your web browser. The application remains "
        "fully usable without signing up.",
    )


def open_privacy_policy(parent=None):
    return _open_https_page(
        PRIVACY_POLICY_URL,
        parent,
        "SpectraSuite privacy",
        "SpectraSuite could not open the privacy page in your web browser.",
    )


def open_release_page(value, parent=None):
    return _open_https_page(
        value,
        parent,
        "SpectraSuite update",
        "SpectraSuite could not open the release page in your web browser.",
    )


class UpdateController(QObject):
    """Check GitHub asynchronously and show a result without blocking startup."""

    CHECK_INTERVAL_SECONDS = 24 * 60 * 60
    RETRY_INTERVAL_MILLISECONDS = 15 * 60 * 1000

    def __init__(self, parent=None, *, update_handler=None):
        super().__init__(parent)
        self.parent_window = parent
        self.update_handler = update_handler
        self.settings = QSettings("SpectraSuite", "SpectraSuite")
        self.network = QNetworkAccessManager(self)
        self._reply = None
        self._silent = True
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._check_if_due)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(self.RETRY_INTERVAL_MILLISECONDS)
        self._retry_timer.timeout.connect(self._check_if_due)
        self._periodic_timer = QTimer(self)
        self._periodic_timer.setInterval(self.CHECK_INTERVAL_SECONDS * 1000)
        self._periodic_timer.timeout.connect(self._check_if_due)

    def automatic_enabled(self):
        value = self.settings.value("updates/automatic", True)
        if isinstance(value, str):
            return value.casefold() not in {"0", "false", "no", "off"}
        return bool(value)

    def set_automatic_enabled(self, enabled):
        self.settings.setValue("updates/automatic", bool(enabled))
        if enabled:
            self.schedule_automatic_check()
        else:
            self._initial_timer.stop()
            self._retry_timer.stop()
            self._periodic_timer.stop()

    def automatic_runtime_enabled(self):
        if not self.automatic_enabled():
            return False
        if os.environ.get("SPECTRASUITE_DISABLE_UPDATE_CHECK") == "1":
            return False
        # GUI tests use the off-screen platform and must never depend on a network.
        if os.environ.get("QT_QPA_PLATFORM", "").casefold() == "offscreen":
            return False
        return True

    def should_check_automatically(self):
        if not self.automatic_runtime_enabled():
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
        if not self.automatic_runtime_enabled():
            return
        if not self._periodic_timer.isActive():
            self._periodic_timer.start()
        if self.should_check_automatically() and not self._initial_timer.isActive():
            self._initial_timer.start(1800)

    def _check_if_due(self):
        if self.should_check_automatically():
            self.check(silent=True)

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
            elif self.automatic_runtime_enabled() and not self._retry_timer.isActive():
                self._retry_timer.start()
            return
        self._retry_timer.stop()
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
        self.present_update(release)

    def present_update(self, release):
        """Use an in-window presenter when available, with a dialog fallback."""
        if self.update_handler is not None:
            self.update_handler(dict(release))
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
            open_release_page(release["url"], self.parent_window)


class PrivacyPreferencesDialog(QDialog):
    """One transparent home for network, mailing and privacy preferences."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Privacy and update preferences")
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Privacy and update preferences")
        title.setStyleSheet("font-size:18px;font-weight:800;")
        root.addWidget(title)
        summary = QLabel(
            "SpectraSuite processes scientific data locally and remains fully usable "
            "without an account or internet connection."
        )
        summary.setWordWrap(True)
        root.addWidget(summary)

        updates = QGroupBox("Application updates")
        updates_layout = QVBoxLayout(updates)
        self.automatic_check = QCheckBox(
            "Automatically check GitHub for SpectraSuite updates"
        )
        self.automatic_check.setChecked(controller.automatic_enabled())
        self.automatic_check.toggled.connect(controller.set_automatic_enabled)
        updates_layout.addWidget(self.automatic_check)
        update_note = QLabel(
            "Checks at most once per 24 hours and sends only the normal HTTPS request "
            "information plus the SpectraSuite version. No installation identifier or "
            "scientific data is attached. If the app is temporarily offline, it retries "
            "quietly while it remains open."
        )
        update_note.setWordWrap(True)
        updates_layout.addWidget(update_note)
        check_now = QPushButton("Check for updates now")
        check_now.clicked.connect(lambda: controller.check(silent=False))
        updates_layout.addWidget(check_now)
        root.addWidget(updates)

        email = QGroupBox("Optional email updates")
        email_layout = QVBoxLayout(email)
        email_note = QLabel(
            "Email registration is optional and separate from application access. "
            "The Brevo form opens only when requested and no mailing credentials are "
            "stored inside SpectraSuite."
        )
        email_note.setWordWrap(True)
        email_layout.addWidget(email_note)
        email_button = QPushButton("Get update emails…")
        email_button.clicked.connect(lambda: open_update_signup(self))
        email_layout.addWidget(email_button)
        root.addWidget(email)

        privacy_row = QHBoxLayout()
        privacy = QPushButton("View privacy policy…")
        privacy.clicked.connect(lambda: open_privacy_policy(self))
        privacy_row.addWidget(privacy)
        privacy_row.addStretch()
        root.addLayout(privacy_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


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
