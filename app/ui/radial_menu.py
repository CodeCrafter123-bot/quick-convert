"""The circular action menu: equal sectors, hover feedback, keyboard navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from app.ui.geometry import clamp_center, polar_to_xy, sector_at, sector_center_angle, sector_step


@dataclass(frozen=True)
class RadialItem:
    label: str
    data: Any
    enabled: bool = True
    tooltip: str = ""


class RadialMenu(QWidget):
    """A popup wheel. Emits `triggered(data)` for an enabled item, then closes."""

    triggered = Signal(object)

    OUTER = 120
    INNER = 42
    MARGIN = 6

    def __init__(self, items: list[RadialItem], center_text: str = "", parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Conversion menu")
        self.items = items
        self.center_text = center_text
        self.current: int | None = None
        size = 2 * (self.OUTER + self.MARGIN)
        self.setFixedSize(size, size)

    # --- showing -------------------------------------------------------------

    def popup_at(self, global_center: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_center) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        radius = self.width() // 2
        x, y = clamp_center(global_center.x(), global_center.y(), radius,
                            (geo.left(), geo.top(), geo.width(), geo.height()))
        self.move(x - radius, y - radius)
        self.current = self._first_enabled()
        self.show()
        self.activateWindow()
        self.setFocus()

    # --- geometry ------------------------------------------------------------

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _index_at(self, pos: QPointF) -> int | None:
        c = self._center()
        return sector_at(pos.x() - c.x(), pos.y() - c.y(), len(self.items), self.INNER, self.OUTER)

    def _sector_path(self, index: int) -> QPainterPath:
        c = self._center()
        step = sector_step(len(self.items))
        # Qt arcs: degrees counter-clockwise from 3 o'clock.
        start = 90 - (sector_center_angle(index, len(self.items)) - step / 2)
        outer = QRectF(c.x() - self.OUTER, c.y() - self.OUTER, 2 * self.OUTER, 2 * self.OUTER)
        inner = QRectF(c.x() - self.INNER, c.y() - self.INNER, 2 * self.INNER, 2 * self.INNER)
        path = QPainterPath()
        if len(self.items) == 1:
            path.addEllipse(outer)
            path.addEllipse(inner)
            return path
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, -step)
        path.arcTo(inner, start - step, step)
        path.closeSubpath()
        return path

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Window)
        text = pal.color(QPalette.ColorRole.WindowText)
        accent = pal.color(QPalette.ColorRole.Highlight)
        accent_text = pal.color(QPalette.ColorRole.HighlightedText)
        disabled = QColor(text)
        disabled.setAlpha(90)

        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        c = self._center()
        mid_radius = (self.INNER + self.OUTER) / 2

        for i, item in enumerate(self.items):
            path = self._sector_path(i)
            fill = accent if i == self.current and item.enabled else base
            if i == self.current and not item.enabled:
                fill = base.darker(110)
            p.setPen(QPen(text.lighter(150) if base.lightness() < 128 else base.darker(125), 1.5))
            p.setBrush(fill)
            p.drawPath(path)

            x, y = polar_to_xy(c.x(), c.y(), mid_radius, sector_center_angle(i, len(self.items)))
            rect = QRectF(x - 40, y - 12, 80, 24)
            if not item.enabled:
                p.setPen(disabled)
            elif i == self.current:
                p.setPen(accent_text)
            else:
                p.setPen(text)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, item.label)

        # Center hub with the file label; clicking it closes the menu.
        p.setPen(QPen(base.darker(125), 1.5))
        p.setBrush(base.darker(105) if base.lightness() >= 128 else base.lighter(130))
        p.drawEllipse(c, self.INNER - 4, self.INNER - 4)
        p.setPen(text)
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        p.setFont(small)
        hub = QRectF(c.x() - self.INNER + 8, c.y() - 14, 2 * self.INNER - 16, 28)
        p.drawText(hub, Qt.AlignmentFlag.AlignCenter,
                   p.fontMetrics().elidedText(self.center_text, Qt.TextElideMode.ElideMiddle,
                                              int(hub.width())))

    # --- interaction ---------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if index != self.current:
            self.current = index
            self.update()
            if index is not None and self.items[index].tooltip:
                QToolTip.showText(event.globalPosition().toPoint(), self.items[index].tooltip, self)
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position())
        if index is None:
            c = self._center()
            if (event.position() - c).manhattanLength() < self.INNER:
                self.close()
            return
        self.activate(index)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._move(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self._move(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.current is not None:
                self.activate(self.current)
        elif key == Qt.Key.Key_Escape:
            self.close()
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_1
            if index < len(self.items):
                self.activate(index)
        else:
            super().keyPressEvent(event)

    def activate(self, index: int) -> None:
        item = self.items[index]
        if not item.enabled:
            self.current = index
            self.update()
            return
        self.close()
        self.triggered.emit(item.data)

    def _move(self, delta: int) -> None:
        n = len(self.items)
        start = self.current if self.current is not None else (-1 if delta > 0 else 0)
        for step in range(1, n + 1):
            candidate = (start + delta * step) % n
            if self.items[candidate].enabled:
                self.current = candidate
                break
        self.update()

    def _first_enabled(self) -> int | None:
        return next((i for i, item in enumerate(self.items) if item.enabled), None)
