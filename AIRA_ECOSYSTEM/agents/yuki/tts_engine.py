"""
Text-to-speech via Kokoro (lokal/offline, ONNX runtime).

Model file (kokoro-v0_19.onnx + voices.bin) HARUS didownload
manual dan ditaruh di models/kokoro/ - lihat instruksi di
requirements.txt. Modul ini gagal-aman: kalau model belum ada,
speak() akan return False dan log error, bukan crash seluruh
agent.
"""

from pathlib import Path

import sounddevice as sd

from agent.core.logger import log_error, logger


BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = BASE_DIR / "models" / "kokoro" / "kokoro-v0_19.onnx"
VOICES_PATH = BASE_DIR / "models" / "kokoro" / "voices.bin"

# Suara default. "af_sarah" adalah salah satu voice bawaan Kokoro
# (American Female). Ganti sesuai voice yang tersedia di voices.bin
# kamu - list lengkap ada di dokumentasi kokoro-onnx.
DEFAULT_VOICE = "af_sarah"

_kokoro_instance = None


def _get_kokoro():

    global _kokoro_instance

    if _kokoro_instance is not None:
        return _kokoro_instance

    if not MODEL_PATH.exists() or not VOICES_PATH.exists():
        log_error(
            "tts._get_kokoro",
            f"Model Kokoro tidak ditemukan di {MODEL_PATH} - "
            f"download dulu sesuai instruksi setup."
        )
        return None

    try:
        from kokoro_onnx import Kokoro
        _kokoro_instance = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        return _kokoro_instance

    except Exception as exc:
        log_error("tts._get_kokoro", exc)
        return None


def speak(text, voice=DEFAULT_VOICE, speed=1.0, on_start=None, on_end=None):
    """
    Sintesis teks jadi audio lalu langsung diputar (blocking sampai
    selesai). on_start/on_end adalah callback opsional - dipakai
    voice_io.py untuk pause/resume mic selama TTS bicara (barge-in
    prevention).

    Return True kalau berhasil bicara, False kalau gagal (model
    belum ada / teks kosong / error runtime).
    """

    if not text or not text.strip():
        return False

    kokoro = _get_kokoro()

    if kokoro is None:
        return False

    try:

        samples, sample_rate = kokoro.create(
            text,
            voice=voice,
            speed=speed,
            lang="en-us",  # lihat catatan: Kokoro belum native ID
        )

        if on_start:
            on_start()

        sd.play(samples, sample_rate)
        sd.wait()  # blocking sampai audio selesai diputar

        if on_end:
            on_end()

        return True

    except Exception as exc:

        log_error("tts.speak", exc)

        if on_end:
            on_end()

        return False