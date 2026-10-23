# Build the Windows release: tests -> icon/version -> PyInstaller -> packaged self-test -> zip.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Requires the dev environment:  .venv\Scripts\pip install -r requirements-dev.txt

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Virtual environment not found. Run: python -m venv .venv" }

$Version = & $Py -c "from app import __version__; print(__version__)"
Write-Host "== QuickConvert $Version ==" -ForegroundColor Cyan

Write-Host "-- Running tests"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; not building." }

Write-Host "-- Generating icon and version resource"
New-Item -ItemType Directory -Force build | Out-Null
& $Py packaging\make_icon.py build\quickconvert.ico
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }
$v = $Version.Split(".") + @("0", "0", "0")
$tuple = "$($v[0]), $($v[1]), $($v[2]), 0"
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($tuple), prodvers=($tuple), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('ProductName', 'QuickConvert'),
      StringStruct('FileDescription', 'QuickConvert - local file conversion and image editing'),
      StringStruct('FileVersion', '$Version'),
      StringStruct('ProductVersion', '$Version'),
      StringStruct('OriginalFilename', 'QuickConvert.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding utf8 build\version_info.txt

Write-Host "-- Packaging with PyInstaller"
& $Py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\quickconvert.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

Write-Host "-- Self-test of the packaged build (no Python on PATH)"
$App = Join-Path $Root "dist\QuickConvert"
$SavedPath = $env:PATH
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
try {
    & "$App\quickconvert-cli.exe" selftest --report "$Root\build\selftest-packaged.json"
    $SelfTest = $LASTEXITCODE
} finally { $env:PATH = $SavedPath }
if ($SelfTest -ne 0) { throw "Packaged self-test failed (see build\selftest-packaged.json)." }

Write-Host "-- Creating zip"
$Zip = Join-Path $Root "dist\QuickConvert-$Version-win64.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $App -DestinationPath $Zip
$SizeMB = [math]::Round((Get-ChildItem $App -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
$ZipMB = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
Write-Host "Done: $Zip ($ZipMB MB zipped, $SizeMB MB installed)" -ForegroundColor Green
