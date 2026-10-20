"""PyMuPDF-based PDF engine: image -> PDF and PDF page -> image.

License note: PyMuPDF is AGPL-3.0 or commercial. Review before distribution.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

from app import limits
from app.adapters.image import CheckCancel, _noop, has_alpha, load_image, save_image
from app.models import ErrorCode, FileType, QuickConvertError


def image_to_pdf(source: Path, destination: Path, *, dpi: int | None,
                 check_cancel: CheckCancel = _noop) -> None:
    """One page sized to the image at the given DPI, so aspect ratio is exact and nothing clips."""
    dpi = dpi or limits.DEFAULT_DPI
    im = load_image(source)
    check_cancel()

    buf = io.BytesIO()
    if has_alpha(im):
        im.save(buf, format="PNG")
    else:
        im.convert("RGB").save(buf, format="JPEG", quality=95)
    check_cancel()

    width_pt, height_pt = im.width * 72 / dpi, im.height * 72 / dpi
    with pymupdf.open() as doc:
        page = doc.new_page(width=width_pt, height=height_pt)
        page.insert_image(page.rect, stream=buf.getvalue())
        doc.save(destination, garbage=3, deflate=True)


def _open_pdf(source: Path, password: str | None) -> pymupdf.Document:
    try:
        doc = pymupdf.open(source, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{source.name}' is corrupt or unreadable.")
    if doc.needs_pass:
        if not password:
            doc.close()
            raise QuickConvertError(ErrorCode.PASSWORD_REQUIRED,
                                    f"'{source.name}' is password protected.")
        if not doc.authenticate(password):
            doc.close()
            raise QuickConvertError(ErrorCode.PASSWORD_REQUIRED, "The password is incorrect.")
    return doc


def pdf_page_count(source: Path, password: str | None = None) -> int:
    with _open_pdf(source, password) as doc:
        return doc.page_count


def render_page(source: Path, *, page: int, dpi: int | None, password: str | None = None,
                check_cancel: CheckCancel = _noop) -> Image.Image:
    """Render a 1-based page number to an RGB image."""
    dpi = dpi or limits.DEFAULT_DPI
    with _open_pdf(source, password) as doc:
        if not 1 <= page <= doc.page_count:
            raise QuickConvertError(
                ErrorCode.INVALID_INPUT,
                f"Page {page} does not exist; the document has {doc.page_count} page(s).",
            )
        pdf_page = doc[page - 1]
        scale = dpi / 72
        pixels = pdf_page.rect.width * scale * pdf_page.rect.height * scale
        if pixels > limits.MAX_RENDER_PIXELS:
            raise QuickConvertError(ErrorCode.RESOURCE_LIMIT,
                                    f"Page {page} at {dpi} DPI is too large. Lower the DPI.")
        check_cancel()
        pix = pdf_page.get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def pdf_page_to_image(source: Path, destination: Path, target: FileType, *, page: int,
                      dpi: int | None, password: str | None, quality: int | None,
                      check_cancel: CheckCancel = _noop) -> None:
    im = render_page(source, page=page, dpi=dpi, password=password, check_cancel=check_cancel)
    check_cancel()
    save_image(im, destination, target, quality=quality)


def verify_pdf(path: Path) -> None:
    try:
        with pymupdf.open(path, filetype="pdf") as doc:
            ok = doc.page_count >= 1
    except Exception:
        ok = False
    if not ok:
        raise QuickConvertError(ErrorCode.CONVERSION_FAILED, "The output PDF could not be read back.")
