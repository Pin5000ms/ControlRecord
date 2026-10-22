"""Non-activating, click-through recording feedback."""
import math
import winsound

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class DragHandle(QLabel):
    def __init__(self, overlay):
        super().__init__('⠿', None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.overlay = overlay
        self.anchor = None
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip('按住並拖曳狀態條')
        self.setStyleSheet('background: #385368; color: white; font-size: 20px; border-radius: 4px;')
        self.setWindowOpacity(.82)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = event.globalPosition().toPoint() - self.overlay.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.overlay.move_clamped(event.globalPosition().toPoint() - self.anchor)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.anchor = None
        event.accept()


def play_start_sound():
    try:
        winsound.PlaySound('SystemAsterisk', winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError:
        pass  # An unavailable audio device must not interrupt recording.


class RecordingOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setObjectName('recordingOverlay')
        self.setWindowOpacity(.82)
        self.positioned = False
        self.handle = DragHandle(self)
        self.setStyleSheet('''
            QWidget#recordingOverlay { background: #14283b; border: 1px solid #678092; border-radius: 8px; }
            QLabel { background: transparent; color: #ffffff; font-family: 'Microsoft JhengHei UI'; font-size: 11px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 6, 8, 6)
        layout.setSpacing(2)
        self.title = QLabel()
        self.details = QLabel()
        layout.addWidget(self.title)
        layout.addWidget(self.details)
        self.setFixedSize(280, 52)

    def move_clamped(self, point):
        area = QApplication.primaryScreen().availableGeometry()
        point.setX(max(area.left(), min(point.x(), area.right() - self.width() + 1)))
        point.setY(max(area.top(), min(point.y(), area.bottom() - self.height() + 1)))
        self.move(point)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.handle.setGeometry(self.x() + 4, self.y() + 4, 22, self.height() - 8)

    def hideEvent(self, event):
        self.handle.hide()
        self.handle.anchor = None
        super().hideEvent(event)

    def closeEvent(self, event):
        self.handle.close()
        self.handle.deleteLater()
        super().closeEvent(event)

    def reveal(self):
        area = QApplication.primaryScreen().availableGeometry()
        if not self.positioned:
            self.move(area.right() - self.width() - 16, area.top() + 16)
            self.positioned = True
        self.move_clamped(self.pos())
        if not self.isVisible():
            self.show()
            self.handle.show()

    def countdown(self, remaining):
        self.title.setStyleSheet('color: #ffd580; font-size: 14px; font-weight: bold;')
        self.title.setText(f'即將開始錄製 · {max(1, math.ceil(remaining))} 秒')
        self.details.setText('請準備操作畫面　｜　F12 取消')
        self.reveal()

    def recording(self, seconds, events):
        total = max(0, int(seconds))
        self.title.setStyleSheet('color: #ff9b9b; font-size: 14px; font-weight: bold;')
        self.title.setText(f'● 錄製中　{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}')
        self.details.setText(f'{events:,} 事件｜F8 儲存 · F12 停止')
        self.reveal()
