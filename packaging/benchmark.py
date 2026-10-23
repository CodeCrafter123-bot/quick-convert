"""Time and peak memory of large conversions, each case in a fresh process (Windows).

    .venv\\Scripts\\python packaging\\benchmark.py
Prints a Markdown table for docs/TEST_REPORT.md.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = {
    "24 MP photo JPEG → PNG": ("24mp.jpg", "png", {}, None),
    "24 MP photo JPEG → WebP (q90)": ("24mp.jpg", "webp", {"quality": 90}, None),
    "24 MP photo JPEG → PDF": ("24mp.jpg", "pdf", {}, None),
    "12 MP transparent PNG → JPEG": ("12mp.png", "jpeg", {}, None),
    "PDF page → PNG at 300 DPI": ("doc.pdf", "png", {"dpi": 300, "pdf_page": 3}, None),
    "24 MP crop + background → PNG": ("24mp.jpg", "png", {}, "edit"),
    "Worst case: 24 MP random noise → PNG": ("noise.jpg", "png", {}, None),
    "Worst case: 24 MP random noise → WebP (q90)": ("noise.jpg", "webp", {"quality": 90}, None),
}


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [(n, ctypes.c_size_t) for n in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


def peak_mb() -> float:
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return c.PeakWorkingSetSize / 2**20


def make_inputs(folder: Path) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    def photo_like(w: int, h: int) -> Image.Image:
        """Smooth gradients, shapes and fine grain: compresses like a real photo."""
        im = Image.linear_gradient("L").resize((w, h)).convert("RGB")
        d = ImageDraw.Draw(im)
        for i in range(40):
            x, y = (i * 7919) % w, (i * 104729) % h
            d.ellipse((x, y, x + w // 6, y + h // 6),
                      fill=((i * 53) % 255, (i * 97) % 255, (i * 31) % 255))
        grain = Image.effect_noise((w, h), 12).convert("RGB")
        return Image.blend(im.filter(ImageFilter.GaussianBlur(6)), grain, 0.08)

    photo_like(6000, 4000).save(folder / "24mp.jpg", quality=90)
    png = photo_like(4000, 3000).convert("RGBA")
    png.putalpha(Image.linear_gradient("L").resize((4000, 3000)))
    png.save(folder / "12mp.png")
    Image.effect_noise((6000, 4000), 60).convert("RGB").save(folder / "noise.jpg", quality=90)
    pages = [Image.new("RGB", (612, 792), "white")] * 5
    pages[0].save(folder / "doc.pdf", "PDF", save_all=True, append_images=pages[1:], resolution=72)


def run_case(folder: Path, name: str) -> None:
    from app.models import (BackgroundOptions, ConversionOptions, ConversionRequest, EditSpec,
                            FileType)
    from app.services import conversion

    src, target, opts, edit = CASES[name]
    target_type = FileType(target)
    spec = EditSpec((500, 500, 5500, 3500), BackgroundOptions((255, 255, 255), 200, 80)) if edit else None
    dest = folder / f"out-{abs(hash(name))}{target_type.extension}"
    before = peak_mb()
    started = time.perf_counter()
    conversion.run(ConversionRequest(folder / src, target_type, dest, ConversionOptions(**opts),
                                     edit=spec))
    print(f"{time.perf_counter() - started:.2f}\t{peak_mb():.0f}\t{before:.0f}")
    dest.unlink()


def main() -> None:
    if len(sys.argv) == 3:  # child process: one case
        run_case(Path(sys.argv[1]), sys.argv[2])
        return
    with tempfile.TemporaryDirectory(prefix="qc-bench-") as tmp:
        folder = Path(tmp)
        make_inputs(folder)
        print("| Case | Time | Peak memory (process) |\n|---|---|---|")
        for name in CASES:
            out = subprocess.run([sys.executable, __file__, str(folder), name], capture_output=True,
                                 text=True, encoding="utf-8", check=True).stdout.strip()
            seconds, peak, start = out.split("\t")
            print(f"| {name} | {float(seconds):.1f} s | {peak} MB (idle: {start} MB) |")


if __name__ == "__main__":
    main()
