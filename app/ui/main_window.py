"""Main window: drop zone, file details, action wheel, pending edits, and the job list."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models import (
    Capability,
    ConversionJob,
    ConversionRequest,
    EditSpec,
    FileInfo,
    FileType,
    QuickConvertError,
)
from app.services.capabilities import get_targets
from app.services.editing import output_size, preview_edit
from app.services.inspection import inspect_file
from app.services.jobs import JobManager
from app.storage.settings import UserSettings
from app.ui.background_dialog import BackgroundDialog
from app.ui.crop_dialog import CropDialog
from app.ui.dnd import accept_safely, shift_held, single_local_file
from app.ui.job_row import JobRow
from app.ui.options_dialog import FORMAT_NAMES, ExportDialog, OptionsDialog
from app.ui.radial_menu import RadialItem, RadialMenu
from app.ui.widgets import hex_color, pil_to_pixmap

THUMB_SIZE = 160
PREVIEW_MAX = 1600  # downscaled working copy for previews; exports always use the source
ACTION_CROP = "crop"
ACTION_BACKGROUND = "background"


class DropZone(QFrame):
    """Accepts one local file. Holding Shift on drop opens the radial menu right there."""

    file_dropped = Signal(Path, bool, QPoint)  # path, shift held, global drop position
    choose_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("DropZone")
        self.setMinimumHeight(150)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        choose = QPushButton("Choose File…")
        choose.clicked.connect(self.choose_requested)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addWidget(choose, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self._set_hint(False)

    def _set_hint(self, active: bool, shift: bool = False) -> None:
        if not active:
            self.label.setText("Drop an image or PDF here\n"
                               "Hold Shift while dropping to open the action wheel")
        elif shift:
            self.label.setText("Release to open the action wheel")
        else:
            self.label.setText("Release to open the file (hold Shift for the wheel)")
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if single_local_file(event) and accept_safely(event):
            self._set_hint(True, shift_held(event))
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if accept_safely(event):
            self._set_hint(True, shift_held(event))

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_hint(False)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_hint(False)
        path = single_local_file(event)
        if path is None or not accept_safely(event):
            event.ignore()
            return
        global_pos = self.mapToGlobal(event.position().toPoint())
        self.file_dropped.emit(path, shift_held(event), global_pos)


class JobSignals(QObject):
    """Carries JobManager updates from worker threads to the GUI thread."""

    updated = Signal(object)


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self, settings: UserSettings | None = None) -> None:
        super().__init__()
        self.hide_on_close = False  # set by the app when the tray icon is running
        self.setWindowTitle("QuickConvert")
        self.resize(660, 660)
        self.settings = settings or UserSettings.load()
        self.info: FileInfo | None = None
        self.preview_image: Image.Image | None = None
        self.edit = EditSpec()
        self.rows: dict[str, JobRow] = {}

        self.signals = JobSignals()
        self.signals.updated.connect(self._on_job_update)
        self.jobs = JobManager(on_update=self.signals.updated.emit)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._on_drop)
        self.drop_zone.choose_requested.connect(self.choose_file)

        # File details
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details = QLabel()
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setWordWrap(True)
        self.wheel_btn = QPushButton("Actions…")
        self.wheel_btn.setToolTip("Open the action wheel (Ctrl+K)")
        self.wheel_btn.clicked.connect(self._open_wheel_at_button)
        self.menu_btn = QToolButton()
        self.menu_btn.setText("Menu")
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip("List menu alternative to the wheel")
        self.menu_btn.setMenu(QMenu(self.menu_btn))

        # Pending edits bar (shown once a crop or background is applied)
        self.edits_label = QLabel()
        self.edits_label.setWordWrap(True)
        self.export_btn = QPushButton("Export…")
        self.export_btn.setToolTip("Save the edited image as a new file")
        self.export_btn.clicked.connect(self.export_edits)
        self.discard_btn = QPushButton("Discard edits")
        self.discard_btn.clicked.connect(self.discard_edits)
        self.edits_bar = QFrame()
        self.edits_bar.setObjectName("EditsBar")
        edits_layout = QVBoxLayout(self.edits_bar)
        edits_layout.setContentsMargins(8, 6, 8, 6)
        edits_layout.addWidget(self.edits_label)
        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(self.export_btn)
        edit_buttons.addWidget(self.discard_btn)
        edit_buttons.addStretch()
        edits_layout.addLayout(edit_buttons)
        self.edits_bar.hide()

        buttons = QHBoxLayout()
        buttons.addWidget(self.wheel_btn)
        buttons.addWidget(self.menu_btn)
        buttons.addStretch()
        info_col = QVBoxLayout()
        info_col.addWidget(self.details)
        info_col.addLayout(buttons)
        info_col.addWidget(self.edits_bar)
        info_col.addStretch()
        self.file_panel = QWidget()
        file_layout = QHBoxLayout(self.file_panel)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self.thumb)
        file_layout.addLayout(info_col, 1)
        self.file_panel.hide()

        # Jobs
        self.jobs_box = QVBoxLayout()
        self.jobs_box.addStretch()
        jobs_host = QWidget()
        jobs_host.setLayout(self.jobs_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(jobs_host)
        jobs_title = QLabel("<b>Jobs</b>")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.drop_zone)
        layout.addWidget(self.file_panel)
        layout.addWidget(jobs_title)
        layout.addWidget(scroll, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(
            "#DropZone { border: 2px dashed palette(mid); border-radius: 10px; }"
            "#DropZone[active=\"true\"] { border-color: palette(highlight); }"
            "#EditsBar { border: 1px solid palette(highlight); border-radius: 6px; }"
        )

        open_action = QAction("Open…", self, shortcut=QKeySequence.StandardKey.Open,
                              triggered=self.choose_file)
        wheel_action = QAction("Action wheel", self, shortcut=QKeySequence("Ctrl+K"),
                               triggered=self._open_wheel_at_cursor)
        self.addActions([open_action, wheel_action])
        self.statusBar().showMessage("Files are processed locally on this computer.")

    # --- loading -------------------------------------------------------------

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a file", "", "Images and PDFs (*.jpg *.jpeg *.png *.webp *.pdf);;All files (*)")
        if path:
            self.load_file(Path(path))

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_file_with_wheel(self, path: Path, global_pos: QPoint | None = None) -> None:
        """Entry point for drops from outside the window (bubble, Send to, second instance)."""
        self.bring_to_front()
        if self.load_file(path):
            self.open_wheel(global_pos or QCursor.pos())

    def _on_drop(self, path: Path, shift: bool, global_pos: QPoint) -> None:
        if self.load_file(path) and shift:
            self.open_wheel(global_pos)

    def load_file(self, path: Path) -> bool:
        try:
            info = inspect_file(path)
            preview = self._load_preview(info)
        except QuickConvertError as exc:
            QMessageBox.warning(self, "Cannot open file", exc.message)
            return False
        self.info = info
        self.preview_image = preview
        self.edit = EditSpec()
        self._show_details(info)
        self._rebuild_list_menu()
        self._refresh_edits()
        self.file_panel.show()
        return True

    @staticmethod
    def _load_preview(info: FileInfo) -> Image.Image | None:
        """Orientation-corrected, downscaled working copy used for every preview."""
        if info.file_type is FileType.PDF:
            if info.encrypted:
                return None
            from app.adapters.pdf import render_page

            return render_page(info.path, page=1, dpi=36)
        from app.adapters.image import load_image

        im = load_image(info.path)
        im.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
        return im

    def _show_details(self, info: FileInfo) -> None:
        parts = [f"<b>{info.path.name}</b>",
                 f"{FORMAT_NAMES[info.file_type]} · {info.size_bytes / 1024:,.0f} KB"]
        if info.width:
            parts.append(f"{info.width} × {info.height} px")
        if info.file_type is FileType.PDF:
            parts.append("Password protected" if info.encrypted else f"{info.page_count} page(s)")
        self.details.setText("<br>".join(parts))

    def _update_thumbnail(self) -> None:
        if self.preview_image is None or self.info is None:
            self.thumb.setPixmap(QPixmap())
            return
        im = self.preview_image
        if not self.edit.is_empty:
            im = preview_edit(im, (self.info.width, self.info.height), self.edit)
        im = im.copy()
        im.thumbnail((THUMB_SIZE, THUMB_SIZE))
        self.thumb.setPixmap(pil_to_pixmap(im))

    # --- choosing an action ---------------------------------------------------

    def targets(self) -> list[Capability]:
        return get_targets(self.info) if self.info else []

    def can_edit(self) -> bool:
        return self.info is not None and self.info.file_type.is_image

    def wheel_items(self) -> list[RadialItem]:
        items = [RadialItem(FORMAT_NAMES[c.output_type], c, c.available, c.unavailable_reason or "")
                 for c in self.targets()]
        if self.can_edit():
            items += [RadialItem("Crop", ACTION_CROP, tooltip="Crop the image"),
                      RadialItem("Background", ACTION_BACKGROUND,
                                 tooltip="Add a colored background with padding")]
        return items

    def _rebuild_list_menu(self) -> None:
        menu = self.menu_btn.menu()
        menu.clear()
        for cap in self.targets():
            action = menu.addAction(f"Convert to {FORMAT_NAMES[cap.output_type]}…")
            action.setEnabled(cap.available)
            if cap.unavailable_reason:
                action.setToolTip(cap.unavailable_reason)
            action.triggered.connect(lambda _=False, c=cap: self.run_action(c))
        if self.can_edit():
            menu.addSeparator()
            menu.addAction("Crop…").triggered.connect(lambda: self.run_action(ACTION_CROP))
            menu.addAction("Add Background…").triggered.connect(
                lambda: self.run_action(ACTION_BACKGROUND))

    def run_action(self, data: Capability | str) -> None:
        if data == ACTION_CROP:
            self.crop_image()
        elif data == ACTION_BACKGROUND:
            self.add_background()
        else:
            self.start_conversion(data)

    def open_wheel(self, global_center: QPoint) -> RadialMenu | None:
        if self.info is None:
            return None
        wheel = RadialMenu(self.wheel_items(), self.info.path.name, self)
        wheel.triggered.connect(self.run_action)
        wheel.popup_at(global_center)
        return wheel

    def _open_wheel_at_button(self) -> None:
        self.open_wheel(self.wheel_btn.mapToGlobal(self.wheel_btn.rect().center()))

    def _open_wheel_at_cursor(self) -> None:
        if self.info is None:
            self.choose_file()
            return
        self.open_wheel(QCursor.pos())

    # --- editing ---------------------------------------------------------------

    def crop_image(self) -> None:
        if not self.can_edit() or self.preview_image is None:
            return
        size = (self.info.width, self.info.height)
        dialog = CropDialog(pil_to_pixmap(self.preview_image), size, self.edit.crop_box, self)
        if dialog.exec() == CropDialog.DialogCode.Accepted:
            self.set_edit(EditSpec(dialog.box(), self.edit.background))

    def add_background(self) -> None:
        if not self.can_edit() or self.preview_image is None:
            return
        size = (self.info.width, self.info.height)
        dialog = BackgroundDialog(self.preview_image, size, self.edit, self)
        if dialog.exec() == BackgroundDialog.DialogCode.Accepted:
            self.set_edit(dialog.spec())

    def set_edit(self, spec: EditSpec) -> None:
        self.edit = spec
        self._refresh_edits()

    def discard_edits(self) -> None:
        self.set_edit(EditSpec())

    def _refresh_edits(self) -> None:
        self._update_thumbnail()
        if self.edit.is_empty or self.info is None:
            self.edits_bar.hide()
            return
        parts = []
        if self.edit.crop_box is not None:
            left, top, right, bottom = self.edit.crop_box
            parts.append(f"Crop {right - left} × {bottom - top}")
        if self.edit.background is not None:
            bg = self.edit.background
            parts.append(f"Background {hex_color(bg.color)}, {bg.padding} px"
                         + (f", radius {bg.radius}" if bg.radius else ""))
        width, height = output_size(self.info.width, self.info.height, self.edit)
        self.edits_label.setText(f"<b>Edits:</b> {' · '.join(parts)}<br>"
                                 f"Result {width} × {height} px · original unchanged")
        self.edits_bar.show()

    def export_edits(self) -> None:
        if self.info is None or self.edit.is_empty:
            return
        dialog = ExportDialog(self.info, self.edit, self.settings, self)
        if dialog.exec() == ExportDialog.DialogCode.Accepted:
            self.submit(dialog.request())

    # --- running jobs ---------------------------------------------------------

    def start_conversion(self, cap: Capability) -> None:
        if self.info is None:
            return
        try:  # the file may have changed since it was loaded
            self.info = inspect_file(self.info.path)
        except QuickConvertError as exc:
            QMessageBox.warning(self, "Cannot convert", exc.message)
            return
        dialog = OptionsDialog(self.info, cap, self.settings, self)
        if dialog.exec() != OptionsDialog.DialogCode.Accepted:
            return
        self.submit(dialog.request())

    def submit(self, request: ConversionRequest) -> str | None:
        try:
            return self.jobs.submit(request)
        except QuickConvertError as exc:
            QMessageBox.warning(self, "Cannot convert", exc.message)
            return None

    def _on_job_update(self, job: ConversionJob) -> None:
        row = self.rows.get(job.id)
        if row is None:
            row = JobRow(job)
            row.cancel_requested.connect(self.jobs.cancel)
            self.rows[job.id] = row
            self.jobs_box.insertWidget(0, row)
        else:
            row.update_job(job)

    # --- closing --------------------------------------------------------------

    def confirm_quit(self) -> bool:
        """Ask before cancelling running jobs. True if it's OK to quit."""
        active = self.jobs.active_count()
        if not active:
            return True
        answer = QMessageBox.question(
            self, "Jobs still running",
            f"{active} job(s) are still running. Cancel them and quit?\n"
            "Unfinished outputs are removed; your originals are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def shutdown(self) -> None:
        self.jobs.shutdown()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.hide_on_close:
            event.ignore()
            self.hide()
            self.hidden_to_tray.emit()
            return
        if not self.confirm_quit():
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)
