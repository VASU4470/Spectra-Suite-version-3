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
QPushButton#primary:disabled { color: #8290a3; background-color: #edf1f6; border-color: #cbd5e1; }
QTabWidget::pane { border: 1px solid #b8c4d6; background-color: #f8fafc; }
QTabBar::tab {
    background-color: #e8eef7;
    color: #334155;
    border: 1px solid #b8c4d6;
    padding: 8px 15px;
}
QTabBar::tab:selected { background-color: #2563eb; color: #ffffff; }
QScrollArea, QSplitter { background-color: #f4f7fb; }
QSplitter::handle { background-color: #d7e0ec; }
QSplitter::handle:hover { background-color: #93b4ec; }
QToolBar#compactDataTools { background: transparent; border: 0; spacing: 2px; }
QToolBar#compactDataTools QToolButton { padding: 3px 5px; font-size: 12px; }
QToolButton#qt_toolbar_ext_button { padding: 0; min-width: 18px; max-width: 18px; }
QToolTip { background-color: #172033; color: #ffffff; border: 1px solid #334155; }

/* Project–Canvas–Inspector spectroscopy workspace */
QFrame#workspaceHeader {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
}
QLabel#workspaceBrand {
    color: #1d4ed8;
    font-size: 18px;
    font-weight: 800;
    padding-right: 4px;
}
QLabel#techniqueBadge {
    color: #1d4ed8;
    background-color: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    padding: 5px 9px;
    font-weight: 700;
}
QLabel#projectTitle { color: #172033; font-size: 15px; font-weight: 750; }
QLabel#inspectorTitle { color: #172033; font-size: 17px; font-weight: 800; }
QLabel#mutedLabel { color: #64748b; font-size: 11px; }
QLabel#sectionLabel {
    color: #64748b;
    font-size: 10px;
    font-weight: 750;
    padding: 8px 3px 2px 3px;
}
QLineEdit#commandSearch {
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 7px 10px;
}
QFrame#projectSidebar {
    background-color: #f8fafc;
    border: 1px solid #d7e0ec;
    border-radius: 8px;
}
QListWidget#projectDataList {
    background-color: transparent;
    border: none;
    padding: 0;
}
QListWidget#projectDataList::item {
    color: #334155;
    border-radius: 6px;
    padding: 8px 7px;
    margin: 1px 0;
}
QListWidget#projectDataList::item:selected {
    color: #1d4ed8;
    background-color: #e8f0ff;
    border: 1px solid #bfdbfe;
}
QPushButton#sidebarAction {
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 7px 8px;
}
QPushButton#sidebarAction:hover { background-color: #e8f0ff; }
QFrame#canvasPanel {
    background-color: #ffffff;
    border: 1px solid #d7e0ec;
    border-radius: 8px;
}
QFrame#workflowBar {
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #d7e0ec;
}
QToolButton#workflowButton {
    background-color: transparent;
    color: #526178;
    border: none;
    border-radius: 0;
    padding: 9px 13px;
    font-size: 13px;
}
QToolButton#workflowButton:hover { color: #1d4ed8; background-color: #f4f7ff; }
QToolButton#workflowButton:checked {
    color: #1d4ed8;
    background-color: #eff6ff;
    border-bottom: 3px solid #2563eb;
    font-weight: 700;
}
QFrame#seriesBar {
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #e2e8f0;
}
QScrollArea#seriesScroll { background-color: #ffffff; border: none; }
QToolButton#seriesChip {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 6px 10px;
}
QToolButton#seriesChip:hover { background-color: #f8fafc; border-color: #93c5fd; }
QToolButton#seriesChip:checked {
    background-color: #eff6ff;
    border: 1px solid #60a5fa;
    font-weight: 700;
}
QFrame#contextInspector {
    background-color: #f8fafc;
    border: 1px solid #d7e0ec;
    border-radius: 8px;
}
QTabWidget#inspectorPages::pane { border: none; background-color: transparent; }
QTabWidget#inspectorPages QScrollArea { background-color: transparent; }
QTabWidget#canvasTabs::pane {
    background-color: #ffffff;
    border: none;
    border-top: 1px solid #e2e8f0;
}
QTabWidget#canvasTabs QTabBar::tab {
    background-color: #ffffff;
    color: #526178;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 7px 18px;
}
QTabWidget#canvasTabs QTabBar::tab:selected {
    color: #1d4ed8;
    background-color: #eff6ff;
    border-bottom: 2px solid #2563eb;
    font-weight: 700;
}
QWidget#dataWorkspace { background-color: #ffffff; }
QTabWidget#rightSidebarTabs::pane {
    background-color: #f8fafc;
    border: 1px solid #d7e0ec;
    border-radius: 8px;
}
QTabWidget#rightSidebarTabs QTabBar::tab {
    background-color: #f8fafc;
    color: #526178;
    border: 1px solid #d7e0ec;
    border-right: none;
    padding: 12px 7px;
    min-width: 24px;
}
QTabWidget#rightSidebarTabs QTabBar::tab:selected {
    color: #1d4ed8;
    background-color: #eff6ff;
    border-left: 3px solid #2563eb;
    font-weight: 700;
}
QSplitter::handle { background-color: #e2e8f0; }
"""


ICON_FILES = {
    "FTIR": "ir_icon_taskbar.png",
    "XRD": "xrd_icon_taskbar.png",
    "UVVIS": "uvvis_icon_taskbar.png",
    "RAMAN": "raman_icon_taskbar.png",
    "XPS": "xps_icon.svg",
    "LIBS": "libs_icon.svg",
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
