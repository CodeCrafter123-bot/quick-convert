"""Fixtures are generated in tmp dirs so the repo needs no binary sample files."""

from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter  # test-only dependency


@pytest.fixture
def jpeg_file(tmp_path: Path) -> Path:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (320, 200), (200, 50, 50)).save(path, "JPEG")
    return path


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    path = tmp_path / "opaque.png"
    Image.new("RGB", (300, 150), (20, 120, 220)).save(path, "PNG")
    return path


@pytest.fixture
def transparent_png(tmp_path: Path) -> Path:
    """Left half fully transparent, right half opaque red."""
    path = tmp_path / "transparent.png"
    im = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    im.paste((255, 0, 0, 255), (100, 0, 200, 100))
    im.save(path, "PNG")
    return path


@pytest.fixture
def webp_file(tmp_path: Path) -> Path:
    path = tmp_path / "image.webp"
    Image.new("RGB", (240, 160), (10, 200, 10)).save(path, "WEBP")
    return path


def _make_pdf(path: Path, pages: int, password: str | None = None) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)  # US Letter
    if password:
        writer.encrypt(password, "owner", algorithm="RC4-128")
    with path.open("wb") as f:
        writer.write(f)
    return path


@pytest.fixture
def pdf_file(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "doc.pdf", pages=3)


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "secret.pdf", pages=1, password="hunter2")


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


def assert_no_temp_files(directory: Path) -> None:
    leftovers = list(directory.glob(".qc-tmp-*"))
    assert not leftovers, f"temporary files left behind: {leftovers}"


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run, torn down before Python exits.

    Qt widgets still alive when the interpreter shuts down can be destroyed after
    the QApplication, which crashes the process even though every test passed.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
