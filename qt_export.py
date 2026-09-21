"""Shared publication sizes, live figure preview, batch export and PDF reports."""
from pathlib import Path
import json
import tempfile

from PySide6.QtCore import Qt, QSettings, QSize, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QProgressDialog, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from plot_export import figure_bytes, save_figure
from report_export import ExportItem, export_batch, save_pdf_report
from qt_theme import LIGHT_STYLE, apply_theme
from qt_pdf_preview import PdfPreviewDocument

# Generic publication widths, rather than a claim of compliance with every journal.
SIZE_PRESETS = (("Custom dimensions", None), ("Single column - 85 mm", (85, None)),
                ("One and a half columns - 120 mm", (120, None)),
                ("Double column - 180 mm", (180, None)),
                ("A4 landscape", (297, 210)), ("A4 portrait", (210, 297)))


class ExportControls(QWidget):
    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self.preferences = QSettings("SpectraSuite", "FigureExport")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.preset = QComboBox()
        for label, size in SIZE_PRESETS:
            self.preset.addItem(label, size)
        self.format = QComboBox(); self.format.addItems(["PDF", "SVG", "PNG", "TIFF", "JPG"])
        self.width = self._dimension(figure.get_figwidth() * 25.4)
        self.height = self._dimension(figure.get_figheight() * 25.4)
        self.dpi = QComboBox(); self.dpi.addItems(["150", "300", "600", "1200"]); self.dpi.setCurrentText("300")
        self.transparent = QCheckBox("Transparent background")
        self.tight = QCheckBox("Trim empty outer margins")
        self.tight.setToolTip(
            "Removes blank padding outside titles, axes and legends. This can make "
            "the saved width and height smaller than the dimensions selected above."
        )
        self.open_folder = QCheckBox("Open destination folder after export")
        self.preset.setMinimumWidth(230)
        self.format.setMinimumWidth(180)
        self.format.view().setMinimumWidth(180)
        self.dpi.setMinimumWidth(120)
        for dimension in (self.width, self.height):
            dimension.setMinimumWidth(180)
        for label, widget in (("Size preset", self.preset), ("Format", self.format),
                              ("Width", self.width), ("Height", self.height), ("DPI", self.dpi)):
            form.addRow(label, widget)
        root.addLayout(form)
        save_preset = QPushButton("Save custom preset…"); save_preset.clicked.connect(self.save_preset)
        root.addWidget(save_preset)
        for control in (self.transparent, self.tight, self.open_folder):
            root.addWidget(control)
        crop_help = QLabel(
            "Trim empty outer margins: removes unused space around the graph. Leave "
            "this off when the journal requires the exact width and height above."
        )
        crop_help.setWordWrap(True)
        crop_help.setObjectName("mutedLabel")
        root.addWidget(crop_help)
        note = QLabel("Column presets keep the current aspect ratio. Check your journal's required width. "
                      "With margin trimming off, the exported canvas has the dimensions above. "
                      "PDF/SVG preserve vectors; DPI controls raster content.")
        note.setWordWrap(True); root.addWidget(note)
        self._load_presets()
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.width.valueChanged.connect(self._custom_dimensions)
        self.height.valueChanged.connect(self._custom_dimensions)
        self.format.currentTextChanged.connect(self._format_changed)

    @staticmethod
    def _dimension(value):
        spin = QDoubleSpinBox(); spin.setRange(10, 1000); spin.setDecimals(2)
        spin.setSuffix(" mm"); spin.setValue(value)
        return spin

    def _custom_dimensions(self):
        self.preset.blockSignals(True); self.preset.setCurrentIndex(0); self.preset.blockSignals(False)

    def _load_presets(self):
        try:
            self.saved_presets = json.loads(self.preferences.value("presets", "{}"))
        except (ValueError, TypeError):
            self.saved_presets = {}
        for name, values in self.saved_presets.items():
            self.preset.addItem("Saved: " + name, values)

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Save export preset", "Preset name")
        if not ok or not name.strip():
            return
        values = {"width": self.width.value(), "height": self.height.value(),
                  "dpi": self.dpi.currentText(), "format": self.format.currentText(),
                  "transparent": self.transparent.isChecked(), "tight": self.tight.isChecked()}
        self.saved_presets[name.strip()] = values
        self.preferences.setValue("presets", json.dumps(self.saved_presets))
        index = self.preset.findText("Saved: " + name.strip())
        if index < 0:
            self.preset.addItem("Saved: " + name.strip(), values)
            index = self.preset.count() - 1
        else:
            self.preset.setItemData(index, values)
        self.preset.setCurrentIndex(index)

    def apply_preset(self):
        preset = self.preset.currentData()
        if not preset:
            return
        self.width.blockSignals(True); self.height.blockSignals(True)
        if isinstance(preset, dict):
            self.width.setValue(preset["width"]); self.height.setValue(preset["height"])
            self.dpi.setCurrentText(preset["dpi"]); self.format.setCurrentText(preset["format"])
            self.transparent.setChecked(preset.get("transparent", False) and preset["format"] != "JPG")
            self.tight.setChecked(preset.get("tight", False))
        else:
            width, height = preset
            ratio = self.height.value() / self.width.value()
            self.width.setValue(width); self.height.setValue(height or width * ratio)
            self.tight.setChecked(False)
        self.width.blockSignals(False); self.height.blockSignals(False)

    def _format_changed(self, value):
        if value == "JPG":
            self.transparent.setChecked(False)
        self.transparent.setEnabled(value != "JPG")

    def options(self):
        return dict(dpi=int(self.dpi.currentText()),
                    size_inches=(self.width.value() / 25.4, self.height.value() / 25.4),
                    transparent=self.transparent.isChecked(), tight=self.tight.isChecked())


