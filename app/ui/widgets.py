"""Small widgets and helpers shared by the dialogs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from app.models import Color, FileType

FORMAT_NAMES = {FileType.JPEG: "JPEG", FileType.PNG: "PNG", FileType.WEBP: "WebP",
                FileType.PDF: "PDF"}


def pil_to_qimage(im: Image.Image) -> QImage:
    rgba = im.convert("RGBA")
    qimg = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888)
    return qimg.copy()  # detach from the Python buffer


def pil_to_pixmap(im: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(im))


def hex_color(color: Color) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


class ColorButton(QPushButton):
    color_changed = Signal(tuple)

    def __init__(self, color: Color, parent: QWidget | None = None):
        super().__init__(parent)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: Color) -> None:
        self.color = tuple(color)
        fg = "#000" if sum(color) > 380 else "#fff"
        self.setText(hex_color(color))
        self.setAccessibleName(f"Color {hex_color(color)}")
        self.setStyleSheet(f"background:{hex_color(color)}; color:{fg}; padding:4px 12px;")
        self.color_changed.emit(self.color)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(*self.color), self, "Background color")
        if chosen.isValid():
            self.set_color((chosen.red(), chosen.green(), chosen.blue()))


class DestinationField(QWidget):
    """Path box + Browse…, with the target extension enforced on accept."""

    def __init__(self, path: Path, target: FileType, parent: QWidget | None = None):
        super().__init__(parent)
        self.target = target
        self.edit = QLineEdit(str(path))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)

    def set_target(self, target: FileType) -> None:
        """Swap the extension when the user picks a different output format."""
        self.target = target
        current = Path(self.edit.text().strip())
        if current.name:
            self.edit.setText(str(current.with_suffix(target.extension)))

    def path(self) -> Path:
        path = Path(self.edit.text().strip())
        if not path.suffix:
            path = path.with_suffix(self.target.extension)
            self.edit.setText(str(path))
        return path

    def _browse(self) -> None:
        ext = self.target.extension
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as", self.edit.text(), f"{FORMAT_NAMES[self.target]} (*{ext})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.edit.setText(path)


def confirm_overwrite(parent: QWidget, path: Path) -> bool | None:
    """None: path is free. True: user agreed to replace. False: user declined."""
    if not path.exists():
        return None
    answer = QMessageBox.question(
        parent, "Replace file?", f"'{path.name}' already exists.\nDo you want to replace it?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
