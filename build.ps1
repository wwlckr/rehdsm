# Build the standalone Windows executable (no Python needed to run it).
#
#   powershell -ExecutionPolicy Bypass -File build.ps1 [-Python <path\to\python.exe>] [-Ucrt <folder>]
#
# The executable runs on the same Windows versions and architecture as the Python used to build it.
# For Windows 7 SP1 support (even without updates), build with Python 3.7 (3.8+ needs update KB2533623 on
# Windows 7) and pass -Ucrt with the Universal C Runtime DLLs of the same architecture, taken from the Windows
# SDK folder "Redist\ucrt\DLLs\x86" or "...\x64". They are only used on Windows 7 / 8; Windows 10+ ignores them.
#   - 32-bit Python -> rehdsm-<version>-windows-x86.exe  (32 and 64-bit Windows)
#   - 64-bit Python -> rehdsm-<version>-windows-x64.exe  (64-bit Windows)
# Output: dist\
# If resave\data\icon.ico exists, it is used for the .exe and the window.
param(
    [string]$Python = "python",
    [string]$Ucrt = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pyVersion = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$arch = & $Python -c "import struct; print('x64' if struct.calcsize('P') == 8 else 'x86')"
if ($pyVersion -ne "3.7") {
    Write-Warning "Building with Python ${pyVersion}: Windows 7 needs extra updates to run it (use Python 3.7)."
}
if (-not $Ucrt) {
    Write-Warning "No -Ucrt folder: Windows 7 / 8 need the Universal C Runtime (KB2999226) installed."
}
& $Python -m pip install --disable-pip-version-check -r requirements-build.txt
$version = & $Python -c "import resave; print(resave.__version__)"
$options = @(
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "rehdsm-$version-windows-$arch",
    "--add-data", "resave\data\empty_slot.bin;resave\data"
)
# Not used by the program (only optional imports in the standard library): leaving them out makes the .exe
# smaller and keeps OpenSSL, bzip2 and xz out of it.
foreach ($module in "ssl", "_ssl", "socket", "_socket", "select", "_hashlib", "bz2", "_bz2", "lzma", "_lzma") {
    $options += @("--exclude-module", $module)
}
if (Test-Path "resave\data\icon.ico") {
    $options += @("--icon", "resave\data\icon.ico", "--add-data", "resave\data\icon.ico;resave\data")
}
if ($Ucrt) {
    if (-not (Test-Path (Join-Path $Ucrt "ucrtbase.dll"))) { throw "ucrtbase.dll not found in $Ucrt" }
    foreach ($dll in Get-ChildItem (Join-Path $Ucrt "*.dll")) {
        $options += @("--add-binary", "$($dll.FullName);.")
    }
}
# Clean PATH: otherwise PyInstaller may bundle stray C runtime DLLs from unrelated programs on PATH.
$pyDir = & $Python -c "import sys, os; print(os.path.dirname(sys.executable))"
$env:PATH = "$pyDir;$pyDir\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
& $Python -m PyInstaller @options save_manager.py
