from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class SkinCubeWidget(QWidget):
    """A small isometric skin-head preview; requires an actual Mojang skin texture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 145)
        self.setMaximumSize(190, 175)
        self._skin = QPixmap()
        self._account_name = "Player"

    def set_skin_path(self, path: str, account_name: str = "") -> None:
        pixmap = QPixmap(path) if path else QPixmap()
        if not pixmap.isNull():
            self._skin = pixmap
        if account_name:
            self._account_name = account_name
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        size = min(self.width(), self.height()) * 0.48
        x = (self.width() - size * 1.55) / 2
        y = (self.height() - size * 1.2) / 2 + 3
        front = QRect(int(x), int(y + size * .2), int(size), int(size))
        side = QRect(int(x + size), int(y + size * .2), int(size * .55), int(size))
        top = QRect(int(x + size * .15), int(y - size * .12), int(size * 1.2), int(size * .32))
        if not self._skin.isNull() and self._skin.width() >= 64 and self._skin.height() >= 32:
            front_source = QRect(8, 8, 8, 8)
            side_source = QRect(16, 8, 8, 8)
            top_source = QRect(8, 0, 8, 8)
            painter.drawPixmap(front, self._skin, front_source)
            painter.setOpacity(.82)
            painter.drawPixmap(side, self._skin, side_source)
            painter.setOpacity(.9)
            painter.drawPixmap(top, self._skin, top_source)
            painter.setOpacity(1)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#a6a1d5"))
            painter.drawRect(front)
            painter.setBrush(QColor("#7772a8"))
            painter.drawRect(side)
            painter.setBrush(QColor("#c0b7ee"))
            painter.drawPolygon([
                front.topLeft(), front.topRight(),
                top.topRight(), top.topLeft()
            ])
            painter.setPen(QColor("#3c2b53"))
            painter.drawLine(front.topLeft(), front.topRight())
            painter.drawLine(front.topLeft(), front.bottomLeft())
        painter.setPen(QColor("#a99ab9"))
        painter.drawText(QRect(0, self.height() - 22, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self._account_name)
        painter.end()
