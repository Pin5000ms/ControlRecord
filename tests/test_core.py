import copy
from pathlib import Path
import tempfile
import threading
import unittest

from controlrecord.model import Event, Screen, Script, load_script, mouse_registry, save_script
from controlrecord.playback import Playback
from controlrecord.storage import Storage


def example():
    return Script("測試腳本", Screen(1920, 1080, 144), 1.0, [
        Event(0, "mouse.move", {"x": 10, "y": 20}),
        Event(.1, "mouse.down", {"x": 10, "y": 20, "button": "left"}),
        Event(.3, "mouse.move", {"x": 30, "y": 40}),
        Event(.4, "mouse.up", {"x": 30, "y": 40, "button": "left"}),
    ])


class FakeClock:
    now = 0.0

    def __call__(self):
        return self.now


class FakeStop:
    def __init__(self, clock, at=float("inf")):
        self.clock = clock
        self.at = at

    def is_set(self):
        return self.clock.now >= self.at

    def wait(self, seconds):
        self.clock.now += seconds
        return self.is_set()


class FakeDriver:
    def __init__(self, clock):
        self.clock = clock
        self.sent = []
        self.held = set()
        self.releases = 0

    def dispatch(self, event):
        self.sent.append((self.clock(), event.kind))
        if event.kind == "mouse.down":
            self.held.add(event.data["button"])
        elif event.kind == "mouse.up":
            self.held.discard(event.data["button"])

    def release_all(self):
        self.held.clear()
        self.releases += 1


class ScriptTests(unittest.TestCase):
    def test_roundtrip_and_unicode(self):
        script = example()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "腳本.json"
            save_script(path, script)
            self.assertEqual(load_script(path), script)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_reject_bad_event_times(self):
        for value in (float("nan"), float("inf"), -1, 2, True, "0.1"):
            with self.subTest(value=value):
                script = example()
                script.events[1] = Event(value, "mouse.down", script.events[1].data)
                with self.assertRaises(ValueError):
                    script.validate()

    def test_reject_unsorted_events(self):
        script = example()
        script.events[0] = Event(.2, "mouse.move", {"x": 1, "y": 2})
        with self.assertRaises(ValueError):
            script.validate()

    def test_reject_unsafe_coordinates_and_buttons(self):
        for data in ({"x": -1, "y": 5}, {"x": 1920, "y": 0}, {"x": 1.2, "y": 0}, {"x": True, "y": 0}):
            script = example()
            script.events[0] = Event(0, "mouse.move", data)
            with self.assertRaises(ValueError):
                script.validate()

    def test_unknown_action_cannot_execute_code(self):
        script = example()
        script.events[0] = Event(0, "shell.exec", {"command": "arbitrary code"})
        with self.assertRaisesRegex(ValueError, "不支援事件"):
            script.validate()

    def test_keyboard_is_explicitly_unsupported(self):
        script = example()
        script.events[0] = Event(0, "keyboard.down", {"scan_code": 30})
        with self.assertRaisesRegex(ValueError, "鍵盤錄製尚未啟用"):
            script.validate()

    def test_future_adapter_can_register_without_scheduler_changes(self):
        registry = mouse_registry()
        registry.register("keyboard.down", lambda data, screen: None)
        registry.register("keyboard.up", lambda data, screen: None)
        script = example()
        script.events = [Event(0, "keyboard.down", {"scan_code": 30}), Event(.5, "keyboard.up", {"scan_code": 30})]
        imported = Script.from_dict(script.to_dict(), registry)
        clock = FakeClock()
        driver = FakeDriver(clock)
        count = Playback(driver, FakeStop(clock), clock=clock, registry=registry).run(imported, 1)
        self.assertEqual(count, 1)
        self.assertEqual([kind for _, kind in driver.sent], ["keyboard.down", "keyboard.up"])

    def test_missing_fields_fail_cleanly(self):
        for value in ({}, [], {"events": [{}]}, {**example().to_dict(), "screen": {"width": 1}}):
            with self.assertRaises(ValueError):
                Script.from_dict(value)

    def test_unbalanced_button_rejected(self):
        script = example()
        script.events.pop()
        with self.assertRaisesRegex(ValueError, "按住"):
            script.validate()

    def test_duplicate_down_rejected(self):
        script = example()
        script.events.insert(2, Event(.2, "mouse.down", {"x": 10, "y": 20, "button": "left"}))
        with self.assertRaisesRegex(ValueError, "重複按下"):
            script.validate()

    def test_import_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder))
            original = example()
            storage.save(original)
            imported = storage.import_file(storage.scripts / f"{original.id}.json")
            self.assertNotEqual(original.id, imported.id)
            self.assertEqual(len(storage.list_scripts()[0]), 2)

    def test_corrupt_script_does_not_hide_valid_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder))
            storage.save(example())
            (storage.scripts / "broken.json").write_text("not json")
            scripts, errors = storage.list_scripts()
            self.assertEqual(len(scripts), 1)
            self.assertEqual(len(errors), 1)