class FigureExportDialog(QDialog):
    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self.figure = figure
        self.setWindowTitle("Save figure")
        self.resize(960, 640); self.setMinimumSize(840, 560); apply_theme(self, LIGHT_STYLE)
        root = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.controls = ExportControls(figure)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.controls)
        scroll.setMinimumWidth(390); self.splitter.addWidget(scroll)
        # Keep the existing public option controls for callers and saved tests.
        for name in ("format", "width", "height", "dpi", "transparent", "tight", "open_folder", "preset"):
            setattr(self, name, getattr(self.controls, name))
        panel = QWidget(); self.preview_layout = QVBoxLayout(panel)
        self.preview = QLabel("Preparing preview…"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview.setMinimumSize(280, 260); self.preview.setStyleSheet("background: #e2e8f0; border: 1px solid #cbd5e1")
        self.preview_layout.addWidget(self.preview, 1)
        self.preview_note = QLabel("Layout preview at screen resolution. Export uses the selected DPI.")
        self.preview_note.setWordWrap(True); self.preview_layout.addWidget(self.preview_note)
        self.splitter.addWidget(panel); self.splitter.setSizes([410, 550])
        root.addWidget(self.splitter, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        advanced = self.buttons.addButton("Batch / PDF report…", QDialogButtonBox.ButtonRole.ActionRole)
        advanced.clicked.connect(lambda: self.done(2))
        self.advanced_button = advanced
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.preview_timer = QTimer(self); self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.refresh_preview)
        for control in (self.width, self.height):
            control.valueChanged.connect(self.schedule_preview)
        for control in (self.format, self.dpi, self.preset):
            control.currentIndexChanged.connect(self.schedule_preview)
        for control in (self.transparent, self.tight):
            control.toggled.connect(self.schedule_preview)
        self.schedule_preview()

    def options(self):
        return self.controls.options()

    def schedule_preview(self, *_args):
        self.preview_timer.start(180)

    def preview_figure(self):
        return self.figure

    def refresh_preview(self):
        try:
            options = self.options()
            w, h = options["size_inches"]
            options["dpi"] = max(12, min(110, 900 / max(w, h)))
            pixmap = QPixmap()
            pixmap.loadFromData(figure_bytes(self.preview_figure(), **options))
            if pixmap.isNull():
                raise ValueError("Could not render the figure preview.")
            self.preview.setPixmap(pixmap.scaled(self.preview.size() - QSize(16, 16),
                                                Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
            self.preview_note.setText("Layout preview at screen resolution. Export uses the selected DPI.")
        except Exception as error:
            self.preview.setText("Preview unavailable")
            self.preview_note.setText(str(error))
        finally:
            self.figure.canvas.draw_idle()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_timer"):
            self.schedule_preview()

    def done(self, result):
        self.preview_timer.stop()
        super().done(result)


class BatchExportDialog(FigureExportDialog):
    def __init__(self, items, parent=None):
        self.items = list(items)
        self.saved_path = None
        self._temporary = tempfile.TemporaryDirectory(prefix="spectrasuite-preview-")
        self.pdf = None
        super().__init__(self.items[0].figure(), parent)
        self.setWindowTitle("Export selected datasets / PDF report")
        self.resize(1050, 730)
        self.advanced_button.hide()
        self.dataset_list = QListWidget()
        for index, item in enumerate(self.items):
            row = QListWidgetItem(item.name)
            row.setToolTip(item.name + "\n" + item.source)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked)
            self.dataset_list.addItem(row)
        self.dataset_list.setMinimumHeight(90)
        self.dataset_list.setMaximumHeight(110)
        self.controls.layout().insertWidget(0, self.dataset_list)
        self.selection_note = QLabel()
        self.controls.layout().insertWidget(1, self.selection_note)
        row = QHBoxLayout()
        for label, checked in (("Select all", True), ("Clear", False)):
            button = QPushButton(label); button.clicked.connect(lambda _=False, value=checked: self.check_all(value))
            row.addWidget(button)
        self.controls.layout().insertLayout(2, row)
        self.include_figures = QCheckBox("Individual figures"); self.include_figures.setChecked(True)
        self.include_data = QCheckBox("CSV data"); self.include_data.setChecked(True)
        self.include_report = QCheckBox("Multi-page PDF report"); self.include_report.setChecked(True)
        for index, control in enumerate((self.include_figures, self.include_data, self.include_report), 3):
            self.controls.layout().insertWidget(index, control)
        note = QLabel("A new export folder includes results, processing settings and a file manifest. "
                      "Reports use A4 pages with vector figures and paginated results/settings. "
                      "Per-dataset figures include stored analysis markers. Save the current figure to include workspace drawings.")
        note.setWordWrap(True); self.controls.layout().addWidget(note)
        self.report_preview = QPushButton("Preview complete PDF report")
        self.report_preview.clicked.connect(self.preview_report)
        self.preview_layout.addWidget(self.report_preview)
        self.report_page = QComboBox(); self.report_page.hide()
        self.report_page.currentIndexChanged.connect(self.render_report_page)
        self.preview_layout.addWidget(self.report_page)
        self.pdf = PdfPreviewDocument(self)
        self.dataset_list.itemChanged.connect(self.selection_changed)
        self.dataset_list.currentRowChanged.connect(self.schedule_preview)
        self.dataset_list.setCurrentRow(0)
        self.buttons.accepted.disconnect(); self.buttons.accepted.connect(self.save_outputs)
        self.selection_changed()

    def selected_items(self):
        return [item for index, item in enumerate(self.items)
                if self.dataset_list.item(index).checkState() == Qt.CheckState.Checked]

    def check_all(self, checked):
        self.dataset_list.blockSignals(True)
        for index in range(self.dataset_list.count()):
            self.dataset_list.item(index).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.dataset_list.blockSignals(False); self.selection_changed()

    def selection_changed(self, *_args):
        selected = self.selected_items()
        self.selection_note.setText(f"{len(selected)} of {len(self.items)} selected")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(selected))
        self.report_preview.setEnabled(bool(selected))
        self.schedule_preview()

    def preview_figure(self):
        index = self.dataset_list.currentRow() if hasattr(self, "dataset_list") else 0
        return self.items[max(0, index)].figure()

    def schedule_preview(self, *_args):
        if self.pdf is not None:
            self.pdf.close()
            self.report_page.hide()
        super().schedule_preview()

    def preview_report(self):
        items = self.selected_items()
        if not items:
            return
        self.preview_timer.stop(); self.pdf.close()
        path = Path(self._temporary.name) / "report.pdf"
        try:
            save_pdf_report(items, path, options=self.options())
            self.pdf.load_path(path)
            count = self.pdf.pageCount()
            if not count:
                raise ValueError("The report preview could not be opened.")
            self.report_page.blockSignals(True); self.report_page.clear()
            self.report_page.addItems([f"Report page {i + 1} of {count}" for i in range(count)])
            self.report_page.blockSignals(False); self.report_page.show()
            self.render_report_page(0)
        except Exception as error:
            QMessageBox.warning(self, "Report preview", str(error))

    def render_report_page(self, index):
        if index < 0 or self.pdf is None or not self.pdf.pageCount():
            return
        size = self.pdf.pagePointSize(index)
        size.scale(self.preview.size() - QSize(12, 12), Qt.AspectRatioMode.KeepAspectRatio)
        image = self.pdf.render(index, size.toSize())
        self.preview.setPixmap(QPixmap.fromImage(image))
        self.preview_note.setText("Complete PDF report preview. Use the page selector to review figures, results and settings.")

    def save_outputs(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder for a new export bundle")
        if not folder:
            return
        selected = self.selected_items()
        progress = QProgressDialog("Exporting selected datasets…", "Cancel", 0, len(selected), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        def update(index, total, name):
            progress.setMaximum(total); progress.setValue(index); progress.setLabelText(name)
            if progress.wasCanceled():
                raise InterruptedError("Export cancelled; no incomplete bundle was saved.")
        try:
            self.saved_path = export_batch(selected, folder, extension=self.format.currentText().lower(),
                                           options=self.options(), include_data=self.include_data.isChecked(),
                                           include_figures=self.include_figures.isChecked(),
                                           include_report=self.include_report.isChecked(), progress=update)
        except Exception as error:
            QMessageBox.warning(self, "Export did not finish", str(error))
            return
        finally:
            progress.close()
        if self.open_folder.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path)))
        QMessageBox.information(self, "Export complete", f"Saved {len(selected)} selected dataset(s) to:\n{self.saved_path}")
        self.accept()

    def done(self, result):
        if self.pdf is not None:
            self.pdf.close()
        self._temporary.cleanup()
        super().done(result)


