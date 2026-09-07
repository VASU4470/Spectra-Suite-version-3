"""Raman-specific peak measurement dialog."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from raman_analysis import measure_raman_peaks, nearest_peak_ratio
from qt_theme import LIGHT_STYLE, apply_window_icon


class RamanAnalysisDialog(QDialog):
    def __init__(self, x, y, sample_name: str, parent=None):
        super().__init__(parent)
        self.x, self.y = np.asarray(x, float), np.asarray(y, float)
        self.sample_name = sample_name
        self.peaks = []
        self.setWindowTitle(f"Raman peak analysis — {sample_name}")
        self.resize(760, 620)
        self.setStyleSheet(LIGHT_STYLE)
        apply_window_icon(self, "RAMAN")
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.prominence = QDoubleSpinBox()
        self.prominence.setRange(0, 1e12)
        self.prominence.setDecimals(5)
        self.prominence.setValue(max(0.0, float(np.nanmax(self.y)-np.nanmin(self.y))*0.05))
        self.first_shift = self._shift_spin(1350.0)
        self.second_shift = self._shift_spin(1580.0)
        form.addRow("Peak prominence", self.prominence)
        form.addRow("Ratio numerator target", self.first_shift)
        form.addRow("Ratio denominator target", self.second_shift)
        root.addLayout(form)
        row = QHBoxLayout()
        detect = QPushButton("Detect and measure peaks")
        detect.clicked.connect(self.calculate)
        ratio = QPushButton("Calculate intensity ratio")
        ratio.clicked.connect(self.calculate_ratio)
        row.addWidget(detect)
        row.addWidget(ratio)
        root.addLayout(row)
        self.result = QLabel("Peak areas are integrated above a local FWHM baseline.")
        self.result.setWordWrap(True)
        root.addWidget(self.result)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Raman shift (cm⁻¹)", "Intensity", "FWHM (cm⁻¹)", "Area"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        export = QPushButton("Export peak table CSV")
        export.clicked.connect(self.export_csv)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom.addWidget(export)
        bottom.addStretch()
        bottom.addWidget(close)
        root.addLayout(bottom)

    @staticmethod
    def _shift_spin(value):
        spin = QDoubleSpinBox()
        spin.setRange(-1e6, 1e6)
        spin.setDecimals(3)
        spin.setSuffix(" cm⁻¹")
        spin.setValue(value)
        return spin

    def calculate(self):
        self.peaks = measure_raman_peaks(self.x, self.y, self.prominence.value())
        self.table.setRowCount(len(self.peaks))
        for row, peak in enumerate(self.peaks):
            for column, value in enumerate((peak.shift_cm1, peak.intensity, peak.fwhm_cm1, peak.area)):
                self.table.setItem(row, column, QTableWidgetItem(f"{value:.7g}"))
        self.result.setText(f"Detected {len(self.peaks)} upward Raman band(s).")

    def calculate_ratio(self):
        if not self.peaks:
            self.calculate()
        try:
            first, second, ratio = nearest_peak_ratio(
                self.peaks, self.first_shift.value(), self.second_shift.value()
            )
        except ValueError as error:
            QMessageBox.warning(self, "Raman ratio", str(error))
            return
        self.result.setText(
            f"I({first.shift_cm1:.3g}) / I({second.shift_cm1:.3g}) = {ratio:.5g}. "
            "Use only ratios appropriate to the material and acquisition conditions."
        )

    def export_csv(self):
        if not self.peaks:
            self.calculate()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Raman peaks", f"{self.sample_name}_raman_peaks.csv", "CSV files (*.csv)"
        )
        if not filename:
            return
        try:
            with Path(filename).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Raman shift (cm^-1)", "Intensity", "FWHM (cm^-1)", "Area"])
                for peak in self.peaks:
                    writer.writerow([peak.shift_cm1, peak.intensity, peak.fwhm_cm1, peak.area])
        except OSError as error:
            QMessageBox.critical(self, "Export error", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Saved to:\n{filename}")
