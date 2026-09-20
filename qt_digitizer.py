"""One shared image-to-data dialog for file, clipboard and dropped graph images."""
from pathlib import Path
import json

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from image_digitizer import AxisCalibration, DigitizedCurve, color_trace, image_provenance
from qt_theme import LIGHT_STYLE
from qt_widgets import CompactNavigationToolbar

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
IMAGE_FILTER = "Graph images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
MAX_IMAGE_PIXELS = 16_000_000


class ImageDigitizerDialog(QDialog):
    def __init__(self, parent=None, image=None, source="Clipboard", *, action_label="Use digitized data"):
        super().__init__(parent)
        self.setWindowTitle("Image to data - calibrated graph digitizer")
        self.resize(1080, 720); self.setMinimumSize(820, 570); self.setStyleSheet(LIGHT_STYLE)
        self.result_curve = None; self.rgb = None; self.source = source
        self.calibration_pixels = []; self.points = []; self.history = []; self.mode = "calibrate"
        self.method = "manual"; self.color = None
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        for text, slot in (("Open image…", self.open_image), ("Paste image", self.paste_image),
                           ("Recalibrate", self.recalibrate), ("Undo", self.undo), ("Clear points", self.clear_points)):
            button = QPushButton(text); button.clicked.connect(slot); top.addWidget(button)
        root.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(); left_layout = QVBoxLayout(left)
        self.figure = Figure(); self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = CompactNavigationToolbar(self.canvas, self)
        left_layout.addWidget(self.canvas, 1); left_layout.addWidget(self.toolbar)
        split.addWidget(left)
        controls = QWidget(); form_layout = QVBoxLayout(controls)
        self.instruction = QLabel("Open, paste or drop a graph image."); self.instruction.setWordWrap(True)
        form_layout.addWidget(self.instruction)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name = QLineEdit("Digitized curve")
        self.xlabel = QLineEdit("X"); self.ylabel = QLineEdit("Y")
        form.addRow("Curve name", self.name); form.addRow("X label / units", self.xlabel); form.addRow("Y label / units", self.ylabel)
        self.values = []
        for name, initial in (("X0 at origin", 0), ("X1 along X", 1), ("Y0 at origin", 0), ("Y1 along Y", 1)):
            spin = QDoubleSpinBox(); spin.setDecimals(10); spin.setRange(-1e15, 1e15); spin.setValue(initial)
            spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed); spin.setMinimumWidth(100)
            spin.valueChanged.connect(self.refresh_status); self.values.append(spin); form.addRow(name, spin)
        self.x_log = QCheckBox("Log X"); self.y_log = QCheckBox("Log Y")
        self.x_log.toggled.connect(self.refresh_status); self.y_log.toggled.connect(self.refresh_status)
        form.addRow(self.x_log, self.y_log)
        form_layout.addLayout(form)
        trace = QPushButton("Pick curve color")
        trace.clicked.connect(lambda: self.set_mode("color")); form_layout.addWidget(trace)
        self.tolerance = QSpinBox(); self.tolerance.setRange(0, 120); self.tolerance.setValue(35)
        self.spacing = QSpinBox(); self.spacing.setRange(1, 30); self.spacing.setValue(3)
        colors = QFormLayout(); colors.addRow("Color tolerance", self.tolerance); colors.addRow("Pixel sampling step", self.spacing)
        form_layout.addLayout(colors)
        auto = QPushButton("Trace selected color"); auto.clicked.connect(self.trace_color); form_layout.addWidget(auto)
        manual = QPushButton("Add points manually"); manual.clicked.connect(lambda: self.set_mode("manual")); form_layout.addWidget(manual)
        self.status = QLabel("No points"); self.status.setWordWrap(True); form_layout.addWidget(self.status)
        note = QLabel("Calibrate a flat XY graph using three axis points. Enter the axis values and units yourself. "
                      "Color tracing follows the largest connected curve; grids, legends, dashed or overlapping curves may need manual points. "
                      "Review the red markers. Digitized values are approximate.")
        note.setWordWrap(True); form_layout.addWidget(note)
        form_layout.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(controls); scroll.setMinimumWidth(300)
        split.addWidget(scroll); split.setSizes([740, 340]); root.addWidget(split, 1)
        row = QHBoxLayout()
        self.csv_button = QPushButton("Export CSV + calibration…"); self.csv_button.clicked.connect(self.export_csv)
        self.use_button = QPushButton(action_label); self.use_button.setObjectName("primary"); self.use_button.clicked.connect(self.use_data)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        row.addWidget(self.csv_button); row.addStretch(); row.addWidget(cancel); row.addWidget(self.use_button); root.addLayout(row)
        self.canvas.mpl_connect("button_press_event", self.image_click)
        shortcut = QShortcut(QKeySequence.StandardKey.Paste, self); shortcut.activated.connect(self.paste_image)
        self.setAcceptDrops(True)
        if image is not None:
            self.load_image(image, source)
        self.refresh_status()

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open graph image", "", IMAGE_FILTER)
        if path:
            self.load_image(path, path)

    def paste_image(self):
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            self.load_image(image, "Clipboard image")
        else:
            urls = clipboard.mimeData().urls()
            path = next((u.toLocalFile() for u in urls if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES), None)
            if path:
                self.load_image(path, path)
            else:
                QMessageBox.information(self, "Paste image", "Copy an image or image file first.")

    def load_image(self, image, source="Image"):
        try:
            if isinstance(image, (str, Path)):
                reader = QImageReader(str(image)); size = reader.size()
                if size.width() * size.height() > MAX_IMAGE_PIXELS:
                    raise ValueError("Use an image smaller than 16 megapixels.")
                reader.setAutoTransform(True); image = reader.read()
            if image.isNull():
                raise ValueError("This image could not be read.")
            if image.width() * image.height() > MAX_IMAGE_PIXELS:
                raise ValueError("Use an image smaller than 16 megapixels.")
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            rgba = np.frombuffer(image.bits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
            rgba = rgba[:, :image.width() * 4].reshape(image.height(), image.width(), 4).copy()
            alpha = rgba[:, :, 3:4].astype(float) / 255
            self.rgb = np.asarray(rgba[:, :, :3] * alpha + 255 * (1 - alpha), dtype=np.uint8)
            self.source = str(source); self.name.setText(Path(str(source)).stem + " (digitized)")
            self.calibration_pixels = []; self.points = []; self.history = []; self.color = None
            self.mode = "calibrate"; self.method = "manual"
            self.draw_image(); self.refresh_status()
        except Exception as error:
            QMessageBox.warning(self, "Image import", str(error))

    def calibration(self):
        if len(self.calibration_pixels) != 3:
            raise ValueError("Click the origin, a point along X, then a point along Y.")
        calibration = AxisCalibration(*self.calibration_pixels, *[spin.value() for spin in self.values],
                                      self.x_log.isChecked(), self.y_log.isChecked())
        calibration.matrix()
        return calibration

    def set_mode(self, mode):
        if len(self.calibration_pixels) < 3:
            mode = "calibrate"
        self.mode = mode; self.refresh_status()

    def recalibrate(self):
        self.calibration_pixels = []; self.mode = "calibrate"
        self.draw_image(); self.refresh_status()

    def image_click(self, event):
        if (self.rgb is None or event.inaxes is not getattr(self, "ax", None)
                or event.xdata is None or event.ydata is None or self.toolbar.mode):
            return
        if event.button == 3:
            self.undo(); return
        if event.button != 1:
            return
        x, y = float(event.xdata), float(event.ydata)
        if not (0 <= x < self.rgb.shape[1] and 0 <= y < self.rgb.shape[0]):
            return
        if self.mode == "calibrate":
            self.calibration_pixels.append((x, y))
            if len(self.calibration_pixels) == 3:
                self.mode = "manual"
        elif self.mode == "color":
            self.color = self.rgb[int(y), int(x)].tolist(); self.mode = "manual"
        else:
            self.history.append((list(self.points), self.method))
            self.points.append((x, y)); self.method = "manual" if self.method == "manual" else "color trace + manual edits"
        self.draw_image(); self.refresh_status()

    def trace_color(self):
        try:
            if self.color is None:
                raise ValueError("Click Pick curve color, then click on the curve in the image.")
            pixels = color_trace(self.rgb, self.color, self.calibration(), self.tolerance.value(), self.spacing.value())
            self.history.append((list(self.points), self.method)); self.points = [tuple(p) for p in pixels]
            self.method = "color trace"
            self.draw_image(); self.refresh_status()
        except Exception as error:
            QMessageBox.warning(self, "Color trace", str(error))

    def undo(self):
        if self.mode == "calibrate" and self.calibration_pixels:
            self.calibration_pixels.pop()
        elif self.history:
            self.points, self.method = self.history.pop()
        self.draw_image(); self.refresh_status()

    def clear_points(self):
        self.history.append((list(self.points), self.method)); self.points = []; self.method = "manual"
        self.draw_image(); self.refresh_status()

    def draw_image(self):
        if self.rgb is None:
            return
        limits = (self.ax.get_xlim(), self.ax.get_ylim()) if hasattr(self, "ax") and self.ax.images and self.ax.images[0].get_array().shape == self.rgb.shape else None
        self.figure.clear(); self.ax = self.figure.add_subplot()
        self.ax.imshow(self.rgb); self.ax.set_axis_off()
        for index, (x, y) in enumerate(self.calibration_pixels):
            self.ax.plot(x, y, "+", color="#16a34a", markersize=12, markeredgewidth=2)
            self.ax.annotate(("Origin", "X1", "Y1")[index], (x, y), xytext=(6, 6), textcoords="offset points", color="#15803d")
        if self.points:
            points = np.asarray(self.points); self.ax.scatter(points[:, 0], points[:, 1], s=13, color="#ef4444", marker="x")
        if limits:
            self.ax.set_xlim(*limits[0]); self.ax.set_ylim(*limits[1])
        self.figure.subplots_adjust(left=.01, right=.99, bottom=.01, top=.99); self.canvas.draw_idle()

    def refresh_status(self, *_args):
        if not hasattr(self, "use_button"):
            return
        ready = False
        if self.rgb is None:
            instruction = "Open, paste or drop a graph image."
        elif self.mode == "calibrate":
            instruction = ("1. Click the axis origin corner (X0, Y0).",
                           "2. Click a point along the X axis at (X1, Y0).",
                           "3. Click a point along the Y axis at (X0, Y1).")[min(2, len(self.calibration_pixels))]
        elif self.mode == "color":
            instruction = "Click directly on the curve to sample its color."
        else:
            instruction = "Click along the curve to add points. Right-click undoes the last edit. Use pan/zoom for precision."
        self.instruction.setText(instruction)
        try:
            xy = self.calibration().convert(self.points)
            ready = len(xy) >= 2
            ranges = (f"\nX: {xy[:,0].min():.5g} to {xy[:,0].max():.5g}; Y: {xy[:,1].min():.5g} to {xy[:,1].max():.5g}" if ready else "")
            self.status.setText(f"{len(xy)} points | {self.method}" + ranges + (f"\nRGB {self.color}" if self.color else ""))
        except ValueError as error:
            self.status.setText(str(error))
        self.use_button.setEnabled(ready); self.csv_button.setEnabled(ready)

    def curve(self):
        calibration = self.calibration(); xy = calibration.convert(self.points)
        if len(xy) < 2:
            raise ValueError("Review at least two extracted points before using the data.")
        order = np.argsort(xy[:, 0], kind="stable"); xy = xy[order]
        metadata = image_provenance(self.rgb, self.source, calibration, self.method, np.asarray(self.points)[order])
        metadata.update(xlabel=self.xlabel.text().strip() or "X", ylabel=self.ylabel.text().strip() or "Y")
        return DigitizedCurve(self.name.text().strip() or "Digitized curve", xy[:, 0], xy[:, 1],
                              metadata["xlabel"], metadata["ylabel"], metadata)

    def use_data(self):
        try:
            self.result_curve = self.curve(); self.accept()
        except ValueError as error:
            QMessageBox.warning(self, "Digitized data", str(error))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export digitized data", "digitized.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            from pandas import DataFrame
            curve = self.curve(); target = Path(path).with_suffix(".csv")
            DataFrame({curve.xlabel: curve.x, curve.ylabel if curve.ylabel != curve.xlabel else curve.ylabel + " (Y)": curve.y}).to_csv(target, index=False)
            target.with_suffix(".calibration.json").write_text(json.dumps(curve.metadata, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Data saved", f"Saved data and image calibration to:\n{target}")
        except Exception as error:
            QMessageBox.warning(self, "Data export", str(error))

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage() or any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage():
            self.load_image(QImage(mime.imageData()), "Dropped image")
        else:
            path = next((u.toLocalFile() for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES), None)
            if path:
                self.load_image(path, path)
        event.acceptProposedAction()
