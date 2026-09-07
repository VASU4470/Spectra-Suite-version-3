"""Spreadsheet-style, general-purpose 2D plotting workspace."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


STYLE = """
QWidget { background: #1e1e2e; color: #cdd6f4; }
QGroupBox { border: 1px solid #45475a; border-radius: 7px; margin-top: 8px;
            padding-top: 8px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit, QComboBox, QDoubleSpinBox, QListWidget, QTableWidget {
    background: #181825; color: #cdd6f4; border: 1px solid #45475a;
    border-radius: 4px; padding: 3px; }
QPushButton { background: #313244; color: #cdd6f4; border: 1px solid #45475a;
              border-radius: 5px; padding: 6px; }
QPushButton:hover { background: #45475a; border-color: #89b4fa; }
QPushButton#primary { background: #89b4fa; color: #11111b; font-weight: 700; }
"""


class DataTable(QTableWidget):
    """Editable grid with spreadsheet-compatible copy, paste, and delete."""

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            rows = [line.split("\t") for line in QApplication.clipboard().text().rstrip("\n").splitlines()]
            if not rows:
                return
            start_row, start_col = max(0, self.currentRow()), max(0, self.currentColumn())
            self.setRowCount(max(self.rowCount(), start_row + len(rows)))
            self.setColumnCount(max(self.columnCount(), start_col + max(map(len, rows))))
            for row_offset, values in enumerate(rows):
                for col_offset, value in enumerate(values):
                    self.setItem(start_row + row_offset, start_col + col_offset, QTableWidgetItem(value))
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
            for item in self.selectedItems():
                item.setText("")
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
        frame = pd.read_csv(path, sep=None, engine="python")
        if all(_looks_numeric(value) for value in frame.columns):
            frame = pd.read_csv(path, sep=None, engine="python", header=None)
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("The file contains no tabular data.")
    frame.columns = _unique_headers([
        str(value).strip() if str(value).strip() else f"Column {index + 1}"
        for index, value in enumerate(frame.columns)
    ])
    return frame


class GeneralPlotter(QWidget):
    CHARTS = ["Line", "Scatter", "Bar", "Area", "Step", "Pie", "Histogram", "Box"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpectraSuite General 2D Plotter")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 680)
        self.setStyleSheet(STYLE)
        self.loaded_files, self.series_styles = [], {}
        self._loading_table = False
        self._build_ui()
        self.new_table(confirm=False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        for text, slot in (("New blank table", self.new_table), ("Add file", self.add_file),
                           ("Save data", self.save_data), ("Save project", self.save_project),
                           ("Open project", self.open_project), ("Export graph", self.export_graph)):
            button = QPushButton(text); button.clicked.connect(slot); top.addWidget(button)
        top.addStretch(); root.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Horizontal); root.addWidget(splitter, 1)

        data_panel = QWidget(); data_layout = QVBoxLayout(data_panel)
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
        data_layout.addWidget(QLabel("Paste rectangular data from Excel with Ctrl/Cmd+V."))
        splitter.addWidget(data_panel)

        plot_panel = QWidget(); plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(4, 0, 4, 0)
        self.figure = Figure(figsize=(8, 6), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        plot_layout.addWidget(NavigationToolbar2QT(self.canvas, plot_panel)); plot_layout.addWidget(self.canvas, 1)
        splitter.addWidget(plot_panel)

        controls = QWidget(); controls.setMinimumWidth(300); controls.setMaximumWidth(390)
        controls_layout = QVBoxLayout(controls); controls_layout.setContentsMargins(4, 0, 0, 0)
        mapping = QGroupBox("Data mapping"); mapping_form = QFormLayout(mapping)
        self.x_column = QComboBox()
        self.y_columns = QListWidget(); self.y_columns.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.y_columns.setMinimumHeight(115)
        self.chart_type = QComboBox(); self.chart_type.addItems(self.CHARTS)
        mapping_form.addRow("X / category", self.x_column); mapping_form.addRow("Y column(s)", self.y_columns)
        mapping_form.addRow("Chart type", self.chart_type); controls_layout.addWidget(mapping)

        labels = QGroupBox("Titles and labels"); label_form = QFormLayout(labels)
        self.title_edit, self.xlabel_edit, self.ylabel_edit = QLineEdit(), QLineEdit(), QLineEdit()
        self.legend_check = QCheckBox("Show legend"); self.legend_check.setChecked(True)
        self.grid_check, self.data_labels_check = QCheckBox("Show grid"), QCheckBox("Show data labels")
        label_form.addRow("Graph title", self.title_edit); label_form.addRow("X-axis", self.xlabel_edit)
        label_form.addRow("Y-axis", self.ylabel_edit); label_form.addRow(self.legend_check)
        label_form.addRow(self.grid_check); label_form.addRow(self.data_labels_check)
        controls_layout.addWidget(labels)

        style = QGroupBox("Selected series style"); style_form = QFormLayout(style)
        self.style_series = QComboBox(); self.color_edit = QLineEdit("#1f77b4")
        color_button = QPushButton("Choose color"); color_button.clicked.connect(self.choose_color)
        self.line_style = QComboBox(); self.line_style.addItems(["Solid", "Dashed", "Dotted", "Dash-dot", "None"])
        self.marker = QComboBox(); self.marker.addItems(["None", "Circle", "Square", "Triangle", "Diamond", "Plus", "Cross"])
        self.line_width = QDoubleSpinBox(); self.line_width.setRange(0.1, 20); self.line_width.setValue(1.8)
        self.bar_width = QDoubleSpinBox(); self.bar_width.setRange(0.05, 1.0); self.bar_width.setSingleStep(0.05); self.bar_width.setValue(0.8)
        style_form.addRow("Series", self.style_series); style_form.addRow("Color", self.color_edit)
        style_form.addRow("", color_button); style_form.addRow("Line", self.line_style)
        style_form.addRow("Marker", self.marker); style_form.addRow("Line width", self.line_width)
        style_form.addRow("Bar width", self.bar_width); controls_layout.addWidget(style)
        self.auto_plot = QCheckBox("Update graph while editing"); controls_layout.addWidget(self.auto_plot)
        plot_button = QPushButton("Plot / refresh"); plot_button.setObjectName("primary"); plot_button.clicked.connect(self.plot_data)
        controls_layout.addWidget(plot_button); controls_layout.addStretch(); splitter.addWidget(controls)
        splitter.setSizes([520, 680, 320])

        self.x_column.currentTextChanged.connect(self._mapping_changed)
        self.y_columns.itemSelectionChanged.connect(self._mapping_changed)
        self.chart_type.currentTextChanged.connect(self.plot_data)
        self.style_series.currentTextChanged.connect(self._load_series_style)
        for widget in (self.title_edit, self.xlabel_edit, self.ylabel_edit): widget.editingFinished.connect(self.plot_data)
        for widget in (self.legend_check, self.grid_check, self.data_labels_check): widget.toggled.connect(self.plot_data)
        self.line_style.currentTextChanged.connect(self._save_series_style); self.marker.currentTextChanged.connect(self._save_series_style)
        self.color_edit.editingFinished.connect(self._save_series_style); self.line_width.valueChanged.connect(self._save_series_style)
        self.bar_width.valueChanged.connect(self._save_series_style)

    def new_table(self, _checked=False, confirm=True):
        if confirm and QMessageBox.question(self, "Start new table", "Clear the current table and graph?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
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
        self._loading_table = True; self.table.clear(); self.table.setRowCount(max(25, len(frame)))
        self.table.setColumnCount(len(frame.columns)); self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for row in range(len(frame)):
            for col in range(len(frame.columns)):
                value = frame.iat[row, col]; self.table.setItem(row, col, QTableWidgetItem("" if pd.isna(value) else str(value)))
        self._loading_table = False; self._refresh_columns()

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

    def _table_changed(self, _item):
        if not self._loading_table and self.auto_plot.isChecked(): self.plot_data()

    def add_row(self):
        self.table.insertRow(self.table.currentRow()+1 if self.table.currentRow() >= 0 else self.table.rowCount())

    def delete_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True): self.table.removeRow(row)

    def add_column(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add column", "Column name", text=f"Column {self.table.columnCount()+1}")
        if ok and name:
            col = self.table.columnCount(); self.table.insertColumn(col); self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name)); self._refresh_columns()

    def delete_columns(self):
        columns = sorted({i.column() for i in self.table.selectedIndexes()}, reverse=True)
        if not columns and self.table.currentColumn() >= 0: columns = [self.table.currentColumn()]
        if self.table.columnCount()-len(columns) < 1:
            QMessageBox.warning(self, "Columns required", "Keep at least one column."); return
        for col in columns: self.table.removeColumn(col)
        self._refresh_columns()

    def rename_column(self):
        from PySide6.QtWidgets import QInputDialog
        col = self.table.currentColumn()
        if col < 0: return
        old = self.table.horizontalHeaderItem(col).text(); name, ok = QInputDialog.getText(self, "Rename column", "New name", text=old)
        if ok and name: self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name)); self._refresh_columns()

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
        filename, _ = QFileDialog.getSaveFileName(self, "Export graph", "graph.png", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if filename:
            try: self.figure.savefig(filename, dpi=300, bbox_inches="tight")
            except Exception as error: QMessageBox.critical(self, "Export error", str(error))

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save plotter project", "plot_project.json", "Plot projects (*.json)")
        if not filename: return
        frame = self._dataframe()
        data = {"columns":list(frame.columns), "rows":frame.values.tolist(), "files":self.loaded_files, "styles":self.series_styles,
            "x":self.x_column.currentText(), "y":[i.text() for i in self.y_columns.selectedItems()], "chart":self.chart_type.currentText(),
            "title":self.title_edit.text(), "xlabel":self.xlabel_edit.text(), "ylabel":self.ylabel_edit.text(),
            "legend":self.legend_check.isChecked(), "grid":self.grid_check.isChecked(), "data_labels":self.data_labels_check.isChecked()}
        try: Path(filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as error: QMessageBox.critical(self, "Save error", str(error))

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open plotter project", "", "Plot projects (*.json)")
        if not filename: return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8")); self.loaded_files = data.get("files", []); self.series_styles = data.get("styles", {})
            self._set_dataframe(pd.DataFrame(data["rows"], columns=data["columns"])); self.x_column.setCurrentText(data.get("x", ""))
            wanted = set(data.get("y", []))
            for index in range(self.y_columns.count()): self.y_columns.item(index).setSelected(self.y_columns.item(index).text() in wanted)
            self.chart_type.setCurrentText(data.get("chart", "Line")); self.title_edit.setText(data.get("title", ""))
            self.xlabel_edit.setText(data.get("xlabel", "")); self.ylabel_edit.setText(data.get("ylabel", ""))
            self.legend_check.setChecked(data.get("legend", True)); self.grid_check.setChecked(data.get("grid", False)); self.data_labels_check.setChecked(data.get("data_labels", False))
            self.file_label.setText("Project: " + Path(filename).name); self.plot_data()
        except (OSError, ValueError, KeyError, TypeError) as error: QMessageBox.critical(self, "Project error", str(error))
