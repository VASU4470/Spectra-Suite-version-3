"""Platform installer download, verification, backup, and handoff UI."""

from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QObject, QProcess, QSaveFile, QStandardPaths, QThread, QTimer, QUrl, Qt, Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)
from app_version import APP_NAME, APP_VERSION, RELEASE_TAG
from update_logic import checksum_from_manifest, select_update_assets, sha256_file

SUPPORT_EMAIL = "vasanthakumar.punitharaj@icat.unam.mx"


class _BackupWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, source, destination):
        super().__init__()
        self.source = Path(source)
        self.destination = Path(destination)

    def run(self):
        try:
            shutil.copytree(self.source, self.destination, symlinks=True, copy_function=shutil.copy2)
            self.completed.emit(str(self.destination))
        except (OSError, shutil.Error) as exception:
            shutil.rmtree(self.destination, ignore_errors=True)
            self.failed.emit(str(exception))


def _latest_backup_directory():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    root = Path(base or (Path.home() / ".spectrasuite")) / "updates" / "previous-versions"
    if not root.is_dir():
        return None
    candidates = [path for path in root.iterdir() if (path / "RECOVERY.txt").is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _preserve_platform_download_warning(path):
    """Keep the OS's ordinary internet-download warning attached to installers."""
    path = Path(path)
    if sys.platform == "win32":
        try:
            stream = Path(f"{path}:Zone.Identifier")
            stream.write_text("[ZoneTransfer]\r\nZoneId=3\r\n", encoding="ascii")
            return "ZoneId=3" in stream.read_text(encoding="ascii")
        except OSError:
            return False
    if sys.platform == "darwin":
        try:
            return bool(os.getxattr(path, "com.apple.quarantine"))
        except (AttributeError, OSError):
            return False
    return True


class UpdateDownloadDialog(QDialog):
    """Download a platform installer, verify its published SHA-256, and hand off."""

    def __init__(self, network, release, parent=None, *, open_page):
        super().__init__(parent)
        self.open_page = open_page
        self.network = network
        self.release = dict(release)
        self.setWindowTitle("Update SpectraSuite")
        self.setMinimumWidth(560)
        self._reply = None
        self._stage = "idle"
        self._save_file = None
        self._started_at = 0.0
        self._installer_asset = None
        self._checksum_asset = None
        self._expected_checksum = ""
        self._download_path = None
        self._backup_path = None
        self._backup_thread = None
        self._backup_worker = None
        self._assets = select_update_assets(self.release)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel(f"Download {self.release.get('tag', 'SpectraSuite')} update")
        title.setStyleSheet("font-size:18px;font-weight:800;")
        root.addWidget(title)
        self.status = QLabel(
            "The official installer will be downloaded and checked before it is opened."
        )
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.progress_note = QLabel("")
        self.progress_note.setWordWrap(True)
        root.addWidget(self.progress_note)

        self.security_note = QLabel(self._security_instructions())
        self.security_note.setWordWrap(True)
        self.security_note.setVisible(False)
        root.addWidget(self.security_note)
        self.support = QLabel(f'Support: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>')
        self.support.setTextFormat(Qt.TextFormat.RichText)
        self.support.setOpenExternalLinks(True)
        self.support.setVisible(False)
        root.addWidget(self.support)

        self.recovery_button = QPushButton("Show previous version backup")
        self.recovery_button.setVisible(False)
        self.recovery_button.clicked.connect(self._show_backup)
        root.addWidget(self.recovery_button)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.primary = QPushButton("Download update")
        self.primary.clicked.connect(self._primary_clicked)
        buttons.addWidget(self.primary)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

        if self._assets is None:
            self.status.setText(
                "An automatic installer is not available for this device or release. "
                "Open the official release page to choose a package manually."
            )
            self.progress.hide()
            self.progress_note.hide()
            self.primary.setText("Open release page")
            self._stage = "unsupported"

    def _security_instructions(self):
        if sys.platform == "darwin":
            return (
                "The macOS Installer will guide you through the update and reopen "
                "SpectraSuite afterward. If macOS blocks the unsigned package or app, "
                "open System Settings → Privacy & Security → Open Anyway, then confirm "
                "Open. Your previous app is kept in the backup folder shown after verification."
            )
        if sys.platform == "win32":
            return (
                "Windows may show a SmartScreen warning for this unsigned installer. "
                "Check that the file is the SpectraSuite installer you just verified; "
                "choose More info → Run anyway only if Windows offers that option. "
                "Approve the normal administrator prompt if one appears. If Smart App "
                "Control gives a hard block without Run anyway, keep using the previous "
                "version backup and contact support; do not turn off system protection."
            )
        return (
            "The Linux package will be opened with your desktop package installer. "
            "Review its normal confirmation prompts before continuing."
        )

    def _primary_clicked(self):
        if self._stage == "unsupported":
            self.open_page(self.release.get("url", ""), self)
            self.accept()
            return
        if self._stage == "idle":
            self._start_manifest_download()
        elif self._stage == "ready":
            self._open_verified_installer()
        elif self._stage == "mac-browser":
            self.open_page(self.release.get("url", ""), self)
        elif self._stage == "failed":
            self._start_manifest_download()

    def _request(self, asset):
        request = QNetworkRequest(QUrl(asset["url"]))
        request.setRawHeader(b"Accept", b"application/octet-stream")
        request.setRawHeader(b"User-Agent", f"{APP_NAME}/{APP_VERSION}".encode("ascii"))
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(60_000)
        return self.network.get(request)

    def _start_manifest_download(self):
        if not self._assets:
            return
        self._installer_asset, self._checksum_asset = self._assets
        self._stage = "manifest"
        self.primary.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress_note.setText("Preparing integrity check…")
        self.status.setText("Fetching the checksum published with this release…")
        self._reply = self._request(self._checksum_asset)
        self._reply.finished.connect(self._manifest_finished)

    def _manifest_finished(self):
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        error = reply.error()
        data = bytes(reply.readAll())
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            self._failed("Could not download the release checksum file. Check your connection and retry.")
            return
        try:
            text = data.decode("utf-8")
            self._expected_checksum = checksum_from_manifest(text, self._installer_asset["name"])
        except (UnicodeDecodeError, ValueError) as exception:
            self._failed(f"Could not validate the release checksum file: {exception}")
            return
        self._start_installer_download()

    def _start_installer_download(self):
        self._stage = "download"
        self._started_at = time.monotonic()
        safe_tag = "".join(
            char for char in self.release.get("tag", "update")
            if char.isalnum() or char in ".-_ "
        )
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        if not base:
            base = str(Path.home() / ".spectrasuite")
        folder = Path(base) / "updates" / safe_tag
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._download_path = folder / self._installer_asset["name"]
            self._save_file = QSaveFile(str(self._download_path))
            if not self._save_file.open(QSaveFile.OpenModeFlag.WriteOnly):
                raise OSError(self._save_file.errorString())
        except OSError as exception:
            self._failed(f"Could not prepare the update download: {exception}")
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_note.setText("0 bytes downloaded")
        self.status.setText(f"Downloading {self._installer_asset['name']}…")
        self._reply = self._request(self._installer_asset)
        self._reply.readyRead.connect(self._write_download_chunk)
        self._reply.downloadProgress.connect(self._download_progress)
        self._reply.finished.connect(self._installer_finished)

    def _write_download_chunk(self):
        if self._reply is None or self._save_file is None:
            return
        data = bytes(self._reply.readAll())
        if data and self._save_file.write(data) != len(data):
            self._reply.abort()
            self._failed(f"Could not save the update file: {self._save_file.errorString()}")

    def _download_progress(self, received, total):
        size = total if total > 0 else int(self._installer_asset.get("size") or 0)
        if size > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, int(received * 100 / size))))
        else:
            self.progress.setRange(0, 0)
        elapsed = max(0.1, time.monotonic() - self._started_at)
        rate = received / elapsed
        remaining = max(0, size - received) / rate if size and rate else 0
        text = f"{self._format_bytes(received)} downloaded"
        if size:
            text += f" / {self._format_bytes(size)} · {int(received * 100 / size)}%"
            text += f" · about {self._format_duration(remaining)} remaining"
        self.progress_note.setText(text)

    def _installer_finished(self):
        self._write_download_chunk()
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        error = reply.error()
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            self._failed("The installer download did not finish. Your existing app is unchanged.")
            return
        try:
            if not self._save_file.commit():
                raise OSError(self._save_file.errorString())
            actual = sha256_file(self._download_path)
            if actual != self._expected_checksum:
                self._download_path.unlink(missing_ok=True)
                raise ValueError("SHA-256 did not match the checksum published with this release.")
            self._security_marker_ok = _preserve_platform_download_warning(self._download_path)
            if sys.platform == "win32" and not self._security_marker_ok:
                raise ValueError(
                    "SpectraSuite could not confirm the normal operating-system internet "
                    "download security marker. The installer was not opened."
                )
        except (OSError, ValueError) as exception:
            self._failed(f"The downloaded update failed verification: {exception}")
            return
        self._stage = "ready"
        self.progress.setValue(100)
        self.progress_note.setText(
            f"SHA-256 verified · {self._expected_checksum[:16]}… · "
            f"{self._format_bytes(self._download_path.stat().st_size)}"
        )
        self.status.setText("The official installer is verified and ready.")
        self.security_note.setVisible(True)
        self.support.setVisible(True)
        self.primary.setText(
            "Open verified installer"
            if sys.platform != "darwin" or self._security_marker_ok
            else "Open official download in browser…"
        )
        self.primary.setEnabled(True)
        self.cancel_button.setText("Close")

    def _open_verified_installer(self):
        if not self._download_path or not self._download_path.is_file():
            self._failed("The verified installer is no longer available. Download it again.")
            return
        source = self._installed_bundle_path()
        if source is not None:
            base = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
            root = Path(base or (Path.home() / ".spectrasuite")) / "updates" / "previous-versions"
            safe_tag = "".join(
                char for char in RELEASE_TAG if char.isalnum() or char in ".-_ "
            )
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self._backup_path = root / f"{safe_tag}-{stamp}" / source.name
            try:
                self._backup_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exception:
                self._failed(f"Could not prepare a previous-version backup: {exception}")
                return
            self._stage = "backup"
            self.status.setText("Preserving the version you are currently using…")
            self.progress.setRange(0, 0)
            self.progress_note.setText("This may take a few moments. Your current app is still available.")
            self.primary.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self._backup_thread = QThread(self)
            self._backup_worker = _BackupWorker(source, self._backup_path)
            self._backup_worker.moveToThread(self._backup_thread)
            self._backup_thread.started.connect(self._backup_worker.run)
            self._backup_worker.completed.connect(self._backup_completed)
            self._backup_worker.failed.connect(self._backup_failed)
            self._backup_worker.completed.connect(self._backup_thread.quit)
            self._backup_worker.failed.connect(self._backup_thread.quit)
            self._backup_thread.finished.connect(self._backup_worker.deleteLater)
            self._backup_thread.start()
            return
        self._launch_verified_installer()

    @staticmethod
    def _installed_bundle_path():
        """Locate the installed PyInstaller bundle; source runs have no bundle to back up."""
        if not getattr(sys, "frozen", False):
            return None
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            candidate = executable.parents[2] if len(executable.parents) > 2 else None
        elif sys.platform == "win32":
            candidate = executable.parent
        else:
            return None
        return candidate if candidate and candidate.exists() else None

    def _backup_completed(self, path):
        self._backup_path = Path(path)
        self._stage = "ready"
        self.primary.setEnabled(True)
        self.cancel_button.setEnabled(True)
        guide = self._backup_path.parent / "RECOVERY.txt"
        security_steps = (
            "If Windows blocks the new installer, confirm it is the verified "
            "SpectraSuite setup file, choose More info → Run anyway only when "
            "offered, and approve the normal administrator prompt if required. "
            "If Smart App Control gives a hard block without Run anyway, use the "
            "previous-version backup; do not turn off system protection.\n\n"
            if sys.platform == "win32" else
            "If macOS blocks the updated app, open System Settings → Privacy & "
            "Security → Open Anyway, then confirm Open.\n\n"
            if sys.platform == "darwin" else ""
        )
        try:
            guide.write_text(
                "Previous SpectraSuite version backup\n\n"
                f"Build: {RELEASE_TAG}\n"
                f"Backup location: {self._backup_path}\n\n"
                "If the update does not open, open this folder and launch the previous "
                "SpectraSuite application from the backup. Your preferences and scientific "
                f"files remain in their usual locations.\n\n{security_steps}"
                f"Support: {SUPPORT_EMAIL}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        self.recovery_button.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress_note.setText(f"Previous version backup: {self._backup_path.parent}")
        self._launch_verified_installer()

    def _backup_failed(self, message):
        self._backup_path = None
        self._failed(
            "SpectraSuite could not preserve the current installation, so the update "
            f"was not opened. Details: {message}"
        )

    def _show_backup(self):
        if self._backup_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._backup_path.parent)))

    def closeEvent(self, event):
        if self._stage == "backup":
            event.ignore()
            return
        if self._reply is not None:
            self._cancel()
        super().closeEvent(event)

    def _launch_verified_installer(self):
        if not self._download_path or not self._download_path.is_file():
            self._failed("The verified installer is no longer available. Download it again.")
            return
        if self._backup_path:
            self._show_backup()
        if sys.platform == "darwin" and not getattr(self, "_security_marker_ok", False):
            self._stage = "mac-browser"
            self.status.setText(
                "The download checksum is verified. To keep macOS's normal Gatekeeper "
                "check, get the installer package in your browser from the official release page. "
                "The previous app backup is available in Finder."
            )
            self.primary.setText("Open official release page…")
            self.primary.setEnabled(True)
            self.cancel_button.setText("Close")
            return
        if sys.platform == "darwin":
            installed_app = self._installed_bundle_path()
            if installed_app is None or installed_app.resolve() != Path("/Applications/SpectraSuite.app").resolve():
                self._stage = "mac-browser"
                self.status.setText(
                    "The update package installs into /Applications. Your current app is "
                    "in a different location, so open the official release page and use "
                    "the DMG to replace it in its current location."
                )
                self.primary.setText("Open official release page…")
                self.primary.setEnabled(True)
                self.cancel_button.setText("Close")
                return
        local_url = QUrl.fromLocalFile(str(self._download_path))
        if sys.platform == "win32":
            started, _process_id = QProcess.startDetached(str(self._download_path), [])
        else:
            started = QDesktopServices.openUrl(local_url)
        if not started:
            self.status.setText(
                "The installer could not be opened. Open the verified file manually."
            )
            self.progress_note.setText(str(self._download_path))
            self.support.setVisible(True)
            return
        if sys.platform == "win32":
            self.status.setText("The verified installer is open. Complete its steps to update SpectraSuite.")
            self.accept()
            QTimer.singleShot(500, QApplication.quit)
        elif sys.platform == "darwin":
            self.status.setText(
                "The macOS Installer is open. Follow its steps; SpectraSuite will reopen "
                "when installation finishes. A copy of the previous app is kept in your "
                "SpectraSuite application-data folder."
            )
            self.accept()
            QTimer.singleShot(500, QApplication.quit)
        else:
            self.status.setText("The verified package is open in your system installer.")
            self.accept()

    def _cancel(self):
        if self._reply is not None:
            reply = self._reply
            self._reply = None
            reply.abort()
            reply.deleteLater()
        self._stage = "cancelled"
        if self._save_file is not None:
            self._save_file.cancelWriting()
            self._save_file = None
        self.reject()

    def _failed(self, message):
        if self._save_file is not None:
            self._save_file.cancelWriting()
            self._save_file = None
        self._stage = "failed"
        self.status.setText(message)
        self.progress_note.setText("The current SpectraSuite installation has not been changed.")
        self.primary.setText("Retry download")
        self.primary.setEnabled(True)
        self.cancel_button.setText("Close")
        self.cancel_button.setEnabled(True)
        self.support.setVisible(True)

    @staticmethod
    def _format_bytes(value):
        amount = float(value)
        for unit in ("bytes", "KB", "MB", "GB"):
            if amount < 1024 or unit == "GB":
                return f"{amount:.1f} {unit}" if unit != "bytes" else f"{int(amount)} bytes"
            amount /= 1024

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds} sec"
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes} min {seconds} sec" if minutes < 60 else f"{minutes} min"
