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
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSlider, QSplitter, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from plot_export import save_figure
from qt_general_plotter import DataTable, read_table
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import CompactNavigationToolbar, PanelToggleButton


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
        self._loading = False; self.loaded_files = []
        self._build_ui(); self._set_dataframe(pd.DataFrame({"X": [""] * 25, "Y": [""] * 25, "Z": [""] * 25}))

    def _build_ui(self):
        root = QVBoxLayout(self); top = QHBoxLayout()
        for label, slot in (("New table", self.new_table), ("Add file", self.add_file),
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
        for label, slot in (("+ Row", self.add_row), ("- Row", self.delete_rows),
                            ("+ Column", self.add_column), ("- Column", self.delete_columns),
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
        form_layout.addWidget(mapping)
        labels = QGroupBox("Labels and view"); label_form = QFormLayout(labels)
        self.title_edit = QLineEdit(); self.xlabel_edit = QLineEdit("X")
        self.ylabel_edit = QLineEdit("Y"); self.zlabel_edit = QLineEdit("Z")
        self.colorbar_check = QCheckBox("Show colorbar"); self.colorbar_check.setChecked(True)
        self.grid_check = QCheckBox("Show grid"); self.grid_check.setChecked(True)
        self.elevation = QSlider(Qt.Orientation.Horizontal); self.elevation.setRange(0, 90); self.elevation.setValue(30)
        self.azimuth = QSlider(Qt.Orientation.Horizontal); self.azimuth.setRange(-180, 180); self.azimuth.setValue(-60)
        for label, widget in (("Title", self.title_edit), ("X label", self.xlabel_edit), ("Y label", self.ylabel_edit),
                              ("Z label", self.zlabel_edit), ("Elevation", self.elevation), ("Azimuth", self.azimuth)):
            label_form.addRow(label, widget)
        label_form.addRow(self.colorbar_check); label_form.addRow(self.grid_check); form_layout.addWidget(labels)
        plot = QPushButton("Plot / refresh"); plot.setObjectName("primary"); plot.clicked.connect(self.plot_data)
        form_layout.addWidget(plot); form_layout.addStretch()
        self.controls_scroll = QScrollArea(); self.controls_scroll.setWidgetResizable(True); self.controls_scroll.setWidget(controls)
        self.splitter.addWidget(self.controls_scroll); self.splitter.setSizes([420, 760, 360])
        self.data_toggle = PanelToggleButton(self.data_panel, "left", self)
        self.controls_toggle = PanelToggleButton(self.controls_scroll, "right", self)
        top.insertWidget(4, self.data_toggle); top.insertWidget(5, self.controls_toggle)

        for widget in (self.plot_type, self.colormap): widget.currentTextChanged.connect(self.plot_data)
        for widget in (self.levels,): widget.valueChanged.connect(self.plot_data)
        for widget in (self.elevation, self.azimuth): widget.valueChanged.connect(self._update_view)
        for widget in (self.title_edit, self.xlabel_edit, self.ylabel_edit, self.zlabel_edit): widget.editingFinished.connect(self.plot_data)
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

    @staticmethod
    def structured_grid(x, y, z):
        ux, uy = np.unique(x), np.unique(y)
        if len(ux) * len(uy) != len(x): return None
        frame = pd.DataFrame({"x": x, "y": y, "z": z}).pivot(index="y", columns="x", values="z")
        if frame.isna().any().any(): return None
        xx, yy = np.meshgrid(frame.columns.to_numpy(float), frame.index.to_numpy(float))
        return xx, yy, frame.to_numpy(float)

    def plot_data(self, *_args):
        if self._loading or not self.x_column.currentText(): return
        try:
            x=self._numeric(self.x_column.currentText()); y=self._numeric(self.y_column.currentText()); z=self._numeric(self.z_column.currentText())
        except (KeyError, ValueError): return
        valid=np.isfinite(x)&np.isfinite(y)&np.isfinite(z); x,y,z=x[valid],y[valid],z[valid]
        if len(x)<3: return
        self.figure.clear(); ax=self.figure.add_subplot(111, projection="3d")
        plot_type=self.plot_type.currentText(); cmap=self.colormap.currentText(); artist=None
        try:
            grid=self.structured_grid(x,y,z)
            if plot_type=="3D scatter": artist=ax.scatter(x,y,z,c=z,cmap=cmap,s=22,depthshade=True)
            elif plot_type=="Triangulated surface": artist=ax.plot_trisurf(x,y,z,cmap=cmap,linewidth=.15,antialiased=True)
            elif plot_type in {"Structured surface","Wireframe","3D contour","Projected contour"}:
                if grid is None: raise ValueError("This plot type requires one Z value for every X/Y grid point. Use Triangulated surface for scattered data.")
                xx,yy,zz=grid
                if plot_type=="Structured surface": artist=ax.plot_surface(xx,yy,zz,cmap=cmap,linewidth=0,antialiased=True)
                elif plot_type=="Wireframe": artist=ax.plot_wireframe(xx,yy,zz,rstride=max(1,len(yy)//40),cstride=max(1,len(xx[0])//40),color="#2563eb",linewidth=.6)
                elif plot_type=="3D contour": artist=ax.contour3D(xx,yy,zz,self.levels.value(),cmap=cmap)
                else:
                    artist=ax.contourf(xx,yy,zz,self.levels.value(),zdir="z",offset=float(np.nanmin(zz)),cmap=cmap)
                    ax.plot_surface(xx,yy,zz,cmap=cmap,alpha=.35,linewidth=0)
            else:
                names=(self.u_column.currentText(),self.v_column.currentText(),self.w_column.currentText())
                if "(none)" in names: raise ValueError("Vector field requires U, V, and W columns.")
                u,v,w=(self._numeric(name)[valid] for name in names)
                stride=max(1,len(x)//1200); magnitude=np.sqrt(u*u+v*v+w*w)
                artist=ax.quiver(x[::stride],y[::stride],z[::stride],u[::stride],v[::stride],w[::stride],length=.1,normalize=True,color="#2563eb")
                if self.colorbar_check.isChecked():
                    from matplotlib.cm import ScalarMappable
                    sm=ScalarMappable(cmap=cmap); sm.set_array(magnitude); self.figure.colorbar(sm,ax=ax,shrink=.65,label="Vector magnitude")
            if self.colorbar_check.isChecked() and artist is not None and plot_type not in {"Wireframe","Vector field"}:
                self.figure.colorbar(artist,ax=ax,shrink=.65,pad=.1,label=self.z_column.currentText())
        except (ValueError,RuntimeError) as error:
            QMessageBox.warning(self,"3D plot",str(error)); self.figure.clear(); self.canvas.draw_idle(); return
        ax.set_title(self.title_edit.text()); ax.set_xlabel(self.xlabel_edit.text()); ax.set_ylabel(self.ylabel_edit.text()); ax.set_zlabel(self.zlabel_edit.text())
        ax.grid(self.grid_check.isChecked()); ax.view_init(self.elevation.value(),self.azimuth.value()); self.canvas.draw_idle()

    def _update_view(self, *_args):
        if self.figure.axes:
            self.figure.axes[0].view_init(self.elevation.value(),self.azimuth.value()); self.canvas.draw_idle()

    def new_table(self, _checked=False):
        self.loaded_files=[]; self._set_dataframe(pd.DataFrame({"X":[""]*25,"Y":[""]*25,"Z":[""]*25}))
        self.file_label.setText("Manual XYZ data - type values or paste from Excel"); self.figure.clear(); self.canvas.draw_idle()

    def add_file(self):
        names,_=QFileDialog.getOpenFileNames(self,"Add XYZ data","","Data (*.csv *.tsv *.txt *.dat *.xyz *.xlsx *.xls);;All files (*)")
        for name in names:
            try: incoming=read_table(Path(name))
            except Exception as error: QMessageBox.warning(self,"Import error",f"Could not import {Path(name).name}:\n{error}"); continue
            current=self._dataframe()
            if not current.empty:
                incoming=incoming.rename(columns={c:f"{Path(name).stem}.{c}" for c in incoming if c in current})
                incoming=pd.concat([current.reset_index(drop=True),incoming.reset_index(drop=True)],axis=1)
            self._set_dataframe(incoming); self.loaded_files.append(name)
        if self.loaded_files: self.file_label.setText("Imported: "+", ".join(Path(n).name for n in self.loaded_files))

    def add_row(self): self.table.insertRow(self.table.currentRow()+1 if self.table.currentRow()>=0 else self.table.rowCount())
    def delete_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True): self.table.removeRow(row)
    def add_column(self):
        name,ok=QInputDialog.getText(self,"Add column","Column name")
        if ok and name:
            col=self.table.columnCount(); self.table.insertColumn(col); self.table.setHorizontalHeaderItem(col,QTableWidgetItem(name)); self._refresh_columns()
    def delete_columns(self):
        cols=sorted({i.column() for i in self.table.selectedIndexes()},reverse=True)
        if self.table.columnCount()-len(cols)<3: QMessageBox.warning(self,"Columns required","Keep at least three columns."); return
        for col in cols: self.table.removeColumn(col)
        self._refresh_columns()
    def rename_column(self):
        col=self.table.currentColumn()
        if col<0:return
        old=self.table.horizontalHeaderItem(col).text(); name,ok=QInputDialog.getText(self,"Rename column","New name",text=old)
        if ok and name:self.table.setHorizontalHeaderItem(col,QTableWidgetItem(name));self._refresh_columns()
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
