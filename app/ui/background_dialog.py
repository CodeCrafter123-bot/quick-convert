"""Add Background dialog: color, padding and corner radius with a live preview."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import limits
from app.models import BackgroundOptions, EditSpec
from app.services.editing import output_size, preview_edit
from app.ui.widgets import ColorButton, hex_color, pil_to_pixmap

PRESETS = [(255, 255, 255), (17, 17, 17), (241, 243, 245), (255, 236, 210),
           (214, 234, 248), (226, 240, 217), (106, 90, 205), (255, 99, 71)]
PREVIEW_BOX = 420


class BackgroundDialog(QDialog):
    def __init__(self, preview: Image.Image, original_size: tuple[int, int], spec: EditSpec,
                 parent: QWidget | None = None):
        """`spec` holds edits applied so far (e.g. a crop); its background is the starting value."""
        super().__init__(parent)
        self.setWindowTitle("Add background")
        self.preview_source = preview
        self.original_size = original_size
        self.crop_box = spec.crop_box
        start = spec.background or BackgroundOptions()

        self.color = ColorButton(start.color)
        swatches = QHBoxLayout()
        swatches.setSpacing(4)
        for color in PRESETS:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setToolTip(hex_color(color))
            btn.setAccessibleName(f"Preset color {hex_color(color)}")
            btn.setStyleSheet(f"background:{hex_color(color)}; border:1px solid palette(mid);"
                              "border-radius:4px;")
            btn.clicked.connect(lambda _=False, c=color: self.color.set_color(c))
            swatches.addWidget(btn)
        swatches.addStretch()

        self.padding = QSpinBox(minimum=0, maximum=limits.MAX_PADDING, value=start.padding,
                                suffix=" px", singleStep=8)
        self.radius = QSpinBox(minimum=0, maximum=limits.MAX_PADDING, value=start.radius,
                               suffix=" px", singleStep=4)
        self.radius.setToolTip("Rounds the corners of the image itself")

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(PREVIEW_BOX, PREVIEW_BOX)
        self.preview.setStyleSheet("background: palette(base); border: 1px solid palette(mid);")
        self.size_label = QLabel()

        form = QFormLayout()
        form.addRow("Color", self.color)
        form.addRow("", swatches)
        form.addRow("Padding", self.padding)
        form.addRow("Corner radius", self.radius)
        form.addRow("Result size", self.size_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, 1)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.color.color_changed.connect(self._refresh)
        self.padding.valueChanged.connect(self._refresh)
        self.radius.valueChanged.connect(self._refresh)
        self._refresh()

    def options(self) -> BackgroundOptions:
        return BackgroundOptions(self.color.color, self.padding.value(), self.radius.value())

    def spec(self) -> EditSpec:
        return EditSpec(self.crop_box, self.options())

    def _refresh(self, *_) -> None:
        spec = self.spec()
        im = preview_edit(self.preview_source, self.original_size, spec)
        im.thumbnail((PREVIEW_BOX, PREVIEW_BOX))
        self.preview.setPixmap(pil_to_pixmap(im))
        width, height = output_size(*self.original_size, spec)
        self.size_label.setText(f"{width} × {height} px")
