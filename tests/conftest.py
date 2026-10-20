"""Fixtures are generated in tmp dirs so the repo needs no binary sample files."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image


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


def _make_pdf(path: Path, pages: int, **save_kwargs) -> Path:
    with pymupdf.open() as doc:
        for i in range(pages):
            page = doc.new_page(width=612, height=792)  # US Letter
            page.insert_text((72, 72), f"Page {i + 1}")
        doc.save(path, **save_kwargs)
    return path


@pytest.fixture
def pdf_file(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "doc.pdf", pages=3)


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "secret.pdf", pages=1, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                     user_pw="hunter2", owner_pw="owner")


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


def assert_no_temp_files(directory: Path) -> None:
    leftovers = list(directory.glob(".qc-tmp-*"))
    assert not leftovers, f"temporary files left behind: {leftovers}"
