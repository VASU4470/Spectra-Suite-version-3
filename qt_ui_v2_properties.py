"""UI-v2 object property dialogs for SpectraSuite.

These dialogs are presentation adapters over existing state/control paths.
They deliberately do not redefine scientific defaults or equations.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import state
from qt_theme import LIGHT_STYLE, apply_theme, apply_window_icon


class AxisPropertiesDialog(QDialog):
    """Edit current plot-axis presentation through PlotViewer's existing controls."""

    def __init__(self, viewer, parent=None):
        super().__init__(parent or viewer)
        self.viewer = viewer
        self.setWindowTitle("Axis Properties")
        self.resize(590, 430)
        self.setMinimumSize(520, 390)
        apply_theme(self, LIGHT_STYLE)
        apply_window_icon(self, state.technique)

        root = QVBoxLayout(self)

        selector_form = QFormLayout()
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X axis", "Y axis"])
        self.axis_combo.currentIndexChanged.connect(self._load_axis)
        selector_form.addRow("Axis", self.axis_combo)
        root.addLayout(selector_form)

        self.pages = QTabWidget()
        root.addWidget(self.pages, 1)

        scale_page = QWidget()
        scale_form = QFormLayout(scale_page)
        self.minimum_edit = QLineEdit()
        self.maximum_edit = QLineEdit()
        self.step_edit = QLineEdit()
        self.direction_label = QLabel()
        self.direction_label.setWordWrap(True)
        scale_form.addRow("Minimum", self.minimum_edit)
        scale_form.addRow("Maximum", self.maximum_edit)
        scale_form.addRow("Major tick interval", self.step_edit)
        scale_form.addRow("Direction", self.direction_label)
        self.pages.addTab(scale_page, "Scale")

        appearance_page = QWidget()
        appearance_form = QFormLayout(appearance_page)
        self.label_edit = QLineEdit()
        self.minor_check = QCheckBox("Show minor ticks")
        self.tick_labels_check = QCheckBox("Show tick labels")
        appearance_form.addRow("Axis label", self.label_edit)
        appearance_form.addRow(self.minor_check)
        appearance_form.addRow(self.tick_labels_check)
        self.pages.addTab(appearance_page, "Appearance")

        information_page = QWidget()
        information_layout = QVBoxLayout(information_page)
        information = QLabel(
            "Axis direction follows the established spectroscopy convention. "
            "FT-IR and XPS X axes remain reversed; other techniques remain normal. "
            "Changing those scientific conventions is outside this UI migration."
        )
        information.setWordWrap(True)
        information_layout.addWidget(information)
        information_layout.addStretch(1)
        self.pages.addTab(information_page, "Convention")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._apply_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        root.addWidget(buttons)

        self._load_axis()

    @staticmethod
    def _split_limits(text):
        value = str(text or "").strip()
        if not value:
            return "", ""
        parts = [item.strip() for item in value.split(",", 1)]
        if len(parts) != 2:
            return "", ""
        return parts[0], parts[1]

    def _load_axis(self):
        is_x = self.axis_combo.currentIndex() == 0
        if is_x:
            minimum, maximum = self._split_limits(self.viewer.xlim_edit.text())
            self.label_edit.setText(self.viewer.xlabel_edit.text())
            self.step_edit.setText(self.viewer.xstep_edit.text())
            direction = "Reversed (technique convention)" if state.technique in {"FTIR", "XPS"} else "Normal"
        else:
            minimum, maximum = self._split_limits(self.viewer.ylim_edit.text())
            self.label_edit.setText(self.viewer.ylabel_edit.text())
            self.step_edit.setText(self.viewer.ystep_edit.text())
            direction = "Normal"
        self.minimum_edit.setText(minimum)
        self.maximum_edit.setText(maximum)
        self.direction_label.setText(direction)
        self.minor_check.setChecked(self.viewer.minor_check.isChecked())
        self.tick_labels_check.setChecked(self.viewer.tick_labels_check.isChecked())

    def apply(self):
        is_x = self.axis_combo.currentIndex() == 0
        minimum = self.minimum_edit.text().strip()
        maximum = self.maximum_edit.text().strip()
        limits = f"{minimum},{maximum}" if minimum and maximum else ""

        if is_x:
            self.viewer.xlabel_edit.setText(self.label_edit.text())
            self.viewer.xlim_edit.setText(limits)
            self.viewer.xstep_edit.setText(self.step_edit.text().strip())
        else:
            self.viewer.ylabel_edit.setText(self.label_edit.text())
            self.viewer.ylim_edit.setText(limits)
            self.viewer.ystep_edit.setText(self.step_edit.text().strip())

        self.viewer.minor_check.setChecked(self.minor_check.isChecked())
        self.viewer.tick_labels_check.setChecked(self.tick_labels_check.isChecked())
        self.viewer.save_and_update()

    def _apply_and_accept(self):
        self.apply()
        self.accept()
