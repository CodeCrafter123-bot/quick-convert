# Third-party notices

QuickConvert bundles the following open-source components. Their full license texts ship with
the app in the `licenses\` folder next to `QuickConvert.exe` (and in each package's
`*.dist-info` folder in a development environment).

| Component | Version | License | Source |
|---|---|---|---|
| Python runtime | 3.14 | PSF-2.0 | https://www.python.org |
| Qt for Python (PySide6-Essentials, shiboken6) and Qt 6 | 6.12.0 | LGPL-3.0-only (also GPL-2.0/3.0) | https://pyside.org · https://download.qt.io/official_releases/qt/ |
| Pillow | 13.0.0 | MIT-CMU (HPND) | https://python-pillow.org |
| pypdfium2 | 5.14.0 | Apache-2.0 or BSD-3-Clause | https://github.com/pypdfium2-team/pypdfium2 |
| PDFium (binary from pdfium-binaries) | 156.0.8076.0 | BSD-3-Clause, Apache-2.0 | https://pdfium.googlesource.com/pdfium |
| PDFium dependencies: FreeType, libjpeg-turbo, libpng, zlib, OpenJPEG, Little CMS, ICU, Abseil, AGG 2.3, fast_float, simdutf, LLVM libc | bundled in PDFium | FreeType License, IJG/BSD-3, libpng, zlib, BSD-2, MIT, Unicode, Apache-2.0, AGG, MIT/Apache, Apache-2.0 with LLVM exception | see `licenses\pypdfium2\` |

## LGPL (Qt / PySide6)

Qt and PySide6 are used under the GNU Lesser General Public License v3. They are included as
separate, unmodified dynamic libraries (`PySide6\*.pyd`, `Qt6*.dll`) in the application folder,
so you may replace them with your own compatible build. The source code for these libraries is
available from the links above; on request, the exact versions used for a release can be provided.

QuickConvert's own source code is available at https://github.com/CodeCrafter123-bot/quick-convert.
