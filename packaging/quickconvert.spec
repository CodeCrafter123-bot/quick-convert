# PyInstaller spec: one folder, two executables sharing the same files.
#   QuickConvert.exe       - the desktop app (no console window)
#   quickconvert-cli.exe   - command line + `selftest`, for validation and scripting
# Build with packaging/build.ps1 (it creates build/quickconvert.ico and build/version_info.txt first).

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from app import __version__  # noqa: E402

block_cipher = None


def license_files():
    """Ship each bundled package's license texts under licenses/<package>/."""
    from importlib.metadata import distribution

    out = []
    for name in ("pillow", "pypdfium2", "PySide6_Essentials", "shiboken6"):
        dist = distribution(name)
        for f in dist.files or []:
            if "licen" in str(f).lower() or "copying" in str(f).lower():
                src = Path(dist.locate_file(f))
                if src.is_file():
                    rel = Path(*[p for p in f.parts[1:-1]])  # path inside the dist-info folder
                    out.append((str(src), str(Path("licenses") / name / rel)))
    return out


a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "docs" / "THIRD_PARTY_NOTICES.md"), "."),
        (str(ROOT / "docs" / "USER_GUIDE.md"), "."),
    ] + license_files(),
    hiddenimports=["app.selftest", "app.ui.app"],
    excludes=[
        # Development-only or unused; keeps the bundle small.
        "tkinter", "pytest", "pypdf", "PyInstaller", "pydoc", "unittest",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL", "PySide6.QtSql",
        "PySide6.QtTest", "PySide6.QtDBus", "PySide6.QtPdf",
    ],
    noarchive=False,
)

# Drop large pieces the app never uses (verified by the packaged self-test in build.ps1):
DROP = (
    "opengl32sw.dll",          # software OpenGL fallback; QuickConvert uses no OpenGL (20 MB)
    "plugins\\tls",            # Qt TLS backends; QuickConvert does no networking over TLS
    "libcrypto-3-x64.dll",     # OpenSSL copy used only by the Qt TLS backend
    "libssl-3-x64.dll",
    "pil\\_avif",              # AVIF codec; AVIF isn't a supported format (7.5 MB)
    "pyside6\\translations",   # Qt UI translations; the app is English only
)


def keep(entry):
    path = entry[0].replace("/", "\\").lower()
    return not any(d.lower() in path for d in DROP)


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

common = dict(
    exclude_binaries=True,
    debug=False,
    strip=False,
    upx=False,  # UPX-packed binaries trigger antivirus false positives
    icon=str(ROOT / "build" / "quickconvert.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
)

gui = EXE(pyz, a.scripts, [], name="QuickConvert", console=False, **common)
cli = EXE(pyz, a.scripts, [], name="quickconvert-cli", console=True, **common)

coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="QuickConvert")
