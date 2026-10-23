# QuickConvert user guide

QuickConvert converts images and PDFs and does quick image edits. **Everything happens on your
computer; nothing is uploaded. Your original file is never changed.** Every result is saved as a
new file.

## Install

1. Unzip `QuickConvert-<version>-win64.zip` anywhere, for example `C:\Users\<you>\Apps\`.
2. Run `QuickConvert\QuickConvert.exe`. No admin rights or Python needed.
3. Optional: right-click `QuickConvert.exe` → *Pin to Start* or *Send to → Desktop (create shortcut)*.

Windows SmartScreen may warn about an unrecognized app the first time, because the release is not
code-signed. Choose *More info → Run anyway* if you trust where you got it.

To uninstall, quit QuickConvert from the tray icon and delete the folder. To also remove settings
and logs, delete `%APPDATA%\QuickConvert` and `%LOCALAPPDATA%\QuickConvert`, and turn off
"Send to" in the tray menu first (or delete `%APPDATA%\Microsoft\Windows\SendTo\QuickConvert.lnk`).

## Open a file

- Drag a file onto the window, or click **Choose File…** (Ctrl+O).
- **Hold Shift while dropping** to open the action wheel right where you dropped it.
- **From any app:** start dragging a file (for example in File Explorer) and hold **Shift**. A round
  *Drop here* bubble appears next to the cursor. Drop the file on it.
- **From Explorer's right-click menu:** turn on *Add to Explorer "Send to" menu* in the tray menu,
  then right-click a file → *Send to* → *QuickConvert*.

Supported inputs: JPEG, PNG, WebP and PDF.

## Choose an action

Click **Actions…** (or press Ctrl+K) for the wheel, or use **Menu** for a plain list.
Only actions that work for the file are shown.

Wheel keys: arrow keys or Tab to move, Enter to choose, 1–9 to pick directly, Esc to close.

| From | Convert to | Options |
|---|---|---|
| JPEG | PNG, WebP, PDF | quality (WebP), resolution (PDF) |
| PNG | JPEG, WebP, PDF | quality, fill color for transparent areas (JPEG) |
| WebP | JPEG, PNG, PDF | quality, fill color (JPEG) |
| PDF | PNG, JPEG | page, resolution (DPI), password if protected |

Images can also be **cropped** and given a **background**.

### Convert

Pick a format, check the options and where to save, and click **Convert**. The job appears under
**Jobs** with a progress bar and a **Cancel** button. When it finishes, click **Open File** or
**Show in Folder**. If a file with that name already exists, QuickConvert suggests a new name, or
asks before replacing it.

### Crop

Drag the corner or edge handles, drag inside the selection to move it, or drag outside it to
draw a new one. Pick an aspect ratio (Free, Original, 1:1, 4:3…) to lock its shape. Arrow keys
nudge the selection (Shift + arrow = 10 px). **Reset** selects the whole image. The size shown is
the size of the result in real pixels.

### Add background

Pick a color (or a preset), the padding around the image, and the corner radius. The preview and
result size update as you change them.

### Save edits

Crop and background can be combined. The thumbnail shows the result, and the blue **Edits** box
lists what will be applied. Click **Export…** to save it as PNG, JPEG or WebP, or
**Discard edits** to go back to the original. Opening another file also discards edits.

## Running in the background

Closing the window keeps QuickConvert in the tray (bottom-right of the taskbar, maybe under the
`^` arrow) so the Shift+drag bubble and Send to keep working. Right-click the tray icon for:

- **Open QuickConvert**, **Choose File…**
- **Shift+drag from any app**: turn the bubble on or off
- **Add to Explorer "Send to" menu**
- **Quit**: asks first if jobs are still running

## Troubleshooting

| Problem | What to do |
|---|---|
| A format isn't offered | It isn't supported for that input; see the table above. |
| "Cannot write to…" | Choose a folder you can write to, and check free disk space. |
| PDF page looks blurry | Increase the resolution (DPI) in the options. |
| Transparent areas turned white in a JPEG | JPEG has no transparency. Pick a fill color, or save as PNG/WebP. |
| "Password protected" | Enter the PDF's password in the options dialog. |
| "Too large" | Very large images and pages are limited to protect memory. Lower the DPI, or crop first. |
| The Shift+drag bubble doesn't appear | Check it's on in the tray menu and QuickConvert is running. Use Choose File or Send to instead. |
| Something went wrong | Details are in `%LOCALAPPDATA%\QuickConvert\logs\quickconvert.log` (no file contents are logged). |

## Checking an installation

Open a Command Prompt in the QuickConvert folder and run:

```
quickconvert-cli selftest
```

It runs every supported conversion with generated sample files and prints PASS/FAIL for each.
