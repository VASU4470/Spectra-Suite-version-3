"""Regression tests for annotation history and clearing."""

import unittest

import numpy as np
from matplotlib.backend_bases import MouseEvent
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

    def test_new_text_draws_immediately_with_visible_selection_handle(self):
        figure = Figure()
        canvas = FigureCanvasAgg(figure)
        axis = figure.add_subplot(111)
        manager = AnnotationManager(canvas, text_input_provider=lambda: "visible")
        manager.set_tool("text")
        canvas.draw()
        pixel_x, pixel_y = axis.transData.transform((0.5, 0.5))
        manager.on_press(MouseEvent("button_press_event", canvas, pixel_x, pixel_y, button=1))
        self.assertEqual(len(manager.annotations), 1)
        self.assertTrue(manager.annotations[0][0].get_visible())
        self.assertEqual(len(manager.selection_handles), 1)

    def test_arrow_runs_from_pressed_tail_to_dragged_head(self):
        figure = Figure()
        canvas = FigureCanvasAgg(figure)
        axis = figure.add_subplot(111)
        manager = AnnotationManager(canvas)
        manager.set_tool("arrow")
        canvas.draw()
        tail = axis.transData.transform((0.2, 0.3))
        head = axis.transData.transform((0.8, 0.7))
        manager.on_press(MouseEvent("button_press_event", canvas, *tail, button=1))
        manager.on_drag(MouseEvent("motion_notify_event", canvas, *head, button=1))
        artist, kind = manager.annotations[0]
        self.assertEqual(kind, "arrow")
        self.assertTrue(np.allclose(artist._posA_posB[0], (0.2, 0.3), atol=1e-3))
        self.assertTrue(np.allclose(artist._posA_posB[1], (0.8, 0.7), atol=1e-3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
