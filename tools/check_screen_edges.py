"""Move only (no clicks) against each screen edge, restoring the cursor."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord.windows import enable_dpi_awareness, screen_info, cursor_position, mouse_is_held, WindowsInput
enable_dpi_awareness()
from controlrecord.capture import MouseRecorder, start_listener
from controlrecord.model import Event
from pynput import mouse

if mouse_is_held():
    raise SystemExit("Release the mouse buttons before the edge test.")
screen = screen_info()
original = cursor_position()
raw = []
observer = mouse.Listener(on_move=lambda x, y, *extra: raw.append((x, y)))
driver = WindowsInput(screen)
recorder = MouseRecorder("screen edge regression", screen)
start_listener(observer)
recorder.start()
try:
    for dx, dy in ((0, -screen.height * 2), (0, screen.height * 2), (-screen.width * 2, 0), (screen.width * 2, 0)):
        driver._send(0x0001 | 0x2000, dx, dy)
        time.sleep(.15)
    driver.dispatch(Event(0, "mouse.move", {"x": original[0], "y": original[1]}))
    time.sleep(5)
    active = recorder.active
    error = recorder.error
    script = recorder.stop()
    script.validate()
    report = {"active_after_edges": active, "error": error,
              "raw_out_of_bounds": [p for p in raw if not (0 <= p[0] < screen.width and 0 <= p[1] < screen.height)],
              "duration": script.duration, "saved_events": len(script.events), "all_saved_coordinates_valid": all(0 <= e.data['x'] < screen.width and 0 <= e.data['y'] < screen.height for e in script.events)}
    folder = ROOT / "artifacts" / "edge-regression"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("fixed.json" if active else "before.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
finally:
    observer.stop()
    observer.join(timeout=2)
    if recorder.active:
        recorder.stop()
    driver.dispatch(Event(0, "mouse.move", {"x": original[0], "y": original[1]}))
