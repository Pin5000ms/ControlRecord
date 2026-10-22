"""FFmpeg screen recording with readiness, health checks and graceful closing."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def ffmpeg_path() -> str:
    # A packaged copy takes precedence; never fetch binaries at run time.
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidate = root / "bin" / "ffmpeg.exe"
    if candidate.is_file():
        return str(candidate)
    import imageio_ffmpeg
    path = imageio_ffmpeg.get_ffmpeg_exe()
    if not Path(path).is_file():
        raise RuntimeError("找不到 FFmpeg，請重新解壓完整的程式資料夾。")
    return path


class VideoRecorder:
    def __init__(self, target: Path, fps=20, executable: str | None = None):
        self.target = target
        self.partial = target.with_suffix(".partial.mkv")
        self.log_path = target.with_suffix(".ffmpeg.log")
        self.fps = fps
        self.executable = executable or ffmpeg_path()
        self.process = None
        self.reader = None
        self.log_file = None
        self.ready = threading.Event()
        self.last_frame = 0.0
        self.frames = 0

    def start(self, stop: threading.Event):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if self.target.exists() or self.partial.exists():
            raise RuntimeError("影片檔名已存在，請重新執行。")
        if shutil.disk_usage(self.target.parent).free < 512 * 1024 * 1024:
            raise RuntimeError("磁碟剩餘空間不足 512 MB，無法開始錄影。")
        self.log_file = self.log_path.open("wb")
        command = [
            self.executable, "-hide_banner", "-loglevel", "warning", "-y",
            "-stats_period", "0.25", "-progress", "pipe:1",
            "-f", "gdigrab", "-framerate", str(self.fps), "-draw_mouse", "1",
            "-i", "desktop", "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-g", str(self.fps * 2), "-threads", "2",
            "-flush_packets", "1", "-f", "matroska", str(self.partial),
        ]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log_file, creationflags=subprocess.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self._read_progress, daemon=True)
        self.reader.start()
        deadline = time.perf_counter() + 15
        while not self.ready.wait(0.05):
            if stop.is_set():
                return False
            if self.process.poll() is not None:
                raise RuntimeError("錄影啟動失敗，請查看執行紀錄中的 FFmpeg 日誌。")
            if time.perf_counter() >= deadline:
                raise RuntimeError("錄影未在 15 秒內就緒，尚未開始重播。")
        return not stop.is_set()

    def _read_progress(self):
        try:
            for raw in self.process.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("frame="):
                    value = int(line.partition("=")[2].strip())
                    if value > self.frames:
                        self.frames = value
                        self.last_frame = time.perf_counter()
                        self.ready.set()
        except (ValueError, OSError):
            return

    def check(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("螢幕錄影已中斷，操作已停止。")
        if self.ready.is_set() and time.perf_counter() - self.last_frame > 10:
            raise RuntimeError("錄影超過 10 秒沒有新影格，操作已停止。")

    def finish(self) -> tuple[str, str]:
        """Return (playable artifact, warning). Partial capture survives failures."""
        warning = ""
        if self.process:
            try:
                if self.process.poll() is None:
                    try:
                        self.process.stdin.write(b"q\n")
                        self.process.stdin.flush()
                    except (OSError, BrokenPipeError):
                        pass
                    try:
                        self.process.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                            self.process.wait(timeout=3)
                        warning = "錄影程序未正常回應，已保留可復原的中間檔。"
                elif self.process.returncode != 0:
                    warning = "錄影程序異常結束，已嘗試保存已錄製部分。"
            finally:
                if self.reader:
                    self.reader.join(timeout=2)
                for stream in (self.process.stdin, self.process.stdout):
                    if stream:
                        stream.close()
        if self.log_file:
            self.log_file.close()
        if not self.partial.exists() or self.partial.stat().st_size < 1024:
            return "", warning or "未產生有效影片；請查看 FFmpeg 日誌。"
        temporary = self.target.with_suffix(".tmp.mp4")
        try:
            with self.log_path.open("ab") as log:
                result = subprocess.run(
                    [self.executable, "-hide_banner", "-loglevel", "error", "-y",
                     "-i", str(self.partial), "-map", "0:v:0", "-c", "copy",
                     "-movflags", "+faststart", str(temporary)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=120,
                )
            if result.returncode or not temporary.exists() or temporary.stat().st_size < 1024:
                raise RuntimeError("影片封裝失敗")
            temporary.replace(self.target)
            self.partial.unlink()
            return str(self.target), warning
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return str(self.partial), (warning + " MP4 封裝未完成，原始 MKV 已保留，可用 VLC 播放。").strip()

