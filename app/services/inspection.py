"""inspect_file(path): detect the real type from content, not the extension."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app import limits
from app.models import ErrorCode, FileInfo, FileType, QuickConvertError

_PIL_FORMATS = {"JPEG": FileType.JPEG, "PNG": FileType.PNG, "WEBP": FileType.WEBP}


def sniff_type(header: bytes) -> FileType | None:
    if header.startswith(b"\xff\xd8\xff"):
        return FileType.JPEG
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileType.PNG
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return FileType.WEBP
    # PDF spec allows junk before the header; readers accept it within 1 KB.
    if b"%PDF-" in header[:1024]:
        return FileType.PDF
    return None


def inspect_file(path: str | os.PathLike[str]) -> FileInfo:
    path = Path(path)
    try:
        size = path.stat().st_size
        if not path.is_file():
            raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' is not a file.")
        with path.open("rb") as f:
            header = f.read(1024)
    except PermissionError:
        raise QuickConvertError(ErrorCode.PERMISSION_DENIED, f"Cannot read '{path.name}'.")
    except FileNotFoundError:
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' does not exist.")

    if size > limits.MAX_INPUT_BYTES:
        raise QuickConvertError(
            ErrorCode.RESOURCE_LIMIT,
            f"'{path.name}' is larger than {limits.MAX_INPUT_BYTES // (1024 * 1024)} MB.",
        )

    file_type = sniff_type(header)
    if file_type is None:
        raise QuickConvertError(
            ErrorCode.INVALID_INPUT,
            f"'{path.name}' is not a supported file type (JPEG, PNG, WebP or PDF).",
        )

    if file_type is FileType.PDF:
        return _inspect_pdf(path, size)
    return _inspect_image(path, size, file_type)


def _inspect_image(path: Path, size: int, sniffed: FileType) -> FileInfo:
    try:
        with Image.open(path) as im:
            fmt = _PIL_FORMATS.get(im.format or "")
            width, height = im.size
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' is corrupt or unreadable.")
    if fmt is not sniffed:
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' is corrupt or unreadable.")
    if width * height > limits.MAX_IMAGE_PIXELS:
        raise QuickConvertError(
            ErrorCode.RESOURCE_LIMIT,
            f"'{path.name}' is {width}x{height}; the limit is "
            f"{limits.MAX_IMAGE_PIXELS // 1_000_000} megapixels.",
        )
    return FileInfo(path, sniffed, size, width=width, height=height)


def _inspect_pdf(path: Path, size: int) -> FileInfo:
    import pymupdf

    try:
        with pymupdf.open(path, filetype="pdf") as doc:
            encrypted = bool(doc.needs_pass)
            page_count = None if encrypted else doc.page_count
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' is corrupt or unreadable.")
    if page_count is not None:
        if page_count == 0:
            raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' has no pages.")
        if page_count > limits.MAX_PDF_PAGES:
            raise QuickConvertError(
                ErrorCode.RESOURCE_LIMIT,
                f"'{path.name}' has {page_count} pages; the limit is {limits.MAX_PDF_PAGES}.",
            )
    return FileInfo(path, FileType.PDF, size, page_count=page_count, encrypted=encrypted)
