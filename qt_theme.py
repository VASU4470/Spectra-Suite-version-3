"""Shared visual theme and window-icon helpers for SpectraSuite."""

from __future__ import annotations

import re
import sys
import weakref
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


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
QToolBar#compactDataTools QToolButton#qt_toolbar_ext_button {
    padding: 0; margin: 0; min-width: 0; border: 0;
}
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


# Themes change only the interface chrome. Matplotlib curves, plot backgrounds,
# and exported figures continue to use their own scientific/style settings.
THEMES = {
    "blue": {
        "label": "Classic blue",
        "accent": "#2563eb",
        "strong": "#1d4ed8",
        "soft": "#dbeafe",
        "pale": "#eff6ff",
        "gradient_end": None,
    },
    "teal": {
        "label": "Laboratory teal",
        "accent": "#0f766e",
        "strong": "#115e59",
        "soft": "#ccfbf1",
        "pale": "#f0fdfa",
        "gradient_end": None,
    },
    "plum": {
        "label": "Plum",
        "accent": "#7e22ce",
        "strong": "#6b21a8",
        "soft": "#f3e8ff",
        "pale": "#faf5ff",
        "gradient_end": None,
    },
    "rose": {
        "label": "Rose",
        "accent": "#be185d",
        "strong": "#9d174d",
        "soft": "#fce7f3",
        "pale": "#fdf2f8",
        "gradient_end": None,
    },
    "graphite": {
        "label": "Graphite",
        "accent": "#475569",
        "strong": "#334155",
        "soft": "#e2e8f0",
        "pale": "#f8fafc",
        "gradient_end": None,
    },
    "ocean": {
        "label": "Ocean gradient",
        "accent": "#0369a1",
        "strong": "#075985",
        "soft": "#cffafe",
        "pale": "#ecfeff",
        "gradient_end": "#0f766e",
    },
    "aurora": {
        "label": "Aurora gradient",
        "accent": "#7e22ce",
        "strong": "#6b21a8",
        "soft": "#f3e8ff",
        "pale": "#faf5ff",
        "gradient_end": "#be185d",
    },
}

_ACTIVE_THEME = None
_THEMED_WIDGETS = weakref.WeakKeyDictionary()


def current_theme():
    """Return the saved interface theme, falling back safely to classic blue."""
    global _ACTIVE_THEME
    if _ACTIVE_THEME is None:
        saved = str(QSettings("SpectraSuite", "SpectraSuite").value(
            "appearance/theme", "blue"
        ))
        _ACTIVE_THEME = saved if saved in THEMES else "blue"
    return _ACTIVE_THEME


def themed_stylesheet(base_style=LIGHT_STYLE, theme_key=None):
    """Recolor one existing light stylesheet without touching plot artists."""
    theme = THEMES[theme_key or current_theme()]
    replacements = {
        "#2563eb": theme["accent"],
        "#1d4ed8": theme["strong"],
        "#60a5fa": theme["accent"],
        "#93b4ec": theme["accent"],
        "#dbeafe": theme["soft"],
        "#bfdbfe": theme["soft"],
        "#eff6ff": theme["pale"],
    }
    result = re.sub(
        r"#[0-9a-fA-F]{6}",
        lambda match: replacements.get(match.group(0).lower(), match.group(0)),
        base_style,
    )
    gradient_end = theme["gradient_end"]
    if gradient_end:
        gradient = (
            "qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {theme['accent']},stop:1 {gradient_end})"
        )
        result += f"""
QPushButton#primary, QPushButton#launch, QTabBar::tab:selected {{
    background: {gradient}; color: #ffffff; border-color: {theme['strong']};
}}
QFrame#homeHero {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #ffffff,stop:1 {theme['soft']});
}}
"""
    return result


def apply_theme(widget, base_style=LIGHT_STYLE):
    """Apply and register a stylesheet so live theme changes reach this window."""
    _THEMED_WIDGETS[widget] = base_style
    widget.setStyleSheet(themed_stylesheet(base_style))


def set_theme(theme_key, *, persist=True):
    """Apply a theme immediately to every registered application window."""
    global _ACTIVE_THEME
    if theme_key not in THEMES:
        raise ValueError(f"Unknown interface theme: {theme_key}")
    _ACTIVE_THEME = theme_key
    if persist:
        QSettings("SpectraSuite", "SpectraSuite").setValue(
            "appearance/theme", theme_key
        )
    for widget, base_style in list(_THEMED_WIDGETS.items()):
        try:
            widget.setStyleSheet(themed_stylesheet(base_style, theme_key))
        except RuntimeError:
            # The Qt object was destroyed before its Python wrapper disappeared.
            _THEMED_WIDGETS.pop(widget, None)


class AppearanceDialog(QDialog):
    """Small live-preview selector for the light interface themes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Appearance")
        self.setMinimumWidth(380)
        root = QVBoxLayout(self)
        heading = QLabel("Interface theme")
        heading.setStyleSheet("font-size:17px;font-weight:800;")
        root.addWidget(heading)
        note = QLabel(
            "Choose a light accent or gradient. This changes application controls "
            "only; spectrum colors and exported figures are unchanged."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        self.theme_combo = QComboBox()
        for key, theme in THEMES.items():
            self.theme_combo.addItem(theme["label"], key)
        self.theme_combo.setCurrentIndex(
            self.theme_combo.findData(current_theme())
        )
        self.theme_combo.currentIndexChanged.connect(self._theme_selected)
        root.addWidget(self.theme_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_theme(self)

    def _theme_selected(self, _index):
        set_theme(self.theme_combo.currentData())
