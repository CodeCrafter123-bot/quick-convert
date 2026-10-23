from __future__ import annotations

import hashlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from app import limits
from app.models import (
    ConversionOptions,
    ConversionRequest,
    ErrorCode,
    FileType,
    QuickConvertError,
)
from app.services import conversion
from app.services.capabilities import all_capabilities, get_targets
from app.services.inspection import inspect_file
from tests.conftest import assert_no_temp_files

FIXTURE_FOR = {
    FileType.JPEG: "jpeg_file",
    FileType.PNG: "png_file",
    FileType.WEBP: "webp_file",
    FileType.PDF: "pdf_file",
}


def _convert(src: Path, target: FileType, out_dir: Path, **opts) -> Path:
    dest = out_dir / f"result{target.extension}"
    conversion.run(ConversionRequest(src, target, dest, ConversionOptions(**opts)))
    return dest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("cap", all_capabilities(),
                         ids=lambda c: f"{c.input_type.value}->{c.output_type.value}")
def test_every_registered_pair_produces_readable_output(cap, request, out_dir):
    assert cap.available, cap.unavailable_reason
    src = request.getfixturevalue(FIXTURE_FOR[cap.input_type])
    before = _sha(src)

    dest = _convert(src, cap.output_type, out_dir)

    assert inspect_file(dest).file_type is cap.output_type
    assert _sha(src) == before, "source must never be modified"
    assert_no_temp_files(out_dir)


def test_transparent_png_to_jpeg_flattens_to_chosen_color(transparent_png, out_dir):
    dest = _convert(transparent_png, FileType.JPEG, out_dir, background_color=(0, 255, 0))
    with Image.open(dest) as im:
        r, g, b = im.convert("RGB").getpixel((20, 50))
    assert g > 230 and r < 30 and b < 30  # green, not black


def test_transparent_png_to_jpeg_defaults_to_white_and_warns(transparent_png, out_dir):
    dest = out_dir / "x.jpg"
    result = conversion.run(ConversionRequest(transparent_png, FileType.JPEG, dest))
    with Image.open(dest) as im:
        assert min(im.convert("RGB").getpixel((20, 50))) > 240
    assert result.warnings


def test_jpeg_to_png_keeps_dimensions(jpeg_file, out_dir):
    dest = _convert(jpeg_file, FileType.PNG, out_dir)
    with Image.open(dest) as im:
        assert im.size == (320, 200)


def test_image_to_pdf_single_page_with_correct_aspect_ratio(jpeg_file, out_dir):
    dest = _convert(jpeg_file, FileType.PDF, out_dir, dpi=100)
    doc = pdfium.PdfDocument(str(dest))
    try:
        assert len(doc) == 1
        width_pt, height_pt = doc[0].get_size()
        assert width_pt == pytest.approx(320 * 72 / 100)
        assert height_pt == pytest.approx(200 * 72 / 100)
        # Rendered back at the same DPI, the image fills the page edge to edge (no clipping).
        rendered = doc[0].render(scale=100 / 72).to_pil().convert("RGB")
    finally:
        doc.close()
    assert rendered.size == (320, 200)
    for xy in [(1, 1), (318, 1), (1, 198), (318, 198), (160, 100)]:
        r, g, b = rendered.getpixel(xy)
        assert r > 170 and g < 90 and b < 90, (xy, (r, g, b))  # the red fixture, not white


