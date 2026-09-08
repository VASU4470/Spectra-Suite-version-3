"""Entry point for the general 3D Plotter."""

import sys
from PySide6.QtWidgets import QApplication
from qt_3d_plotter import Plot3D


def main():
    app=QApplication.instance() or QApplication(sys.argv); app.setApplicationName("SpectraSuite 3D Plotter")
    window=Plot3D(); window.show(); return app.exec()


def run():return main()


if __name__=="__main__":raise SystemExit(run())
