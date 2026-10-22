"""Run using the bundled interpreter to validate real services, then close."""
import json
from pathlib import Path
import sys

from controlrecord.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from controlrecord.storage import Storage
from controlrecord.ui import MainWindow

folder = Path(sys.argv[1]).resolve()
app = QApplication([])
app.setStyle("Fusion")
window = MainWindow(Storage(folder), services=True)
window.show()
report = {}


def inspect():
    report.update({"hotkeys_active": window.hotkeys_ok,
                   "power_active": "已啟用" in window.power_label.text(),
                   "record_button_enabled": window.record_button.isEnabled(),
                   "state": window.state})
    window.grab().save(str(folder / "services-preview.png"))
    window.close()


QTimer.singleShot(1000, inspect)
app.exec()
report["listener_stopped"] = not window.hotkeys.listener.is_alive()
(folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
assert report["hotkeys_active"] and report["power_active"] and report["record_button_enabled"] and report["listener_stopped"]

