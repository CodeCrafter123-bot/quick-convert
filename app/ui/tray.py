"""Tray icon: always-available import, plus the system-integration switches."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QObject):
    show_requested = Signal()
    choose_requested = Signal()
    quit_requested = Signal()
    global_drag_toggled = Signal(bool)
    send_to_toggled = Signal(bool)

    def __init__(self, icon: QIcon, global_drag_available: bool, send_to_available: bool,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(icon, self)
        self.icon.setToolTip("QuickConvert")
        menu = QMenu()
        menu.addAction("Open QuickConvert").triggered.connect(self.show_requested)
        menu.addAction("Choose File…").triggered.connect(self.choose_requested)
        menu.addSeparator()

        self.global_drag = QAction("Shift+drag from any app", menu, checkable=True)
        self.global_drag.setEnabled(global_drag_available)
        self.global_drag.setToolTip("Hold Shift while dragging a file anywhere to show a drop bubble")
        self.global_drag.toggled.connect(self.global_drag_toggled)
        menu.addAction(self.global_drag)

        self.send_to = QAction("Add to Explorer \"Send to\" menu", menu, checkable=True)
        self.send_to.setEnabled(send_to_available)
        self.send_to.toggled.connect(self.send_to_toggled)
        menu.addAction(self.send_to)

        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self.quit_requested)
        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_requested.emit()

    def set_checked(self, action: QAction, checked: bool) -> None:
        """Update a checkbox without re-emitting its toggled signal."""
        action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(False)

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def notify(self, title: str, message: str) -> None:
        self.icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
