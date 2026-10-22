"""Exercise live Windows APIs only inside our own disposable test window."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord.windows import (
    INPUT, KEYBDINPUT, PowerGuard, WindowsInput, cursor_position,
    enable_dpi_awareness, screen_info, user32,
)
enable_dpi_awareness()
from controlrecord.capture import Hotkeys, MouseRecorder
from controlrecord.model import Event, Script, save_script, write_json
from controlrecord.playback import Playback
from controlrecord.video import VideoRecorder, ffmpeg_path


def main():
    folder = ROOT / "artifacts" / ("integration_" + time.strftime("%Y%m%d_%H%M%S"))
    folder.mkdir(parents=True)
    original = cursor_position()
    process = subprocess.Popen([sys.executable, str(ROOT / "tools/test_target.py"), str(folder)],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    driver = WindowsInput(screen_info())
    recorder = hotkeys = video = None
    guard = PowerGuard()
    report = {"screen": vars(screen_info()), "checks": []}
    try:
        deadline = time.perf_counter() + 10
        while not (folder / "target-ready.json").exists():
            if time.perf_counter() > deadline or process.poll() is not None:
                raise RuntimeError("Test target did not start")
            time.sleep(.05)
        target = json.loads((folder / "target-ready.json").read_text())
        x, y = target["x"], target["y"]

        def verify_target(px=x, py=y):
            handle = user32.WindowFromPoint(W.POINT(px, py))
            pid = W.DWORD()
            user32.GetWindowThreadProcessId(handle, C.byref(pid))
            if pid.value != target["pid"]:
                raise RuntimeError("Test target is obscured; aborting input test")

        verify_target()
        user32.SetForegroundWindow.argtypes = [W.HWND]
        user32.SetForegroundWindow(target["hwnd"])
        guard.set()
        report["checks"].append("power request acquired/released")
        driver.dispatch(Event(0, "mouse.move", {"x": x, "y": y}))
        for _ in range(20):
            time.sleep(.02)
            if cursor_position() == (x, y):
                break
        assert cursor_position() == (x, y), (cursor_position(), (x, y))
        recorder = MouseRecorder("Windows 實測腳本", screen_info())
        recorder.start()
        steps = [
            (.05, "mouse.down", {"button": "left"}),
            (.10, "mouse.up", {"button": "left"}),
            (.18, "mouse.down", {"button": "left"}),
            (.23, "mouse.up", {"button": "left"}),
            (.50, "mouse.down", {"button": "left"}),
            (.65, "mouse.move", {"x": x + 80}),
            (.80, "mouse.up", {"x": x + 80, "button": "left"}),
            (.95, "mouse.down", {"button": "right"}),
            (1.00, "mouse.up", {"button": "right"}),
            (1.15, "mouse.down", {"button": "middle"}),
            (1.20, "mouse.up", {"button": "middle"}),
            (1.35, "mouse.scroll", {"dx": 0, "dy": -2}),
            (1.50, "mouse.scroll", {"dx": 1, "dy": 0}),
        ]
        start = time.perf_counter()
        for offset, kind, extra in steps:
            time.sleep(max(0, start + offset - time.perf_counter()))
            data = {"x": x, "y": y, **extra}
            verify_target(data["x"], data["y"])
            driver.dispatch(Event(offset, kind, data))
        time.sleep(.25)
        script = recorder.stop()
        recorder = None
        save_script(folder / "captured.json", script)
        kinds = {e.kind for e in script.events}
        assert kinds == {"mouse.move", "mouse.down", "mouse.up", "mouse.scroll"}, kinds
        assert {e.data["button"] for e in script.events if e.kind == "mouse.down"} == {"left", "right", "middle"}
        assert script.duration - script.events[-1].t >= .2
        report["checks"].append("native capture: movement, three buttons, double-click, drag, vertical/horizontal scroll, tail delay")

        video = VideoRecorder(folder / "normal.mp4")
        assert video.start(threading.Event())
        count = Playback(driver, threading.Event(), lambda: (verify_target(), video.check())).run(script, 2)
        assert count == 2
        path, warning = video.finish()
        video = None
        assert path.endswith(".mp4"), (path, warning)
        report["checks"].append("two native replay loops with live cursor video")

        stop = threading.Event()
        seen_f8 = threading.Event()
        hotkeys = Hotkeys(seen_f8.set, stop.set)
        hotkeys.start()

        def key(vk):
            verify_target()
            for flags in (0, 2):
                event = INPUT(type=1, ki=KEYBDINPUT(vk, 0, flags, 0, 0))
                assert user32.SendInput(1, C.byref(event), C.sizeof(INPUT)) == 1

        key(0x77)  # F8
        assert seen_f8.wait(2)
        report["checks"].append("global F8 hook")
        video = VideoRecorder(folder / "stopped.mp4")
        assert video.start(stop)
        drag = Script("取消拖曳測試", screen_info(), 5, [
            Event(0, "mouse.down", {"x": x, "y": y, "button": "left"}),
            Event(4, "mouse.up", {"x": x, "y": y, "button": "left"}),
        ])
        trigger = threading.Timer(.4, lambda: key(0x7B))  # F12
        trigger.start()
        begin = time.perf_counter()
        count = Playback(driver, stop, lambda: (verify_target(), video.check())).run(drag, 1)
        trigger.join()
        assert count == 0 and not driver.pressed and time.perf_counter() - begin < 1.5
        assert not user32.GetAsyncKeyState(1) & 0x8000
        report["checks"].append("F12 cancels active drag and releases the physical button state")
        path, warning = video.finish()
        video = None
        assert path.endswith(".mp4"), (path, warning)
        report["checks"].append("interrupted playback still produces MP4")
        for name in ("normal.mp4", "stopped.mp4"):
            decoded = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(folder / name),
                                      "-f", "null", "-"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            assert decoded.returncode == 0 and not decoded.stderr, decoded.stderr
        subprocess.run([ffmpeg_path(), "-v", "error", "-y", "-ss", "1", "-i", str(folder / "normal.mp4"),
                        "-frames:v", "1", str(folder / "video-frame.png")], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        report["checks"].append("both MP4 files decode completely without errors")
        events = json.loads((folder / "target-events.json").read_text())
        assert all(any(e["kind"] == kind for e in events) for kind in ("down", "up", "double", "drag", "wheel"))
        report["target_events"] = len(events)
        report["result"] = "PASS"
        write_json(folder / "report.json", report)
        print(json.dumps({"folder": str(folder), **report}, ensure_ascii=False, indent=2))
    finally:
        if recorder:
            recorder.stop()
        if hotkeys:
            hotkeys.close()
        if video:
            video.finish()
        driver.release_all()
        driver.dispatch(Event(0, "mouse.move", {"x": original[0], "y": original[1]}))
        guard.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()

