import gzip, io, tarfile, tempfile, unittest, zipfile
from pathlib import Path

from core.file_processing.archive import extract_archive
from core.file_processing.processor import FileProcessor
from core.file_processing.models import FAILED, PARTIAL, COMPLETED


class BoomOCR:
    def ocr_image(self, image):
        raise RuntimeError("ocr down")


class NoVision:
    def analyze(self, reference, metadata):
        raise RuntimeError("vision down")


def png(w=8, h=8):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (w, h), "white").save(b, "PNG"); return b.getvalue()


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    def zip(self, files, name="a.zip"):
        p = self.d / name
        with zipfile.ZipFile(p, "w") as z:
            for k, v in files.items(): z.writestr(k, v)
        return p

    def test_zip_nested_dirs_text(self):
        r = FileProcessor(ocr=BoomOCR(), vision=NoVision()).process(self.zip({"a/b/config.rsc": "/ip address", "x.txt": "hi"}))
        self.assertEqual(r.status, COMPLETED); self.assertEqual(len(r.text), 2)

    def test_path_traversal_blocked(self):
        r = FileProcessor().process(self.zip({"../evil.txt": "x", "ok.txt": "y"}))
        self.assertEqual(r.status, PARTIAL)
        self.assertTrue(any(e["code"] == "security_blocked" for e in r.errors))
        self.assertFalse((self.d.parent / "evil.txt").exists())

    def test_corrupted_archive(self):
        p = self.d / "bad.zip"; p.write_bytes(b"PK\x03\x04garbage")
        r = FileProcessor().process(p)
        self.assertEqual(r.status, FAILED); self.assertEqual(r.errors[0]["code"], "corrupted_archive")

    def test_unsupported(self):
        p = self.d / "x.bin"; p.write_bytes(b"\x00\x01\x02")
        r = FileProcessor().process(p)
        self.assertEqual(r.status, FAILED); self.assertEqual(r.errors[0]["code"], "unsupported_format")

    def test_partial_mixed(self):
        r = FileProcessor().process(self.zip({"a.txt": "ok", "b.bin": b"\x00\x00"}))
        self.assertEqual(r.status, PARTIAL)

    def test_ocr_and_vision_failure_reported(self):
        p = self.d / "i.png"; p.write_bytes(png())
        r = FileProcessor(ocr=BoomOCR(), vision=NoVision()).process(p)
        codes = {e["code"] for e in r.errors}
        self.assertEqual(r.status, FAILED); self.assertEqual(codes, {"ocr_failed", "vision_failed"})

    def test_vision_fails_ocr_still_works(self):
        class OK:
            def ocr_image(self, i): return {"extracted_text": "R1", "lines": [], "confidence": 90.0, "language": "eng", "engine": "t"}
        p = self.d / "i.png"; p.write_bytes(png())
        r = FileProcessor(ocr=OK(), vision=NoVision()).process(p)
        self.assertEqual(r.status, PARTIAL); self.assertEqual(r.ocr[0]["extracted_text"], "R1")

    def test_tgz_and_gz(self):
        p = self.d / "a.tgz"
        with tarfile.open(p, "w:gz") as t:
            i = tarfile.TarInfo("d/f.txt"); data = b"hello"; i.size = len(data); t.addfile(i, io.BytesIO(data))
            l = tarfile.TarInfo("link"); l.type = tarfile.SYMTYPE; l.linkname = "/etc/passwd"; t.addfile(l)
        r = FileProcessor().process(p)
        self.assertEqual(r.text[0]["text"], "hello")
        self.assertTrue(any(e["code"] == "security_blocked" for e in r.errors))
        g = self.d / "n.txt.gz"; g.write_bytes(gzip.compress(b"zz"))
        self.assertEqual(FileProcessor().process(g).text[0]["text"], "zz")

    def test_large_file_no_size_limit(self):
        p = self.d / "big.log"; p.write_text("line\n" * 3_000_000)
        r = FileProcessor().process(p)
        self.assertEqual(len(r.text[0]["text"]), 15_000_000)

    def test_bomb_guard(self):
        from core.file_processing.archive import ArchiveLimits
        p = self.zip({"z.bin": b"\x00" * 5_000_000})
        rep = extract_archive(p, self.d / "o", ArchiveLimits(max_ratio=10, expansion_floor=1000))
        self.assertTrue(rep.fatal); self.assertEqual(rep.errors[0][0], "resource_exhausted")

    def test_nested_depth(self):
        inner = self.zip({"a.txt": "x"}, "in.zip")
        outer = self.zip({"in.zip": inner.read_bytes()}, "out.zip")
        from core.file_processing.archive import ArchiveLimits
        r = FileProcessor(limits=ArchiveLimits(max_depth=1)).process(outer)
        self.assertTrue(any(e["code"] == "security_blocked" for e in r.errors))
        r2 = FileProcessor().process(outer); self.assertEqual(r2.text[0]["text"], "x")


if __name__ == "__main__":
    unittest.main()
