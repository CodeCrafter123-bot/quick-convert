"""Render the in-code app icon to a multi-size .ico for the Windows executable."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ui.icon import _render  # noqa: E402


def main(out: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    _render(256).save(buf, "PNG")
    out.parent.mkdir(parents=True, exist_ok=True)
    import io

    Image.open(io.BytesIO(bytes(buf.data()))).save(
        out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
