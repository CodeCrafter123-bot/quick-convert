"""GUI bootstrap: single instance, tray, system-wide Shift+drag, crash logging."""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QPoint
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from app.integration import windows
from app.integration.single_instance import InstanceServer, send_to_running
from app.logging_setup import setup_logging
from app.storage.settings import UserSettings
from app.ui.drop_bubble import GlobalDragWatcher
from app.ui.icon import app_icon
from app.ui.main_window import MainWindow
from app.ui.tray import Tray

log = logging.getLogger("quickconvert")


class QuickConvertApp(QObject):
    """Owns the window, tray and integrations, and decides when the process really exits."""

    def __init__(self, qapp: QApplication, settings: UserSettings, settings_path: Path | None = None,
                 server_name: str | None = None, read_input=None):
        super().__init__()
        self.qapp = qapp
        self.settings = settings
        self.settings_path = settings_path
        self.window = MainWindow(settings)
        self.window.setWindowIcon(app_icon())

        self.server = InstanceServer(server_name, self)
        if not self.server.listen():
            log.warning("single-instance server unavailable: %s", self.server.server.errorString())
        self.server.open_requested.connect(self.window.open_file_with_wheel)
        self.server.show_requested.connect(self.window.bring_to_front)

        read_input = read_input or (windows.input_state if windows.IS_WINDOWS else None)
        self.watcher = GlobalDragWatcher(read_input, self) if read_input else None
        if self.watcher is not None:
            self.watcher.file_dropped.connect(self._on_bubble_drop)

        self.tray: Tray | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(app_icon(), self.watcher is not None, windows.IS_WINDOWS, self)
            self.tray.show_requested.connect(self.window.bring_to_front)
            self.tray.choose_requested.connect(self._choose_from_tray)
            self.tray.quit_requested.connect(self.quit)
            self.tray.global_drag_toggled.connect(self.set_global_drag)
            self.tray.send_to_toggled.connect(self.set_send_to)
            self.tray.set_checked(self.tray.send_to, windows.IS_WINDOWS and windows.is_send_to_installed())
            self.tray.show()
            self.window.hide_on_close = settings.close_to_tray
            self.window.hidden_to_tray.connect(self._on_hidden_to_tray)
            qapp.setQuitOnLastWindowClosed(False)

        self.set_global_drag(settings.global_drag and self.watcher is not None, save=False)

    # --- integrations ----------------------------------------------------------

    def set_global_drag(self, enabled: bool, save: bool = True) -> None:
        if self.watcher is None:
            return
        self.watcher.set_enabled(enabled)
        if self.tray is not None:
            self.tray.set_checked(self.tray.global_drag, enabled)
        if save:
            self.settings.global_drag = enabled
            self._save_settings()

    def set_send_to(self, enabled: bool) -> None:
        try:
            if enabled:
                windows.install_send_to()
            else:
                windows.uninstall_send_to()
        except OSError as exc:
            log.warning("Send to change failed: %s", exc)
            QMessageBox.warning(self.window, "Send to menu", str(exc))
        if self.tray is not None:
            self.tray.set_checked(self.tray.send_to, windows.is_send_to_installed())

    def _on_bubble_drop(self, path: Path, pos: QPoint) -> None:
        self.window.open_file_with_wheel(path, pos)

    def _choose_from_tray(self) -> None:
        self.window.bring_to_front()
        self.window.choose_file()

    def _on_hidden_to_tray(self) -> None:
        if self.tray is not None and not self.settings.tray_hint_shown:
            self.tray.notify("QuickConvert is still running",
                             "Shift+drag a file from any app, or use the tray icon. "
                             "Right-click the icon to quit.")
            self.settings.tray_hint_shown = True
            self._save_settings()

    def _save_settings(self) -> None:
        try:
            self.settings.save(self.settings_path)
        except OSError:
            log.exception("could not save settings")

    # --- lifecycle -----------------------------------------------------------------

    def quit(self) -> None:
        if not self.window.confirm_quit():
            return
        self.shutdown()
        self.qapp.quit()

    def shutdown(self) -> None:
        if self.watcher is not None:
            self.watcher.shutdown()
        if self.tray is not None:
            self.tray.hide()
        self.server.close()
        self.window.hide_on_close = False
        self.window.shutdown()


def _install_excepthook(log_path: Path | None) -> None:
    def hook(exc_type, exc, tb):
        log.critical("unhandled error", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            where = f"\n\nDetails were saved to:\n{log_path}" if log_path else ""
            QMessageBox.critical(None, "QuickConvert", f"Something went wrong.{where}")
        else:
            traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = hook


def run_gui(argv: list[str] | None = None, initial_file: Path | None = None) -> int:
    log_path = setup_logging()
    _install_excepthook(log_path)
    qapp = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    qapp.setApplicationName("QuickConvert")
    qapp.setOrganizationName("QuickConvert")
    qapp.setWindowIcon(app_icon())

    # Another instance already running (e.g. launched from "Send to"): hand over and exit.
    if send_to_running(initial_file):
        return 0

    app = QuickConvertApp(qapp, UserSettings.load())
    app.window.show()
    if initial_file is not None:
        app.window.open_file_with_wheel(initial_file)
    code = qapp.exec()
    app.shutdown()
    return code
