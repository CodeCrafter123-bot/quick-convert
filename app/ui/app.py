"""GUI bootstrap."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def run_gui(argv: list[str] | None = None, initial_file: Path | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("QuickConvert")
    app.setOrganizationName("QuickConvert")
    window = MainWindow()
    window.show()
    if initial_file is not None:
        window.load_file(initial_file)
    return app.exec()
