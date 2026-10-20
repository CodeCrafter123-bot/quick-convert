"""Output naming and atomic, non-overwriting saves."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from app.models import ErrorCode, QuickConvertError

_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM\d|LPT\d)$", re.IGNORECASE)
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

TEMP_PREFIX = ".qc-tmp-"


def sanitize_stem(stem: str) -> str:
    stem = _INVALID_CHARS.sub("_", stem).strip(" .")
    if not stem or _WINDOWS_RESERVED.match(stem):
        stem = f"_{stem}" if stem else "output"
    return stem[:200]


def default_output_path(source: Path, extension: str, directory: Path | None = None,
                        suffix: str = "") -> Path:
    directory = directory or source.parent
    return unique_path(directory / f"{sanitize_stem(source.stem + suffix)}{extension}")


def unique_path(path: Path) -> Path:
    """Return path, or 'name (2).ext', 'name (3).ext', ... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


@contextmanager
def atomic_output(destination: Path, overwrite: bool = False,
                  verify: Callable[[Path], None] | None = None) -> Iterator[Path]:
    """Yield a temp path in the destination directory; on success verify and move it into place.

    The temp file is always removed on failure or cancellation, so no partial
    output is left behind.
    """
    destination = Path(destination)
    if destination.exists() and not overwrite:
        raise QuickConvertError(ErrorCode.OUTPUT_EXISTS, f"'{destination.name}' already exists.")
    directory = destination.parent
    if not directory.is_dir():
        raise QuickConvertError(ErrorCode.PERMISSION_DENIED, f"Folder '{directory}' does not exist.")

    tmp = directory / f"{TEMP_PREFIX}{uuid.uuid4().hex[:12]}{destination.suffix}"
    try:
        try:
            yield tmp
            if verify is not None:
                verify(tmp)
            if overwrite:
                os.replace(tmp, destination)
            else:
                # os.rename refuses to replace an existing file on Windows, which
                # protects against a file created while the job was running.
                os.rename(tmp, destination)
        except FileExistsError:
            raise QuickConvertError(ErrorCode.OUTPUT_EXISTS, f"'{destination.name}' already exists.")
        except PermissionError:
            raise QuickConvertError(
                ErrorCode.PERMISSION_DENIED, f"Cannot write to '{directory}'. Choose another folder."
            )
    finally:
        tmp.unlink(missing_ok=True)
