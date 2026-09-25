"""
core/vision/metadata.py — ekstraksi dimensi piksel untuk Image & Visual
Input (Sprint 2.7 / Wave 2 / Worker 3).

Hanya membaca byte HEADER file yang diperlukan untuk menemukan
lebar/tinggi - tidak pernah men-decode piksel, tidak pernah "melihat"
gambar. Ini ekstraksi metadata, bukan analisis gambar (batas analisis ada
di core/vision/provider.py).

Didukung: PNG, GIF, JPEG, WEBP (chunk 'VP8X' saja - lihat LIMITASI di
bawah), dan pembacaan best-effort atribut width/height literal pada tag
root <svg>. Selain itu (atau header yang gagal diparse) mengembalikan
(None, None) - tidak pernah raise, tidak pernah menebak.

LIMITASI (didokumentasikan, tidak ditutup-tutupi):
  - WEBP: hanya chunk 'VP8X' (extended format) yang diparse. Payload WEBP
    lossy biasa ('VP8 ') dan lossless ('VP8L') TIDAK di-decode di sini -
    mengembalikan (None, None) untuk variant tersebut.
  - SVG: width/height dibaca sebagai teks literal pada atribut tag <svg>
    (mis. "120" atau "120px"); SVG yang hanya punya persentase/viewBox
    mengembalikan (None, None), bukan hasil tebakan.
"""

from __future__ import annotations

import re
import struct
from typing import Optional


def _png_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    if data[12:16] != b"IHDR":
        return None, None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _gif_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 10 or data[:3] != b"GIF":
        return None, None
    width, height = struct.unpack("<HH", data[6:10])
    return width, height


_SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def _jpeg_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None, None

    offset = 2
    total = len(data)

    while offset + 4 <= total:
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker = data[offset + 1]

        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue

        segment_length = struct.unpack(">H", data[offset + 2:offset + 4])[0]

        if marker in _SOF_MARKERS:
            if offset + 9 > total:
                return None, None
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return width, height

        if marker == 0xD9 or segment_length < 2:  # EOI / rusak
            break

        offset += 2 + segment_length

    return None, None


def _webp_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None, None

    if data[12:16] == b"VP8X":
        width = 1 + (data[24] | (data[25] << 8) | (data[26] << 16))
        height = 1 + (data[27] | (data[28] << 8) | (data[29] << 16))
        return width, height

    # VP8 / VP8L (format sederhana) sengaja tidak di-decode di sini.
    return None, None


_SVG_TAG_RE = re.compile(rb"<svg\b[^>]*>", re.DOTALL)
_SVG_ATTR_RE = re.compile(rb'\b(width|height)\s*=\s*"([0-9]+(?:\.[0-9]+)?)')


def _svg_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    head = data[:4096]

    tag_match = _SVG_TAG_RE.search(head)
    if tag_match is None:
        return None, None

    found = dict(re.findall(_SVG_ATTR_RE, tag_match.group(0)))

    def _to_int(raw: Optional[bytes]) -> Optional[int]:
        if raw is None:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    return _to_int(found.get(b"width")), _to_int(found.get(b"height"))


_PARSERS = {
    "image/png": _png_dimensions,
    "image/gif": _gif_dimensions,
    "image/jpeg": _jpeg_dimensions,
    "image/webp": _webp_dimensions,
    "image/svg+xml": _svg_dimensions,
}


def extract_image_dimensions(content: bytes, mime_type: str) -> tuple[Optional[int], Optional[int]]:
    """(width, height) hasil parse header file, atau (None, None) kalau
    mime_type tidak didukung atau header gagal diparse. Tidak pernah raise."""
    if not isinstance(content, (bytes, bytearray)) or not content:
        return None, None

    parser = _PARSERS.get((mime_type or "").strip().lower())

    if parser is None:
        return None, None

    try:
        return parser(bytes(content))
    except Exception:
        return None, None