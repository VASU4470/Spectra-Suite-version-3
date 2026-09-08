"""Spreadsheet-style, general-purpose 2D plotting workspace."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu,
    QListWidget, QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from annotations import AnnotationManager
from plot_export import save_figure
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import CompactNavigationToolbar, PanelToggleButton


STYLE = LIGHT_STYLE


class DataTable(QTableWidget):
    """Editable grid with spreadsheet-compatible copy, paste, and delete."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.undo_stack, self.redo_stack = [], []
        self._history_suspended = False
        self._last_state = self._snapshot()
        self.itemChanged.connect(self._capture_edit)

    def _snapshot(self):
        return {
            "rows": self.rowCount(), "columns": self.columnCount(),
            "headers": [
                self.horizontalHeaderItem(col).text() if self.horizontalHeaderItem(col) else ""
                for col in range(self.columnCount())
            ],
            "cells": [
                [self.item(row, col).text() if self.item(row, col) else ""
                 for col in range(self.columnCount())]
                for row in range(self.rowCount())
            ],
        }

    def reset_history(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._last_state = self._snapshot()

    def begin_command(self):
        if self._history_suspended:
            return
        self._command_before = self._snapshot()
        self._history_suspended = True

    def end_command(self):
        before = getattr(self, "_command_before", self._last_state)
        self._history_suspended = False
        after = self._snapshot()
        if before != after:
            self.undo_stack.append(before)
            del self.undo_stack[:-100]
            self.redo_stack.clear()
        self._last_state = after

    def _capture_edit(self, _item):
        if self._history_suspended:
            return
        current = self._snapshot()
        if current != self._last_state:
            self.undo_stack.append(self._last_state)
            del self.undo_stack[:-100]
            self.redo_stack.clear()
            self._last_state = current

    def _restore(self, snapshot):
        self._history_suspended = True
        self.clear()
        self.setRowCount(snapshot["rows"])
        self.setColumnCount(snapshot["columns"])
        self.setHorizontalHeaderLabels(snapshot["headers"])
        for row, values in enumerate(snapshot["cells"]):
            for col, value in enumerate(values):
                if value:
                    self.setItem(row, col, QTableWidgetItem(value))
        self._history_suspended = False
        self._last_state = self._snapshot()

    def undo_edit(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())
        return True

    def redo_edit(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())
        return True

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            rows = [line.split("\t") for line in QApplication.clipboard().text().rstrip("\n").splitlines()]
            if not rows:
                return
            start_row, start_col = max(0, self.currentRow()), max(0, self.currentColumn())
            self.begin_command()
            self.setRowCount(max(self.rowCount(), start_row + len(rows)))
            self.setColumnCount(max(self.columnCount(), start_col + max(map(len, rows))))
            for row_offset, values in enumerate(rows):
                for col_offset, value in enumerate(values):
                    self.setItem(start_row + row_offset, start_col + col_offset, QTableWidgetItem(value))
            self.end_command()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            ranges = self.selectedRanges()
            if ranges:
                selected = ranges[0]
                lines = []
                for row in range(selected.topRow(), selected.bottomRow() + 1):
                    lines.append("\t".join(
                        self.item(row, col).text() if self.item(row, col) else ""
                        for col in range(selected.leftColumn(), selected.rightColumn() + 1)
                    ))
                QApplication.clipboard().setText("\n".join(lines))
            return
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.begin_command()
            for item in self.selectedItems():
                item.setText("")
            self.end_command()
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo_edit()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo_edit()
            return
        super().keyPressEvent(event)


def _looks_numeric(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _unique_headers(headers):
    used, output = {}, []
    for header in headers:
        count = used.get(header, 0) + 1
        used[header] = count
        output.append(header if count == 1 else f"{header}_{count}")
    return output


def read_table(path: Path):
    """Read a complete delimited-text or Excel table while preserving columns."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
        if all(_looks_numeric(value) for value in frame.columns):
            frame = pd.read_excel(path, header=None)
    else:
        separator = detect_delimiter(path)
        frame = pd.read_csv(path, sep=separator, engine="python")
        if all(_looks_numeric(value) for value in frame.columns):
            frame = pd.read_csv(path, sep=separator, engine="python", header=None)
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("The file contains no tabular data.")
    frame.columns = _unique_headers([
        str(value).strip() if str(value).strip() else f"Column {index + 1}"
        for index, value in enumerate(frame.columns)
    ])
    return frame


def detect_delimiter(path: Path):
    """Detect comma, tab, semicolon, or arbitrary whitespace separation."""
    sample = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    if not sample.strip():
        raise ValueError("The file is empty.")
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",\t; ").delimiter
    except csv.Error:
        delimiter = " "
    return r"\s+" if delimiter == " " else delimiter


class GeneralPlotter(QWidget):
    CHARTS = ["Line", "Scatter", "Bar", "Area", "Step", "Pie", "Histogram", "Box"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpectraSuite General 2D Plotter")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 680)
        self.setStyleSheet(STYLE)
        apply_window_icon(self, "GENERAL")
        self.loaded_files, self.series_styles = [], {}
        self._loading_table = False
        self._build_ui()
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_list_update_callback=lambda _items: self._sync_annotation_list(),
            text_input_provider=self._annotation_text,
        )
        self._install_shortcuts()
        self.new_table(confirm=False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        for text, slot in (("New blank table", self.new_table), ("Add file", self.add_file),
                           ("Save data", self.save_data), ("Save project", self.save_project),
                           ("Open project", self.open_project), ("Export graph", self.export_graph)):
            button = QPushButton(text); button.clicked.connect(slot); top.addWidget(button)
        panels = QPushButton("Panels ▾")
        panel_menu = QMenu(panels)
        self.panel_actions = {}
        for label, slot in (
            ("Data table", self._set_data_panel_visible),
            ("Plot options", self._set_controls_visible),
            ("Plot toolbar", self._set_toolbar_visible),
        ):
            action = panel_menu.addAction(label)
            action.setCheckable(True); action.setChecked(True)
            action.toggled.connect(slot)
            self.panel_actions[label] = action
        panels.setMenu(panel_menu); top.addWidget(panels)
        top.addStretch(); root.addLayout(top)
        self.splitter = QSplitter(Qt.Orientation.Horizontal); self.splitter.setChildrenCollapsible(True)
        root.addWidget(self.splitter, 1)

        self.data_panel = QWidget(); data_layout = QVBoxLayout(self.data_panel)
        data_layout.setContentsMargins(0, 0, 4, 0)
        self.file_label = QLabel("Manual data"); self.file_label.setWordWrap(True)
        data_layout.addWidget(self.file_label)
        self.table = DataTable(); self.table.itemChanged.connect(self._table_changed)
        self.table.model().columnsInserted.connect(
            lambda *_args: None if self._loading_table else self._refresh_columns()
        )
        data_layout.addWidget(self.table, 1)
        edit_row = QHBoxLayout()
        for text, slot in (("+ Row", self.add_row), ("− Row", self.delete_rows),
                           ("+ Column", self.add_column), ("− Column", self.delete_columns),
                           ("Rename", self.rename_column)):
            button = QPushButton(text); button.clicked.connect(slot); edit_row.addWidget(button)
        data_layout.addLayout(edit_row)
        table_history = QHBoxLayout()
        for text, slot in (("↶ Undo data", self._undo_table), ("↷ Redo data", self._redo_table)):
            button = QPushButton(text); button.clicked.connect(slot); table_history.addWidget(button)
        data_layout.addLayout(table_history)
        data_layout.addWidget(QLabel("Paste rectangular data from Excel with Ctrl/Cmd+V."))
        self.splitter.addWidget(self.data_panel)

        self.plot_panel = QWidget(); plot_layout = QVBoxLayout(self.plot_panel)
        plot_layout.setContentsMargins(4, 0, 4, 0)
        self.figure = Figure(figsize=(8, 6), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        plot_layout.addWidget(self.canvas, 1)
        self.toolbar = CompactNavigationToolbar(self.canvas, self.plot_panel)
        toolbar_row = QHBoxLayout(); toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.addWidget(self.toolbar, 1)
        self.toolbar_toggle = PanelToggleButton(self.toolbar, "bottom", self.plot_panel)
        toolbar_row.addWidget(self.toolbar_toggle)
        plot_layout.addLayout(toolbar_row)
        self.splitter.addWidget(self.plot_panel)

        controls = QWidget(); controls.setMinimumWidth(260)
        controls_layout = QVBoxLayout(controls); controls_layout.setContentsMargins(4, 0, 0, 0)
        mapping = QGroupBox("Data mapping"); mapping_form = QFormLayout(mapping)
        mapping_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.x_column = QComboBox()
        self.y_columns = QListWidget(); self.y_columns.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.y_columns.setMinimumHeight(115)
        self.chart_type = QComboBox(); self.chart_type.addItems(self.CHARTS)
        mapping_form.addRow("X / category", self.x_column); mapping_form.addRow("Y column(s)", self.y_columns)
        y_buttons = QWidget(); y_row = QHBoxLayout(y_buttons); y_row.setContentsMargins(0, 0, 0, 0)
        select_all_y = QPushButton("Select all Y")
        select_all_y.clicked.connect(self._select_all_y)
        clear_y = QPushButton("Clear Y selection")
        clear_y.clicked.connect(self.y_columns.clearSelection)
        y_row.addWidget(select_all_y); y_row.addWidget(clear_y)
        mapping_form.addRow("Ctrl/Cmd selects multiple", y_buttons)
        mapping_form.addRow("Chart type", self.chart_type); controls_layout.addWidget(mapping)

        labels = QGroupBox("Titles and labels"); label_form = QFormLayout(labels)
        label_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title_edit, self.xlabel_edit, self.ylabel_edit = QLineEdit(), QLineEdit(), QLineEdit()
        self.legend_check = QCheckBox("Show legend"); self.legend_check.setChecked(True)
        self.grid_check, self.data_labels_check = QCheckBox("Show grid"), QCheckBox("Show data labels")
        label_form.addRow("Graph title", self.title_edit); label_form.addRow("X-axis", self.xlabel_edit)
        label_form.addRow("Y-axis", self.ylabel_edit); label_form.addRow(self.legend_check)
        label_form.addRow(self.grid_check); label_form.addRow(self.data_labels_check)
        controls_layout.addWidget(labels)

        style = QGroupBox("Selected series style"); style_form = QFormLayout(style)
        style_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.style_series = QComboBox(); self.color_edit = QLineEdit("#1f77b4")
        color_button = QPushButton("Choose color"); color_button.clicked.connect(self.choose_color)
        self.line_style = QComboBox(); self.line_style.addItems(["Solid", "Dashed", "Dotted", "Dash-dot", "None"])
        self.marker = QComboBox(); self.marker.addItems(["None", "Circle", "Square", "Triangle", "Diamond", "Plus", "Cross"])
        self.line_width = QDoubleSpinBox(); self.line_width.setRange(0.1, 20); self.line_width.setValue(1.8)
        self.bar_width = QDoubleSpinBox(); self.bar_width.setRange(0.05, 1.0); self.bar_width.setSingleStep(0.05); self.bar_width.setValue(0.8)
        for field in (self.style_series, self.color_edit, self.line_style, self.marker,
                      self.line_width, self.bar_width):
            field.setMinimumWidth(210)
        style_form.addRow("Series", self.style_series); style_form.addRow("Color", self.color_edit)
        style_form.addRow("", color_button); style_form.addRow("Line", self.line_style)
        style_form.addRow("Marker", self.marker); style_form.addRow("Line width", self.line_width)
        style_form.addRow("Bar width", self.bar_width); controls_layout.addWidget(style)

        annotation = QGroupBox("Annotations")
        annotation_layout = QVBoxLayout(annotation)
        self.annotation_tool = QComboBox()
        for label, value in (
            ("Select / move", "none"), ("Text", "text"), ("Arrow", "arrow"),
            ("Line", "line"), ("Rectangle", "rect"), ("Ellipse", "circle"),
        ):
            self.annotation_tool.addItem(label, value)
        self.annotation_tool.currentIndexChanged.connect(self._set_annotation_tool)
        annotation_layout.addWidget(self.annotation_tool)
        self.annotation_list = QListWidget()
        self.annotation_list.setMaximumHeight(90)
        self.annotation_list.currentRowChanged.connect(self._select_annotation)
        annotation_layout.addWidget(self.annotation_list)
        annotation_buttons = QGridLayout()
        for index, (text, slot) in enumerate((
            ("↶ Undo", self._undo_annotation), ("↷ Redo", self._redo_annotation),
            ("⌫ Delete", self._delete_annotation), ("🗑 Clear all", self._clear_annotations),
        )):
            button = QPushButton(text); button.clicked.connect(slot)
            annotation_buttons.addWidget(button, index // 2, index % 2)
        annotation_layout.addLayout(annotation_buttons)
        controls_layout.addWidget(annotation)
        self.auto_plot = QCheckBox("Update graph while editing"); controls_layout.addWidget(self.auto_plot)
        plot_button = QPushButton("Plot / refresh"); plot_button.setObjectName("primary"); plot_button.clicked.connect(self.plot_data)
        controls_layout.addWidget(plot_button); controls_layout.addStretch()
        self.controls_scroll = QScrollArea(); self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setWidget(controls); self.controls_scroll.setMinimumWidth(260)
        self.splitter.addWidget(self.controls_scroll)
        self.splitter.setSizes([460, 650, 420])

        self.data_toggle = PanelToggleButton(self.data_panel, "left", self)
        self.options_toggle = PanelToggleButton(self.controls_scroll, "right", self)
        top.insertWidget(6, self.data_toggle)
        top.insertWidget(7, self.options_toggle)
        self.data_toggle.toggled.connect(
            lambda hidden: self.panel_actions["Data table"].setChecked(not hidden)
        )
        self.options_toggle.toggled.connect(
            lambda hidden: self.panel_actions["Plot options"].setChecked(not hidden)
        )
        self.toolbar_toggle.toggled.connect(
            lambda hidden: self.panel_actions["Plot toolbar"].setChecked(not hidden)
        )

        self.x_column.currentTextChanged.connect(self._mapping_changed)
        self.y_columns.itemSelectionChanged.connect(self._mapping_changed)
        self.chart_type.currentTextChanged.connect(self.plot_data)
        self.style_series.currentTextChanged.connect(self._load_series_style)
        for widget in (self.title_edit, self.xlabel_edit, self.ylabel_edit): widget.editingFinished.connect(self.plot_data)
        for widget in (self.legend_check, self.grid_check, self.data_labels_check): widget.toggled.connect(self.plot_data)
        self.line_style.currentTextChanged.connect(self._save_series_style); self.marker.currentTextChanged.connect(self._save_series_style)
        self.color_edit.editingFinished.connect(self._save_series_style); self.line_width.valueChanged.connect(self._save_series_style)
        self.bar_width.valueChanged.connect(self._save_series_style)

    def _set_data_panel_visible(self, visible):
        self.data_toggle.set_panel_visible(visible)

    def _set_controls_visible(self, visible):
        self.options_toggle.set_panel_visible(visible)

    def _set_toolbar_visible(self, visible):
        self.toolbar_toggle.set_panel_visible(visible)

    def _install_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.activated.connect(self._undo_active)
        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.redo_shortcut.activated.connect(self._redo_active)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.delete_shortcut.activated.connect(self._delete_active)
        self.backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self.backspace_shortcut.activated.connect(self._delete_active)

    def _focus_in_table(self):
        focus = QApplication.focusWidget()
        return focus is self.table or (focus is not None and self.table.isAncestorOf(focus))

    def _undo_active(self):
        if self._focus_in_table():
            if self.table.undo_edit():
                self._refresh_columns()
                self.plot_data()
        else:
            self._undo_annotation()

    def _undo_table(self):
        if self.table.undo_edit():
            self._refresh_columns()
            self.plot_data()

    def _redo_active(self):
        if self._focus_in_table():
            if self.table.redo_edit():
                self._refresh_columns()
                self.plot_data()
        else:
            self._redo_annotation()

    def _redo_table(self):
        if self.table.redo_edit():
            self._refresh_columns()
            self.plot_data()

    def _delete_active(self):
        if self._focus_in_table():
            self.table.begin_command()
            for item in self.table.selectedItems():
                item.setText("")
            self.table.end_command()
        else:
            self._delete_annotation()

    def _annotation_text(self):
        text, accepted = QInputDialog.getText(self, "Text annotation", "Annotation text")
        return text if accepted and text.strip() else None

    def _set_annotation_tool(self):
        self.annotation_mgr.set_tool(self.annotation_tool.currentData())
        self.canvas.setFocus()

    def _sync_annotation_list(self):
        self.annotation_list.blockSignals(True)
        self.annotation_list.clear()
        for index, (artist, kind) in enumerate(self.annotation_mgr.annotations):
            suffix = f": {artist.get_text()[:20]}" if kind == "text" else ""
            self.annotation_list.addItem(f"{index + 1}. {kind.title()}{suffix}")
        self.annotation_list.blockSignals(False)

    def _select_annotation(self, row):
        if row >= 0:
            self.annotation_mgr.select_by_index(row)
            self.canvas.setFocus()

    def _undo_annotation(self):
        self.annotation_mgr.undo()

    def _redo_annotation(self):
        self.annotation_mgr.redo()

    def _delete_annotation(self):
        self.annotation_mgr.delete_selected()

    def _clear_annotations(self):
        if not self.annotation_mgr.annotations:
            return
        if QMessageBox.question(
            self, "Clear annotations", "Remove every annotation from this graph?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.annotation_mgr.clear_all()

    def new_table(self, _checked=False, confirm=True):
        if confirm and QMessageBox.question(self, "Start new table", "Clear the current table and graph?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if hasattr(self, "annotation_mgr"):
            self.annotation_mgr._clear_artists()
            self.annotation_mgr.undo_stack.clear()
            self.annotation_mgr.redo_stack.clear()
        self.loaded_files, self.series_styles = [], {}
        self._set_dataframe(pd.DataFrame({"X": [""]*25, "Y": [""]*25}))
        self.file_label.setText("Manual data — type values below or paste from Excel")
        self.title_edit.clear(); self.xlabel_edit.setText("X"); self.ylabel_edit.setText("Y")
        self.figure.clear(); self.canvas.draw_idle()

    def add_file(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Add data table", "",
            "Data tables (*.csv *.tsv *.txt *.dat *.xy *.xlsx *.xls);;All files (*)")
        for filename in filenames:
            path = Path(filename)
            try: incoming = read_table(path)
            except Exception as error:
                QMessageBox.warning(self, "Import error", f"Could not import {path.name}:\n{error}"); continue
            current = self._dataframe(False)
            if current.empty:
                merged = incoming.reset_index(drop=True)
            else:
                incoming = incoming.rename(columns={c: f"{path.stem}.{c}" for c in incoming.columns if c in current.columns})
                merged = pd.concat([current.reset_index(drop=True), incoming.reset_index(drop=True)], axis=1)
            self.loaded_files.append(str(path)); self._set_dataframe(merged)
        if self.loaded_files: self.file_label.setText("Imported: " + ", ".join(Path(f).name for f in self.loaded_files))

    def _set_dataframe(self, frame):
        self._loading_table = True; self.table._history_suspended = True
        self.table.clear(); self.table.setRowCount(max(25, len(frame)))
        self.table.setColumnCount(len(frame.columns)); self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for row in range(len(frame)):
            for col in range(len(frame.columns)):
                value = frame.iat[row, col]; self.table.setItem(row, col, QTableWidgetItem("" if pd.isna(value) else str(value)))
        self._loading_table = False; self.table._history_suspended = False
        self.table.reset_history(); self._refresh_columns()

    def _dataframe(self, include_blank=True):
        headers = [self.table.horizontalHeaderItem(c).text() if self.table.horizontalHeaderItem(c) else f"Column {c+1}" for c in range(self.table.columnCount())]
        rows = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().strip() if self.table.item(row, col) else "" for col in range(self.table.columnCount())]
            if include_blank or any(values): rows.append(values)
        return pd.DataFrame(rows, columns=_unique_headers(headers))

    def _refresh_columns(self):
        headers = [
            self.table.horizontalHeaderItem(i).text()
            if self.table.horizontalHeaderItem(i) else f"Column {i+1}"
            for i in range(self.table.columnCount())
        ]
        old_x, old_y = self.x_column.currentText(), {i.text() for i in self.y_columns.selectedItems()}
        self.x_column.blockSignals(True); self.y_columns.blockSignals(True)
        self.x_column.clear(); self.x_column.addItems(headers); self.y_columns.clear(); self.y_columns.addItems(headers)
        if old_x in headers: self.x_column.setCurrentText(old_x)
        for index in range(self.y_columns.count()):
            item = self.y_columns.item(index)
            if item.text() in old_y or (not old_y and index == min(1, len(headers)-1)): item.setSelected(True)
        self.x_column.blockSignals(False); self.y_columns.blockSignals(False); self._mapping_changed()

    def _mapping_changed(self):
        selected = [i.text() for i in self.y_columns.selectedItems()]; current = self.style_series.currentText()
        self.style_series.blockSignals(True); self.style_series.clear(); self.style_series.addItems(selected)
        if current in selected: self.style_series.setCurrentText(current)
        self.style_series.blockSignals(False); self._load_series_style()
        if self.auto_plot.isChecked(): self.plot_data()

    def _select_all_y(self):
        x_name = self.x_column.currentText()
        for index in range(self.y_columns.count()):
            item = self.y_columns.item(index)
            item.setSelected(item.text() != x_name)

    def _table_changed(self, _item):
        if not self._loading_table and self.auto_plot.isChecked(): self.plot_data()

    def add_row(self):
        self.table.begin_command()
        self.table.insertRow(self.table.currentRow()+1 if self.table.currentRow() >= 0 else self.table.rowCount())
        self.table.end_command()

    def delete_rows(self):
        self.table.begin_command()
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True): self.table.removeRow(row)
        self.table.end_command()

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Add column", "Column name", text=f"Column {self.table.columnCount()+1}")
        if ok and name:
            self.table.begin_command()
            col = self.table.columnCount(); self.table.insertColumn(col); self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name))
            self.table.end_command(); self._refresh_columns()

    def delete_columns(self):
        columns = sorted({i.column() for i in self.table.selectedIndexes()}, reverse=True)
        if not columns and self.table.currentColumn() >= 0: columns = [self.table.currentColumn()]
        if self.table.columnCount()-len(columns) < 1:
            QMessageBox.warning(self, "Columns required", "Keep at least one column."); return
        self.table.begin_command()
        for col in columns: self.table.removeColumn(col)
        self.table.end_command()
        self._refresh_columns()

    def rename_column(self):
        col = self.table.currentColumn()
        if col < 0: return
        old = self.table.horizontalHeaderItem(col).text(); name, ok = QInputDialog.getText(self, "Rename column", "New name", text=old)
        if ok and name:
            self.table.begin_command(); self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name))
            self.table.end_command(); self._refresh_columns()

    def _default_style(self, series):
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        names = [self.style_series.itemText(i) for i in range(self.style_series.count())]
        index = names.index(series) if series in names else 0
        return {"color": colors[index % len(colors)], "line": "Solid", "marker": "None", "line_width": 1.8, "bar_width": 0.8}

    def _load_series_style(self):
        series = self.style_series.currentText()
        if not series: return
        style = self.series_styles.setdefault(series, self._default_style(series))
        widgets = (self.color_edit, self.line_style, self.marker, self.line_width, self.bar_width)
        for widget in widgets: widget.blockSignals(True)
        self.color_edit.setText(style["color"]); self.line_style.setCurrentText(style["line"]); self.marker.setCurrentText(style["marker"])
        self.line_width.setValue(style["line_width"]); self.bar_width.setValue(style["bar_width"])
        for widget in widgets: widget.blockSignals(False)

    def _save_series_style(self, *_args):
        series = self.style_series.currentText()
        if series:
            self.series_styles[series] = {"color": self.color_edit.text() or "#1f77b4", "line": self.line_style.currentText(),
                "marker": self.marker.currentText(), "line_width": self.line_width.value(), "bar_width": self.bar_width.value()}
            self.plot_data()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color_edit.text()), self, "Series color")
        if color.isValid(): self.color_edit.setText(color.name()); self._save_series_style()

    def plot_data(self, *_args):
        x_name, y_names = self.x_column.currentText(), [i.text() for i in self.y_columns.selectedItems()]
        frame = self._dataframe(False)
        if not x_name or not y_names or frame.empty: return
        annotations = []
        if hasattr(self, "annotation_mgr"):
            annotations = self.annotation_mgr.get_serialized_data()
            self.annotation_mgr.annotations = []
            self.annotation_mgr.selected_artist = None
        chart = self.chart_type.currentText(); self.figure.clear(); ax = self.figure.add_subplot(111)
        x_raw = frame[x_name]; x_numeric = pd.to_numeric(x_raw, errors="coerce")
        x_is_numeric = x_numeric.notna().sum() == x_raw.replace("", np.nan).notna().sum()
        x_plot = x_numeric.to_numpy(float) if x_is_numeric else np.arange(len(frame), dtype=float)
        line_map = {"Solid":"-", "Dashed":"--", "Dotted":":", "Dash-dot":"-.", "None":"None"}
        marker_map = {"None":"", "Circle":"o", "Square":"s", "Triangle":"^", "Diamond":"D", "Plus":"+", "Cross":"x"}
        plotted = 0
        for series_index, y_name in enumerate(y_names):
            y = pd.to_numeric(frame[y_name], errors="coerce").to_numpy(float); valid = np.isfinite(y) & np.isfinite(x_plot)
            if not np.any(valid): continue
            xv, yv = x_plot[valid], y[valid]; style = self.series_styles.setdefault(y_name, self._default_style(y_name))
            common = {"label": y_name, "color": style["color"]}; artist = None
            if chart == "Line": artist = ax.plot(xv, yv, linestyle=line_map[style["line"]], marker=marker_map[style["marker"]], linewidth=style["line_width"], **common)[0]
            elif chart == "Scatter": artist = ax.scatter(xv, yv, **common)
            elif chart == "Step": artist = ax.step(xv, yv, where="mid", linestyle=line_map[style["line"]], linewidth=style["line_width"], **common)[0]
            elif chart == "Bar":
                width = style["bar_width"]/max(1, len(y_names)); offset = (series_index-(len(y_names)-1)/2)*width
                artist = ax.bar(xv+offset, yv, width=width, **common)
            elif chart == "Area": artist = ax.fill_between(xv, yv, alpha=.45, **common)
            elif chart == "Histogram": artist = ax.hist(yv, bins="auto", alpha=.6, **common)[2]
            elif chart == "Box":
                artist = ax.boxplot(yv, positions=[series_index], tick_labels=[y_name], patch_artist=True); artist["boxes"][0].set_facecolor(style["color"])
            elif chart == "Pie":
                if series_index: continue
                pie_values = np.clip(yv, 0, None)
                if not np.any(pie_values > 0):
                    QMessageBox.warning(self, "Pie chart", "A pie chart requires at least one positive Y value.")
                    self.figure.clear(); self.canvas.draw_idle(); return
                ax.pie(pie_values, labels=x_raw[valid].astype(str).to_numpy(), autopct="%1.1f%%" if self.data_labels_check.isChecked() else None)
            plotted += 1
            if self.data_labels_check.isChecked() and chart not in {"Pie", "Histogram", "Box"}:
                for px, py in zip(xv, yv): ax.annotate(f"{py:.4g}", (px, py), xytext=(0,5), textcoords="offset points", ha="center", fontsize=8)
        if not x_is_numeric and chart not in {"Histogram", "Box", "Pie"}:
            labels = x_raw.astype(str).tolist(); ax.set_xticks(np.arange(len(labels)), labels, rotation=30, ha="right")
        ax.set_title(self.title_edit.text()); ax.set_xlabel(self.xlabel_edit.text() or (x_name if chart not in {"Histogram","Box"} else "Value"))
        ax.set_ylabel(self.ylabel_edit.text() or ("Frequency" if chart == "Histogram" else "Value"))
        if self.grid_check.isChecked() and chart != "Pie": ax.grid(True, alpha=.3)
        if self.legend_check.isChecked() and plotted and chart not in {"Pie","Box"}: ax.legend()
        if hasattr(self, "annotation_mgr"):
            self.annotation_mgr.active_ax = ax
            if annotations:
                self.annotation_mgr.load_serialized_data(annotations, ax)
        self.canvas.draw_idle()

    def save_data(self):
        filename, selected = QFileDialog.getSaveFileName(self, "Save edited data", "plot_data.csv", "CSV (*.csv);;Excel (*.xlsx)")
        if not filename: return
        try:
            frame = self._dataframe(False)
            if filename.lower().endswith(".xlsx") or "Excel" in selected: frame.to_excel(filename if filename.lower().endswith(".xlsx") else filename+".xlsx", index=False)
            else: frame.to_csv(filename, index=False)
        except Exception as error: QMessageBox.critical(self, "Save error", str(error))

    def export_graph(self):
        filename, selected = QFileDialog.getSaveFileName(self, "Export graph", "graph.png", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if filename:
            try: save_figure(self.figure, filename, selected_filter=selected, dpi=300)
            except Exception as error: QMessageBox.critical(self, "Export error", str(error))

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save plotter project", "plot_project.json", "Plot projects (*.json)")
        if not filename: return
        frame = self._dataframe()
        data = {"columns":list(frame.columns), "rows":frame.values.tolist(), "files":self.loaded_files, "styles":self.series_styles,
            "x":self.x_column.currentText(), "y":[i.text() for i in self.y_columns.selectedItems()], "chart":self.chart_type.currentText(),
            "title":self.title_edit.text(), "xlabel":self.xlabel_edit.text(), "ylabel":self.ylabel_edit.text(),
            "legend":self.legend_check.isChecked(), "grid":self.grid_check.isChecked(), "data_labels":self.data_labels_check.isChecked(),
            "annotations":self.annotation_mgr.get_serialized_data()}
        try: Path(filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as error: QMessageBox.critical(self, "Save error", str(error))

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open plotter project", "", "Plot projects (*.json)")
        if not filename: return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8")); self.loaded_files = data.get("files", []); self.series_styles = data.get("styles", {})
            self.annotation_mgr._clear_artists()
            self.annotation_mgr.undo_stack.clear(); self.annotation_mgr.redo_stack.clear()
            self._set_dataframe(pd.DataFrame(data["rows"], columns=data["columns"])); self.x_column.setCurrentText(data.get("x", ""))
            wanted = set(data.get("y", []))
            for index in range(self.y_columns.count()): self.y_columns.item(index).setSelected(self.y_columns.item(index).text() in wanted)
            self.chart_type.setCurrentText(data.get("chart", "Line")); self.title_edit.setText(data.get("title", ""))
            self.xlabel_edit.setText(data.get("xlabel", "")); self.ylabel_edit.setText(data.get("ylabel", ""))
            self.legend_check.setChecked(data.get("legend", True)); self.grid_check.setChecked(data.get("grid", False)); self.data_labels_check.setChecked(data.get("data_labels", False))
            self.file_label.setText("Project: " + Path(filename).name); self.plot_data()
            if data.get("annotations") and self.figure.axes:
                self.annotation_mgr.load_serialized_data(data["annotations"], self.figure.axes[0])
                self.canvas.draw_idle()
        except (OSError, ValueError, KeyError, TypeError) as error: QMessageBox.critical(self, "Project error", str(error))
