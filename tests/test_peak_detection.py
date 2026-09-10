"""Regression tests for scale-independent spectroscopy peak selection."""

import unittest

import numpy as np

from peak_detection import local_extremum_index, noise_adaptive_peak_indices, peak_polarity


class PeakDetectionTests(unittest.TestCase):
    def test_defaults_use_expected_direction(self):
        self.assertEqual(peak_polarity("FTIR"), "down")
        self.assertEqual(peak_polarity("FTIR", converted_transmittance=True), "up")
        for technique in ("XRD", "UVVIS", "RAMAN"):
            self.assertEqual(peak_polarity(technique), "up")

    def test_noise_adaptive_search_ignores_small_noise_and_caps_results(self):
        rng = np.random.default_rng(12)
        x = np.linspace(0, 100, 2000)
        y = rng.normal(0, 0.02, len(x))
        centers = (20, 48, 79)
        for center in centers:
            y += np.exp(-0.5 * ((x - center) / 0.7) ** 2)
        peaks, properties = noise_adaptive_peak_indices(y, maximum=8)
        self.assertEqual(len(peaks), 3)
        self.assertTrue(all(np.min(np.abs(x[index] - np.asarray(centers))) < 0.2 for index in peaks))
        self.assertGreater(properties["used_prominence"], 0)

    def test_valleys_and_click_snapping_respect_polarity(self):
        x = np.linspace(0, 10, 501)
        y = 2.0 - np.exp(-0.5 * ((x - 4.0) / 0.25) ** 2)
        valleys, _ = noise_adaptive_peak_indices(y, direction="down", maximum=5)
        self.assertAlmostEqual(x[valleys[0]], 4.0, places=1)
        up = 3.0 - y
        index = local_extremum_index(x, up, 4.2, direction="up")
        self.assertAlmostEqual(x[index], 4.0, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
