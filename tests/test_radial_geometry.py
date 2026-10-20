from __future__ import annotations

import pytest

from app.ui.geometry import clamp_center, polar_to_xy, sector_at

INNER, OUTER = 40, 120


@pytest.mark.parametrize("dx,dy,expected", [
    (0, -80, 0),    # straight up -> sector 0
    (80, 0, 1),     # right
    (0, 80, 2),     # down
    (-80, 0, 3),    # left
])
def test_four_sectors_by_direction(dx, dy, expected):
    assert sector_at(dx, dy, 4, INNER, OUTER) == expected


def test_sector_boundaries_are_halfway_between_centers():
    # With 4 sectors, sector 0 spans -45..45 degrees; just past 45 is sector 1.
    assert sector_at(70, -72, 4, INNER, OUTER) == 0
    assert sector_at(72, -70, 4, INNER, OUTER) == 1


@pytest.mark.parametrize("dx,dy", [(0, 0), (10, 10), (0, -INNER + 1), (0, -OUTER - 1), (200, 0)])
def test_hole_and_outside_select_nothing(dx, dy):
    assert sector_at(dx, dy, 4, INNER, OUTER) is None


@pytest.mark.parametrize("count", [1, 2, 3, 5, 7])
def test_label_position_maps_back_to_its_sector(count):
    for i in range(count):
        x, y = polar_to_xy(0, 0, 80, i * 360 / count)
        assert sector_at(x, y, count, INNER, OUTER) == i


def test_zero_items():
    assert sector_at(0, -80, 0, INNER, OUTER) is None


@pytest.mark.parametrize("point,expected", [
    ((500, 400), (500, 400)),      # already fits
    ((10, 10), (126, 126)),        # top-left corner
    ((1910, 1070), (1794, 954)),   # bottom-right corner
])
def test_clamp_keeps_wheel_on_screen(point, expected):
    assert clamp_center(*point, 126, (0, 0, 1920, 1080)) == expected


def test_clamp_on_secondary_monitor_with_offset():
    assert clamp_center(-1910, 5, 126, (-1920, 0, 1920, 1080)) == (-1794, 126)
