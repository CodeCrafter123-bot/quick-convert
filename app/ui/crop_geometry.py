"""Crop-selection math in original image pixels, kept free of Qt so it can be unit tested.

A rect is (left, top, right, bottom) as floats; bounds are the image (width, height).
`ratio` is width / height, or None for a free selection.
"""

from __future__ import annotations

Rect = tuple[float, float, float, float]

CORNERS = {"nw": ("w", "n"), "ne": ("e", "n"), "se": ("e", "s"), "sw": ("w", "s")}
EDGES = ("n", "e", "s", "w")
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi))


def full_rect(width: float, height: float) -> Rect:
    return (0.0, 0.0, float(width), float(height))


def fit_ratio(rect: Rect, ratio: float | None) -> Rect:
    """Largest rect of the given ratio, centered inside rect."""
    if ratio is None:
        return rect
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if w / h > ratio:
        w = h * ratio
    else:
        h = w / ratio
    cx, cy = (left + right) / 2, (top + bottom) / 2
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def move(rect: Rect, dx: float, dy: float, width: float, height: float) -> Rect:
    left, top, right, bottom = rect
    dx = _clamp(dx, -left, width - right)
    dy = _clamp(dy, -top, height - bottom)
    return (left + dx, top + dy, right + dx, bottom + dy)


def from_points(ax: float, ay: float, px: float, py: float, width: float, height: float,
                ratio: float | None = None, min_size: float = 1.0) -> Rect:
    """Rect spanned from fixed anchor (ax, ay) to drag point (px, py), clamped to bounds."""
    px, py = _clamp(px, 0, width), _clamp(py, 0, height)
    sx = 1 if px >= ax else -1
    sy = 1 if py >= ay else -1
    max_w = width - ax if sx > 0 else ax
    max_h = height - ay if sy > 0 else ay
    # Not enough room on the dragged side for even a minimal rect: flip direction.
    if max_w < min_size:
        sx, max_w = -sx, width - max_w
    if max_h < min_size:
        sy, max_h = -sy, height - max_h
    w = max(abs(px - ax), min_size)
    h = max(abs(py - ay), min_size)
    if ratio is not None:
        if w / h > ratio:
            h = w / ratio
        else:
            w = h * ratio
        if w > max_w:
            w, h = max_w, max_w / ratio
        if h > max_h:
            h, w = max_h, max_h * ratio
    else:
        w, h = min(w, max_w), min(h, max_h)
    x2, y2 = ax + sx * w, ay + sy * h
    return (min(ax, x2), min(ay, y2), max(ax, x2), max(ay, y2))


def resize(rect: Rect, handle: str, px: float, py: float, width: float, height: float,
           ratio: float | None = None, min_size: float = 1.0) -> Rect:
    left, top, right, bottom = rect
    if handle in CORNERS:
        hx, hy = CORNERS[handle]
        ax = right if hx == "w" else left
        ay = bottom if hy == "n" else top
        return from_points(ax, ay, px, py, width, height, ratio, min_size)

    if handle in ("e", "w"):
        if handle == "e":
            new_w = _clamp(px, left + min_size, width) - left
            avail_w = width - left
        else:
            new_w = right - _clamp(px, 0, right - min_size)
            avail_w = right
        if ratio is None:
            return (right - new_w, top, right, bottom) if handle == "w" else (left, top, left + new_w, bottom)
        cy = (top + bottom) / 2
        max_h = 2 * min(cy, height - cy)
        new_w = min(new_w, avail_w, max_h * ratio)
        new_h = new_w / ratio
        x1, x2 = (right - new_w, right) if handle == "w" else (left, left + new_w)
        return (x1, cy - new_h / 2, x2, cy + new_h / 2)

    if handle in ("n", "s"):
        if handle == "s":
            new_h = _clamp(py, top + min_size, height) - top
            avail_h = height - top
        else:
            new_h = bottom - _clamp(py, 0, bottom - min_size)
            avail_h = bottom
        if ratio is None:
            return (left, bottom - new_h, right, bottom) if handle == "n" else (left, top, right, top + new_h)
        cx = (left + right) / 2
        max_w = 2 * min(cx, width - cx)
        new_h = min(new_h, avail_h, max_w / ratio)
        new_w = new_h * ratio
        y1, y2 = (bottom - new_h, bottom) if handle == "n" else (top, top + new_h)
        return (cx - new_w / 2, y1, cx + new_w / 2, y2)

    raise ValueError(f"unknown handle {handle!r}")


def to_box(rect: Rect, width: int, height: int) -> tuple[int, int, int, int]:
    """Round to whole pixels inside the image, at least 1x1."""
    left = int(_clamp(round(rect[0]), 0, width - 1))
    top = int(_clamp(round(rect[1]), 0, height - 1))
    right = int(_clamp(round(rect[2]), left + 1, width))
    bottom = int(_clamp(round(rect[3]), top + 1, height))
    return (left, top, right, bottom)


def handle_points(rect: Rect) -> dict[str, tuple[float, float]]:
    left, top, right, bottom = rect
    cx, cy = (left + right) / 2, (top + bottom) / 2
    return {"nw": (left, top), "n": (cx, top), "ne": (right, top), "e": (right, cy),
            "se": (right, bottom), "s": (cx, bottom), "sw": (left, bottom), "w": (left, cy)}
