"""Render generated PDFs without holding operating-system file handles open."""
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtPdf import QPdfDocument


class PdfPreviewDocument(QPdfDocument):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffer = QBuffer(self)

    def load_path(self, filename):
        data = Path(filename).read_bytes()
        self.close()
        self._buffer.setData(data)
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        super().load(self._buffer)

    def close(self):
        super().close()
        self._buffer.close()
