"""Pillow-based image engine: conversion, crop and background composition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from app import limits
from app.models import Box, Color, ErrorCode, FileType, QuickConvertError

Image.MAX_IMAGE_PIXELS = limits.MAX_IMAGE_PIXELS

PIL_FORMAT = {FileType.JPEG: "JPEG", FileType.PNG: "PNG", FileType.WEBP: "WEBP"}

CheckCancel = Callable[[], None]


def _noop() -> None:
    pass


def load_image(path: Path) -> Image.Image:
    """Open, apply EXIF orientation and fully decode an image."""
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.load()
            return im
    except Image.DecompressionBombError:
        raise QuickConvertError(ErrorCode.RESOURCE_LIMIT, f"'{path.name}' is too large to open.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise QuickConvertError(ErrorCode.INVALID_INPUT, f"'{path.name}' is corrupt or unreadable.")


def has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def flatten(im: Image.Image, color: Color) -> Image.Image:
    """Composite onto an opaque background so transparent areas don't turn black."""
    if not has_alpha(im):
        return im.convert("RGB") if im.mode not in ("RGB", "L") else im
    rgba = im.convert("RGBA")
    canvas = Image.new("RGB", rgba.size, color)
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def save_image(im: Image.Image, path: Path, target: FileType, *, quality: int | None = None,
               background: Color | None = None, exif: bytes | None = None) -> None:
    quality = quality or limits.DEFAULT_QUALITY
    kwargs: dict = {}
    if exif:
        kwargs["exif"] = exif
    if target is FileType.JPEG:
        im = flatten(im, background or limits.DEFAULT_BACKGROUND)
        kwargs.update(quality=quality, optimize=True)
    elif target is FileType.WEBP:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if has_alpha(im) else "RGB")
        kwargs.update(quality=quality, method=4)
    elif target is FileType.PNG:
        if im.mode == "CMYK":
            im = im.convert("RGB")
        kwargs.update(optimize=False)
    im.save(path, format=PIL_FORMAT[target], **kwargs)


def convert_image(source: Path, destination: Path, target: FileType, *, quality: int | None,
                  background: Color | None, keep_metadata: bool,
                  check_cancel: CheckCancel = _noop) -> list[str]:
    """Convert and return user-facing warnings."""
    im = load_image(source)
    check_cancel()
    warnings = []
    if target is FileType.JPEG and has_alpha(im):
        warnings.append("JPEG has no transparency; transparent areas were filled with the "
                        "background color.")
    exif = None
    if keep_metadata:
        # Orientation was already applied to pixels, so reset that tag.
        exif_data = im.getexif()
        if exif_data:
            exif_data[0x0112] = 1
            exif = exif_data.tobytes()
    save_image(im, destination, target, quality=quality, background=background, exif=exif)
    return warnings


def verify_image(path: Path, expected: FileType) -> None:
    try:
        with Image.open(path) as im:
            fmt = im.format
            im.load()
    except Exception:
        raise QuickConvertError(ErrorCode.CONVERSION_FAILED, "The output could not be read back.")
    if fmt != PIL_FORMAT[expected]:
        raise QuickConvertError(ErrorCode.CONVERSION_FAILED, "The output has the wrong format.")


# --- Editing ---------------------------------------------------------------

def crop(im: Image.Image, box: Box) -> Image.Image:
    left, top, right, bottom = box
    if not (0 <= left < right <= im.width and 0 <= top < bottom <= im.height):
        raise QuickConvertError(
            ErrorCode.INVALID_INPUT,
            f"Crop area {box} is outside the {im.width}x{im.height} image.",
        )
    return im.crop(box)


def compose_background(im: Image.Image, *, color: Color, padding: int,
                       radius: int = 0) -> Image.Image:
    """Place the image on a solid canvas with padding; optionally round its corners."""
    if not 0 <= padding <= limits.MAX_PADDING:
        raise QuickConvertError(ErrorCode.INVALID_INPUT,
                                f"Padding must be between 0 and {limits.MAX_PADDING}.")
    radius = max(0, min(radius, min(im.size) // 2))
    width, height = im.width + 2 * padding, im.height + 2 * padding
    if width * height > limits.MAX_IMAGE_PIXELS:
        raise QuickConvertError(ErrorCode.RESOURCE_LIMIT, "The result would be too large.")

    src = im.convert("RGBA")
    mask = src.getchannel("A")
    if radius:
        rounded = Image.new("L", src.size, 0)
        ImageDraw.Draw(rounded).rounded_rectangle((0, 0, src.width - 1, src.height - 1),
                                                  radius=radius, fill=255)
        mask = Image.composite(mask, rounded, rounded)
    canvas = Image.new("RGBA", (width, height), (*color, 255))
    canvas.paste(src, (padding, padding), mask)
    return canvas
