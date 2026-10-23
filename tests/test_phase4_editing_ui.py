"""Phase 4: crop/background dialogs, edit export as a job, EXIF-rotated sources."""

from __future__ import annotations

import os

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.models import (  # noqa: E402
    BackgroundOptions,
    ConversionOptions,
    ConversionRequest,
    EditSpec,
    ErrorCode,
    FileType,
    JobStatus,
    QuickConvertError,
)
from app.services import conversion  # noqa: E402
from app.services.editing import export_edit, output_size, preview_edit, render_edit  # noqa: E402
from app.services.inspection import inspect_file  # noqa: E402
from app.storage.settings import UserSettings  # noqa: E402
from app.ui.background_dialog import BackgroundDialog  # noqa: E402
from app.ui.crop_dialog import CropDialog  # noqa: E402
from app.ui.main_window import ACTION_BACKGROUND, ACTION_CROP, MainWindow  # noqa: E402
from app.ui.options_dialog import ExportDialog  # noqa: E402
from app.ui.widgets import pil_to_pixmap  # noqa: E402
from tests.conftest import assert_no_temp_files  # noqa: E402
from tests.test_ui import wait_until  # noqa: E402


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    w = MainWindow(UserSettings())
    yield w
    w.close()


@pytest.fixture
def rotated_jpeg(tmp_path):
    """Stored 400x200 but EXIF says rotate 90°, so it displays as 200x400."""
    path = tmp_path / "phone.jpg"
    im = Image.new("RGB", (400, 200), (255, 0, 0))
    im.paste((0, 0, 255), (0, 0, 100, 200))  # blue strip on the stored left
    exif = im.getexif()
    exif[0x0112] = 6
    im.save(path, exif=exif.tobytes())
    return path


def mouse(widget, kind, x, y):
    ev = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    {QMouseEvent.Type.MouseButtonPress: widget.mousePressEvent,
     QMouseEvent.Type.MouseMove: widget.mouseMoveEvent,
     QMouseEvent.Type.MouseButtonRelease: widget.mouseReleaseEvent}[kind](ev)


# --- EXIF orientation ---------------------------------------------------------

def test_inspection_reports_displayed_size_for_rotated_photo(rotated_jpeg):
    info = inspect_file(rotated_jpeg)
    assert (info.width, info.height) == (200, 400)


def test_crop_on_rotated_photo_uses_displayed_coordinates(rotated_jpeg, out_dir):
    # Bottom half of the displayed portrait image is valid and must not be rejected.
    dest = export_edit(rotated_jpeg, EditSpec(crop_box=(0, 200, 200, 400)), FileType.PNG,
                       out_dir / "bottom.png")
    with Image.open(dest) as im:
        assert im.size == (200, 200)


# --- edit export as a job -------------------------------------------------------

def test_edit_export_runs_as_job(window, png_file, out_dir):
    spec = EditSpec((0, 0, 100, 100), BackgroundOptions((0, 0, 0), 10, 0))
    req = ConversionRequest(png_file, FileType.WEBP, out_dir / "e.webp",
                            ConversionOptions(quality=80), edit=spec)
    job = window.jobs.wait(window.submit(req), timeout=30)
    assert job.status is JobStatus.COMPLETED
    with Image.open(out_dir / "e.webp") as im:
        assert im.size == (120, 120)
    assert_no_temp_files(out_dir)


def test_edit_cannot_export_pdf(png_file, out_dir):
    req = ConversionRequest(png_file, FileType.PDF, out_dir / "e.pdf", edit=EditSpec((0, 0, 5, 5)))
    with pytest.raises(QuickConvertError) as err:
        conversion.run(req)
    assert err.value.code is ErrorCode.UNSUPPORTED_PAIR


def test_edit_rejects_inapplicable_option(png_file, out_dir):
    req = ConversionRequest(png_file, FileType.PNG, out_dir / "e.png",
                            ConversionOptions(quality=50), edit=EditSpec((0, 0, 5, 5)))
    with pytest.raises(QuickConvertError) as err:
        conversion.validate(req)
    assert err.value.code is ErrorCode.INVALID_INPUT


def test_edit_same_format_as_source_is_allowed(png_file, out_dir):
    dest = export_edit(png_file, EditSpec((0, 0, 10, 10)), FileType.PNG, out_dir / "same.png")
    assert dest.exists()


def test_preview_matches_export_proportions(jpeg_file):
    spec = EditSpec((40, 20, 240, 120), BackgroundOptions((9, 9, 9), 30, 12))
    full = render_edit(jpeg_file, spec)
    small = Image.open(jpeg_file).convert("RGB").resize((160, 100))
    preview = preview_edit(small, (320, 200), spec)
    assert full.size == output_size(320, 200, spec) == (260, 160)
    assert preview.size == (130, 80)  # exactly half


# --- crop dialog ------------------------------------------------------------------

