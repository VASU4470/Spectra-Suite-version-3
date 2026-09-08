"""Regression tests for conservative optical-spectrum preprocessing."""

import unittest

import numpy as np

from spectral_preprocessing import subtract_reference, trim_noisy_edges


class SpectralPreprocessingTests(unittest.TestCase):
    def test_clean_spectrum_is_not_trimmed(self):
        x = np.linspace(200, 900, 500)
        y = np.sin(x / 80)
        clean_x, clean_y = trim_noisy_edges(x, y)
        self.assertEqual(len(clean_x), len(x))
        self.assertEqual(len(clean_y), len(y))

    def test_noisy_ends_are_trimmed_conservatively(self):
        rng = np.random.default_rng(7)
        x = np.linspace(200, 900, 600)
        y = np.sin(x / 80)
        y[:35] += rng.normal(0, 2.0, 35)
        y[-30:] += rng.normal(0, 2.0, 30)
        clean_x, _clean_y = trim_noisy_edges(x, y)
        self.assertGreater(clean_x[0], x[0])
        self.assertLess(clean_x[-1], x[-1])
        self.assertGreaterEqual(len(clean_x), int(0.8 * len(x)))

    def test_reference_is_interpolated_before_subtraction(self):
        x = np.array([0.0, 1.0, 2.0])
        result = subtract_reference(x, [3.0, 4.0, 5.0], [0.0, 2.0], [1.0, 3.0])
        self.assertTrue(np.allclose(result, [2.0, 2.0, 2.0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
