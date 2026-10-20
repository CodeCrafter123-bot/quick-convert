"""Windows-specific pieces: input-state polling and the Explorer "Send to" shortcut.

Nothing here installs hooks or injects into other processes. Input state is read
with GetAsyncKeyState; the shortcut is created through the documented WScript.Shell
COM object, with every path passed as an environment variable (never interpolated
into a command line).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

VK_LBUTTON, VK_RBUTTON, VK_SHIFT = 0x01, 0x02, 0x10
SM_SWAPBUTTON = 23
SHORTCUT_NAME = "QuickConvert.lnk"


def input_state() -> tuple[bool, bool]:
    """(primary mouse button down, Shift down), from the physical device state."""
    import ctypes

    user32 = ctypes.windll.user32
    # GetAsyncKeyState reports physical buttons; left-handed setups swap them.
    button = VK_RBUTTON if user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
    return (bool(user32.GetAsyncKeyState(button) & 0x8000),
            bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000))


# --- Explorer "Send to" ------------------------------------------------------------

def send_to_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "SendTo"


def launch_command() -> tuple[Path, str, Path]:
    """(target, arguments, working dir) that start QuickConvert without a console."""
    if getattr(sys, "frozen", False):  # packaged build (Phase 6)
        exe = Path(sys.executable)
        return exe, "", exe.parent
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    project_root = Path(__file__).resolve().parents[2]
    return (pythonw if pythonw.exists() else python), "-m app", project_root


def shortcut_path(directory: Path | None = None) -> Path:
    return (directory or send_to_dir()) / SHORTCUT_NAME


def is_send_to_installed(directory: Path | None = None) -> bool:
    return shortcut_path(directory).exists()


_CREATE_SHORTCUT = (
    "$ErrorActionPreference = 'Stop';"
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:QC_LNK);"
    "$s.TargetPath = $env:QC_TARGET;"
    "$s.Arguments = $env:QC_ARGS;"
    "$s.WorkingDirectory = $env:QC_DIR;"
    "$s.Description = 'Convert or edit with QuickConvert';"
    "$s.Save()"
)


def install_send_to(directory: Path | None = None) -> Path:
    if not IS_WINDOWS:
        raise OSError("The Send to menu is only available on Windows.")
    link = shortcut_path(directory)
    link.parent.mkdir(parents=True, exist_ok=True)
    target, args, workdir = launch_command()
    env = {**os.environ, "QC_LNK": str(link), "QC_TARGET": str(target), "QC_ARGS": args,
           "QC_DIR": str(workdir)}
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CREATE_SHORTCUT],
        env=env, capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 or not link.exists():
        raise OSError(f"Could not create the shortcut: {result.stderr.strip()[:300]}")
    return link


def uninstall_send_to(directory: Path | None = None) -> None:
    shortcut_path(directory).unlink(missing_ok=True)
