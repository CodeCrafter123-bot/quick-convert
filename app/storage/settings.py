"""UserSettings persisted as JSON in %APPDATA%\\QuickConvert (no database for the MVP)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app import limits

log = logging.getLogger("quickconvert.settings")


def settings_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "QuickConvert"


@dataclass
class UserSettings:
    default_output_dir: str | None = None  # None = next to the source file
    default_quality: int = limits.DEFAULT_QUALITY
    metadata_policy: str = "strip"  # "strip" | "keep"
    theme: str = "system"
    global_drag: bool = True  # Shift+drag bubble from any app (Windows)
    close_to_tray: bool = True
    tray_hint_shown: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> UserSettings:
        path = path or settings_dir() / "settings.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.warning("settings file unreadable; using defaults")
            return cls()
        known = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in data.items() if k in known})
        except TypeError:
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, path)
