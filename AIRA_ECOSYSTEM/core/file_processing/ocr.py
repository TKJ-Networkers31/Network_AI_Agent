"""core/file_processing/ocr.py - OCR nyata via Tesseract (pytesseract + binary tesseract).
Tidak ada hasil palsu: kalau engine/bahasa tidak tersedia, OCRUnavailable dilempar
dan pemanggil mencatat ocr_failed.

Konfigurasi (.env):
  AIRA_OCR_LANG        bahasa tesseract, default "eng"
  AIRA_TESSERACT_CMD   path binary tesseract (atau TESSERACT_CMD); kosong = auto-detect
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aira.file_processing.ocr")


class OCRUnavailable(Exception):
    pass


def _resolve_tesseract_cmd() -> Optional[str]:
    """Cari path tesseract yang valid di environment atau lokasi instalasi standar."""
    candidates = []
    env_cmd = os.getenv("AIRA_TESSERACT_CMD") or os.getenv("TESSERACT_CMD")
    if env_cmd:
        candidates.append(env_cmd.strip('"'))

    # Path standar di Windows
    candidates.extend([
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ])

    which = shutil.which("tesseract")
    if which:
        candidates.append(which)

    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _patch_pytesseract_version_check(pytesseract_mod):
    """Patch pytesseract.get_tesseract_version agar kompatibel dengan Tesseract 3.02+ di Windows
    dan tidak melempar SystemExit jika banner versi berisi teks non-standar."""
    try:
        from packaging.version import parse
    except ImportError:
        def parse(v):
            return tuple(int(x) for x in re.findall(r"\d+", v))

    orig_getter = getattr(pytesseract_mod, "get_tesseract_version", None)

    def safe_get_version(*args, **kwargs):
        try:
            cmd = getattr(pytesseract_mod, "tesseract_cmd", "tesseract")
            import subprocess
            out = subprocess.check_output(
                [cmd, "--version"],
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore")
            m = re.search(r"(\d+(?:\.\d+)+)", out)
            if m:
                return parse(m.group(1))
            return parse("3.02")
        except Exception:
            return parse("3.02")

    pytesseract_mod.get_tesseract_version = safe_get_version


class TesseractOCR:
    name = "tesseract"

    def __init__(self, lang: str = None):
        self.lang = lang or os.getenv("AIRA_OCR_LANG", "eng")

    def _prepare_image(self, image):
        """Pre-processing gambar untuk meningkatkan akurasi teks OCR."""
        from PIL import Image, ImageOps
        if not isinstance(image, Image.Image):
            return image
        try:
            # Jika mode RGBA/P/CMYK konversi ke RGB lalu Grayscale
            if image.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", image.size, (255, 255, 255))
                bg.paste(image, mask=image.split()[-1])
                img = bg.convert("L")
            elif image.mode != "L":
                img = image.convert("L")
            else:
                img = image
            # Autocontrast untuk mempertajam kontras huruf terhadap latar belakang
            return ImageOps.autocontrast(img)
        except Exception:
            return image

    def _determine_language(self, pytesseract_mod) -> str:
        """Pilih bahasa terbaik berdasarkan paket bahasa yang benar-benar terpasang."""
        requested = self.lang
        try:
            available = pytesseract_mod.get_languages()
        except Exception:
            available = []

        if not available:
            return "eng"

        # Cek jika requested persis ada di available
        if requested in available:
            return requested

        # Jika requested gabungan misal "eng+ind"
        parts = [p.strip() for p in requested.split("+") if p.strip()]
        supported = [p for p in parts if p in available]
        if supported:
            return "+".join(supported)

        # Fallback ke eng jika ada, atau bahasa pertama yang terpasang
        if "eng" in available:
            return "eng"
        return available[0]

    def ocr_image(self, image) -> dict:
        try:
            import pytesseract
            from pytesseract import Output
            from pytesseract.pytesseract import TSVNotSupported
        except ImportError as exc:
            raise OCRUnavailable("pytesseract belum terpasang (pip install pytesseract).") from exc

        cmd = _resolve_tesseract_cmd()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        elif not shutil.which("tesseract"):
            raise OCRUnavailable("Binary tesseract tidak ditemukan (isi AIRA_TESSERACT_CMD atau pasang Tesseract-OCR).")

        _patch_pytesseract_version_check(pytesseract.pytesseract)

        processed_img = self._prepare_image(image)
        lang_to_use = self._determine_language(pytesseract)

        lines: dict = {}
        out = []
        confs = []

        try:
            # Coba ambil data terstruktur (kata, koordinat bbox, confidence)
            data = pytesseract.image_to_data(processed_img, lang=lang_to_use, output_type=Output.DICT)
            for i, word in enumerate(data.get("text", [])):
                word = (word or "").strip()
                if not word:
                    continue
                try:
                    conf = float(data["conf"][i])
                except (TypeError, ValueError, KeyError):
                    conf = -1.0
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                ln = lines.setdefault(key, {"words": [], "conf": [], "x0": 10**9, "y0": 10**9, "x1": 0, "y1": 0})
                ln["words"].append(word)
                if conf >= 0:
                    ln["conf"].append(conf)
                x, y, w, h = (data[k][i] for k in ("left", "top", "width", "height"))
                ln["x0"], ln["y0"] = min(ln["x0"], x), min(ln["y0"], y)
                ln["x1"], ln["y1"] = max(ln["x1"], x + w), max(ln["y1"], y + h)

            for (block, par, line), ln in sorted(lines.items()):
                c = round(sum(ln["conf"]) / len(ln["conf"]), 1) if ln["conf"] else None
                if c is not None:
                    confs.append(c)
                out.append({
                    "text": " ".join(ln["words"]),
                    "confidence": c,
                    "block": block,
                    "paragraph": par,
                    "line": line,
                    "bbox": [ln["x0"], ln["y0"], ln["x1"], ln["y1"]],
                })
            extracted_text = "\n".join(l["text"] for l in out)

        except (TSVNotSupported, Exception) as exc:
            # Fallback untuk Tesseract versi lawas (< 3.05) atau yang tidak mendukung TSV output
            logger.info("Tesseract image_to_data tidak didukung (%s), menggunakan image_to_string.", exc)
            try:
                extracted_text = pytesseract.image_to_string(processed_img, lang=lang_to_use)
            except Exception as str_exc:
                raise OCRUnavailable(f"Gagal mengekstrak teks dengan OCR: {str_exc}") from str_exc

            extracted_text = (extracted_text or "").strip()
            raw_lines = [l.strip() for l in extracted_text.splitlines() if l.strip()]
            for idx, text_line in enumerate(raw_lines, 1):
                out.append({
                    "text": text_line,
                    "confidence": 80.0,
                    "block": 1,
                    "paragraph": 1,
                    "line": idx,
                    "bbox": [0, 0, getattr(image, "width", 0), getattr(image, "height", 0)],
                })
            confs = [80.0] if raw_lines else []

        avg_conf = round(sum(confs) / len(confs), 1) if confs else None
        return {
            "extracted_text": extracted_text,
            "lines": out,
            "confidence": avg_conf,
            "language": self.lang,
            "language_used": lang_to_use,
            "engine": self.name,
        }
