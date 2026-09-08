"""Entry point for the Multi-X / Multi-Y Plotter."""

from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication
from qt_multi_axis_plotter import MultiAxisPlotter


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite Multi-X Multi-Y Plotter")
    window = MultiAxisPlotter(); window.show()
    return app.exec()


def run(): return main()


if __name__ == "__main__": raise SystemExit(run())
