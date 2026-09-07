"""Regression tests for Raman peak measurements."""

import unittest

import numpy as np

from raman_analysis import measure_raman_peaks, nearest_peak_ratio


class RamanAnalysisTests(unittest.TestCase):
    def test_gaussian_peak_position_and_fwhm(self):
        x = np.linspace(900, 1100, 4001)
        sigma = 8.0
        y = 3.0 + 100.0 * np.exp(-0.5 * ((x - 1000.0) / sigma) ** 2)
        peaks = measure_raman_peaks(x, y, prominence=20)
        self.assertEqual(len(peaks), 1)
        self.assertAlmostEqual(peaks[0].shift_cm1, 1000.0, places=6)
        self.assertAlmostEqual(peaks[0].fwhm_cm1, 2.35482 * sigma, places=2)
        self.assertGreater(peaks[0].area, 0)

    def test_nearest_peak_ratio(self):
        x = np.linspace(1200, 1700, 5001)
        y = 10*np.exp(-0.5*((x-1350)/6)**2) + 5*np.exp(-0.5*((x-1580)/7)**2)
        peaks = measure_raman_peaks(x, y, prominence=1)
        first, second, ratio = nearest_peak_ratio(peaks, 1350, 1580)
        self.assertAlmostEqual(first.shift_cm1, 1350, places=3)
        self.assertAlmostEqual(second.shift_cm1, 1580, places=3)
        self.assertAlmostEqual(ratio, 2.0, places=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
