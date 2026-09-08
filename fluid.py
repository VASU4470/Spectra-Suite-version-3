"""Entry point for the fluid-dynamics plotter."""

import sys
from PySide6.QtWidgets import QApplication
from qt_fluid_plotter import FluidPlotter


def main():
    app=QApplication.instance() or QApplication(sys.argv); app.setApplicationName("SpectraSuite Fluid Dynamics")
    window=FluidPlotter(); window.show(); return app.exec()


def run():return main()


if __name__=="__main__":raise SystemExit(run())
