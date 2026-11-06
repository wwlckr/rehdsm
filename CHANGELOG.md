# Changelog

All notable changes to this project. Versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-06
First public release.

### Added
- Opens Resident Evil HD Remaster (PC) `biodata.bin` saves: decrypts them and checks the checksum.
- Shows the 8 slots like the in-game "Load" menu, with its colours: character, save count, difficulty / mode
  (Real Survival, Invisible Enemy), costume, health and **play time**.
- "Cleared" label for completed files (save count 00).
- Shows whether each game was played with **"Once again.."** and with **One Dangerous Zombie**.
- **Delete slots** (they become "No data", exactly as the game leaves them). A backup of the file is made before
  every write.
- Finds the Steam save automatically (any Steam account); falls back to the GOG Galaxy folder.
  "Find on Steam" / "Find on GOG" / "Open…" buttons.
- **Drag and drop** a `biodata.bin` onto the window to open it.

### License
- GNU General Public License v3.0. Third-party components: see `THIRD_PARTY_NOTICES.md`.

### System requirements
- Windows 7 SP1, 8, 8.1, 10 or 11.
- `windows-x86` build: 32-bit and 64-bit Windows. `windows-x64` build: 64-bit Windows only.
- No installation and no extra downloads: the executables include everything they need, also on a
  Windows 7 SP1 without updates (tested).