def workspace_export_items(parent, figure, name):
    if hasattr(parent, "export_items"):
        return parent.export_items()
    settings = {}
    for key, control in vars(parent).items():
        if isinstance(control, QComboBox):
            settings[key] = control.currentText()
        elif isinstance(control, QCheckBox):
            settings[key] = control.isChecked()
        elif hasattr(control, "value") and callable(control.value):
            settings[key] = control.value()
        elif hasattr(control, "text") and callable(control.text):
            settings[key] = control.text()
    return [ExportItem(name, lambda: figure, settings=settings)]


def export_batch_dialog(parent, items):
    if not items:
        QMessageBox.information(parent, "No data", "Load and plot data before exporting.")
        return None
    dialog = BatchExportDialog(items, parent)
    dialog.exec()
    return dialog.saved_path


def export_figure_dialog(parent, figure, suggested_name="figure"):
    if not figure.axes:
        QMessageBox.information(parent, "No figure", "Plot data before exporting a figure.")
        return None
    dialog = FigureExportDialog(figure, parent)
    result = dialog.exec()
    if result == 2:
        return export_batch_dialog(parent, workspace_export_items(parent, figure, suggested_name))
    if result != QDialog.DialogCode.Accepted:
        return None
    suffix = "." + dialog.format.currentText().lower()
    name, selected = QFileDialog.getSaveFileName(parent, "Save figure", str(Path(suggested_name).with_suffix(suffix)),
                                               f"{dialog.format.currentText()} (*{suffix})")
    if not name:
        return None
    path = Path(name).with_suffix(suffix)
    if str(path) != name and path.exists():
        if QMessageBox.question(parent, "Replace figure?", f"Replace the existing file?\n{path}") != QMessageBox.StandardButton.Yes:
            return None
    try:
        saved = save_figure(figure, path, selected_filter=selected, **dialog.options())
    except Exception as error:
        QMessageBox.critical(parent, "Figure export failed", f"Could not save {path.name}:\n{error}")
        return None
    finally:
        figure.canvas.draw_idle()
    if dialog.open_folder.isChecked():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved.parent.resolve())))
    QMessageBox.information(parent, "Figure saved", f"Saved to:\n{saved}")
    return saved
