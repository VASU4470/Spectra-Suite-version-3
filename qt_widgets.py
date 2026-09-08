"""Small shared Qt widgets used by every plotting window."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton


class CompactNavigationToolbar(NavigationToolbar2QT):
    """Matplotlib's standard toolbar in a compact, bottom-panel-friendly form."""

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        self.setIconSize(QSize(17, 17))
        self.setMaximumHeight(32)
        self.setContentsMargins(0, 0, 0, 0)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(2, 1, 2, 1)
            layout.setSpacing(1)
        for action in self.actions():
            action.setIconVisibleInMenu(True)


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
