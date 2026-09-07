"""Tests for multi-sheet and repeated-column spectrum discovery."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from dataset_reader import discover_spectra


class DatasetReaderTests(unittest.TestCase):
    def test_repeated_xy_pairs_are_separate_datasets(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "samples.csv"
            path.write_text(
                "Sample A,,Sample B,\nWavelength,Absorbance,Wavelength,Absorbance\n"
                "1,10,1,20\n2,11,2,21\n3,12,3,22\n",
                encoding="utf-8",
            )
            datasets = discover_spectra(path)
        self.assertEqual([item.name for item in datasets], [
            "samples — Sample A", "samples — Sample B",
        ])
        self.assertEqual(datasets[1].y.tolist(), [20.0, 21.0, 22.0])

    def test_shared_x_with_multiple_y_columns(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "shared.csv"
            path.write_text("Wavelength,A,B\n1,10,20\n2,11,21\n3,12,22\n", encoding="utf-8")
            datasets = discover_spectra(path)
        self.assertEqual(len(datasets), 2)
        self.assertEqual(datasets[0].x.tolist(), [1.0, 2.0, 3.0])

    def test_every_excel_sheet_is_discovered(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "book.xlsx"
            with pd.ExcelWriter(path) as writer:
                pd.DataFrame({"x": [1, 2, 3], "y": [3, 4, 5]}).to_excel(
                    writer, sheet_name="First sample", index=False
                )
                pd.DataFrame({"x": [1, 2, 3], "y": [6, 7, 8]}).to_excel(
                    writer, sheet_name="Second sample", index=False
                )
            datasets = discover_spectra(path)
        self.assertEqual(len(datasets), 2)
        self.assertEqual([item.sheet for item in datasets], ["First sample", "Second sample"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
