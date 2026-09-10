"""File-import tests for the General 2D Plotter."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from qt_general_plotter import detect_delimiter, parse_axis_limits, read_table


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

    def test_common_delimiters_are_detected(self):
        cases = {
            "comma.csv": ("x,y\n1,2\n3,4\n", ","),
            "tab.tsv": ("x\ty\n1\t2\n3\t4\n", "\t"),
            "space.txt": ("x   y\n1   2\n3   4\n", r"\s+"),
        }
        with TemporaryDirectory() as folder:
            for name, (content, expected) in cases.items():
                with self.subTest(name=name):
                    path = Path(folder) / name
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(detect_delimiter(path), expected)
                    self.assertEqual(read_table(path).shape, (2, 2))

    def test_manual_axis_limits(self):
        self.assertIsNone(parse_axis_limits(""))
        self.assertEqual(parse_axis_limits("10, -2"), [-2.0, 10.0])
        with self.assertRaises(ValueError):
            parse_axis_limits("5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
