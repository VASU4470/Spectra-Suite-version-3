"""PySide6 plotting workspace for the FT-IR and XRD applications."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon
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
    QVBoxLayout,
    QWidget,
)
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from annotations import AnnotationManager
from config import state
from processing import process_spectrum
from readers import read_generic_configured, robust_read_spectrum


STYLE = """
QDialog, QWidget { background: #1e1e2e; color: #cdd6f4; }
QTabWidget::pane, QGroupBox {
    border: 1px solid #45475a; border-radius: 7px; margin-top: 7px;
}
QGroupBox { font-weight: 700; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {
    background: #181825; color: #cdd6f4; border: 1px solid #45475a;
    border-radius: 4px; padding: 4px;
}
QPushButton {
    background: #313244; color: #cdd6f4; border: 1px solid #45475a;
    border-radius: 5px; padding: 6px;
}
QPushButton:hover { background: #45475a; border-color: #89b4fa; }
QPushButton#primary { background: #89b4fa; color: #11111b; font-weight: 700; }
QLabel#cursor { color: #89b4fa; font-weight: 700; }
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


class PlotViewer(QDialog):
    """Qt-native data viewer retaining the existing processing state model."""

    def __init__(self, data_tuples, title: str, out_dir=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1450, 850)
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(STYLE)

        icon_name = {
            "XRD": "xrd_icon.png", "FTIR": "ir_icon.png", "GENERAL": "icon.png"
        }.get(state.technique, "icon.png")
        icon_path = Path(__file__).resolve().parent / icon_name
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

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

        self._build_layout()
        self._build_controls()
        self._connect_canvas()
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_select_callback=self._annotation_selected,
            on_list_update_callback=lambda _items: self._sync_annotation_list(),
            text_input_provider=self._request_annotation_text,
        )
        self._load_active_settings()
        self.update_plot()

    # ------------------------------- UI ---------------------------------
    def _build_layout(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        self.controls = QWidget()
        self.controls.setMinimumWidth(365)
        self.controls.setMaximumWidth(500)
        self.controls_layout = QVBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(0, 0, 4, 0)
        splitter.addWidget(self.controls)

        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(4, 0, 0, 0)
        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toolbar = NavigationToolbar2QT(self.canvas, plot_panel)
        self.cursor_label = QLabel("X: -- | Y: --")
        self.cursor_label.setObjectName("cursor")
        self.cursor_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas, 1)
        plot_layout.addWidget(self.cursor_label)
        splitter.addWidget(plot_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _build_controls(self):
        self.tabs = QTabWidget()
        self.controls_layout.addWidget(self.tabs, 1)
        self._build_file_tab()
        self._build_axes_tab()
        self._build_annotation_tab()
        self._build_analysis_tab()

        self.finish_button = QPushButton(
            "Next Spectrum" if state.settings.get("mode") == "individual" else "Close Viewer"
        )
        self.finish_button.setObjectName("primary")
        self.finish_button.clicked.connect(self.finish_current)
        self.controls_layout.addWidget(self.finish_button)

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
        row = QHBoxLayout()
        for label, slot in (
            ("Add", self.add_files), ("Replace", self.replace_current), ("Remove", self.remove_current)
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            row.addWidget(button)
        manage_layout.addLayout(row)
        order = QHBoxLayout()
        up = QPushButton("Move Up")
        up.clicked.connect(lambda: self.move_current(-1))
        down = QPushButton("Move Down")
        down.clicked.connect(lambda: self.move_current(1))
        order.addWidget(up)
        order.addWidget(down)
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
        apply_button = QPushButton("Apply axes settings")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self.save_and_update)
        layout.addWidget(apply_button)

    def _build_annotation_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Annotate")
        tools = QGroupBox("Drawing Tool")
        tools_layout = QVBoxLayout(tools)
        self.annotation_tool = QComboBox()
        self.annotation_tool.addItem("Select / move", "none")
        for label, value in (
            ("Text", "text"), ("Arrow", "arrow"), ("Line", "line"),
            ("Rectangle", "rect"), ("Ellipse", "circle")
        ):
            self.annotation_tool.addItem(label, value)
        self.annotation_tool.currentIndexChanged.connect(self._set_annotation_tool)
        tools_layout.addWidget(self.annotation_tool)
        tools_layout.addWidget(QLabel("Draw on the graph. Use arrow keys to nudge a selection."))
        layout.addWidget(tools)

        props = QGroupBox("Selected Object")
        form = QFormLayout(props)
        self.ann_text_edit = QLineEdit()
        self.ann_color_edit = QLineEdit("black")
        self.ann_width_spin = QDoubleSpinBox()
        self.ann_width_spin.setRange(0.1, 20)
        self.ann_width_spin.setValue(2.0)
        self.ann_size_spin = QDoubleSpinBox()
        self.ann_size_spin.setRange(4, 100)
        self.ann_size_spin.setValue(12)
        self.ann_bold_check = QCheckBox("Bold")
        self.ann_italic_check = QCheckBox("Italic")
        form.addRow("Text", self.ann_text_edit)
        form.addRow("Color", self.ann_color_edit)
        form.addRow("Line width", self.ann_width_spin)
        form.addRow("Font size", self.ann_size_spin)
        form.addRow(self.ann_bold_check)
        form.addRow(self.ann_italic_check)
        apply_props = QPushButton("Apply properties")
        apply_props.clicked.connect(self._apply_annotation_properties)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_annotation)
        form.addRow(apply_props)
        form.addRow(delete)
        layout.addWidget(props)
        self.annotation_list = QListWidget()
        self.annotation_list.currentRowChanged.connect(self._select_annotation_row)
        layout.addWidget(self.annotation_list)

    def _build_analysis_tab(self):
        tab, layout = self._scroll_tab()
        self.tabs.addTab(tab, "Analyze")
        interactive = QGroupBox("Interactive Tools")
        form = QFormLayout(interactive)
        self.click_mode = QComboBox()
        self.click_mode.addItem("Navigation", "none")
        if state.technique == "XRD":
            self.click_mode.addItem("Pick XRD peak", "xrd_peak")
        elif state.technique == "GENERAL":
            self.click_mode.addItem("Pick point", "peak")
        else:
            self.click_mode.addItem("Pick FT-IR peak", "peak")
        self.click_mode.addItem("Calculate area", "area")
        self.click_mode.addItem("Draw manual baseline", "baseline")
        if state.technique == "FTIR":
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
        form.addRow("XRD minimum height", self.xrd_height_spin)
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

        export = QPushButton("Export data, report and graph")
        export.clicked.connect(self.export_data)
        save = QPushButton("Save workspace session")
        save.clicked.connect(lambda: self.save_session(save_as=True))
        layout.addWidget(export)
        layout.addWidget(save)

    def _connect_canvas(self):
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("button_press_event", lambda _event: self.canvas.setFocus())

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
        self.sync_peak_list()

    def save_and_update(self):
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
        )
        self.update_plot()

    def apply_to_all(self):
        self.save_and_update()
        source = state.file_set[self.current_stem]
        keys = ("smooth", "do_baseline", "normalize", "derivative", "als_lam", "t2a", "offset")
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
        self.baseline_check.setChecked(False)
        self.als_spin.setValue(8.0)
        self.derivative_combo.setCurrentIndex(0)
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

    def _select_file(self, stem):
        if stem and stem in self.data_dict:
            self.current_stem = stem
            self._load_active_settings()
            self.update_plot()

    # ------------------------------- data --------------------------------
    def get_processed_data_for_stem(self, stem):
        raw_x, raw_y = self.data_dict[stem]
        fs = state.file_set[stem]
        try:
            x, y = process_spectrum(raw_x, raw_y, stem)
        except Exception:
            x, y = raw_x, raw_y
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)

        if fs.get("t2a", False):
            y_arr = 2 - np.log10(np.clip(y_arr, 0.0001, None))
        if fs.get("bg_sub", False) and "bg_data" in fs:
            bg_x, bg_y = (np.asarray(item) for item in fs["bg_data"])
            order = np.argsort(bg_x)
            y_arr -= np.interp(x_arr, bg_x[order], bg_y[order]) * fs.get("bg_mult", 1.0)
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
        return x_arr, y_arr

    def _init_file_settings(self, stem):
        index = len(state.file_set)
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        state.file_set[stem] = {
            "custom_name": stem, "color": colors[index % len(colors)], "offset": 0.0,
            "smooth": state.settings.get("smooth", 15), "labels": [], "areas": [],
            "do_baseline": False, "als_lam": 8.0, "als_p": 0.05,
        }

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add data files", "", "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.xlsx *.xls);;All files (*)"
        )
        if not paths:
            return
        if state.technique == "GENERAL" and not self._ensure_general_format(Path(paths[0])):
            return
        if state.settings.get("mode") == "individual" and self.stems:
            choice = QMessageBox(self)
            choice.setWindowTitle("Add Files")
            choice.setText("How should the new files be displayed with the current spectrum?")
            choice.addButton("Overlay", QMessageBox.ButtonRole.AcceptRole)
            stack = choice.addButton("Stacked grid", QMessageBox.ButtonRole.ActionRole)
            cancel = choice.addButton(QMessageBox.StandardButton.Cancel)
            choice.exec()
            if choice.clickedButton() == cancel:
                return
            state.settings["mode"] = "stack" if choice.clickedButton() == stack else "overlay"
            state.mode_switched_mid_session = True
            self.finish_button.setText("Close Viewer")
        failed = []
        for value in paths:
            path = Path(value)
            try:
                x, y = self._read_data_file(path)
                if len(x) <= 10:
                    raise ValueError("not enough numeric rows")
            except Exception:
                failed.append(path.name)
                continue
            stem = _unique_stem(path, self.stems)
            self.stems.append(stem)
            self.data_dict[stem] = (x, y)
            state.all_data.append((stem, x, y))
            self._init_file_settings(stem)
            self.file_combo.addItem(stem)
        if failed:
            QMessageBox.warning(self, "Files Skipped", "Could not read:\n" + "\n".join(failed))
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
        self.stems[old], self.stems[new] = self.stems[new], self.stems[old]
        state.all_data.sort(key=lambda item: self.stems.index(item[0]))
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(self.stems)
        self.file_combo.setCurrentText(self.current_stem)
        self.file_combo.blockSignals(False)
        self.update_plot()

    # ------------------------------ plotting -----------------------------
    def update_plot(self):
        annotations = None
        if hasattr(self, "annotation_mgr"):
            annotations = self.annotation_mgr.get_serialized_data() or self._pending_annotations
            self.annotation_mgr.annotations = []
            self.annotation_mgr.selected_artist = None
            self._pending_annotations = []

        self.figure.clear()
        self.cursors = []
        mode = state.settings.get("mode", "individual")
        is_stack = mode == "stack"
        if is_stack:
            axes_value = self.figure.subplots(len(self.stems), 1, sharex=True)
            axes = list(np.atleast_1d(axes_value).flat)
        else:
            axes = [self.figure.add_subplot(111)] * len(self.stems)

        extents = []
        for index, stem in enumerate(self.stems):
            ax = axes[index]
            fs = state.file_set[stem]
            x, y = self.get_processed_data_for_stem(stem)
            if not len(x):
                continue
            extents.append((np.min(x), np.max(x), np.min(y), np.max(y)))
            color = fs.get("color", "black")
            ax.plot(x, y, label=fs.get("custom_name", stem), color=color, linewidth=1.5)
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

        unique_axes = list(dict.fromkeys(axes))
        if extents:
            for ax in unique_axes:
                self._style_axis(ax, extents, is_stack)
        if mode == "overlay":
            axes[0].legend(loc="best", fontsize=8)
        else:
            for ax in unique_axes:
                ax.legend(loc="upper right", fontsize=8)
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
        if mode == "none" or event.inaxes is None or event.xdata is None:
            return
        x, y = self.get_processed_data_for_stem(self.current_stem)
        index = int(np.abs(x - event.xdata).argmin())
        closest_x, closest_y = x[index], y[index]
        fs = state.file_set[self.current_stem]
        if mode == "peak":
            fs.setdefault("labels", []).append((closest_x, closest_y, f"{closest_x:.1f}"))
            self.update_plot()
        elif mode == "xrd_peak":
            result = self.calculate_xrd_peak(event.xdata, x, y)
            if result:
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

    def apply_manual_baseline(self):
        if len(self.baseline_pts) < 2:
            QMessageBox.warning(self, "Baseline", "Click at least two baseline points first.")
            return
        state.file_set[self.current_stem]["manual_baseline_pts"] = list(self.baseline_pts)
        self.baseline_pts = []
        self.click_mode.setCurrentIndex(0)
        self.update_plot()

    def clear_manual_baseline(self):
        state.file_set[self.current_stem]["manual_baseline_pts"] = []
        self.baseline_pts = []
        self.update_plot()

    def auto_find_peaks(self):
        if state.technique == "XRD":
            self.auto_find_xrd_peaks()
            return
        x, y = self.get_processed_data_for_stem(self.current_stem)
        fs = state.file_set[self.current_stem]
        search_y = y if state.technique == "GENERAL" or fs.get("t2a", False) else -y
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
        state.file_set[self.current_stem].setdefault("deconvs", []).append(
            (x1, x2, baseline, params, count, valley)
        )
        self.click_mode.setCurrentIndex(0)
        self.update_plot()

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
        text_value, accepted = QInputDialog.getText(self, "Text Box", "Annotation text:")
        return text_value if accepted and text_value else None

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
        if kind == "text":
            self.ann_text_edit.setText(artist.get_text())
            self.ann_color_edit.setText(str(artist.get_color()))
            self.ann_size_spin.setValue(float(artist.get_fontsize()))
            self.ann_bold_check.setChecked(artist.get_fontweight() == "bold")
            self.ann_italic_check.setChecked(artist.get_fontstyle() == "italic")
        else:
            color = artist.get_color() if kind == "line" else artist.get_edgecolor()
            try:
                color = to_hex(color)
            except ValueError:
                color = str(color)
            self.ann_color_edit.setText(color)
            self.ann_width_spin.setValue(float(artist.get_linewidth()))

    def _apply_annotation_properties(self):
        self.annotation_mgr.update_selected_properties({
            "text": self.ann_text_edit.text(), "color": self.ann_color_edit.text() or "black",
            "fontsize": self.ann_size_spin.value(), "linewidth": self.ann_width_spin.value(),
            "bold": self.ann_bold_check.isChecked(), "italic": self.ann_italic_check.isChecked(),
        })
        self._sync_annotation_list()

    def _delete_annotation(self):
        self.annotation_mgr.delete_selected()
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
        folder = QFileDialog.getExistingDirectory(self, "Select export folder")
        if not folder:
            return
        destination = Path(folder)
        fs = state.file_set[self.current_stem]
        x, y = self.get_processed_data_for_stem(self.current_stem)
        try:
            header = {
                "FTIR": "Wavenumber,Intensity", "XRD": "2-Theta,Intensity",
                "GENERAL": "X,Y",
            }.get(state.technique, "X,Y")
            np.savetxt(
                destination / f"{self.current_stem}_processed.csv",
                np.column_stack((x, y)), delimiter=",", header=header, comments="",
            )
            self._write_report(destination / f"{self.current_stem}_analysis_report.txt", fs)
            self.figure.savefig(destination / f"{self.current_stem}_plot.png", dpi=300, bbox_inches="tight")
            self._export_deconvolutions(destination, fs)
        except (OSError, ValueError) as error:
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
            ("3200–3600", "O–H stretch", "Broad, strong"),
            ("3300–3500", "N–H stretch", "Medium"),
            ("2850–3000", "C–H stretch", "Medium/strong"),
            ("2100–2260", "C≡C / C≡N", "Weak/medium"),
            ("1650–1750", "C=O stretch", "Strong"),
            ("1000–1300", "C–O stretch", "Strong"),
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
        first.bar(labels, sizes, color="#89b4fa", edgecolor="black")
        first.axhline(average, color="red", linestyle="--", label=f"Average {average:.1f} nm")
        first.set_ylabel("Crystallite size (nm)")
        first.legend()
        if len(sizes) > 1:
            second.hist(sizes, bins=max(3, len(sizes)), color="#a6adc8", edgecolor="black")
        else:
            second.text(0.5, 0.5, "At least two peaks are needed", ha="center", va="center")
        second.set_xlabel("Crystallite size (nm)")
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
            figure.savefig(filename, dpi=300, bbox_inches="tight")

    # ------------------------------ closing ------------------------------
    def finish_current(self):
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
