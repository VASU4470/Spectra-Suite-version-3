"""Regression tests for figure formats, including the former PDF failure path."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from matplotlib.figure import Figure

from plot_export import normalize_figure_path, save_figure


class PlotExportTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure(figsize=(3, 2))
        axis = self.figure.add_subplot(111)
        axis.plot([0, 1, 2], [1, 3, 2])
        axis.set_title("Export test")

    def test_selected_filter_adds_extension(self):
        self.assertEqual(
            normalize_figure_path("figure", "PDF (*.pdf)"), Path("figure.pdf")
        )

    def test_pdf_export_has_valid_signature(self):
        with TemporaryDirectory() as folder:
            path = save_figure(self.figure, Path(folder) / "ftir_xrd.pdf")
            self.assertGreater(path.stat().st_size, 1000)
            self.assertEqual(path.read_bytes()[:5], b"%PDF-")

    def test_common_image_and_vector_formats_export(self):
        with TemporaryDirectory() as folder:
            for suffix in (".png", ".svg"):
                with self.subTest(suffix=suffix):
                    path = save_figure(self.figure, Path(folder) / f"figure{suffix}")
                    self.assertGreater(path.stat().st_size, 100)


if __name__ == "__main__": unittest.main(verbosity=2)
