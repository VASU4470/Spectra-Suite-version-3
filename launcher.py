"""PySide6 entry point for SpectraSuite Version 3."""

from __future__ import annotations

import ctypes
import multiprocessing
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qt_shell import SpectraSuiteWindow


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
    coming_soon: bool = False


WORKSPACES = (
    Workspace("ir", "FT-IR\nSpectroscopy", "ir_icon.svg"),
    Workspace("xrd", "XRD\nAnalysis", "xrd_icon.svg"),
    Workspace("uvvis", "UV-Vis\nAnalysis", "uvvis_icon.svg"),
    Workspace("raman", "Raman\nAnalysis", "raman_icon.svg"),
    Workspace("general", "General\n2D Plotter", "plot_icon.svg"),
    Workspace("plot3d", "General\n3D Plotter", "plot3d_icon.svg"),
    Workspace("multiaxis", "Multi-X / Multi-Y\nPlotter", "multiaxis_icon.svg", coming_soon=True),
    Workspace("fluid", "Fluid Dynamics\nPlotter", "fluid_icon.svg", coming_soon=True),
    Workspace("xps", "XPS\nAnalysis", "xps_icon.svg", coming_soon=True),
)


def workspace_command(key: str) -> tuple[str, list[str]]:
    """Return the correct child-process command for source and frozen runs."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--workspace", key]
    return sys.executable, [str(Path(__file__).resolve()), "--workspace", key]


def set_windows_app_id(workspace="launcher") -> None:
    """Give each child workspace its own Windows taskbar identity."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"analytical.spectroscopy.suite.3.{workspace}"
        )
    except (AttributeError, OSError):
        pass


# ``WelcomeDashboard`` remains the public entry-point name used by existing
# installations, while its implementation is now the persistent project shell.
class WelcomeDashboard(SpectraSuiteWindow):
    def __init__(self) -> None:
        super().__init__(WORKSPACES, resource_path)


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
    elif key == "multiaxis":
        from multiaxis import run
    elif key == "plot3d":
        from plot3d import run
    elif key == "fluid":
        from fluid import run
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
    from multiaxis import main as _multiaxis_main
    from plot3d import main as _plot3d_main
    from fluid import main as _fluid_main

    # Keep references alive through the check and make import failures fatal.
    required = (
        _general_main, _GeneralPlotter, _ir_main, _PlotViewer, _SetupDialog, _xrd_main,
        _uvvis_main, _raman_main,
        _multiaxis_main, _plot3d_main, _fluid_main,
    )
    if not all(required):
        raise RuntimeError("A required workspace entry point is unavailable")

    app = QApplication.instance() or QApplication([])
    window = WelcomeDashboard()
    window.show()
    app.processEvents()
    if window.document_tabs.count() != 1 or window.document_tabs.widget(0) is not window.home_page:
        raise RuntimeError("The persistent Home document did not initialize")
    if set(window._buttons) != {
        "ir", "xrd", "uvvis", "raman", "general", "plot3d",
        "multiaxis", "fluid", "xps",
    }:
        raise RuntimeError("The dashboard did not create every workspace button")
    window.close()
    app.processEvents()
    print("SpectraSuite startup smoke test passed")
    return 0


def main() -> int:
    multiprocessing.freeze_support()
    workspace_key = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == "--workspace" else "launcher"
    set_windows_app_id(workspace_key)
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke-test":
        return startup_smoke_test()
    if len(sys.argv) == 3 and sys.argv[1] == "--workspace":
        return run_workspace(sys.argv[2])
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
