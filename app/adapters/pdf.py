"""PDF engine: pypdfium2 (Apache-2.0 / BSD-3) renders pages, Pillow writes image -> PDF."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from app import limits
from app.adapters.image import CheckCancel, _noop, has_alpha, load_image, save_image
from app.models import ErrorCode, FileType, QuickConvertError

FPDF_ERR_PASSWORD = 4


def image_to_pdf(source: Path, destination: Path, *, dpi: int | None,
                 check_cancel: CheckCancel = _noop) -> None:
    """One page sized to the image at the given DPI, so aspect ratio is exact and nothing clips."""
    dpi = dpi or limits.DEFAULT_DPI
    im = load_image(source)
    check_cancel()
    if has_alpha(im):
        im = im.convert("RGBA")
    elif im.mode not in ("RGB", "L", "CMYK"):
        im = im.convert("RGB")
    im.save(destination, format="PDF", resolution=dpi, quality=95)


def is_encrypted(source: Path) -> bool:
    try:
        with open_pdf(source, None):
            return False
    except QuickConvertError as exc:
        if exc.code is ErrorCode.PASSWORD_REQUIRED:
            return True
        raise


@contextmanager
def open_pdf(source: Path, password: str | None) -> Iterator[pdfium.PdfDocument]:
    try:
        doc = pdfium.PdfDocument(str(source), password=password or None)
    except pdfium.PdfiumError as exc:
        if getattr(exc, "err_code", None) == FPDF_ERR_PASSWORD:
            message = ("The password is incorrect." if password
                       else f"'{source.name}' is password protected.")
            raise QuickConvertError(ErrorCode.PASSWORD_REQUIRED, message) from exc
        raise QuickConvertError(ErrorCode.INVALID_INPUT,
                                f"'{source.name}' is corrupt or unreadable.") from exc
    try:
        yield doc
    finally:
        doc.close()


def pdf_page_count(source: Path, password: str | None = None) -> int:
    with open_pdf(source, password) as doc:
        return len(doc)


def render_page(source: Path, *, page: int, dpi: int | None, password: str | None = None,
                check_cancel: CheckCancel = _noop) -> Image.Image:
    """Render a 1-based page number to an RGB image."""
    dpi = dpi or limits.DEFAULT_DPI
    with open_pdf(source, password) as doc:
        if not 1 <= page <= len(doc):
            raise QuickConvertError(
                ErrorCode.INVALID_INPUT,
                f"Page {page} does not exist; the document has {len(doc)} page(s).",
            )
        pdf_page = doc[page - 1]
        try:
            width_pt, height_pt = pdf_page.get_size()
            scale = dpi / 72
            if width_pt * scale * height_pt * scale > limits.MAX_RENDER_PIXELS:
                raise QuickConvertError(ErrorCode.RESOURCE_LIMIT,
                                        f"Page {page} at {dpi} DPI is too large. Lower the DPI.")
            check_cancel()
            bitmap = pdf_page.render(scale=scale, fill_color=(255, 255, 255, 255))
            try:
                return bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
        finally:
            pdf_page.close()


def pdf_page_to_image(source: Path, destination: Path, target: FileType, *, page: int,
                      dpi: int | None, password: str | None, quality: int | None,
                      check_cancel: CheckCancel = _noop) -> None:
    im = render_page(source, page=page, dpi=dpi, password=password, check_cancel=check_cancel)
    check_cancel()
    save_image(im, destination, target, quality=quality)


def verify_pdf(path: Path) -> None:
    try:
        with open_pdf(path, None) as doc:
            ok = len(doc) >= 1
    except QuickConvertError:
        ok = False
    if not ok:
        raise QuickConvertError(ErrorCode.CONVERSION_FAILED, "The output PDF could not be read back.")
