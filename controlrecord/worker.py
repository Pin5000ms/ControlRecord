from __future__ import annotations

import logging
from pathlib import Path
import threading
import time

from PySide6.QtCore import QThread, Signal

from .model import Script, now_iso, write_json
from .playback import Playback
from .video import VideoRecorder
from .windows import WindowsInput, desktop_available, mouse_is_held, screen_info


class RunWorker(QThread):
    stage = Signal(str)
    progress = Signal(int, int)
    result = Signal(dict)

    def __init__(self, script: Script, repeats: int, folder: Path,
                 stop: threading.Event, hotkey_check, parent=None, record_video=True):
        super().__init__(parent)
        self.script = script
        self.repeats = repeats
        self.folder = folder
        self.stop_event = stop
        self.hotkey_check = hotkey_check
        self.video = None
        self.record_video = record_video
        self.last_health = 0.0

    def health(self):
        if self.video:
            self.video.check()
        if time.perf_counter() - self.last_health >= 0.5:
            self.hotkey_check()
            if not desktop_available():
                raise RuntimeError("桌面已鎖定或切換，操作已停止。")
            if screen_info() != self.script.screen:
                raise RuntimeError("螢幕解析度、縮放或螢幕數量改變，操作已停止。")
            self.last_health = time.perf_counter()

    def run(self):
        record = {
            "script_id": self.script.id, "script_name": self.script.name,
            "started_at": now_iso(), "ended_at": "", "repeats": self.repeats,
            "completed": 0, "status": "running", "error": "", "video": "",
            "warning": "", "playback_started_at": "", "video_offset_seconds": None,
            "record_video": self.record_video,
        }
        completed = 0
        folder_created = False

        def progress(done, total):
            nonlocal completed
            completed = done
            record["completed"] = done
            self.progress.emit(done, total)

        try:
            self.folder.mkdir(parents=True, exist_ok=False)
            folder_created = True
            write_json(self.folder / "script.json", self.script.to_dict())
            write_json(self.folder / "result.json", record)
            if self.stop_event.is_set():
                record["status"] = "stopped"
                return
            if mouse_is_held():
                raise RuntimeError("請放開所有滑鼠按鍵後再執行。")
            if self.record_video:
                self.stage.emit("正在啟動螢幕錄影…")
                self.video = VideoRecorder(self.folder / "screen.mp4")
                if not self.video.start(self.stop_event):
                    record["status"] = "stopped"
                    return
            self.health()
            self.stage.emit("正在重播 · F12 可隨時停止")
            record["playback_started_at"] = now_iso()
            if self.video:
                record["video_offset_seconds"] = round(self.video.frames / self.video.fps, 3)
            playback = Playback(WindowsInput(self.script.screen), self.stop_event, self.health)
            completed = playback.run(self.script, self.repeats, progress)
            record["status"] = "stopped" if self.stop_event.is_set() else "completed"
        except Exception as exc:
            logging.exception("Run failed")
            record["status"] = "failed"
            record["error"] = str(exc)
        finally:
            record["completed"] = completed
            self.stage.emit("正在保存影片，請稍候…" if self.video else "正在保存執行紀錄…")
            if self.video:
                try:
                    record["video"], record["warning"] = self.video.finish()
                    if not record["video"] and record["status"] == "completed":
                        record["status"] = "failed"
                        record["error"] = "操作完成，但錄影未能保存。"
                except Exception as exc:
                    logging.exception("Video finalization failed")
                    record["warning"] = f"保存影片失敗：{exc}"
                    record["status"] = "failed"
                    if self.video.partial.exists():
                        record["video"] = str(self.video.partial)
            record["ended_at"] = now_iso()
            # Store a relative path so the portable folder can be moved.
            if record["video"]:
                record["video"] = Path(record["video"]).name
            try:
                if folder_created:
                    write_json(self.folder / "result.json", record)
            except OSError as exc:
                record["warning"] += f" 無法寫入執行紀錄：{exc}"
                record["status"] = "failed"
            record["folder"] = str(self.folder)
            self.result.emit(record)

