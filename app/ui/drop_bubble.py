"""System-wide Shift+drag: a small drop target that appears next to the cursor.

The bubble sits beside the cursor (not under it), so ordinary Shift+drags in other
apps, such as text selection, are never intercepted; the user moves onto it to drop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from app.integration.gesture import DragGestureDetector
from app.ui.dnd import accept_safely, single_local_file
from app.ui.geometry import clamp_center

log = logging.getLogger("quickconvert.bubble")

BUBBLE_SIZE = 104
CURSOR_OFFSET = 70  # bubble center distance from the cursor
POLL_MS = 40
HIDE_DELAY_MS = 600  # let an in-flight drop be delivered before hiding


class DropBubble(QWidget):
    file_dropped = Signal(Path, QPoint)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setFixedSize(BUBBLE_SIZE, BUBBLE_SIZE)
        self.setAccessibleName("QuickConvert drop target")
        self.hot = False

    def show_near(self, cursor: QPoint) -> None:
        """Place the bubble down-right of the cursor, flipping/clamping at screen edges."""
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        radius = BUBBLE_SIZE // 2
        dx = CURSOR_OFFSET if cursor.x() + CURSOR_OFFSET + radius <= geo.right() else -CURSOR_OFFSET
        dy = CURSOR_OFFSET if cursor.y() + CURSOR_OFFSET + radius <= geo.bottom() else -CURSOR_OFFSET
        x, y = clamp_center(cursor.x() + dx, cursor.y() + dy, radius,
                            (geo.left(), geo.top(), geo.width(), geo.height()))
        self.move(x - radius, y - radius)
        self.hot = False
        self.show()
        self.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = self.palette().highlight().color()
        fill = QColor(accent)
        fill.setAlpha(235 if self.hot else 200)
        p.setPen(QPen(QColor(255, 255, 255, 230), 3))
        p.setBrush(fill)
        p.drawEllipse(QRectF(4, 4, BUBBLE_SIZE - 8, BUBBLE_SIZE - 8))
        p.setPen(QColor(255, 255, 255))
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "Release\nto convert" if self.hot else "Drop here\nQuickConvert")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if single_local_file(event) and accept_safely(event):
            self.hot = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        accept_safely(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.hot = False
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = single_local_file(event)
        if path is None or not accept_safely(event):
            event.ignore()
            return
        center = self.mapToGlobal(self.rect().center())
        self.hide()
        self.file_dropped.emit(path, center)


InputReader = Callable[[], tuple[bool, bool]]


class GlobalDragWatcher(QObject):
    """Polls input state and shows the bubble during a Shift+drag outside our windows."""

    file_dropped = Signal(Path, QPoint)

    def __init__(self, read_input: InputReader, parent: QObject | None = None,
                 cursor_pos: Callable[[], QPoint] = QCursor.pos):
        super().__init__(parent)
        self.read_input = read_input
        self.cursor_pos = cursor_pos
        self.detector = DragGestureDetector()
        self.bubble = DropBubble()
        self.bubble.file_dropped.connect(self.file_dropped)
        self.timer = QTimer(self, interval=POLL_MS)
        self.timer.timeout.connect(self.poll)
        self.hide_timer = QTimer(self, singleShot=True, interval=HIDE_DELAY_MS)
        self.hide_timer.timeout.connect(self.bubble.hide)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.timer.start()
        else:
            self.timer.stop()
            self.bubble.hide()
            self.detector = DragGestureDetector()

    def is_enabled(self) -> bool:
        return self.timer.isActive()

    def poll(self) -> None:
        try:
            button, shift = self.read_input()
        except OSError:
            log.exception("input polling failed; disabling the Shift+drag bubble")
            self.set_enabled(False)
            return
        cursor = self.cursor_pos()
        top = QApplication.topLevelAt(cursor)
        over_own = top is not None and top is not self.bubble
        result = self.detector.update(button, shift, (cursor.x(), cursor.y()), over_own)
        if result == "show":
            self.hide_timer.stop()
            self.bubble.show_near(cursor)
        elif result == "hide":
            self.hide_timer.start()

    def shutdown(self) -> None:
        self.set_enabled(False)
        self.bubble.close()
