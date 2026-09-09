"""Shared PySide6 plotting workspace for SpectraSuite applications."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from annotations import AnnotationManager
from config import state
from dataset_reader import discover_many
from processing import process_spectrum
from readers import read_generic_configured, robust_read_spectrum
from qt_uvvis import UVVisAnalysisDialog
from qt_raman import RamanAnalysisDialog
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import AnnotationToolBar, CompactNavigationToolbar, PanelToggleButton
from plot_export import save_figure
from plot_styles import BASIC_COLORS, LEGEND_LOCATIONS, PLOT_COLORS
from spectral_preprocessing import subtract_reference, trim_noisy_edges


STYLE = LIGHT_STYLE + """
QLabel#cursor { color: #1d4ed8; font-weight: 700; }
"""


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _parse_limits(text: str):
    if not text.strip():
        return None
    try:
        values = [float(item.strip()) for item in text.split(",")]
    except ValueError:
        return None
    return values if len(values) == 2 else None


def _format_limits(value) -> str:
    if not value:
        return ""
    return ", ".join(str(item) for item in value)


def _unique_stem(path: Path, existing: list[str]) -> str:
    stem = path.stem
    if stem not in existing:
        return stem
    index = 2
    while f"{stem}_{index}" in existing:
        index += 1
    return f"{stem}_{index}"


class TextAnnotationDialog(QDialog):
    """Qt rich-text composer using Matplotlib mathtext syntax."""

    GREEK = (
        ("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"),
        ("δ", r"\delta"), ("ε", r"\epsilon"), ("ζ", r"\zeta"),
        ("η", r"\eta"), ("θ", r"\theta"), ("ι", r"\iota"),
        ("κ", r"\kappa"), ("λ", r"\lambda"), ("μ", r"\mu"),
        ("ν", r"\nu"), ("ξ", r"\xi"), ("π", r"\pi"),
        ("ρ", r"\rho"), ("σ", r"\sigma"), ("τ", r"\tau"),
        ("υ", r"\upsilon"), ("φ", r"\phi"), ("χ", r"\chi"),
        ("ψ", r"\psi"), ("ω", r"\omega"), ("Γ", r"\Gamma"),
        ("Δ", r"\Delta"), ("Θ", r"\Theta"), ("Λ", r"\Lambda"),
        ("Ξ", r"\Xi"), ("Π", r"\Pi"), ("Σ", r"\Sigma"),
        ("Υ", r"\Upsilon"), ("Φ", r"\Phi"), ("Ψ", r"\Psi"),
        ("Ω", r"\Omega"),
    )
    SYMBOLS = (
        ("±", r"\pm"), ("×", r"\times"), ("÷", r"\div"),
        ("≈", r"\approx"), ("≠", r"\neq"), ("≤", r"\leq"),
        ("≥", r"\geq"), ("∞", r"\infty"), ("√", r"\sqrt{}"),
        ("∑", r"\sum"), ("∫", r"\int"), ("°", r"^{\circ}"),
        ("→", r"\rightarrow"), ("∂", r"\partial"), ("Å", r"\AA"),
    )

    def __init__(
        self,
        parent=None,
        *,
        text="",
        color="black",
        fontsize=12.0,
        bold=False,
        italic=False,
        family="sans-serif",
        underline=False,
    ):
        super().__init__(parent)
        self.result = None
        self.setWindowTitle("Text Annotation")
        self.resize(760, 760)
        self.setMinimumSize(620, 580)
        self.setStyleSheet(STYLE)
        apply_window_icon(self, state.technique)
        self._build_ui(text, color, fontsize, bold, italic, family, underline)

    def _build_ui(self, text, color, fontsize, bold, italic, family, underline):
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Text and Matplotlib math notation"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setMinimumHeight(100)
        self.text_edit.setMaximumHeight(150)
        layout.addWidget(self.text_edit)

        style_group = QGroupBox("Style")
        style_group.setMinimumHeight(175)
        style_form = QFormLayout(style_group)
        flags = QWidget()
        flags_layout = QHBoxLayout(flags)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        self.bold_check = QCheckBox("Bold")
        self.bold_check.setChecked(bold)
        self.italic_check = QCheckBox("Italic")
        self.italic_check.setChecked(italic)
        self.underline_check = QCheckBox("Underline")
        self.underline_check.setChecked(underline)
        flags_layout.addWidget(self.bold_check)
        flags_layout.addWidget(self.italic_check)
        flags_layout.addWidget(self.underline_check)
        style_form.addRow(flags)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(4, 100)
        self.size_spin.setValue(float(fontsize))
        self.size_spin.setMinimumWidth(180)
        style_form.addRow("Font size", self.size_spin)
        self.family_combo = QComboBox()
        self.family_combo.setMinimumWidth(180)
        self.family_combo.addItems(["sans-serif", "serif", "monospace", "cursive", "fantasy"])
        self.family_combo.setCurrentText(family if family in {
            "sans-serif", "serif", "monospace", "cursive", "fantasy"
        } else "sans-serif")
        style_form.addRow("Font family", self.family_combo)
        color_widget = QWidget()
        color_layout = QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_edit = QLineEdit(str(color))
        self.color_edit.setMinimumWidth(180)
        color_button = QPushButton("Pick")
        color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_edit)
        color_layout.addWidget(color_button)
        style_form.addRow("Color", color_widget)
        layout.addWidget(style_group)

        insert_group = QGroupBox("Insert at Cursor")
        insert_layout = QHBoxLayout(insert_group)
        superscript = QPushButton("x² Superscript")
        superscript.clicked.connect(lambda: self._insert_math(r"^{}", -1))
        subscript = QPushButton("x₂ Subscript")
        subscript.clicked.connect(lambda: self._insert_math(r"_{}", -1))
        superscript.setMinimumHeight(36)
        subscript.setMinimumHeight(36)
        insert_layout.addWidget(superscript)
        insert_layout.addWidget(subscript)
        layout.addWidget(insert_group)

        greek_group = QGroupBox("Greek Letters")
        greek_layout = QGridLayout(greek_group)
        self._symbol_buttons(greek_layout, self.GREEK, 9)
        layout.addWidget(greek_group)
        symbol_group = QGroupBox("Math Symbols")
        symbol_layout = QGridLayout(symbol_group)
        self._symbol_buttons(symbol_layout, self.SYMBOLS, 8)
        layout.addWidget(symbol_group)

        help_text = QLabel(
            "Symbols use Matplotlib mathtext ($…$), so no LaTeX installation is required."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _symbol_buttons(self, layout, values, columns):
        for index, (label, command) in enumerate(values):
            button = QPushButton(label)
            button.setFixedSize(44, 34)
            button.setAccessibleName(f"Insert {label}")
            button.setStyleSheet("""
                QPushButton {
                    color: #172033; background: #e8eef7;
                    border: 1px solid #94a3b8; border-radius: 5px;
                    font-size: 16px; font-weight: 700; padding: 1px;
                }
                QPushButton:hover { background: #dbeafe; border-color: #2563eb; }
                QPushButton:pressed { background: #bfdbfe; }
            """)
            button.clicked.connect(lambda _checked=False, value=command: self._insert_math(value + " "))
            layout.addWidget(button, index // columns, index % columns)

    def _insert_math(self, snippet, cursor_offset=0):
        text = self.text_edit.toPlainText()
        cursor = self.text_edit.textCursor()
        position = cursor.position()
        if not (text.startswith("$") and text.endswith("$") and len(text) >= 2):
            text = f"${text}$"
            position = min(position + 1, len(text) - 1)
            self.text_edit.setPlainText(text)
            cursor = self.text_edit.textCursor()
        position = min(max(1, position), len(self.text_edit.toPlainText()) - 1)
        cursor.setPosition(position)
        cursor.insertText(snippet)
        cursor.setPosition(max(1, cursor.position() + cursor_offset))
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    def _choose_color(self):
        color = QColorDialog.getColor(QColor(self.color_edit.text()), self, "Text Color")
        if color.isValid():
            self.color_edit.setText(color.name())

    def _confirm(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Text Required", "Enter annotation text first.")
            return
        self.result = {
            "text": text,
            "color": self.color_edit.text().strip() or "black",
            "fontsize": self.size_spin.value(),
            "bold": self.bold_check.isChecked(),
            "italic": self.italic_check.isChecked(),
            "family": self.family_combo.currentText(),
            "underline": self.underline_check.isChecked(),
        }
        self.accept()


class ExportOptionsDialog(QDialog):
    """Select export products plus graph format and resolution."""

    def __init__(self, has_deconvolution=False, parent=None):
        super().__init__(parent)
        self.result = None
        self.setWindowTitle("Export Options")
        self.setMinimumWidth(430)
        self.resize(460, 330)
        self.setStyleSheet(STYLE)
        apply_window_icon(self, state.technique)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select items to export:"))
        self.data_check = QCheckBox("Processed data (.csv)")
        self.report_check = QCheckBox("Peaks and areas report (.txt)")
        self.image_check = QCheckBox("Graph image")
        for widget in (self.data_check, self.report_check, self.image_check):
            widget.setChecked(True)
            layout.addWidget(widget)
        self.deconv_check = QCheckBox("Deconvolution component data (.csv)")
        self.deconv_check.setChecked(has_deconvolution)
        self.deconv_check.setEnabled(has_deconvolution)
        layout.addWidget(self.deconv_check)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        self.format_combo = QComboBox()
        self.format_combo.addItems([".png", ".jpg", ".svg", ".pdf", ".tiff"])
        self.format_combo.setMinimumWidth(190)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150", "300", "600", "1200"])
        self.dpi_combo.setCurrentText("300")
        self.dpi_combo.setMinimumWidth(190)
        form.addRow("Image format", self.format_combo)
        form.addRow("Image DPI", self.dpi_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _confirm(self):
        if not any((
            self.data_check.isChecked(), self.report_check.isChecked(),
            self.image_check.isChecked(), self.deconv_check.isChecked(),
        )):
            QMessageBox.warning(self, "Selection Required", "Select at least one export item.")
            return
        self.result = {
            "data": self.data_check.isChecked(),
            "report": self.report_check.isChecked(),
            "image": self.image_check.isChecked(),
            "deconvolution": self.deconv_check.isChecked(),
            "format": self.format_combo.currentText(),
            "dpi": int(self.dpi_combo.currentText()),
        }
        self.accept()


class PlotViewer(QDialog):
    """Qt-native data viewer retaining the existing processing state model."""

    def __init__(self, data_tuples, title: str, out_dir=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1450, 850)
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(STYLE)

        apply_window_icon(self, state.technique)

        self.data_dict = {item[0]: (np.asarray(item[1]), np.asarray(item[2])) for item in data_tuples}
        self.stems = list(self.data_dict)
        if not self.stems:
            raise ValueError("PlotViewer requires at least one data series")
        self.current_stem = self.stems[0]
        self.out_dir = Path(out_dir) if out_dir else None
        self.ax = None
        self.cursors = []
        self.baseline_pts = []
        self.area_start = None
        self.deconv_start = None
        self._skip_close_prompt = False
        self._pending_annotations = state.global_set.get("annotations") or []
        self._state_undo = []
        self._state_redo = []
        self._artist_to_stem = {}
        self._axes_to_stem = {}

        self._build_layout()
        self._build_controls()
        self._connect_canvas()
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_select_callback=self._annotation_selected,
            on_list_update_callback=lambda _items: self._sync_annotation_list(),
            text_input_provider=self._request_annotation_text,
        )
        self._install_shortcuts()
        self._load_active_settings()
        self.update_plot()

    # ------------------------------- UI ---------------------------------
    def _build_layout(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.controls = QWidget()
        self.controls.setMinimumWidth(250)
        self.controls_layout = QVBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(0, 0, 4, 0)

        visibility = QHBoxLayout()
        self.controls_toggle = PanelToggleButton(self.controls, "left", self)
        self.controls_toggle.setToolTip("Hide side panel")
        visibility.addWidget(QLabel("Side panel"))
        visibility.addWidget(self.controls_toggle)
        visibility.addStretch()
        root.addLayout(visibility)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(True)
        root.addWidget(self.splitter, 1)

        self.splitter.addWidget(self.controls)

        self.plot_panel = QWidget()
        plot_layout = QVBoxLayout(self.plot_panel)
        plot_layout.setContentsMargins(4, 0, 0, 0)
        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toolbar = CompactNavigationToolbar(self.canvas, self.plot_panel)
        self.cursor_label = QLabel("X: -- | Y: --")
        self.cursor_label.setObjectName("cursor")
        self.cursor_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        plot_layout.addWidget(self.canvas, 1)
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.addWidget(self.toolbar, 1)
        self.toolbar_toggle = PanelToggleButton(self.toolbar, "bottom", self.plot_panel)
        self.toolbar_toggle.setToolTip("Hide plot toolbar")
        toolbar_row.addWidget(self.toolbar_toggle)
        plot_layout.addLayout(toolbar_row)
        plot_layout.addWidget(self.cursor_label)
        self.splitter.addWidget(self.plot_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([390, 1040])

    def _toggle_controls(self, hidden):
        self.controls_toggle.setChecked(bool(hidden))

    def _toggle_toolbar(self, hidden):
        self.toolbar_toggle.setChecked(bool(hidden))

    def _install_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.activated.connect(self._undo_active)
        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.redo_shortcut.activated.connect(self._redo_active)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.delete_shortcut.activated.connect(self._delete_active)
        self.backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self.backspace_shortcut.activated.connect(self._delete_active)

    def _build_controls(self):
        self.tabs = QTabWidget()
        self.controls_layout.addWidget(self.tabs, 1)
        self._build_file_tab()
        self._build_axes_tab()
        self._build_annotation_tab()
        self._build_analysis_tab()

        history = QHBoxLayout()
        undo = QPushButton("↶ Undo (Ctrl/Cmd+Z)")
        undo.clicked.connect(self._undo_active)
        redo = QPushButton("↷ Redo")
        redo.clicked.connect(self._redo_active)
        history.addWidget(undo)
        history.addWidget(redo)
        self.controls_layout.addLayout(history)

        self.finish_button = QPushButton()
        self.finish_button.setObjectName("primary")
        self.finish_button.clicked.connect(self.finish_current)
        self.controls_layout.addWidget(self.finish_button)
        self._refresh_finish_button()

    @staticmethod
    def _scroll_tab():
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll, layout

    def _build_file_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "File")

        manage = QGroupBox("Manage Data")
        manage_layout = QVBoxLayout(manage)
        self.file_combo = QComboBox()
        self.file_combo.addItems(self.stems)
        self.file_combo.currentTextChanged.connect(self._select_file)
        manage_layout.addWidget(self.file_combo)
        layout_form = QFormLayout()
        self.plot_layout_combo = QComboBox()
        for label, value in (
            ("Individual", "individual"), ("Overlay", "overlay"),
            ("Vertical stack", "stack"), ("Grid subplots", "grid"),
        ):
            self.plot_layout_combo.addItem(label, value)
        current_mode = state.settings.get("mode", "individual")
        index = self.plot_layout_combo.findData(current_mode)
        self.plot_layout_combo.setCurrentIndex(max(0, index))
        self.plot_layout_combo.currentIndexChanged.connect(self._plot_layout_changed)
        layout_form.addRow("Plot layout", self.plot_layout_combo)
        manage_layout.addLayout(layout_form)
        row = QHBoxLayout()
        for label, slot in (
            ("Add", self.add_files), ("Replace", self.replace_current), ("Remove", self.remove_current)
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            row.addWidget(button)
        manage_layout.addLayout(row)
        order = QGridLayout()
        for position, (label, direction) in enumerate((
            ("↑ Up", "up"), ("↓ Down", "down"),
            ("← Left", "left"), ("→ Right", "right"),
        )):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, step=direction: self.move_current_spatial(step)
            )
            order.addWidget(button, position // 2, position % 2)
        manage_layout.addLayout(order)
        layout.addWidget(manage)

        appearance = QGroupBox("Line & Processing")
        form = QFormLayout(appearance)
        self.name_edit = QLineEdit()
        form.addRow("Display name", self.name_edit)
        color_row = QWidget()
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_edit = QLineEdit()
        pick = QPushButton("Pick")
        pick.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_edit)
        color_layout.addWidget(pick)
        form.addRow("Color", color_row)
        palette = QWidget()
        palette_layout = QGridLayout(palette)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(3)
        for index, (name, value) in enumerate(BASIC_COLORS):
            swatch = QPushButton()
            swatch.setFixedSize(24, 24)
            swatch.setToolTip(name)
            swatch.setStyleSheet(
                f"background:{value}; border:1px solid #64748b; border-radius:4px; padding:0;"
            )
            swatch.clicked.connect(
                lambda _checked=False, selected=value: self.color_edit.setText(selected)
            )
            palette_layout.addWidget(swatch, index // 6, index % 6)
        form.addRow("Basic palette", palette)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e9, 1e9)
        self.offset_spin.setDecimals(5)
        form.addRow("Y offset", self.offset_spin)
        self.smooth_spin = QSpinBox()
        self.smooth_spin.setRange(0, 999)
        form.addRow("Smoothing points", self.smooth_spin)
        self.normalize_check = QCheckBox("Normalize")
        form.addRow(self.normalize_check)
        self.t2a_check = QCheckBox("Convert %T to absorbance")
        self.t2a_check.setVisible(state.technique == "FTIR")
        form.addRow(self.t2a_check)
        self.baseline_check = QCheckBox("Apply ALS baseline")
        form.addRow(self.baseline_check)
        self.als_spin = QDoubleSpinBox()
        self.als_spin.setRange(1.0, 14.0)
        self.als_spin.setDecimals(1)
        form.addRow("ALS stiffness (10^x)", self.als_spin)
        self.derivative_combo = QComboBox()
        self.derivative_combo.addItems(["None", "First", "Second"])
        form.addRow("Derivative", self.derivative_combo)
        self.clean_edges_check = QCheckBox("Trim unusually noisy spectrum ends")
        self.clean_edges_check.setVisible(state.technique in {"UVVIS", "RAMAN"})
        form.addRow(self.clean_edges_check)
        layout.addWidget(appearance)

        reference = QGroupBox("Reference Spectrum Subtraction")
        reference_form = QFormLayout(reference)
        self.reference_check = QCheckBox("Subtract a reference file")
        reference_form.addRow(self.reference_check)
        reference_row = QWidget()
        reference_layout = QHBoxLayout(reference_row)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self.reference_edit = QLineEdit()
        self.reference_edit.setReadOnly(True)
        browse_reference = QPushButton("Browse")
        browse_reference.clicked.connect(self.load_reference_file)
        reference_layout.addWidget(self.reference_edit)
        reference_layout.addWidget(browse_reference)
        reference_form.addRow("Reference", reference_row)
        self.reference_multiplier = QDoubleSpinBox()
        self.reference_multiplier.setRange(-1e9, 1e9)
        self.reference_multiplier.setDecimals(5)
        self.reference_multiplier.setValue(1.0)
        reference_form.addRow("Multiplier", self.reference_multiplier)
        layout.addWidget(reference)

        buttons = QHBoxLayout()
        apply_button = QPushButton("Apply")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self.save_and_update)
        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self.reset_file_settings)
        buttons.addWidget(apply_button)
        buttons.addWidget(reset_button)
        layout.addLayout(buttons)
        apply_all = QPushButton("Apply processing to all files")
        apply_all.clicked.connect(self.apply_to_all)
        layout.addWidget(apply_all)

    def _build_axes_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Axes")
        group = QGroupBox("Global Axes")
        form = QFormLayout(group)
        self.xlabel_edit = QLineEdit()
        self.ylabel_edit = QLineEdit()
        self.title_edit = QLineEdit()
        self.xlim_edit = QLineEdit()
        self.ylim_edit = QLineEdit()
        self.xstep_edit = QLineEdit()
        self.ystep_edit = QLineEdit()
        form.addRow("X label", self.xlabel_edit)
        form.addRow("Y label", self.ylabel_edit)
        form.addRow("Title", self.title_edit)
        form.addRow("X limits (min,max)", self.xlim_edit)
        form.addRow("Y limits (min,max)", self.ylim_edit)
        form.addRow("X tick step", self.xstep_edit)
        form.addRow("Y tick step", self.ystep_edit)
        self.minor_check = QCheckBox("Show minor ticks")
        self.tick_labels_check = QCheckBox("Show tick labels")
        form.addRow(self.minor_check)
        form.addRow(self.tick_labels_check)
        layout.addWidget(group)
        legend = QGroupBox("Legend")
        legend_form = QFormLayout(legend)
        self.legend_check = QCheckBox("Show legend")
        self.legend_location = QComboBox()
        for label, value in LEGEND_LOCATIONS:
            self.legend_location.addItem(label, value)
        self.legend_size = QDoubleSpinBox()
        self.legend_size.setRange(4, 48)
        self.legend_size.setValue(9)
        self.legend_color = QLineEdit("#172033")
        legend_color_row = QWidget()
        legend_color_layout = QHBoxLayout(legend_color_row)
        legend_color_layout.setContentsMargins(0, 0, 0, 0)
        legend_color_layout.addWidget(self.legend_color)
        legend_color_button = QPushButton("Pick")
        legend_color_button.clicked.connect(self.choose_legend_color)
        legend_color_layout.addWidget(legend_color_button)
        legend_form.addRow(self.legend_check)
        legend_form.addRow("Position", self.legend_location)
        legend_form.addRow("Font size", self.legend_size)
        legend_form.addRow("Font color", legend_color_row)
        layout.addWidget(legend)
        apply_button = QPushButton("Apply axes settings")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self.save_and_update)
        layout.addWidget(apply_button)

    def _build_annotation_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Annotate")
        tools = QGroupBox("Drawing Tool")
        tools_layout = QVBoxLayout(tools)
        self.annotation_tool = AnnotationToolBar()
        self.annotation_tool.currentIndexChanged.connect(self._set_annotation_tool)
        tools_layout.addWidget(self.annotation_tool)
        tools_layout.addWidget(QLabel("Draw on the graph. Use arrow keys to nudge a selection."))
        layout.addWidget(tools)

        props = QGroupBox("Selected Object")
        form = QFormLayout(props)
        text_widget = QWidget()
        text_layout = QHBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.ann_text_edit = QLineEdit()
        rich_edit = QPushButton("Rich Edit")
        rich_edit.clicked.connect(self._edit_rich_annotation)
        text_layout.addWidget(self.ann_text_edit)
        text_layout.addWidget(rich_edit)
        color_widget = QWidget()
        color_layout = QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.ann_color_edit = QLineEdit("black")
        color_button = QPushButton("Pick")
        color_button.clicked.connect(self._choose_annotation_color)
        color_layout.addWidget(self.ann_color_edit)
        color_layout.addWidget(color_button)
        self.ann_width_spin = QDoubleSpinBox()
        self.ann_width_spin.setRange(0.1, 20)
        self.ann_width_spin.setValue(2.0)
        self.ann_size_spin = QDoubleSpinBox()
        self.ann_size_spin.setRange(4, 100)
        self.ann_size_spin.setValue(12)
        self.ann_bold_check = QCheckBox("Bold")
        self.ann_italic_check = QCheckBox("Italic")
        self.ann_underline_check = QCheckBox("Underline")
        self.ann_family_combo = QComboBox()
        self.ann_family_combo.addItems(["sans-serif", "serif", "monospace", "cursive", "fantasy"])
        self.ann_alpha_spin = QDoubleSpinBox()
        self.ann_alpha_spin.setRange(0.0, 1.0)
        self.ann_alpha_spin.setSingleStep(0.1)
        self.ann_alpha_spin.setValue(1.0)
        form.addRow("Text", text_widget)
        form.addRow("Color", color_widget)
        form.addRow("Line width", self.ann_width_spin)
        form.addRow("Font size", self.ann_size_spin)
        form.addRow("Font family", self.ann_family_combo)
        form.addRow("Opacity", self.ann_alpha_spin)
        form.addRow(self.ann_bold_check)
        form.addRow(self.ann_italic_check)
        form.addRow(self.ann_underline_check)
        apply_props = QPushButton("Apply properties")
        apply_props.clicked.connect(self._apply_annotation_properties)
        delete = QPushButton("⌫ Delete selected")
        delete.clicked.connect(self._delete_annotation)
        form.addRow(apply_props)
        form.addRow(delete)
        layout.addWidget(props)
        self.annotation_list = QListWidget()
        self.annotation_list.currentRowChanged.connect(self._select_annotation_row)
        layout.addWidget(self.annotation_list)
        history = QGridLayout()
        undo = QPushButton("↶ Undo")
        undo.clicked.connect(lambda: self.annotation_mgr.undo())
        redo = QPushButton("↷ Redo")
        redo.clicked.connect(lambda: self.annotation_mgr.redo())
        clear_all = QPushButton("🗑 Clear all annotations")
        clear_all.clicked.connect(self._clear_all_annotations)
        history.addWidget(undo, 0, 0)
        history.addWidget(redo, 0, 1)
        history.addWidget(clear_all, 1, 0, 1, 2)
        layout.addLayout(history)

    def _build_analysis_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Analyze")
        interactive = QGroupBox("Interactive Tools")
        form = QFormLayout(interactive)
        self.click_mode = QComboBox()
        self.click_mode.addItem("Navigation", "none")
        if state.technique == "XRD":
            self.click_mode.addItem("Pick XRD peak", "xrd_peak")
        elif state.technique in {"GENERAL", "UVVIS", "RAMAN"}:
            self.click_mode.addItem("Pick point", "peak")
        else:
            self.click_mode.addItem("Pick FT-IR peak", "peak")
        self.click_mode.addItem("Calculate area", "area")
        self.click_mode.addItem("Draw manual baseline", "baseline")
        if state.technique in {"FTIR", "UVVIS", "RAMAN"}:
            self.click_mode.addItem("Peak deconvolution", "deconv")
        self.click_mode.currentIndexChanged.connect(self._click_mode_changed)
        form.addRow("Canvas mode", self.click_mode)
        self.prominence_spin = QDoubleSpinBox()
        self.prominence_spin.setRange(0, 1e9)
        self.prominence_spin.setDecimals(4)
        self.prominence_spin.setValue(10.2)
        form.addRow("Peak prominence", self.prominence_spin)
        self.xrd_height_spin = QDoubleSpinBox()
        self.xrd_height_spin.setRange(-1e9, 1e9)
        self.xrd_height_spin.setValue(5.0)
        self.xrd_height_spin.setVisible(state.technique == "XRD")
        self.xrd_height_label = QLabel("XRD minimum height")
        self.xrd_height_label.setVisible(state.technique == "XRD")
        form.addRow(self.xrd_height_label, self.xrd_height_spin)
        self.show_fwhm_check = QCheckBox("Show FWHM and grain size")
        self.show_fwhm_check.setChecked(True)
        self.show_fwhm_check.setVisible(state.technique == "XRD")
        self.show_fwhm_check.toggled.connect(self.update_plot)
        form.addRow(self.show_fwhm_check)
        layout.addWidget(interactive)

        row = QHBoxLayout()
        find_button = QPushButton("Auto-find peaks")
        find_button.clicked.connect(self.auto_find_peaks)
        baseline_button = QPushButton("Apply baseline")
        baseline_button.clicked.connect(self.apply_manual_baseline)
        row.addWidget(find_button)
        row.addWidget(baseline_button)
        layout.addLayout(row)
        clear_baseline = QPushButton("Clear manual baseline")
        clear_baseline.clicked.connect(self.clear_manual_baseline)
        layout.addWidget(clear_baseline)
        if state.technique in {"FTIR", "UVVIS", "RAMAN"}:
            clear_fit = QPushButton("Clear deconvolution fit")
            clear_fit.clicked.connect(self.clear_deconvolution)
            layout.addWidget(clear_fit)

        self.peak_list = QListWidget()
        layout.addWidget(self.peak_list)
        peak_row = QHBoxLayout()
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self.delete_selected_peak)
        clear = QPushButton("Clear analysis")
        clear.clicked.connect(self.clear_peaks)
        peak_row.addWidget(delete)
        peak_row.addWidget(clear)
        layout.addLayout(peak_row)

        if state.technique == "XRD":
            chart = QPushButton("Grain-size chart")
            chart.clicked.connect(self.show_grain_size_chart)
            layout.addWidget(chart)
        elif state.technique == "FTIR":
            cheat = QPushButton("FT-IR functional-group cheat sheet")
            cheat.clicked.connect(self.show_cheat_sheet)
            layout.addWidget(cheat)
        elif state.technique == "UVVIS":
            advanced = QPushButton("UV-Vis band-gap and Urbach analysis")
            advanced.clicked.connect(self.show_uvvis_analysis)
            layout.addWidget(advanced)
        elif state.technique == "RAMAN":
            advanced = QPushButton("Raman peak measurements and ratios")
            advanced.clicked.connect(self.show_raman_analysis)
            layout.addWidget(advanced)

        export = QPushButton("Export data, report and graph")
        export.clicked.connect(self.export_data)
        save = QPushButton("Save workspace session")
        save.clicked.connect(lambda: self.save_session(save_as=True))
        layout.addWidget(export)
        layout.addWidget(save)

    def _connect_canvas(self):
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("pick_event", self._plot_artist_picked)
        self.canvas.mpl_connect("button_press_event", lambda _event: self.canvas.setFocus())

    def _state_snapshot(self):
        return {
            "file_set": copy.deepcopy(state.file_set),
            "global_set": copy.deepcopy(state.global_set),
            "mode": state.settings.get("mode", "individual"),
            "stems": list(self.stems),
            "data_dict": copy.deepcopy(self.data_dict),
            "all_data": copy.deepcopy(state.all_data),
        }

    def _checkpoint_state(self):
        snapshot = self._state_snapshot()
        self._state_undo.append(snapshot)
        del self._state_undo[:-100]
        self._state_redo.clear()

    def _restore_state(self, snapshot):
        state.file_set = copy.deepcopy(snapshot["file_set"])
        state.global_set = copy.deepcopy(snapshot["global_set"])
        state.settings["mode"] = snapshot["mode"]
        self.data_dict = copy.deepcopy(snapshot["data_dict"])
        state.all_data = copy.deepcopy(snapshot["all_data"])
        self.stems = list(snapshot["stems"])
        if self.current_stem not in self.stems:
            self.current_stem = self.stems[0]
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(self.stems)
        self.file_combo.setCurrentText(self.current_stem)
        self.file_combo.blockSignals(False)
        self.plot_layout_combo.blockSignals(True)
        index = self.plot_layout_combo.findData(state.settings["mode"])
        self.plot_layout_combo.setCurrentIndex(max(0, index))
        self.plot_layout_combo.blockSignals(False)
        self._load_active_settings()
        self.update_plot()

    def _undo_active(self):
        if self.tabs.currentWidget() is self.tabs.widget(2) and self.annotation_mgr.undo():
            return
        if self._state_undo:
            self._state_redo.append(self._state_snapshot())
            self._restore_state(self._state_undo.pop())

    def _redo_active(self):
        if self.tabs.currentWidget() is self.tabs.widget(2) and self.annotation_mgr.redo():
            return
        if self._state_redo:
            self._state_undo.append(self._state_snapshot())
            self._restore_state(self._state_redo.pop())

    def _delete_active(self):
        if self.tabs.currentWidget() is self.tabs.widget(2):
            self._delete_annotation()
        elif self.tabs.currentWidget() is self.tabs.widget(3):
            self.delete_selected_peak()

    def _plot_layout_changed(self):
        mode = self.plot_layout_combo.currentData()
        if not mode or mode == state.settings.get("mode"):
            return
        if mode == "individual" and len(self.stems) > 1:
            QMessageBox.information(
                self, "Individual windows",
                "Individual mode is chosen before launch. Use Overlay, Vertical stack, or Grid here.",
            )
            self.plot_layout_combo.blockSignals(True)
            index = self.plot_layout_combo.findData(state.settings.get("mode", "overlay"))
            self.plot_layout_combo.setCurrentIndex(max(0, index))
            self.plot_layout_combo.blockSignals(False)
            return
        self._checkpoint_state()
        state.settings["mode"] = mode
        self.update_plot()

    # ---------------------------- settings ------------------------------
    def _load_active_settings(self):
        fs = state.file_set.setdefault(self.current_stem, {})
        als_value = float(fs.get("als_lam", 8.0))
        if als_value > 14:
            # Older sessions sometimes stored lambda itself; Version 3 stores
            # its base-10 exponent, matching processing.process_spectrum().
            als_value = float(np.log10(als_value))
            fs["als_lam"] = als_value
        self.name_edit.setText(str(fs.get("custom_name", self.current_stem)))
        self.color_edit.setText(str(fs.get("color", "black")))
        self.offset_spin.setValue(float(fs.get("offset", 0.0)))
        self.smooth_spin.setValue(int(fs.get("smooth", state.settings.get("smooth", 15))))
        self.normalize_check.setChecked(bool(fs.get("normalize", False)))
        self.t2a_check.setChecked(bool(fs.get("t2a", False)))
        self.baseline_check.setChecked(bool(fs.get("do_baseline", False)))
        self.als_spin.setValue(als_value)
        self.derivative_combo.setCurrentIndex(int(fs.get("derivative", 0)))
        self.clean_edges_check.setChecked(bool(fs.get("auto_clean_edges", False)))
        self.reference_check.setChecked(bool(fs.get("bg_sub", False)))
        self.reference_edit.setText(str(fs.get("bg_filename", "")))
        self.reference_multiplier.setValue(float(fs.get("bg_mult", 1.0)))
        self.xlabel_edit.setText(str(state.global_set.get("xlabel", "")))
        self.ylabel_edit.setText(str(state.global_set.get("ylabel", "")))
        self.title_edit.setText(str(state.global_set.get("title", "")))
        self.xlim_edit.setText(_format_limits(state.global_set.get("xlim")))
        self.ylim_edit.setText(_format_limits(state.global_set.get("ylim")))
        self.xstep_edit.setText(str(state.global_set.get("xstep", "")))
        self.ystep_edit.setText(str(state.global_set.get("ystep", "")))
        self.minor_check.setChecked(bool(state.global_set.get("show_minor", False)))
        self.tick_labels_check.setChecked(bool(state.global_set.get("show_tick_lbls", True)))
        self.legend_check.setChecked(bool(state.global_set.get("show_legend", True)))
        legend_index = self.legend_location.findData(
            state.global_set.get("legend_location", "best")
        )
        self.legend_location.setCurrentIndex(max(0, legend_index))
        self.legend_size.setValue(float(state.global_set.get("legend_fontsize", 9)))
        self.legend_color.setText(str(state.global_set.get("legend_color", "#172033")))
        self.sync_peak_list()

    def save_and_update(self):
        self._checkpoint_state()
        fs = state.file_set[self.current_stem]
        fs.update(
            custom_name=self.name_edit.text().strip() or self.current_stem,
            color=self.color_edit.text().strip() or "black",
            offset=self.offset_spin.value(),
            smooth=self.smooth_spin.value(),
            normalize=self.normalize_check.isChecked(),
            t2a=self.t2a_check.isChecked(),
            do_baseline=self.baseline_check.isChecked(),
            als_lam=self.als_spin.value(),
            derivative=self.derivative_combo.currentIndex(),
            auto_clean_edges=self.clean_edges_check.isChecked(),
            bg_sub=self.reference_check.isChecked(),
            bg_filename=self.reference_edit.text(),
            bg_mult=self.reference_multiplier.value(),
        )
        gs = state.global_set
        gs.update(
            xlabel=self.xlabel_edit.text(), ylabel=self.ylabel_edit.text(),
            title=self.title_edit.text(), xlim=_parse_limits(self.xlim_edit.text()),
            ylim=_parse_limits(self.ylim_edit.text()), xstep=self.xstep_edit.text(),
            ystep=self.ystep_edit.text(), show_minor=self.minor_check.isChecked(),
            show_tick_lbls=self.tick_labels_check.isChecked(),
            show_legend=self.legend_check.isChecked(),
            legend_location=self.legend_location.currentData() or "best",
            legend_fontsize=self.legend_size.value(),
            legend_color=self.legend_color.text().strip() or "#172033",
        )
        self.update_plot()

    def apply_to_all(self):
        self.save_and_update()
        source = state.file_set[self.current_stem]
        keys = (
            "smooth", "do_baseline", "normalize", "derivative", "als_lam",
            "als_p", "t2a", "offset", "auto_clean_edges",
        )
        for stem in self.stems:
            for key in keys:
                state.file_set[stem][key] = source.get(key)
        self.update_plot()
        QMessageBox.information(self, "Settings Applied", "Processing settings were applied to all files.")

    def reset_file_settings(self):
        self.offset_spin.setValue(0)
        self.smooth_spin.setValue(15)
        self.normalize_check.setChecked(False)
        self.t2a_check.setChecked(False)
        self.baseline_check.setChecked(state.technique == "RAMAN")
        self.als_spin.setValue(8.0)
        self.derivative_combo.setCurrentIndex(0)
        self.clean_edges_check.setChecked(state.technique in {"UVVIS", "RAMAN"})
        self.reference_check.setChecked(False)
        self.reference_edit.clear()
        self.reference_multiplier.setValue(1.0)
        fs = state.file_set[self.current_stem]
        for key in ("manual_baseline_pts", "labels", "areas", "deconvs", "xrd_peaks"):
            fs[key] = []
        self.save_and_update()

    def load_reference_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select reference spectrum",
            "",
            "Data files (*.dpt *.csv *.txt *.xy *.dat *.xlsx);;All files (*)",
        )
        if not filename:
            return
        try:
            x, y = robust_read_spectrum(filename)
            if len(x) <= 10:
                raise ValueError("The reference file did not contain enough numeric data")
        except Exception as error:
            QMessageBox.critical(self, "Reference Error", str(error))
            return
        fs = state.file_set[self.current_stem]
        self._checkpoint_state()
        fs["bg_data"] = (x, y)
        fs["bg_filename"] = Path(filename).name
        self.reference_edit.setText(Path(filename).name)
        self.reference_check.setChecked(True)
        self.save_and_update()

    def choose_color(self):
        initial = QColor(self.color_edit.text())
        color = QColorDialog.getColor(initial, self, "Choose line color")
        if color.isValid():
            self.color_edit.setText(color.name())

    def choose_legend_color(self):
        color = QColorDialog.getColor(QColor(self.legend_color.text()), self, "Legend font color")
        if color.isValid():
            self.legend_color.setText(color.name())

    def _select_file(self, stem):
        if stem and stem in self.data_dict:
            self.current_stem = stem
            self._load_active_settings()
            self.update_plot()

    # ------------------------------- data --------------------------------
    def get_processed_data_for_stem(self, stem):
        raw_x, raw_y = self.data_dict[stem]
        fs = state.file_set[stem]
        x_arr = np.asarray(raw_x, dtype=float)
        y_arr = np.asarray(raw_y, dtype=float).copy()

        if fs.get("t2a", False):
            y_arr = 2 - np.log10(np.clip(y_arr, 0.0001, None))
        if fs.get("bg_sub", False) and "bg_data" in fs:
            bg_x, bg_y = fs["bg_data"]
            y_arr = subtract_reference(
                x_arr, y_arr, bg_x, bg_y, fs.get("bg_mult", 1.0)
            )
        try:
            x, y = process_spectrum(x_arr, y_arr, stem)
        except Exception:
            x, y = x_arr, y_arr
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        manual = fs.get("manual_baseline_pts", [])
        if len(manual) >= 2:
            points = np.asarray(manual, dtype=float)
            order = np.argsort(points[:, 0])
            y_arr -= np.interp(x_arr, points[order, 0], points[order, 1])
        if fs.get("normalize", False):
            low, high = np.min(y_arr), np.max(y_arr)
            if high != low:
                target = 1.0 if fs.get("t2a", False) else 100.0
                y_arr = (y_arr - low) / (high - low) * target
        y_arr += float(fs.get("offset", 0.0))
        if fs.get("auto_clean_edges", False) and state.technique in {"UVVIS", "RAMAN"}:
            x_arr, y_arr = trim_noisy_edges(x_arr, y_arr)
        return x_arr, y_arr

    def _init_file_settings(self, stem):
        index = len(state.file_set)
        state.file_set[stem] = {
            "custom_name": stem, "color": PLOT_COLORS[index % len(PLOT_COLORS)], "offset": 0.0,
            "smooth": state.settings.get("smooth", 15), "labels": [], "areas": [],
            "do_baseline": state.technique == "RAMAN", "als_lam": 8.0, "als_p": 0.05,
            "auto_clean_edges": state.technique in {"UVVIS", "RAMAN"},
        }

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add data files", "", "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.xlsx *.xls);;All files (*)"
        )
        if not paths:
            return
        datasets, failures = discover_many(paths, minimum_points=11)
        if not datasets:
            details = "\n".join(f"{name}: {reason}" for name, reason in failures)
            QMessageBox.warning(self, "Files skipped", details or "No X/Y datasets were found.")
            return
        from qt_setup import DatasetSelectionDialog
        picker = DatasetSelectionDialog(datasets, self, existing_count=len(self.stems))
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        self._checkpoint_state()
        previous_mode = state.settings.get("mode", "individual")
        if len(picker.selected) > 1 or len(self.stems) > 0:
            state.settings["mode"] = picker.mode
            index = self.plot_layout_combo.findData(state.settings["mode"])
            self.plot_layout_combo.blockSignals(True)
            self.plot_layout_combo.setCurrentIndex(index)
            self.plot_layout_combo.blockSignals(False)
        if previous_mode == "individual" and state.settings.get("mode") != "individual":
            state.mode_switched_mid_session = True
            self._refresh_finish_button()
        for dataset in picker.selected:
            x, y = dataset.x, dataset.y
            stem = _unique_stem(Path(dataset.name), self.stems)
            self.stems.append(stem)
            self.data_dict[stem] = (x, y)
            state.all_data.append((stem, x, y))
            self._init_file_settings(stem)
            if picker.reference_dataset is not None:
                state.file_set[stem].update(
                    bg_sub=True,
                    bg_filename=picker.reference_dataset.name,
                    bg_data=(picker.reference_dataset.x, picker.reference_dataset.y),
                    bg_mult=1.0,
                )
            self.file_combo.addItem(stem)
        if failures:
            QMessageBox.warning(
                self, "Some files skipped",
                "\n".join(f"{name}: {reason}" for name, reason in failures),
            )
        self.update_plot()

    def replace_current(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Replace current data", "", "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.xlsx *.xls);;All files (*)"
        )
        if not path:
            return
        if state.technique == "GENERAL" and not self._ensure_general_format(Path(path)):
            return
        try:
            x, y = self._read_data_file(Path(path))
            if len(x) <= 10:
                raise ValueError("The file did not contain enough numeric data")
        except Exception as error:
            QMessageBox.critical(self, "Read Error", str(error))
            return
        self.data_dict[self.current_stem] = (x, y)
        state.all_data = [
            (item[0], x, y) if item[0] == self.current_stem else item
            for item in state.all_data
        ]
        fs = state.file_set[self.current_stem]
        for key in ("labels", "areas", "deconvs", "xrd_peaks", "manual_baseline_pts"):
            fs[key] = []
        self.update_plot()

    def _read_data_file(self, path):
        if state.technique != "GENERAL":
            return robust_read_spectrum(path)
        configuration = state.general_format or state.settings.get("general_format")
        if not configuration:
            raise ValueError("General Plotter column configuration is missing")
        return read_generic_configured(path, **configuration)

    def _ensure_general_format(self, sample_path):
        if state.general_format or state.settings.get("general_format"):
            return True
        from qt_setup import ColumnPickerDialog
        picker = ColumnPickerDialog(sample_path, self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return False
        state.general_format = picker.result
        state.settings["general_format"] = picker.result
        return True

    def remove_current(self):
        if len(self.stems) <= 1:
            QMessageBox.warning(self, "Cannot Remove", "At least one file must remain open.")
            return
        answer = QMessageBox.question(self, "Remove File", f"Remove '{self.current_stem}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._checkpoint_state()
        stem = self.current_stem
        index = self.stems.index(stem)
        self.stems.remove(stem)
        self.data_dict.pop(stem, None)
        state.file_set.pop(stem, None)
        state.all_data = [item for item in state.all_data if item[0] != stem]
        self.file_combo.removeItem(index)
        self.current_stem = self.file_combo.currentText()
        self._load_active_settings()
        self.update_plot()

    def move_current(self, direction):
        old = self.stems.index(self.current_stem)
        new = old + direction
        if not 0 <= new < len(self.stems):
            return
        self._checkpoint_state()
        self.stems[old], self.stems[new] = self.stems[new], self.stems[old]
        state.all_data.sort(key=lambda item: self.stems.index(item[0]))
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(self.stems)
        self.file_combo.setCurrentText(self.current_stem)
        self.file_combo.blockSignals(False)
        self.update_plot()

    def move_current_spatial(self, direction):
        """Reorder row-major grid cells or the linear stack/overlay order."""
        if state.settings.get("mode") == "grid":
            columns = max(1, int(math.ceil(math.sqrt(len(self.stems)))))
            current = self.stems.index(self.current_stem)
            if direction == "left" and current % columns == 0:
                return
            if direction == "right" and (
                current % columns == columns - 1 or current + 1 >= len(self.stems)
            ):
                return
            step = {"left": -1, "right": 1, "up": -columns, "down": columns}[direction]
        else:
            step = -1 if direction in {"left", "up"} else 1
        self.move_current(step)

    # ------------------------------ plotting -----------------------------
    def update_plot(self):
        annotations = None
        if hasattr(self, "annotation_mgr"):
            annotations = self.annotation_mgr.get_serialized_data() or self._pending_annotations
            self.annotation_mgr._remove_handles()
            self.annotation_mgr.annotations = []
            self.annotation_mgr.selected_artist = None
            self._pending_annotations = []

        self.figure.clear()
        self.cursors = []
        self._artist_to_stem = {}
        self._axes_to_stem = {}
        mode = state.settings.get("mode", "individual")
        is_stack = mode in {"stack", "grid"}
        if mode == "stack":
            axes_value = self.figure.subplots(len(self.stems), 1, sharex=True)
            axes = list(np.atleast_1d(axes_value).flat)
        elif mode == "grid":
            columns = max(1, int(math.ceil(math.sqrt(len(self.stems)))))
            rows = int(math.ceil(len(self.stems) / columns))
            axes_value = self.figure.subplots(rows, columns, squeeze=False)
            all_axes = list(np.asarray(axes_value).flat)
            axes = all_axes[:len(self.stems)]
            for unused in all_axes[len(self.stems):]:
                unused.set_visible(False)
        else:
            axes = [self.figure.add_subplot(111)] * len(self.stems)

        extents = []
        for index, stem in enumerate(self.stems):
            ax = axes[index]
            if is_stack:
                self._axes_to_stem[ax] = stem
            fs = state.file_set[stem]
            x, y = self.get_processed_data_for_stem(stem)
            if not len(x):
                continue
            extents.append((np.min(x), np.max(x), np.min(y), np.max(y)))
            color = fs.get("color", "black")
            line = ax.plot(
                x, y, label=fs.get("custom_name", stem), color=color,
                linewidth=2.4 if stem == self.current_stem else 1.5,
                picker=6,
            )[0]
            self._artist_to_stem[line] = stem
            for px, py, text_value in fs.get("labels", []):
                ax.plot(px, py, "v", color=color, markersize=6)
                ax.annotate(text_value, (px, py), xytext=(0, -20), textcoords="offset points", ha="center")
            for px, py, fwhm, size in fs.get("xrd_peaks", []):
                label = f"2θ: {px:.1f}°"
                if self.show_fwhm_check.isChecked():
                    label += f"\nFWHM: {fwhm:.2f}°\nD: {size:.1f} nm"
                ax.plot(px, py, "o", color=color, markersize=5)
                ax.annotate(label, (px, py), xytext=(0, 10), textcoords="offset points", ha="center")
            for x1, x2, area in fs.get("areas", []):
                mask = (x >= x1) & (x <= x2)
                x_sel, y_sel = x[mask], y[mask]
                if len(x_sel) > 1:
                    order = np.argsort(x_sel)
                    x_sel, y_sel = x_sel[order], y_sel[order]
                    base = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
                    ax.fill_between(x_sel, y_sel, base, color=color, alpha=0.35)
                    mid = len(x_sel) // 2
                    ax.text(x_sel[mid], y_sel[mid], f"Area: {area:.1f}", ha="center")
            self._plot_deconvolutions(ax, x, y, fs)
            if is_stack:
                span = np.max(y) - np.min(y)
                margin = span * 0.05 if span else 1.0
                ax.set_ylim(np.min(y) - margin, np.max(y) + margin)
                active_color = "#2563eb" if stem == self.current_stem else "#94a3b8"
                active_width = 2.0 if stem == self.current_stem else 0.8
                for spine in ax.spines.values():
                    spine.set_edgecolor(active_color)
                    spine.set_linewidth(active_width)

        unique_axes = list(dict.fromkeys(axes))
        if extents:
            for ax in unique_axes:
                self._style_axis(ax, extents, is_stack)
        if state.global_set.get("show_legend", True):
            legend_axes = [axes[0]] if mode == "overlay" else unique_axes
            for ax in legend_axes:
                legend = ax.legend(
                    loc=state.global_set.get("legend_location", "best"),
                    fontsize=float(state.global_set.get("legend_fontsize", 9)),
                )
                if legend is not None:
                    legend.set_draggable(True)
                    for text_artist in legend.get_texts():
                        text_artist.set_color(state.global_set.get("legend_color", "#172033"))
        self.ax = axes[0] if axes else None

        if hasattr(self, "annotation_mgr") and annotations and self.ax is not None:
            self.annotation_mgr.load_serialized_data(annotations, self.ax)
        elif hasattr(self, "annotation_mgr"):
            self.annotation_mgr.active_ax = self.ax

        try:
            self.figure.tight_layout()
        except ValueError:
            pass
        self.canvas.draw_idle()
        self.sync_peak_list()

    def _style_axis(self, ax, extents, is_stack):
        gs = state.global_set
        min_x = min(item[0] for item in extents)
        max_x = max(item[1] for item in extents)
        min_y = min(item[2] for item in extents)
        max_y = max(item[3] for item in extents)
        xlim = gs.get("xlim") or [min_x, max_x]
        if state.technique == "FTIR":
            ax.set_xlim(max(xlim), min(xlim))
        else:
            ax.set_xlim(min(xlim), max(xlim))
        if gs.get("ylim"):
            ax.set_ylim(min(gs["ylim"]), max(gs["ylim"]))
        elif not is_stack:
            margin = (max_y - min_y) * 0.05 or 1.0
            ax.set_ylim(min_y - margin, max_y + margin)
        try:
            if gs.get("xstep"):
                from matplotlib.ticker import MultipleLocator
                ax.xaxis.set_major_locator(MultipleLocator(float(gs["xstep"])))
            if gs.get("ystep"):
                from matplotlib.ticker import MultipleLocator
                ax.yaxis.set_major_locator(MultipleLocator(float(gs["ystep"])))
        except ValueError:
            pass
        if gs.get("show_minor"):
            ax.minorticks_on()
        else:
            ax.minorticks_off()
        ax.tick_params(labelbottom=gs.get("show_tick_lbls", True), labelleft=gs.get("show_tick_lbls", True))
        ax.set_title(gs.get("title", ""), fontweight="bold")
        ax.set_xlabel(gs.get("xlabel", ""), fontweight="bold")
        ax.set_ylabel(gs.get("ylabel", ""), fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.2)
        cursor = Cursor(ax, useblit=True, color="red", linewidth=1, linestyle="dotted")
        cursor.visible = self.click_mode.currentData() != "none"
        self.cursors.append(cursor)

    def _plot_deconvolutions(self, ax, x, _y, fs):
        for item in fs.get("deconvs", []):
            if len(item) == 6:
                x1, x2, baseline, params, count, is_valley = item
            else:
                x1, x2, baseline, params, count = item
                is_valley = False
            mask = (x >= x1) & (x <= x2)
            x_sel = x[mask]
            if not len(x_sel):
                continue
            baseline_arr = np.asarray(baseline)
            if len(baseline_arr) != len(x_sel):
                baseline_arr = np.interp(x_sel, [x_sel[0], x_sel[-1]], [baseline_arr[0], baseline_arr[-1]])
            total = np.zeros_like(x_sel)
            sign = -1 if is_valley else 1
            for index in range(0, len(params), 3):
                amp, center, sigma = params[index:index + 3]
                peak = amp * np.exp(-((x_sel - center) ** 2) / (2 * sigma ** 2))
                total += peak
                ax.plot(x_sel, baseline_arr + sign * peak, "--", alpha=0.8)
            ax.plot(x_sel, baseline_arr + sign * total, "r:", linewidth=2, label=f"Fit ({count} peaks)")

    def on_mouse_move(self, event):
        if event.inaxes is not None and event.xdata is not None and event.ydata is not None:
            self.cursor_label.setText(f"X: {event.xdata:.2f} | Y: {event.ydata:.2f}")
        else:
            self.cursor_label.setText("X: -- | Y: --")

    # ------------------------------ analysis -----------------------------
    def _click_mode_changed(self):
        if self.click_mode.currentData() != "none":
            self.annotation_tool.blockSignals(True)
            self.annotation_tool.setCurrentIndex(0)
            self.annotation_tool.blockSignals(False)
        self.annotation_mgr.set_tool("none")
        self.area_start = None
        self.deconv_start = None
        self.update_plot()

    def on_click(self, event):
        mode = self.click_mode.currentData()
        if mode == "none":
            stem = self._axes_to_stem.get(event.inaxes)
            if stem and stem != self.current_stem and self.annotation_mgr.active_tool == "none":
                self.file_combo.setCurrentText(stem)
            return
        if event.inaxes is None or event.xdata is None:
            return
        x, y = self.get_processed_data_for_stem(self.current_stem)
        index = int(np.abs(x - event.xdata).argmin())
        closest_x, closest_y = x[index], y[index]
        fs = state.file_set[self.current_stem]
        if mode == "peak":
            self._checkpoint_state()
            fs.setdefault("labels", []).append((closest_x, closest_y, f"{closest_x:.1f}"))
            self.update_plot()
        elif mode == "xrd_peak":
            result = self.calculate_xrd_peak(event.xdata, x, y)
            if result:
                self._checkpoint_state()
                fs.setdefault("xrd_peaks", []).append(result)
                self.update_plot()
        elif mode == "area":
            if self.area_start is None:
                self.area_start = closest_x
                event.inaxes.axvline(closest_x, color="gray", linestyle="--")
                self.canvas.draw_idle()
            else:
                x1, x2 = sorted((self.area_start, closest_x))
                mask = (x >= x1) & (x <= x2)
                x_sel, y_sel = x[mask], y[mask]
                if len(x_sel) > 1:
                    self._checkpoint_state()
                    order = np.argsort(x_sel)
                    x_sel, y_sel = x_sel[order], y_sel[order]
                    baseline = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
                    area = abs(np.trapezoid(y_sel - baseline, x_sel))
                    fs.setdefault("areas", []).append((x1, x2, area))
                self.area_start = None
                self.update_plot()
        elif mode == "baseline":
            self.baseline_pts.append((closest_x, closest_y))
            event.inaxes.plot(closest_x, closest_y, "go")
            if len(self.baseline_pts) > 1:
                points = sorted(self.baseline_pts)
                event.inaxes.plot([p[0] for p in points], [p[1] for p in points], "g--")
            self.canvas.draw_idle()
        elif mode == "deconv":
            if self.deconv_start is None:
                self.deconv_start = closest_x
                event.inaxes.axvline(closest_x, color="purple", linestyle="--")
                self.canvas.draw_idle()
            else:
                x1, x2 = sorted((self.deconv_start, closest_x))
                self.deconv_start = None
                self.perform_deconvolution(x1, x2, x, y)

    def _plot_artist_picked(self, event):
        stem = self._artist_to_stem.get(event.artist)
        if stem and stem != self.current_stem and self.annotation_mgr.active_tool == "none":
            self.file_combo.setCurrentText(stem)

    def apply_manual_baseline(self):
        if len(self.baseline_pts) < 2:
            QMessageBox.warning(self, "Baseline", "Click at least two baseline points first.")
            return
        self._checkpoint_state()
        state.file_set[self.current_stem]["manual_baseline_pts"] = list(self.baseline_pts)
        self.baseline_pts = []
        self.click_mode.setCurrentIndex(0)
        self.update_plot()

    def clear_manual_baseline(self):
        self._checkpoint_state()
        state.file_set[self.current_stem]["manual_baseline_pts"] = []
        self.baseline_pts = []
        self.update_plot()

    def clear_deconvolution(self):
        self._checkpoint_state()
        state.file_set[self.current_stem]["deconvs"] = []
        self.deconv_start = None
        self.update_plot()

    def auto_find_peaks(self):
        if state.technique == "XRD":
            self.auto_find_xrd_peaks()
            return
        x, y = self.get_processed_data_for_stem(self.current_stem)
        self._checkpoint_state()
        fs = state.file_set[self.current_stem]
        search_y = y if state.technique in {"GENERAL", "UVVIS", "RAMAN"} or fs.get("t2a", False) else -y
        peaks, _ = find_peaks(search_y, prominence=self.prominence_spin.value())
        existing = fs.setdefault("labels", [])
        for index in peaks:
            if not any(abs(item[0] - x[index]) < 0.1 for item in existing):
                existing.append((x[index], y[index], f"{x[index]:.1f}"))
        self.update_plot()

    def calculate_xrd_peak(self, x_click, x, y):
        mask = (x >= x_click - 1.0) & (x <= x_click + 1.0)
        if not np.any(mask):
            return None
        xw, yw = x[mask], y[mask]
        index = int(np.argmax(yw))
        peak_x, peak_y = xw[index], yw[index]
        half = peak_y / 2
        try:
            left = np.interp(half, yw[:index], xw[:index])
            right = np.interp(half, yw[index:][::-1], xw[index:][::-1])
            fwhm = abs(right - left)
        except (ValueError, IndexError):
            fwhm = 0.0
        size = 0.0
        if fwhm > 0:
            size = (0.9 * 0.15406) / (np.radians(fwhm) * np.cos(np.radians(peak_x / 2)))
        return peak_x, peak_y, fwhm, size

    def auto_find_xrd_peaks(self):
        self._checkpoint_state()
        x, y = self.get_processed_data_for_stem(self.current_stem)
        peaks, _ = find_peaks(
            y, height=self.xrd_height_spin.value(), prominence=self.prominence_spin.value()
        )
        results = state.file_set[self.current_stem].setdefault("xrd_peaks", [])
        for index in peaks:
            result = self.calculate_xrd_peak(x[index], x, y)
            if result and not any(abs(item[0] - result[0]) < 0.01 for item in results):
                results.append(result)
        self.update_plot()

    def perform_deconvolution(self, x1, x2, x, y):
        count, accepted = QInputDialog.getInt(
            self, "Deconvolution", "Expected sub-peaks:", 2, 1, 5
        )
        if not accepted:
            self.update_plot()
            return
        mask = (x >= x1) & (x <= x2)
        x_sel, y_sel = x[mask], y[mask]
        if len(x_sel) < 10:
            QMessageBox.warning(self, "Deconvolution", "Not enough data points in this region.")
            return
        baseline = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
        valley = y_sel[len(y_sel) // 2] < baseline[len(y_sel) // 2]
        y_fit = np.clip((baseline - y_sel) if valley else (y_sel - baseline), 0, None)

        def model(values, *params):
            result = np.zeros_like(values)
            for index in range(0, len(params), 3):
                amp, center, sigma = params[index:index + 3]
                result += amp * np.exp(-((values - center) ** 2) / (2 * sigma ** 2))
            return result

        width = x2 - x1
        amplitude = max(float(np.max(y_fit)), np.finfo(float).eps)
        spacing = width / (count + 1)
        guess, lower, upper = [], [], []
        for index in range(count):
            guess.extend([amplitude, x1 + spacing * (index + 1), width / (count * 2)])
            lower.extend([0, x1, 0.01])
            upper.extend([amplitude * 1.5, x2, width])
        try:
            params, _ = curve_fit(model, x_sel, y_fit, p0=guess, bounds=(lower, upper))
        except Exception as error:
            QMessageBox.critical(self, "Fitting Error", f"The fit did not converge:\n{error}")
            return
        self._checkpoint_state()
        state.file_set[self.current_stem].setdefault("deconvs", []).append(
            (x1, x2, baseline, params, count, valley)
        )
        self.click_mode.setCurrentIndex(0)
        self.update_plot()

    def show_uvvis_analysis(self):
        x, y = self.get_processed_data_for_stem(self.current_stem)
        dialog = UVVisAnalysisDialog(x, y, self.current_stem, self)
        dialog.exec()

    def show_raman_analysis(self):
        x, y = self.get_processed_data_for_stem(self.current_stem)
        dialog = RamanAnalysisDialog(x, y, self.current_stem, self)
        dialog.exec()

    def sync_peak_list(self):
        self.peak_list.clear()
        fs = state.file_set.get(self.current_stem, {})
        if state.technique == "XRD":
            for px, _py, fwhm, size in fs.get("xrd_peaks", []):
                self.peak_list.addItem(f"2θ {px:.2f}° | FWHM {fwhm:.2f}° | {size:.1f} nm")
        elif state.technique == "FTIR":
            for px, _py, text_value in fs.get("labels", []):
                self.peak_list.addItem(f"Peak {px:.1f} cm⁻¹ ({text_value})")
        else:
            for px, py, _text_value in fs.get("labels", []):
                self.peak_list.addItem(f"Point ({px:.5g}, {py:.5g})")
        for x1, x2, area in fs.get("areas", []):
            self.peak_list.addItem(f"Area {area:.3g} ({x1:.2f}–{x2:.2f})")

    def delete_selected_peak(self):
        row = self.peak_list.currentRow()
        if row < 0:
            return
        self._checkpoint_state()
        fs = state.file_set[self.current_stem]
        primary_key = "xrd_peaks" if state.technique == "XRD" else "labels"
        primary = fs.get(primary_key, [])
        if row < len(primary):
            primary.pop(row)
        else:
            area_index = row - len(primary)
            if area_index < len(fs.get("areas", [])):
                fs["areas"].pop(area_index)
        self.update_plot()

    def clear_peaks(self):
        self._checkpoint_state()
        fs = state.file_set[self.current_stem]
        for key in ("labels", "areas", "deconvs", "xrd_peaks"):
            fs[key] = []
        self.update_plot()

    # ---------------------------- annotations ----------------------------
    def _set_annotation_tool(self):
        if self.annotation_tool.currentData() != "none":
            self.click_mode.blockSignals(True)
            self.click_mode.setCurrentIndex(0)
            self.click_mode.blockSignals(False)
        self.annotation_mgr.set_tool(self.annotation_tool.currentData())

    def _request_annotation_text(self):
        dialog = TextAnnotationDialog(self)
        return dialog.result if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _choose_annotation_color(self):
        color = QColorDialog.getColor(
            QColor(self.ann_color_edit.text()), self, "Annotation Color"
        )
        if color.isValid():
            self.ann_color_edit.setText(color.name())

    def _edit_rich_annotation(self):
        if not self.annotation_mgr.selected_artist:
            QMessageBox.information(self, "No Selection", "Select a text annotation first.")
            return
        artist, kind = self.annotation_mgr.selected_artist
        if kind != "text":
            QMessageBox.information(self, "Not Text", "The selected annotation is not text.")
            return
        family = artist.get_fontfamily()[0] if artist.get_fontfamily() else "sans-serif"
        dialog = TextAnnotationDialog(
            self,
            text=artist.get_text(),
            color=artist.get_color(),
            fontsize=artist.get_fontsize(),
            bold=artist.get_fontweight() == "bold",
            italic=artist.get_fontstyle() == "italic",
            family=family,
            underline=bool(getattr(artist, "_spectra_underline", False)),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.annotation_mgr.update_selected_properties(dialog.result)
        self._annotation_selected(artist, kind)
        self._sync_annotation_list()

    def _sync_annotation_list(self):
        self.annotation_list.blockSignals(True)
        self.annotation_list.clear()
        for index, (artist, kind) in enumerate(self.annotation_mgr.annotations):
            suffix = f": {artist.get_text()[:24]}" if kind == "text" else ""
            self.annotation_list.addItem(f"{index + 1}. {kind.title()}{suffix}")
        self.annotation_list.blockSignals(False)

    def _select_annotation_row(self, row):
        if row >= 0:
            self.annotation_mgr.select_by_index(row)

    def _annotation_selected(self, artist, kind):
        if artist is None:
            return
        self.annotation_tool.blockSignals(True)
        self.annotation_tool.setCurrentIndex(0)
        self.annotation_tool.blockSignals(False)
        self.annotation_mgr.active_tool = "none"
        if kind == "text":
            self.ann_text_edit.setText(artist.get_text())
            self.ann_color_edit.setText(str(artist.get_color()))
            self.ann_size_spin.setValue(float(artist.get_fontsize()))
            self.ann_bold_check.setChecked(artist.get_fontweight() == "bold")
            self.ann_italic_check.setChecked(artist.get_fontstyle() == "italic")
            self.ann_underline_check.setChecked(
                bool(getattr(artist, "_spectra_underline", False))
            )
            family = artist.get_fontfamily()[0] if artist.get_fontfamily() else "sans-serif"
            self.ann_family_combo.setCurrentText(family)
            alpha = artist.get_alpha()
            self.ann_alpha_spin.setValue(1.0 if alpha is None else float(alpha))
        else:
            color = artist.get_color() if kind == "line" else artist.get_edgecolor()
            try:
                color = to_hex(color)
            except ValueError:
                color = str(color)
            self.ann_color_edit.setText(color)
            self.ann_width_spin.setValue(float(artist.get_linewidth()))
            alpha = artist.get_alpha()
            self.ann_alpha_spin.setValue(1.0 if alpha is None else float(alpha))

    def _apply_annotation_properties(self):
        self.annotation_mgr.update_selected_properties({
            "text": self.ann_text_edit.text(), "color": self.ann_color_edit.text() or "black",
            "fontsize": self.ann_size_spin.value(), "linewidth": self.ann_width_spin.value(),
            "bold": self.ann_bold_check.isChecked(), "italic": self.ann_italic_check.isChecked(),
            "underline": self.ann_underline_check.isChecked(),
            "family": self.ann_family_combo.currentText(),
            "alpha": self.ann_alpha_spin.value(), "text_alpha": self.ann_alpha_spin.value(),
        })
        self._sync_annotation_list()

    def _delete_annotation(self):
        self.annotation_mgr.delete_selected()
        self._sync_annotation_list()

    def _clear_all_annotations(self):
        if not self.annotation_mgr.annotations:
            return
        answer = QMessageBox.question(
            self, "Clear annotations", "Remove every annotation from this plot?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.annotation_mgr.clear_all()
            self._sync_annotation_list()

    def sync_annotations_to_state(self):
        state.global_set["annotations"] = self.annotation_mgr.get_serialized_data()

    # --------------------------- export/session --------------------------
    def save_session(self, save_as=False):
        self.sync_annotations_to_state()
        filepath = state.current_session_file
        if save_as or not filepath:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Save Session", filepath or "", "Session files (*.json)"
            )
            if not filepath:
                return False
            if not filepath.lower().endswith(".json"):
                filepath += ".json"
            state.current_session_file = filepath
        data = {
            "settings": state.settings,
            "all_data": [(stem, x.tolist(), y.tolist()) for stem, x, y in state.all_data],
            "master_folder": state.master_folder,
            "file_set": state.file_set,
            "global_set": state.global_set,
        }
        try:
            Path(filepath).write_text(json.dumps(data, cls=NumpyEncoder, indent=2), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Save Error", str(error))
            return False
        if save_as:
            QMessageBox.information(self, "Session Saved", f"Saved to:\n{filepath}")
        return True

    def export_data(self):
        fs = state.file_set[self.current_stem]
        options_dialog = ExportOptionsDialog(bool(fs.get("deconvs")), self)
        if options_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = options_dialog.result
        folder = QFileDialog.getExistingDirectory(self, "Select export folder")
        if not folder:
            return
        destination = Path(folder)
        x, y = self.get_processed_data_for_stem(self.current_stem)
        try:
            header = {
                "FTIR": "Wavenumber,Intensity", "XRD": "2-Theta,Intensity",
                "UVVIS": "Wavelength,Signal", "RAMAN": "Raman Shift,Intensity",
                "GENERAL": "X,Y",
            }.get(state.technique, "X,Y")
            if options["data"]:
                np.savetxt(
                    destination / f"{self.current_stem}_processed.csv",
                    np.column_stack((x, y)), delimiter=",", header=header, comments="",
                )
            if options["report"]:
                self._write_report(destination / f"{self.current_stem}_analysis_report.txt", fs)
            if options["image"]:
                save_figure(
                    self.figure,
                    destination / f"{self.current_stem}_plot{options['format']}",
                    dpi=options["dpi"],
                )
            if options["deconvolution"]:
                self._export_deconvolutions(destination, fs)
        except Exception as error:
            QMessageBox.critical(self, "Export Error", str(error))
            return
        QMessageBox.information(self, "Export Complete", f"Files saved to:\n{destination}")

    def _write_report(self, path, fs):
        with path.open("w", encoding="utf-8") as stream:
            stream.write(f"{state.technique} analysis report: {self.current_stem}\n\n")
            if state.technique == "XRD":
                stream.write("2-Theta\tIntensity\tFWHM\tCrystallite size (nm)\n")
                for row in fs.get("xrd_peaks", []):
                    stream.write("\t".join(f"{value:.5g}" for value in row) + "\n")
                sizes = [row[3] for row in fs.get("xrd_peaks", []) if row[3] > 0]
                if sizes:
                    average = float(np.mean(sizes))
                    deviation = float(np.std(sizes)) if len(sizes) > 1 else 0.0
                    stream.write(
                        f"\nAverage crystallite size: {average:.4g} nm\n"
                        f"Standard deviation: {deviation:.4g} nm\n"
                    )
            elif state.technique == "FTIR":
                stream.write("Wavenumber\tIntensity\tLabel\n")
                for px, py, label in fs.get("labels", []):
                    stream.write(f"{px:.5g}\t{py:.5g}\t{label}\n")
            else:
                stream.write("X\tY\tLabel\n")
                for px, py, label in fs.get("labels", []):
                    stream.write(f"{px:.5g}\t{py:.5g}\t{label}\n")
            if fs.get("areas"):
                stream.write("\nIntegrated areas\nStart\tEnd\tArea\n")
                for row in fs["areas"]:
                    stream.write("\t".join(f"{value:.5g}" for value in row) + "\n")

    def _export_deconvolutions(self, destination, fs):
        for region, item in enumerate(fs.get("deconvs", []), start=1):
            if len(item) == 6:
                x1, x2, baseline, params, count, is_valley = item
            else:
                x1, x2, baseline, params, count = item
                is_valley = False
            x_fit = np.linspace(min(x1, x2), max(x1, x2), 500)
            baseline_arr = np.asarray(baseline, dtype=float)
            baseline_fit = np.linspace(baseline_arr[0], baseline_arr[-1], len(x_fit))
            sign = -1 if is_valley else 1
            components = []
            for index in range(count):
                amp, center, sigma = params[index * 3:index * 3 + 3]
                components.append(amp * np.exp(-((x_fit - center) ** 2) / (2 * sigma ** 2)))
            total = np.sum(components, axis=0)
            columns = [x_fit, baseline_fit + sign * total]
            columns.extend(baseline_fit + sign * component for component in components)
            header = "X,Total Fit," + ",".join(f"Peak {index + 1}" for index in range(count))
            np.savetxt(
                destination / f"{self.current_stem}_deconvolution_{region}.csv",
                np.column_stack(columns), delimiter=",", header=header, comments="",
            )

    # ---------------------------- extra dialogs --------------------------
    def show_cheat_sheet(self):
        rows = [
            ("3200–3600", "O–H stretch (alcohols)", "Broad, strong"),
            ("3300–3500", "N–H stretch (amines)", "Medium"),
            ("2850–3000", "C–H stretch (alkanes)", "Medium/strong"),
            ("3000–3100", "=C–H stretch (alkenes)", "Medium"),
            ("2100–2260", "C≡C / C≡N stretch", "Weak/medium"),
            ("1650–1750", "C=O stretch (carbonyl)", "Strong"),
            ("1600–1680", "C=C stretch (alkenes)", "Weak/medium"),
            ("1500–1600", "N–H bend (amines)", "Medium"),
            ("1000–1300", "C–O stretch (ethers/esters)", "Strong"),
            ("600–900", "C–H bend (aromatics)", "Strong"),
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle("FT-IR Functional Groups")
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["Frequency (cm⁻¹)", "Group", "Intensity"])
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(620, 340)
        dialog.exec()

    def show_grain_size_chart(self):
        peaks = [item for item in state.file_set[self.current_stem].get("xrd_peaks", []) if item[3] > 0]
        if not peaks:
            QMessageBox.warning(self, "No Data", "Select valid XRD peaks first.")
            return
        peaks.sort(key=lambda item: item[0])
        labels = [f"{item[0]:.1f}°" for item in peaks]
        sizes = np.asarray([item[3] for item in peaks])
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Grain Size — {self.current_stem}")
        layout = QVBoxLayout(dialog)
        figure = Figure(figsize=(10, 4), dpi=100)
        canvas = FigureCanvasQTAgg(figure)
        first, second = figure.subplots(1, 2)
        average = float(np.mean(sizes))
        deviation = float(np.std(sizes)) if len(sizes) > 1 else 0.0
        first.bar(labels, sizes, color="#89b4fa", edgecolor="black", zorder=3)
        first.axhline(
            average, color="red", linestyle="--", linewidth=2,
            label=f"Average: {average:.1f} nm", zorder=4,
        )
        if deviation > 0:
            first.fill_between(
                [-0.5, len(labels) - 0.5], average - deviation, average + deviation,
                color="red", alpha=0.12, label=f"±1σ ({deviation:.1f} nm)", zorder=1,
            )
        first.set_ylabel("Crystallite size (nm)")
        first.set_xlabel("Peak position (2θ)")
        first.set_title("Size per Diffraction Peak")
        first.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)
        first.legend()
        if len(sizes) > 1 and deviation > 0:
            second.hist(
                sizes, bins=max(3, len(sizes)), density=True,
                color="#a6adc8", edgecolor="black", alpha=0.65, label="Data histogram",
            )
            x_curve = np.linspace(
                float(np.min(sizes) - 3 * deviation),
                float(np.max(sizes) + 3 * deviation),
                200,
            )
            y_curve = (
                1 / (deviation * np.sqrt(2 * np.pi))
                * np.exp(-0.5 * ((x_curve - average) / deviation) ** 2)
            )
            second.plot(x_curve, y_curve, color="#89b4fa", linewidth=2.5, label="Gaussian fit")
            second.axvline(
                average, color="red", linestyle="--", linewidth=2,
                label=f"Mean: {average:.1f} nm",
            )
        else:
            second.text(
                0.5, 0.5, "At least two distinct sizes are needed\nfor a Gaussian fit.",
                ha="center", va="center", transform=second.transAxes,
            )
        second.set_xlabel("Crystallite size (nm)")
        second.set_ylabel("Probability density")
        second.set_title("Gaussian Size Distribution")
        if len(sizes) > 1 and deviation > 0:
            second.legend()
        figure.tight_layout()
        layout.addWidget(canvas)
        save = QPushButton("Save chart")
        save.clicked.connect(lambda: self._save_figure(figure))
        layout.addWidget(save)
        dialog.resize(1000, 550)
        dialog.exec()

    def _save_figure(self, figure):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save chart", f"{self.current_stem}_grain_size.png", "Images (*.png *.pdf *.svg)"
        )
        if filename:
            save_figure(figure, filename, selected_filter=_)

    # ------------------------------ closing ------------------------------
    def _has_next_individual_spectrum(self):
        if state.settings.get("mode") != "individual" or not self.stems:
            return False
        all_stems = [item[0] for item in state.all_data]
        try:
            return all_stems.index(self.stems[0]) < len(all_stems) - 1
        except ValueError:
            return False

    def _refresh_finish_button(self):
        label = "Next Spectrum" if self._has_next_individual_spectrum() else "Finish & Close"
        self.finish_button.setText(label)

    def finish_current(self):
        if not self._has_next_individual_spectrum():
            self.close()
            return
        self.sync_annotations_to_state()
        self._skip_close_prompt = True
        self.accept()

    def closeEvent(self, event):
        if self._skip_close_prompt:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle("Close Viewer")
        box.setText("Save the workspace session before closing?")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        menu = QCheckBox("Return to file-selection screen")
        box.setCheckBox(menu)
        box.exec()
        if box.clickedButton() == cancel:
            event.ignore()
            return
        if box.clickedButton() == save and not self.save_session(save_as=not bool(state.current_session_file)):
            event.ignore()
            return
        if box.clickedButton() == discard:
            self.sync_annotations_to_state()
        state.restart_to_menu = menu.isChecked()
        event.accept()


def run_plot_viewer(data_tuples, title, out_dir=None, parent=None):
    """Open a modal Qt plot viewer and return its dialog result."""
    viewer = PlotViewer(data_tuples, title, out_dir=out_dir, parent=parent)
    return viewer.exec()
