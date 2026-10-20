"""Non-destructive crop + background export. Every export starts from the source file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.adapters import image as image_adapter
from app.adapters.image import Box
from app.models import Color, ErrorCode, FileType, QuickConvertError
from app.services.inspection import inspect_file
from app.services.output import atomic_output


@dataclass(frozen=True)
class BackgroundOptions:
    color: Color = (255, 255, 255)
    padding: int = 64
    radius: int = 0


@dataclass(frozen=True)
class EditSpec:
    crop_box: Box | None = None  # in original image pixels
    background: BackgroundOptions | None = None


def render_edit(source: Path, spec: EditSpec) -> Image.Image:
    """Apply the edit to a fresh copy of the source; used for both preview and export."""
    info = inspect_file(source)
    if not info.file_type.is_image:
        raise QuickConvertError(ErrorCode.UNSUPPORTED_PAIR, "Editing is only available for images.")
    im = image_adapter.load_image(info.path)
    if spec.crop_box is not None:
        im = image_adapter.crop(im, spec.crop_box)
    if spec.background is not None:
        bg = spec.background
        im = image_adapter.compose_background(im, color=bg.color, padding=bg.padding,
                                              radius=bg.radius)
    return im


def export_edit(source: Path, spec: EditSpec, target: FileType, destination: Path, *,
                quality: int | None = None, overwrite: bool = False) -> Path:
    if not target.is_image:
        raise QuickConvertError(ErrorCode.UNSUPPORTED_PAIR, "Edits can be saved as JPEG, PNG or WebP.")
    destination = Path(destination)
    if destination.exists() and destination.samefile(source):
        raise QuickConvertError(ErrorCode.OUTPUT_EXISTS, "The output cannot replace the original file.")
    im = render_edit(Path(source), spec)
    background = spec.background.color if spec.background else None
    with atomic_output(destination, overwrite=overwrite,
                       verify=lambda p: image_adapter.verify_image(p, target)) as tmp:
        image_adapter.save_image(im, tmp, target, quality=quality, background=background)
    return destination
