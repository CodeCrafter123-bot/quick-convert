"""App icon drawn in code: a small action wheel (no binary assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

COLORS = ["#1e88e5", "#43a047", "#fb8c00", "#8e24aa"]


def _render(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size * 0.04
    outer = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    inner_r = size * 0.18
    c = size / 2
    for i, color in enumerate(COLORS):
        path = QPainterPath()
        start = 90 - i * 90 + 45  # four quadrants, rotated like the wheel
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, -90)
        path.arcTo(QRectF(c - inner_r, c - inner_r, 2 * inner_r, 2 * inner_r), start - 90, 90)
        path.closeSubpath()
        p.setPen(QPen(QColor("white"), max(1.0, size / 32)))
        p.setBrush(QColor(color))
        p.drawPath(path)
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_render(size))
    return icon
