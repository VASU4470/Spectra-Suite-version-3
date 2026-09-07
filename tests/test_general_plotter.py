"""File-import tests for the General 2D Plotter."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from qt_general_plotter import read_table


class GeneralPlotterImportTests(unittest.TestCase):
    def test_import_keeps_named_columns(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "multi.csv"
            path.write_text("time,a,b\n0,1,2\n1,3,4\n", encoding="utf-8")
            frame = read_table(path)
        self.assertEqual(list(frame.columns), ["time", "a", "b"])
        self.assertEqual(frame.shape, (2, 3))

    def test_headerless_data_is_not_lost(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "xy.txt"
            path.write_text("0 10\n1 20\n2 30\n", encoding="utf-8")
            frame = read_table(path)
        self.assertEqual(frame.shape, (3, 2))
        self.assertEqual(float(frame.iloc[0, 0]), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
