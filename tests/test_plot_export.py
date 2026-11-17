"""Regression tests for figure formats, including the former PDF failure path."""

from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageChops
from pypdf import PdfReader
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

    def test_publication_formats_keep_requested_size_and_label_clearance(self):
        axis = self.figure.axes[0]
        axis.set(xlabel="Wavelength (nm)", ylabel="Intensity (counts)")
        axis.legend(["Reference spectrum"], loc="upper left")
        with TemporaryDirectory() as folder:
            paths = {
                extension: save_figure(
                    self.figure, Path(folder) / f"reference.{extension}",
                    size_inches=(3.5, 2.5), dpi=240, tight=False,
                )
                for extension in ("pdf", "svg", "png", "tiff")
            }
            pdf = PdfReader(paths["pdf"]).pages[0]
            self.assertAlmostEqual(float(pdf.mediabox.width), 252)
            self.assertAlmostEqual(float(pdf.mediabox.height), 180)
            for text in ("Export test", "Wavelength (nm)", "Intensity (counts)", "Reference spectrum"):
                self.assertIn(text, pdf.extract_text())
                self.assertIn(text, paths["svg"].read_text(encoding="utf-8"))
            svg = ElementTree.parse(paths["svg"]).getroot()
            self.assertEqual(tuple(map(float, svg.attrib["viewBox"].split())), (0, 0, 252, 180))
            for extension in ("png", "tiff"):
                with self.subTest(extension=extension), Image.open(paths[extension]) as image:
                    self.assertEqual(image.size, (840, 600))
                    self.assertAlmostEqual(image.info["dpi"][0], 240, delta=.1)
                    rgb = image.convert("RGB")
                    ink = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).getbbox()
                    self.assertIsNotNone(ink)
                    self.assertGreater(min(ink[0], ink[1], rgb.width - ink[2], rgb.height - ink[3]), 0)


if __name__ == "__main__": unittest.main(verbosity=2)
