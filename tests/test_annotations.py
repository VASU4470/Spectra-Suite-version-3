"""Regression tests for annotation history and clearing."""

import unittest

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from annotations import AnnotationManager


class AnnotationHistoryTests(unittest.TestCase):
    def setUp(self):
        figure = Figure()
        self.canvas = FigureCanvasAgg(figure)
        self.ax = figure.add_subplot(111)
        self.manager = AnnotationManager(self.canvas)
        self.manager.load_serialized_data([{
            "kind": "text", "pos": [1, 2], "text": "sample", "c": "black",
            "fs": 12, "fw": "normal", "fsy": "normal", "family": "sans-serif",
            "underline": False, "alpha": 1.0, "box_alpha": 0.8, "box_ec": "gray",
        }], self.ax)

    def test_clear_all_can_be_undone_and_redone(self):
        self.assertTrue(self.manager.clear_all())
        self.assertEqual(len(self.manager.annotations), 0)
        self.assertTrue(self.manager.undo())
        self.assertEqual(len(self.manager.annotations), 1)
        self.assertTrue(self.manager.redo())
        self.assertEqual(len(self.manager.annotations), 0)

    def test_nudge_can_be_undone(self):
        self.manager.select_by_index(0)
        before = self.manager.annotations[0][0].get_position()
        self.manager.nudge_selected("right")
        moved = self.manager.annotations[0][0].get_position()
        self.assertNotEqual(before, moved)
        self.manager.undo()
        self.assertEqual(self.manager.annotations[0][0].get_position(), before)

    def test_line_endpoint_can_be_reshaped(self):
        self.manager.load_serialized_data([{
            "kind": "line", "x": [0.0, 1.0], "y": [0.0, 1.0],
            "c": "red", "lw": 2.0, "ls": "-",
        }], self.ax)
        artist, kind = self.manager.annotations[1]
        self.manager._select_artist(artist, kind)
        self.manager.drag_original = self.manager._geometry(artist, kind)
        self.manager.drag_handle = "end"
        self.manager._apply_geometry_drag(artist, kind, 2.0, 3.0, 0.0, 0.0)
        self.assertEqual(float(artist.get_xdata()[-1]), 2.0)
        self.assertEqual(float(artist.get_ydata()[-1]), 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
