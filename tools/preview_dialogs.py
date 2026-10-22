"""Render message boxes with a dark system palette; no user data or input hooks."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox
from controlrecord.storage import Storage
from controlrecord.ui import MainWindow, STYLE

app = QApplication([])
app.setStyle('Fusion')
palette = app.palette()
palette.setColor(QPalette.ColorRole.Window, QColor('#202020'))
palette.setColor(QPalette.ColorRole.WindowText, QColor('#ffffff'))
palette.setColor(QPalette.ColorRole.Base, QColor('#151515'))
palette.setColor(QPalette.ColorRole.Text, QColor('#ffffff'))
app.setPalette(palette)
app.setStyleSheet(STYLE)
output = ROOT / 'artifacts/dialogs-0.1.3'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    window = MainWindow(Storage(Path(temporary)), services=False)
    for name, parent, icon in [('delete', window, QMessageBox.Icon.Question),
                               ('warning', window, QMessageBox.Icon.Warning),
                               ('startup', None, QMessageBox.Icon.Critical)]:
        box = QMessageBox(parent)
        box.setWindowTitle('刪除腳本' if name == 'delete' else '無法完成操作')
        box.setIcon(icon)
        box.setText('確定刪除「每日操作」？\n已保存的執行紀錄與影片會保留。' if name == 'delete' else '測試提示：請確認螢幕設定與執行權限。')
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No if name == 'delete' else QMessageBox.StandardButton.Ok)
        def capture():
            box.grab().save(str(output / f'{name}.png'))
            box.reject()
        QTimer.singleShot(200, capture)
        box.exec()
    window.close()
print(output)
