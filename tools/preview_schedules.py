"""Render schedule controls using temporary sample data; never executes input."""
from pathlib import Path
from datetime import datetime, timedelta
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord.windows import enable_dpi_awareness, screen_info
enable_dpi_awareness()
from PySide6.QtWidgets import QApplication
from controlrecord.storage import Storage
from controlrecord.model import Script, Event
from controlrecord.ui import MainWindow, STYLE
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
output = ROOT / 'artifacts/schedules-0.2.0'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    storage = Storage(Path(temporary))
    script = Script('每日操作 A', screen_info(), 1, [Event(0, 'mouse.move', {'x': 1, 'y': 1})])
    storage.save(script)
    window = MainWindow(storage, services=False)
    page = window.schedule_page
    page.timer.stop()
    now = datetime.now()
    page.store.add(script, 'once', now + timedelta(days=1), [], '09:00', False, now)
    page.store.add(script, 'weekly', now, [0, 2, 4], '18:30', True, now)
    page.refresh()
    window.tabs.setCurrentWidget(page)
    window.show()
    for mode, name in ((0, 'once'), (1, 'weekly')):
        page.mode.setCurrentIndex(mode)
        for day in (0, 2, 4):
            page.days[day].setChecked(True)
        app.processEvents()
        window.grab().save(str(output / f'{name}.png'))
    window.close()
print(output)
