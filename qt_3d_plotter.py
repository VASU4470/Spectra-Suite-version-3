"""General-purpose editable 3D plotting workspace."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
    QSlider, QSplitter, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from plot_export import save_figure
from fluid_reader import read_tecplot
from qt_general_plotter import DataTable, parse_axis_limits, read_table
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import CompactNavigationToolbar, PanelToggleButton


def read_3d_table(path: Path):
    """Read generic XYZ tables or flatten an ASCII Tecplot POINT grid."""
    path = Path(path)
    if path.suffix.lower() == ".plt":
        field = read_tecplot(path)
        return pd.DataFrame(
            field.values.reshape(-1, len(field.variables)),
            columns=list(field.variables),
        )
    return read_table(path)


class Plot3D(QWidget):
    PLOTS = (
        "3D scatter", "Triangulated surface", "Structured surface", "Wireframe",
        "3D contour", "Projected contour", "Vector field",
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpectraSuite 3D Plotter")
        self.resize(1500, 900); self.setMinimumSize(1050, 700)
        self.setStyleSheet(LIGHT_STYLE); apply_window_icon(self, "PLOT3D")
        self._loading = False; self.loaded_files = []; self.layers = []
        self._build_ui(); self._set_dataframe(pd.DataFrame({"X": [""] * 25, "Y": [""] * 25, "Z": [""] * 25}))

    def _build_ui(self):
        root = QVBoxLayout(self); top = QHBoxLayout()
        for label, slot in (("New table", self.new_table), ("Add file", self.add_file),
                            ("Replace data", self.replace_data),
                            ("Save data", self.save_data), ("Export graph", self.export_graph)):
            button = QPushButton(label); button.clicked.connect(slot); top.addWidget(button)
        top.addStretch(); root.addLayout(top)
        self.splitter = QSplitter(Qt.Orientation.Horizontal); self.splitter.setChildrenCollapsible(True)
        root.addWidget(self.splitter, 1)

        self.data_panel = QWidget(); data_layout = QVBoxLayout(self.data_panel)
        data_layout.setContentsMargins(0, 0, 4, 0)
        self.file_label = QLabel("Manual XYZ data - type values or paste from Excel")
        data_layout.addWidget(self.file_label)
        self.table = DataTable(); data_layout.addWidget(self.table, 1)
        edit = QHBoxLayout()
        for label, slot in (("Insert row", self.add_row), ("Delete row(s)", self.delete_rows),
                            ("Insert column", self.add_column), ("Delete column(s)", self.delete_columns),
                            ("Rename", self.rename_column)):
            button = QPushButton(label); button.clicked.connect(slot); edit.addWidget(button)
        data_layout.addLayout(edit); self.splitter.addWidget(self.data_panel)

        self.plot_panel = QWidget(); plot_layout = QVBoxLayout(self.plot_panel)
        plot_layout.setContentsMargins(4, 0, 4, 0)
        self.figure = Figure(figsize=(8, 6), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure); plot_layout.addWidget(self.canvas, 1)
        self.toolbar = CompactNavigationToolbar(self.canvas, self.plot_panel)
        toolbar_row = QHBoxLayout(); toolbar_row.addWidget(self.toolbar, 1)
        self.toolbar_toggle = PanelToggleButton(self.toolbar, "bottom", self.plot_panel)
        toolbar_row.addWidget(self.toolbar_toggle); plot_layout.addLayout(toolbar_row)
        self.splitter.addWidget(self.plot_panel)

        controls = QWidget(); controls.setMinimumWidth(330); form_layout = QVBoxLayout(controls)
        mapping = QGroupBox("Data mapping"); form = QFormLayout(mapping)
        self.x_column = QComboBox(); self.y_column = QComboBox(); self.z_column = QComboBox()
        self.u_column = QComboBox(); self.v_column = QComboBox(); self.w_column = QComboBox()
        self.plot_type = QComboBox(); self.plot_type.addItems(self.PLOTS)
        self.colormap = QComboBox(); self.colormap.addItems(["viridis", "turbo", "plasma", "inferno", "coolwarm", "jet", "cividis"])
        self.levels = QSpinBox(); self.levels.setRange(5, 100); self.levels.setValue(24)
        for label, widget in (("X", self.x_column), ("Y", self.y_column), ("Z / scalar", self.z_column),
                              ("U vector", self.u_column), ("V vector", self.v_column), ("W vector", self.w_column),
                              ("Plot type", self.plot_type), ("Colormap", self.colormap), ("Contour levels", self.levels)):
            form.addRow(label, widget)
        self.layer_list = QListWidget(); self.layer_list.setMaximumHeight(100)
        self.layer_list.currentRowChanged.connect(self._select_layer_mapping)
        form.addRow("Datasets in plot", self.layer_list)
        layer_buttons = QHBoxLayout()
        add_layer = QPushButton("Add current mapping")
        add_layer.clicked.connect(self.add_current_layer)
        remove_layer = QPushButton("Remove selected data")
        remove_layer.clicked.connect(self.remove_selected_layer)
        layer_buttons.addWidget(add_layer); layer_buttons.addWidget(remove_layer)
        form.addRow(layer_buttons)
        form_layout.addWidget(mapping)
        labels = QGroupBox("Labels and view"); label_form = QFormLayout(labels)
        self.title_edit = QLineEdit(); self.xlabel_edit = QLineEdit("X")
        self.ylabel_edit = QLineEdit("Y"); self.zlabel_edit = QLineEdit("Z")
        self.xlim_edit = QLineEdit(); self.ylim_edit = QLineEdit(); self.zlim_edit = QLineEdit()
        for field in (self.xlim_edit, self.ylim_edit, self.zlim_edit):
            field.setPlaceholderText("automatic or min,max")
        self.colorbar_check = QCheckBox("Show colorbar"); self.colorbar_check.setChecked(True)
        self.grid_check = QCheckBox("Show grid"); self.grid_check.setChecked(True)
        self.elevation = QSlider(Qt.Orientation.Horizontal); self.elevation.setRange(0, 90); self.elevation.setValue(30)
        self.azimuth = QSlider(Qt.Orientation.Horizontal); self.azimuth.setRange(-180, 180); self.azimuth.setValue(-60)
        for label, widget in (("Title", self.title_edit), ("X label", self.xlabel_edit), ("Y label", self.ylabel_edit),
                              ("Z label", self.zlabel_edit), ("X limits", self.xlim_edit),
                              ("Y limits", self.ylim_edit), ("Z limits", self.zlim_edit),
                              ("Elevation", self.elevation), ("Azimuth", self.azimuth)):
            label_form.addRow(label, widget)
        label_form.addRow(self.colorbar_check); label_form.addRow(self.grid_check); form_layout.addWidget(labels)
        plot = QPushButton("Plot / refresh"); plot.setObjectName("primary"); plot.clicked.connect(self.plot_data)
        form_layout.addWidget(plot); form_layout.addStretch()
        self.controls_scroll = QScrollArea(); self.controls_scroll.setWidgetResizable(True); self.controls_scroll.setWidget(controls)
        self.splitter.addWidget(self.controls_scroll); self.splitter.setSizes([420, 760, 360])
        self.data_toggle = PanelToggleButton(self.data_panel, "left", self)
        self.controls_toggle = PanelToggleButton(self.controls_scroll, "right", self)
        top.insertWidget(5, self.data_toggle); top.insertWidget(6, self.controls_toggle)

        for widget in (self.plot_type, self.colormap): widget.currentTextChanged.connect(self.plot_data)
        for widget in (self.levels,): widget.valueChanged.connect(self.plot_data)
        for widget in (self.elevation, self.azimuth): widget.valueChanged.connect(self._update_view)
        for widget in (self.title_edit, self.xlabel_edit, self.ylabel_edit, self.zlabel_edit,
                       self.xlim_edit, self.ylim_edit, self.zlim_edit):
            widget.editingFinished.connect(self.plot_data)
        for widget in (self.colorbar_check, self.grid_check): widget.toggled.connect(self.plot_data)

    def _headers(self):
        return [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]

    def _set_dataframe(self, frame):
        self._loading = True; self.table._history_suspended = True
        self.table.clear(); self.table.setRowCount(max(25, len(frame))); self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for row in range(len(frame)):
            for col in range(len(frame.columns)):
                value = frame.iat[row, col]
                self.table.setItem(row, col, QTableWidgetItem("" if pd.isna(value) else str(value)))
        self.table._history_suspended = False; self.table.reset_history(); self._loading = False; self._refresh_columns()

    def _dataframe(self):
        rows=[]; headers=self._headers()
        for row in range(self.table.rowCount()):
            values=[self.table.item(row,col).text().strip() if self.table.item(row,col) else "" for col in range(self.table.columnCount())]
            if any(values): rows.append(values)
        return pd.DataFrame(rows, columns=headers)

    def _refresh_columns(self):
        headers = self._headers(); combos=(self.x_column,self.y_column,self.z_column,self.u_column,self.v_column,self.w_column)
        for index, combo in enumerate(combos):
            current=combo.currentText(); combo.blockSignals(True); combo.clear()
            if index >= 3: combo.addItem("(none)")
            combo.addItems(headers)
            if current in headers: combo.setCurrentText(current)
            elif index < 3 and headers: combo.setCurrentIndex(min(index, len(headers)-1))
            combo.blockSignals(False)

    def _numeric(self, name): return pd.to_numeric(self._dataframe()[name], errors="coerce").to_numpy(float)

    def _current_layer(self, name="Current mapping", columns=None, path=None):
        return {
            "name": name,
            "x": self.x_column.currentText(),
            "y": self.y_column.currentText(),
            "z": self.z_column.currentText(),
            "u": self.u_column.currentText(),
            "v": self.v_column.currentText(),
            "w": self.w_column.currentText(),
            "columns": list(columns or []),
            "path": str(path) if path else "",
        }

    def _refresh_layer_list(self):
        self.layer_list.clear()
        for layer in self.layers:
            self.layer_list.addItem(
                f"{layer['name']}: {layer['x']}, {layer['y']}, {layer['z']}"
            )

    def _select_layer_mapping(self, row):
        if row < 0 or row >= len(self.layers):
            return
        layer = self.layers[row]
        for combo, key in (
            (self.x_column, "x"), (self.y_column, "y"), (self.z_column, "z"),
            (self.u_column, "u"), (self.v_column, "v"), (self.w_column, "w"),
        ):
            index = combo.findText(layer.get(key, ""))
            if index >= 0:
                combo.setCurrentIndex(index)

    def add_current_layer(self):
        if not all((self.x_column.currentText(), self.y_column.currentText(), self.z_column.currentText())):
            return
        default = self.z_column.currentText() or f"Dataset {len(self.layers) + 1}"
        name, accepted = QInputDialog.getText(
            self, "Add 3D dataset", "Dataset/legend name", text=default
        )
        if accepted and name.strip():
            self.layers.append(self._current_layer(name.strip()))
            self._refresh_layer_list()
            self.plot_data()

    def remove_selected_layer(self):
        row = self.layer_list.currentRow()
        if row < 0 or row >= len(self.layers):
            QMessageBox.information(self, "Select data", "Select a dataset in the list first.")
            return
        layer = self.layers.pop(row)
        source_path = layer.get("path")
        if source_path in self.loaded_files:
            self.loaded_files.remove(source_path)
        source_columns = set(layer.get("columns", []))
        if source_columns:
            for column in range(self.table.columnCount() - 1, -1, -1):
                header = self.table.horizontalHeaderItem(column)
                if header and header.text() in source_columns:
                    self.table.removeColumn(column)
            self._refresh_columns()
        self._refresh_layer_list()
        self.file_label.setText(
            "Imported: " + ", ".join(Path(name).name for name in self.loaded_files)
            if self.loaded_files else "Manual XYZ data - type values or paste from Excel"
        )
        self.plot_data()

    @staticmethod
    def structured_grid(x, y, z):
        ux, uy = np.unique(x), np.unique(y)
        if len(ux) * len(uy) != len(x): return None
        frame = pd.DataFrame({"x": x, "y": y, "z": z}).pivot(index="y", columns="x", values="z")
        if frame.isna().any().any(): return None
        xx, yy = np.meshgrid(frame.columns.to_numpy(float), frame.index.to_numpy(float))
        return xx, yy, frame.to_numpy(float)

    def plot_data(self, *_args):
        if self._loading:
            return
        if not self.x_column.currentText():
            self.figure.clear(); self.canvas.draw_idle()
            return
        try:
            x_limits = parse_axis_limits(self.xlim_edit.text())
            y_limits = parse_axis_limits(self.ylim_edit.text())
            z_limits = parse_axis_limits(self.zlim_edit.text())
        except ValueError as error:
            QMessageBox.warning(self, "Axis limits", str(error))
            return
        mappings = list(self.layers) if self.layers else [self._current_layer()]
        self.figure.clear()
        ax = self.figure.add_subplot(111, projection="3d")
        plot_type = self.plot_type.currentText()
        cmap = self.colormap.currentText()
        last_artist = None
        plotted = 0
        try:
            for layer in mappings:
                x = self._numeric(layer["x"])
                y = self._numeric(layer["y"])
                z = self._numeric(layer["z"])
                valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                x, y, z = x[valid], y[valid], z[valid]
                if len(x) < 3:
                    continue
                grid = self.structured_grid(x, y, z)
                alpha = 0.78 if len(mappings) > 1 else 1.0
                if plot_type == "3D scatter":
                    last_artist = ax.scatter(
                        x, y, z, c=z, cmap=cmap, s=22, depthshade=True,
                        alpha=alpha, label=layer["name"],
                    )
                elif plot_type == "Triangulated surface":
                    last_artist = ax.plot_trisurf(
                        x, y, z, cmap=cmap, linewidth=.15,
                        antialiased=True, alpha=alpha,
                    )
                elif plot_type in {"Structured surface", "Wireframe", "3D contour", "Projected contour"}:
                    if grid is None:
                        raise ValueError(
                            f"{layer['name']} is not a complete X/Y grid. "
                            "Use Triangulated surface for scattered data."
                        )
                    xx, yy, zz = grid
                    if plot_type == "Structured surface":
                        last_artist = ax.plot_surface(
                            xx, yy, zz, cmap=cmap, linewidth=0,
                            antialiased=True, alpha=alpha,
                        )
                    elif plot_type == "Wireframe":
                        last_artist = ax.plot_wireframe(
                            xx, yy, zz, rstride=max(1, len(yy) // 40),
                            cstride=max(1, len(xx[0]) // 40), linewidth=.6,
                        )
                    elif plot_type == "3D contour":
                        last_artist = ax.contour3D(
                            xx, yy, zz, self.levels.value(), cmap=cmap, alpha=alpha
                        )
                    else:
                        last_artist = ax.contourf(
                            xx, yy, zz, self.levels.value(), zdir="z",
                            offset=float(np.nanmin(zz)), cmap=cmap, alpha=alpha,
                        )
                        ax.plot_surface(xx, yy, zz, cmap=cmap, alpha=.25, linewidth=0)
                else:
                    names = (layer.get("u"), layer.get("v"), layer.get("w"))
                    if not all(names) or "(none)" in names:
                        raise ValueError(
                            f"{layer['name']} needs mapped U, V, and W columns for a vector field."
                        )
                    u, v, w = (self._numeric(name)[valid] for name in names)
                    stride = max(1, len(x) // 1200)
                    magnitude = np.sqrt(u * u + v * v + w * w)
                    last_artist = ax.quiver(
                        x[::stride], y[::stride], z[::stride],
                        u[::stride], v[::stride], w[::stride],
                        length=.1, normalize=True,
                    )
                    if self.colorbar_check.isChecked():
                        from matplotlib.cm import ScalarMappable
                        scalar = ScalarMappable(cmap=cmap)
                        scalar.set_array(magnitude)
                        self.figure.colorbar(
                            scalar, ax=ax, shrink=.65, label="Vector magnitude"
                        )
                plotted += 1
            if not plotted:
                self.figure.clear()
                self.canvas.draw_idle()
                return
            if (
                self.colorbar_check.isChecked() and last_artist is not None
                and plot_type not in {"Wireframe", "Vector field"}
            ):
                self.figure.colorbar(
                    last_artist, ax=ax, shrink=.65, pad=.1,
                    label=mappings[-1]["z"],
                )
        except (KeyError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "3D plot", str(error))
            self.figure.clear(); self.canvas.draw_idle()
            return
        ax.set_title(self.title_edit.text())
        ax.set_xlabel(self.xlabel_edit.text()); ax.set_ylabel(self.ylabel_edit.text())
        ax.set_zlabel(self.zlabel_edit.text())
        if x_limits: ax.set_xlim(x_limits)
        if y_limits: ax.set_ylim(y_limits)
        if z_limits: ax.set_zlim(z_limits)
        if plot_type == "3D scatter" and len(mappings) > 1:
            ax.legend(loc="best")
        ax.grid(self.grid_check.isChecked())
        ax.view_init(self.elevation.value(), self.azimuth.value())
        self.canvas.draw_idle()

    def _update_view(self, *_args):
        if self.figure.axes:
            self.figure.axes[0].view_init(self.elevation.value(),self.azimuth.value()); self.canvas.draw_idle()

    def new_table(self, _checked=False):
        self.loaded_files=[]; self.layers=[]; self._refresh_layer_list()
        self._set_dataframe(pd.DataFrame({"X":[""]*25,"Y":[""]*25,"Z":[""]*25}))
        self.xlim_edit.clear(); self.ylim_edit.clear(); self.zlim_edit.clear()
        self.file_label.setText("Manual XYZ data - type values or paste from Excel"); self.figure.clear(); self.canvas.draw_idle()

    def add_file(self):
        names,_=QFileDialog.getOpenFileNames(self,"Add XYZ data","","3D data (*.csv *.tsv *.txt *.dat *.xyz *.plt *.xlsx *.xls);;All files (*)")
        self.load_paths(names, replace=False)

    def replace_data(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Replace 3D data", "",
            "3D data (*.csv *.tsv *.txt *.dat *.xyz *.plt *.xlsx *.xls);;All files (*)",
        )
        if not name:
            return
        if QMessageBox.question(
            self, "Replace data", "Replace all current 3D table data and plot layers?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.load_paths([name], replace=True)

    @staticmethod
    def _suggest_xyz(columns):
        columns = list(columns)
        by_lower = {str(column).strip().lower(): column for column in columns}
        x = by_lower.get("x", columns[0] if columns else "")
        y = by_lower.get("y", columns[1] if len(columns) > 1 else x)
        z = by_lower.get("z")
        if z is None:
            z = next((column for column in columns if column not in {x, y}), "")
        return x, y, z

    def load_paths(self, names, *, replace=False):
        if replace:
            self.loaded_files = []
            self.layers = []
            current = pd.DataFrame()
        else:
            current = self._dataframe()
        for name in names:
            path = Path(name)
            try:
                incoming = read_3d_table(path)
            except Exception as error:
                QMessageBox.warning(
                    self, "Import error", f"Could not import {path.name}:\n{error}"
                )
                continue
            original_columns = list(incoming.columns)
            if not current.empty:
                rename = {column: f"{path.stem}.{column}" for column in original_columns}
                incoming = incoming.rename(columns=rename)
            actual_columns = list(incoming.columns)
            merged = (
                incoming.reset_index(drop=True) if current.empty
                else pd.concat(
                    [current.reset_index(drop=True), incoming.reset_index(drop=True)], axis=1
                )
            )
            current = merged
            self._set_dataframe(merged)
            x, y, z = self._suggest_xyz(actual_columns)
            if x and y and z:
                self.x_column.setCurrentText(x)
                self.y_column.setCurrentText(y)
                self.z_column.setCurrentText(z)
                layer = self._current_layer(path.stem, actual_columns, path)
                self.layers.append(layer)
            self.loaded_files.append(str(path))
        self._refresh_layer_list()
        if self.loaded_files:
            self.file_label.setText("Imported: "+", ".join(Path(n).name for n in self.loaded_files))
            self.plot_data()

    def add_row(self): self.table.insertRow(self.table.currentRow() if self.table.currentRow()>=0 else self.table.rowCount())
    def delete_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        for row in rows: self.table.removeRow(row)
    def add_column(self):
        name,ok=QInputDialog.getText(self,"Add column","Column name")
        if ok and name:
            col=self.table.currentColumn()
            if col < 0: col=self.table.columnCount()
            self.table.insertColumn(col); self.table.setHorizontalHeaderItem(col,QTableWidgetItem(name)); self._refresh_columns()
    def delete_columns(self):
        cols=sorted({i.column() for i in self.table.selectedIndexes()},reverse=True)
        if not cols and self.table.currentColumn() >= 0: cols=[self.table.currentColumn()]
        if self.table.columnCount()-len(cols)<3: QMessageBox.warning(self,"Columns required","Keep at least three columns."); return
        removed = {
            self.table.horizontalHeaderItem(col).text()
            for col in cols if self.table.horizontalHeaderItem(col)
        }
        for col in cols: self.table.removeColumn(col)
        self.layers = [
            layer for layer in self.layers
            if not removed.intersection({layer["x"], layer["y"], layer["z"]})
        ]
        self._refresh_layer_list()
        self._refresh_columns()
    def rename_column(self):
        col=self.table.currentColumn()
        if col<0:return
        old=self.table.horizontalHeaderItem(col).text(); name,ok=QInputDialog.getText(self,"Rename column","New name",text=old)
        if ok and name:
            self.table.setHorizontalHeaderItem(col,QTableWidgetItem(name))
            for layer in self.layers:
                for key in ("x", "y", "z", "u", "v", "w"):
                    if layer.get(key) == old: layer[key] = name
                layer["columns"] = [name if value == old else value for value in layer.get("columns", [])]
            self._refresh_layer_list(); self._refresh_columns()
    def save_data(self):
        name,selected=QFileDialog.getSaveFileName(self,"Save data","xyz_data.csv","CSV (*.csv);;Excel (*.xlsx)")
        if not name:return
        try:
            if "Excel" in selected or name.lower().endswith(".xlsx"):self._dataframe().to_excel(name if name.lower().endswith(".xlsx") else name+".xlsx",index=False)
            else:self._dataframe().to_csv(name,index=False)
        except Exception as error:QMessageBox.critical(self,"Save error",str(error))
    def export_graph(self):
        name,selected=QFileDialog.getSaveFileName(self,"Export 3D graph","plot3d.png","PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tiff)")
        if name:
            try:save_figure(self.figure,name,selected_filter=selected)
            except Exception as error:QMessageBox.critical(self,"Export error",str(error))
