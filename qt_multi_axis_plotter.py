"""Editable multi-X and multi-Y 2D plotting workspace."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from annotations import AnnotationManager
from plot_export import save_figure
from qt_general_plotter import DataTable, read_table
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import AnnotationToolBar, CompactNavigationToolbar, PanelToggleButton


COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2"]


class MultiAxisPlotter(QWidget):
    """Plot independent X/Y column pairs against bottom/top and left/right axes."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpectraSuite Multi-X / Multi-Y Plotter")
        self.resize(1550, 900)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(LIGHT_STYLE)
        apply_window_icon(self, "MULTIAXIS")
        self.loaded_files = []
        self._loading = False
        self._build_ui()
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_list_update_callback=lambda _items: self._sync_annotations(),
            text_input_provider=self._annotation_text,
        )
        self._install_shortcuts()
        self._set_dataframe(pd.DataFrame({"X1": [""] * 25, "Y1": [""] * 25}))
        self.add_mapping()

    def _build_ui(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        for label, slot in (
            ("New table", self.new_table), ("Add file", self.add_file),
            ("Save data", self.save_data), ("Export graph", self.export_graph),
        ):
            button = QPushButton(label); button.clicked.connect(slot); top.addWidget(button)
        top.addStretch(); root.addLayout(top)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(True); root.addWidget(self.splitter, 1)

        self.data_panel = QWidget(); data_layout = QVBoxLayout(self.data_panel)
        data_layout.setContentsMargins(0, 0, 4, 0)
        self.file_label = QLabel("Manual data - type values or paste from Excel")
        self.file_label.setWordWrap(True); data_layout.addWidget(self.file_label)
        self.table = DataTable(); self.table.itemChanged.connect(self._table_changed)
        self.table.model().columnsInserted.connect(lambda *_args: self._refresh_mapping_columns())
        data_layout.addWidget(self.table, 1)
        edit = QHBoxLayout()
        for label, slot in (("+ Row", self.add_row), ("- Row", self.delete_rows),
                            ("+ Column", self.add_column), ("- Column", self.delete_columns),
                            ("Rename", self.rename_column)):
            button = QPushButton(label); button.clicked.connect(slot); edit.addWidget(button)
        data_layout.addLayout(edit)
        self.splitter.addWidget(self.data_panel)

        self.plot_panel = QWidget(); plot_layout = QVBoxLayout(self.plot_panel)
        plot_layout.setContentsMargins(4, 0, 4, 0)
        self.figure = Figure(figsize=(8, 6), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure); self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        plot_layout.addWidget(self.canvas, 1)
        self.toolbar = CompactNavigationToolbar(self.canvas, self.plot_panel)
        toolbar_row = QHBoxLayout(); toolbar_row.addWidget(self.toolbar, 1)
        self.toolbar_toggle = PanelToggleButton(self.toolbar, "bottom", self.plot_panel)
        toolbar_row.addWidget(self.toolbar_toggle); plot_layout.addLayout(toolbar_row)
        self.splitter.addWidget(self.plot_panel)

        settings = QWidget(); settings.setMinimumWidth(390)
        settings_layout = QVBoxLayout(settings); settings_layout.setContentsMargins(4, 0, 0, 0)
        mapping_group = QGroupBox("Series mapping")
        mapping_layout = QVBoxLayout(mapping_group)
        mapping_layout.addWidget(QLabel(
            "Each row may use a different X and Y column. Assign it to a bottom/top X axis "
            "and a left/right Y axis."
        ))
        self.mapping_table = QTableWidget(0, 7)
        self.mapping_table.setHorizontalHeaderLabels(
            ["Show", "X column", "Y column", "X axis", "Y axis", "Label", "Color"]
        )
        self.mapping_table.itemChanged.connect(self.plot_data)
        self.mapping_table.setMinimumHeight(220)
        mapping_layout.addWidget(self.mapping_table)
        mapping_buttons = QHBoxLayout()
        add = QPushButton("+ Series"); add.clicked.connect(self.add_mapping)
        remove = QPushButton("- Series"); remove.clicked.connect(self.remove_mapping)
        mapping_buttons.addWidget(add); mapping_buttons.addWidget(remove)
        mapping_layout.addLayout(mapping_buttons); settings_layout.addWidget(mapping_group)

        axes_group = QGroupBox("Titles and axes"); axes_form = QFormLayout(axes_group)
        self.title_edit = QLineEdit(); self.bottom_x_edit = QLineEdit("Bottom X")
        self.top_x_edit = QLineEdit("Top X"); self.left_y_edit = QLineEdit("Left Y")
        self.right_y_edit = QLineEdit("Right Y")
        self.grid_check = QCheckBox("Show grid"); self.legend_check = QCheckBox("Show legend")
        self.legend_check.setChecked(True)
        axes_form.addRow("Title", self.title_edit); axes_form.addRow("Bottom X label", self.bottom_x_edit)
        axes_form.addRow("Top X label", self.top_x_edit); axes_form.addRow("Left Y label", self.left_y_edit)
        axes_form.addRow("Right Y label", self.right_y_edit); axes_form.addRow(self.grid_check)
        axes_form.addRow(self.legend_check); settings_layout.addWidget(axes_group)

        ann_group = QGroupBox("Annotations"); ann_layout = QVBoxLayout(ann_group)
        self.annotation_tool = AnnotationToolBar()
        self.annotation_tool.currentIndexChanged.connect(self._set_annotation_tool)
        ann_layout.addWidget(self.annotation_tool)
        self.annotation_list = QListWidget(); self.annotation_list.setMaximumHeight(75)
        self.annotation_list.currentRowChanged.connect(self._select_annotation)
        ann_layout.addWidget(self.annotation_list)
        ann_buttons = QHBoxLayout()
        for label, slot in (("Undo", self._undo_annotation), ("Redo", self._redo_annotation),
                            ("Delete", self._delete_annotation), ("Clear all", self._clear_annotations)):
            button = QPushButton(label); button.clicked.connect(slot); ann_buttons.addWidget(button)
        ann_layout.addLayout(ann_buttons); settings_layout.addWidget(ann_group)
        plot = QPushButton("Plot / refresh"); plot.setObjectName("primary"); plot.clicked.connect(self.plot_data)
        settings_layout.addWidget(plot); settings_layout.addStretch()
        self.settings_scroll = QScrollArea(); self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setWidget(settings); self.splitter.addWidget(self.settings_scroll)
        self.splitter.setSizes([430, 720, 430])

        self.data_toggle = PanelToggleButton(self.data_panel, "left", self)
        self.settings_toggle = PanelToggleButton(self.settings_scroll, "right", self)
        top.insertWidget(4, self.data_toggle); top.insertWidget(5, self.settings_toggle)

    def _columns(self):
        columns = []
        for index in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(index)
            columns.append(header.text() if header is not None else f"Column {index + 1}")
        return columns

    def _combo(self, values, current=""):
        combo = QComboBox(); combo.addItems(values)
        if current in values: combo.setCurrentText(current)
        combo.currentTextChanged.connect(self.plot_data)
        return combo

    def add_mapping(self):
        columns = self._columns()
        if len(columns) < 2:
            return
        was_loading = self._loading
        self._loading = True
        try:
            row = self.mapping_table.rowCount(); self.mapping_table.insertRow(row)
            show = QCheckBox(); show.setChecked(True); show.toggled.connect(self.plot_data)
            holder = QWidget(); holder_layout = QHBoxLayout(holder); holder_layout.setContentsMargins(8, 0, 0, 0)
            holder_layout.addWidget(show); holder_layout.addStretch(); self.mapping_table.setCellWidget(row, 0, holder)
            self.mapping_table.setCellWidget(row, 1, self._combo(columns, columns[0]))
            self.mapping_table.setCellWidget(row, 2, self._combo(columns, columns[min(row + 1, len(columns) - 1)]))
            self.mapping_table.setCellWidget(row, 3, self._combo(["Bottom", "Top"], "Bottom"))
            self.mapping_table.setCellWidget(row, 4, self._combo(["Left", "Right"], "Left" if row == 0 else "Right"))
            self.mapping_table.setItem(row, 5, QTableWidgetItem(columns[min(row + 1, len(columns) - 1)]))
            color_button = QPushButton(COLORS[row % len(COLORS)]); color_button.setStyleSheet(
                f"background:{COLORS[row % len(COLORS)]}; color:white"
            )
            color_button.clicked.connect(lambda _checked=False, b=color_button: self._choose_color(b))
            self.mapping_table.setCellWidget(row, 6, color_button)
        finally:
            self._loading = was_loading
        if not self._loading:
            self.plot_data()

    def remove_mapping(self):
        rows = sorted({index.row() for index in self.mapping_table.selectedIndexes()}, reverse=True)
        if not rows and self.mapping_table.currentRow() >= 0: rows = [self.mapping_table.currentRow()]
        for row in rows: self.mapping_table.removeRow(row)
        self.plot_data()

    def _choose_color(self, button):
        color = QColorDialog.getColor(QColor(button.text()), self, "Series color")
        if color.isValid():
            button.setText(color.name()); button.setStyleSheet(f"background:{color.name()}; color:white")
            self.plot_data()

    def _mapping(self, row):
        widgets = [self.mapping_table.cellWidget(row, column) for column in range(7)]
        if any(widget is None for index, widget in enumerate(widgets) if index != 5):
            return None
        show = widgets[0].findChild(QCheckBox)
        if show is None:
            return None
        return {
            "show": show.isChecked(),
            "x": widgets[1].currentText(),
            "y": widgets[2].currentText(),
            "x_axis": widgets[3].currentText(),
            "y_axis": widgets[4].currentText(),
            "label": self.mapping_table.item(row, 5).text() if self.mapping_table.item(row, 5) else "",
            "color": widgets[6].text(),
        }

    def plot_data(self, *_args):
        if self._loading or self.mapping_table.rowCount() == 0: return
        frame = self._dataframe()
        if frame.empty: return
        annotations = self.annotation_mgr.get_serialized_data() if hasattr(self, "annotation_mgr") else []
        self.figure.clear(); base = self.figure.add_subplot(111)
        axes = {("Bottom", "Left"): base}
        def get_axis(x_axis, y_axis):
            key = (x_axis, y_axis)
            if key in axes: return axes[key]
            if key == ("Bottom", "Right"):
                axes[key] = base.twinx()
            elif key == ("Top", "Left"):
                axes[key] = base.twiny()
            else:
                top_left = axes.get(("Top", "Left")) or base.twiny()
                axes[("Top", "Left")] = top_left
                axes[key] = top_left.twinx()
                axes[key].spines["right"].set_position(("axes", 1.0))
            return axes[key]
        handles, labels = [], []
        for row in range(self.mapping_table.rowCount()):
            item = self._mapping(row)
            if item is None or not item["show"] or item["x"] not in frame or item["y"] not in frame: continue
            x = pd.to_numeric(frame[item["x"]], errors="coerce").to_numpy(float)
            y = pd.to_numeric(frame[item["y"]], errors="coerce").to_numpy(float)
            valid = np.isfinite(x) & np.isfinite(y)
            if not np.any(valid): continue
            axis = get_axis(item["x_axis"], item["y_axis"])
            line = axis.plot(x[valid], y[valid], color=item["color"], linewidth=1.9,
                             label=item["label"] or item["y"])[0]
            handles.append(line); labels.append(line.get_label())
            axis.tick_params(axis="x" if item["x_axis"] == "Top" else "y", colors=item["color"])
        base.set_title(self.title_edit.text()); base.set_xlabel(self.bottom_x_edit.text())
        base.set_ylabel(self.left_y_edit.text())
        if ("Top", "Left") in axes: axes[("Top", "Left")].set_xlabel(self.top_x_edit.text())
        for key, axis in axes.items():
            if key[1] == "Right": axis.set_ylabel(self.right_y_edit.text())
        if self.grid_check.isChecked(): base.grid(True, alpha=.3)
        if self.legend_check.isChecked() and handles: base.legend(handles, labels, loc="best")
        if hasattr(self, "annotation_mgr"):
            self.annotation_mgr.annotations = []; self.annotation_mgr.selected_artist = None
            self.annotation_mgr.active_ax = base
            if annotations: self.annotation_mgr.load_serialized_data(annotations, base)
        self.canvas.draw_idle()

    def _set_dataframe(self, frame):
        self._loading = True; self.table._history_suspended = True
        self.table.clear(); self.table.setRowCount(max(25, len(frame))); self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for row in range(len(frame)):
            for col in range(len(frame.columns)):
                value = frame.iat[row, col]
                self.table.setItem(row, col, QTableWidgetItem("" if pd.isna(value) else str(value)))
        self.table._history_suspended = False; self.table.reset_history(); self._loading = False

    def _dataframe(self):
        headers = self._columns(); rows = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().strip() if self.table.item(row, col) else ""
                      for col in range(self.table.columnCount())]
            if any(values): rows.append(values)
        return pd.DataFrame(rows, columns=headers)

    def _refresh_mapping_columns(self):
        if self._loading:
            return
        columns = self._columns()
        for row in range(self.mapping_table.rowCount()):
            for col in (1, 2):
                combo = self.mapping_table.cellWidget(row, col)
                if combo is None:
                    continue
                current = combo.currentText()
                combo.blockSignals(True); combo.clear(); combo.addItems(columns)
                if current in columns: combo.setCurrentText(current)
                combo.blockSignals(False)

    def new_table(self, _checked=False):
        self.loaded_files = []; self.mapping_table.setRowCount(0)
        self._set_dataframe(pd.DataFrame({"X1": [""] * 25, "Y1": [""] * 25}))
        self.file_label.setText("Manual data - type values or paste from Excel"); self.add_mapping()
        self.figure.clear(); self.canvas.draw_idle()

    def add_file(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Add tabular data", "",
            "Data (*.csv *.tsv *.txt *.dat *.xy *.xlsx *.xls);;All files (*)")
        for name in names:
            try: incoming = read_table(Path(name))
            except Exception as error:
                QMessageBox.warning(self, "Import error", f"Could not import {Path(name).name}:\n{error}"); continue
            current = self._dataframe()
            if not current.empty:
                incoming = incoming.rename(columns={c: f"{Path(name).stem}.{c}" for c in incoming if c in current})
                incoming = pd.concat([current.reset_index(drop=True), incoming.reset_index(drop=True)], axis=1)
            self._set_dataframe(incoming); self.loaded_files.append(name)
        if names:
            self.file_label.setText("Imported: " + ", ".join(Path(n).name for n in self.loaded_files))
            self.mapping_table.setRowCount(0); self.add_mapping()

    def add_row(self):
        self.table.insertRow(self.table.currentRow() + 1 if self.table.currentRow() >= 0 else self.table.rowCount())

    def delete_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True): self.table.removeRow(row)

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Add column", "Column name")
        if ok and name:
            col = self.table.columnCount(); self.table.insertColumn(col)
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name)); self._refresh_mapping_columns()

    def delete_columns(self):
        columns = sorted({i.column() for i in self.table.selectedIndexes()}, reverse=True)
        if self.table.columnCount() - len(columns) < 2:
            QMessageBox.warning(self, "Columns required", "Keep at least two columns."); return
        for col in columns: self.table.removeColumn(col)
        self._refresh_mapping_columns()

    def rename_column(self):
        col = self.table.currentColumn()
        if col < 0: return
        old = self.table.horizontalHeaderItem(col).text()
        name, ok = QInputDialog.getText(self, "Rename column", "New name", text=old)
        if ok and name:
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name)); self._refresh_mapping_columns()

    def save_data(self):
        name, selected = QFileDialog.getSaveFileName(self, "Save data", "multi_axis_data.csv",
                                                     "CSV (*.csv);;Excel (*.xlsx)")
        if not name: return
        try:
            if "Excel" in selected or name.lower().endswith(".xlsx"):
                self._dataframe().to_excel(name if name.lower().endswith(".xlsx") else name + ".xlsx", index=False)
            else: self._dataframe().to_csv(name, index=False)
        except Exception as error: QMessageBox.critical(self, "Save error", str(error))

    def export_graph(self):
        name, selected = QFileDialog.getSaveFileName(self, "Export graph", "multi_axis.png",
                                                     "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tiff)")
        if name:
            try: save_figure(self.figure, name, selected_filter=selected)
            except Exception as error: QMessageBox.critical(self, "Export error", str(error))

    def _table_changed(self, _item):
        if not self._loading: self.plot_data()

    def _annotation_text(self):
        text, ok = QInputDialog.getText(self, "Text annotation", "Text")
        return text if ok and text.strip() else None

    def _set_annotation_tool(self): self.annotation_mgr.set_tool(self.annotation_tool.currentData())
    def _sync_annotations(self):
        self.annotation_list.clear()
        for i, (_artist, kind) in enumerate(self.annotation_mgr.annotations): self.annotation_list.addItem(f"{i + 1}. {kind.title()}")
    def _select_annotation(self, row):
        if row >= 0: self.annotation_mgr.select_by_index(row)
    def _undo_annotation(self): self.annotation_mgr.undo()
    def _redo_annotation(self): self.annotation_mgr.redo()
    def _delete_annotation(self): self.annotation_mgr.delete_selected()
    def _clear_annotations(self):
        if self.annotation_mgr.annotations and QMessageBox.question(
            self, "Clear annotations", "Remove every annotation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes: self.annotation_mgr.clear_all()

    def _install_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self); self.undo_shortcut.activated.connect(self._undo_annotation)
        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self); self.redo_shortcut.activated.connect(self._redo_annotation)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self); self.delete_shortcut.activated.connect(self._delete_annotation)
        self.backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self); self.backspace_shortcut.activated.connect(self._delete_annotation)
