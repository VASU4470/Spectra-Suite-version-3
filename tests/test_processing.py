"""Regression tests for shared spectral processing."""

import unittest

import numpy as np

from processing import baseline_als


class ProcessingTests(unittest.TestCase):
    def test_small_asymmetry_tracks_lower_raman_envelope(self):
        x = np.linspace(0, 1, 300)
        baseline = 1.0 + 0.25 * x
        peak = 2.0 * np.exp(-0.5 * ((x - 0.5) / 0.05) ** 2)
        measured = baseline + peak
        lower = baseline_als(measured, lam=1e6, p=0.05)
        upper = baseline_als(measured, lam=1e6, p=0.95)
        lower_error = float(np.median(np.abs(lower - baseline)))
        upper_error = float(np.median(np.abs(upper - baseline)))
        self.assertLess(lower_error, upper_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
