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
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
    QListWidgetItem,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from scipy.optimize import curve_fit

from annotations import AnnotationManager
from app_version import APP_VERSION
from column_math import (
    FormulaError,
    apply_optical_transform,
    evaluate_column_formula,
)
from config import state
from dataset_reader import discover_many
from peak_detection import (
    DEFAULT_MAX_PEAKS,
    local_extremum_index,
    noise_adaptive_peak_indices,
    peak_polarity,
)
from processing import process_spectrum
from qt_general_plotter import DataTable
from readers import read_generic_configured, robust_read_spectrum
from qt_uvvis import UVVisAnalysisDialog
from qt_raman import RamanAnalysisDialog
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_updates import (
    PrivacyPreferencesDialog,
    UpdateController,
    open_update_signup,
    show_about,
)
from qt_widgets import (
    AnalysisToolBar,
    AnnotationToolBar,
    ColumnFormulaDialog,
    CompactNavigationToolbar,
    PanelToggleButton,
)
from plot_export import save_figure
from qt_export import export_figure_dialog, export_batch_dialog
from report_export import ExportItem
from qt_import_support import install_import_support
from plot_styles import BASIC_COLORS, LEGEND_LOCATIONS, PLOT_COLORS
from spectral_preprocessing import subtract_reference, trim_noisy_edges


STYLE = LIGHT_STYLE + """
QLabel#cursor { color: #1d4ed8; font-weight: 700; }
"""


UV_SIGNAL_TRANSFORMS = (
    ("Original / as imported", "none", None),
    ("Absorbance → Transmittance (%)", "absorbance_to_percent_transmittance", "Transmittance (%)"),
    ("Transmittance (%) → Absorbance", "percent_transmittance_to_absorbance", "Absorbance"),
    ("Reflectance (fraction) → Kubelka–Munk F(R)", "reflectance_fraction_to_kubelka_munk", "Kubelka–Munk F(R)"),
    ("Reflectance (%) → Kubelka–Munk F(R)", "reflectance_percent_to_kubelka_munk", "Kubelka–Munk F(R)"),
)


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


