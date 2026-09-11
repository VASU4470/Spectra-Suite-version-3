"""Shared visual theme and window-icon helpers for SpectraSuite."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


LIGHT_STYLE = """
QWidget, QDialog {
    background-color: #f4f7fb;
    color: #172033;
    font-size: 13px;
}
QLabel, QCheckBox, QRadioButton {
    color: #172033;
    background-color: transparent;
}
QCheckBox::indicator {
    width: 16px; height: 16px; background-color: #ffffff;
    border: 1px solid #64748b; border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #2563eb; border: 2px solid #1d4ed8;
}
QGroupBox {
    color: #172033;
    border: 1px solid #b8c4d6;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 700;
    background-color: #f8fafc;
}
QGroupBox::title {
    color: #172033;
    background-color: #f4f7fb;
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget,
QTableWidget, QPlainTextEdit, QTextEdit {
    background-color: #ffffff;
    color: #172033;
    border: 1px solid #a9b7ca;
    border-radius: 5px;
    padding: 5px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #172033;
    selection-background-color: #dbeafe;
    selection-color: #172033;
}
QHeaderView::section {
    background-color: #e8eef7;
    color: #172033;
    border: 1px solid #c5cfdd;
    padding: 5px;
    font-weight: 700;
}
QPushButton {
    background-color: #e8eef7;
    color: #172033;
    border: 1px solid #a9b7ca;
    border-radius: 6px;
    padding: 7px 11px;
}
QPushButton:hover { background-color: #dbeafe; border-color: #2563eb; }
QPushButton:pressed { background-color: #bfdbfe; }
QPushButton:disabled { color: #8290a3; background-color: #edf1f6; }
QToolButton {
    background-color: #e8eef7; color: #172033;
    border: 1px solid #94a3b8; border-radius: 5px; padding: 3px 7px;
}
QToolButton:hover { background-color: #dbeafe; border-color: #2563eb; }
QToolButton:pressed, QToolButton:checked { background-color: #bfdbfe; }
QPushButton#panelArrow {
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    padding: 0; border-radius: 5px; font-size: 15px; font-weight: 700;
}
QPushButton#primary, QPushButton#launch {
    background-color: #2563eb;
    color: #ffffff;
    border-color: #1d4ed8;
    font-weight: 700;
}
QPushButton#primary:hover, QPushButton#launch:hover { background-color: #1d4ed8; }
QTabWidget::pane { border: 1px solid #b8c4d6; background-color: #f8fafc; }
QTabBar::tab {
    background-color: #e8eef7;
    color: #334155;
    border: 1px solid #b8c4d6;
    padding: 8px 15px;
}
QTabBar::tab:selected { background-color: #2563eb; color: #ffffff; }
QScrollArea, QSplitter { background-color: #f4f7fb; }
QToolTip { background-color: #172033; color: #ffffff; border: 1px solid #334155; }
"""


ICON_FILES = {
    "FTIR": "ir_icon_taskbar.png",
    "XRD": "xrd_icon_taskbar.png",
    "UVVIS": "uvvis_icon_taskbar.png",
    "RAMAN": "raman_icon_taskbar.png",
    "GENERAL": "plot_icon_taskbar.png",
    "MULTIAXIS": "multiaxis_icon_taskbar.png",
    "PLOT3D": "plot3d_icon_taskbar.png",
    "FLUID": "fluid_icon_taskbar.png",
    "APP": "icon.png",
}


def resource_path(filename: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / filename


def apply_window_icon(window, technique: str = "APP") -> None:
    path = resource_path(ICON_FILES.get(technique, "icon.png"))
    if path.exists():
        icon = QIcon(str(path))
        window.setWindowIcon(icon)
        # Child workspaces run in separate processes. Setting the QApplication
        # icon as well as the window icon makes the taskbar/Dock icon visible.
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