class PlaybackTests(unittest.TestCase):
    def test_timestamps_tail_wait_and_repeats(self):
        clock = FakeClock()
        driver = FakeDriver(clock)
        progress = []
        result = Playback(driver, FakeStop(clock), clock=clock).run(example(), 3, lambda n, total: progress.append(n))
        self.assertEqual(result, 3)
        self.assertAlmostEqual(clock.now, 3)
        self.assertEqual(progress, [1, 2, 3])
        for actual, expected in zip([t for t, _ in driver.sent], [0, .1, .3, .4, 1, 1.1, 1.3, 1.4, 2, 2.1, 2.3, 2.4]):
            self.assertAlmostEqual(actual, expected)

    def test_cancel_drag_releases_button(self):
        clock = FakeClock()
        driver = FakeDriver(clock)
        count = Playback(driver, FakeStop(clock, .15), clock=clock).run(example(), 1)
        self.assertEqual(count, 0)
        self.assertEqual(len(driver.sent), 2)
        self.assertFalse(driver.held)
        self.assertLessEqual(clock.now, .2)

    def test_cancel_before_start_sends_no_events(self):
        clock = FakeClock()
        driver = FakeDriver(clock)
        self.assertEqual(Playback(driver, FakeStop(clock, 0), clock=clock).run(example(), 1), 0)
        self.assertFalse(driver.sent)

    def test_cancel_during_tail_does_not_mark_loop_complete(self):
        clock = FakeClock()
        driver = FakeDriver(clock)
        count = Playback(driver, FakeStop(clock, .6), clock=clock).run(example(), 2)
        self.assertEqual(count, 0)
        self.assertEqual(len(driver.sent), 4)

    def test_health_failure_releases_pressed_buttons(self):
        clock = FakeClock()
        driver = FakeDriver(clock)

        def health():
            if clock.now >= .2:
                raise RuntimeError("recorder failed")

        with self.assertRaisesRegex(RuntimeError, "recorder failed"):
            Playback(driver, FakeStop(clock), health=health, clock=clock).run(example(), 1)
        self.assertFalse(driver.held)

    def test_execution_overhead_does_not_accumulate_per_event(self):
        clock = FakeClock()
        driver = FakeDriver(clock)
        original = driver.dispatch

        def slow(event):
            original(event)
            clock.now += .02

        driver.dispatch = slow
        Playback(driver, FakeStop(clock), clock=clock).run(example(), 1)
        self.assertAlmostEqual(clock.now, 1)
        self.assertAlmostEqual(driver.sent[-1][0], .4)

    def test_invalid_repeat_count(self):
        for count in (0, -1, True, 1.5, 10000):
            clock = FakeClock()
            with self.assertRaises(ValueError):
                Playback(FakeDriver(clock), FakeStop(clock), clock=clock).run(example(), count)


if __name__ == "__main__":
    unittest.main()

