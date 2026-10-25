"""Shared UI-v2 helpers for on-demand tool panels.

These helpers change presentation only. They do not alter scientific data,
processing, plotting, or export behavior.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)


def park_panel(owner, panel, *, host_name="_ui_v2_panel_host"):
    """Keep a legacy control widget alive but off the permanent workspace."""
    host = getattr(owner, host_name, None)
    if host is None:
        host = QWidget(owner)
        host.hide()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        setattr(owner, host_name, host)
        setattr(owner, host_name + "_layout", layout)
    else:
        layout = getattr(owner, host_name + "_layout")
    panel.setParent(host)
    layout.addWidget(panel)
    panel.hide()
    return host


def show_panel_dialog(
    owner,
    panel,
    title,
    *,
    dialog_name="_ui_v2_panel_dialog",
    host_name="_ui_v2_panel_host",
    size=(620, 760),
    minimum=(500, 520),
):
    """Show one existing control widget in a reusable non-modal dialog."""
    existing = getattr(owner, dialog_name, None)
    if existing is not None and existing.isVisible():
        existing.setWindowTitle(title)
        existing.raise_()
        existing.activateWindow()
        return existing

    park_panel(owner, panel, host_name=host_name)

    dialog = QDialog(owner)
    dialog.setWindowTitle(title)
    dialog.resize(*size)
    dialog.setMinimumSize(*minimum)
    layout = QVBoxLayout(dialog)
    panel.setParent(dialog)
    panel.show()
    layout.addWidget(panel, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.accept)
    layout.addWidget(buttons)

    def restore(_result=0):
        park_panel(owner, panel, host_name=host_name)
        setattr(owner, dialog_name, None)

    dialog.finished.connect(restore)
    setattr(owner, dialog_name, dialog)
    dialog.show()
    return dialog
