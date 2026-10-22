import time
import unittest
from unittest.mock import Mock, patch

from pynput import mouse
from controlrecord.capture import MouseRecorder
from controlrecord.model import Screen


class CaptureTests(unittest.TestCase):
    def recorder(self):
        recorder = MouseRecorder("capture", Screen(1920, 1080, 96))
        recorder.active = True
        recorder.started = time.perf_counter() - .1
        recorder.position = (10, 20)
        return recorder

    @patch("controlrecord.capture.own_window_at", return_value=False)
    def test_stop_mid_drag_synthesizes_release(self, _):
        recorder = self.recorder()
        recorder._click(10, 20, mouse.Button.left, True)
        recorder._move(50, 60)
        script = recorder.stop()
        self.assertEqual(script.events[-1].kind, "mouse.up")
        self.assertEqual(script.events[-1].t, script.duration)
        self.assertEqual(script.events[-1].data, {"x": 50, "y": 60, "button": "left"})
        script.validate()

    @patch("controlrecord.capture.own_window_at", return_value=True)
    def test_own_controls_not_recorded(self, _):
        recorder = self.recorder()
        recorder._move(10, 20)
        recorder._click(10, 20, mouse.Button.left, True)
        recorder._click(10, 20, mouse.Button.left, False)
        recorder._scroll(10, 20, 0, 1)
        self.assertEqual([e.kind for e in recorder.stop().events], ["mouse.move"])

    def test_drag_release_over_own_window_is_preserved(self):
        recorder = self.recorder()
        with patch("controlrecord.capture.own_window_at", return_value=False):
            recorder._click(10, 20, mouse.Button.left, True)
        with patch("controlrecord.capture.own_window_at", return_value=True):
            recorder._click(30, 40, mouse.Button.left, False)
        script = recorder.stop()
        self.assertEqual(script.events[-1].data["x"], 30)
        self.assertLess(script.events[-1].t, script.duration)

    def test_raw_edge_coordinates_are_clipped_without_stopping(self):
        recorder = self.recorder()
        for x, y in ((2000, 20), (30, -50), (-9000, 5000), (9000, -9000)):
            recorder._move(x, y)
        self.assertTrue(recorder.active)
        self.assertFalse(recorder.error)
        self.assertEqual(recorder.clipped_events, 4)
        script = recorder.stop()
        self.assertEqual([(e.data['x'], e.data['y']) for e in script.events],
                         [(1919, 20), (30, 0), (0, 1079), (1919, 0)])
        script.validate()

    @patch("controlrecord.capture.own_window_at", return_value=False)
    def test_edge_drag_release_keeps_buttons_balanced(self, _):
        recorder = self.recorder()
        recorder._click(10, 20, mouse.Button.left, True)
        recorder._move(-10, 1081)
        recorder._click(-20, 1085, mouse.Button.left, False)
        recorder._scroll(1921, -1, 1, -1)
        recorder._move(100, 100)
        self.assertTrue(recorder.active)
        script = recorder.stop()
        self.assertEqual(script.events[2].kind, "mouse.up")
        self.assertEqual(script.events[2].data, {"x": 0, "y": 1079, "button": "left"})
        self.assertEqual(script.events[-1].data, {"x": 100, "y": 100})
        script.validate()

    def test_edge_diagnostics_logged_when_recording_ends(self):
        recorder = self.recorder()
        recorder._move(20, -50)
        with self.assertLogs(level="INFO") as messages:
            recorder.stop()
        self.assertIn("clipped=1", messages.output[0])
        self.assertIn("first_clipped=(20, -50)", messages.output[0])

    @patch("controlrecord.capture.MAX_EVENTS", 5)
    def test_event_capacity_stops_without_losing_pending_release(self):
        recorder = self.recorder()
        with patch("controlrecord.capture.own_window_at", return_value=False):
            recorder._click(10, 20, mouse.Button.left, True)
            recorder._move(30, 40)
            recorder._move(50, 60)
        self.assertFalse(recorder.active)
        script = recorder.stop()
        self.assertEqual(len(script.events), 3)
        self.assertEqual(script.events[-1].kind, "mouse.up")


if __name__ == "__main__":
    unittest.main()

