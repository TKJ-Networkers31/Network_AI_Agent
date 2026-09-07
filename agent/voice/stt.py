"""
Speech-to-text via faster-whisper (lokal, offline, CPU-only).

Kenapa faster-whisper bukan openai-whisper asli: faster-whisper
pakai CTranslate2 sebagai backend inference, jauh lebih cepat dan
lebih hemat memory dibanding implementasi PyTorch asli - penting
di hardware 2-core/4-thread seperti X270.

Model "tiny" dipilih karena ini yang paling ringan (~75MB, ~39M
parameter). Trade-off: akurasi lebih rendah dari base/small,
terutama untuk audio noisy atau aksen kurang jelas. Kalau nanti
akurasi terasa kurang dan CPU masih ada headroom, "base" adalah
langkah upgrade berikutnya yang wajar.

Model didownload OTOMATIS dari HuggingFace Hub saat pertama kali
dipanggil (butuh internet sekali saja), lalu di-cache lokal
(default di ~/.cache/huggingface) dan dipakai offline setelahnya.
"""

from faster_whisper import WhisperModel

from agent.core.logger import log_error, logger


MODEL_SIZE = "tiny"

# compute_type "int8" dipilih karena paling ringan untuk CPU-only -
# quantized ke 8-bit, jauh lebih cepat dari float32 dengan penurunan
# akurasi yang biasanya masih dapat diterima untuk model sekecil tiny.
COMPUTE_TYPE = "int8"

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
    / kosong.
    """

    if audio_int16 is None or len(audio_int16) == 0:
        return None

    model = _get_model()

    if model is None:
        return None

    # faster-whisper minta float32 range [-1, 1], bukan int16 mentah.
    audio_float32 = audio_int16.astype("float32") / 32768.0

    try:

        segments, info = model.transcribe(
            audio_float32,
            language="id",
            beam_size=1,       # beam_size=1 = greedy decode, paling
                                # cepat untuk CPU lemah (trade-off
                                # sedikit akurasi vs kecepatan)
            vad_filter=False,  # VAD sudah dilakukan sebelumnya di
                                # voice_io.py (webrtcvad), tidak perlu
                                # double-filter di sini
        )

        text = " ".join(segment.text.strip() for segment in segments).strip()