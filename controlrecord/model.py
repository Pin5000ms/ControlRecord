"""Versioned, data-only scripts. Event kinds are independent of input devices.

Future keyboard adapters can register keyboard.down / keyboard.up validators
and playback handlers without changing the scheduler or storage format.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

MAX_EVENTS = 500_000
MAX_SECONDS = 7 * 24 * 3600
MAX_FILE_BYTES = 64 * 1024 * 1024


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def number(value, label: str, minimum=0, maximum=MAX_SECONDS) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必須是數字")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} 超出允許範圍")
    return value


def integer(value, label: str, minimum=0, maximum=65535) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} 必須是整數")
    number(value, label, minimum, maximum)
    return value


@dataclass(frozen=True)
class Screen:
    width: int
    height: int
    dpi: int
    monitors: int = 1

    def validate(self):
        integer(self.width, "螢幕寬度", 1)
        integer(self.height, "螢幕高度", 1)
        integer(self.dpi, "DPI", 48, 960)
        integer(self.monitors, "螢幕數量", 1, 32)


@dataclass(frozen=True)
class Event:
    t: float
    kind: str
    data: dict = field(default_factory=dict)


class EventRegistry:
    def __init__(self):
        self.validators: dict[str, Callable[[dict, Screen], None]] = {}

    def register(self, kind: str, validator: Callable[[dict, Screen], None]):
        if kind in self.validators:
            raise ValueError(f"重複的事件類型：{kind}")
        self.validators[kind] = validator

    def validate(self, event: Event, screen: Screen):
        if not isinstance(event.kind, str) or event.kind not in self.validators:
            raise ValueError(f"此版本不支援事件 {event.kind!r}；鍵盤錄製尚未啟用。")
        if not isinstance(event.data, dict):
            raise ValueError("事件資料必須是物件")
        self.validators[event.kind](event.data, screen)


def mouse_registry() -> EventRegistry:
    registry = EventRegistry()

    def position(data, screen):
        integer(data.get("x"), "X 座標", 0, screen.width - 1)
        integer(data.get("y"), "Y 座標", 0, screen.height - 1)

    def button(data, screen):
        position(data, screen)
        if data.get("button") not in ("left", "right", "middle"):
            raise ValueError("不支援的滑鼠按鍵")

    def scroll(data, screen):
        position(data, screen)
        integer(data.get("dx"), "水平滾輪", -10000, 10000)
        integer(data.get("dy"), "垂直滾輪", -10000, 10000)

    registry.register("mouse.move", position)
    registry.register("mouse.down", button)
    registry.register("mouse.up", button)
    registry.register("mouse.scroll", scroll)
    return registry


@dataclass
class Script:
    name: str
    screen: Screen
    duration: float
    events: list[Event]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=now_iso)
    schema_version: int = 1

    def validate(self, registry: EventRegistry | None = None):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("不支援的腳本版本")
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 100:
            raise ValueError("腳本名稱需為 1～100 個字元")
        if not isinstance(self.id, str) or len(self.id) != 32:
            raise ValueError("腳本 ID 格式錯誤")
        try:
            uuid.UUID(hex=self.id)
            datetime.fromisoformat(self.created_at)
        except (ValueError, TypeError):
            raise ValueError("腳本識別或建立時間格式錯誤") from None
        self.screen.validate()
        number(self.duration, "腳本長度", 0.001)
        if not self.events or len(self.events) > MAX_EVENTS:
            raise ValueError(f"事件數量需為 1～{MAX_EVENTS:,}")
        registry = registry or mouse_registry()
        previous = 0.0
        pressed = set()
        for event in self.events:
            number(event.t, "事件時間", previous, self.duration)
            registry.validate(event, self.screen)
            if event.kind == "mouse.down":
                key = event.data["button"]
                if key in pressed:
                    raise ValueError("腳本包含重複按下的滑鼠按鍵")
                pressed.add(key)
            elif event.kind == "mouse.up":
                key = event.data["button"]
                if key not in pressed:
                    raise ValueError("腳本包含未按下就放開的滑鼠按鍵")
                pressed.remove(key)
            previous = event.t
        if pressed:
            raise ValueError("腳本結尾仍有按住的滑鼠按鍵")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict, registry: EventRegistry | None = None) -> Script:
        try:
            if not isinstance(data, dict) or not isinstance(data.get("events"), list):
                raise ValueError("不是有效的腳本物件")
            if len(data["events"]) > MAX_EVENTS:
                raise ValueError("腳本事件數量過多")
            script = cls(
                name=data["name"], screen=Screen(**data["screen"]),
                duration=data["duration"], events=[Event(**e) for e in data["events"]],
                id=data["id"], created_at=data["created_at"],
                schema_version=data["schema_version"],
            )
            script.validate(registry)
            return script
        except (KeyError, TypeError) as exc:
            raise ValueError(f"腳本結構不完整：{exc}") from exc


def write_json(path: Path, data: dict):
    """Replace atomically; never leave a half-written script or history file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def load_script(path: Path) -> Script:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("腳本檔案超過 64 MB")
    try:
        with path.open(encoding="utf-8-sig") as file:
            return Script.from_dict(json.load(file))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("無法讀取 JSON 腳本") from exc


def save_script(path: Path, script: Script):
    script.validate()
    write_json(path, script.to_dict())