def _unique_label(label: str, existing: list[str]) -> str:
    base = str(label).strip() or "Series"
    if base not in existing:
        return base
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    return f"{base}_{index}"


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
        self.resize(820, 800)
        self.setMinimumSize(660, 600)
        self.setStyleSheet(STYLE)
        apply_window_icon(self, state.technique)
        self._build_ui(text, color, fontsize, bold, italic, family, underline)

    def _build_ui(self, text, color, fontsize, bold, italic, family, underline):
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setMinimumWidth(620)
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
        style_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        style_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        style_form.setVerticalSpacing(8)
        flags = QWidget()
        flags.setMinimumHeight(34)
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
        self.size_spin.setMinimumHeight(32)
        style_form.addRow("Font size", self.size_spin)
        self.family_combo = QComboBox()
        self.family_combo.setMinimumWidth(180)
        self.family_combo.setMinimumHeight(32)
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
        self.color_edit.setMinimumHeight(32)
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
        self.data_check = QCheckBox("Processed data — active spectrum (.csv)")
        self.report_check = QCheckBox("Peaks and areas — active spectrum (.txt)")
        self.image_check = QCheckBox("Graph — current figure, including plotted series")
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

    closeRequested = Signal(object)

    def __init__(self, data_tuples, title: str, out_dir=None, parent=None, *, embedded=False):
        super().__init__(parent)
        self.embedded = bool(embedded)
        if self.embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
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
        self._table_columns = []
        self._table_dirty = False
        self._table_loading = False

        self._build_layout()
        self._build_controls()
        self._connect_canvas()
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_select_callback=self._annotation_selected,
            on_list_update_callback=lambda _items: self._annotation_list_updated(),
            text_input_provider=self._request_annotation_text,
        )
        self.update_controller = UpdateController(self)
        self._build_menu_bar()
        self._install_shortcuts()
        self._load_active_settings()
        self._rebuild_data_table()
        self.update_plot()

        install_import_support(self, self.add_files, self.import_digitized,
                               suffixes={".csv", ".tsv", ".txt", ".dat", ".xy", ".xlsx", ".xls", ".dpt", ".asc"}
                               | ({".zip"} if state.technique == "LIBS" else set()))

    # ------------------------------- UI ---------------------------------
    def _build_layout(self):
        root = QVBoxLayout(self)
        self.root_layout = root
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        # Application header: a small number of persistent, global actions.
        # Technique-specific work stays in the workflow strip and inspector.
        self.app_header = QFrame()
        self.app_header.setObjectName("workspaceHeader")
        header = QHBoxLayout(self.app_header)
        header.setContentsMargins(12, 8, 10, 8)
        header.setSpacing(8)
        brand = QLabel("SpectraSuite")
        brand.setObjectName("workspaceBrand")
        header.addWidget(brand)
        technique = QLabel({
            "FTIR": "FT–IR", "UVVIS": "UV–Vis", "RAMAN": "Raman",
            "GENERAL": "2D Plot",
        }.get(state.technique, state.technique))
        technique.setObjectName("techniqueBadge")
        header.addWidget(technique)
        project = QWidget()
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(8, 0, 12, 0)
        project_layout.setSpacing(0)
        self.project_title_label = QLabel(self.windowTitle())
        self.project_title_label.setObjectName("projectTitle")
        project_layout.addWidget(self.project_title_label)
        self.project_summary_label = QLabel(f"{len(self.stems)} spectrum{'s' if len(self.stems) != 1 else ''} · Ready")
        self.project_summary_label.setObjectName("mutedLabel")
        project_layout.addWidget(self.project_summary_label)
        header.addWidget(project)
        self.command_search = QLineEdit()
        self.command_search.setObjectName("commandSearch")
        self.command_search.setPlaceholderText("Find a tool or action…")
        self.command_search.setClearButtonEnabled(True)
        self.command_search.setMinimumWidth(260)
        self.command_search.setMaximumWidth(540)
        self.command_search.returnPressed.connect(self._run_command_search)
        header.addWidget(self.command_search, 1)
        save_button = QPushButton("Save")
        save_button.setToolTip("Save workspace session")
        save_button.clicked.connect(lambda: self.save_session(save_as=True))
        header.addWidget(save_button)
        undo_button = QToolButton()
        undo_button.setText("↶")
        undo_button.setToolTip("Undo")
        undo_button.setAccessibleName("Undo")
        undo_button.clicked.connect(self._undo_active)
        header.addWidget(undo_button)
        redo_button = QToolButton()
        redo_button.setText("↷")
        redo_button.setToolTip("Redo")
        redo_button.setAccessibleName("Redo")
        redo_button.clicked.connect(self._redo_active)
        header.addWidget(redo_button)
        root.addWidget(self.app_header)

        # The inspector remains available through the historical ``controls``
        # attribute so existing session and GUI code keeps working.
        self.controls = QFrame()
        self.controls.setObjectName("contextInspector")
        self.controls_layout = QVBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(10, 10, 10, 8)
        self.controls_layout.setSpacing(7)
        inspector_header = QHBoxLayout()
        inspector_titles = QWidget()
        inspector_titles_layout = QVBoxLayout(inspector_titles)
        inspector_titles_layout.setContentsMargins(0, 0, 0, 0)
        inspector_titles_layout.setSpacing(0)
        self.inspector_title = QLabel("Prepare figure")
        self.inspector_title.setObjectName("inspectorTitle")
        self.inspector_subtitle = QLabel("Data, processing and layout")
        self.inspector_subtitle.setObjectName("mutedLabel")
        self.inspector_subtitle.setWordWrap(True)
        inspector_titles_layout.addWidget(self.inspector_title)
        inspector_titles_layout.addWidget(self.inspector_subtitle)
        inspector_header.addWidget(inspector_titles, 1)
        self.controls_layout.addLayout(inspector_header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(True)
        root.addWidget(self.splitter, 1)

        self.project_sidebar = QFrame()
        self.project_sidebar.setObjectName("projectSidebar")
        self.project_sidebar.setMinimumWidth(205)
        self.project_sidebar.setMaximumWidth(310)
        project_sidebar_layout = QVBoxLayout(self.project_sidebar)
        project_sidebar_layout.setContentsMargins(10, 10, 10, 10)
        project_sidebar_layout.setSpacing(7)
        new_analysis = QPushButton("+  New analysis")
        new_analysis.setObjectName("primary")
        new_analysis.setToolTip("Import another spectrum into this workspace")
        new_analysis.clicked.connect(self.add_files)
        project_sidebar_layout.addWidget(new_analysis)
        data_heading = QLabel("PROJECT DATA")
        data_heading.setObjectName("sectionLabel")
        project_sidebar_layout.addWidget(data_heading)
        self.project_data_list = QListWidget()
        self.project_data_list.setObjectName("projectDataList")
        self.project_data_list.setMinimumHeight(150)
        self.project_data_list.currentItemChanged.connect(self._project_series_selected)
        project_sidebar_layout.addWidget(self.project_data_list, 1)
        quick_heading = QLabel("WORKFLOWS")
        quick_heading.setObjectName("sectionLabel")
        project_sidebar_layout.addWidget(quick_heading)
        prepare_shortcut = QPushButton("≈  Prepare figure")
        prepare_shortcut.setObjectName("sidebarAction")
        prepare_shortcut.clicked.connect(lambda: self._activate_workflow("Prepare"))
        project_sidebar_layout.addWidget(prepare_shortcut)
        peaks_shortcut = QPushButton("⌁  Find peaks")
        peaks_shortcut.setObjectName("sidebarAction")
        peaks_shortcut.clicked.connect(lambda: self._activate_workflow("Analyze"))
        project_sidebar_layout.addWidget(peaks_shortcut)
        project_sidebar_layout.addStretch()
        data_help = QLabel("Select a spectrum here or click a line directly on the plot.")
        data_help.setObjectName("mutedLabel")
        data_help.setWordWrap(True)
        project_sidebar_layout.addWidget(data_help)
        self.splitter.addWidget(self.project_sidebar)

        self.center_panel = QFrame()
        self.center_panel.setObjectName("canvasPanel")
        center_layout = QVBoxLayout(self.center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.workflow_bar = QFrame()
        self.workflow_bar.setObjectName("workflowBar")
        workflow_layout = QHBoxLayout(self.workflow_bar)
        workflow_layout.setContentsMargins(8, 5, 8, 5)
        workflow_layout.setSpacing(2)
        self.workflow_button_group = QButtonGroup(self)
        self.workflow_button_group.setExclusive(True)
        self.workflow_buttons = {}
        for index, (name, glyph) in enumerate((
            ("Prepare", "≈"), ("Analyze", "⌁"), ("Style", "◐"),
            ("Annotate", "T"), ("Export", "↓"),
        )):
            button = QToolButton()
            button.setText(f"{glyph}  {name}")
            button.setToolTip(f"Open {name.lower()} tools")
            button.setAccessibleName(f"{name} workflow")
            button.setCheckable(True)
            button.setObjectName("workflowButton")
            button.clicked.connect(
                lambda checked=False, selected=name: checked and self._activate_workflow(selected)
            )
            self.workflow_button_group.addButton(button, index)
            self.workflow_buttons[name] = button
            workflow_layout.addWidget(button)
        workflow_layout.addStretch()
        center_layout.addWidget(self.workflow_bar)

        self.series_bar = QFrame()
        self.series_bar.setObjectName("seriesBar")
        self.series_chip_layout = QHBoxLayout(self.series_bar)
        self.series_chip_layout.setContentsMargins(10, 6, 10, 6)
        self.series_chip_layout.setSpacing(6)
        self.series_scroll = QScrollArea()
        self.series_scroll.setObjectName("seriesScroll")
        self.series_scroll.setWidgetResizable(True)
        self.series_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.series_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.series_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.series_scroll.setMinimumHeight(47)
        self.series_scroll.setMaximumHeight(64)
        self.series_scroll.setWidget(self.series_bar)
        center_layout.addWidget(self.series_scroll)

        self.plot_panel = QWidget()
        plot_layout = QVBoxLayout(self.plot_panel)
        plot_layout.setContentsMargins(8, 4, 8, 4)
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
        self.canvas_tabs = QTabWidget()
        self.canvas_tabs.setObjectName("canvasTabs")
        self.canvas_tabs.setDocumentMode(True)
        self.canvas_tabs.addTab(self.plot_panel, "Plot")
        center_layout.addWidget(self.canvas_tabs, 1)

        results_page = QWidget()
        results_layout = QVBoxLayout(results_page)
        results_layout.setContentsMargins(10, 8, 10, 8)
        self.results_list = QListWidget()
        self.results_list.setObjectName("resultsList")
        self.results_list.addItem("Analysis results will appear here.")
        results_layout.addWidget(self.results_list)

        table_page = QWidget()
        table_page.setObjectName("dataWorkspace")
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(8, 6, 8, 6)
        table_layout.setSpacing(5)
        data_header = QHBoxLayout()
        title = QLabel("Editable spectroscopy data — columns are marked [X], [Y], or [Ignore]")
        title.setWordWrap(True)
        data_header.addWidget(title, 1)
        table_layout.addLayout(data_header)
        self.data_table = DataTable()
        self.data_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.data_table.itemChanged.connect(self._data_table_changed)
        self.data_table.model().columnsInserted.connect(self._data_columns_inserted)
        self.data_table.historyRestored.connect(self._sync_table_metadata)
        table_layout.addWidget(self.data_table, 1)
        data_tools = QHBoxLayout()
        for label, tooltip, slot in (
            ("＋ Row", "Insert a row at the current selection", self._insert_data_row),
            ("− Row", "Delete the selected rows", self._delete_data_rows),
            ("＋ Column", "Insert a new blank column", self._insert_data_column),
            ("− Column", "Delete the selected columns", self._delete_data_columns),
            ("Rename", "Rename the selected column", self._rename_data_column),
            ("X", "Set the selected column as an X axis", lambda: self._set_data_column_role("X")),
            ("Y", "Set the selected column as a plotted Y series", lambda: self._set_data_column_role("Y")),
            ("Ignore", "Keep the selected column but do not plot it", lambda: self._set_data_column_role("Ignore")),
            ("ƒx", "Create a calculated column from a safe formula", self._create_formula_column),
        ):
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setFixedHeight(28)
            button.clicked.connect(slot)
            data_tools.addWidget(button)
        data_tools.addStretch()
        apply_table = QPushButton("Apply table to plot")
        apply_table.setObjectName("primary")
        apply_table.setToolTip("Rebuild plotted X/Y series from the edited table")
        apply_table.clicked.connect(self._apply_data_table)
        data_tools.addWidget(apply_table)
        table_layout.addLayout(data_tools)
        self.canvas_tabs.addTab(table_page, "Data table")
        self.canvas_tabs.currentChanged.connect(self._canvas_view_changed)

        self.splitter.addWidget(self.center_panel)

        # Inspector, results and history share one full-height right sidebar.
        # A vertical tab rail avoids the old bottom drawer stealing height from
        # both the plot and the spreadsheet-style data table.
        self.right_sidebar = QTabWidget()
        self.right_sidebar.setObjectName("rightSidebarTabs")
        self.right_sidebar.setDocumentMode(True)
        self.right_sidebar.setTabPosition(QTabWidget.TabPosition.West)
        self.right_sidebar.setMinimumWidth(430)
        self.right_sidebar.setMaximumWidth(620)
        self.right_sidebar.addTab(self.controls, "Inspector")
        self.right_sidebar.addTab(results_page, "Results")

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(10, 8, 10, 8)
        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        history_layout.addWidget(self.history_list)
        self.right_sidebar.addTab(history_page, "History")

        # Retain the historical attributes for lightweight extension code.
        self.detail_tabs = self.right_sidebar
        self.data_panel = self.right_sidebar
        self.splitter.addWidget(self.right_sidebar)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([225, 800, 460])

        self.controls_toggle = PanelToggleButton(self.right_sidebar, "right", self)
        self.controls_toggle.setToolTip("Hide Inspector, Results and History")
        header.addWidget(self.controls_toggle)
        self.project_toggle = PanelToggleButton(self.project_sidebar, "left", self)
        self.project_toggle.setToolTip("Hide project sidebar")
        header.insertWidget(max(0, header.count() - 1), self.project_toggle)
        self._sync_history_list()

    def _activate_workflow(self, name):
        """Show one contextual tool family without changing analysis state."""
        page_map = {"Prepare": 0, "Style": 1, "Annotate": 2, "Analyze": 3, "Export": 4}
        if name not in page_map or not hasattr(self, "tabs"):
            return
        self.tabs.setCurrentIndex(page_map[name])
        for button_name, button in self.workflow_buttons.items():
            button.setChecked(button_name == name)
        descriptions = {
            "Prepare": ("Prepare figure", "Data, processing and plot arrangement"),
            "Analyze": ("Analyze spectrum", "Peaks, baseline, area and technique-specific tools"),
            "Style": ("Style figure", "Axes, legend and publication appearance"),
            "Annotate": ("Annotate figure", "Text, arrows, lines and editable shapes"),
            "Export": ("Export & save", "Data, report, figure and reusable workspace session"),
        }
        title, subtitle = descriptions[name]
        self.inspector_title.setText(title)
        self.inspector_subtitle.setText(subtitle)
        if self.right_sidebar.isHidden():
            self.controls_toggle.set_panel_visible(True)
        self.right_sidebar.setCurrentIndex(0)
        if name == "Analyze":
            self.canvas_tabs.setCurrentIndex(0)

    def _run_command_search(self):
        """Route a plain-language command search to the relevant workflow."""
        query = self.command_search.text().strip().lower()
        if not query:
            return
        routes = (
            (("peak", "area", "baseline", "fit", "band gap", "urbach", "grain"), "Analyze"),
            (("axis", "axes", "legend", "colour", "color", "font", "style"), "Style"),
            (("annot", "text", "arrow", "line", "shape"), "Annotate"),
            (("export", "save", "report", "pdf", "png", "svg"), "Export"),
            (("data", "table", "formula", "process", "smooth", "normal", "prepare"), "Prepare"),
        )
        destination = next(
            (name for keywords, name in routes if any(keyword in query for keyword in keywords)),
            None,
        )
        if destination:
            self._activate_workflow(destination)
            if destination == "Prepare" and "table" in query:
                self.canvas_tabs.setCurrentIndex(1)
            self.command_search.clear()
            self.command_search.setPlaceholderText(f"Opened {destination} tools")
        else:
            self.command_search.clear()
            self.command_search.setPlaceholderText("No match — try peak, table, axes, legend or export")
            self.command_search.setToolTip(
                "Try peak, baseline, table, formula, axes, legend, annotation, export or save."
            )

    def _canvas_view_changed(self, index):
        """Keep the inspector relevant when the central document changes."""
        if index == 1 and hasattr(self, "tabs"):
            self._activate_workflow("Prepare")

    def _project_series_selected(self, item, _previous=None):
        if item is None or not hasattr(self, "file_combo"):
            return
        stem = item.data(Qt.ItemDataRole.UserRole)
        if stem in self.data_dict and stem != self.current_stem:
            self.file_combo.setCurrentText(stem)

    def _select_series_chip(self, stem):
        if hasattr(self, "file_combo") and stem in self.data_dict:
            self.file_combo.setCurrentText(stem)

    def _sync_project_data_list(self):
        if not hasattr(self, "project_data_list"):
            return
        self.project_data_list.blockSignals(True)
        self.project_data_list.clear()
        current_item = None
        for stem in self.stems:
            settings = state.file_set.get(stem, {})
            display_name = str(settings.get("custom_name", stem))
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, stem)
            item.setToolTip(f"Source: {stem}\nRole: plotted Y spectrum")
            color = QColor(str(settings.get("color", "#2563eb")))
            if color.isValid():
                item.setForeground(QBrush(color))
            self.project_data_list.addItem(item)
            if stem == self.current_stem:
                current_item = item
        if current_item is not None:
            self.project_data_list.setCurrentItem(current_item)
        self.project_data_list.blockSignals(False)

    def _sync_series_chips(self):
        if not hasattr(self, "series_chip_layout"):
            return
        while self.series_chip_layout.count():
            item = self.series_chip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.series_chip_buttons = {}
        for stem in self.stems:
            settings = state.file_set.get(stem, {})
            display_name = str(settings.get("custom_name", stem))
            button = QToolButton()
            button.setObjectName("seriesChip")
            button.setText(f"●  {display_name}")
            button.setToolTip(f"Select {display_name}\nSource: {stem}")
            button.setAccessibleName(f"Select spectrum {display_name}")
            button.setCheckable(True)
            button.setChecked(stem == self.current_stem)
            color = QColor(str(settings.get("color", "#2563eb")))
            foreground = color.name() if color.isValid() else "#2563eb"
            button.setStyleSheet(
                "QToolButton { color: " + foreground + "; }"
                "QToolButton:checked { color: #1d4ed8; }"
            )
            button.clicked.connect(
                lambda _checked=False, selected=stem: self._select_series_chip(selected)
            )
            self.series_chip_layout.addWidget(button)
            self.series_chip_buttons[stem] = button
        self.series_chip_layout.addStretch()

    def _sync_workspace_navigation(self):
        self._sync_project_data_list()
        self._sync_series_chips()
        if hasattr(self, "project_summary_label"):
            count = len(self.stems)
            self.project_summary_label.setText(
                f"{count} spectrum{'s' if count != 1 else ''} · {self.current_stem} selected"
            )

    def _sync_history_list(self):
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        table_edits = len(getattr(getattr(self, "data_table", None), "undo_stack", []))
        annotation_edits = len(
            getattr(getattr(self, "annotation_mgr", None), "undo_stack", [])
        )
        if not self._state_undo and not table_edits and not annotation_edits:
            self.history_list.addItem("Workspace opened — no edits yet")
        else:
            start = max(0, len(self._state_undo) - 49)
            for index in range(start, len(self._state_undo)):
                self.history_list.addItem(f"Workspace change {index + 1}")
            if table_edits:
                self.history_list.addItem(f"Data-table edits available to undo: {table_edits}")
            if annotation_edits:
                self.history_list.addItem(
                    f"Annotation edits available to undo: {annotation_edits}"
                )
        if self._state_redo:
            self.history_list.addItem(f"{len(self._state_redo)} change(s) available to redo")

    def _toggle_controls(self, hidden):
        self.controls_toggle.setChecked(bool(hidden))

    def _toggle_toolbar(self, hidden):
        self.toolbar_toggle.setChecked(bool(hidden))

    def _build_menu_bar(self):
        """Add desktop-standard menus alongside the contextual inspector."""
        menu_bar = QMenuBar(self)
        menu_bar.setNativeMenuBar(not self.embedded)
        self.root_layout.setMenuBar(menu_bar)
        self.desktop_menu_bar = menu_bar

        file_menu = menu_bar.addMenu("&File")
        add_action = QAction("&Add data…", self)
        add_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        add_action.triggered.connect(self.add_files)
        file_menu.addAction(add_action)
        replace_action = QAction("&Replace active data…", self)
        replace_action.triggered.connect(self.replace_current)
        file_menu.addAction(replace_action)
        file_menu.addSeparator()
        figure_action = QAction("Save &figure…", self)
        figure_action.triggered.connect(self.export_figure)
        file_menu.addAction(figure_action)
        export_action = QAction("&Export data and graph…", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_data)
        file_menu.addAction(export_action)
        save_action = QAction("&Save session…", self)
        save_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        save_action.triggered.connect(lambda: self.save_session(save_as=True))
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        close_action = QAction("&Close", self)
        close_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Close))
        close_action.triggered.connect(self._request_close)
        file_menu.addAction(close_action)

        edit_menu = menu_bar.addMenu("&Edit")
        apply_table = QAction("Apply &data table to plot", self)
        apply_table.triggered.connect(
            lambda: (self._activate_workflow("Prepare"), self._apply_data_table())
        )
        edit_menu.addAction(apply_table)
        formula_action = QAction("Create calculated &column…", self)
        formula_action.triggered.connect(
            lambda: (self._activate_workflow("Prepare"), self._create_formula_column())
        )
        edit_menu.addAction(formula_action)
        edit_menu.addSeparator()
        rename_legend = QAction("Edit selected &legend name", self)
        rename_legend.triggered.connect(
            lambda: (self._activate_workflow("Style"), self._edit_selected_legend_name())
        )
        edit_menu.addAction(rename_legend)

        history_menu = menu_bar.addMenu("&History")
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        undo_action.triggered.connect(self._undo_active)
        history_menu.addAction(undo_action)
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        redo_action.triggered.connect(self._redo_active)
        history_menu.addAction(redo_action)

        view_menu = menu_bar.addMenu("&View")
        self.view_project_action = QAction("Project and data sidebar", self)
        self.view_controls_action = QAction("Inspector, results and history sidebar", self)
        self.view_toolbar_action = QAction("Plot navigation toolbar", self)
        for action in (
            self.view_project_action, self.view_controls_action, self.view_toolbar_action,
        ):
            action.setCheckable(True)
            action.setChecked(True)
            view_menu.addAction(action)
        self.view_project_action.toggled.connect(self.project_toggle.set_panel_visible)
        self.view_controls_action.toggled.connect(self.controls_toggle.set_panel_visible)
        self.view_toolbar_action.toggled.connect(self.toolbar_toggle.set_panel_visible)
        self.project_toggle.toggled.connect(
            lambda hidden: self.view_project_action.setChecked(not hidden)
        )
        self.controls_toggle.toggled.connect(
            lambda hidden: self.view_controls_action.setChecked(not hidden)
        )
        self.toolbar_toggle.toggled.connect(
            lambda hidden: self.view_toolbar_action.setChecked(not hidden)
        )
        view_menu.addSeparator()
        plot_workspace = QAction("Show plot workspace", self)
        plot_workspace.setShortcut(QKeySequence("Ctrl+1"))
        plot_workspace.triggered.connect(lambda: self.canvas_tabs.setCurrentIndex(0))
        view_menu.addAction(plot_workspace)
        table_workspace = QAction("Show data-table workspace", self)
        table_workspace.setShortcut(QKeySequence("Ctrl+2"))
        table_workspace.triggered.connect(lambda: self.canvas_tabs.setCurrentIndex(1))
        view_menu.addAction(table_workspace)

        analysis_menu = menu_bar.addMenu("&Analysis")
        analysis_actions = []
        for _glyph, label, value, _color, _background in self.click_mode.TOOLS:
            action = QAction(label, self)
            action.triggered.connect(
                lambda _checked=False, mode=value: (
                    self._activate_workflow("Analyze"),
                    self.click_mode.setCurrentData(mode),
                )
            )
            analysis_menu.addAction(action)
            analysis_actions.append(action)
        analysis_menu.addSeparator()
        auto_peaks = QAction("Auto-find &peaks", self)
        auto_peaks.triggered.connect(
            lambda: (self._activate_workflow("Analyze"), self.auto_find_peaks())
        )
        analysis_menu.addAction(auto_peaks)
        advanced = None
        if state.technique == "UVVIS":
            advanced = QAction("Band-gap and &Urbach analysis…", self)
            advanced.triggered.connect(
                lambda: (self._activate_workflow("Analyze"), self.show_uvvis_analysis())
            )
            analysis_menu.addAction(advanced)
        elif state.technique == "RAMAN":
            advanced = QAction("Raman peak &measurements…", self)
            advanced.triggered.connect(
                lambda: (self._activate_workflow("Analyze"), self.show_raman_analysis())
            )
            analysis_menu.addAction(advanced)

        account_menu = menu_bar.addMenu("&Account")
        edition = QAction("Community edition · Offline-ready", self)
        edition.setEnabled(False)
        account_menu.addAction(edition)
        account_menu.addSeparator()
        email_updates = QAction("Get &update emails…", self)
        email_updates.triggered.connect(lambda: open_update_signup(self))
        account_menu.addAction(email_updates)
        privacy_preferences = QAction("Privacy && update &preferences…", self)
        privacy_preferences.triggered.connect(self._show_privacy_preferences)
        account_menu.addAction(privacy_preferences)

        help_menu = menu_bar.addMenu("&Help")
        check_updates = QAction("Check for &updates…", self)
        check_updates.triggered.connect(lambda: self.update_controller.check(silent=False))
        help_menu.addAction(check_updates)
        automatic_updates = QAction("Automatically check for updates", self)
        automatic_updates.setCheckable(True)
        automatic_updates.setChecked(self.update_controller.automatic_enabled())
        automatic_updates.toggled.connect(self.update_controller.set_automatic_enabled)
        help_menu.addAction(automatic_updates)
        help_menu.addSeparator()
        about = QAction(f"About SpectraSuite {APP_VERSION}", self)
        about.triggered.connect(lambda: show_about(self))
        help_menu.addAction(about)

        # Keep stable Python references to the leaf actions.  The single-window
        # shell can place these actions in its native menus without re-parenting
        # QMenu objects.  Moving QMenu objects between menu bars is unsafe on
        # macOS because Cocoa may delete the underlying native menu while a
        # Python wrapper still exists.
        self.menu_action_groups = {
            "File": [
                add_action, replace_action, None, figure_action, export_action, save_action,
                None, close_action,
            ],
            "Edit": [apply_table, formula_action, None, rename_legend],
            "History": [undo_action, redo_action],
            "View": [
                self.view_project_action, self.view_controls_action,
                self.view_toolbar_action, None, plot_workspace, table_workspace,
            ],
            "Analysis": analysis_actions + [None, auto_peaks]
            + ([advanced] if advanced is not None else []),
            "Account": [edition, None, email_updates, privacy_preferences],
            "Help": [check_updates, automatic_updates, None, about],
        }

    def _show_privacy_preferences(self):
        dialog = PrivacyPreferencesDialog(self.update_controller, self)
        dialog.exec()

    def _install_shortcuts(self):
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.delete_shortcut.activated.connect(self._delete_active)
        self.backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self.backspace_shortcut.activated.connect(self._delete_active)
        self.command_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.command_shortcut.activated.connect(self.command_search.setFocus)

    def _build_controls(self):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("inspectorPages")
        self.tabs.setDocumentMode(True)
        self.controls_layout.addWidget(self.tabs, 1)
        self._build_file_tab()
        self._build_axes_tab()
        self._build_annotation_tab()
        self._build_analysis_tab()
        self._build_export_tab()
        self.tabs.tabBar().hide()

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
        self._activate_workflow("Prepare")

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
        layout_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        self.order_buttons = []
        for position, (label, direction) in enumerate((
            ("↑", "up"), ("↓", "down"),
            ("←", "left"), ("→", "right"),
        )):
            button = QToolButton()
            button.setText(label)
            button.setFixedSize(34, 30)
            button.setToolTip(f"Move selected spectrum {direction}")
            button.setAccessibleName(f"Move selected spectrum {direction}")
            button.clicked.connect(
                lambda _checked=False, step=direction: self.move_current_spatial(step)
            )
            order.addWidget(button, position // 2, position % 2)
            self.order_buttons.append(button)
        manage_layout.addLayout(order)
        layout.addWidget(manage)

        appearance = QGroupBox("Line & Processing")
        form = QFormLayout(appearance)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit()
        self.name_edit.setToolTip("Press Enter to update this series name in the legend")
        self.name_edit.returnPressed.connect(self._commit_display_name)
        form.addRow("Display name", self.name_edit)
        color_row = QWidget()
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_edit = QLineEdit()
        self.color_edit.editingFinished.connect(
            lambda: self._set_active_line_color(self.color_edit.text())
        )
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
                lambda _checked=False, selected=value: self._set_active_line_color(selected)
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
        self.uv_transform_combo = QComboBox()
        for transform_label, transform_value, _axis_label in UV_SIGNAL_TRANSFORMS:
            self.uv_transform_combo.addItem(transform_label, transform_value)
        self.uv_transform_combo.setToolTip(
            "Absorbance/transmittance conversions are reversible from raw data. "
            "Kubelka–Munk is a separate diffuse-reflectance transform."
        )
        self.uv_transform_label = QLabel("UV-Vis signal")
        self.uv_transform_label.setVisible(state.technique == "UVVIS")
        self.uv_transform_combo.setVisible(state.technique == "UVVIS")
        self.uv_transform_combo.currentIndexChanged.connect(self._uv_transform_changed)
        form.addRow(self.uv_transform_label, self.uv_transform_combo)
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
        reference_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        legend_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        self.legend_name_list = QListWidget()
        self.legend_name_list.setMinimumHeight(105)
        self.legend_name_list.setMinimumWidth(275)
        self.legend_name_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.legend_name_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.legend_name_list.setToolTip(
            "Double-click a name to edit it. The original file or column name is shown as a tooltip."
        )
        self.legend_name_list.itemChanged.connect(self._legend_name_changed)
        self.legend_name_list.currentItemChanged.connect(self._legend_series_selected)
        series_label = QLabel("Series names — double-click a full-width row to edit")
        series_label.setWordWrap(True)
        legend_form.addRow(series_label)
        legend_form.addRow(self.legend_name_list)
        edit_legend_name = QPushButton("Edit selected legend name")
        edit_legend_name.clicked.connect(self._edit_selected_legend_name)
        legend_form.addRow(edit_legend_name)
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.click_mode = AnalysisToolBar(state.technique)
        self.click_mode.currentIndexChanged.connect(self._click_mode_changed)
        form.addRow(self.click_mode)
        mode_hint = QLabel("Move the pointer over an icon to see what it does.")
        mode_hint.setWordWrap(True)
        form.addRow(mode_hint)
        self.prominence_spin = QDoubleSpinBox()
        self.prominence_spin.setRange(0, 1e9)
        self.prominence_spin.setDecimals(6)
        self.prominence_spin.setSingleStep(0.01)
        self.prominence_spin.setValue(0.0)
        self.auto_peak_threshold_check = QCheckBox("Automatic noise-adaptive threshold")
        self.auto_peak_threshold_check.setChecked(True)
        self.auto_peak_threshold_check.toggled.connect(self._toggle_peak_threshold_fields)
        form.addRow(self.auto_peak_threshold_check)
        form.addRow("Peak prominence", self.prominence_spin)
        self.xrd_height_spin = QDoubleSpinBox()
        self.xrd_height_spin.setRange(-1e9, 1e9)
        self.xrd_height_spin.setDecimals(6)
        self.xrd_height_spin.setSingleStep(0.1)
        self.xrd_height_spin.setValue(0.0)
        self.xrd_height_spin.setVisible(state.technique == "XRD")
        self.xrd_height_label = QLabel("XRD minimum height")
        self.xrd_height_label.setVisible(state.technique == "XRD")
        form.addRow(self.xrd_height_label, self.xrd_height_spin)
        self.maximum_peaks_spin = QSpinBox()
        self.maximum_peaks_spin.setRange(1, 200)
        self.maximum_peaks_spin.setValue(DEFAULT_MAX_PEAKS.get(state.technique, 30))
        form.addRow("Maximum auto peaks", self.maximum_peaks_spin)
        self.peak_threshold_info = QLabel(
            "Automatic mode adapts to the spectrum scale and measured point-to-point noise."
        )
        self.peak_threshold_info.setWordWrap(True)
        form.addRow(self.peak_threshold_info)
        self._toggle_peak_threshold_fields(True)
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

        if state.technique in {"XPS", "LIBS"}:
            scope = QLabel(
                "XPS preview: import binding-energy data in eV. Peak labels are user assignments; "
                "chemical-state fitting and atomic percentages are not available yet."
                if state.technique == "XPS" else
                "LIBS preview: import wavelength data in nm. Smoothing starts off. "
                "Peak positions alone do not confirm an element; automatic line assignment is not available yet."
            )
            scope.setWordWrap(True)
            layout.addWidget(scope)

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

    def _build_export_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Export")
        figure_group = QGroupBox("Export results")
        figure_layout = QVBoxLayout(figure_group)
        description = QLabel(
            "Create a data table, analysis report and publication figure from the current spectrum."
        )
        description.setWordWrap(True)
        figure_layout.addWidget(description)
        save_figure_button = QPushButton("Save figure…")
        save_figure_button.setObjectName("primary")
        save_figure_button.clicked.connect(self.export_figure)
        figure_layout.addWidget(save_figure_button)
        export = QPushButton("Export data / results bundle…")
        export.setObjectName("primary")
        export.clicked.connect(self.export_data)
        figure_layout.addWidget(export)
        layout.addWidget(figure_group)

        session_group = QGroupBox("Continue later")
        session_layout = QVBoxLayout(session_group)
        session_hint = QLabel(
            "Save the current spectra, processing choices, figure settings and annotations as a session."
        )
        session_hint.setWordWrap(True)
        session_layout.addWidget(session_hint)
        save = QPushButton("Save workspace session…")
        save.clicked.connect(lambda: self.save_session(save_as=True))
        session_layout.addWidget(save)
        layout.addWidget(session_group)

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
        self._sync_history_list()

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
        self._rebuild_data_table()
        self.update_plot()

    def _undo_active(self):
        if self._focus_in_data_table() and self.data_table.undo_edit():
            self._table_dirty = True
            self._sync_history_list()
            return
        if self.tabs.currentWidget() is self.tabs.widget(2) and self.annotation_mgr.undo():
            self._sync_history_list()
            return
        if self._state_undo:
            self._state_redo.append(self._state_snapshot())
            self._restore_state(self._state_undo.pop())
            self._sync_history_list()

    def _redo_active(self):
        if self._focus_in_data_table() and self.data_table.redo_edit():
            self._table_dirty = True
            self._sync_history_list()
            return
        if self.tabs.currentWidget() is self.tabs.widget(2) and self.annotation_mgr.redo():
            self._sync_history_list()
            return
        if self._state_redo:
            self._state_undo.append(self._state_snapshot())
            self._restore_state(self._state_redo.pop())
            self._sync_history_list()

    def _focus_in_data_table(self):
        focus = self.focusWidget()
        return focus is self.data_table or (
            focus is not None and self.data_table.isAncestorOf(focus)
        )

    def _delete_active(self):
        if self._focus_in_data_table():
            self.data_table.begin_command()
            for item in self.data_table.selectedItems():
                item.setText("")
            self.data_table.end_command()
            self._table_dirty = True
        elif self.tabs.currentWidget() is self.tabs.widget(2):
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
        self.uv_transform_combo.blockSignals(True)
        transform_index = self.uv_transform_combo.findData(fs.get("uv_transform", "none"))
        self.uv_transform_combo.setCurrentIndex(max(0, transform_index))
        self.uv_transform_combo.blockSignals(False)
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
        self._sync_legend_name_list()
        self.sync_peak_list()
        self._sync_workspace_navigation()

    def _sync_legend_name_list(self):
        if not hasattr(self, "legend_name_list"):
            return
        self.legend_name_list.blockSignals(True)
        existing_stems = [
            self.legend_name_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.legend_name_list.count())
        ]
        rebuild = existing_stems != self.stems
        if rebuild:
            self.legend_name_list.clear()
        current_item = None
        for index, stem in enumerate(self.stems):
            display_name = str(state.file_set.get(stem, {}).get("custom_name", stem))
            if rebuild:
                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, stem)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.legend_name_list.addItem(item)
            else:
                item = self.legend_name_list.item(index)
                item.setText(display_name)
            item.setToolTip(f"Source: {stem}\nDouble-click to edit the displayed legend name.")
            if stem == self.current_stem:
                current_item = item
        if current_item is not None:
            self.legend_name_list.setCurrentItem(current_item)
        self.legend_name_list.blockSignals(False)

    def _legend_series_selected(self, item, _previous=None):
        if item is None:
            return
        stem = item.data(Qt.ItemDataRole.UserRole)
        if stem in self.data_dict and stem != self.current_stem:
            self.file_combo.setCurrentText(stem)

    def _edit_selected_legend_name(self):
        item = self.legend_name_list.currentItem()
        if item is not None:
            self.legend_name_list.editItem(item)

    def _legend_name_changed(self, item):
        stem = item.data(Qt.ItemDataRole.UserRole)
        if stem not in state.file_set:
            return
        new_name = item.text().strip()
        old_name = str(state.file_set[stem].get("custom_name", stem))
        if not new_name:
            item.setText(old_name)
            return
        if new_name == old_name:
            return
        self._checkpoint_state()
        state.file_set[stem]["custom_name"] = new_name
        if stem == self.current_stem:
            self.name_edit.setText(new_name)
        item.setToolTip(f"Source: {stem}\nDouble-click to edit the displayed legend name.")
        self._sync_workspace_navigation()
        self.update_plot()

    def _commit_display_name(self):
        new_name = self.name_edit.text().strip() or self.current_stem
        old_name = str(state.file_set[self.current_stem].get("custom_name", self.current_stem))
        if new_name == old_name:
            return
        self._checkpoint_state()
        state.file_set[self.current_stem]["custom_name"] = new_name
        self._sync_legend_name_list()
        self._sync_workspace_navigation()
        self.update_plot()

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
            uv_transform=self.uv_transform_combo.currentData() or "none",
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
        self._sync_legend_name_list()
        self.update_plot()

    def apply_to_all(self):
        self.save_and_update()
        source = state.file_set[self.current_stem]
        keys = (
            "smooth", "do_baseline", "normalize", "derivative", "als_lam",
            "als_p", "t2a", "uv_transform", "offset", "auto_clean_edges",
        )
        for stem in self.stems:
            for key in keys:
                state.file_set[stem][key] = source.get(key)
        self.update_plot()
        QMessageBox.information(self, "Settings Applied", "Processing settings were applied to all files.")

    def reset_file_settings(self):
        self.offset_spin.setValue(0)
        self.smooth_spin.setValue(0 if state.technique in {"XPS", "LIBS"} else 15)
        self.normalize_check.setChecked(False)
        self.t2a_check.setChecked(False)
        self.uv_transform_combo.setCurrentIndex(0)
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
            self._set_active_line_color(color.name())

    def _set_active_line_color(self, value):
        color = QColor(str(value))
        if not color.isValid() or self.current_stem not in state.file_set:
            return
        normalized = color.name()
        self.color_edit.setText(normalized)
        if state.file_set[self.current_stem].get("color") == normalized:
            return
        self._checkpoint_state()
        state.file_set[self.current_stem]["color"] = normalized
        self._sync_workspace_navigation()
        self.update_plot()

    def choose_legend_color(self):
        color = QColorDialog.getColor(QColor(self.legend_color.text()), self, "Legend font color")
        if color.isValid():
            self.legend_color.setText(color.name())

    def _select_file(self, stem):
        if stem and stem in self.data_dict:
            self.current_stem = stem
            self._load_active_settings()
            self.update_plot()

    def _uv_transform_changed(self):
        if state.technique != "UVVIS" or self.current_stem not in state.file_set:
            return
        transform = self.uv_transform_combo.currentData() or "none"
        fs = state.file_set[self.current_stem]
        if fs.get("uv_transform", "none") == transform:
            return
        self._checkpoint_state()
        fs.setdefault("uv_source_ylabel", state.global_set.get("ylabel", "Signal"))
        fs["uv_transform"] = transform
        axis_label = next(
            (label for _name, value, label in UV_SIGNAL_TRANSFORMS if value == transform),
            None,
        )
        if transform == "none":
            axis_label = str(fs.get("uv_source_ylabel") or "Signal")
        if axis_label:
            state.global_set["ylabel"] = axis_label
            self.ylabel_edit.setText(axis_label)
        self.update_plot()

    # ------------------------------- data --------------------------------
    @staticmethod
    def _column_code(index):
        """Return spreadsheet-style letters: A...Z, AA..."""
        value = int(index) + 1
        output = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            output = chr(65 + remainder) + output
        return output

    @staticmethod
    def _arrays_match(first, second):
        first = np.asarray(first, dtype=float)
        second = np.asarray(second, dtype=float)
        return first.shape == second.shape and bool(np.allclose(
            first, second, equal_nan=True, rtol=1e-10, atol=1e-12
        ))

    def _unique_column_name(self, requested, *, excluding=None):
        base = str(requested).strip() or "Column"
        used = {
            item["name"] for index, item in enumerate(self._table_columns)
            if index != excluding
        }
        if base not in used:
            return base
        number = 2
        while f"{base}_{number}" in used:
            number += 1
        return f"{base}_{number}"

    def _data_header(self, index):
        item = self._table_columns[index]
        return f"{self._column_code(index)} [{item['role']}] {item['name']}"

    def _refresh_data_headers(self):
        for index in range(self.data_table.columnCount()):
            header = QTableWidgetItem(self._data_header(index))
            header.setData(Qt.ItemDataRole.UserRole, copy.deepcopy(self._table_columns[index]))
            self.data_table.setHorizontalHeaderItem(index, header)
        self.data_table.resizeColumnsToContents()

    def _sync_table_metadata(self):
        restored = []
        for index in range(self.data_table.columnCount()):
            header = self.data_table.horizontalHeaderItem(index)
            metadata = header.data(Qt.ItemDataRole.UserRole) if header else None
            if not isinstance(metadata, dict):
                metadata = {
                    "name": f"Column {index + 1}", "role": "Ignore",
                }
            restored.append(copy.deepcopy(metadata))
        self._table_columns = restored
        self._table_dirty = True
        self._sync_history_list()

    def _rebuild_data_table(self):
        if not hasattr(self, "data_table"):
            return
        columns = []
        values = []
        x_columns = []
        axis_name = str(state.global_set.get("xlabel") or "X")
        for stem in self.stems:
            x_values, y_values = self.data_dict[stem]
            x_values = np.asarray(x_values, dtype=float)
            y_values = np.asarray(y_values, dtype=float)
            x_index = next(
                (index for index in x_columns if self._arrays_match(values[index], x_values)),
                None,
            )
            if x_index is None:
                x_name = axis_name if not x_columns else f"{stem} X"
                x_name = self._unique_name_for_meta(x_name, columns)
                x_index = len(columns)
                columns.append({"name": x_name, "role": "X", "source_stem": stem})
                values.append(x_values)
                x_columns.append(x_index)
            y_name = self._unique_name_for_meta(stem, columns)
            columns.append({
                "name": y_name, "role": "Y", "source_stem": stem,
                "x_index": x_index,
            })
            values.append(y_values)

        self._table_columns = columns
        row_count = max((len(value) for value in values), default=0)
        self._table_loading = True
        self.data_table._history_suspended = True
        self.data_table.setUpdatesEnabled(False)
        self.data_table.clear()
        self.data_table.setRowCount(row_count)
        self.data_table.setColumnCount(len(columns))
        self._refresh_data_headers()
        for column, array in enumerate(values):
            for row, value in enumerate(array):
                text = "" if not np.isfinite(value) else f"{float(value):.12g}"
                if text:
                    self.data_table.setItem(row, column, QTableWidgetItem(text))
        self.data_table.setUpdatesEnabled(True)
        self.data_table._history_suspended = False
        self.data_table.reset_history()
        self._table_loading = False
        self._table_dirty = False
        self._sync_history_list()

    @staticmethod
    def _unique_name_for_meta(requested, metadata):
        used = {item["name"] for item in metadata}
        base = str(requested).strip() or "Column"
        if base not in used:
            return base
        number = 2
        while f"{base}_{number}" in used:
            number += 1
        return f"{base}_{number}"

    def _data_table_changed(self, _item=None):
        if not self._table_loading:
            self._table_dirty = True
            self._sync_history_list()

    def _data_columns_inserted(self, _parent=None, _first=None, _last=None):
        if self._table_loading or self.data_table._history_suspended:
            return
        while len(self._table_columns) < self.data_table.columnCount():
            self._table_columns.append({
                "name": self._unique_column_name(
                    f"Column {len(self._table_columns) + 1}"
                ),
                "role": "Ignore",
            })
        self._refresh_data_headers()
        self._table_dirty = True
        self._sync_history_list()

    def _selected_data_columns(self):
        columns = sorted({index.column() for index in self.data_table.selectedIndexes()})
        if not columns and self.data_table.currentColumn() >= 0:
            columns = [self.data_table.currentColumn()]
        return columns

    def _insert_data_row(self):
        row = self.data_table.currentRow()
        if row < 0:
            row = self.data_table.rowCount()
        self.data_table.begin_command()
        self.data_table.insertRow(row)
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _delete_data_rows(self):
        rows = sorted({index.row() for index in self.data_table.selectedIndexes()}, reverse=True)
        if not rows and self.data_table.currentRow() >= 0:
            rows = [self.data_table.currentRow()]
        if not rows:
            return
        self.data_table.begin_command()
        for row in rows:
            self.data_table.removeRow(row)
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _insert_data_column(self):
        name, accepted = QInputDialog.getText(
            self, "Insert column", "Column name", text=f"Column {len(self._table_columns) + 1}"
        )
        if not accepted or not name.strip():
            return
        column = self.data_table.currentColumn()
        column = self.data_table.columnCount() if column < 0 else column + 1
        self.data_table.begin_command()
        self._table_columns.insert(column, {
            "name": self._unique_column_name(name), "role": "Ignore",
        })
        self.data_table.insertColumn(column)
        self._refresh_data_headers()
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _delete_data_columns(self):
        columns = self._selected_data_columns()
        if not columns:
            return
        if self.data_table.columnCount() - len(columns) < 1:
            QMessageBox.warning(self, "Columns required", "Keep at least one table column.")
            return
        self.data_table.begin_command()
        for column in reversed(columns):
            self.data_table.removeColumn(column)
            self._table_columns.pop(column)
        self._refresh_data_headers()
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _rename_data_column(self):
        column = self.data_table.currentColumn()
        if not 0 <= column < len(self._table_columns):
            return
        current = self._table_columns[column]["name"]
        name, accepted = QInputDialog.getText(
            self, "Rename column", "New column name", text=current
        )
        if not accepted or not name.strip():
            return
        self.data_table.begin_command()
        self._table_columns[column]["name"] = self._unique_column_name(
            name, excluding=column
        )
        self._refresh_data_headers()
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _set_data_column_role(self, role):
        columns = self._selected_data_columns()
        if not columns:
            QMessageBox.information(self, "Select a column", "Select one or more columns first.")
            return
        self.data_table.begin_command()
        for column in columns:
            self._table_columns[column]["role"] = role
        self._refresh_data_headers()
        self.data_table.end_command()
        self._table_dirty = True
        self._sync_history_list()

    def _numeric_table_columns(self):
        output = []
        for column in range(self.data_table.columnCount()):
            values = []
            for row in range(self.data_table.rowCount()):
                item = self.data_table.item(row, column)
                text = item.text().strip() if item else ""
                if not text:
                    values.append(np.nan)
                    continue
                try:
                    values.append(float(text))
                except ValueError as error:
                    name = self._table_columns[column]["name"]
                    raise FormulaError(
                        f"'{text}' in {name}, row {row + 1}, is not numeric."
                    ) from error
            output.append(np.asarray(values, dtype=float))
        return output

    def _create_formula_column(self):
        if not self._table_columns:
            return
        dialog = ColumnFormulaDialog(
            [item["name"] for item in self._table_columns], self,
            suggested_name=f"Calculated {len(self._table_columns) + 1}",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, expression = dialog.result
        try:
            result = evaluate_column_formula(expression, self._numeric_table_columns())
        except FormulaError as error:
            QMessageBox.warning(self, "Formula error", str(error))
            return
        column = self.data_table.columnCount()
        self.data_table.begin_command()
        self._table_columns.append({
            "name": self._unique_column_name(name), "role": "Y", "formula": expression,
        })
        self.data_table.insertColumn(column)
        self._refresh_data_headers()
        for row, value in enumerate(result):
            if np.isfinite(value):
                self.data_table.setItem(row, column, QTableWidgetItem(f"{float(value):.12g}"))
        self.data_table.end_command()
        self._table_dirty = True
        self.data_table.selectColumn(column)
        self._sync_history_list()

    def _x_column_for_y(self, y_column, x_columns):
        preceding = [index for index in x_columns if index < y_column]
        return preceding[-1] if preceding else x_columns[0]

    def _apply_data_table(self):
        try:
            columns = self._numeric_table_columns()
            x_columns = [
                index for index, item in enumerate(self._table_columns) if item["role"] == "X"
            ]
            y_columns = [
                index for index, item in enumerate(self._table_columns) if item["role"] == "Y"
            ]
            if not x_columns or not y_columns:
                raise FormulaError("Mark at least one column [X] and one column [Y].")
            rebuilt = []
            used_names = [
                item[0] for item in state.all_data if item[0] not in self.stems
            ]
            for y_column in y_columns:
                x_column = self._x_column_for_y(y_column, x_columns)
                x_values, y_values = columns[x_column], columns[y_column]
                finite = np.isfinite(x_values) & np.isfinite(y_values)
                if np.count_nonzero(finite) < 3:
                    continue
                name = _unique_label(self._table_columns[y_column]["name"], used_names)
                used_names.append(name)
                rebuilt.append((name, x_values[finite], y_values[finite], y_column))
            if not rebuilt:
                raise FormulaError("No [Y] column has at least three numeric X/Y row pairs.")
        except FormulaError as error:
            QMessageBox.warning(self, "Cannot apply data table", str(error))
            return False

        self._checkpoint_state()
        old_view_stems = list(self.stems)
        old_all_data = list(state.all_data)
        old_data = self.data_dict
        old_settings = state.file_set
        new_data = {}
        new_settings = {
            stem: copy.deepcopy(settings)
            for stem, settings in old_settings.items()
            if stem not in old_view_stems
        }
        renamed_current = None
        for index, (name, x_values, y_values, y_column) in enumerate(rebuilt):
            metadata = self._table_columns[y_column]
            source = metadata.get("source_stem")
            source_settings = old_settings.get(name) or old_settings.get(source)
            settings = copy.deepcopy(source_settings) if source_settings else {
                "custom_name": name,
                "color": PLOT_COLORS[index % len(PLOT_COLORS)],
                "offset": 0.0,
                "smooth": state.settings.get("smooth", 15),
                "labels": [], "areas": [],
                "do_baseline": state.technique == "RAMAN",
                "als_lam": 8.0, "als_p": 0.05,
                "auto_clean_edges": state.technique in {"UVVIS", "RAMAN"},
            }
            old_pair = old_data.get(source or name)
            changed = old_pair is None or not (
                self._arrays_match(old_pair[0], x_values)
                and self._arrays_match(old_pair[1], y_values)
            )
            if changed:
                for key in ("labels", "areas", "deconvs", "xrd_peaks", "manual_baseline_pts"):
                    settings[key] = []
            if name != source:
                settings["custom_name"] = name
            new_data[name] = (np.asarray(x_values), np.asarray(y_values))
            new_settings[name] = settings
            metadata["source_stem"] = name
            if source == self.current_stem or name == self.current_stem:
                renamed_current = name

        self.data_dict = new_data
        self.stems = list(new_data)
        state.file_set = new_settings
        rebuilt_all_data = [
            (stem, self.data_dict[stem][0], self.data_dict[stem][1]) for stem in self.stems
        ]
        viewed_positions = [
            index for index, item in enumerate(old_all_data) if item[0] in old_view_stems
        ]
        if viewed_positions:
            first_position = viewed_positions[0]
            remaining = [item for item in old_all_data if item[0] not in old_view_stems]
            insertion = sum(
                1 for index, item in enumerate(old_all_data[:first_position])
                if item[0] not in old_view_stems
            )
            state.all_data = remaining[:insertion] + rebuilt_all_data + remaining[insertion:]
        else:
            state.all_data = rebuilt_all_data
        self.current_stem = renamed_current if renamed_current in new_data else self.stems[0]
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(self.stems)
        self.file_combo.setCurrentText(self.current_stem)
        self.file_combo.blockSignals(False)
        if state.settings.get("mode") == "individual" and len(self.stems) > 1:
            state.settings["mode"] = "overlay"
            state.mode_switched_mid_session = True
            self.plot_layout_combo.blockSignals(True)
            self.plot_layout_combo.setCurrentIndex(
                max(0, self.plot_layout_combo.findData("overlay"))
            )
            self.plot_layout_combo.blockSignals(False)
        self._table_dirty = False
        self._load_active_settings()
        self._sync_legend_name_list()
        self._refresh_finish_button()
        self.update_plot()
        return True

    def get_processed_data_for_stem(self, stem, *, strict=False):
        raw_x, raw_y = self.data_dict[stem]
        fs = state.file_set[stem]
        x_arr = np.asarray(raw_x, dtype=float)
        y_arr = np.asarray(raw_y, dtype=float).copy()

        if state.technique == "UVVIS":
            y_arr = apply_optical_transform(y_arr, fs.get("uv_transform", "none"))
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
            if strict:
                raise
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
                transform = fs.get("uv_transform", "none")
                target = 100.0 if transform == "absorbance_to_percent_transmittance" else 1.0
                if state.technique == "FTIR" and not fs.get("t2a", False):
                    target = 100.0
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
            "uv_transform": "none",
        }

    def add_files(self, paths=None):
        if self._table_dirty and not self._apply_data_table():
            return
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Add data files", "",
                ("LIBS files (*.zip *.txt *.csv *.tsv *.dat *.xy *.asc *.xlsx *.xls);;All files (*)"
                 if state.technique == "LIBS" else
                 "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.xlsx *.xls);;All files (*)"))
        if not paths:
            return
        datasets, failures = discover_many(paths, minimum_points=11, technique=state.technique)
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
            stem = _unique_label(dataset.name, self.stems)
            self.stems.append(stem)
            self.data_dict[stem] = (x, y)
            state.all_data.append((stem, x, y))
            self._init_file_settings(stem)
            state.file_set[stem]["source"] = dataset.source
            if picker.reference_dataset is not None:
                state.file_set[stem].update(
                    bg_sub=True,
                    bg_filename=picker.reference_dataset.name,
                    bg_data=(picker.reference_dataset.x, picker.reference_dataset.y),
                    bg_mult=1.0,
                )
            self.file_combo.addItem(stem)
        self._rebuild_data_table()
        self._sync_legend_name_list()
        self._sync_workspace_navigation()
        if failures:
            QMessageBox.warning(
                self, "Some files skipped",
                "\n".join(f"{name}: {reason}" for name, reason in failures),
            )
        self.update_plot()

    def import_digitized(self, curve):
        if self._table_dirty and not self._apply_data_table():
            return
        self._checkpoint_state()
        stem = _unique_label(curve.name, self.stems)
        self.stems.append(stem); self.data_dict[stem] = (curve.x, curve.y)
        state.all_data.append((stem, curve.x, curve.y))
        self._init_file_settings(stem)
        state.file_set[stem].update(smooth=0, do_baseline=False, auto_clean_edges=False,
                                   source="Image: " + curve.metadata["source_image"], digitization=curve.metadata)
        if state.settings.get("mode") == "individual":
            state.settings["mode"] = "overlay"
            self.plot_layout_combo.setCurrentIndex(self.plot_layout_combo.findData("overlay"))
        self.file_combo.addItem(stem)
        self._rebuild_data_table(); self._sync_legend_name_list(); self._sync_workspace_navigation()
        self.update_plot()

    def replace_current(self):
        if self._table_dirty and not self._apply_data_table():
            return
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
        fs["source"] = str(path)
        for key in ("labels", "areas", "deconvs", "xrd_peaks", "manual_baseline_pts"):
            fs[key] = []
        self._rebuild_data_table()
        self.update_plot()

    def _read_data_file(self, path):
        if state.technique == "LIBS":
            datasets, failures = discover_many([path], minimum_points=11, technique="LIBS")
            if failures:
                raise ValueError("\n".join(f"{name}: {reason}" for name, reason in failures))
            if len(datasets) != 1:
                raise ValueError("Choose a file containing one spectrum to replace the current data. "
                                 "Use Add files to select spectra from a ZIP or multi-series file.")
            return datasets[0].x, datasets[0].y
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
        self._rebuild_data_table()
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
        self._sync_legend_name_list()
        self._sync_workspace_navigation()
        self._rebuild_data_table()
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

        self.cursors = []
        self.ax, self._artist_to_stem, self._axes_to_stem = self._draw_spectra(
            self.figure, self.stems, interactive=True)

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

    def _draw_spectra(self, figure, stems, *, mode=None, interactive=False):
        figure.clear()
        artist_to_stem = {}
        axes_to_stem = {}
        mode = mode or state.settings.get("mode", "individual")
        is_stack = mode in {"stack", "grid"}
        if mode == "stack":
            axes_value = figure.subplots(len(stems), 1, sharex=True)
            axes = list(np.atleast_1d(axes_value).flat)
        elif mode == "grid":
            columns = max(1, int(math.ceil(math.sqrt(len(stems)))))
            rows = int(math.ceil(len(stems) / columns))
            axes_value = figure.subplots(rows, columns, squeeze=False)
            all_axes = list(np.asarray(axes_value).flat)
            axes = all_axes[:len(stems)]
            for unused in all_axes[len(stems):]:
                unused.set_visible(False)
        else:
            axes = [figure.add_subplot(111)] * len(stems)

        extents = []
        label_padding = {}
        for index, stem in enumerate(stems):
            ax = axes[index]
            if is_stack:
                axes_to_stem[ax] = stem
            fs = state.file_set[stem]
            x, y = self.get_processed_data_for_stem(stem, strict=not interactive)
            if not len(x):
                continue
            extents.append((np.min(x), np.max(x), np.min(y), np.max(y)))
            color = fs.get("color", "black")
            line = ax.plot(
                x, y, label=fs.get("custom_name", stem), color=color,
                linewidth=2.4 if stem == self.current_stem else 1.5,
                picker=6,
            )[0]
            artist_to_stem[line] = stem
            # Fractions are [horizontal, bottom, top]. Horizontal padding
            # protects centered labels on the first/last measured point.
            padding = label_padding.setdefault(ax, [0.0, 0.0, 0.0])
            upward_labels = peak_polarity(
                state.technique, bool(fs.get("t2a", False))
            ) == "up"
            for px, py, text_value in fs.get("labels", []):
                marker = "^" if upward_labels else "v"
                offset = 14 if upward_labels else -14
                vertical_alignment = "bottom" if upward_labels else "top"
                horizontal_alignment, horizontal_offset = self._peak_label_horizontal_position(
                    px, x
                )
                ax.plot(px, py, marker, color=color, markersize=7)
                ax.annotate(
                    text_value, (px, py), xytext=(horizontal_offset, offset),
                    textcoords="offset points", ha=horizontal_alignment, va=vertical_alignment,
                    annotation_clip=True,
                )
                padding[0] = max(padding[0], 0.01)
                padding[2 if upward_labels else 1] = max(
                    padding[2 if upward_labels else 1], 0.09
                )
            for px, py, fwhm, size in fs.get("xrd_peaks", []):
                label = f"2θ: {px:.1f}°"
                if self.show_fwhm_check.isChecked():
                    label += f"\nFWHM: {fwhm:.2f}°\nD: {size:.1f} nm"
                horizontal_alignment, horizontal_offset = self._peak_label_horizontal_position(
                    px, x
                )
                ax.plot(px, py, "o", color=color, markersize=5)
                ax.annotate(
                    label, (px, py), xytext=(horizontal_offset, 10),
                    textcoords="offset points", ha=horizontal_alignment, va="bottom",
                    annotation_clip=True,
                )
                padding[0] = max(padding[0], 0.01)
                padding[2] = max(
                    padding[2], 0.12 if self.show_fwhm_check.isChecked() else 0.07
                )
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
                self._style_axis(ax, extents, is_stack, interactive=interactive)
            for ax, (horizontal_fraction, bottom_fraction, top_fraction) in label_padding.items():
                if horizontal_fraction and not state.global_set.get("xlim"):
                    left, right = ax.get_xlim()
                    span = abs(right - left) or 1.0
                    if left <= right:
                        ax.set_xlim(
                            left - span * horizontal_fraction,
                            right + span * horizontal_fraction,
                        )
                    else:
                        ax.set_xlim(
                            left + span * horizontal_fraction,
                            right - span * horizontal_fraction,
                        )
                if not state.global_set.get("ylim"):
                    bottom, top = ax.get_ylim()
                    span = abs(top - bottom) or 1.0
                    ax.set_ylim(
                        bottom - span * bottom_fraction,
                        top + span * top_fraction,
                    )
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
        return (axes[0] if axes else None), artist_to_stem, axes_to_stem


    @staticmethod
    def _peak_label_horizontal_position(x_value, x_values):
        """Keep centered peak text from crossing the left or right plot border."""
        finite = np.asarray(x_values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if len(finite) < 2:
            return "center", 0
        low, high = float(np.min(finite)), float(np.max(finite))
        span = high - low
        if span <= 0:
            return "center", 0
        fraction = (float(x_value) - low) / span
        if state.technique in {"FTIR", "XPS"}:
            fraction = 1.0 - fraction
        if fraction <= 0.08:
            return "left", 4
        if fraction >= 0.92:
            return "right", -4
        return "center", 0

    def _style_axis(self, ax, extents, is_stack, *, interactive=True):
        gs = state.global_set
        min_x = min(item[0] for item in extents)
        max_x = max(item[1] for item in extents)
        min_y = min(item[2] for item in extents)
        max_y = max(item[3] for item in extents)
        xlim = gs.get("xlim") or [min_x, max_x]
        if state.technique in {"FTIR", "XPS"}:
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
        if interactive:
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

    def _toggle_peak_threshold_fields(self, automatic):
        self.prominence_spin.setEnabled(not automatic)
        self.xrd_height_spin.setEnabled(not automatic)

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
        if mode == "peak" and state.technique in {"FTIR", "UVVIS", "RAMAN", "XPS", "LIBS"}:
            direction = peak_polarity(
                state.technique,
                bool(state.file_set[self.current_stem].get("t2a", False)),
            )
            index = local_extremum_index(x, y, event.xdata, direction=direction)
        closest_x, closest_y = x[index], y[index]
        fs = state.file_set[self.current_stem]
        if mode == "peak":
            self._checkpoint_state()
            fs.setdefault("labels", []).append((closest_x, closest_y, (f"{closest_x:.3f}" if state.technique == "LIBS" else f"{closest_x:.1f}")))
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
        x, y = self.get_processed_data_for_stem(self.current_stem)
        self._checkpoint_state()
        fs = state.file_set[self.current_stem]
        direction = peak_polarity(state.technique, bool(fs.get("t2a", False)))
        automatic = self.auto_peak_threshold_check.isChecked()
        peaks, properties = noise_adaptive_peak_indices(
            y,
            direction=direction,
            maximum=self.maximum_peaks_spin.value(),
            prominence=None if automatic else self.prominence_spin.value(),
            minimum_height=(
                None if automatic or state.technique != "XRD"
                else self.xrd_height_spin.value()
            ),
        )
        used_prominence = float(properties.get("used_prominence", 0.0))
        self.peak_threshold_info.setText(
            f"Found {len(peaks)} peak(s); detection prominence {used_prominence:.4g}."
        )
        if state.technique == "XRD":
            results = fs.setdefault("xrd_peaks", [])
            for index in peaks:
                result = self.calculate_xrd_peak(x[index], x, y)
                if result and not any(abs(item[0] - result[0]) < 0.01 for item in results):
                    results.append(result)
            self.update_plot()
            self.right_sidebar.setCurrentIndex(1)
            return
        existing = fs.setdefault("labels", [])
        for index in peaks:
            if not any(abs(item[0] - x[index]) < (0.001 if state.technique == "LIBS" else 0.1) for item in existing):
                existing.append((x[index], y[index], (f"{x[index]:.3f}" if state.technique == "LIBS" else f"{x[index]:.1f}")))
        self.update_plot()
        self.right_sidebar.setCurrentIndex(1)

    def calculate_xrd_peak(self, x_click, x, y):
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        finite_x = x_values[np.isfinite(x_values)]
        if not len(finite_x):
            return None
        spacing = np.median(np.abs(np.diff(np.unique(np.sort(finite_x))))) if len(finite_x) > 1 else 0.0
        # Snap only to the nearby peak. The former +/-1 degree search could
        # unexpectedly jump from a shoulder to a neighbouring strong peak.
        snap_half_width = max(float(spacing) * 3.0, min(float(np.ptp(finite_x)) * 0.006, 0.5))
        snap_mask = np.abs(x_values - float(x_click)) <= snap_half_width
        snap_mask &= np.isfinite(y_values)
        if not np.any(snap_mask):
            return None
        candidates = np.flatnonzero(snap_mask)
        peak_index = int(candidates[np.argmax(y_values[candidates])])
        peak_x, peak_y = x_values[peak_index], y_values[peak_index]
        measure_mask = np.abs(x_values - peak_x) <= max(1.0, snap_half_width)
        xw, yw = x_values[measure_mask], y_values[measure_mask]
        order = np.argsort(xw)
        xw, yw = xw[order], yw[order]
        index = int(np.abs(xw - peak_x).argmin())
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
        """Compatibility entry point retained for saved UI callbacks."""
        self.auto_find_peaks()

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
        transform = state.file_set[self.current_stem].get("uv_transform", "none")
        signal_kind = {
            "absorbance_to_percent_transmittance": "Transmittance (%)",
            "percent_transmittance_to_absorbance": "Absorbance",
            "reflectance_fraction_to_kubelka_munk": "Kubelka-Munk F(R)",
            "reflectance_percent_to_kubelka_munk": "Kubelka-Munk F(R)",
        }.get(transform)
        dialog = UVVisAnalysisDialog(
            x, y, self.current_stem, self, signal_kind=signal_kind
        )
        dialog.exec()

    def show_raman_analysis(self):
        x, y = self.get_processed_data_for_stem(self.current_stem)
        dialog = RamanAnalysisDialog(x, y, self.current_stem, self)
        dialog.exec()

    def sync_peak_list(self):
        self.peak_list.clear()
        result_lines = []
        fs = state.file_set.get(self.current_stem, {})
        if state.technique == "XRD":
            for px, _py, fwhm, size in fs.get("xrd_peaks", []):
                result_lines.append(f"2θ {px:.2f}° | FWHM {fwhm:.2f}° | {size:.1f} nm")
        elif state.technique == "FTIR":
            for px, _py, text_value in fs.get("labels", []):
                result_lines.append(f"Peak {px:.1f} cm⁻¹ ({text_value})")
        else:
            for px, py, _text_value in fs.get("labels", []):
                result_lines.append(f"Point ({px:.5g}, {py:.5g})")
        for x1, x2, area in fs.get("areas", []):
            result_lines.append(f"Area {area:.3g} ({x1:.2f}–{x2:.2f})")
        self.peak_list.addItems(result_lines)
        if hasattr(self, "results_list"):
            self.results_list.clear()
            if result_lines:
                for line in result_lines:
                    self.results_list.addItem(f"{self.current_stem}  ·  {line}")
            else:
                self.results_list.addItem(
                    "No saved results for this spectrum. Open Analyze to find peaks or measure an area."
                )

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
        self._annotation_list_updated()

    def _annotation_list_updated(self):
        self._sync_annotation_list()
        self._sync_history_list()

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
        self._annotation_list_updated()

    def _delete_annotation(self):
        self.annotation_mgr.delete_selected()
        self._annotation_list_updated()

    def _clear_all_annotations(self):
        if not self.annotation_mgr.annotations:
            return
        answer = QMessageBox.question(
            self, "Clear annotations", "Remove every annotation from this plot?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.annotation_mgr.clear_all()
            self._annotation_list_updated()

    def sync_annotations_to_state(self):
        state.global_set["annotations"] = self.annotation_mgr.get_serialized_data()

    # --------------------------- export/session --------------------------
    def save_session(self, save_as=False):
        if self._table_dirty and not self._apply_data_table():
            return False
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
            "technique": state.technique,
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

    def export_figure(self):
        if self._table_dirty and not self._apply_data_table():
            return
        export_figure_dialog(self, self.figure, f"{self.current_stem}_plot")

    def _spectrum_export_figure(self, stem):
        figure = Figure(figsize=self.figure.get_size_inches())
        self._draw_spectra(figure, [stem], mode="individual")
        figure.tight_layout()
        return figure

    def export_items(self):
        from pandas import DataFrame
        from report_export import setting_lines
        items = []
        for stem in self.stems:
            fs = copy.deepcopy(state.file_set[stem])
            x, y = self.get_processed_data_for_stem(stem, strict=True)
            results = []
            for px, py, label in fs.get("labels", []):
                results.append(f"Peak: X={px:.7g}; Y={py:.7g}; label={label}")
            for x1, x2, area in fs.get("areas", []):
                results.append(f"Integrated area: {x1:.7g} to {x2:.7g}; area={area:.7g}")
            for px, py, fwhm, size in fs.get("xrd_peaks", []):
                results.append(f"XRD: 2-theta={px:.7g}; intensity={py:.7g}; FWHM={fwhm:.7g}; crystallite size={size:.7g} nm")
            for index, fit in enumerate(fs.get("deconvs", []), 1):
                results.extend(setting_lines({f"Deconvolution {index}": {
                    "range": fit[:2], "Gaussian amplitude/center/sigma parameters": fit[3],
                    "components": fit[4], "valleys": fit[5] if len(fit) > 5 else False}}))
            settings = {"technique": state.technique, "processing": fs,
                        "axes": copy.deepcopy(state.global_set), "original_points": len(self.data_dict[stem][0])}
            settings["processing"] = {k: v for k, v in fs.items() if k not in {"labels", "areas", "xrd_peaks", "deconvs"}}
            xlabel = state.global_set.get("xlabel", "X") or "X"
            ylabel = state.global_set.get("ylabel", "Y") or "Y"
            if ylabel == xlabel:
                ylabel += " (Y)"
            items.append(ExportItem(fs.get("custom_name", stem), lambda key=stem: self._spectrum_export_figure(key),
                                    DataFrame({xlabel: x, ylabel: y}), results, settings, fs.get("source", stem)))
        return items

    def export_data(self):
        if self._table_dirty and not self._apply_data_table():
            return
        try:
            export_batch_dialog(self, self.export_items())
        except Exception as error:
            QMessageBox.critical(self, "Export error", str(error))

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
        if self.embedded:
            label = "Close analysis"
        else:
            label = "Next Spectrum" if self._has_next_individual_spectrum() else "Finish & Close"
        self.finish_button.setText(label)

    def _request_close(self):
        if self.embedded:
            self.closeRequested.emit(self)
        else:
            self.close()

    def finish_current(self):
        if self._table_dirty and not self._apply_data_table():
            return
        if self.embedded:
            self.closeRequested.emit(self)
            return
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
