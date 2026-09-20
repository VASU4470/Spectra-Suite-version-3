"""Consistent local file/image drops and image paste across plotting workspaces."""
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QStyle, QWidget

from qt_digitizer import IMAGE_SUFFIXES, ImageDigitizerDialog

DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".dat", ".xy", ".xlsx", ".xls", ".dpt", ".asr", ".raw", ".asc", ".plt", ".zip", ".spe"}


def local_import_paths(paths, suffixes=DATA_SUFFIXES):
    result = []
    for value in paths:
        path = Path(value)
        entries = sorted(path.rglob("*")) if path.is_dir() else [path]
        for entry in entries:
            relative = entry.relative_to(path) if path.is_dir() else Path(entry.name)
            if (entry.is_file() and entry.suffix.lower() in suffixes
                    and not any(p.startswith(".") or p == "__MACOSX" for p in relative.parts)):
                resolved = str(entry.resolve())
                if resolved not in result:
                    result.append(resolved)
    return result


def mime_image(mime):
    value = mime.imageData()
    return value.toImage() if isinstance(value, QPixmap) else QImage(value)


class ImportDropFilter(QObject):
    def __init__(self, owner, load_paths, on_curve, *, suffixes=None):
        super().__init__(owner)
        self.owner = owner; self.load_paths = load_paths; self.on_curve = on_curve
        self.suffixes = DATA_SUFFIXES if suffixes is None else set(suffixes)
        for widget in [owner, *owner.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def accepts(self, mime):
        return mime.hasImage() or any(u.isLocalFile() and
                                     (Path(u.toLocalFile()).is_dir() or Path(u.toLocalFile()).suffix.lower() in self.suffixes | IMAGE_SUFFIXES)
                                     for u in mime.urls())

    def open_digitizer(self, image=None, source="Image"):
        dialog = ImageDigitizerDialog(self.owner, image, source)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_curve(dialog.result_curve)

    def import_mime(self, mime):
        urls = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        data = local_import_paths(urls, self.suffixes)
        if data:
            self.load_paths(data)
        images = local_import_paths(urls, IMAGE_SUFFIXES)
        if images:
            for path in images:
                self.open_digitizer(path, path)
        elif mime.hasImage():
            self.open_digitizer(mime_image(mime), "Pasted or dropped image")

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in {QEvent.Type.DragEnter, QEvent.Type.DragMove} and self.accepts(event.mimeData()):
            event.acceptProposedAction(); return True
        if kind == QEvent.Type.Drop and self.accepts(event.mimeData()):
            event.acceptProposedAction()
            try:
                self.import_mime(event.mimeData())
            except Exception as error:
                QMessageBox.warning(self.owner, "Import", str(error))
            return True
        if kind in {QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress} and event.matches(QKeySequence.StandardKey.Paste):
            mime = QApplication.clipboard().mimeData()
            images = mime.hasImage() or any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES for u in mime.urls())
            if images:
                event.accept()
                if kind == QEvent.Type.KeyPress:
                    self.import_mime(mime)
                return True
        return super().eventFilter(watched, event)


def install_import_support(owner, load_paths, on_curve, *, suffixes=None):
    owner.import_support = ImportDropFilter(owner, load_paths, on_curve, suffixes=suffixes)
    action = QAction("Image to data…", owner)
    action.setIcon(owner.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
    action.setToolTip("Image to data: open, paste or drop a graph image (Ctrl+Shift+I)")
    action.setShortcut(QKeySequence("Ctrl+Shift+I")); action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    action.triggered.connect(lambda: owner.import_support.open_digitizer())
    owner.addAction(action); owner.image_to_data_action = action
    if hasattr(owner, "toolbar"):
        owner.toolbar.addSeparator(); owner.toolbar.addAction(action)
    return owner.import_support


def open_curve_in_2d(owner, curve):
    window = owner.window()
    if hasattr(window, "add_digitized_document"):
        return window.add_digitized_document(curve)
    from qt_general_plotter import GeneralPlotter
    plotter = GeneralPlotter(); plotter.import_digitized(curve); plotter.show()
    owner._digitized_plot_window = plotter
    return plotter
