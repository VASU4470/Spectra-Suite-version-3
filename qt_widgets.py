"""Small shared Qt widgets used by every plotting window."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtCore import QSize


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
