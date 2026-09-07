"""Entry point for the spreadsheet-style General 2D Plotter."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication

from config import state
from qt_general_plotter import GeneralPlotter


def main():
    state.technique = "GENERAL"
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite General 2D Plotter")
    window = GeneralPlotter()
    window.show()
    return app.exec()


def run():
    try:
        return main()
    except Exception:
        report = Path.home() / "Desktop" / "CRASH_REPORT_GENERAL.txt"
        try:
            report.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(run())
