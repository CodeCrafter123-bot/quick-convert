"""Built-in acceptance check: every advertised pair + edits, run against *this* build.

Used to validate the packaged app on a clean machine (report section 7):
    QuickConvert-cli.exe selftest --report result.json
Sample inputs are generated on the fly, so nothing needs to ship with the app.
"""

from __future__ import annotations

import json
import platform
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

from app import __version__
from app.models import (
    BackgroundOptions,
    ConversionOptions,
    ConversionRequest,
    EditSpec,
    ErrorCode,
    FileType,
    QuickConvertError,
)
from app.services import conversion
from app.services.capabilities import all_capabilities
from app.services.inspection import inspect_file


def _make_fixtures(folder: Path) -> dict[FileType, Path]:
    rgba = Image.new("RGBA", (640, 400), (0, 0, 0, 0))
    rgba.paste((30, 144, 255, 255), (80, 50, 560, 350))
    rgb = rgba.convert("RGB")
    paths = {FileType.JPEG: folder / "sample.jpg", FileType.PNG: folder / "sample.png",
             FileType.WEBP: folder / "sample.webp", FileType.PDF: folder / "sample.pdf"}
    rgb.save(paths[FileType.JPEG], "JPEG")
    rgba.save(paths[FileType.PNG], "PNG")
    rgba.save(paths[FileType.WEBP], "WEBP")
    pages = [Image.new("RGB", (612, 792), color) for color in ("white", "lightyellow", "lightblue")]
    pages[0].save(paths[FileType.PDF], "PDF", save_all=True, append_images=pages[1:], resolution=72)
    return paths


def _check(name: str, fn) -> dict:
    started = time.perf_counter()
    try:
        detail = fn() or ""
        status = "pass"
    except Exception as exc:  # report every failure, keep going
        status = "fail"
        detail = f"{type(exc).__name__}: {getattr(exc, 'message', exc)}"
    return {"test": name, "status": status, "detail": detail,
            "ms": round((time.perf_counter() - started) * 1000, 1)}


def run_selftest() -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="quickconvert-selftest-") as tmp:
        folder = Path(tmp)
        fixtures = _make_fixtures(folder)
        out = folder / "out"
        out.mkdir()

        for cap in all_capabilities():
            name = f"{cap.input_type.value} -> {cap.output_type.value}"

            def convert(cap=cap, name=name):
                if not cap.available:
                    raise RuntimeError(cap.unavailable_reason)
                dest = out / f"{cap.input_type.value}_to{cap.output_type.extension}"
                opts = ConversionOptions(pdf_page=2) if cap.input_type is FileType.PDF else ConversionOptions()
                result = conversion.run(ConversionRequest(fixtures[cap.input_type], cap.output_type,
                                                          dest, opts))
                info = inspect_file(dest)
                assert info.file_type is cap.output_type, info.file_type
                size = f"{info.width}x{info.height}" if info.width else f"{info.page_count} page(s)"
                return f"{size}, {result.output_sizes[0]:,} bytes"

            results.append(_check(name, convert))

        def edit():
            spec = EditSpec((80, 50, 560, 350), BackgroundOptions((255, 236, 210), 40, 24))
            dest = out / "edited.png"
            conversion.run(ConversionRequest(fixtures[FileType.PNG], FileType.PNG, dest, edit=spec))
            with Image.open(dest) as im:
                assert im.size == (560, 380), im.size
            return "crop + background -> 560x380"

        def rejects_corrupt():
            bad = folder / "corrupt.png"
            bad.write_bytes(fixtures[FileType.PNG].read_bytes()[:100])
            try:
                conversion.run(ConversionRequest(bad, FileType.JPEG, out / "corrupt.jpg"))
            except QuickConvertError as exc:
                assert exc.code in (ErrorCode.INVALID_INPUT, ErrorCode.CONVERSION_FAILED)
                assert not (out / "corrupt.jpg").exists()
                return f"rejected with {exc.code.value}"
            raise AssertionError("corrupt input was accepted")

        def protects_existing():
            dest = out / "png_to.jpg"  # created by the png -> jpeg check above
            before = dest.read_bytes()
            try:
                conversion.run(ConversionRequest(fixtures[FileType.PNG], FileType.JPEG, dest))
            except QuickConvertError as exc:
                assert exc.code is ErrorCode.OUTPUT_EXISTS and dest.read_bytes() == before
                return "existing output kept"
            raise AssertionError("existing output was overwritten")

        results.append(_check("edit: crop + background", edit))
        results.append(_check("rejects corrupt input", rejects_corrupt))
        results.append(_check("protects existing output", protects_existing))
        leftovers = [p.name for p in out.glob(".qc-tmp-*")]
        results.append(_check("no temporary files left",
                              lambda: (_ for _ in ()).throw(AssertionError(leftovers)) if leftovers
                              else "clean"))

    failed = [r for r in results if r["status"] != "pass"]
    return {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "os": platform.platform(),
        "python": platform.python_version(),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }


def format_report(report: dict) -> str:
    lines = [f"QuickConvert {report['version']} self-test on {report['os']} "
             f"({'packaged' if report['frozen'] else 'development'} build)"]
    for r in report["results"]:
        mark = "PASS" if r["status"] == "pass" else "FAIL"
        lines.append(f"  [{mark}] {r['test']:<28} {r['ms']:>7.1f} ms  {r['detail']}")
    lines.append(f"{report['passed']} passed, {report['failed']} failed")
    return "\n".join(lines)


def main(report_path: Path | None) -> int:
    report = run_selftest()
    if report_path is not None:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(format_report(report))
    return 0 if report["failed"] == 0 else 1
