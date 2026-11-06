# Third-party notices

This program is licensed under the **GNU General Public License v3.0** (see [`LICENSE`](LICENSE)).
All the components below have licenses compatible with it. The Microsoft runtime files are system libraries
normally distributed with Windows and the compiler, which the GPL allows to ship alongside the program.

The source code in this repository only uses Python and pycryptodome. The **release executables**
(`rehdsm-<version>-windows-x86.exe` / `-x64.exe`) are built with PyInstaller and contain the following
third-party software. Full license texts are in the [`licenses/`](licenses/) folder.

| Component | Version | Used for | License | Text |
|---|---|---|---|---|
| Python | 3.7.9 | Runs the program | Python Software Foundation License v2 | [licenses/Python.txt](licenses/Python.txt) |
| Tcl/Tk (`_tkinter`) | 8.6.9 | The window | Tcl/Tk license (BSD-style) | [licenses/Tcl-Tk.txt](licenses/Tcl-Tk.txt) |
| libffi (inside Python's `_ctypes`) | 3.x | Drag and drop (Windows API calls) | MIT | [licenses/libffi.txt](licenses/libffi.txt) |
| pycryptodome | 3.24 | Blowfish encryption of the save file | BSD 2-Clause / public domain | [licenses/pycryptodome.txt](licenses/pycryptodome.txt) |
| PyInstaller bootloader | 5.13.2 | Starts the program from the single .exe | GPL 2.0 **with the Bootloader Exception** (executables built with it may use any license) | [licenses/PyInstaller.txt](licenses/PyInstaller.txt) |
| Microsoft Visual C++ runtime (`VCRUNTIME140.dll`) | 14.x | Required by Python | Microsoft Visual Studio redistributable | Distributed as part of this application, as Microsoft allows |
| Microsoft Universal C Runtime (`ucrtbase.dll`, `api-ms-win-*.dll`) | 10.0.19041 | Lets the program run on Windows 7 / 8 without updates | Microsoft Windows SDK redistributable ("app-local" deployment) | Distributed as part of this application, as Microsoft allows. On Windows 10 and newer, Windows always uses its own copy |

The Microsoft runtime files are unmodified, signed by Microsoft, and are only redistributed inside the
release executables (they are not part of this repository). `setup_buildtools.ps1` downloads them from
Microsoft's official package when you build the executables yourself.

"Resident Evil" is a trademark of CAPCOM. This is an unofficial fan-made tool, not affiliated with or endorsed
by CAPCOM.
