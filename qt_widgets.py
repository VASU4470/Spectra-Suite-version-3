"""Small shared Qt widgets used by every plotting window."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QToolButton, QWidget


class CompactNavigationToolbar(NavigationToolbar2QT):
    """Matplotlib's standard toolbar in a compact, bottom-panel-friendly form."""

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        palette = self.palette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            palette.setColor(role, QColor("#f8fafc"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#172033"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#172033"))
        self.setPalette(palette)
        # Matplotlib creates icons before the application stylesheet can
        # override a dark macOS system palette. Rebuild them against the light
        # palette so their black glyphs cannot disappear on pale buttons.
        for _text, _tooltip, image_file, callback in self.toolitems:
            if image_file and callback in self._actions:
                self._actions[callback].setIcon(self._icon(image_file + ".png"))
        self.setIconSize(QSize(17, 17))
        self.setMaximumHeight(32)
        self.setContentsMargins(0, 0, 0, 0)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(2, 1, 2, 1)
            layout.setSpacing(1)
        for action in self.actions():
            action.setIconVisibleInMenu(True)
        self.setStyleSheet("""
            QToolBar { background: #e8eef7; border: 1px solid #a9b7ca; spacing: 2px; }
            QToolButton {
                background: #ffffff; color: #172033; border: 1px solid #94a3b8;
                border-radius: 4px; padding: 2px; margin: 1px;
            }
            QToolButton:hover { background: #dbeafe; border-color: #2563eb; }
            QToolButton:checked { background: #bfdbfe; border-color: #1d4ed8; }
        """)


class AnnotationToolBar(QWidget):
    """Compact horizontal selector shared by every annotation workspace."""

    currentIndexChanged = Signal(int)
    TOOLS = (
        ("↖", "Select / move", "none", "#1d4ed8", "#eff6ff"),
        ("T", "Text", "text", "#7c3aed", "#f5f3ff"),
        ("➜", "Arrow", "arrow", "#dc2626", "#fef2f2"),
        ("╱", "Line", "line", "#9333ea", "#faf5ff"),
        ("▭", "Rectangle", "rect", "#0284c7", "#f0f9ff"),
        ("○", "Ellipse", "circle", "#059669", "#ecfdf5"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._index = 0
        self._buttons = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, (glyph, label, _value, color, background) in enumerate(self.TOOLS):
            button = QToolButton()
            button.setText(glyph)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setFixedSize(44, 40)
            button.setStyleSheet(f"""
                QToolButton {{
                    background: {background}; color: {color};
                    border: 1px solid #94a3b8; border-radius: 6px;
                    font-size: 18px; font-weight: 700;
                }}
                QToolButton:hover {{ border: 2px solid {color}; }}
                QToolButton:checked {{ background: {color}; color: white; border: 2px solid {color}; }}
            """)
            self.group.addButton(button, index)
            self._buttons.append(button)
            layout.addWidget(button)
        layout.addStretch()
        self._buttons[0].setChecked(True)
        self.group.idClicked.connect(self.setCurrentIndex)

    def currentData(self):
        return self.TOOLS[self._index][2]

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        index = max(0, min(int(index), len(self.TOOLS) - 1))
        changed = index != self._index
        self._index = index
        self._buttons[index].setChecked(True)
        if changed:
            self.currentIndexChanged.emit(index)


class PanelToggleButton(QPushButton):
    """Small, always-visible arrow used to collapse an adjacent panel."""

    def __init__(self, panel, side="left", parent=None):
        super().__init__(parent)
        if side not in {"left", "right", "bottom"}:
            raise ValueError("side must be left, right, or bottom")
        self.panel = panel
        self.side = side
        self.setCheckable(True)
        self.setFixedSize(30, 30)
        self.setObjectName("panelArrow")
        self.setToolTip("Hide panel")
        self.toggled.connect(self._apply_state)
        self._refresh_arrow(False)

    def _refresh_arrow(self, hidden):
        visible_arrow = {"left": "◀", "right": "▶", "bottom": "▼"}
        hidden_arrow = {"left": "▶", "right": "◀", "bottom": "▲"}
        self.setText(hidden_arrow[self.side] if hidden else visible_arrow[self.side])
        self.setToolTip("Show panel" if hidden else "Hide panel")

    def _apply_state(self, hidden):
        self.panel.setVisible(not hidden)
        self._refresh_arrow(hidden)

    def set_panel_visible(self, visible):
        self.setChecked(not visible)
        self._apply_state(not visible)
