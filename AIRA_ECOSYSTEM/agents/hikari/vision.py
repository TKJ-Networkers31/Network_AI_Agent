"""
agents/hikari/vision.py — HIKARI (Hybrid Intelligent Knowledge & Augmented
Recognition Interface).

Peran: YOLO object detection, OCR, screenshot analysis, camera understanding,
diagram understanding. Model lokal: YOLO11n (sesuai model mapping master
prompt - "jangan menjalankan model besar secara lokal").

Ini wrapper tipis di atas tools/vision/detector.py yang sudah ada (logic
OpenCV + Ultralytics YOLO TIDAK ditulis ulang). Sama seperti AKANE, tujuan
lapisan ini supaya orchestrator/api hanya kenal `agents.hikari`, tidak
pernah `import tools.vision` langsung.

TODO migrasi:
  1. git mv tools/vision -> AIRA_ECOSYSTEM/tools/vision (Tahap 4)
  2. Uncomment import di bawah.
  3. Tambahkan OCR & screenshot analysis sebagai fungsi baru di sini kalau
     sudah ada implementasinya (belum ada di repo lama).
"""

# from tools.vision.detector import detect_objects as _detect_objects


def detect_objects(camera_index: int = 0, duration: float = 4.0,
                    show_window: bool = True, save_snapshot: bool = True) -> dict:
    """TODO: return _detect_objects(camera_index, duration, show_window, save_snapshot)"""
    return {
        "success": False,
        "tool": "detect_objects",
        "error": "HIKARI.detect_objects belum disambungkan ke tools/vision - lihat MIGRATION_PLAN.md Tahap 4.",
    }


def recognize_object(camera_index: int = 0) -> dict:
    """
    Belum ada implementasinya di repo lama (baru disebut di system prompt
    engine.py sebagai tool masa depan) - TODO implementasi nyata: ambil satu
    foto, kirim ke model vision-capable (lewat agents/rei/provider_client
    HANYA kalau butuh model eksternal - ingat: HIKARI sendiri tidak boleh
    panggil OpenRouter langsung, harus minta REI).
    """
    return {
        "success": False,
        "tool": "recognize_object",
        "error": "Belum diimplementasikan.",
    }
