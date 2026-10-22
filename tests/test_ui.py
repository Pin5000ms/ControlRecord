from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from controlrecord.model import Event, Script, Screen
from controlrecord.storage import Storage
from controlrecord.ui import MainWindow
from controlrecord.windows import screen_info


app = QApplication.instance() or QApplication([])


class UiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.folder.name))
        script = Script("UI test", screen_info(), 1, [Event(0, "mouse.move", {"x": 10, "y": 10})])
        self.storage.save(script)
        self.window = MainWindow(self.storage, services=False)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        app.processEvents()
        self.folder.cleanup()

    def test_cancel_delay_never_creates_worker_or_video(self):
        self.window.hours.setValue(1)
        self.window.prepare_run()
        self.assertEqual(self.window.state, "countdown")
        self.assertFalse(self.window.record_button.isEnabled())
        self.window.stop()
        self.window.tick()
        self.assertEqual(self.window.state, "idle")
        self.assertIsNone(self.window.worker)
        self.assertFalse(list(self.storage.runs.iterdir()))

    def test_delete_row_cancel_then_confirm_preserves_history(self):
        marker = self.storage.runs / "keep.txt"
        marker.write_text("keep")
        row = self.window.script_list.itemWidget(self.window.script_list.item(0))
        button = row.findChild(QPushButton, "deleteScript")
        with patch("controlrecord.ui.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            button.click()
        self.assertEqual(len(self.storage.list_scripts()[0]), 1)
        with patch("controlrecord.ui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            button.click()
        self.assertFalse(self.storage.list_scripts()[0])
        self.assertEqual(self.window.script_list.count(), 0)
        self.assertFalse(self.window.run_button.isEnabled())
        self.assertTrue(marker.exists())

    def test_unchecked_video_is_forwarded_and_locked_during_run(self):
        self.window.record_video.setChecked(False)
        self.window.prepare_run()
        self.assertFalse(self.window.record_video.isEnabled())
        with patch("controlrecord.ui.RunWorker") as worker:
            self.window.begin_run()
            self.assertFalse(worker.call_args.kwargs["record_video"])
        self.window.worker = None
        self.window.state = "idle"

    def test_cancel_record_preparation_never_starts_listener(self):
        self.window.prepare_recording()
        self.assertEqual(self.window.state, "prepare_record")
        self.assertTrue(self.window.recording_overlay.isVisible())
        self.window.stop()
        self.assertFalse(self.window.recording_overlay.isVisible())
        self.assertIsNone(self.window.recorder)
        self.assertEqual(self.window.state, "idle")

    def test_recording_overlay_only_announces_successful_start(self):
        with patch('controlrecord.ui.MouseRecorder') as recorder, patch('controlrecord.ui.play_start_sound') as sound:
            self.window.prepare_recording()
            self.window.begin_recording()
            self.assertEqual(self.window.state, 'recording')
            self.assertIn('錄製中', self.window.recording_overlay.title.text())
            sound.assert_called_once()
            recorder.return_value.stop.return_value = self.window.selected_script()
            self.window.finish_recording()
            self.assertFalse(self.window.recording_overlay.isVisible())

    def test_failed_recording_hides_overlay_and_does_not_play_sound(self):
        with patch('controlrecord.ui.MouseRecorder') as recorder, patch('controlrecord.ui.play_start_sound') as sound, patch.object(self.window, 'error'), self.assertLogs(level='ERROR'):
            recorder.return_value.start.side_effect = RuntimeError('listener failed')
            self.window.prepare_recording()
            self.window.begin_recording()
            self.assertEqual(self.window.state, 'idle')
            self.assertFalse(self.window.recording_overlay.isVisible())
            sound.assert_not_called()

    def test_f12_sets_cancel_before_gui_event_delivery(self):
        self.window.prepare_run()
        thread = threading.Thread(target=self.window.emergency)
        thread.start()
        thread.join()
        self.assertTrue(self.window.cancel.is_set())
        self.assertEqual(self.window.state, "countdown")
        app.processEvents()
        self.assertEqual(self.window.state, "idle")

    def test_history_keeps_partial_artifact_link(self):
        from controlrecord.model import write_json
        folder = self.storage.runs / "sample"
        write_json(folder / "result.json", {"started_at": "2026-10-21", "script_name": "sample", "status": "failed", "video": "screen.partial.mkv", "completed": 0, "repeats": 1})
        self.window.refresh_history()
        self.assertEqual(self.window.history_table.rowCount(), 1)
        self.assertTrue(self.window.video_button.isEnabled())

    def test_real_display_change_still_stops_and_explains_why(self):
        screen = screen_info()
        recorder = Mock()
        recorder.screen = screen
        recorder.stop.return_value = Script("interrupted", screen, 1, [Event(0, "mouse.move", {"x": 10, "y": 10})])
        self.window.state = "recording"
        self.window.recorder = recorder
        changed = Screen(screen.width + 1, screen.height, screen.dpi)
        with patch("controlrecord.ui.screen_info", return_value=changed), patch("controlrecord.ui.QMessageBox.warning") as warning, self.assertLogs(level="INFO") as messages:
            self.window.tick()
        self.assertEqual(self.window.state, "idle")
        recorder.stop.assert_called_once()
        self.assertIn("錄製已中斷", self.window.status_label.text())
        self.assertIn("停止原因", self.window.message.text())
        self.assertIn("解析度", self.window.message.text())
        warning.assert_called_once()
        self.assertTrue(any("Automatic stop" in message for message in messages.output))
        self.assertEqual(len(self.storage.list_scripts()[0]), 2)


if __name__ == "__main__":
    unittest.main()

