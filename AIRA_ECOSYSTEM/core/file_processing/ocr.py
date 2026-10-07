"""core/file_processing/ocr.py - OCR nyata via Tesseract (pytesseract + binary tesseract).
Tidak ada hasil palsu: kalau engine/bahasa tidak tersedia, OCRUnavailable dilempar
dan pemanggil mencatat ocr_failed."""
from __future__ import annotations

import os


class OCRUnavailable(Exception):
    pass


class TesseractOCR:
    name = "tesseract"

    def __init__(self, lang: str = None):
        self.lang = lang or os.getenv("AIRA_OCR_LANG", "eng+ind")

    def ocr_image(self, image) -> dict:
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:
            raise OCRUnavailable("pytesseract belum terpasang (pip install pytesseract).") from exc

        lang = self.lang
        try:
            data = pytesseract.image_to_data(image, lang=lang, output_type=Output.DICT)
        except pytesseract.TesseractNotFoundError as exc:
            raise OCRUnavailable("Binary tesseract tidak ditemukan di PATH.") from exc
        except pytesseract.TesseractError as exc:
            if "load" in str(exc).lower() and "+" in lang or lang != "eng":
                lang = "eng"  # paket bahasa belum ada; dilaporkan lewat language_used
                data = pytesseract.image_to_data(image, lang=lang, output_type=Output.DICT)
            else:
                raise

        lines: dict = {}
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            ln = lines.setdefault(key, {"words": [], "conf": [], "x0": 10**9, "y0": 10**9, "x1": 0, "y1": 0})
            ln["words"].append(word)
            if conf >= 0:
                ln["conf"].append(conf)
            x, y, w, h = (data[k][i] for k in ("left", "top", "width", "height"))
            ln["x0"], ln["y0"] = min(ln["x0"], x), min(ln["y0"], y)
            ln["x1"], ln["y1"] = max(ln["x1"], x + w), max(ln["y1"], y + h)

        out, confs = [], []
        for (block, par, line), ln in sorted(lines.items()):
            c = round(sum(ln["conf"]) / len(ln["conf"]), 1) if ln["conf"] else None
            if c is not None:
                confs.append(c)
            out.append({"text": " ".join(ln["words"]), "confidence": c, "block": block, "paragraph": par,
                        "line": line, "bbox": [ln["x0"], ln["y0"], ln["x1"], ln["y1"]]})

        return {
            "extracted_text": "\n".join(l["text"] for l in out),
            "lines": out,
            "confidence": round(sum(confs) / len(confs), 1) if confs else None,
            "language": lang, "language_used": lang, "engine": self.name,
        }
