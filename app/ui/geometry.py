"""Radial-menu geometry, kept free of Qt so it can be unit tested.

Angles are in degrees, measured clockwise from 12 o'clock. Sector 0 is centered at the top.
"""

from __future__ import annotations

import math


def sector_step(count: int) -> float:
    return 360.0 / count


def sector_center_angle(index: int, count: int) -> float:
    return index * sector_step(count)


def sector_at(dx: float, dy: float, count: int, inner: float, outer: float) -> int | None:
    """Return the sector under a point offset (dx, dy) from the center, or None.

    dy grows downward (screen coordinates). Points inside the inner hole or
    outside the outer ring belong to no sector.
    """
    if count <= 0:
        return None
    distance = math.hypot(dx, dy)
    if distance < inner or distance > outer:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0
    step = sector_step(count)
    return int(((angle + step / 2) % 360.0) // step)


def polar_to_xy(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    return cx + radius * math.sin(rad), cy - radius * math.cos(rad)


def clamp_center(x: int, y: int, radius: int,
                 screen: tuple[int, int, int, int]) -> tuple[int, int]:
    """Move a wheel center so the whole wheel fits inside screen (left, top, width, height)."""
    left, top, width, height = screen
    x = max(left + radius, min(x, left + width - radius))
    y = max(top + radius, min(y, top + height - radius))
    return x, y
