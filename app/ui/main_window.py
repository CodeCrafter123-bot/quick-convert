"""Main window: drop zone, file details, radial menu, and the job list."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QGuiApplication,
    QImage,
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

from app.models import Capability, ConversionJob, ConversionRequest, FileInfo, FileType, QuickConvertError
from app.services.capabilities import get_targets
from app.services.inspection import inspect_file
from app.services.jobs import JobManager
from app.storage.settings import UserSettings
from app.ui.job_row import JobRow
from app.ui.options_dialog import FORMAT_NAMES, OptionsDialog
from app.ui.radial_menu import RadialItem, RadialMenu

THUMB_SIZE = 160


def _single_local_file(event) -> Path | None:
    urls = event.mimeData().urls()
    if len(urls) == 1 and urls[0].isLocalFile():
        path = Path(urls[0].toLocalFile())
        if path.is_file():
            return path
    return None


def _shift_held(event) -> bool:
    mods = event.modifiers() | QGuiApplication.queryKeyboardModifiers()
    return bool(mods & Qt.KeyboardModifier.ShiftModifier)


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
                               "Hold Shift while dropping to open the conversion menu")
        elif shift:
            self.label.setText("Release to open the conversion menu")
        else:
            self.label.setText("Release to open the file (hold Shift for the menu)")
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if _single_local_file(event):
            event.acceptProposedAction()
            self._set_hint(True, _shift_held(event))
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        event.acceptProposedAction()
        self._set_hint(True, _shift_held(event))

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_hint(False)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_hint(False)
        path = _single_local_file(event)
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        global_pos = self.mapToGlobal(event.position().toPoint())
        self.file_dropped.emit(path, _shift_held(event), global_pos)


class JobSignals(QObject):
    """Carries JobManager updates from worker threads to the GUI thread."""

    updated = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self, settings: UserSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("QuickConvert")
        self.resize(640, 620)
        self.settings = settings or UserSettings.load()
        self.info: FileInfo | None = None
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
        self.wheel_btn = QPushButton("Convert…")
        self.wheel_btn.setToolTip("Open the conversion wheel (Ctrl+K)")
        self.wheel_btn.clicked.connect(self._open_wheel_at_button)
        self.menu_btn = QToolButton()
        self.menu_btn.setText("Convert to")
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip("List menu alternative to the wheel")
        self.menu_btn.setMenu(QMenu(self.menu_btn))

        buttons = QHBoxLayout()
        buttons.addWidget(self.wheel_btn)
        buttons.addWidget(self.menu_btn)
        buttons.addStretch()
        info_col = QVBoxLayout()
        info_col.addWidget(self.details)
        info_col.addLayout(buttons)
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
        )

        open_action = QAction("Open…", self, shortcut=QKeySequence.StandardKey.Open,
                              triggered=self.choose_file)
        wheel_action = QAction("Conversion wheel", self, shortcut=QKeySequence("Ctrl+K"),
                               triggered=self._open_wheel_at_cursor)
        self.addActions([open_action, wheel_action])
        self.statusBar().showMessage("Files are processed locally on this computer.")

    # --- loading -------------------------------------------------------------

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a file", "", "Images and PDFs (*.jpg *.jpeg *.png *.webp *.pdf);;All files (*)")
        if path:
            self.load_file(Path(path))

    def _on_drop(self, path: Path, shift: bool, global_pos: QPoint) -> None:
        if self.load_file(path) and shift:
            self.open_wheel(global_pos)

    def load_file(self, path: Path) -> bool:
        try:
            info = inspect_file(path)
        except QuickConvertError as exc:
            QMessageBox.warning(self, "Cannot open file", exc.message)
            return False
        self.info = info
        self._show_details(info)
        self._rebuild_list_menu()
        self.file_panel.show()
        return True

    def _show_details(self, info: FileInfo) -> None:
        parts = [f"<b>{info.path.name}</b>",
                 f"{FORMAT_NAMES[info.file_type]} · {info.size_bytes / 1024:,.0f} KB"]
        if info.width:
            parts.append(f"{info.width} × {info.height} px")
        if info.file_type is FileType.PDF:
            parts.append("Password protected" if info.encrypted else f"{info.page_count} page(s)")
        self.details.setText("<br>".join(parts))
        self.thumb.setPixmap(self._thumbnail(info))

    def _thumbnail(self, info: FileInfo) -> QPixmap:
        pixmap = QPixmap()
        try:
            if info.file_type is FileType.PDF:
                if info.encrypted:
                    return pixmap
                from app.adapters.pdf import render_page

                im = render_page(info.path, page=1, dpi=36).convert("RGBA")
                qimg = QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimg.copy())
            else:
                pixmap = QPixmap(str(info.path))
        except QuickConvertError:
            return QPixmap()
        if pixmap.isNull():
            return pixmap
        return pixmap.scaled(THUMB_SIZE, THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    # --- choosing an action ---------------------------------------------------

    def targets(self) -> list[Capability]:
        return get_targets(self.info) if self.info else []

    def wheel_items(self) -> list[RadialItem]:
        return [RadialItem(FORMAT_NAMES[c.output_type], c, c.available, c.unavailable_reason or "")
                for c in self.targets()]

    def _rebuild_list_menu(self) -> None:
        menu = self.menu_btn.menu()
        menu.clear()
        for cap in self.targets():
            action = menu.addAction(FORMAT_NAMES[cap.output_type])
            action.setEnabled(cap.available)
            if cap.unavailable_reason:
                action.setToolTip(cap.unavailable_reason)
            action.triggered.connect(lambda _=False, c=cap: self.start_conversion(c))

    def open_wheel(self, global_center: QPoint) -> RadialMenu | None:
        if self.info is None:
            return None
        wheel = RadialMenu(self.wheel_items(), self.info.path.name, self)
        wheel.triggered.connect(self.start_conversion)
        wheel.popup_at(global_center)
        return wheel

    def _open_wheel_at_button(self) -> None:
        self.open_wheel(self.wheel_btn.mapToGlobal(self.wheel_btn.rect().center()))

    def _open_wheel_at_cursor(self) -> None:
        if self.info is None:
            self.choose_file()
            return
        from PySide6.QtGui import QCursor

        self.open_wheel(QCursor.pos())

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

    def closeEvent(self, event) -> None:  # noqa: N802
        self.jobs.shutdown()
        super().closeEvent(event)
