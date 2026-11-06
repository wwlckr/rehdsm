"""Encryption of the biodata.bin container.

Blowfish ECB with 32-bit words in little-endian order: every 4-byte group must be
byte-swapped before and after using a standard (big-endian) Blowfish library.
See FORMAT.md, sections 1 and 2.
"""
import hashlib
import struct

from Crypto.Cipher import Blowfish

KEY = b"SBmdYgEamc=#sA0)Mhs9#>/4iiXbMPxW"
SHA_OFFSET = 0x0C
SHA_END = 0x20
LEN_OFFSET = 0x20
DATA_START = 0x40


def _swap32(data: bytes) -> bytes:
    n = len(data) // 4
    return struct.pack(f"<{n}I", *struct.unpack(f">{n}I", data))


def _cipher():
    return Blowfish.new(KEY, Blowfish.MODE_ECB)


def decrypt(raw: bytes) -> bytes:
    if len(raw) % 8:
        raise ValueError("File size is not a multiple of 8: not a valid biodata.bin.")
    return _swap32(_cipher().decrypt(_swap32(raw)))


def encrypt(plain: bytes) -> bytes:
    if len(plain) % 8:
        raise ValueError("Data size is not a multiple of 8.")
    return _swap32(_cipher().encrypt(_swap32(plain)))


def compute_sha_field(plain: bytes) -> bytes:
    length = struct.unpack_from("<I", plain, LEN_OFFSET)[0]
    if DATA_START + length > len(plain):
        raise ValueError("Data length out of range.")
    return _swap32(hashlib.sha1(plain[DATA_START:DATA_START + length]).digest())


def verify(plain: bytes) -> bool:
    try:
        return plain[SHA_OFFSET:SHA_END] == compute_sha_field(plain)
    except ValueError:
        return False


def fix_checksum(plain: bytes) -> bytes:
    buf = bytearray(plain)
    buf[SHA_OFFSET:SHA_END] = compute_sha_field(plain)
    return bytes(buf)
