"""Shows only the options that apply to the chosen conversion, plus where to save."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from app import limits
from app.models import (
    Capability,
    ConversionOptions,
    ConversionRequest,
    FileInfo,
    FileType,
)
from app.services.output import default_output_path
from app.storage.settings import UserSettings

FORMAT_NAMES = {FileType.JPEG: "JPEG", FileType.PNG: "PNG", FileType.WEBP: "WebP",
                FileType.PDF: "PDF"}


class ColorButton(QPushButton):
    def __init__(self, color: tuple[int, int, int], parent: QWidget | None = None):
        super().__init__(parent)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: tuple[int, int, int]) -> None:
        self.color = color
        hex_color = "#{:02x}{:02x}{:02x}".format(*color)
        self.setText(hex_color)
        fg = "#000" if sum(color) > 380 else "#fff"
        self.setStyleSheet(f"background:{hex_color}; color:{fg}; padding:4px 12px;")

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(*self.color), self, "Background color")
        if chosen.isValid():
            self.set_color((chosen.red(), chosen.green(), chosen.blue()))


class OptionsDialog(QDialog):
    def __init__(self, info: FileInfo, cap: Capability, settings: UserSettings,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.info, self.cap, self.settings = info, cap, settings
        self.overwrite = False
        target = cap.output_type
        self.setWindowTitle(f"Convert to {FORMAT_NAMES[target]}")
        self.setMinimumWidth(460)

        form = QFormLayout(self)
        opts = cap.supported_options

        self.page = self.quality = self.dpi = self.password = None
        self.background = self.keep_metadata = None

        if "pdf_page" in opts:
            self.page = QSpinBox(minimum=1, maximum=info.page_count or 9999, value=1)
            label = f"Page (of {info.page_count})" if info.page_count else "Page"
            form.addRow(label, self.page)
        if "password" in opts and info.encrypted:
            self.password = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
            self.password.setPlaceholderText("This PDF is password protected")
            form.addRow("Password", self.password)
        if "dpi" in opts:
            self.dpi = QSpinBox(minimum=36, maximum=limits.MAX_DPI, value=limits.DEFAULT_DPI,
                                singleStep=24, suffix=" DPI")
            self.dpi.setToolTip("PDF → image: output resolution.\n"
                                "Image → PDF: sets the printed page size.")
            form.addRow("Resolution", self.dpi)
        if "quality" in opts:
            self.quality = QSpinBox(minimum=1, maximum=100, value=settings.default_quality)
            form.addRow("Quality", self.quality)
        if "background_color" in opts:
            self.background = ColorButton(limits.DEFAULT_BACKGROUND)
            self.background.setToolTip("JPEG has no transparency; transparent areas get this color.")
            form.addRow("Fill transparency", self.background)
        if "keep_metadata" in opts:
            self.keep_metadata = QCheckBox("Keep metadata (EXIF)")
            self.keep_metadata.setChecked(settings.metadata_policy == "keep")
            form.addRow("", self.keep_metadata)

        out_dir = Path(settings.default_output_dir) if settings.default_output_dir else None
        if out_dir is not None and not out_dir.is_dir():
            out_dir = None
        self.destination = QLineEdit(str(default_output_path(info.path, target.extension, out_dir)))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.destination, 1)
        row.addWidget(browse)
        form.addRow("Save as", row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Convert")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self) -> None:
        ext = self.cap.output_type.extension
        name = FORMAT_NAMES[self.cap.output_type]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as", self.destination.text(), f"{name} (*{ext})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.destination.setText(path)

    def accept(self) -> None:
        dest = Path(self.destination.text().strip())
        if not dest.suffix:
            dest = dest.with_suffix(self.cap.output_type.extension)
            self.destination.setText(str(dest))
        if dest.exists():
            answer = QMessageBox.question(
                self, "Replace file?",
                f"'{dest.name}' already exists.\nDo you want to replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.overwrite = True
        super().accept()

    def request(self) -> ConversionRequest:
        options = ConversionOptions(
            quality=self.quality.value() if self.quality else None,
            dpi=self.dpi.value() if self.dpi else None,
            pdf_page=self.page.value() if self.page else None,
            password=(self.password.text() or None) if self.password else None,
            background_color=self.background.color if self.background else None,
            keep_metadata=bool(self.keep_metadata and self.keep_metadata.isChecked()),
        )
        return ConversionRequest(self.info.path, self.cap.output_type,
                                 Path(self.destination.text().strip()), options, self.overwrite)
