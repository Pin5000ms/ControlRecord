"""Device-independent scheduling; never execute code from imported scripts."""
from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from .model import Event, EventRegistry, Script, integer


class Driver(Protocol):
    def dispatch(self, event: Event) -> None: ...
    def release_all(self) -> None: ...


class Playback:
    def __init__(self, driver: Driver, stop: threading.Event,
                 health: Callable[[], None] = lambda: None,
                 clock: Callable[[], float] = time.perf_counter,
                 registry: EventRegistry | None = None):
        self.driver = driver
        self.stop = stop
        self.health = health
        self.clock = clock
        self.registry = registry

    def wait_until(self, deadline: float) -> bool:
        while not self.stop.is_set():
            self.health()
            remaining = deadline - self.clock()
            if remaining <= 0:
                return True
            self.stop.wait(min(remaining, 0.05))
        return False

    def run(self, script: Script, repeats: int, progress=lambda done, total: None) -> int:
        script.validate(self.registry)
        integer(repeats, "重複次數", 1, 9999)
        completed = 0
        try:
            for _ in range(repeats):
                start = self.clock()
                for event in script.events:
                    if not self.wait_until(start + event.t):
                        return completed
                    if self.stop.is_set():
                        return completed
                    self.driver.dispatch(event)
                # A script's tail delay belongs to every iteration.
                if not self.wait_until(start + script.duration):
                    return completed
                self.driver.release_all()
                completed += 1
                progress(completed, repeats)
            return completed
        finally:
            self.driver.release_all()

