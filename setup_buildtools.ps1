# Download and prepare everything needed to build the Windows 7-compatible release executables.
#
#   powershell -ExecutionPolicy Bypass -File setup_buildtools.ps1
#
# Creates buildtools\ (ignored by git, about 150 MB) with:
#   python37-x86, python37-x64  portable Python 3.7.9 + Tcl/Tk, pycryptodome and PyInstaller 5.13.2
#   ucrt\x86, ucrt\x64          Microsoft Universal C Runtime DLLs (Windows SDK 10.0.19041 redistributable)
# Nothing is installed on the system: the Tcl/Tk MSI is only unpacked (administrative install).
# Every download is checked against a fixed SHA256 checksum; the C runtime DLLs must be signed by Microsoft.
#
# Then build with:
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Python buildtools\python37-x86\python.exe -Ucrt buildtools\ucrt\x86
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Python buildtools\python37-x64\python.exe -Ucrt buildtools\ucrt\x64
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # much faster Invoke-WebRequest on Windows PowerShell 5.1
Set-Location $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$tools = Join-Path $PSScriptRoot "buildtools"
$downloads = Join-Path $tools "downloads"
New-Item -ItemType Directory -Force $downloads | Out-Null

function Get-Checked([string]$Url, [string]$Name, [string]$Sha256) {
    $file = Join-Path $downloads $Name
    if (-not (Test-Path $file) -or (Get-FileHash $file).Hash -ne $Sha256) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest $Url -OutFile $file -UseBasicParsing
    }
    $actual = (Get-FileHash $file).Hash
    if ($actual -ne $Sha256) {
        Remove-Item $file
        throw "Checksum mismatch for $Name (got $actual). The download may be corrupted or tampered with."
    }
    return $file
}

# --- Python 3.7.9 (last Python whose modules load on a Windows 7 without updates) ---
$pythons = @(
    @{ Arch = "x86"; Package = "pythonx86"; MsiArch = "win32"
       Zip = "E47905FA5CA92E9556A76D8415B52950B2C1C0B1E2A2AB4DB18913C2FAD4386F"
       Msi = "B20999748CE4769644134EB0C0144AD3B7FA135265D3608415F6940EE7B0801F" },
    @{ Arch = "x64"; Package = "python"; MsiArch = "amd64"
       Zip = "029E1EA5BEEB142CD0F2DA4E75C45F49BD7E0C7B48EB5BB6C6947F2D1B665C5E"
       Msi = "8075ACE9D2ADADBE0C339DB9B394A14A0BE4AAABCD25D1FA9D47B3F5373EE1C7" }
)
foreach ($p in $pythons) {
    $dest = Join-Path $tools "python37-$($p.Arch)"
    if (Test-Path (Join-Path $dest "python.exe")) {
        Write-Host "python37-$($p.Arch) already exists, skipping (delete it to set it up again)."
        continue
    }
    $zip = Get-Checked "https://www.nuget.org/api/v2/package/$($p.Package)/3.7.9" "$($p.Package)-3.7.9.zip" $p.Zip
    $msi = Get-Checked "https://www.python.org/ftp/python/3.7.9/$($p.MsiArch)/tcltk.msi" "tcltk-3.7.9-$($p.MsiArch).msi" $p.Msi

    $unpacked = Join-Path $downloads "$($p.Package)-unpacked"
    if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
    Expand-Archive $zip $unpacked
    Move-Item (Join-Path $unpacked "tools") $dest
    Remove-Item -Recurse -Force $unpacked

    # The NuGet package has no tkinter: take it from python.org's tcltk.msi (administrative install = unpack only).
    $tk = Join-Path $downloads "tcltk-$($p.MsiArch)"
    if (Test-Path $tk) { Remove-Item -Recurse -Force $tk }
    $proc = Start-Process msiexec -ArgumentList "/a `"$msi`" /qn TARGETDIR=`"$tk`"" -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "Could not unpack $msi (msiexec exit code $($proc.ExitCode))" }
    Copy-Item (Join-Path $tk "DLLs\*") (Join-Path $dest "DLLs") -Force
    Copy-Item -Recurse (Join-Path $tk "Lib\tkinter") (Join-Path $dest "Lib") -Force
    Copy-Item -Recurse (Join-Path $tk "tcl") $dest -Force
    Remove-Item -Recurse -Force $tk

    $python = Join-Path $dest "python.exe"
    $ErrorActionPreference = "Continue"  # pip writes notices to stderr
    & $python -m pip install --disable-pip-version-check --no-warn-script-location -q -r requirements-build.txt
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed for python37-$($p.Arch)" }
    & $python -c "import sys, struct, tkinter, Crypto, PyInstaller; print('python37-%s ready: Python %s, %d-bit, Tk %s, PyInstaller %s' % ('$($p.Arch)', sys.version.split()[0], struct.calcsize('P') * 8, tkinter.TkVersion, PyInstaller.__version__))"
}

# --- Universal C Runtime (needed by Windows 7 / 8 without update KB2999226) ---
$ucrt = Join-Path $tools "ucrt"
if (Test-Path (Join-Path $ucrt "x64\ucrtbase.dll")) {
    Write-Host "ucrt already exists, skipping (delete it to set it up again)."
} else {
    $nupkg = Get-Checked "https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.19041.5/microsoft.windows.sdk.cpp.10.0.19041.5.nupkg" `
        "microsoft.windows.sdk.cpp.10.0.19041.5.nupkg" "35074CAFACC99A47E87C25641F98E0952576487FE29607103F83D61540AD0523"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($nupkg)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -match "/ucrt/DLLs/(x86|x64)/[^/]+\.dll$") {
                $dir = Join-Path $ucrt $Matches[1]
                New-Item -ItemType Directory -Force $dir | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $dir $entry.Name), $true)
            }
        }
    } finally { $archive.Dispose() }
    foreach ($dll in Get-ChildItem $ucrt -Recurse -Filter *.dll) {
        $sig = Get-AuthenticodeSignature $dll.FullName
        if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
            Remove-Item -Recurse -Force $ucrt
            throw "$($dll.Name) is not validly signed by Microsoft."
        }
    }
    foreach ($a in "x86", "x64") { Write-Host ("ucrt\{0} ready: {1} DLLs signed by Microsoft" -f $a, (Get-ChildItem (Join-Path $ucrt $a)).Count) }
}

Remove-Item -Recurse -Force $downloads
Write-Host "`nDone. Build with:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File build.ps1 -Python buildtools\python37-x86\python.exe -Ucrt buildtools\ucrt\x86"
Write-Host "  powershell -ExecutionPolicy Bypass -File build.ps1 -Python buildtools\python37-x64\python.exe -Ucrt buildtools\ucrt\x64"
