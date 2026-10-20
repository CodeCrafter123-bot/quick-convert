from __future__ import annotations

import pytest
from PIL import Image

from app.models import ErrorCode, FileType, QuickConvertError
from app.services.editing import BackgroundOptions, EditSpec, export_edit, render_edit
from tests.conftest import assert_no_temp_files


def test_crop_matches_box_in_original_pixels(jpeg_file, out_dir):
    dest = export_edit(jpeg_file, EditSpec(crop_box=(10, 20, 110, 70)), FileType.PNG,
                       out_dir / "crop.png")
    with Image.open(dest) as im:
        assert im.size == (100, 50)


@pytest.mark.parametrize("box", [(0, 0, 0, 10), (-1, 0, 10, 10), (0, 0, 321, 10), (50, 50, 40, 60)])
def test_crop_outside_bounds_rejected(jpeg_file, out_dir, box):
    with pytest.raises(QuickConvertError) as err:
        export_edit(jpeg_file, EditSpec(crop_box=box), FileType.PNG, out_dir / "c.png")
    assert err.value.code is ErrorCode.INVALID_INPUT
    assert not any(out_dir.iterdir())


def test_background_dimensions_and_corners(png_file):
    bg = BackgroundOptions(color=(0, 0, 255), padding=20, radius=30)
    im = render_edit(png_file, EditSpec(background=bg))
    assert im.size == (300 + 40, 150 + 40)
    # Padding is background color.
    assert im.getpixel((5, 5))[:3] == (0, 0, 255)
    # The image's rounded corner shows background, its center shows the image.
    assert im.getpixel((21, 21))[:3] == (0, 0, 255)
    assert im.getpixel((170, 95))[:3] == (20, 120, 220)


def test_crop_then_background_matches_preview(jpeg_file, out_dir):
    spec = EditSpec(crop_box=(0, 0, 100, 100),
                    background=BackgroundOptions((255, 255, 255), padding=10, radius=0))
    preview = render_edit(jpeg_file, spec)
    dest = export_edit(jpeg_file, spec, FileType.PNG, out_dir / "e.png")
    with Image.open(dest) as saved:
        assert saved.size == preview.size == (120, 120)
        assert saved.convert("RGBA").tobytes() == preview.tobytes()
    assert_no_temp_files(out_dir)


def test_edit_to_jpeg_uses_background_color_for_corners(png_file, out_dir):
    spec = EditSpec(background=BackgroundOptions((0, 255, 0), padding=5, radius=40))
    dest = export_edit(png_file, spec, FileType.JPEG, out_dir / "e.jpg")
    with Image.open(dest) as im:
        r, g, b = im.getpixel((6, 6))
    assert g > 200 and r < 60 and b < 60


def test_edit_pdf_rejected(pdf_file, out_dir):
    with pytest.raises(QuickConvertError) as err:
        export_edit(pdf_file, EditSpec(), FileType.PNG, out_dir / "x.png")
    assert err.value.code is ErrorCode.UNSUPPORTED_PAIR
