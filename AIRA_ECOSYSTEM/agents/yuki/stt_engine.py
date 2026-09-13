"""
Speech-to-text via faster-whisper (lokal, offline, CPU-only).

Kenapa faster-whisper bukan openai-whisper asli: faster-whisper
pakai CTranslate2 sebagai backend inference, jauh lebih cepat dan
lebih hemat memory dibanding implementasi PyTorch asli - penting
di hardware 2-core/4-thread seperti X270.

Model "tiny" dipilih karena ini yang paling ringan (~75MB, ~39M
parameter). Trade-off: akurasi lebih rendah dari base/small,
terutama untuk audio noisy atau aksen kurang jelas.

Model didownload OTOMATIS dari HuggingFace Hub saat pertama kali
dipanggil (butuh internet sekali saja), lalu di-cache lokal
(default di ~/.cache/huggingface) dan dipakai offline setelahnya.

FIX (halusinasi pada ucapan pendek, mis. "hai" terdeteksi "bye"):
Whisper (termasuk faster-whisper) dikenal berhalusinasi - menghasilkan
teks yang sama sekali tidak diucapkan - ketika audio input terlalu
pendek/nyaris hening, biasanya karena VAD energi sederhana di sisi
client memotong terlalu dini. Tiga lapis mitigasi ditambahkan di sini,
TANPA mengubah signature transcribe(), jadi voice_io.py, ws.py, dan
agents/yuki/stt.py tidak perlu disentuh sama sekali:

  1. MIN_AUDIO_DURATION_SEC - audio yang lebih pendek dari ini
     langsung ditolak sebelum masuk model (hemat CPU + mencegah
     halusinasi akibat audio nyaris kosong).
  2. vad_filter=True + vad_parameters - faster-whisper membuang
     segmen yang terdeteksi non-speech oleh Silero VAD internal
     (sudah dibundel library, tidak perlu install apa pun tambahan)
     sebelum ditranskripsi.
  3. Filter no_speech_probability & avg_logprob per segmen - segmen
     dengan kemungkinan besar "bukan ucapan" (no_speech_prob tinggi)
     atau confidence sangat rendah (avg_logprob sangat negatif)
     dibuang, bukan digabung ke hasil transkrip akhir.

Kalau setelah fix ini akurasi masih kurang untuk kebutuhanmu, opsi
tuning paling berdampak (urutan dari termurah): naikkan
MIN_AUDIO_DURATION_SEC ke 0.7-1.0, atau ganti MODEL_SIZE ke "base"
(lebih akurat, lebih berat).
"""

from faster_whisper import WhisperModel

import logging

logger = logging.getLogger("aira.yuki.stt")


def log_error(context, exc):
    logger.error(f"ERROR | context={context} | detail={exc}")


MODEL_SIZE = "tiny"
COMPUTE_TYPE = "int8"

# --- Anti-halusinasi ---
MIN_AUDIO_DURATION_SEC = 0.5
NO_SPEECH_PROB_THRESHOLD = 0.6
AVG_LOGPROB_THRESHOLD = -1.0

_model_instance = None


def _get_model():

    global _model_instance

    if _model_instance is not None:
        return _model_instance

    try:

        logger.info(
            f"STT | loading model faster-whisper '{MODEL_SIZE}' "
            f"(compute_type={COMPUTE_TYPE})..."
        )

        _model_instance = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type=COMPUTE_TYPE,
        )

        logger.info("STT | model berhasil di-load.")

        return _model_instance

    except Exception as exc:

        log_error("stt._get_model", exc)
        return None


def transcribe(audio_int16, sample_rate=16000):
    """
    audio_int16: numpy array int16 mono (hasil rekaman VAD).
    Return: string teks hasil transkripsi, atau None kalau gagal
    / kosong / audio dinilai terlalu pendek atau bukan ucapan.
    """

    if audio_int16 is None or len(audio_int16) == 0:
        return None

    duration_sec = len(audio_int16) / float(sample_rate)

    if duration_sec < MIN_AUDIO_DURATION_SEC:
        logger.info(
            "STT | audio %.2fs lebih pendek dari batas minimum %.2fs - "
            "dilewati (mencegah halusinasi pada audio nyaris kosong).",
            duration_sec,
            MIN_AUDIO_DURATION_SEC,
        )
        return None

    model = _get_model()

    if model is None:
        return None

    audio_float32 = audio_int16.astype("float32") / 32768.0

    try:

        segments, info = model.transcribe(
            audio_float32,
            language="id",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )

        text_parts = []

        for segment in segments:

            no_speech_prob = getattr(segment, "no_speech_prob", 0.0) or 0.0
            avg_logprob = getattr(segment, "avg_logprob", 0.0) or 0.0

            if no_speech_prob >= NO_SPEECH_PROB_THRESHOLD:
                logger.info(
                    "STT | segmen dibuang (no_speech_prob=%.2f): %r",
                    no_speech_prob,
                    segment.text,
                )
                continue

            if avg_logprob <= AVG_LOGPROB_THRESHOLD:
                logger.info(
                    "STT | segmen dibuang (avg_logprob=%.2f, confidence rendah): %r",
                    avg_logprob,
                    segment.text,
                )
                continue

            cleaned = segment.text.strip()

            if cleaned:
                text_parts.append(cleaned)

        text = " ".join(text_parts).strip()

        return text or None

    except Exception as exc:

        log_error("stt.transcribe", exc)
        return None