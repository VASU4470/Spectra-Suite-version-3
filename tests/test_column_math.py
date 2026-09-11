"""Regression tests for safe formulas and UV-Vis signal conversions."""

from __future__ import annotations

import unittest

import numpy as np

from column_math import (
    FormulaError,
    absorbance_to_percent_transmittance,
    evaluate_column_formula,
    kubelka_munk,
    percent_transmittance_to_absorbance,
)


class ColumnMathTests(unittest.TestCase):
    def test_absorbance_percent_transmittance_round_trip(self):
        absorbance = np.array([0.0, 0.25, 1.0, 2.0])
        transmittance = absorbance_to_percent_transmittance(absorbance)
        np.testing.assert_allclose(
            percent_transmittance_to_absorbance(transmittance), absorbance,
            rtol=1e-12, atol=1e-12,
        )
        np.testing.assert_allclose(transmittance, [100.0, 56.2341325, 10.0, 1.0])

    def test_kubelka_munk_accepts_fraction_or_percent_reflectance(self):
        reflectance = np.array([0.2, 0.5, 1.0])
        expected = (1.0 - reflectance) ** 2 / (2.0 * reflectance)
        np.testing.assert_allclose(kubelka_munk(reflectance), expected)
        np.testing.assert_allclose(kubelka_munk(reflectance * 100, percent=True), expected)
        self.assertTrue(np.isnan(kubelka_munk([0.0, 1.1])).all())

    def test_arithmetic_and_approved_functions(self):
        first = np.arange(1.0, 8.0)
        second = np.arange(10.0, 17.0)
        np.testing.assert_allclose(
            evaluate_column_formula("C1 + C2 * 2", [first, second]),
            first + second * 2,
        )
        normalized = evaluate_column_formula("normalize(C2)", [first, second])
        self.assertAlmostEqual(float(np.nanmin(normalized)), 0.0)
        self.assertAlmostEqual(float(np.nanmax(normalized)), 1.0)

    def test_baseline_and_smoothing_return_one_value_per_row(self):
        x = np.linspace(0, 1, 101)
        y = 2 + 0.5 * x + np.exp(-0.5 * ((x - 0.5) / 0.05) ** 2)
        baseline_corrected = evaluate_column_formula("baseline(C2)", [x, y])
        smoothed = evaluate_column_formula("smooth(C2, 9)", [x, y])
        self.assertEqual(len(baseline_corrected), len(y))
        self.assertEqual(len(smoothed), len(y))
        self.assertGreater(float(np.nanmax(baseline_corrected)), 0.5)

    def test_formula_language_rejects_python_access(self):
        values = np.arange(5.0)
        for expression in (
            "__import__('os').system('echo unsafe')",
            "C1.__class__",
            "open('file')",
            "[value for value in C1]",
        ):
            with self.subTest(expression=expression), self.assertRaises(FormulaError):
                evaluate_column_formula(expression, [values])


if __name__ == "__main__":
    unittest.main()
