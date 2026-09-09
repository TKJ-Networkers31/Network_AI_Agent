"""
agents/hikari/vision.py — HIKARI (Hybrid Intelligent Knowledge & Augmented
Recognition Interface). Wrapper tipis di atas tools/vision/detector.py
(sudah dipindah ke AIRA_ECOSYSTEM/tools/vision).
"""

from tools.vision.detector import (
    detect_objects as _detect_objects,
    FUSION_LIVE_DURATION,
)

__all__ = ["detect_objects", "recognize_object", "FUSION_LIVE_DURATION"]


def detect_objects(camera_index: int = 0, duration: float = 4.0,
                    show_window: bool = True, save_snapshot: bool = True) -> dict:
    return _detect_objects(
        camera_index=camera_index, duration=duration,
        show_window=show_window, save_snapshot=save_snapshot,
    )


def recognize_object(camera_index: int = 0) -> dict:
    """
    Belum ada implementasi di repo lama juga (tool ini disebut di skema
    LLM tapi tidak pernah ada di TOOL_MAP lama) - status dipertahankan
    sama seperti sebelumnya, bukan regresi baru.
    """
    return {
        "success": False,
        "tool": "recognize_object",
        "error": "Belum diimplementasikan.",
    }
