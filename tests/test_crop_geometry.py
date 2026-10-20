from __future__ import annotations

import itertools

import pytest

from app.ui.crop_geometry import (
    HANDLES,
    fit_ratio,
    from_points,
    full_rect,
    move,
    resize,
    to_box,
)

W, H = 400, 300
R = (100.0, 100.0, 200.0, 200.0)


def inside(rect, width=W, height=H, eps=1e-6):
    left, top, right, bottom = rect
    return -eps <= left < right <= width + eps and -eps <= top < bottom <= height + eps


def ratio_of(rect):
    return (rect[2] - rect[0]) / (rect[3] - rect[1])


def test_move_is_clamped_to_image():
    assert move(R, 1000, 1000, W, H) == (300, 200, 400, 300)
    assert move(R, -1000, -1000, W, H) == (0, 0, 100, 100)
    assert move(R, 10, -5, W, H) == (110, 95, 210, 195)


def test_corner_drag_from_anchor():
    assert resize(R, "se", 250, 260, W, H) == (100, 100, 250, 260)
    assert resize(R, "nw", 50, 40, W, H) == (50, 40, 200, 200)


def test_corner_drag_past_anchor_flips():
    assert resize(R, "se", 50, 50, W, H) == (50, 50, 100, 100)


def test_edges_move_only_one_side():
    assert resize(R, "e", 300, 0, W, H) == (100, 100, 300, 200)
    assert resize(R, "n", 0, 20, W, H) == (100, 20, 200, 200)


def test_edge_cannot_cross_opposite_edge():
    rect = resize(R, "e", 0, 0, W, H, min_size=5)
    assert rect == (100, 100, 105, 200)


@pytest.mark.parametrize("handle", HANDLES)
@pytest.mark.parametrize("ratio", [None, 1.0, 16 / 9, 0.5])
def test_resize_always_stays_in_bounds_and_keeps_ratio(handle, ratio):
    for px, py in itertools.product([-500, 0, 37, 150, 399, 900], repeat=2):
        rect = resize(R, handle, px, py, W, H, ratio)
        assert inside(rect), (handle, ratio, px, py, rect)
        if ratio is not None:
            assert ratio_of(rect) == pytest.approx(ratio, rel=1e-6), (handle, px, py, rect)


def test_from_points_with_ratio_is_clamped_by_shorter_room():
    rect = from_points(300, 200, 1000, 1000, W, H, ratio=1.0)
    assert rect == (300, 200, 400, 300)


def test_from_points_at_edge_flips_inward():
    rect = from_points(400, 300, 500, 500, W, H, min_size=10)
    assert inside(rect)
    assert rect[2] - rect[0] >= 10 and rect[3] - rect[1] >= 10


@pytest.mark.parametrize("ratio", [1.0, 4 / 3, 16 / 9, 9 / 16])
def test_fit_ratio_centered_and_inside(ratio):
    rect = fit_ratio(full_rect(W, H), ratio)
    assert inside(rect)
    assert ratio_of(rect) == pytest.approx(ratio)
    assert (rect[0] + rect[2]) / 2 == pytest.approx(W / 2)
    assert (rect[1] + rect[3]) / 2 == pytest.approx(H / 2)


def test_to_box_rounds_and_clamps():
    assert to_box((10.4, 10.6, 99.5, 50.2), W, H) == (10, 11, 100, 50)
    assert to_box((-3, -3, 500, 500), W, H) == (0, 0, W, H)
    assert to_box((5, 5, 5.2, 5.1), W, H) == (5, 5, 6, 6)  # never empty
