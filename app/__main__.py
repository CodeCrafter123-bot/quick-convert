"""Entry point.

    python -m app [FILE]          open the desktop app (optionally with a file loaded)

Command-line tools over the same conversion core:
    python -m app inspect FILE
    python -m app convert FILE --to png [--out PATH] [--quality N] [--dpi N] [--page N]
    python -m app edit FILE --to png [--crop L,T,R,B] [--bg #RRGGBB --padding N --radius N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.models import ConversionOptions, ConversionRequest, FileType, QuickConvertError
from app.services import conversion
from app.services.capabilities import get_targets
from app.services.editing import BackgroundOptions, EditSpec, export_edit
from app.services.inspection import inspect_file
from app.services.output import default_output_path


def _file_type(value: str) -> FileType:
    value = value.lower().lstrip(".")
    value = "jpeg" if value == "jpg" else value
    try:
        return FileType(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"unknown format '{value}'")


def _color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("use #RRGGBB")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _box(value: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("use LEFT,TOP,RIGHT,BOTTOM")
    return tuple(parts)  # type: ignore[return-value]


COMMANDS = {"inspect", "convert", "edit"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or (len(argv) == 1 and argv[0] not in COMMANDS and not argv[0].startswith("-")):
        from app.ui.app import run_gui

        return run_gui(initial_file=Path(argv[0]) if argv else None)

    parser = argparse.ArgumentParser(prog="quickconvert")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="show file type and supported targets")
    p.add_argument("file", type=Path)

    p = sub.add_parser("convert", help="convert a file")
    p.add_argument("file", type=Path)
    p.add_argument("--to", type=_file_type, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--quality", type=int)
    p.add_argument("--dpi", type=int)
    p.add_argument("--page", type=int)
    p.add_argument("--bg", type=_color, help="background for transparent -> JPEG")
    p.add_argument("--password")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("edit", help="crop and/or add a background")
    p.add_argument("file", type=Path)
    p.add_argument("--to", type=_file_type, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--crop", type=_box)
    p.add_argument("--bg", type=_color)
    p.add_argument("--padding", type=int, default=64)
    p.add_argument("--radius", type=int, default=0)
    p.add_argument("--quality", type=int)
    p.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            info = inspect_file(args.file)
            print(f"type: {info.file_type.value}  size: {info.size_bytes:,} bytes")
            if info.width:
                print(f"dimensions: {info.width}x{info.height}")
            if info.file_type is FileType.PDF:
                print("pages: " + ("(encrypted)" if info.encrypted else str(info.page_count)))
            for cap in get_targets(info):
                state = "ok" if cap.available else f"unavailable: {cap.unavailable_reason}"
                print(f"  -> {cap.output_type.value:<5} {state}")
            return 0

        out = args.out or default_output_path(args.file, args.to.extension,
                                              suffix="" if args.command == "convert" else "-edited")
        if args.command == "convert":
            opts = ConversionOptions(quality=args.quality, dpi=args.dpi, pdf_page=args.page,
                                     background_color=args.bg, password=args.password)
            result = conversion.run(ConversionRequest(args.file, args.to, out, opts, args.overwrite))
            for w in result.warnings:
                print(f"warning: {w}")
        else:
            bg = (BackgroundOptions(args.bg, args.padding, args.radius)
                  if args.bg is not None else None)
            export_edit(args.file, EditSpec(args.crop, bg), args.to, out,
                        quality=args.quality, overwrite=args.overwrite)
        print(f"saved: {out}")
        return 0
    except QuickConvertError as exc:
        print(f"error [{exc.code.value}]: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
