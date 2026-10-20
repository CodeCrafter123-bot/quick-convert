# QuickConvert

Local desktop file conversion and image editing with a radial menu. Files never leave the machine.
Target OS for the MVP: **Windows 11** (others later).

## Developer setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app --help      # CLI over the conversion core (desktop UI arrives in Phase 3)
pytest
```

`requirements.in` lists direct dependencies; `requirements.txt` is the pinned lock (`pip freeze`).

## Capability matrix (MVP)

The UI only offers pairs from `app/services/capabilities.py`. Every pair below is covered by
`tests/test_conversion.py::test_every_registered_pair_produces_readable_output`.

| Input \ Output | JPEG | PNG | WebP | PDF |
|---|---|---|---|---|
| **JPEG** | — | ✓ | ✓ quality | ✓ dpi |
| **PNG**  | ✓ quality, bg color | — | ✓ quality | ✓ dpi |
| **WebP** | ✓ quality, bg color | ✓ | — | ✓ dpi |
| **PDF**  | ✓ page, dpi, password, quality | ✓ page, dpi, password | — | — |

Editing (JPEG/PNG/WebP in → JPEG/PNG/WebP out): crop, background color + padding + corner radius.

Rules: input type is detected from file content, not the extension. Transparent → JPEG is
flattened onto the chosen color (white by default). Image → PDF produces one page sized to the
image at the chosen DPI (default 150). Metadata is stripped unless `keep_metadata` is set.

## Architecture

```
UI request → validation → capability lookup → job queue → adapter → temp file → verify → rename
```

| Path | Role |
|---|---|
| `app/models/` | `ConversionRequest`, `ConversionOptions`, `ConversionJob`, `ConversionResult`, `Capability`, `ErrorCode` |
| `app/services/inspection.py` | `inspect_file` — magic-byte type detection, size/pixel/page limits |
| `app/services/capabilities.py` | explicit registry of supported pairs and their options |
| `app/services/conversion.py` | `validate` + `run` a request through an adapter |
| `app/services/jobs.py` | `JobManager.submit / cancel / get_job` on worker threads |
| `app/services/editing.py` | non-destructive crop + background preview/export |
| `app/services/output.py` | safe names, temp-file-then-rename saves, cleanup on failure/cancel |
| `app/adapters/` | Pillow (images) and PyMuPDF (PDF) engines |
| `app/storage/settings.py` | JSON settings in `%APPDATA%\QuickConvert` |
| `app/limits.py` | resource limits |

Error codes: `UNSUPPORTED_PAIR`, `INVALID_INPUT`, `PASSWORD_REQUIRED`, `PERMISSION_DENIED`,
`OUTPUT_EXISTS`, `RESOURCE_LIMIT`, `CONVERSION_FAILED`, `CANCELLED`.

## Status

- [x] Phase 1 — repo, venv, lock file, engine proven on fixtures
- [x] Phase 2 — conversion core (M1: engine)
- [ ] Phase 3 — desktop UI: main window, drop zone, radial menu, progress/cancel (M2)
- [ ] Phase 4 — crop/background dialogs (core logic done; UI pending) (M3)
- [ ] Phase 5 — system-wide drag+Shift prototype, hardening
- [ ] Phase 6 — PyInstaller package, clean-machine test (M4)

## Licensing

PyMuPDF is **AGPL-3.0 or commercial**. Distributing a build that bundles it requires either
releasing QuickConvert under AGPL-compatible terms or buying an Artifex license. Decide before
Phase 6. Alternative: `pypdfium2` (Apache/BSD) for rendering plus Pillow for image → PDF.
