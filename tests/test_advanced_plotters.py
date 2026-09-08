"""Off-screen construction and rendering tests for new plotting workspaces."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

from PySide6.QtWidgets import QApplication, QTableWidgetItem

from qt_3d_plotter import Plot3D
from qt_fluid_plotter import FluidPlotter
from qt_multi_axis_plotter import MultiAxisPlotter


class AdvancedPlotterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets(): widget.close()
        self.app.processEvents()

    @staticmethod
    def fill_table(table, columns):
        for col, values in enumerate(columns):
            for row, value in enumerate(values): table.setItem(row, col, QTableWidgetItem(str(value)))

    def test_multi_axis_independent_pairs(self):
        plotter = MultiAxisPlotter(); self.fill_table(plotter.table, ([0, 1, 2], [1, 2, 4]))
        plotter.plot_data(); self.assertGreaterEqual(len(plotter.figure.axes), 1)
        plotter.add_mapping(); plotter.mapping_table.cellWidget(1, 3).setCurrentText("Top")
        plotter.mapping_table.cellWidget(1, 4).setCurrentText("Right"); plotter.plot_data()
        self.assertGreaterEqual(len(plotter.figure.axes), 3)
        self.assertFalse(plotter.windowIcon().isNull())
        plotter.data_toggle.click(); self.assertTrue(plotter.data_panel.isHidden())
        self.assertEqual(plotter.data_toggle.text(), "▶")

    def test_3d_plot_types(self):
        plotter = Plot3D()
        self.fill_table(plotter.table, ([0, 0, 1, 1], [0, 1, 0, 1], [0, 1, 1, 2]))
        for kind in ("3D scatter", "Triangulated surface", "Structured surface", "Wireframe", "3D contour", "Projected contour"):
            with self.subTest(kind=kind):
                plotter.plot_type.setCurrentText(kind); plotter.plot_data(); self.assertGreaterEqual(len(plotter.figure.axes), 1)
        self.assertFalse(plotter.windowIcon().isNull())
        plotter.controls_toggle.click(); self.assertTrue(plotter.controls_scroll.isHidden())
        self.assertEqual(plotter.controls_toggle.text(), "◀")

    def test_fluid_workspace_loads_and_renders(self):
        text='''TITLE="Velocity"\nVARIABLES="X"\n"Y"\n"U"\nZONE T="Grid"\nI=2 J=3 K=1,F=POINT\n0 0 1\n0 1 2\n0 2 3\n1 0 4\n1 1 5\n1 2 6\n'''
        with TemporaryDirectory() as folder:
            path=Path(folder)/"velocity.plt"; path.write_text(text,encoding="utf-8")
            plotter=FluidPlotter(); plotter.load_paths([str(path)])
            for kind in ("Filled contour", "Contour lines", "Heatmap", "3D surface", "3D wireframe", "Profile along X", "Profile along Y", "Grid of fields", "Mesh geometry"):
                with self.subTest(kind=kind):
                    plotter.plot_type.setCurrentText(kind); plotter.plot_selected(); self.assertGreaterEqual(len(plotter.figure.axes), 1)
            self.assertFalse(plotter.windowIcon().isNull())
            plotter.toolbar_toggle.click(); self.assertTrue(plotter.toolbar.isHidden())
            self.assertEqual(plotter.toolbar_toggle.text(), "▲")


if __name__ == "__main__": unittest.main(verbosity=2)
