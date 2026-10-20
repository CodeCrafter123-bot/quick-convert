"""Local diagnostic log: technical details only, never file contents."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or Path.home() / ".cache"
    return Path(base) / "QuickConvert" / "logs"


def setup_logging() -> Path | None:
    """Log to a small rotating file; returns its path (None if the folder isn't writable)."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stderr is not None:  # pythonw has no console
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "quickconvert.log"
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(fmt)
    root.addHandler(handler)
    return path
