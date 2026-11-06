"""Data model for biodata.bin: file, slots and known fields.

The only write operation is clearing a slot. Every offset is documented in FORMAT.md.
"""
from __future__ import annotations

import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import crypto

FILE_SIZE = 457376
TABLE_OFFSET = 0x40
BLOCK_COUNT = 9
SYSTEM_BLOCK = 6
SLOT_SIZE = 0xDF30          # size of each slot block in the file
SLOT_DATA_SIZE = 0xDF20     # size declared in the block header
SAVE_TIME_OFFSET = 0x28     # u32: Unix timestamp of the last save

# In-game slot (1-8) -> block index in the file.
SLOT_TO_BLOCK = {1: 1, 2: 2, 3: 7, 4: 5, 5: 0, 6: 3, 7: 8, 8: 4}

# Offsets inside a slot block.
OFF_CHARACTER = 0x018
OFF_SAVE_COUNT = 0x01C
OFF_MODE = 0x0C4
OFF_DIFFICULTY = 0x0C8
OFF_COSTUME = 0x0CC
OFF_OPTIONS = 0x0D0         # option flags: bit 0 = One Dangerous Zombie (RS/IE set other bits)
OFF_CARRY_OVER = 0x0D8      # non-zero when the game was started with "Once again.." (Standard mode)
OPTION_ODZ = 0x1
OFF_PLAY_TIME = 0x0E0
OFF_HEALTH = 0x144

MODE_NORMAL, MODE_REAL_SURVIVAL, MODE_INVISIBLE_ENEMY = 0, 1, 2

CHARACTERS = {0: "Chris", 1: "Jill"}
MAX_HEALTH = {0: 1400, 1: 960}
DIFFICULTIES = {0: "Easy", 1: "Normal", 2: "Hard", 3: "Very Easy"}
MODES = {MODE_NORMAL: "Standard", MODE_REAL_SURVIVAL: "Real Survival", MODE_INVISIBLE_ENEMY: "Invisible Enemy"}
COSTUMES = {0: "Default", 1: "Alternate 1", 2: "Alternate 2", 3: "Alternate 3"}
# The save area (+0x020) is not shown yet: only a few IDs are known (see FORMAT.md / PROJECT_LOG.md).

_TEMPLATE_PATH = Path(__file__).with_name("data") / "empty_slot.bin"


class SaveFormatError(Exception):
    """The file does not have the expected format."""


def load_empty_template() -> bytes:
    """Contents of an empty slot (the block without its 4-byte hash)."""
    data = _TEMPLATE_PATH.read_bytes()
    if len(data) != SLOT_SIZE - 4:
        raise SaveFormatError("Empty slot template is corrupted.")
    return data


def format_time(seconds: float) -> str:
    total = int(max(0.0, seconds))
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


@dataclass
class Slot:
    """Read-only view of one slot inside the decrypted buffer."""

    save: "SaveFile"
    number: int  # 1-8, as in the in-game menu

    @property
    def block(self) -> int:
        return SLOT_TO_BLOCK[self.number]

    @property
    def base(self) -> int:
        return self.save.block_offset(self.block)

    def _u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.save.data, self.base + off)[0]

    def _f32(self, off: int) -> float:
        return struct.unpack_from("<f", self.save.data, self.base + off)[0]

    # -- state --
    @property
    def is_empty(self) -> bool:
        body = bytes(self.save.data[self.base + 4:self.base + SLOT_SIZE])
        return body == self.save.empty_template

    def clear(self) -> None:
        """Turn the slot into "No data", exactly as the game does."""
        start = self.base + 4  # keep the block hash
        self.save.data[start:start + SLOT_SIZE - 4] = self.save.empty_template
        self.save.dirty = True

    # -- fields --
    @property
    def character_id(self) -> int:
        return self._u32(OFF_CHARACTER)

    @property
    def character(self) -> str:
        return CHARACTERS.get(self.character_id, f"Unknown ({self.character_id})")

    @property
    def save_count(self) -> int:
        return self._u32(OFF_SAVE_COUNT)

    @property
    def is_cleared(self) -> bool:
        """Completed File ("Archivo completado"): the game shows its save count as 00."""
        return not self.is_empty and self.save_count == 0

    @property
    def mode_id(self) -> int:
        return self._u32(OFF_MODE)

    @property
    def mode(self) -> str:
        return MODES.get(self.mode_id, f"Unknown ({self.mode_id})")

    @property
    def difficulty_id(self) -> int:
        return self._u32(OFF_DIFFICULTY)

    @property
    def difficulty(self) -> str | None:
        """None in Real Survival: that mode has no selectable difficulty."""
        if self.mode_id == MODE_REAL_SURVIVAL:
            return None
        return DIFFICULTIES.get(self.difficulty_id, f"Unknown ({self.difficulty_id})")

    @property
    def costume_id(self) -> int:
        return self._u32(OFF_COSTUME)

    @property
    def costume(self) -> str:
        return COSTUMES.get(self.costume_id, f"Unknown ({self.costume_id})")

    @property
    def is_once_again(self) -> bool | None:
        """Started with "Once again..". None in Real Survival / Invisible Enemy,
        where +0x0D8 is always set and does not tell it apart."""
        if self.mode_id != MODE_NORMAL:
            return None
        return self._u32(OFF_CARRY_OVER) != 0

    @property
    def has_odz(self) -> bool:
        """One Dangerous Zombie enabled."""
        return bool(self._u32(OFF_OPTIONS) & OPTION_ODZ)

    @property
    def play_time(self) -> float:
        """Play time in seconds."""
        return self._f32(OFF_PLAY_TIME)

    @property
    def health(self) -> int:
        return self._u32(OFF_HEALTH)

    @property
    def max_health(self) -> int:
        return MAX_HEALTH.get(self.character_id, 1400)

    @property
    def summary(self) -> str:
        """Difficulty / mode text as shown in the slot list."""
        if self.mode_id == MODE_REAL_SURVIVAL:
            return "Real Survival"
        if self.mode_id == MODE_INVISIBLE_ENEMY:
            return f"Invisible Enemy · {self.difficulty}"
        return self.difficulty

    @property
    def color_key(self) -> str:
        """Colour key matching the in-game "Load" menu."""
        if self.mode_id == MODE_REAL_SURVIVAL:
            return "real_survival"
        if self.mode_id == MODE_INVISIBLE_ENEMY:
            return "invisible_enemy"
        return {0: "easy", 1: "normal", 2: "hard", 3: "very_easy"}.get(self.difficulty_id, "normal")


