"""Input adapters produce timestamped events; callbacks do no disk I/O."""
from __future__ import annotations

import threading
import time
import logging
from typing import Protocol

from pynput import keyboard, mouse

from .model import Event, MAX_EVENTS, MAX_SECONDS, Screen, Script
from .windows import cursor_position, mouse_is_held, own_window_at


class CaptureAdapter(Protocol):
    """Keyboard recording can implement this same lifecycle."""
    def start(self) -> None: ...
    def stop(self) -> Script: ...


def start_listener(listener):
    listener.start()
    ready = threading.Event()

    def await_ready():
        listener.wait()
        ready.set()

    threading.Thread(target=await_ready, daemon=True).start()
    if not ready.wait(3) or not listener.is_alive():
        listener.stop()
        raise RuntimeError("輸入監聽啟動逾時，請重新啟動軟體。")


class MouseRecorder:
    def __init__(self, name: str, screen: Screen):
        self.name = name
        self.screen = screen
        self.events: list[Event] = []
        self.lock = threading.Lock()
        self.listener = None
        self.active = False
        self.started = 0.0
        self.error = ""
        self.pressed: set[str] = set()
        self.position = (0, 0)
        self.clipped_events = 0
        self.first_clipped_position = None

    def start(self):
        if mouse_is_held():
            raise RuntimeError("請先放開所有滑鼠按鍵，再開始錄製。")
        self.position = cursor_position()
        self.listener = mouse.Listener(on_move=self._move, on_click=self._click, on_scroll=self._scroll)
        start_listener(self.listener)
        with self.lock:
            self.started = time.perf_counter()
            self.events = [Event(0.0, "mouse.move", {"x": self.position[0], "y": self.position[1]})]
            self.active = True
        logging.info("Recording started: name=%r screen=%s", self.name, self.screen)

    def _append(self, kind: str, data: dict):
        # Caller holds the lock. Leave room for synthetic releases at the end.
        t = time.perf_counter() - self.started
        if len(self.events) >= MAX_EVENTS - 3 or t > MAX_SECONDS - 1:
            self.error = "已達錄製容量上限，錄製已停止；請將流程拆成較短腳本。"
            self.active = False
            return False
        if not 0 <= data["x"] < self.screen.width or not 0 <= data["y"] < self.screen.height:
            # A low-level hook can report a movement before Windows clips it
            # to the screen. This is not evidence of a display change. The UI
            # independently checks the actual display configuration each tick.
            self.clipped_events += 1
            if self.first_clipped_position is None:
                self.first_clipped_position = (data["x"], data["y"])
            data = {**data, "x": max(0, min(self.screen.width - 1, data["x"])),
                    "y": max(0, min(self.screen.height - 1, data["y"]))}
        self.events.append(Event(t, kind, data))
        self.position = (data["x"], data["y"])
        return True

    def _move(self, x, y, *unused):
        with self.lock:
            if self.active:
                self._append("mouse.move", {"x": x, "y": y})

    def _click(self, x, y, button, pressed, *unused):
        name = button.name
        if name not in ("left", "right", "middle"):
            return
        with self.lock:
            if not self.active:
                return
            # Do not record clicks on this tool, including its Stop button.
            if pressed:
                if own_window_at(x, y) or name in self.pressed:
                    return
                if self._append("mouse.down", {"x": x, "y": y, "button": name}):
                    self.pressed.add(name)
            elif name in self.pressed:
                if self._append("mouse.up", {"x": x, "y": y, "button": name}):
                    self.pressed.discard(name)

    def _scroll(self, x, y, dx, dy, *unused):
        with self.lock:
            if self.active and not own_window_at(x, y):
                self._append("mouse.scroll", {"x": x, "y": y, "dx": int(dx), "dy": int(dy)})

    def stop(self) -> Script:
        with self.lock:
            self.active = False
            duration = max(0.001, min(MAX_SECONDS, time.perf_counter() - self.started))
            for button in sorted(self.pressed):
                self.events.append(Event(duration, "mouse.up", {"x": self.position[0], "y": self.position[1], "button": button}))
            self.pressed.clear()
            events = list(self.events)
        if self.listener:
            self.listener.stop()
            self.listener.join(timeout=2)
        script = Script(self.name, self.screen, duration, events)
        script.validate()
        # Log on the caller/GUI thread, never from the low-level input callback.
        logging.info("Recording captured: name=%r duration=%.3f events=%d clipped=%d first_clipped=%s error=%r",
                     self.name, duration, len(events), self.clipped_events, self.first_clipped_position, self.error)
        return script

    def count(self) -> int:
        with self.lock:
            return len(self.events)

    def check(self):
        if self.error:
            raise RuntimeError(self.error)
        if self.listener and not self.listener.is_alive():
            raise RuntimeError("滑鼠監聽已中斷，請重新錄製。")


class Hotkeys:
    """Only F8/F12 are acted upon; other keyboard input is never retained."""
    def __init__(self, finish_recording, emergency_stop):
        self.finish_recording = finish_recording
        self.emergency_stop = emergency_stop
        self.down = set()
        self.listener = keyboard.Listener(win32_event_filter=self._filter)

    def _filter(self, message, data):
        key = {0x77: keyboard.Key.f8, 0x7B: keyboard.Key.f12}.get(data.vkCode)
        if key is None:
            return False  # Ignore ordinary keys, without suppressing them in Windows.
        if message in (0x100, 0x104):
            self._press(key)
        elif message in (0x101, 0x105):
            self._release(key)
        # These two keys belong to this tool, not to the emulator underneath it.
        self.listener.suppress_event()

    def _press(self, key, *unused):
        if key not in (keyboard.Key.f8, keyboard.Key.f12) or key in self.down:
            return
        self.down.add(key)
        if key == keyboard.Key.f8:
            self.finish_recording()
        else:
            # This callback sets a threading.Event before notifying the GUI.
            self.emergency_stop()

    def _release(self, key, *unused):
        self.down.discard(key)

    def start(self):
        start_listener(self.listener)

    def check(self):
        if not self.listener.is_alive():
            raise RuntimeError("全域快捷鍵已中斷，請重新啟動軟體。")

    def close(self):
        self.listener.stop()
        self.listener.join(timeout=2)

