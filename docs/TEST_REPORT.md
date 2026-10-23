# Test report: QuickConvert 0.1.0

| | |
|---|---|
| Build | `QuickConvert-0.1.0-win64.zip` (38.8 MB zipped, 86.6 MB unpacked), PyInstaller 6.22.3, one-folder |
| OS | Windows 11 Pro 10.0.26200, 64-bit |
| Hardware | Intel Core i7-1355U (laptop, mains power, *Balanced* power plan), 32 GB RAM |
| Runtime | Python 3.14.3, PySide6-Essentials 6.12.0, Pillow 13.0.0, pypdfium2 5.14.0 (PDFium 156.0.8076.0) |
| Date | 2026-10-20 |

## 1. Automated test suite (development build)

`pytest`: **166 passed, 0 failed**, ~4 s. Test inputs are generated per test, so the repo holds
no binary sample files. UI tests run off-screen.

| Area | File | Tests |
|---|---|---|
| Every supported pair, conversion rules, error handling, limits | `test_conversion.py` | 37 |
| Crop/background engine | `test_editing.py` | 9 |
| Job queue, cancel, safe naming, settings | `test_jobs_and_output.py` | 13 |
| Action wheel geometry | `test_radial_geometry.py` | 20 |
| Crop selection geometry (all handles × ratios × drag points) | `test_crop_geometry.py` | 44 |
| Main window workflow | `test_ui.py` | 8 |
| Crop/background dialogs, edit export, EXIF rotation | `test_phase4_editing_ui.py` | 15 |
| Safe drops, Shift+drag, single instance, Send to, quit | `test_phase5_integration.py` | 20 |

## 2. Acceptance tests (report section 7)

| Test | Expected | Result | Evidence |
|---|---|---|---|
| Transparent PNG → JPEG | Flattened onto chosen color, no black | Pass | `test_transparent_png_to_jpeg_*` |
| JPEG → PNG | Reopens, same dimensions | Pass | `test_jpeg_to_png_keeps_dimensions` |
| Image → PDF | One page, correct aspect ratio, no clipping | Pass | page size checked in points; rendered corners are image pixels |
| PDF page → PNG | Selected page at configured DPI; invalid page rejected | Pass | 612×792 pt at 72 DPI → 612×792 px; pages 0 and 4 of 3 rejected |
| Crop at scaled preview | Saved crop matches selection in original pixels | Pass | 2000×1000 source shown at 0.25×; drag maps to exactly (200,100,1200,600) |
| Add background | Canvas size, padding and corners match preview | Pass | preview and export compared pixel for pixel |
| Existing output name | New name suggested or explicit overwrite | Pass | `name (2).png` naming; existing file untouched without confirmation |
| Corrupt / disguised input | Fails safely with clear message | Pass | text renamed `.png`, truncated PNG, broken PDF → `INVALID_INPUT`, no output |
| Encrypted PDF | Password requested or clearly rejected | Pass | no/wrong password → `PASSWORD_REQUIRED`; correct password renders |
| Cancel / close during job | Worker stops; partial files removed | Pass | cancel after temp file exists → no output, no `.qc-tmp-*`; quit asks first |
| Very large input | Limit enforced before allocation | Pass | pixel and render limits trigger `RESOURCE_LIMIT` before decoding |
| Unicode path / read-only folder | Valid names work; denied writes explained | Pass (Unicode) | Arabic + CJK paths; write errors map to `PERMISSION_DENIED` |
| Wheel near screen edge | Wheel stays visible; keyboard usable | Pass | wheel clamped on-screen incl. offset 2nd monitor; arrows/Enter/1–9/Esc |
| Packaged installation | Core formats work without a developer environment | Pass | section 3 |

Also found and fixed during testing:
- Shift+drop from Explorer was accepted as *Move*, which could let Explorer delete the original. Drops are now Copy-only (Phase 5).
- EXIF-rotated phone photos reported sideways dimensions, so valid crops were rejected (Phase 4).
- `pdf_page=0` was silently treated as page 1 (Phase 2).
- The Export dialog would have crashed opening (Qt converted the format to a string) (Phase 4).
- The UI test process crashed on exit (widgets outlived the QApplication). Tests only; the app always exited cleanly (Phase 6).

## 3. Packaged build

Run by `packaging/build.ps1` against `dist\QuickConvert`, with `PATH` reduced to `System32`
(no Python):

```
QuickConvert 0.1.0 self-test on Windows-11-10.0.26200-SP0 (packaged build)
  [PASS] jpeg -> png / webp, png -> jpeg / webp, webp -> jpeg / png
  [PASS] jpeg / png / webp -> pdf, pdf -> png / jpeg (page 2)
  [PASS] edit: crop + background          crop + background -> 560x380
  [PASS] rejects corrupt input            rejected with INVALID_INPUT
  [PASS] protects existing output         existing output kept
  [PASS] no temporary files left          clean
15 passed, 0 failed
```

GUI check from a fresh unzip into a new folder, Python not on PATH: `QuickConvert.exe` starts and
shows its window; a second launch with a file argument hands the file to the running instance
and exits with code 0; no errors in the log.

**Not yet done:** a true clean-machine test (a PC or VM that never had Python or this project).
Recommended: Windows Sandbox (*Turn Windows features on or off → Windows Sandbox*), copy the zip
in, unzip, run `quickconvert-cli selftest`, then try the app by hand.

## 4. Performance

`packaging/benchmark.py`; each case in a fresh process, end-to-end (inspect, decode, encode, verify
by reopening, atomic save). Two runs agreed within 0.2 s.

| Case | Time | Peak memory |
|---|---|---|
| 24 MP photo JPEG → PNG | 1.1 s | 216 MB |
| 24 MP photo JPEG → WebP (q90) | 2.7 s | 402 MB |
| 24 MP photo JPEG → PDF | 0.3 s | 216 MB |
| 12 MP transparent PNG → JPEG | 0.4 s | 181 MB |
| PDF page → PNG at 300 DPI | 0.2 s | 122 MB |
| 24 MP crop + background → PNG | 1.0 s | 329 MB |
| Worst case: 24 MP random noise → PNG | 1.8 s | 216 MB |
| Worst case: 24 MP random noise → WebP (q90) | 55.5 s | 608 MB |

Idle process: 23 MB. All jobs run off the UI thread and can be cancelled, so the window stays
responsive regardless. PNG uses zlib level 3 (measured ~35% faster than level 6 for ~7% larger
files). WebP keeps encoder method 4: method 2 was 3–6× faster but made files up to 2.5× larger.

## 5. Manual checks still to do

| Check | Why it can't be automated here |
|---|---|
| Shift+drag from File Explorer onto the bubble; original still present | Needs a real OLE drag between processes |
| Explorer → right-click → Send to → QuickConvert | Needs Explorer interaction |
| Wheel and dialogs at 150%/200% display scaling, and on a second monitor | Needs real displays |
| Windows dark mode appearance | Visual check |
| Clean-machine install (Windows Sandbox) | See section 3 |
