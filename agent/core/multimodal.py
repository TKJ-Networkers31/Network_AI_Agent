"""
Fusion konteks multi-sumber (suara + visual) menjadi SATU pesan
user sebelum dikirim ke LLM.

Desain ini sengaja mempertahankan "satu otak" - tidak ada LLM
terpisah untuk suara/visi. Karena model chat di project ini
(Ollama qwen3, OpenRouter Nemotron) adalah text-only, bukan
vision-capable, maka "melihat" diwujudkan dengan menerjemahkan
hasil tracking YOLO menjadi ringkasan teks, lalu digabung dengan
teks hasil transkripsi suara jadi satu pesan user tunggal.

Gagal-aman: kalau webcam/YOLO error atau tidak ada objek
terdeteksi, fungsi ini TETAP mengembalikan teks suara asli
tanpa modifikasi - error di jalur visual tidak boleh menghentikan
alur percakapan suara yang sudah berjalan.
"""

from tools.vision.detector import detect_objects, FUSION_LIVE_DURATION
from agent.core.logger import log_error, logger


def _describe_detections(result):

    if not result.get("success"):
        return None

    detections = result.get("detections", [])

    if not detections:
        return None

    counts = {}

    for detection in detections:
        label = detection["label"]
        counts[label] = counts.get(label, 0) + 1

    parts = [
        f"{count}x {label}" if count > 1 else label
        for label, count in counts.items()
    ]

    return "terdeteksi di depan kamera: " + ", ".join(parts)


def fuse_voice_and_vision(voice_text, camera_index=0, show_window=True):
    """
    Jalankan tracking singkat (durasi lebih pendek dari tool call
    manual, supaya tidak terlalu mengganggu alur percakapan suara),
    gabungkan deskripsinya dengan teks hasil transkripsi suara.

    show_window=True akan memunculkan window live preview yang
    sama seperti tool call manual - berguna supaya kamu tahu apa
    yang AI lihat bahkan saat trigger-nya dari suara, bukan
    perintah eksplisit "deteksi objek".
    """

    try:

        result = detect_objects(
            camera_index=camera_index,
            duration=FUSION_LIVE_DURATION,
            show_window=show_window,
            save_snapshot=False,
        )

        description = _describe_detections(result)

    except Exception as exc:

        log_error("multimodal.fuse_voice_and_vision", exc)
        description = None

    if not description:
        return voice_text

    logger.info(f"MULTIMODAL | fusion aktif: {description}")

    return (
        f"{voice_text}\n\n"
        f"[Konteks visual otomatis dari webcam saat pesan ini "
        f"diucapkan: {description}]"
    )