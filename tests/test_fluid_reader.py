"""Tecplot POINT reader tests for the fluid-dynamics workspace."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from fluid_reader import aligned_difference, read_tecplot


TEC = '''TITLE = "Synthetic"
VARIABLES = "X"
"Y"
"U"
ZONE T="Grid"
I=2 J=3 K=1, F=POINT
0 0 1
0 1 2
0 2 3
1 0 4
1 1 5
1 2 6
'''


class FluidReaderTests(unittest.TestCase):
    def test_structured_point_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "velocity.plt"; path.write_text(TEC, encoding="utf-8")
            field = read_tecplot(path)
        self.assertEqual(field.variables, ("X", "Y", "U"))
        self.assertEqual(field.values.shape, (2, 3, 3))
        np.testing.assert_allclose(field.variable("U"), [[1, 2, 3], [4, 5, 6]])

    def test_standard_i_fast_and_shuffled_cartesian_order(self):
        header = 'VARIABLES="X" "Y" "U"\nZONE I=2,J=3,F=POINT\n'
        rows = ['0 0 1', '1 0 4', '0 1 2', '1 1 5', '0 2 3', '1 2 6']
        with TemporaryDirectory() as folder:
            for order in (rows, list(reversed(rows))):
                path = Path(folder)/"standard.dat"
                path.write_text(header + "\n".join(order))
                field = read_tecplot(path)
                np.testing.assert_allclose(field.variable("U"), [[1, 2, 3], [4, 5, 6]])
                np.testing.assert_allclose(field.x[:, 0], [0, 1])
                np.testing.assert_allclose(field.y[0, :], [0, 1, 2])

    def test_volume_rejected_instead_of_flattening(self):
        text = TEC.replace("I=2 J=3 K=1", "I=1 J=3 K=2")
        with TemporaryDirectory() as folder:
            path = Path(folder)/"volume.dat"
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, "2D slice"):
                read_tecplot(path)

    def test_dimension_mismatch_is_reported(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "bad.plt"; path.write_text(TEC.rsplit("\n", 2)[0] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expect"):
                read_tecplot(path)

    def test_shifted_structured_grids_are_aligned_for_difference(self):
        shifted = TEC.replace("0 0 1", "0.5 0 1.5").replace("0 1 2", "0.5 1 2.5").replace(
            "0 2 3", "0.5 2 3.5"
        ).replace("1 0 4", "1.5 0 4.5").replace("1 1 5", "1.5 1 5.5").replace(
            "1 2 6", "1.5 2 6.5"
        )
        with TemporaryDirectory() as folder:
            first_path = Path(folder) / "first.plt"; first_path.write_text(TEC, encoding="utf-8")
            second_path = Path(folder) / "second.plt"; second_path.write_text(shifted, encoding="utf-8")
            first, second = read_tecplot(first_path), read_tecplot(second_path)
            x, _y, difference = aligned_difference(first, second, "U")
        self.assertEqual(x.shape, (1, 3))
        np.testing.assert_allclose(difference, [[-1.0, -1.0, -1.0]])


if __name__ == "__main__": unittest.main(verbosity=2)
