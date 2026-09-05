"""PySide6 entry point for SpectraSuite Version 3."""

from __future__ import annotations

import ctypes
import multiprocessing
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


def resource_path(relative_path: str) -> Path:
    """Return an asset path in development and PyInstaller bundles."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


@dataclass(frozen=True)
class Workspace:
    key: str
    title: str
    icon: str
    experimental: bool = False


WORKSPACES = (
    Workspace("ir", "FT-IR\nSpectroscopy", "📈"),
    Workspace("xrd", "XRD\nAnalysis", "📊"),
    Workspace("general", "General\nPlotter", "📉", experimental=True),
)


APP_STYLE = """
QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QLabel#title { color: #89b4fa; font-size: 26px; font-weight: 700; }
QLabel#subtitle, QLabel#footer { color: #a6adc8; font-size: 14px; }
QPushButton {
    background-color: #313244; border: 2px solid #45475a;
    border-radius: 15px; font-size: 16px; font-weight: 700; padding: 15px;
}
QPushButton:hover { background-color: #45475a; border-color: #89b4fa; }
QPushButton:pressed { background-color: #585b70; }
QPushButton:disabled { color: #7f849c; }
QPushButton[experimental="true"] { border-color: #f9e2af; }
"""


class WelcomeDashboard(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Analytical Spectroscopy Suite")
        self.resize(760, 520)
        self.setMinimumSize(680, 460)
        self.setStyleSheet(APP_STYLE)

        icon_path = resource_path("icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._processes: dict[str, QProcess] = {}
        self._buttons: dict[str, QPushButton] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 32)
        layout.setSpacing(18)

        title = QLabel("Analytical Spectroscopy Suite")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Select a workspace to begin")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(20)
        for index, workspace in enumerate(WORKSPACES):
            button = self._workspace_button(workspace)
            grid.addWidget(button, index // 3, index % 3)
            self._buttons[workspace.key] = button
        layout.addLayout(grid, 1)

        footer = QLabel("Version 3 · PySide6 migration")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

    def _workspace_button(self, workspace: Workspace) -> QPushButton:
        suffix = "\n\nEXPERIMENTAL" if workspace.experimental else ""
        button = QPushButton(f"{workspace.icon}\n\n{workspace.title}{suffix}")
        button.setMinimumHeight(145)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("experimental", workspace.experimental)
        button.clicked.connect(
            lambda _checked=False, item=workspace: self.launch_workspace(item)
        )
        return button

    def launch_workspace(self, workspace: Workspace) -> None:
        process = self._processes.get(workspace.key)
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(
                self, "Already Running",
                f"{workspace.title.replace(chr(10), ' ')} is already open.",
            )
            return

        button = self._buttons[workspace.key]
        original_text = button.text()
        button.setText("⏳\n\nStarting…")
        button.setEnabled(False)

        process = QProcess(self)
        process.setProgram(sys.executable)
        if getattr(sys, "frozen", False):
            # In a PyInstaller build sys.executable is the SpectraSuite app,
            # not a Python interpreter. Relaunch it with an explicit dispatch
            # argument instead of passing a .py path that may not exist.
            process.setArguments(["--workspace", workspace.key])
        else:
            process.setArguments([
                str(Path(__file__).resolve()), "--workspace", workspace.key,
            ])
        process.setWorkingDirectory(str(Path(__file__).resolve().parent))
        process.errorOccurred.connect(
            lambda _error, item=workspace, proc=process: self._show_process_error(item, proc)
        )
        process.finished.connect(
            lambda exit_code, _status, item=workspace, proc=process:
                self._process_finished(item, proc, exit_code)
        )
        self._processes[workspace.key] = process
        process.start()
        QTimer.singleShot(3000, lambda: self._reset_button(button, original_text))

    def _show_process_error(self, workspace: Workspace, process: QProcess) -> None:
        QMessageBox.critical(
            self, "Launch Error",
            f"Could not start {workspace.title.replace(chr(10), ' ')}.\n{process.errorString()}",
        )

    def _process_finished(
        self, workspace: Workspace, process: QProcess, exit_code: int
    ) -> None:
        if self._processes.get(workspace.key) is process:
            self._processes.pop(workspace.key, None)
        if exit_code:
            QMessageBox.critical(
                self,
                "Workspace Error",
                f"{workspace.title.replace(chr(10), ' ')} stopped during startup.\n\n"
                "A crash report was written to your Desktop when possible.",
            )

    @staticmethod
    def _reset_button(button: QPushButton, original_text: str) -> None:
        button.setText(original_text)
        button.setEnabled(True)


def run_workspace(key: str) -> int:
    """Dispatch a workspace in a fresh source or frozen application process."""
    if key == "ir":
        from ir import run
    elif key == "xrd":
        from xrd import run
    elif key == "general":
        from general import run
    else:
        raise ValueError(f"Unknown workspace: {key}")
    run()
    return 0


def main() -> int:
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--workspace":
        return run_workspace(sys.argv[2])
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "analytical.spectroscopy.suite.3"
        )
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("SpectraSuite")
    icon_path = resource_path("icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = WelcomeDashboard()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
