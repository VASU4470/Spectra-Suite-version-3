"""Figure export controls shared by every plotting workspace."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QLabel, QMessageBox, QVBoxLayout,
)

from plot_export import save_figure
from qt_theme import LIGHT_STYLE


class FigureExportDialog(QDialog):
    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save figure")
        self.setMinimumWidth(410)
        self.setStyleSheet(LIGHT_STYLE)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.format = QComboBox()
        self.format.addItems(["PDF", "SVG", "PNG", "TIFF", "JPG"])
        self.width = self._dimension(figure.get_figwidth() * 25.4)
        self.height = self._dimension(figure.get_figheight() * 25.4)
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "300", "600", "1200"])
        self.dpi.setCurrentText("300")
        self.transparent = QCheckBox("Transparent background")
        self.tight = QCheckBox("Crop to content (changes final dimensions)")
        self.open_folder = QCheckBox("Open destination folder after export")
        for label, widget in (("Format", self.format), ("Width", self.width),
                              ("Height", self.height), ("Raster resolution (DPI)", self.dpi)):
            form.addRow(label, widget)
        root.addLayout(form)
        root.addWidget(self.transparent)
        root.addWidget(self.tight)
        root.addWidget(self.open_folder)
        note = QLabel("PDF and SVG keep lines and text as vectors. DPI affects raster content. "
                      "With cropping off, the saved figure uses the exact dimensions above.")
        note.setWordWrap(True)
        root.addWidget(note)
        self.format.currentTextChanged.connect(self._format_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _dimension(value):
        spin = QDoubleSpinBox()
        spin.setRange(10, 1000)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    def _format_changed(self, value):
        if value == "JPG":
            self.transparent.setChecked(False)
        self.transparent.setEnabled(value != "JPG")

    def options(self):
        return dict(dpi=int(self.dpi.currentText()),
                    size_inches=(self.width.value()/25.4, self.height.value()/25.4),
                    transparent=self.transparent.isChecked(), tight=self.tight.isChecked())


def export_figure_dialog(parent, figure, suggested_name="figure"):
    if not figure.axes:
        QMessageBox.information(parent, "No figure", "Plot data before exporting a figure.")
        return None
    dialog = FigureExportDialog(figure, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    suffix = "." + dialog.format.currentText().lower()
    name, selected = QFileDialog.getSaveFileName(
        parent, "Save figure", str(Path(suggested_name).with_suffix(suffix)),
        f"{dialog.format.currentText()} (*{suffix})")
    if not name:
        return None
    # A format selection must not accidentally save a PDF as filename.png.
    path = Path(name).with_suffix(suffix)
    if str(path) != name and path.exists():
        answer = QMessageBox.question(parent, "Replace figure?", f"Replace the existing file?\n{path}")
        if answer != QMessageBox.StandardButton.Yes:
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
