"""PySide6 entry point for SpectraSuite Version 3."""

from __future__ import annotations

import ctypes
import multiprocessing
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QProcess, QSize, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from qt_theme import LIGHT_STYLE, apply_window_icon


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
    Workspace("ir", "FT-IR\nSpectroscopy", "ir_icon.png"),
    Workspace("xrd", "XRD\nAnalysis", "xrd_icon.png"),
    Workspace("uvvis", "UV-Vis\nAnalysis", "uvvis_icon.svg"),
    Workspace("raman", "Raman\nAnalysis", "raman_icon.svg"),
    Workspace("general", "General\nPlotter", "plot_icon.svg", experimental=True),
)


def workspace_command(key: str) -> tuple[str, list[str]]:
    """Return the correct child-process command for source and frozen runs."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--workspace", key]
    return sys.executable, [str(Path(__file__).resolve()), "--workspace", key]


APP_STYLE = LIGHT_STYLE + """
QLabel#title { color: #1d4ed8; font-size: 26px; font-weight: 700; }
QLabel#subtitle, QLabel#footer { color: #526175; font-size: 14px; }
QPushButton {
    background-color: #ffffff; border: 2px solid #c5cfdd;
    border-radius: 15px; font-size: 16px; font-weight: 700; padding: 15px;
}
QPushButton:hover { background-color: #eff6ff; border-color: #2563eb; }
QPushButton:pressed { background-color: #dbeafe; }
QPushButton:disabled { color: #8290a3; }
QPushButton[experimental="true"] { border-color: #d97706; }
"""


class WelcomeDashboard(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Analytical Spectroscopy Suite")
        self.resize(760, 520)
        self.setMinimumSize(680, 460)
        self.setStyleSheet(APP_STYLE)

        apply_window_icon(self)

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
        button = QPushButton(f"{workspace.title}{suffix}")
        icon_path = resource_path(workspace.icon)
        if icon_path.exists():
            button.setIcon(QIcon(str(icon_path)))
            button.setIconSize(QSize(52, 52))
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
        program, arguments = workspace_command(workspace.key)
        process.setProgram(program)
        process.setArguments(arguments)
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
    elif key == "uvvis":
        from uvvis import run
    elif key == "raman":
        from raman import run
    else:
        raise ValueError(f"Unknown workspace: {key}")
    run()
    return 0


def startup_smoke_test() -> int:
    """Exercise imports and the dashboard without entering the Qt event loop."""
    from general import main as _general_main
    from qt_general_plotter import GeneralPlotter as _GeneralPlotter
    from ir import main as _ir_main
    from qt_plot_viewer import PlotViewer as _PlotViewer
    from qt_setup import SetupDialog as _SetupDialog
    from xrd import main as _xrd_main
    from uvvis import main as _uvvis_main
    from raman import main as _raman_main

    # Keep references alive through the check and make import failures fatal.
    required = (
        _general_main, _GeneralPlotter, _ir_main, _PlotViewer, _SetupDialog, _xrd_main,
        _uvvis_main, _raman_main,
    )
    if not all(required):
        raise RuntimeError("A required workspace entry point is unavailable")

    app = QApplication.instance() or QApplication([])
    window = WelcomeDashboard()
    window.show()
    app.processEvents()
    if set(window._buttons) != {"ir", "xrd", "uvvis", "raman", "general"}:
        raise RuntimeError("The dashboard did not create every workspace button")
    window.close()
    app.processEvents()
    print("SpectraSuite startup smoke test passed")
    return 0


def main() -> int:
    multiprocessing.freeze_support()
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke-test":
        return startup_smoke_test()
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
