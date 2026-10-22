"""Harmless isolated input target used only by windows_integration.py."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controlrecord.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

folder = Path(sys.argv[1])


class Target(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ControlRecord 自動驗證視窗")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(80, 80, 650, 380)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #e8f7f3; color: #123b39; font-size: 22px;")
        self.setLayout(QVBoxLayout())
        text = QLabel("ControlRecord 輸入測試\n\n此視窗接收測試點擊、拖曳與滾輪。\n測試完成後會自動關閉。")
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.layout().addWidget(text)
        self.events = []

    def log(self, kind, data):
        self.events.append({"kind": kind, **data})
        (folder / "target-events.json").write_text(json.dumps(self.events), encoding="utf-8")

    def mousePressEvent(self, event):
        self.log("down", {"button": event.button().name})

    def mouseReleaseEvent(self, event):
        self.log("up", {"button": event.button().name})

    def mouseDoubleClickEvent(self, event):
        self.log("double", {"button": event.button().name})

    def mouseMoveEvent(self, event):
        if event.buttons():
            self.log("drag", {})

    def wheelEvent(self, event):
        self.log("wheel", {"x": event.angleDelta().x(), "y": event.angleDelta().y()})


app = QApplication(sys.argv[:1])
target = Target()
target.show()
target.activateWindow()


def ready():
    import os
    point = target.mapToGlobal(target.rect().center())
    scale = target.devicePixelRatioF()
    (folder / "target-ready.json").write_text(json.dumps({
        "pid": os.getpid(), "hwnd": int(target.winId()),
        "x": round(point.x() * scale), "y": round(point.y() * scale),
    }))


QTimer.singleShot(500, ready)
QTimer.singleShot(90000, app.quit)
app.exec()

