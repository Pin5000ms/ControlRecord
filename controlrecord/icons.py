"""Small vector-drawn button icons, bundled as code with no font dependency."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def action_icon(action: str, color: str) -> QIcon:
    icon = QIcon()
    for mode, ink in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, '#a4afbb')):
        for size in (16, 20, 24, 32, 40, 48, 64):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(size / 24, size / 24)
            painter.setPen(QPen(QColor(ink), 1.8, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if action == 'delete':
                painter.drawLine(QPointF(4, 6), QPointF(20, 6))
                painter.drawPolyline(QPolygonF([QPointF(9, 6), QPointF(9, 3), QPointF(15, 3), QPointF(15, 6)]))
                painter.drawPolyline(QPolygonF([QPointF(6, 6), QPointF(7, 21), QPointF(17, 21), QPointF(18, 6)]))
                painter.drawLine(QPointF(10, 10), QPointF(10, 17))
                painter.drawLine(QPointF(14, 10), QPointF(14, 17))
            else:
                painter.setBrush(QColor(ink))
                painter.setPen(Qt.PenStyle.NoPen)
                if action == 'record':
                    painter.drawEllipse(QRectF(4, 4, 16, 16))
                elif action == 'stop':
                    painter.drawRoundedRect(QRectF(5, 5, 14, 14), 1.5, 1.5)
                elif action == 'play':
                    painter.drawPolygon(QPolygonF([QPointF(7, 3), QPointF(21, 12), QPointF(7, 21)]))
                else:
                    painter.end()
                    raise ValueError(f'Unknown icon: {action}')
            painter.end()
            icon.addPixmap(pixmap, mode)
    return icon
