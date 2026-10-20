"""Crop dialog: drag handles over a scaled preview; the selection is kept in original pixels."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models import Box
from app.ui import crop_geometry as cg

HANDLE_RADIUS = 6
HIT_RADIUS = 10
MIN_VIEW_SIZE = 12  # smallest selection, in screen pixels

CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
    "move": Qt.CursorShape.SizeAllCursor,
}


class CropWidget(QWidget):
    changed = Signal()

    def __init__(self, pixmap: QPixmap, original_size: tuple[int, int],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.img_w, self.img_h = original_size
        self.rect_img: cg.Rect = cg.full_rect(self.img_w, self.img_h)
        self.ratio: float | None = None
        self._drag: str | None = None
        self._drag_origin = QPointF()
        self._drag_rect = self.rect_img
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Crop area. Arrow keys move the selection; Shift moves faster.")

    # --- coordinate mapping (view <-> original image pixels) -----------------

    def _scale_offset(self) -> tuple[float, float, float]:
        scale = min(self.width() / self.img_w, self.height() / self.img_h)
        ox = (self.width() - self.img_w * scale) / 2
        oy = (self.height() - self.img_h * scale) / 2
        return scale, ox, oy

    def to_image(self, p: QPointF) -> tuple[float, float]:
        scale, ox, oy = self._scale_offset()
        return (p.x() - ox) / scale, (p.y() - oy) / scale

    def to_view(self, x: float, y: float) -> QPointF:
        scale, ox, oy = self._scale_offset()
        return QPointF(x * scale + ox, y * scale + oy)

    def view_rect(self) -> QRectF:
        left, top, right, bottom = self.rect_img
        return QRectF(self.to_view(left, top), self.to_view(right, bottom))

    def _min_size(self) -> float:
        return max(1.0, MIN_VIEW_SIZE / self._scale_offset()[0])

    # --- public API -----------------------------------------------------------

    def box(self) -> Box:
        return cg.to_box(self.rect_img, self.img_w, self.img_h)

    def set_box(self, box: Box | None) -> None:
        self.rect_img = cg.full_rect(self.img_w, self.img_h) if box is None else tuple(map(float, box))
        self._after_change()

    def set_ratio(self, ratio: float | None) -> None:
        self.ratio = ratio
        if ratio is not None:
            self.rect_img = cg.fit_ratio(self.rect_img, ratio)
        self._after_change()

    def _after_change(self) -> None:
        self.update()
        self.changed.emit()

    # --- interaction ------------------------------------------------------------

    def _hit(self, pos: QPointF) -> str | None:
        for name, (x, y) in cg.handle_points(self.rect_img).items():
            if (self.to_view(x, y) - pos).manhattanLength() <= HIT_RADIUS * 1.4:
                return name
        if self.view_rect().contains(pos):
            return "move"
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self._drag = self._hit(pos) or "new"
        self._drag_origin = pos
        self._drag_rect = self.rect_img
        if self._drag == "new":
            x, y = self.to_image(pos)
            self._anchor = (min(max(x, 0), self.img_w), min(max(y, 0), self.img_h))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if self._drag is None:
            hit = self._hit(pos)
            self.setCursor(CURSORS.get(hit, Qt.CursorShape.CrossCursor))
            return
        x, y = self.to_image(pos)
        if self._drag == "move":
            scale = self._scale_offset()[0]
            delta = (pos - self._drag_origin) / scale
            self.rect_img = cg.move(self._drag_rect, delta.x(), delta.y(), self.img_w, self.img_h)
        elif self._drag == "new":
            if (pos - self._drag_origin).manhattanLength() < 4:
                return  # ignore clicks; only real drags make a new selection
            self.rect_img = cg.from_points(*self._anchor, x, y, self.img_w, self.img_h,
                                           self.ratio, self._min_size())
        else:
            self.rect_img = cg.resize(self._drag_rect, self._drag, x, y, self.img_w, self.img_h,
                                      self.ratio, self._min_size())
        self._after_change()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag = None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        step = max(step, step / self._scale_offset()[0])
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if event.key() in moves:
            self.rect_img = cg.move(self.rect_img, *moves[event.key()], self.img_w, self.img_h)
            self._after_change()
        else:
            super().keyPressEvent(event)

    # --- painting ---------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        image_rect = QRectF(self.to_view(0, 0), self.to_view(self.img_w, self.img_h))
        p.drawPixmap(image_rect, self.pixmap, QRectF(self.pixmap.rect()))

        sel = self.view_rect()
        shade = QPainterPath()
        shade.addRect(image_rect)
        shade.addRect(sel)
        shade.setFillRule(Qt.FillRule.OddEvenFill)
        p.fillPath(shade, QColor(0, 0, 0, 130))

        # Rule-of-thirds guides.
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for i in (1, 2):
            x = sel.left() + sel.width() * i / 3
            y = sel.top() + sel.height() * i / 3
            p.drawLine(QPointF(x, sel.top()), QPointF(x, sel.bottom()))
            p.drawLine(QPointF(sel.left(), y), QPointF(sel.right(), y))

        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sel)
        if self.hasFocus():
            p.setPen(QPen(self.palette().highlight().color(), 1, Qt.PenStyle.DashLine))
            p.drawRect(sel.adjusted(-3, -3, 3, 3))

        p.setPen(QPen(QColor(40, 40, 40), 1))
        p.setBrush(QColor(255, 255, 255))
        for x, y in cg.handle_points(self.rect_img).values():
            p.drawEllipse(self.to_view(x, y), HANDLE_RADIUS, HANDLE_RADIUS)


ASPECTS: list[tuple[str, float | None]] = [
    ("Free", None), ("Original", -1.0), ("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 3 / 2),
    ("16:9", 16 / 9), ("3:4", 3 / 4), ("9:16", 9 / 16),
]


class CropDialog(QDialog):
    def __init__(self, preview: QPixmap, original_size: tuple[int, int], box: Box | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Crop")
        self.resize(820, 640)
        self.original_size = original_size
        self.crop = CropWidget(preview, original_size)
        self.crop.set_box(box)

        self.aspect = QComboBox()
        for label, _ in ASPECTS:
            self.aspect.addItem(label)
        self.aspect.setToolTip("Lock the aspect ratio")
        self.aspect.currentIndexChanged.connect(self._aspect_changed)
        self.size_label = QLabel()
        reset = QPushButton("Reset")
        reset.setToolTip("Select the whole image")
        reset.clicked.connect(self.reset)

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Aspect"))
        tools.addWidget(self.aspect)
        tools.addWidget(reset)
        tools.addStretch()
        tools.addWidget(self.size_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.crop, 1)
        layout.addWidget(QLabel("Drag the handles or the selection. Drag outside it to draw a new one."))
        layout.addWidget(buttons)

        self.crop.changed.connect(self._update_label)
        self._update_label()
        self.crop.setFocus()

    def _aspect_changed(self, index: int) -> None:
        ratio = ASPECTS[index][1]
        if ratio == -1.0:
            ratio = self.original_size[0] / self.original_size[1]
        self.crop.set_ratio(ratio)

    def reset(self) -> None:
        self.crop.set_box(None)
        self.crop.set_ratio(self.crop.ratio)

    def _update_label(self) -> None:
        left, top, right, bottom = self.crop.box()
        self.size_label.setText(f"{right - left} × {bottom - top} px")

    def box(self) -> Box | None:
        """The selection, or None if it covers the whole image (no crop)."""
        box = self.crop.box()
        return None if box == (0, 0, *self.original_size) else box
