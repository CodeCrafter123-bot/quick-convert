"""Drag-and-drop helpers shared by every drop target.

Safety rule: a drop is only ever accepted as Copy (or Link). In Windows Explorer,
Shift+drag proposes *Move*; accepting that tells Explorer the file was moved, and
Explorer may then delete the original. QuickConvert never changes the source file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDropEvent, QGuiApplication

SAFE_ACTIONS = (Qt.DropAction.CopyAction, Qt.DropAction.LinkAction)


def single_local_file(event) -> Path | None:
    urls = event.mimeData().urls()
    if len(urls) == 1 and urls[0].isLocalFile():
        path = Path(urls[0].toLocalFile())
        if path.is_file():
            return path
    return None


def shift_held(event) -> bool:
    mods = event.modifiers() | QGuiApplication.queryKeyboardModifiers()
    return bool(mods & Qt.KeyboardModifier.ShiftModifier)


def accept_safely(event: QDropEvent) -> bool:
    """Accept as Copy/Link; refuse when the source only offers Move."""
    for action in SAFE_ACTIONS:
        if event.possibleActions() & action:
            event.setDropAction(action)
            event.accept()
            return True
    event.ignore()
    return False
