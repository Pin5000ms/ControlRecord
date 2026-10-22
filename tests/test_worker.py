import logging
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from controlrecord.model import Event, Screen, Script
from controlrecord.worker import RunWorker


class FakeVideo:
    ready = True
    fail_checks = False
    frames = 2
    fps = 20

    def __init__(self, target):
        self.target = target
        self.partial = target.with_suffix(".partial.mkv")

    def start(self, stop):
        return self.ready

    def check(self):
        if self.fail_checks:
            raise RuntimeError("encoder failed")

    def finish(self):
        self.target.write_bytes(b"fake video")
        return str(self.target), ""


class FakeDriver:
    events = []

    def __init__(self, screen):
        pass

    def dispatch(self, event):
        self.events.append(event.kind)

    def release_all(self):
        pass


class WorkerTests(unittest.TestCase):
    def run_worker(self, stop=None, record_video=True):
        with tempfile.TemporaryDirectory() as temporary:
            screen = Screen(1920, 1080, 96)
            script = Script("worker", screen, .002, [Event(0, "mouse.move", {"x": 1, "y": 1})])
            worker = RunWorker(script, 2, Path(temporary) / "run", stop or threading.Event(), lambda: None, record_video=record_video)
            results = []
            worker.result.connect(results.append)
            with patch("controlrecord.worker.VideoRecorder", FakeVideo), patch("controlrecord.worker.WindowsInput", FakeDriver), patch("controlrecord.worker.screen_info", return_value=screen), patch("controlrecord.worker.desktop_available", return_value=True), patch("controlrecord.worker.mouse_is_held", return_value=False):
                worker.run()
            import json
            saved = json.loads((Path(temporary) / "run/result.json").read_text(encoding="utf-8"))
            self.assertTrue((Path(temporary) / "run/script.json").exists())
            self.assertEqual(len(results), 1)
            if not record_video:
                self.assertIsNone(worker.video)
                self.assertFalse((Path(temporary) / "run/screen.mp4").exists())
            return saved

    def test_without_video_replays_and_saves_history_even_if_encoder_unavailable(self):
        FakeVideo.ready = False
        FakeVideo.fail_checks = True
        saved = self.run_worker(record_video=False)
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["completed"], 2)
        self.assertEqual(len(FakeDriver.events), 2)
        self.assertFalse(saved["video"])
        self.assertFalse(saved["record_video"])
        self.assertIsNone(saved["video_offset_seconds"])

    def setUp(self):
        FakeVideo.ready = True
        FakeVideo.fail_checks = False
        FakeDriver.events = []

    def test_complete_run_stores_relative_video_and_counts(self):
        saved = self.run_worker()
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["completed"], 2)
        self.assertEqual(saved["video"], "screen.mp4")
        self.assertEqual(len(FakeDriver.events), 2)

    def test_recording_start_cancelled_never_replays(self):
        FakeVideo.ready = False
        saved = self.run_worker()
        self.assertEqual(saved["status"], "stopped")
        self.assertFalse(FakeDriver.events)
        self.assertEqual(saved["video"], "screen.mp4")

    def test_encoder_failure_never_dispatches_input(self):
        FakeVideo.fail_checks = True
        with self.assertLogs(level=logging.ERROR):
            saved = self.run_worker()
        self.assertEqual(saved["status"], "failed")
        self.assertIn("encoder failed", saved["error"])
        self.assertFalse(FakeDriver.events)
        self.assertEqual(saved["video"], "screen.mp4")

    def test_pre_cancelled_run_still_has_history(self):
        stop = threading.Event()
        stop.set()
        saved = self.run_worker(stop)
        self.assertEqual(saved["status"], "stopped")
        self.assertFalse(saved["video"])
        self.assertFalse(FakeDriver.events)

    def test_existing_run_folder_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            marker = folder / "result.json"
            marker.write_text('{"previous": true}', encoding="utf-8")
            script = Script("worker", Screen(1920, 1080, 96), 1, [Event(0, "mouse.move", {"x": 1, "y": 1})])
            worker = RunWorker(script, 1, folder, threading.Event(), lambda: None)
            with self.assertLogs(level=logging.ERROR):
                worker.run()
            self.assertEqual(marker.read_text(encoding="utf-8"), '{"previous": true}')


if __name__ == "__main__":
    unittest.main()

