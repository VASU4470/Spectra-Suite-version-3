"""Regression tests for UV-Vis scientific calculations."""

from __future__ import annotations

import unittest

import numpy as np

from uvvis_analysis import (
    fit_tauc, fit_urbach, signal_to_absorption, spectral_axis_to_energy,
)


class UVVisAnalysisTests(unittest.TestCase):
    def test_wavelength_energy_conversion(self):
        energy = spectral_axis_to_energy([619.920992], "Wavelength (nm)")
        self.assertAlmostEqual(float(energy[0]), 2.0, places=7)

    def test_absorbance_and_transmittance_to_alpha(self):
        from_absorbance, label = signal_to_absorption([1.0], "Absorbance", 10.0)
        from_transmittance, _ = signal_to_absorption([10.0], "Transmittance (%)", 10.0)
        self.assertEqual(label, "α (cm⁻¹)")
        self.assertAlmostEqual(float(from_absorbance[0]), 2302.585093, places=6)
        self.assertAlmostEqual(float(from_transmittance[0]), 2302.585093, places=6)

    def test_kubelka_munk_transform(self):
        transformed, label = signal_to_absorption([50.0], "Reflectance (%)")
        self.assertEqual(label, "F(R)")
        self.assertAlmostEqual(float(transformed[0]), 0.25)

    def test_direct_allowed_tauc_fit_recovers_known_gap(self):
        energy = np.linspace(2.2, 3.8, 400)
        expected_gap = 2.05
        alpha = np.sqrt(7.5 * (energy - expected_gap)) / energy
        result, _ = fit_tauc(energy, alpha, "Direct allowed", 2.3, 3.6)
        self.assertAlmostEqual(result.band_gap_ev, expected_gap, places=8)
        self.assertGreater(result.fit.r_squared, 0.999999)

    def test_urbach_fit_recovers_known_energy(self):
        energy = np.linspace(1.5, 2.1, 300)
        expected = 0.075
        alpha = 2.0 * np.exp(energy / expected)
        result, _ = fit_urbach(energy, alpha, 1.6, 2.0)
        self.assertAlmostEqual(result.urbach_energy_ev, expected, places=8)
        self.assertGreater(result.fit.r_squared, 0.999999)


if __name__ == "__main__":
    unittest.main(verbosity=2)