def test_transparent_image_to_pdf(transparent_png, out_dir):
    dest = _convert(transparent_png, FileType.PDF, out_dir, dpi=72)
    doc = pdfium.PdfDocument(str(dest))
    try:
        rendered = doc[0].render(scale=1, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
    finally:
        doc.close()
    assert rendered.getpixel((150, 50))[0] > 200 and rendered.getpixel((150, 50))[1] < 60  # red half
    assert min(rendered.getpixel((20, 50))) > 230  # transparent half shows page, not black


def test_pdf_page_to_png_uses_selected_page_and_dpi(pdf_file, out_dir):
    dest = _convert(pdf_file, FileType.PNG, out_dir, pdf_page=2, dpi=72)
    with Image.open(dest) as im:
        assert im.size == (612, 792)


@pytest.mark.parametrize("page", [0, 4])
def test_pdf_invalid_page_is_rejected(pdf_file, out_dir, page):
    with pytest.raises(QuickConvertError) as err:
        _convert(pdf_file, FileType.PNG, out_dir, pdf_page=page)
    assert err.value.code is ErrorCode.INVALID_INPUT
    assert not any(out_dir.iterdir())


def test_encrypted_pdf_requires_password(encrypted_pdf, out_dir):
    assert inspect_file(encrypted_pdf).encrypted
    with pytest.raises(QuickConvertError) as err:
        _convert(encrypted_pdf, FileType.PNG, out_dir)
    assert err.value.code is ErrorCode.PASSWORD_REQUIRED


def test_encrypted_pdf_wrong_password(encrypted_pdf, out_dir):
    with pytest.raises(QuickConvertError) as err:
        _convert(encrypted_pdf, FileType.PNG, out_dir, password="nope")
    assert err.value.code is ErrorCode.PASSWORD_REQUIRED
    assert_no_temp_files(out_dir)


def test_encrypted_pdf_with_password(encrypted_pdf, out_dir):
    dest = _convert(encrypted_pdf, FileType.PNG, out_dir, password="hunter2", dpi=72)
    assert dest.exists()


def test_existing_output_is_protected(jpeg_file, out_dir):
    dest = out_dir / "taken.png"
    dest.write_bytes(b"keep me")
    with pytest.raises(QuickConvertError) as err:
        conversion.run(ConversionRequest(jpeg_file, FileType.PNG, dest))
    assert err.value.code is ErrorCode.OUTPUT_EXISTS
    assert dest.read_bytes() == b"keep me"


def test_explicit_overwrite_replaces_output(jpeg_file, out_dir):
    dest = out_dir / "taken.png"
    dest.write_bytes(b"old")
    conversion.run(ConversionRequest(jpeg_file, FileType.PNG, dest, overwrite=True))
    assert inspect_file(dest).file_type is FileType.PNG


def test_output_cannot_replace_source(png_file):
    with pytest.raises(QuickConvertError) as err:
        conversion.run(ConversionRequest(png_file, FileType.PNG, png_file, overwrite=True))
    assert err.value.code in (ErrorCode.OUTPUT_EXISTS, ErrorCode.UNSUPPORTED_PAIR)


def test_disguised_input_is_rejected(tmp_path):
    fake = tmp_path / "not_really.png"
    fake.write_text("hello, I am text")
    with pytest.raises(QuickConvertError) as err:
        inspect_file(fake)
    assert err.value.code is ErrorCode.INVALID_INPUT


def test_truncated_image_fails_cleanly(png_file, out_dir):
    data = png_file.read_bytes()
    broken = png_file.with_name("broken.png")
    broken.write_bytes(data[: len(data) // 2])
    with pytest.raises(QuickConvertError) as err:
        _convert(broken, FileType.JPEG, out_dir)
    assert err.value.code in (ErrorCode.INVALID_INPUT, ErrorCode.CONVERSION_FAILED)
    assert not any(out_dir.iterdir())


def test_extension_is_ignored_in_favor_of_content(jpeg_file, tmp_path):
    renamed = tmp_path / "actually_jpeg.png"
    renamed.write_bytes(jpeg_file.read_bytes())
    info = inspect_file(renamed)
    assert info.file_type is FileType.JPEG
    assert FileType.JPEG not in {c.output_type for c in get_targets(info)}


def test_unsupported_pair(png_file, out_dir):
    with pytest.raises(QuickConvertError) as err:
        _convert(png_file, FileType.PNG, out_dir)
    assert err.value.code is ErrorCode.UNSUPPORTED_PAIR


def test_inapplicable_option_is_rejected(jpeg_file, out_dir):
    with pytest.raises(QuickConvertError) as err:
        _convert(jpeg_file, FileType.PNG, out_dir, quality=80)
    assert err.value.code is ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("opts", [{"quality": 0}, {"quality": 101}])
def test_quality_range(png_file, out_dir, opts):
    with pytest.raises(QuickConvertError):
        _convert(png_file, FileType.JPEG, out_dir, **opts)


def test_pixel_limit_enforced_before_decoding(png_file, out_dir, monkeypatch):
    monkeypatch.setattr(limits, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(QuickConvertError) as err:
        _convert(png_file, FileType.JPEG, out_dir)
    assert err.value.code is ErrorCode.RESOURCE_LIMIT


def test_render_limit_enforced(pdf_file, out_dir, monkeypatch):
    monkeypatch.setattr(limits, "MAX_RENDER_PIXELS", 10_000)
    with pytest.raises(QuickConvertError) as err:
        _convert(pdf_file, FileType.PNG, out_dir)
    assert err.value.code is ErrorCode.RESOURCE_LIMIT
    assert_no_temp_files(out_dir)


def test_unicode_paths(tmp_path, jpeg_file):
    folder = tmp_path / "صور ✓ 写真"
    folder.mkdir()
    src = folder / "صورة.jpg"
    src.write_bytes(jpeg_file.read_bytes())
    dest = folder / "نتيجة.png"
    conversion.run(ConversionRequest(src, FileType.PNG, dest))
    assert inspect_file(dest).file_type is FileType.PNG


def test_wrong_extension_for_target(jpeg_file, out_dir):
    with pytest.raises(QuickConvertError) as err:
        conversion.run(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "x.jpg"))
    assert err.value.code is ErrorCode.INVALID_INPUT


def test_corrupt_pdf_is_rejected(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4\n this is not really a pdf")
    with pytest.raises(QuickConvertError) as err:
        inspect_file(bad)
    assert err.value.code is ErrorCode.INVALID_INPUT
