"""Small Windows adapter, kept separate from the portable script engine."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os

from .model import Event, Screen

user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = C.c_size_t


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", W.DWORD), ("value", INPUTUNION)]


user32.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
user32.SendInput.restype = W.UINT
user32.WindowFromPoint.argtypes = [W.POINT]
user32.WindowFromPoint.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetAsyncKeyState.argtypes = [C.c_int]
user32.GetAsyncKeyState.restype = W.SHORT
user32.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
user32.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
user32.OpenInputDesktop.restype = W.HANDLE
user32.GetUserObjectInformationW.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
user32.CloseDesktop.argtypes = [W.HANDLE]
kernel32.SetThreadExecutionState.argtypes = [W.DWORD]
kernel32.SetThreadExecutionState.restype = W.DWORD
kernel32.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
kernel32.CreateMutexW.restype = W.HANDLE
kernel32.CloseHandle.argtypes = [W.HANDLE]


def enable_dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
        user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except AttributeError:
        C.windll.shcore.SetProcessDpiAwareness(2)


def screen_info() -> Screen:
    return Screen(user32.GetSystemMetrics(0), user32.GetSystemMetrics(1),
                  user32.GetDpiForSystem(), user32.GetSystemMetrics(80))


def cursor_position() -> tuple[int, int]:
    point = W.POINT()
    if not user32.GetCursorPos(C.byref(point)):
        raise OSError("無法取得游標位置")
    return point.x, point.y


def mouse_is_held() -> bool:
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (1, 2, 4))


def own_window_at(x: int, y: int) -> bool:
    window = user32.WindowFromPoint(W.POINT(x, y))
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(window, C.byref(pid))
    return pid.value == os.getpid()


def desktop_available() -> bool:
    handle = user32.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
    if not handle:
        return False
    try:
        name = C.create_unicode_buffer(256)
        needed = W.DWORD()
        return bool(user32.GetUserObjectInformationW(handle, 2, name, C.sizeof(name), C.byref(needed))) and name.value.lower() == "default"
    finally:
        user32.CloseDesktop(handle)


class SingleInstance:
    def __init__(self):
        self.handle = kernel32.CreateMutexW(None, False, "Local\\ControlRecord_v1")
        if not self.handle:
            raise OSError("無法建立單一執行個體鎖定")
        self.already_running = C.get_last_error() == 183

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None


class PowerGuard:
    """All calls must occur on the same (GUI) thread."""
    def set(self, display=True):
        flags = 0x80000000 | 0x00000001 | (0x00000002 if display else 0)
        if not kernel32.SetThreadExecutionState(flags):
            raise OSError("Windows 無法啟用防休眠")

    def close(self):
        kernel32.SetThreadExecutionState(0x80000000)


class WindowsInput:
    BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

    def __init__(self, screen: Screen):
        self.screen = screen
        self.pressed: set[str] = set()
        self.handlers = {
            "mouse.move": self._move_event,
            "mouse.down": self._down,
            "mouse.up": self._up,
            "mouse.scroll": self._scroll,
        }

    def register_handler(self, kind, handler):
        """Extension point for keyboard/UI actions; register validation as well."""
        if kind in self.handlers:
            raise ValueError(f"重複的執行處理器：{kind}")
        self.handlers[kind] = handler

    def _send(self, flags, x=0, y=0, data=0):
        event = INPUT(type=0, mi=MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, 0))
        if user32.SendInput(1, C.byref(event), C.sizeof(INPUT)) != 1:
            raise OSError("滑鼠輸入被 Windows 拒絕；請確認目標程式與此工具的執行權限一致。")

    def _position(self, data):
        # Map the centre of the physical pixel into the 16-bit absolute range.
        x = min(65535, (data["x"] * 65536 + 32768) // self.screen.width)
        y = min(65535, (data["y"] * 65536 + 32768) // self.screen.height)
        self._send(0x8000 | 0x0001 | 0x2000, x, y)  # ABSOLUTE | MOVE | NOCOALESCE

    def _move_event(self, event):
        self._position(event.data)

    def _down(self, event):
        self._position(event.data)
        button = event.data["button"]
        self._send(self.BUTTONS[button][0])
        self.pressed.add(button)

    def _up(self, event):
        self._position(event.data)
        button = event.data["button"]
        self._send(self.BUTTONS[button][1])
        self.pressed.discard(button)

    def _scroll(self, event):
        self._position(event.data)
        if event.data["dy"]:
            self._send(0x0800, data=event.data["dy"] * 120)
        if event.data["dx"]:
            self._send(0x1000, data=event.data["dx"] * 120)

    def dispatch(self, event: Event):
        try:
            handler = self.handlers[event.kind]
        except KeyError:
            raise ValueError(f"未實作的事件：{event.kind}") from None
        handler(event)

    def release_all(self):
        errors = []
        for button in tuple(self.pressed):
            try:
                self._send(self.BUTTONS[button][1])
                self.pressed.discard(button)
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            raise OSError("無法釋放滑鼠按鍵：" + "; ".join(errors))

