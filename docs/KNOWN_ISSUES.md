# Known issues and limitations: QuickConvert 0.1.0

## Limitations by design (MVP scope)

- **Formats:** JPEG, PNG, WebP and PDF only. TIFF, BMP, HEIC, AVIF and DOCX are not supported.
  The reference video shows those labels, but the app only offers pairs it has verified.
- **PDF → image converts one page at a time.** There is no "all pages to a folder" yet.
- **PDF output is always one page** from one image. No merging, splitting or multi-image PDFs.
- **One file at a time.** No batch conversion.
- **Metadata:** EXIF is dropped unless *Keep metadata* is ticked. Color profiles (ICC) aren't
  carried over, so wide-gamut photos may look slightly less saturated in other apps.
- **English only.**

## Known issues

- **WebP is slow on very large, noisy images.** A 24-megapixel image of pure noise takes about a
  minute (real photos about 3 s). It runs in the background and can be cancelled. A faster encoder
  setting was measured but made files up to 2.5× larger, so it wasn't adopted.
- **Shift+drag bubble:**
  - It appears for *any* Shift+drag outside QuickConvert, for example a Shift+drag text selection
    in Word. It sits beside the cursor and disappears on release, so it doesn't interfere, but
    it's visible.
  - If a drag starts while another window holds the mouse in a special mode, such as a full-screen
    game, the bubble may not appear.
  - It works only while QuickConvert is running (it keeps running in the tray after the window
    is closed).
  - It's turned off automatically if reading the input state fails; the log records why.
- **Unsigned executable:** SmartScreen may warn on first launch ("Windows protected your PC").
  Code-signing needs a paid certificate.
- **Untested on real hardware variations:** high display scaling (150%+), multiple monitors and
  dark mode were checked only in code, not visually (see TEST_REPORT section 5).
- **No clean-machine test yet:** the packaged build was verified with Python removed from PATH
  on the build PC, not on a machine that never had Python.
- **Large previews:** previews use a copy scaled down to 1600 px. Opening a 100-megapixel image
  still decodes the full file once and takes a moment.
- **Windows only.** Tray, Send to, Shift+drag and packaging target Windows. The conversion core
  and main window are cross-platform but untested elsewhere.
