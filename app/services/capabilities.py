"""Explicit capability registry: the UI may only offer pairs listed here."""

from __future__ import annotations

from functools import cache

from app.models import Capability, FileInfo, FileType

J, P, W, PDF = FileType.JPEG, FileType.PNG, FileType.WEBP, FileType.PDF

_IMAGE_OPTS = frozenset({"keep_metadata"})
_LOSSY_OPTS = _IMAGE_OPTS | {"quality", "background_color"}

# (input, output) -> (adapter, supported options)
_PAIRS: dict[tuple[FileType, FileType], tuple[str, frozenset[str]]] = {
    (J, P): ("image", _IMAGE_OPTS),
    (J, W): ("image", _LOSSY_OPTS - {"background_color"}),
    (P, J): ("image", _LOSSY_OPTS),
    (P, W): ("image", _LOSSY_OPTS - {"background_color"}),
    (W, J): ("image", _LOSSY_OPTS),
    (W, P): ("image", _IMAGE_OPTS),
    (J, PDF): ("pdf", frozenset({"dpi"})),
    (P, PDF): ("pdf", frozenset({"dpi"})),
    (W, PDF): ("pdf", frozenset({"dpi"})),
    (PDF, P): ("pdf", frozenset({"pdf_page", "dpi", "password"})),
    (PDF, J): ("pdf", frozenset({"pdf_page", "dpi", "password", "quality"})),
}


def _adapter_status(adapter: str, input_type: FileType, output_type: FileType) -> str | None:
    """Return None if available, otherwise a reason."""
    if adapter == "pdf":
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            return "PDF support (PyMuPDF) is not installed."
    if W in (input_type, output_type):
        from PIL import features

        if not features.check("webp"):
            return "This Pillow build has no WebP codec."
    return None


@cache
def all_capabilities() -> tuple[Capability, ...]:
    caps = []
    for (src, dst), (adapter, opts) in _PAIRS.items():
        reason = _adapter_status(adapter, src, dst)
        caps.append(Capability(src, dst, adapter, reason is None, opts, reason))
    return tuple(caps)


def get_capability(input_type: FileType, output_type: FileType) -> Capability | None:
    for cap in all_capabilities():
        if cap.input_type is input_type and cap.output_type is output_type:
            return cap
    return None


def get_targets(file_info: FileInfo) -> list[Capability]:
    """All registered targets for this input, including unavailable ones (to show disabled)."""
    return [c for c in all_capabilities() if c.input_type is file_info.file_type]