def test_crop_dialog_maps_scaled_view_back_to_original_pixels(qapp):
    # A 2000x1000 original shown via a 400x200 preview inside a 400x200 widget (scale 0.2).
    preview = pil_to_pixmap(Image.new("RGB", (400, 200), "gray"))
    dialog = CropDialog(preview, (2000, 1000))
    widget = dialog.crop
    widget.resize(500, 400)  # letterboxed: scale 0.25, image offset vertically
    assert widget._scale_offset() == (0.25, 0.0, 75.0)
    widget.set_box((0, 0, 10, 10))  # shrink so the drag starts outside the selection
    start, end = widget.to_view(200, 100), widget.to_view(1200, 600)
    assert (start.x(), start.y(), end.x(), end.y()) == (50, 100, 300, 225)
    mouse(widget, QMouseEvent.Type.MouseButtonPress, 50, 100)
    mouse(widget, QMouseEvent.Type.MouseMove, 300, 225)
    mouse(widget, QMouseEvent.Type.MouseButtonRelease, 300, 225)
    assert dialog.box() == (200, 100, 1200, 600)
    assert dialog.size_label.text() == "1000 × 500 px"


def test_crop_dialog_full_image_means_no_crop(qapp):
    dialog = CropDialog(pil_to_pixmap(Image.new("RGB", (40, 20))), (400, 200))
    assert dialog.box() is None
    dialog.crop.set_box((10, 10, 100, 100))
    dialog.reset()
    assert dialog.box() is None


def test_crop_dialog_aspect_lock(qapp):
    dialog = CropDialog(pil_to_pixmap(Image.new("RGB", (400, 200))), (400, 200))
    dialog.aspect.setCurrentText("1:1")
    left, top, right, bottom = dialog.box()
    assert right - left == bottom - top == 200


def test_crop_dialog_keyboard_moves_selection(qapp):
    from PySide6.QtGui import QKeyEvent

    dialog = CropDialog(pil_to_pixmap(Image.new("RGB", (400, 200))), (400, 200), (10, 10, 50, 50))
    dialog.crop.resize(400, 200)
    dialog.crop.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right,
                                        Qt.KeyboardModifier.NoModifier))
    assert dialog.box() == (11, 10, 51, 50)


# --- background dialog ----------------------------------------------------------

def test_background_dialog_keeps_crop_and_reports_size(qapp):
    start = EditSpec(crop_box=(0, 0, 100, 50))
    dialog = BackgroundDialog(Image.new("RGB", (400, 200)), (400, 200), start)
    dialog.padding.setValue(25)
    dialog.radius.setValue(8)
    dialog.color.set_color((1, 2, 3))
    spec = dialog.spec()
    assert spec.crop_box == (0, 0, 100, 50)
    assert spec.background == BackgroundOptions((1, 2, 3), 25, 8)
    assert dialog.size_label.text() == "150 × 100 px"
    assert not dialog.preview.pixmap().isNull()


# --- main window workflow ---------------------------------------------------------

def test_edit_workflow_in_main_window(window, jpeg_file, out_dir, monkeypatch):
    window.load_file(jpeg_file)
    actions = [i.data for i in window.wheel_items()]
    assert ACTION_CROP in actions and ACTION_BACKGROUND in actions
    assert not window.edits_bar.isVisibleTo(window)

    window.set_edit(EditSpec((0, 0, 100, 80), BackgroundOptions((255, 255, 255), 10, 0)))
    assert window.edits_bar.isVisibleTo(window)
    assert "Crop 100 × 80" in window.edits_label.text()
    assert "Result 120 × 100" in window.edits_label.text()

    dialog = ExportDialog(window.info, window.edit, window.settings, window)
    assert dialog.target() is FileType.JPEG  # keeps the source format by default
    dialog.format.setCurrentText("PNG")
    assert not dialog.quality.isEnabled()
    assert dialog.destination.edit.text().endswith("photo-edited.png")
    dialog.destination.edit.setText(str(out_dir / "edited.png"))
    job = window.jobs.wait(window.submit(dialog.request()), timeout=30)
    assert job.status is JobStatus.COMPLETED
    assert wait_until(lambda: job.id in window.rows)
    with Image.open(out_dir / "edited.png") as im:
        assert im.size == (120, 100)

    window.discard_edits()
    assert not window.edits_bar.isVisibleTo(window)
    assert window.edit.is_empty


def test_loading_new_file_clears_edits(window, jpeg_file, png_file):
    window.load_file(jpeg_file)
    window.set_edit(EditSpec((0, 0, 10, 10)))
    window.load_file(png_file)
    assert window.edit.is_empty


def test_pdf_has_no_edit_actions(window, pdf_file):
    window.load_file(pdf_file)
    assert not window.can_edit()
    assert all(isinstance(i.data, object) and i.data not in (ACTION_CROP, ACTION_BACKGROUND)
               for i in window.wheel_items())
