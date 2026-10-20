"""Shows only the options that apply to the chosen conversion, plus where to save."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from app import limits
from app.models import (
    Capability,
    ConversionOptions,
    ConversionRequest,
    EditSpec,
    FileInfo,
    FileType,
)
from app.services.editing import EDIT_TARGETS
from app.services.output import default_output_path
from app.storage.settings import UserSettings
from app.ui.widgets import FORMAT_NAMES, ColorButton, DestinationField, confirm_overwrite

__all__ = ["FORMAT_NAMES", "ExportDialog", "OptionsDialog"]


def _default_dir(settings: UserSettings) -> Path | None:
    out_dir = Path(settings.default_output_dir) if settings.default_output_dir else None
    return out_dir if out_dir is not None and out_dir.is_dir() else None


def _buttons(dialog: QDialog, ok_text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


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

        self.destination = DestinationField(
            default_output_path(info.path, target.extension, _default_dir(settings)), target)
        form.addRow("Save as", self.destination)
        form.addRow(_buttons(self, "Convert"))

    def accept(self) -> None:
        replace = confirm_overwrite(self, self.destination.path())
        if replace is False:
            return
        self.overwrite = bool(replace)
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
        return ConversionRequest(self.info.path, self.cap.output_type, self.destination.path(),
                                 options, self.overwrite)


class ExportDialog(QDialog):
    """Save the edited image: pick a format, quality and destination."""

    def __init__(self, info: FileInfo, spec: EditSpec, settings: UserSettings,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.info, self.spec = info, spec
        self.overwrite = False
        self.setWindowTitle("Export edited image")
        self.setMinimumWidth(460)
        form = QFormLayout(self)

        self.format = QComboBox()
        for target in EDIT_TARGETS:
            self.format.addItem(FORMAT_NAMES[target], target)
        # Keep the source format by default, PNG for PDFs or anything else.
        start = info.file_type if info.file_type in EDIT_TARGETS else FileType.PNG
        self.format.setCurrentIndex(EDIT_TARGETS.index(start))
        form.addRow("Format", self.format)

        self.quality = QSpinBox(minimum=1, maximum=100, value=settings.default_quality)
        form.addRow("Quality", self.quality)

        self.destination = DestinationField(
            default_output_path(info.path, start.extension, _default_dir(settings), suffix="-edited"),
            start)
        form.addRow("Save as", self.destination)
        form.addRow(_buttons(self, "Export"))

        self.format.currentIndexChanged.connect(self._format_changed)
        self._format_changed()

    def target(self) -> FileType:
        # Index, not currentData(): Qt converts the str-enum to a plain str.
        return EDIT_TARGETS[self.format.currentIndex()]

    def _format_changed(self) -> None:
        target = self.target()
        self.quality.setEnabled(target in (FileType.JPEG, FileType.WEBP))
        self.destination.set_target(target)

    def accept(self) -> None:
        replace = confirm_overwrite(self, self.destination.path())
        if replace is False:
            return
        self.overwrite = bool(replace)
        super().accept()

    def request(self) -> ConversionRequest:
        target = self.target()
        quality = self.quality.value() if self.quality.isEnabled() else None
        return ConversionRequest(self.info.path, target, self.destination.path(),
                                 ConversionOptions(quality=quality), self.overwrite, edit=self.spec)
