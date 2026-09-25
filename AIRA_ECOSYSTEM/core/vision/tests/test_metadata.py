import struct
import unittest

from core.vision.metadata import extract_image_dimensions


def _make_png(width, height):
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return sig + struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"


def _make_gif(width, height):
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


def _make_jpeg(width, height):
    payload = struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00"
    sof0 = b"\xff\xc0" + struct.pack(">H", len(payload) + 2) + payload
    return b"\xff\xd8" + sof0 + b"\xff\xd9"


def _make_webp_vp8x(width, height):
    payload = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    header = b"RIFF" + struct.pack("<I", 4 + 4 + 4 + len(payload)) + b"WEBP" + b"VP8X" + struct.pack("<I", len(payload))
    return header + payload


def _make_svg(width, height):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect/></svg>'.encode()


class TestExtractImageDimensions(unittest.TestCase):

    def test_png_dimensions(self):
        self.assertEqual(extract_image_dimensions(_make_png(800, 600), "image/png"), (800, 600))

    def test_gif_dimensions(self):
        self.assertEqual(extract_image_dimensions(_make_gif(320, 240), "image/gif"), (320, 240))

    def test_jpeg_dimensions(self):
        self.assertEqual(extract_image_dimensions(_make_jpeg(1024, 768), "image/jpeg"), (1024, 768))

    def test_webp_vp8x_dimensions(self):
        self.assertEqual(extract_image_dimensions(_make_webp_vp8x(500, 400), "image/webp"), (500, 400))

    def test_svg_dimensions(self):
        self.assertEqual(extract_image_dimensions(_make_svg(120, 80), "image/svg+xml"), (120, 80))

    def test_unsupported_mime_returns_none(self):
        self.assertEqual(extract_image_dimensions(b"whatever", "application/pdf"), (None, None))

    def test_corrupt_png_header_returns_none_not_raise(self):
        self.assertEqual(extract_image_dimensions(b"\x89PNG\r\n\x1a\ngarbage", "image/png"), (None, None))

    def test_empty_content_returns_none(self):
        self.assertEqual(extract_image_dimensions(b"", "image/png"), (None, None))

    def test_non_bytes_content_returns_none_not_raise(self):
        self.assertEqual(extract_image_dimensions("not bytes", "image/png"), (None, None))  # type: ignore[arg-type]

    def test_svg_without_width_height_returns_none(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
        self.assertEqual(extract_image_dimensions(svg, "image/svg+xml"), (None, None))

    def test_webp_plain_vp8_not_decoded(self):
        data = b"RIFF" + struct.pack("<I", 20) + b"WEBP" + b"VP8 " + struct.pack("<I", 8) + b"\x00" * 8
        self.assertEqual(extract_image_dimensions(data, "image/webp"), (None, None))


if __name__ == "__main__":
    unittest.main()