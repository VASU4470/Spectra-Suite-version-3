"""Experimental SpectraSuite UI v2 desktop shell.

This module is deliberately isolated from the production launcher.  It exercises
only presentation architecture: ribbon commands, project navigation,
multi-document data/plot windows, status context, and object properties.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qt_theme import LIGHT_STYLE, apply_theme, apply_window_icon


PROTOTYPE_STYLE = LIGHT_STYLE + """
QMainWindow#uiV2Prototype { background-color: #edf1f6; }
QFrame#uiV2Ribbon {
    background-color: #ffffff;
    border-bottom: 1px solid #cfd7e3;
}
QTabWidget#uiV2RibbonTabs::pane {
    background-color: #ffffff;
    border: none;
    border-top: 1px solid #e2e8f0;
}
QTabWidget#uiV2RibbonTabs QTabBar::tab {
    background-color: #ffffff;
    color: #334155;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 8px 14px;
}
QTabWidget#uiV2RibbonTabs QTabBar::tab:selected {
    color: #1d4ed8;
    background-color: #ffffff;
    border-bottom: 3px solid #2563eb;
    font-weight: 700;
}
QFrame#uiV2RibbonGroup {
    background-color: #ffffff;
    border-right: 1px solid #dde3eb;
}
QLabel#uiV2GroupTitle {
    color: #64748b;
    font-size: 10px;
}
QToolButton#uiV2RibbonButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    min-width: 68px;
    min-height: 54px;
    padding: 4px 7px;
}
QToolButton#uiV2RibbonButton:hover {
    background-color: #e9f0ff;
    border-color: #cedcff;
}
QFrame#uiV2ProjectPanel {
    background-color: #f8fafc;
    border-right: 1px solid #cfd7e3;
}
QTreeWidget#uiV2ProjectTree {
    background-color: transparent;
    border: none;
    outline: none;
}
QTreeWidget#uiV2ProjectTree::item {
    padding: 5px 4px;
    border-radius: 5px;
}
QTreeWidget#uiV2ProjectTree::item:selected {
    color: #164aa8;
    background-color: #e9f0ff;
}
QMdiArea#uiV2Mdi {
    background-color: #dfe5ed;
}
QMdiSubWindow {
    background-color: #ffffff;
    border: 1px solid #bfc8d4;
}
QFrame#uiV2DocumentToolbar {
    background-color: #f5f7fa;
    border-bottom: 1px solid #cfd7e3;
}
QPushButton#uiV2CompactButton {
    padding: 4px 9px;
}
"""


@dataclass(frozen=True)
class RibbonCommand:
    label: str
    status: str


RIBBON = {
    "Home": {
        "File": ("Open", "Save", "Undo", "Redo"),
        "Common": ("Import", "New Plot", "Properties"),
    },
    "Data": {
        "Import": ("Open Data", "Add Dataset", "Paste"),
        "Table": ("Add Column", "Delete", "Set X/Y", "Formula"),
    },
    "Plot": {
        "Graph": ("Axes", "Legend", "Series", "Layout"),
        "View": ("Fit View", "Zoom", "Pan", "Cursor"),
    },
    "Process": {
        "Processing": ("Baseline", "Smooth", "Normalize", "Derivative", "Subtract"),
    },
    "Analyze": {
        "FT-IR Analysis": ("Find Peaks", "Area", "Deconvolution", "Functional Groups"),
        "General": ("Fit", "Statistics"),
    },
    "Annotate": {
        "Insert": ("Text", "Arrow", "Peak Label", "Shape"),
    },
    "View": {
        "Workspace": ("Project Explorer", "Tile", "Maximize Active", "Status Bar"),
    },
    "Export": {
        "Export": ("Figure", "Data", "Results", "Report"),
    },
}


class AxisPropertiesDialog(QDialog):
    """Small functional proof-of-concept for explicit axis configuration."""

    applied = Signal(float, float, bool)

    def __init__(self, minimum=4000.0, maximum=400.0, reversed_axis=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Axis Properties")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)

        axis_row = QHBoxLayout()
        self.axis_buttons = []
        for index, text in enumerate(("Bottom X", "Top X", "Left Y", "Right Y")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked, target=button: self._select_axis(target))
            axis_row.addWidget(button)
            self.axis_buttons.append(button)
        root.addLayout(axis_row)

        self.pages = QTabWidget()
        root.addWidget(self.pages)

        scale = QWidget()
        form = QFormLayout(scale)

        self.minimum = QDoubleSpinBox()
        self.minimum.setRange(-1e9, 1e9)
        self.minimum.setDecimals(6)
        self.minimum.setValue(minimum)

        self.maximum = QDoubleSpinBox()
        self.maximum.setRange(-1e9, 1e9)
        self.maximum.setDecimals(6)
        self.maximum.setValue(maximum)

        self.scale_type = QComboBox()
        self.scale_type.addItems(["Linear", "Log"])

        self.direction = QComboBox()
        self.direction.addItems(["Reversed", "Normal"])
        self.direction.setCurrentText("Reversed" if reversed_axis else "Normal")

        self.major_ticks = QComboBox()
        self.major_ticks.addItems(["Automatic", "Interval"])

        self.minor_ticks = QComboBox()
        self.minor_ticks.addItems([str(value) for value in range(0, 11)])
        self.minor_ticks.setCurrentText("4")

        form.addRow("Minimum", self.minimum)
        form.addRow("Maximum", self.maximum)
        form.addRow("Scale type", self.scale_type)
        form.addRow("Direction", self.direction)
        form.addRow("Major ticks", self.major_ticks)
        form.addRow("Minor ticks", self.minor_ticks)
        self.pages.addTab(scale, "Scale")

        for label in ("Appearance", "Labels", "Grid"):
            page = QWidget()
            layout = QVBoxLayout(page)
            note = QLabel(f"{label} controls will be connected during the property-dialog phase.")
            note.setWordWrap(True)
            layout.addWidget(note)
            layout.addStretch(1)
            self.pages.addTab(page, label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._apply_and_accept)
        buttons.rejected.connect(self.reject)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self.apply)
        root.addWidget(buttons)

    def _select_axis(self, target):
        for button in self.axis_buttons:
            button.setChecked(button is target)

    def apply(self):
        self.applied.emit(
            float(self.minimum.value()),
            float(self.maximum.value()),
            self.direction.currentText() == "Reversed",
        )

    def _apply_and_accept(self):
        self.apply()
        self.accept()


class DataTableDocument(QWidget):
    document_kind = "data"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(8, 2)
        self.table.setHorizontalHeaderLabels(["A(X) / cm⁻¹", "B(Y) / Abs."])
        x = [4000, 3500, 3000, 2500, 2000, 1500, 1000, 500]
        y = [0.102, 0.184, 0.221, 0.195, 0.312, 0.481, 0.358, 0.149]
        for row, (x_value, y_value) in enumerate(zip(x, y)):
            self.table.setItem(row, 0, QTableWidgetItem(str(x_value)))
            self.table.setItem(row, 1, QTableWidgetItem(str(y_value)))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)


class PlotDocument(QWidget):
    document_kind = "plot"
    request_axis_properties = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QFrame()
        toolbar.setObjectName("uiV2DocumentToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 3, 6, 3)
        toolbar_layout.addStretch(1)
        axis_button = QPushButton("Axis properties…")
        axis_button.setObjectName("uiV2CompactButton")
        axis_button.clicked.connect(self.request_axis_properties)
        toolbar_layout.addWidget(axis_button)
        layout.addWidget(toolbar)

        self.figure = Figure(figsize=(6.4, 4.2), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)

        x = np.array([4000, 3500, 3000, 2500, 2000, 1500, 1000, 500], dtype=float)
        y = np.array([0.102, 0.184, 0.221, 0.195, 0.312, 0.481, 0.358, 0.149], dtype=float)
        self.axes.plot(x, y, linewidth=1.8, label="ZnO_FTIR")
        self.axes.set_xlabel("Wavenumber (cm⁻¹)")
        self.axes.set_ylabel("Absorbance")
        self.axes.set_title("ZnO FT-IR")
        self.axes.invert_xaxis()
        self.axes.legend(frameon=False)

        self.canvas.mpl_connect("button_press_event", self._mouse_press)
        layout.addWidget(self.canvas, 1)

    def _mouse_press(self, event):
        if getattr(event, "dblclick", False):
            self.request_axis_properties.emit()

    def apply_x_axis(self, minimum, maximum, reversed_axis):
        lo, hi = sorted((minimum, maximum))
        if reversed_axis:
            self.axes.set_xlim(hi, lo)
        else:
            self.axes.set_xlim(lo, hi)
        self.canvas.draw_idle()


class UIV2PrototypeWindow(QMainWindow):
    """Isolated desktop prototype for the proposed UI-v2 architecture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uiV2Prototype")
        self.setWindowTitle("SpectraSuite — UI v2 Prototype")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 650)

        self._subwindows = {}
        self._tree_items = {}

        apply_theme(self, PROTOTYPE_STYLE)
        apply_window_icon(self, "APP")

        self._build_ui()
        self._open_initial_documents()
        QTimer.singleShot(0, self.tile_documents)

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.ribbon_frame = QFrame()
        self.ribbon_frame.setObjectName("uiV2Ribbon")
        ribbon_layout = QVBoxLayout(self.ribbon_frame)
        ribbon_layout.setContentsMargins(0, 0, 0, 0)
        ribbon_layout.setSpacing(0)

        self.ribbon_tabs = QTabWidget()
        self.ribbon_tabs.setObjectName("uiV2RibbonTabs")
        self.ribbon_tabs.setTabPosition(QTabWidget.TabPosition.North)
        ribbon_layout.addWidget(self.ribbon_tabs)
        root_layout.addWidget(self.ribbon_frame)

        for tab_name, groups in RIBBON.items():
            page = QWidget()
            page_layout = QHBoxLayout(page)
            page_layout.setContentsMargins(8, 5, 8, 5)
            page_layout.setSpacing(0)
            for group_name, labels in groups.items():
                page_layout.addWidget(self._ribbon_group(group_name, labels))
            page_layout.addStretch(1)
            self.ribbon_tabs.addTab(page, tab_name)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(self.main_splitter, 1)

        self.project_panel = QFrame()
        self.project_panel.setObjectName("uiV2ProjectPanel")
        project_layout = QVBoxLayout(self.project_panel)
        project_layout.setContentsMargins(6, 6, 6, 6)

        heading_row = QHBoxLayout()
        heading = QLabel("Project Explorer")
        heading.setStyleSheet("font-weight: 700;")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.project_toggle = QToolButton()
        self.project_toggle.setText("‹")
        self.project_toggle.setToolTip("Collapse Project Explorer")
        self.project_toggle.clicked.connect(self.toggle_project_explorer)
        heading_row.addWidget(self.project_toggle)
        project_layout.addLayout(heading_row)

        self.project_tree = QTreeWidget()
        self.project_tree.setObjectName("uiV2ProjectTree")
        self.project_tree.setHeaderHidden(True)
        self.project_tree.itemDoubleClicked.connect(self._activate_tree_item)
        project_layout.addWidget(self.project_tree, 1)

        sample = QTreeWidgetItem(["ZnO_FTIR"])
        sample.setExpanded(True)
        self.project_tree.addTopLevelItem(sample)
        for key, label in (
            ("table", "▦  Raw Data"),
            ("plot", "⌁  FT-IR Plot"),
            ("peaks", "⋮  Peak Results"),
        ):
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            sample.addChild(item)
            self._tree_items[key] = item

        comparison = QTreeWidgetItem(["Comparison"])
        comparison.setExpanded(True)
        overlay = QTreeWidgetItem(["⌁  Overlay Plot"])
        overlay.setData(0, Qt.ItemDataRole.UserRole, "overlay")
        comparison.addChild(overlay)
        self.project_tree.addTopLevelItem(comparison)
        self._tree_items["overlay"] = overlay

        self.main_splitter.addWidget(self.project_panel)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        document_tools = QFrame()
        document_tools.setObjectName("uiV2DocumentToolbar")
        tools_layout = QHBoxLayout(document_tools)
        tools_layout.setContentsMargins(6, 3, 6, 3)

        for text, slot in (
            ("Tile", self.tile_documents),
            ("Data", lambda: self.activate_document("table")),
            ("Plot", lambda: self.activate_document("plot")),
        ):
            button = QPushButton(text)
            button.setObjectName("uiV2CompactButton")
            button.clicked.connect(slot)
            tools_layout.addWidget(button)

        self.active_label = QLabel("Active: —")
        self.active_label.setObjectName("mutedLabel")
        tools_layout.addWidget(self.active_label)
        tools_layout.addStretch(1)
        workspace_layout.addWidget(document_tools)

        self.mdi = QMdiArea()
        self.mdi.setObjectName("uiV2Mdi")
        self.mdi.subWindowActivated.connect(self._subwindow_activated)
        workspace_layout.addWidget(self.mdi, 1)

        self.main_splitter.addWidget(workspace)
        self.main_splitter.setSizes([220, 1220])

        self.setStatusBar(QStatusBar())
        self.technique_status = QLabel("FT-IR")
        self.dataset_status = QLabel("ZnO_FTIR")
        self.point_status = QLabel("8 points")
        self.action_status = QLabel("Ready")
        for widget in (
            self.technique_status,
            self.dataset_status,
            self.point_status,
            self.action_status,
        ):
            self.statusBar().addWidget(widget)
        self.statusBar().addPermanentWidget(QLabel("Zoom 100%"))

    def _ribbon_group(self, title, labels):
        group = QFrame()
        group.setObjectName("uiV2RibbonGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(7, 3, 7, 1)
        layout.setSpacing(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(3)
        for label in labels:
            button = QToolButton()
            button.setObjectName("uiV2RibbonButton")
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.clicked.connect(lambda checked=False, command=label: self.run_command(command))
            buttons.addWidget(button)
        layout.addLayout(buttons)

        caption = QLabel(title)
        caption.setObjectName("uiV2GroupTitle")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)
        return group

    def _open_initial_documents(self):
        self.add_document("table", "Raw Data — ZnO_FTIR", DataTableDocument())

        plot = PlotDocument()
        plot.request_axis_properties.connect(self.open_axis_properties)
        self.add_document("plot", "FT-IR Plot — ZnO_FTIR", plot)

    def add_document(self, key, title, widget):
        subwindow = QMdiSubWindow()
        subwindow.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        subwindow.setWindowTitle(title)
        subwindow.setWidget(widget)
        subwindow.resize(560, 560)
        self.mdi.addSubWindow(subwindow)
        subwindow.show()
        self._subwindows[key] = subwindow
        return subwindow

    def activate_document(self, key):
        subwindow = self._subwindows.get(key)
        if subwindow is None:
            self.action_status.setText(f"{key}: prototype document not implemented yet")
            return
        if subwindow.isHidden():
            subwindow.show()
        self.mdi.setActiveSubWindow(subwindow)
        subwindow.raise_()

    def tile_documents(self):
        for subwindow in self._subwindows.values():
            subwindow.showNormal()
            subwindow.show()
        self.mdi.tileSubWindows()
        self.action_status.setText("Tiled documents")

    def toggle_project_explorer(self):
        visible = self.project_panel.width() > 40
        if visible:
            self.project_panel.setMinimumWidth(34)
            self.project_panel.setMaximumWidth(34)
            self.project_tree.hide()
            self.project_toggle.setText("›")
            self.project_toggle.setToolTip("Show Project Explorer")
        else:
            self.project_panel.setMinimumWidth(180)
            self.project_panel.setMaximumWidth(16777215)
            self.project_tree.show()
            self.project_toggle.setText("‹")
            self.project_toggle.setToolTip("Collapse Project Explorer")
            self.main_splitter.setSizes([220, max(800, self.width() - 220)])

    def _activate_tree_item(self, item, column):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.activate_document(str(key))

    def _subwindow_activated(self, subwindow):
        if subwindow is None:
            return
        key = next((key for key, value in self._subwindows.items() if value is subwindow), None)
        if key is None:
            return

        labels = {
            "table": "Raw Data",
            "plot": "FT-IR Plot",
        }
        self.active_label.setText(f"Active: {labels.get(key, key)}")
        item = self._tree_items.get(key)
        if item is not None:
            self.project_tree.setCurrentItem(item)

        desired_tab = {"table": "Data", "plot": "Plot"}.get(key)
        if desired_tab:
            for index in range(self.ribbon_tabs.count()):
                if self.ribbon_tabs.tabText(index) == desired_tab:
                    self.ribbon_tabs.setCurrentIndex(index)
                    break

    def run_command(self, command):
        self.action_status.setText(command)
        if command in {"Axes", "Properties"}:
            self.open_axis_properties()
        elif command == "Tile":
            self.tile_documents()
        elif command == "Project Explorer":
            self.toggle_project_explorer()
        elif command == "Maximize Active":
            active = self.mdi.activeSubWindow()
            if active is not None:
                active.showMaximized()

    def open_axis_properties(self):
        plot_subwindow = self._subwindows.get("plot")
        if plot_subwindow is None:
            return
        plot = plot_subwindow.widget()
        if not isinstance(plot, PlotDocument):
            return

        x_left, x_right = plot.axes.get_xlim()
        reversed_axis = x_left > x_right
        dialog = AxisPropertiesDialog(
            minimum=x_left,
            maximum=x_right,
            reversed_axis=reversed_axis,
            parent=self,
        )
        dialog.applied.connect(plot.apply_x_axis)
        dialog.applied.connect(
            lambda minimum, maximum, reversed_axis:
            self.action_status.setText("Axis settings applied")
        )
        dialog.exec()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = UIV2PrototypeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
