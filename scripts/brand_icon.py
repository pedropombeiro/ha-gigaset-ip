"""Build a simple original phone-status icon using only the standard library."""

import struct
import zlib
from pathlib import Path


def chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def generate(size):
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            px, py = x * 256 / size, y * 256 / size
            color = (26, 54, 78, 255)
            if 75 <= px <= 177 and 30 <= py <= 224:
                color = (235, 244, 250, 255)
            if 91 <= px <= 161 and 57 <= py <= 126:
                color = (26, 54, 78, 255)
            if 111 <= px <= 141 and 151 <= py <= 181:
                color = (26, 54, 78, 255)
            if (px - 185) ** 2 + (py - 185) ** 2 < 31**2:
                color = (44, 194, 132, 255)
            rows.extend(color)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    folder = Path(__file__).parents[1] / "custom_components/gigaset_ip/brand"
    folder.mkdir(exist_ok=True)
    for filename, size in (("icon.png", 256), ("icon@2x.png", 512)):
        (folder / filename).write_bytes(generate(size))
