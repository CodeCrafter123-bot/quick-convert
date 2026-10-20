"""Non-destructive crop + background. Every export starts from the source file."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app import limits
from app.adapters import image as image_adapter
from app.adapters.image import CheckCancel, _noop
from app.models import (
    BackgroundOptions,
    ConversionOptions,
    ConversionRequest,
    EditSpec,
    ErrorCode,
    FileInfo,
    FileType,
    QuickConvertError,
)

__all__ = ["BackgroundOptions", "EditSpec", "export_edit", "output_size", "preview_edit",
           "render_edit", "save_edit", "validate_edit"]

EDIT_TARGETS = (FileType.PNG, FileType.JPEG, FileType.WEBP)


def output_size(width: int, height: int, spec: EditSpec) -> tuple[int, int]:
    """Final pixel size of an edit applied to a width x height source."""
    if spec.crop_box is not None:
        left, top, right, bottom = spec.crop_box
        width, height = right - left, bottom - top
    if spec.background is not None:
        width += 2 * spec.background.padding
        height += 2 * spec.background.padding
    return width, height


def validate_edit(info: FileInfo, spec: EditSpec, target: FileType,
                  options: ConversionOptions) -> None:
    if not info.file_type.is_image:
        raise QuickConvertError(ErrorCode.UNSUPPORTED_PAIR, "Editing is only available for images.")
    if target not in EDIT_TARGETS:
        raise QuickConvertError(ErrorCode.UNSUPPORTED_PAIR, "Edits can be saved as PNG, JPEG or WebP.")
    allowed = {"quality"} if target in (FileType.JPEG, FileType.WEBP) else set()
    extra = options.set_fields() - allowed
    if extra:
        raise QuickConvertError(ErrorCode.INVALID_INPUT,
                                f"Option(s) {', '.join(sorted(extra))} do not apply to this export.")
    if options.quality is not None and not 1 <= options.quality <= 100:
        raise QuickConvertError(ErrorCode.INVALID_INPUT, "Quality must be between 1 and 100.")
    if spec.crop_box is not None:
        left, top, right, bottom = spec.crop_box
        if not (0 <= left < right <= info.width and 0 <= top < bottom <= info.height):
            raise QuickConvertError(
                ErrorCode.INVALID_INPUT,
                f"Crop area {spec.crop_box} is outside the {info.width}x{info.height} image.",
            )
    if spec.background is not None:
        bg = spec.background
        if not 0 <= bg.padding <= limits.MAX_PADDING:
            raise QuickConvertError(ErrorCode.INVALID_INPUT,
                                    f"Padding must be between 0 and {limits.MAX_PADDING}.")
        if bg.radius < 0:
            raise QuickConvertError(ErrorCode.INVALID_INPUT, "Corner radius cannot be negative.")
        if not (len(bg.color) == 3 and all(0 <= c <= 255 for c in bg.color)):
            raise QuickConvertError(ErrorCode.INVALID_INPUT, "Background color must be RGB 0-255.")
    width, height = output_size(info.width, info.height, spec)
    if width * height > limits.MAX_IMAGE_PIXELS:
        raise QuickConvertError(ErrorCode.RESOURCE_LIMIT, "The result would be too large.")


def apply_edit(im: Image.Image, spec: EditSpec, scale: float = 1.0) -> Image.Image:
    """Apply spec to an image that is `scale` times the size of the original source."""
    if spec.crop_box is not None:
        box = spec.crop_box
        if scale != 1.0:
            box = tuple(round(v * scale) for v in box)  # type: ignore[assignment]
            box = (box[0], box[1], max(box[2], box[0] + 1), max(box[3], box[1] + 1))
            box = (min(box[0], im.width - 1), min(box[1], im.height - 1),
                   min(box[2], im.width), min(box[3], im.height))
        im = image_adapter.crop(im, box)
    if spec.background is not None:
        bg = spec.background
        im = image_adapter.compose_background(im, color=bg.color, padding=round(bg.padding * scale),
                                              radius=round(bg.radius * scale))
    return im


def render_edit(source: Path, spec: EditSpec) -> Image.Image:
    """Full-resolution result, exactly as it will be exported."""
    from app.services.inspection import inspect_file

    info = inspect_file(source)
    validate_edit(info, spec, FileType.PNG, ConversionOptions())
    return apply_edit(image_adapter.load_image(info.path), spec)


def preview_edit(preview: Image.Image, original_size: tuple[int, int], spec: EditSpec) -> Image.Image:
    """Fast approximate preview from a downscaled copy of the source."""
    scale = preview.width / original_size[0]
    return apply_edit(preview, spec, scale)


def save_edit(source: Path, spec: EditSpec, destination: Path, target: FileType, *,
              quality: int | None, check_cancel: CheckCancel = _noop) -> list[str]:
    im = image_adapter.load_image(source)
    check_cancel()
    im = apply_edit(im, spec)
    check_cancel()
    background = spec.background.color if spec.background else None
    warnings = []
    if target is FileType.JPEG and background is None and image_adapter.has_alpha(im):
        warnings.append("JPEG has no transparency; transparent areas were filled with white.")
    image_adapter.save_image(im, destination, target, quality=quality, background=background)
    return warnings


def export_edit(source: Path, spec: EditSpec, target: FileType, destination: Path, *,
                quality: int | None = None, overwrite: bool = False) -> Path:
    """Synchronous export (CLI and tests). The UI submits the same request as a job."""
    from app.services import conversion

    request = ConversionRequest(Path(source), target, Path(destination),
                                ConversionOptions(quality=quality), overwrite, edit=spec)
    conversion.run(request)
    return Path(destination)