class SaveFile:
    """biodata.bin decrypted in memory."""

    def __init__(self, plain: bytes, path: Path | None = None):
        self.data = bytearray(plain)
        self.path = path
        self.dirty = False
        self.empty_template = load_empty_template()
        self._validate()
        self.slots = [Slot(self, n) for n in range(1, 9)]

    # -- load / save --
    @classmethod
    def load(cls, path: str | os.PathLike) -> "SaveFile":
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) != FILE_SIZE:
            raise SaveFormatError(
                f"Unexpected size ({len(raw)} bytes; expected {FILE_SIZE}). "
                "Is this a Resident Evil HD Remaster biodata.bin?")
        plain = crypto.decrypt(raw)
        if not crypto.verify(plain):
            raise SaveFormatError("Checksum mismatch: the file is invalid or damaged.")
        return cls(plain, path)

    def to_bytes(self) -> bytes:
        """Encrypted file with a recomputed checksum, ready for the game."""
        plain = crypto.fix_checksum(bytes(self.data))
        raw = crypto.encrypt(plain)
        # Safety check: it must decrypt back to the same data and verify.
        check = crypto.decrypt(raw)
        if check != plain or not crypto.verify(check):
            raise SaveFormatError("Internal encryption error: nothing was written.")
        return raw

    def save(self, path: str | os.PathLike | None = None,
             backup_dir: str | os.PathLike | None = None) -> Path | None:
        """Write the file. Returns the backup path, if one was made."""
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("No destination path.")
        raw = self.to_bytes()
        backup = None
        if backup_dir and target.exists():
            backup_dir = Path(backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = backup_dir / f"biodata_{stamp}.bin"
            n = 1
            while backup.exists():
                backup = backup_dir / f"biodata_{stamp}_{n}.bin"
                n += 1
            shutil.copy2(target, backup)
        # Atomic write: temporary file in the same folder, then replace.
        fd, tmp = tempfile.mkstemp(prefix=".biodata_", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        self.path = target
        self.dirty = False
        return backup

    # -- structure --
    def block_offset(self, index: int) -> int:
        return struct.unpack_from("<I", self.data, TABLE_OFFSET + 4 * index)[0]

    @property
    def last_saved(self) -> datetime:
        ts = struct.unpack_from("<I", self.data, SAVE_TIME_OFFSET)[0]
        return datetime.fromtimestamp(ts)

    def _validate(self) -> None:
        if len(self.data) != FILE_SIZE:
            raise SaveFormatError("Unexpected data size.")
        offsets = [self.block_offset(i) for i in range(BLOCK_COUNT)]
        if offsets != sorted(offsets) or offsets[0] != TABLE_OFFSET + 4 * BLOCK_COUNT:
            raise SaveFormatError("Unexpected block table.")
        for i, off in enumerate(offsets):
            hdr_size, size = struct.unpack_from("<II", self.data, off + 4)
            expected = 0xA0 if i == SYSTEM_BLOCK else SLOT_DATA_SIZE
            if hdr_size != 0x0C or size != expected:
                raise SaveFormatError(f"Unexpected header in block {i}.")
            if i != SYSTEM_BLOCK and off + SLOT_SIZE > len(self.data):
                raise SaveFormatError(f"Block {i} extends past the end of the file.")


def find_steam_saves() -> list[Path]:
    """Find RE HD Remaster (app 304240) biodata.bin files in the Steam folders."""
    roots: list[Path] = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except (OSError, ImportError):
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / "Steam")
    found: list[Path] = []
    seen = set()
    for root in roots:
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for candidate in userdata.glob("*/304240/remote/biodata.bin"):
            key = str(candidate.resolve()).lower()
            if key not in seen:
                seen.add(key)
                found.append(candidate)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


# GOG Galaxy save folder (given by the user; not verified with a real GOG save yet).
GOG_GAME_ID = "58424498340553405"
GOG_RELATIVE_DIR = Path("GOG.com") / "Galaxy" / "Applications" / GOG_GAME_ID / "Storage" / "Shared" / "Files"


def gog_save_dir() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / GOG_RELATIVE_DIR if local else None


def find_gog_saves() -> list[Path]:
    """Find RE HD Remaster saves in the GOG Galaxy folder.

    The GOG file name is not confirmed, so besides biodata.bin any file with the
    exact biodata.bin size is returned as a candidate (newest first).
    """
    folder = gog_save_dir()
    if folder is None or not folder.is_dir():
        return []
    named = [p for p in folder.rglob("biodata.bin") if p.is_file()]
    candidates = named or [p for p in folder.rglob("*") if p.is_file() and p.stat().st_size == FILE_SIZE]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates
