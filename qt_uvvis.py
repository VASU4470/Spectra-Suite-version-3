"""PySide6 UV-Vis band-edge analysis dialog."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from uvvis_analysis import (
    correct_absorption_baseline, fit_tauc, fit_urbach, signal_to_absorption,
    spectral_axis_to_energy, suggest_tauc_range,
)
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import CompactNavigationToolbar, PanelToggleButton


class UVVisAnalysisDialog(QDialog):
    """Interactive Tauc and Urbach fitting with explicit measurement assumptions."""

    def __init__(self, x, y, sample_name: str, parent=None, *, signal_kind=None):
        super().__init__(parent)
        self.x = np.asarray(x, float)
        self.y = np.asarray(y, float)
        self.sample_name = sample_name
        self.last_results = None
        self.setWindowTitle(f"UV-Vis advanced analysis — {sample_name}")
        self.resize(1050, 760)
        self.setStyleSheet(LIGHT_STYLE)
        apply_window_icon(self, "UVVIS")
        self._build_ui()
        if signal_kind:
            self.signal_kind.setCurrentText(signal_kind)
        self._set_default_ranges()
        self.result_label.setText(
            "Choose the correct data representation and linear fit ranges, then click Calculate."
        )

    def _build_ui(self):
        root = QVBoxLayout(self)
        assumptions = QGroupBox("Measurement and model assumptions")
        form = QFormLayout(assumptions)
        self.axis_kind = QComboBox()
        self.axis_kind.addItems(["Wavelength (nm)", "Photon energy (eV)", "Wavenumber (cm⁻¹)"])
        self.signal_kind = QComboBox()
        self.signal_kind.addItems([
            "Absorbance", "Transmittance (%)", "Transmittance (fraction)",
            "Reflectance (%)", "Reflectance (fraction)", "Kubelka-Munk F(R)",
            "Absorption coefficient (cm⁻¹)",
        ])
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0, 1e7)
        self.thickness.setDecimals(4)
        self.thickness.setSuffix(" µm")
        self.thickness.setSpecialValueText("not supplied")
        self.transition = QComboBox()
        self.transition.addItems(["Direct allowed", "Indirect allowed", "Direct forbidden", "Indirect forbidden"])
        form.addRow("X-axis data", self.axis_kind)
        form.addRow("Y-axis data", self.signal_kind)
        form.addRow("Optical path / film thickness", self.thickness)
        form.addRow("Tauc transition model", self.transition)
        self.baseline_method = QComboBox()
        self.baseline_method.addItems([
            "None", "Constant pre-edge baseline", "Linear pre-edge baseline",
        ])
        form.addRow("Absorption baseline", self.baseline_method)
        root.addWidget(assumptions)

        ranges = QGroupBox("Linear fit ranges (photon energy)")
        range_form = QFormLayout(ranges)
        self.tauc_start, self.tauc_end = self._range_pair()
        self.urbach_start, self.urbach_end = self._range_pair()
        self.baseline_start, self.baseline_end = self._range_pair()
        range_form.addRow("Pre-edge baseline range", self._pair_widget(self.baseline_start, self.baseline_end))
        range_form.addRow("Tauc range", self._pair_widget(self.tauc_start, self.tauc_end))
        range_form.addRow("Urbach range", self._pair_widget(self.urbach_start, self.urbach_end))
        root.addWidget(ranges)

        self.notice = QLabel(
            "Tauc and Urbach values depend on the selected linear region and material model. "
            "Kubelka–Munk F(R) is used only for reflectance inputs."
        )
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)

        self.figure = Figure(figsize=(9, 5), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        root.addWidget(self.canvas, 1)
        toolbar_row = QHBoxLayout()
        self.toolbar = CompactNavigationToolbar(self.canvas, self)
        self.toolbar_toggle = PanelToggleButton(self.toolbar, "bottom", self)
        toolbar_row.addWidget(self.toolbar, 1)
        toolbar_row.addWidget(self.toolbar_toggle)
        root.addLayout(toolbar_row)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)
        row = QHBoxLayout()
        suggest = QPushButton("Suggest Tauc range")
        suggest.clicked.connect(self.suggest_range)
        calculate = QPushButton("Calculate / refresh")
        calculate.clicked.connect(self.calculate)
        export = QPushButton("Export analysis CSV")
        export.clicked.connect(self.export_csv)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(suggest)
        row.addWidget(calculate)
        row.addWidget(export)
        row.addStretch()
        row.addWidget(close)
        root.addLayout(row)

    def _toggle_toolbar(self, hidden):
        self.toolbar_toggle.setChecked(bool(hidden))

    @staticmethod
    def _range_pair():
        controls = []
        for _ in range(2):
            spin = QDoubleSpinBox()
            spin.setRange(0, 1000)
            spin.setDecimals(4)
            spin.setSuffix(" eV")
            controls.append(spin)
        return controls

    @staticmethod
    def _pair_widget(first, second):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(first)
        row.addWidget(QLabel("to"))
        row.addWidget(second)
        return widget

    def _set_default_ranges(self):
        energy = spectral_axis_to_energy(self.x, self.axis_kind.currentText())
        finite = np.sort(energy[np.isfinite(energy) & (energy > 0)])
        if len(finite) < 3:
            return
        low, high = float(finite[0]), float(finite[-1])
        span = high - low
        self.tauc_start.setValue(low + 0.35 * span)
        self.tauc_end.setValue(low + 0.65 * span)
        self.urbach_start.setValue(low + 0.15 * span)
        self.urbach_end.setValue(low + 0.35 * span)
        self.baseline_start.setValue(low + 0.05 * span)
        self.baseline_end.setValue(low + 0.20 * span)

    def _converted_absorption(self):
        energy = spectral_axis_to_energy(self.x, self.axis_kind.currentText())
        thickness = self.thickness.value() or None
        raw_absorption, label = signal_to_absorption(
            self.y, self.signal_kind.currentText(), thickness
        )
        corrected, baseline = correct_absorption_baseline(
            energy, raw_absorption, self.baseline_start.value(), self.baseline_end.value(),
            self.baseline_method.currentText(),
        )
        return energy, raw_absorption, corrected, baseline, label

    def suggest_range(self):
        try:
            energy, _raw, absorption, _baseline, _label = self._converted_absorption()
            start, end = suggest_tauc_range(
                energy, absorption, self.transition.currentText()
            )
        except ValueError as error:
            QMessageBox.warning(self, "Tauc range suggestion", str(error))
            return
        self.tauc_start.setValue(start)
        self.tauc_end.setValue(end)
        self.result_label.setText(
            "A candidate linear region was selected. Inspect the plotted fit and R² before reporting Eg."
        )

    def calculate(self):
        try:
            energy, raw_absorption, absorption, baseline, absorption_label = self._converted_absorption()
            tauc, ordinate = fit_tauc(
                energy, absorption, self.transition.currentText(),
                self.tauc_start.value(), self.tauc_end.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "UV-Vis analysis", str(error))
            return
        urbach_error = ""
        try:
            urbach, log_alpha = fit_urbach(
                energy, absorption, self.urbach_start.value(), self.urbach_end.value()
            )
        except ValueError as error:
            urbach = None
            urbach_error = str(error)
            log_alpha = np.full_like(absorption, np.nan, dtype=float)
            positive = absorption > 0
            log_alpha[positive] = np.log(absorption[positive])

        order = np.argsort(energy)
        energy, raw_absorption, absorption, baseline = (
            energy[order], raw_absorption[order], absorption[order], baseline[order]
        )
        ordinate, log_alpha = ordinate[order], log_alpha[order]
        finite = np.isfinite(energy) & np.isfinite(absorption)
        energy, raw_absorption, absorption, baseline, ordinate, log_alpha = (
            energy[finite], raw_absorption[finite], absorption[finite], baseline[finite],
            ordinate[finite], log_alpha[finite]
        )
        self.figure.clear()
        ax1, ax2, ax3 = self.figure.subplots(1, 3)
        if self.baseline_method.currentText() != "None":
            ax1.plot(energy, raw_absorption, color="#94a3b8", alpha=0.8, label="Converted raw")
            ax1.plot(energy, baseline, "--", color="#d62728", label="Estimated baseline")
        ax1.plot(energy, absorption, color="#1f77b4", label="Analysis signal")
        ax1.legend(fontsize=8)
        ax1.set(xlabel="Photon energy (eV)", ylabel=absorption_label, title="Converted spectrum")
        ax2.plot(energy, ordinate, color="#9467bd")
        ax2.axvspan(tauc.fit.x_start, tauc.fit.x_end, color="#dbeafe", alpha=0.35)
        tx = np.linspace(tauc.band_gap_ev, tauc.fit.x_end, 150)
        ax2.plot(tx, tauc.fit.slope * tx + tauc.fit.intercept, "--", color="#d62728")
        ax2.axhline(0, color="#64748b", linewidth=0.8)
        ax2.scatter([tauc.band_gap_ev], [0], color="#2ca02c", zorder=5)
        ax2.annotate(f"Eg = {tauc.band_gap_ev:.4g} eV\n(y = 0 intercept)",
                     (tauc.band_gap_ev, 0), xytext=(8, 14), textcoords="offset points",
                     color="#166534", fontsize=8)
        ax2.set(xlabel="Photon energy (eV)", ylabel=f"(αhν)^{tauc.exponent:.3g}", title="Tauc plot")
        ax3.plot(energy, log_alpha, color="#ff7f0e")
        if urbach is not None:
            ux = np.linspace(urbach.fit.x_start, urbach.fit.x_end, 100)
            ax3.plot(ux, urbach.fit.slope * ux + urbach.fit.intercept, "--", color="#d62728")
        ax3.set(xlabel="Photon energy (eV)", ylabel="ln(absorption)", title="Urbach plot")
        self.canvas.draw_idle()
        proxy_note = "" if absorption_label == "α (cm⁻¹)" else f"; using {absorption_label} as an absorption proxy"
        uncertainty = (
            f" ± {tauc.band_gap_std_ev:.2g}" if np.isfinite(tauc.band_gap_std_ev) else ""
        )
        warning = " " + " ".join(tauc.warnings) if tauc.warnings else ""
        urbach_note = (
            f"Urbach energy = {urbach.urbach_energy_ev:.4g} eV "
            f"(R² = {urbach.fit.r_squared:.5f})"
            if urbach is not None else f"Urbach fit unavailable: {urbach_error}"
        )
        self.result_label.setText(
            f"Estimated Eg = {tauc.band_gap_ev:.4g}{uncertainty} eV at y=0; "
            f"fit: y = {tauc.fit.slope:.5g}E {tauc.fit.intercept:+.5g}, "
            f"R² = {tauc.fit.r_squared:.5f}; "
            f"{urbach_note}{proxy_note}.{warning}"
        )
        self.last_results = (energy, absorption, ordinate, log_alpha, tauc, urbach, absorption_label)

    def export_csv(self):
        if self.last_results is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export UV-Vis analysis", f"{self.sample_name}_uvvis_analysis.csv", "CSV files (*.csv)"
        )
        if not filename:
            return
        energy, absorption, ordinate, log_alpha, tauc, urbach, label = self.last_results
        try:
            with Path(filename).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["sample", self.sample_name])
                writer.writerow(["absorption representation", label])
                writer.writerow(["transition", self.transition.currentText()])
                writer.writerow(["band gap (eV)", tauc.band_gap_ev])
                writer.writerow(["band gap uncertainty (eV)", tauc.band_gap_std_ev])
                writer.writerow(["Tauc slope", tauc.fit.slope])
                writer.writerow(["Tauc y intercept", tauc.fit.intercept])
                writer.writerow(["Tauc R squared", tauc.fit.r_squared])
                writer.writerow(["Urbach energy (eV)", urbach.urbach_energy_ev if urbach else "unavailable"])
                writer.writerow(["Urbach R squared", urbach.fit.r_squared if urbach else "unavailable"])
                writer.writerow([])
                writer.writerow(["photon energy (eV)", label, "Tauc ordinate", "ln(absorption)"])
                writer.writerows(zip(energy, absorption, ordinate, log_alpha))
        except OSError as error:
            QMessageBox.critical(self, "Export error", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Saved to:\n{filename}")
