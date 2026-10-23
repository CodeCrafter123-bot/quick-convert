"""Regenerate docs/screenshots/*.png from the real widgets.

    .venv\\Scripts\\python packaging\\make_screenshots.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = ROOT / "docs" / "screenshots"


def sample_image(path: Path) -> None:
    """A simple landscape: sky gradient, sun, two mountain ranges, a lake."""
    im = Image.new("RGB", (1200, 800))
    d = ImageDraw.Draw(im)
    for y in range(800):
        t = y / 800
        d.line((0, y, 1200, y), fill=(int(120 + 110 * t), int(170 + 60 * t), int(235 - 20 * t)))
    d.ellipse((800, 120, 960, 280), fill=(255, 214, 102))
    d.polygon([(0, 560), (220, 300), (420, 520), (620, 260), (900, 540), (1200, 380), (1200, 800),
               (0, 800)], fill=(94, 129, 172))
    d.polygon([(0, 640), (300, 470), (560, 620), (840, 480), (1200, 640), (1200, 800), (0, 800)],
              fill=(52, 92, 70))
    d.rectangle((0, 690, 1200, 800), fill=(64, 140, 200))
    im.save(path, quality=92)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from app.models import BackgroundOptions, ConversionRequest, EditSpec, FileType
    from app.storage.settings import UserSettings
    from app.ui.background_dialog import BackgroundDialog
    from app.ui.crop_dialog import CropDialog
    from app.ui.drop_bubble import DropBubble
    from app.ui.main_window import MainWindow
    from app.ui.options_dialog import OptionsDialog
    from app.ui.widgets import pil_to_pixmap

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "holiday-photo.jpg"
        sample_image(src)
        w = MainWindow(UserSettings())
        w.resize(680, 640)
        w.show()
        w.load_file(src)
        job = w.submit(ConversionRequest(src, FileType.PNG, Path(tmp) / "holiday-photo.png"))
        w.jobs.wait(job, timeout=30)
        for _ in range(20):
            app.processEvents()

        def grab(widget, name):
            widget.show()
            app.processEvents()
            widget.grab().save(str(OUT / name))
            print("wrote", OUT / name)

        grab(w, "main-window.png")
        wheel = w.open_wheel(QPoint(700, 400))
        wheel.current = 0
        grab(wheel, "action-wheel.png")
        wheel.close()

        cap = next(c for c in w.targets() if c.output_type is FileType.WEBP)
        grab(OptionsDialog(w.info, cap, w.settings, w), "convert-options.png")

        spec = EditSpec((300, 100, 900, 700), BackgroundOptions((255, 236, 210), 64, 48))
        crop = CropDialog(pil_to_pixmap(w.preview_image), (1200, 800), spec.crop_box, w)
        crop.resize(720, 540)
        grab(crop, "crop-dialog.png")
        grab(BackgroundDialog(w.preview_image, (1200, 800), spec, w), "background-dialog.png")

        w.set_edit(spec)
        grab(w, "pending-edits.png")

        bubble = DropBubble()
        bubble.hot = True
        grab(bubble, "drop-bubble.png")
        w.shutdown()


if __name__ == "__main__":
    main()
