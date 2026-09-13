"""
Text-to-speech via Kokoro (lokal/offline, ONNX runtime).

Model file (kokoro-v0_19.onnx + voices.bin) HARUS didownload manual dan
ditaruh di models/kokoro/ - lihat DOWNLOAD_INSTRUCTIONS di bawah, atau
jalankan scripts/download_kokoro_model.ps1. Modul ini gagal-aman: kalau
model belum ada, speak()/synthesize_bytes() akan return False/None dan
log error dengan instruksi jelas, bukan crash seluruh agent.

FIX (TTS gagal total karena model belum ada):
- Folder models/kokoro/ sekarang dibuat otomatis kalau belum ada.
- Pesan error mencantumkan PERSIS 2 URL yang harus didownload plus nama
  file tujuannya, supaya jelas apa yang kurang tanpa perlu baca source.
- Menambahkan log sukses eksplisit ("TTS | model Kokoro berhasil
  dimuat...") supaya gampang diverifikasi lewat logs/categories/tts.log.

Menambahkan synthesize_bytes() yang mengembalikan audio sebagai bytes
WAV, TANPA memutar lewat sounddevice. Dipakai oleh api/routers/ws.py
untuk giliran suara dari PWA (audio dikirim ke browser client untuk
diputar di sana), sedangkan speak() yang lama TETAP dipakai apa
adanya oleh run_chat.py / agents/yuki/voice_io.py untuk mode
terminal (audio diputar langsung di speaker laptop server).
"""

import io
from pathlib import Path

import sounddevice as sd
import soundfile as sf

import logging

logger = logging.getLogger("aira.yuki.tts")


def log_error(context, exc):
    logger.error(f"ERROR | context={context} | detail={exc}")


BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
MODEL_DIR = BASE_DIR / "models" / "kokoro"
MODEL_PATH = MODEL_DIR / "kokoro-v0_19.onnx"
VOICES_PATH = MODEL_DIR / "voices.bin"

DOWNLOAD_INSTRUCTIONS = (
    f"Model Kokoro belum lengkap di {MODEL_DIR}. Download 2 file berikut "
    f"dan taruh persis di folder itu dengan nama yang sama (atau jalankan "
    f"'scripts/download_kokoro_model.ps1' dari root AIRA_ECOSYSTEM):\n"
    f"  1) kokoro-v0_19.onnx -> "
    f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx\n"
    f"  2) voices.bin -> "
    f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"
)

# Suara default. "af_sarah" adalah salah satu voice bawaan Kokoro
# (American Female). Ganti sesuai voice yang tersedia di voices.bin
# kamu - list lengkap ada di dokumentasi kokoro-onnx.
DEFAULT_VOICE = "af_sarah"

_kokoro_instance = None


def _get_kokoro():

    global _kokoro_instance

    if _kokoro_instance is not None:
        return _kokoro_instance

    # Dibuat otomatis supaya user tinggal drop 2 file, tidak perlu
    # bikin folder manual dulu.
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_PATH.exists() or not VOICES_PATH.exists():
        log_error("tts._get_kokoro", DOWNLOAD_INSTRUCTIONS)
        return None

    try:
        from kokoro_onnx import Kokoro
        _kokoro_instance = Kokoro(str(MODEL_PATH), str(VOICES_PATH))

        logger.info(
            "TTS | model Kokoro berhasil dimuat dari %s", MODEL_DIR
        )

        return _kokoro_instance

    except Exception as exc:
        log_error("tts._get_kokoro", exc)
        return None


def speak(text, voice=DEFAULT_VOICE, speed=1.0, on_start=None, on_end=None):
    """
    Sintesis teks jadi audio lalu langsung diputar (blocking sampai
    selesai) LEWAT SPEAKER SERVER. Dipakai mode terminal
    (run_chat.py, voice_io.py) - JANGAN dipakai untuk giliran PWA
    karena akan bunyi di laptop server, bukan di browser user.

    on_start/on_end adalah callback opsional - dipakai voice_io.py
    untuk pause/resume mic selama TTS bicara (barge-in prevention).

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


def synthesize_bytes(text, voice=DEFAULT_VOICE, speed=1.0):
    """
    Sama seperti speak(), tapi TIDAK memutar audio di server - hanya
    mengembalikan bytes WAV siap kirim (mis. di-base64 lalu dikirim
    lewat WebSocket ke browser untuk diputar di sisi client).

    Dipakai SATU-SATUNYA oleh api/routers/ws.py untuk giliran suara
    dari PWA. Return None kalau model belum ada / teks kosong / gagal
    sintesis - pemanggil harus menangani None secara graceful (skip
    audio, tetap kirim teks jawaban).
    """

    if not text or not text.strip():
        return None

    kokoro = _get_kokoro()

    if kokoro is None:
        return None

    try:

        samples, sample_rate = kokoro.create(
            text,
            voice=voice,
            speed=speed,
            lang="en-us",
        )

        buffer = io.BytesIO()
        sf.write(buffer, samples, sample_rate, format="WAV")

        return buffer.getvalue()

    except Exception as exc:

        log_error("tts.synthesize_bytes", exc)
        return None