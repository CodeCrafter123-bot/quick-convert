"""Validates a ConversionRequest and runs it through the right adapter."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from app import limits
from app.adapters import image as image_adapter
from app.adapters.image import CheckCancel, _noop
from app.models import (
    ConversionRequest,
    ConversionResult,
    ErrorCode,
    FileInfo,
    FileType,
    QuickConvertError,
)
from app.services.capabilities import get_capability
from app.services.inspection import inspect_file
from app.services.output import atomic_output


def validate(request: ConversionRequest) -> FileInfo:
    """Raise QuickConvertError if the request cannot run; return the inspected source."""
    info = inspect_file(request.source_path)
    cap = get_capability(info.file_type, request.target_format)
    if cap is None:
        raise QuickConvertError(
            ErrorCode.UNSUPPORTED_PAIR,
            f"{info.file_type.value.upper()} to {request.target_format.value.upper()} "
            "is not supported.",
        )
    if not cap.available:
        raise QuickConvertError(ErrorCode.UNSUPPORTED_PAIR, cap.unavailable_reason or "Unavailable.")

    opts = request.options
    extra = opts.set_fields() - cap.supported_options
    if extra:
        raise QuickConvertError(
            ErrorCode.INVALID_INPUT,
            f"Option(s) {', '.join(sorted(extra))} do not apply to this conversion.",
        )
    if opts.quality is not None and not 1 <= opts.quality <= 100:
        raise QuickConvertError(ErrorCode.INVALID_INPUT, "Quality must be between 1 and 100.")
    if opts.dpi is not None and not 36 <= opts.dpi <= limits.MAX_DPI:
        raise QuickConvertError(ErrorCode.INVALID_INPUT,
                                f"DPI must be between 36 and {limits.MAX_DPI}.")
    if opts.background_color is not None and not (
        len(opts.background_color) == 3 and all(0 <= c <= 255 for c in opts.background_color)
    ):
        raise QuickConvertError(ErrorCode.INVALID_INPUT, "Background color must be RGB 0-255.")
    if info.file_type is FileType.PDF:
        if info.encrypted and not opts.password:
            raise QuickConvertError(ErrorCode.PASSWORD_REQUIRED,
                                    f"'{info.path.name}' is password protected.")
        page = 1 if opts.pdf_page is None else opts.pdf_page
        if info.page_count is not None and not 1 <= page <= info.page_count:
            raise QuickConvertError(
                ErrorCode.INVALID_INPUT,
                f"Page {page} does not exist; the document has {info.page_count} page(s).",
            )

    dest = Path(request.destination_path)
    if dest.suffix.lower() not in _valid_suffixes(request.target_format):
        raise QuickConvertError(
            ErrorCode.INVALID_INPUT,
            f"The file name should end in {request.target_format.extension}.",
        )
    if _same_file(dest, info.path):
        raise QuickConvertError(ErrorCode.OUTPUT_EXISTS, "The output cannot replace the original file.")
    if dest.exists() and not request.overwrite:
        raise QuickConvertError(ErrorCode.OUTPUT_EXISTS, f"'{dest.name}' already exists.")
    return info


def run(request: ConversionRequest, check_cancel: CheckCancel = _noop,
        job_id: str = "") -> ConversionResult:
    info = validate(request)
    check_cancel()
    opts = request.options
    target = request.target_format
    dest = Path(request.destination_path)

    if target is FileType.PDF:
        from app.adapters import pdf as pdf_adapter

        verify = pdf_adapter.verify_pdf
        work = partial(pdf_adapter.image_to_pdf, info.path, dpi=opts.dpi, check_cancel=check_cancel)
    elif info.file_type is FileType.PDF:
        from app.adapters import pdf as pdf_adapter

        verify = partial(image_adapter.verify_image, expected=target)
        work = partial(pdf_adapter.pdf_page_to_image, info.path, target=target,
                       page=1 if opts.pdf_page is None else opts.pdf_page, dpi=opts.dpi,
                       password=opts.password, quality=opts.quality, check_cancel=check_cancel)
    else:
        verify = partial(image_adapter.verify_image, expected=target)
        work = partial(image_adapter.convert_image, info.path, target=target,
                       quality=opts.quality, background=opts.background_color,
                       keep_metadata=opts.keep_metadata, check_cancel=check_cancel)

    try:
        with atomic_output(dest, overwrite=request.overwrite, verify=verify) as tmp:
            warnings = work(tmp) or []
            check_cancel()
    except QuickConvertError:
        raise
    except MemoryError:
        raise QuickConvertError(ErrorCode.RESOURCE_LIMIT, "Not enough memory for this file.")
    except Exception as exc:  # engine failure: keep technical detail out of the UI message
        raise QuickConvertError(ErrorCode.CONVERSION_FAILED, "The conversion failed.") from exc

    return ConversionResult(job_id, [dest], [dest.stat().st_size], warnings)


def _valid_suffixes(target: FileType) -> set[str]:
    return {".jpg", ".jpeg"} if target is FileType.JPEG else {target.extension}


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and a.samefile(b)
    except OSError:
        return False
