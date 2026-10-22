"""Preview feedback without recording or generating mouse input."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord.windows import enable_dpi_awareness, own_window_at
enable_dpi_awareness()
from PySide6.QtWidgets import QApplication
from controlrecord.overlay import RecordingOverlay
app = QApplication([])
output = ROOT / 'artifacts/overlay-0.1.5'
output.mkdir(parents=True, exist_ok=True)
overlay = RecordingOverlay()
for state in ('countdown', 'recording'):
    if state == 'countdown':
        overlay.countdown(3)
    else:
        overlay.recording(12, 152)
    app.processEvents()
    overlay.grab().save(str(output / f'{state}.png'))
# Qt coordinates are logical; WindowFromPoint requires physical pixels.
point = overlay.geometry().center()
ratio = overlay.devicePixelRatioF()
assert not own_window_at(int(point.x() * ratio), int(point.y() * ratio)), 'Overlay blocks mouse hit testing'
point = overlay.handle.geometry().center()
assert own_window_at(int(point.x() * ratio), int(point.y() * ratio)), 'Drag handle is not clickable'
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
old = overlay.pos()
QTest.mousePress(overlay.handle, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
QTest.mouseMove(overlay.handle, QPoint(-90, 60))
QTest.mouseRelease(overlay.handle, Qt.MouseButton.LeftButton)
app.processEvents()
assert overlay.pos() != old, 'Handle did not move overlay'
dragged = overlay.pos()
overlay.recording(13, 160)
assert overlay.pos() == dragged, 'Timer update reset dragged position'
overlay.hide()
assert not overlay.handle.isVisible()
overlay.close()
print('Preview, native body/handle hit tests, drag, position retention and hide passed')
