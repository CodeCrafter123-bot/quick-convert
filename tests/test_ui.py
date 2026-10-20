"""Off-screen smoke tests of the desktop workflow (no visible window needed)."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.models import ConversionRequest, FileType, JobStatus  # noqa: E402
from app.storage.settings import UserSettings  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.options_dialog import OptionsDialog  # noqa: E402
from app.ui.radial_menu import RadialItem, RadialMenu  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    w = MainWindow(UserSettings())
    w.warnings = warnings
    yield w
    w.close()


def wait_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def press(widget, key):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def test_load_image_shows_details_and_targets(window, png_file):
    assert window.load_file(png_file)
    assert window.file_panel.isVisibleTo(window)
    assert "300 × 150" in window.details.text()
    labels = [item.label for item in window.wheel_items()]
    assert sorted(labels) == ["JPEG", "PDF", "WebP"]
    assert not window.thumb.pixmap().isNull()


def test_load_pdf_shows_pages(window, pdf_file):
    assert window.load_file(pdf_file)
    assert "3 page(s)" in window.details.text()
    assert sorted(i.label for i in window.wheel_items()) == ["JPEG", "PNG"]


def test_invalid_file_shows_message(window, tmp_path):
    bad = tmp_path / "x.png"
    bad.write_text("nope")
    assert not window.load_file(bad)
    assert window.warnings and "not a supported file type" in window.warnings[0]


def test_wheel_keyboard_navigation_and_activation(qapp):
    items = [RadialItem("A", "a"), RadialItem("B", "b", enabled=False), RadialItem("C", "c")]
    wheel = RadialMenu(items, "file.png")
    chosen = []
    wheel.triggered.connect(chosen.append)
    wheel.popup_at(QPoint(5, 5))  # near the corner: must be clamped on-screen
    screen = qapp.primaryScreen().availableGeometry()
    assert screen.contains(wheel.geometry())
    assert wheel.current == 0
    press(wheel, Qt.Key.Key_Right)
    assert wheel.current == 2  # skips the disabled item
    press(wheel, Qt.Key.Key_Return)
    assert chosen == ["c"]


def test_disabled_wheel_item_does_not_trigger(qapp):
    wheel = RadialMenu([RadialItem("A", "a", enabled=False)])
    chosen = []
    wheel.triggered.connect(chosen.append)
    wheel.popup_at(QPoint(400, 400))
    wheel.activate(0)
    assert chosen == []


def test_options_dialog_shows_only_applicable_fields(window, pdf_file, out_dir):
    window.load_file(pdf_file)
    cap = next(c for c in window.targets() if c.output_type is FileType.PNG)
    dialog = OptionsDialog(window.info, cap, window.settings, window)
    assert dialog.page is not None and dialog.page.maximum() == 3
    assert dialog.dpi is not None
    assert dialog.quality is None and dialog.background is None
    assert dialog.password is None  # not encrypted
    dialog.page.setValue(2)
    dialog.dpi.setValue(72)
    dialog.destination.setText(str(out_dir / "p2.png"))
    req = dialog.request()
    assert req.options.pdf_page == 2 and req.options.dpi == 72


def test_full_workflow_creates_job_row_and_output(window, transparent_png, out_dir):
    window.load_file(transparent_png)
    dest = out_dir / "flat.jpg"
    job_id = window.submit(ConversionRequest(transparent_png, FileType.JPEG, dest))
    assert job_id
    assert wait_until(lambda: (j := window.jobs.get_job(job_id)) and j.status.is_final)
    assert wait_until(lambda: window.rows[job_id].open_btn.isVisibleTo(window.rows[job_id]))
    row = window.rows[job_id]
    assert window.jobs.get_job(job_id).status is JobStatus.COMPLETED
    assert "Saved" in row.status.text() and "transparency" in row.status.text()
    assert not row.cancel_btn.isVisibleTo(row)
    assert dest.exists()


def test_submit_error_is_reported(window, png_file, out_dir):
    existing = out_dir / "taken.jpg"
    existing.write_bytes(b"x")
    assert window.submit(ConversionRequest(png_file, FileType.JPEG, existing)) is None
    assert "already exists" in window.warnings[-1]
