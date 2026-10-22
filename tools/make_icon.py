from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPolygonF

app = QGuiApplication([])
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor("#14283b"))
painter.drawRoundedRect(QRectF(4, 4, 248, 248), 54, 54)
painter.setBrush(Qt.BrushStyle.NoBrush)
painter.setPen(QPen(QColor("#7be5cf"), 20, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
painter.drawArc(QRectF(48, 48, 160, 160), 45 * 16, 280 * 16)
painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor("#ffffff"))
painter.drawPolygon(QPolygonF([QPointF(111, 91), QPointF(111, 165), QPointF(173, 128)]))
painter.end()
path = Path(__file__).resolve().parents[1] / "controlrecord" / "app.ico"
assert image.save(str(path), "ICO")
print(path)

