"""Fluid-dynamics plotting workspace for structured Tecplot fields."""

from __future__ import annotations

from math import ceil, sqrt
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from fluid_reader import TecplotField, aligned_difference, read_tecplot
from plot_export import save_figure
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_widgets import CompactNavigationToolbar, PanelToggleButton


class FluidPlotter(QWidget):
    PLOTS = (
        "Filled contour", "Contour lines", "Heatmap", "3D surface", "3D wireframe",
        "Profile along X", "Profile along Y", "Field difference", "Grid of fields",
        "Mesh geometry",
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpectraSuite Fluid Dynamics Plotter")
        self.resize(1550, 900); self.setMinimumSize(1100, 700)
        self.setStyleSheet(LIGHT_STYLE); apply_window_icon(self, "FLUID")
        self.fields: list[TecplotField] = []
        self._build_ui()

    def _build_ui(self):
        root=QVBoxLayout(self); top=QHBoxLayout()
        add=QPushButton("Add Tecplot files"); add.clicked.connect(self.add_files); top.addWidget(add)
        remove=QPushButton("Remove selected"); remove.clicked.connect(self.remove_selected); top.addWidget(remove)
        clear=QPushButton("Clear all"); clear.clicked.connect(self.clear_files); top.addWidget(clear)
        export=QPushButton("Export graph"); export.clicked.connect(self.export_graph); top.addWidget(export)
        export_data=QPushButton("Export selected data"); export_data.clicked.connect(self.export_data); top.addWidget(export_data)
        top.addStretch(); root.addLayout(top)

        self.splitter=QSplitter(Qt.Orientation.Horizontal); self.splitter.setChildrenCollapsible(True); root.addWidget(self.splitter,1)
        self.data_panel=QWidget(); data_layout=QVBoxLayout(self.data_panel); data_layout.setContentsMargins(0,0,4,0)
        heading=QLabel("Tecplot datasets"); heading.setStyleSheet("font-weight:700"); data_layout.addWidget(heading)
        self.file_list=QListWidget(); self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self._selection_changed); data_layout.addWidget(self.file_list,1)
        self.summary=QTableWidget(0,2); self.summary.setHorizontalHeaderLabels(["Property","Value"]); self.summary.setMaximumHeight(220)
        data_layout.addWidget(self.summary); self.splitter.addWidget(self.data_panel)

        self.plot_panel=QWidget(); plot_layout=QVBoxLayout(self.plot_panel); plot_layout.setContentsMargins(4,0,4,0)
        self.figure=Figure(figsize=(8,6),constrained_layout=True); self.canvas=FigureCanvasQTAgg(self.figure); plot_layout.addWidget(self.canvas,1)
        self.toolbar=CompactNavigationToolbar(self.canvas,self.plot_panel); toolbar_row=QHBoxLayout(); toolbar_row.addWidget(self.toolbar,1)
        self.toolbar_toggle=PanelToggleButton(self.toolbar,"bottom",self.plot_panel); toolbar_row.addWidget(self.toolbar_toggle); plot_layout.addLayout(toolbar_row)
        self.splitter.addWidget(self.plot_panel)

        controls=QWidget(); controls.setMinimumWidth(330); controls_layout=QVBoxLayout(controls)
        plot_group=QGroupBox("Fluid plot"); form=QFormLayout(plot_group)
        self.plot_type=QComboBox(); self.plot_type.addItems(self.PLOTS)
        self.variable=QComboBox(); self.colormap=QComboBox(); self.colormap.addItems(["turbo","viridis","plasma","coolwarm","jet","cividis"])
        self.levels=QSpinBox(); self.levels.setRange(5,100); self.levels.setValue(30)
        self.slice_coordinate=QDoubleSpinBox(); self.slice_coordinate.setDecimals(7); self.slice_coordinate.setRange(-1e12,1e12)
        self.title_edit=QLineEdit(); self.xlabel_edit=QLineEdit("X"); self.ylabel_edit=QLineEdit("Y"); self.value_label_edit=QLineEdit("Field value")
        for label,widget in (("Plot type",self.plot_type),("Scalar variable",self.variable),("Colormap",self.colormap),
                             ("Contour levels",self.levels),("Profile coordinate",self.slice_coordinate),("Title",self.title_edit),
                             ("X label",self.xlabel_edit),("Y label",self.ylabel_edit),("Value / Z label",self.value_label_edit)):
            form.addRow(label,widget)
        controls_layout.addWidget(plot_group)
        note=QLabel("Select one or more datasets. Profiles and grid plots compare all selected datasets; field difference uses the first two.")
        note.setWordWrap(True); controls_layout.addWidget(note)
        selected=QPushButton("Plot selected"); selected.setObjectName("primary"); selected.clicked.connect(self.plot_selected)
        all_button=QPushButton("Plot all"); all_button.clicked.connect(self.plot_all)
        controls_layout.addWidget(selected); controls_layout.addWidget(all_button); controls_layout.addStretch()
        self.controls_scroll=QScrollArea(); self.controls_scroll.setWidgetResizable(True); self.controls_scroll.setWidget(controls)
        self.splitter.addWidget(self.controls_scroll); self.splitter.setSizes([330,850,360])
        self.data_toggle=PanelToggleButton(self.data_panel,"left",self); self.controls_toggle=PanelToggleButton(self.controls_scroll,"right",self)
        top.insertWidget(5,self.data_toggle); top.insertWidget(6,self.controls_toggle)
        self.plot_type.currentTextChanged.connect(self.plot_selected); self.variable.currentTextChanged.connect(self.plot_selected)
        self.colormap.currentTextChanged.connect(self.plot_selected); self.levels.valueChanged.connect(self.plot_selected)

    def add_files(self):
        names,_=QFileDialog.getOpenFileNames(self,"Add fluid-dynamics data","","Tecplot files (*.plt *.dat);;All files (*)")
        self.load_paths(names)

    def load_paths(self, names):
        errors=[]
        for name in names:
            path=Path(name)
            if any(field.path.resolve()==path.resolve() for field in self.fields): continue
            try: field=read_tecplot(path)
            except Exception as error: errors.append(f"{path.name}: {error}"); continue
            self.fields.append(field); self.file_list.addItem(path.name)
        if errors: QMessageBox.warning(self,"Import error","\n\n".join(errors))
        if self.fields:
            self.file_list.clearSelection(); self.file_list.item(self.file_list.count()-1).setSelected(True)
            self._refresh_variables(); self._selection_changed()

    def remove_selected(self):
        for row in sorted({self.file_list.row(item) for item in self.file_list.selectedItems()},reverse=True):
            self.file_list.takeItem(row); self.fields.pop(row)
        self._refresh_variables(); self._selection_changed()

    def clear_files(self): self.fields.clear(); self.file_list.clear(); self.figure.clear(); self.canvas.draw_idle(); self._refresh_variables()

    def _selected_indices(self): return sorted({self.file_list.row(item) for item in self.file_list.selectedItems()})
    def _selected_fields(self): return [self.fields[i] for i in self._selected_indices()]

    def _refresh_variables(self):
        current=self.variable.currentText(); variables=[]
        for field in self.fields:
            for name in field.scalar_variables:
                if name not in variables: variables.append(name)
        self.variable.blockSignals(True); self.variable.clear(); self.variable.addItems(variables)
        if current in variables:self.variable.setCurrentText(current)
        self.variable.blockSignals(False)

    def _selection_changed(self):
        selected=self._selected_fields(); self.summary.setRowCount(0)
        if not selected:return
        field=selected[0]; details=(("File",field.path.name),("Title",field.title),("Zone",field.zone),
                                   ("Grid",f"{field.i} x {field.j} x {field.k}"),("Variables",", ".join(field.variables)),
                                   ("X range",f"{np.nanmin(field.x):.5g} to {np.nanmax(field.x):.5g}"),
                                   ("Y range",f"{np.nanmin(field.y):.5g} to {np.nanmax(field.y):.5g}"))
        for row,(key,value) in enumerate(details):
            self.summary.insertRow(row); self.summary.setItem(row,0,QTableWidgetItem(key)); self.summary.setItem(row,1,QTableWidgetItem(value))
        midpoint=(float(np.nanmin(field.y))+float(np.nanmax(field.y)))/2
        self.slice_coordinate.setValue(midpoint)

    def _value(self,field):
        name=self.variable.currentText()
        if not name:
            if not field.scalar_variables: raise ValueError("This dataset contains only mesh coordinates.")
            name=field.scalar_variables[0]
        if name not in field.variables: raise ValueError(f"{field.path.name} has no '{name}' variable.")
        return field.variable(name)

    def plot_all(self):
        self.file_list.selectAll(); self.plot_selected()

    def plot_selected(self,*_args):
        fields=self._selected_fields()
        if not fields:return
        kind=self.plot_type.currentText(); cmap=self.colormap.currentText(); levels=self.levels.value(); self.figure.clear()
        try:
            if kind != "Mesh geometry":
                variable = self.variable.currentText()
                compatible = [field for field in fields if variable in field.variables]
                if not compatible:
                    raise ValueError(f"None of the selected datasets contains '{variable}'. Use Mesh geometry for coordinate-only files.")
                fields = compatible
            if kind=="Grid of fields":
                cols=min(3,max(1,ceil(sqrt(len(fields))))); rows=ceil(len(fields)/cols)
                for index,field in enumerate(fields,1):
                    ax=self.figure.add_subplot(rows,cols,index); scalar=self._value(field)
                    artist=ax.contourf(field.x,field.y,scalar,levels=levels,cmap=cmap)
                    ax.set_title(field.path.stem); ax.set_xlabel(self.xlabel_edit.text()); ax.set_ylabel(self.ylabel_edit.text())
                    self.figure.colorbar(artist,ax=ax,shrink=.8)
            elif kind in {"Profile along X","Profile along Y"}:
                ax=self.figure.add_subplot(111); coordinate=self.slice_coordinate.value()
                for field in fields:
                    scalar=self._value(field)
                    if kind=="Profile along X":
                        distances=np.nanmean(abs(field.y-coordinate),axis=0); column=int(np.nanargmin(distances))
                        axis_values=field.x[:,column]; values=scalar[:,column]; axis_label=self.xlabel_edit.text()
                    else:
                        distances=np.nanmean(abs(field.x-coordinate),axis=1); row=int(np.nanargmin(distances))
                        axis_values=field.y[row,:]; values=scalar[row,:]; axis_label=self.ylabel_edit.text()
                    ax.plot(axis_values,values,linewidth=1.8,label=field.path.stem)
                ax.set_xlabel(axis_label); ax.set_ylabel(self.value_label_edit.text()); ax.grid(True,alpha=.3); ax.legend()
            elif kind=="Field difference":
                if len(fields)<2: raise ValueError("Select at least two compatible field datasets for a difference plot.")
                first,second=fields[:2]
                x_grid,y_grid,difference=aligned_difference(first,second,self.variable.currentText())
                ax=self.figure.add_subplot(111)
                limit=float(np.nanmax(abs(difference))) or 1.0
                artist=ax.contourf(x_grid,y_grid,difference,levels=levels,cmap="coolwarm",vmin=-limit,vmax=limit)
                self.figure.colorbar(artist,ax=ax,label=f"{second.path.stem} - {first.path.stem}")
                ax.set_xlabel(self.xlabel_edit.text()); ax.set_ylabel(self.ylabel_edit.text())
            else:
                field=fields[0]
                if kind in {"3D surface","3D wireframe"}:
                    ax=self.figure.add_subplot(111,projection="3d"); scalar=self._value(field)
                    if kind=="3D surface":
                        artist=ax.plot_surface(field.x,field.y,scalar,cmap=cmap,linewidth=0,antialiased=True)
                        self.figure.colorbar(artist,ax=ax,shrink=.65,pad=.1)
                    else: ax.plot_wireframe(field.x,field.y,scalar,rstride=max(1,field.i//40),cstride=max(1,field.j//40),color="#2563eb",linewidth=.55)
                    ax.set_zlabel(self.value_label_edit.text())
                else:
                    ax=self.figure.add_subplot(111)
                    if kind=="Mesh geometry":
                        stride_i=max(1,field.i//35);stride_j=max(1,field.j//35)
                        ax.plot(field.x[::stride_i,:].T,field.y[::stride_i,:].T,color="#64748b",linewidth=.4)
                        ax.plot(field.x[:,::stride_j],field.y[:,::stride_j],color="#64748b",linewidth=.4)
                        ax.set_aspect("equal",adjustable="box")
                    else:
                        scalar=self._value(field)
                        if kind=="Filled contour": artist=ax.contourf(field.x,field.y,scalar,levels=levels,cmap=cmap)
                        elif kind=="Contour lines": artist=ax.contour(field.x,field.y,scalar,levels=levels,cmap=cmap); ax.clabel(artist,fontsize=7)
                        else: artist=ax.pcolormesh(field.x,field.y,scalar,shading="auto",cmap=cmap)
                        self.figure.colorbar(artist,ax=ax,label=self.value_label_edit.text())
                    ax.set_xlabel(self.xlabel_edit.text()); ax.set_ylabel(self.ylabel_edit.text())
            title=self.title_edit.text() or (fields[0].path.stem if len(fields)==1 else f"{self.variable.currentText()} comparison")
            if self.figure.axes:self.figure.axes[0].set_title(title)
            self.canvas.draw_idle()
        except (ValueError,KeyError,RuntimeError) as error:
            QMessageBox.warning(self,"Fluid plot",str(error)); self.figure.clear(); self.canvas.draw_idle()

    def export_graph(self):
        name,selected=QFileDialog.getSaveFileName(self,"Export fluid graph","fluid_plot.png","PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tiff)")
        if name:
            try:save_figure(self.figure,name,selected_filter=selected)
            except Exception as error:QMessageBox.critical(self,"Export error",str(error))

    def export_data(self):
        fields=self._selected_fields()
        if not fields:return
        folder=QFileDialog.getExistingDirectory(self,"Export selected Tecplot data")
        if not folder:return
        try:
            for field in fields:
                matrix=field.values.reshape(-1,len(field.variables))
                np.savetxt(Path(folder)/f"{field.path.stem}.csv",matrix,delimiter=",",header=",".join(field.variables),comments="")
        except OSError as error:QMessageBox.critical(self,"Export error",str(error))
