"""PyInstaller entry point for both QuickConvert.exe (windowed) and quickconvert-cli.exe."""

import sys

from app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
