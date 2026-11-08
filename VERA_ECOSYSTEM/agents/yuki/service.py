"""
agents/yuki/service.py — Manajer Layanan Suara Latar Belakang (Background Voice Service).

Menyediakan orkestrasi lifecycle resmi:
  STOPPED -> STARTING -> RUNNING -> LISTENING -> PROCESSING -> ERROR / PAUSED

Memastikan integrasi aman dengan Event Bus, perlindungan duplikasi proses,
manajemen perangkat audio fisik host, dan isolasi dari chat PWA.
"""

import logging
import threading
from typing import Any, Dict, Optional

from agents.yuki.voice_io import (
    STATE_ERROR,
    STATE_LISTENING,
    STATE_PAUSED,
    STATE_PROCESSING,
    STATE_RUNNING,
    STATE_STARTING,
    STATE_STOPPED,
    VoiceIO,
)
from core.events import EventNames, event_bus

logger = logging.getLogger("aira.yuki.service")

_GLOBAL_VOICE_SERVICE: Optional["BackgroundVoiceService"] = None
_GLOBAL_LOCK = threading.Lock()


class BackgroundVoiceService:
    """
    Manajer Layanan Suara Latar Belakang untuk AIRA OS.
    Beroperasi secara mandiri di sisi server host (Python runtime).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._voice_io = VoiceIO(on_transcript=self._handle_transcript)
        self._auto_start_enabled = False

    def _handle_transcript(self, text: str) -> None:
        """Dipanggil oleh VoiceIO saat ucapan pengguna di transkrip."""
        if not text or not text.strip():
            return

        # Publikasikan event ke Event Bus sistem
        try:
            event_bus.publish(
                EventNames.VOICE_LISTENING_STOP,
                {
                    "transcript": text,
                    "source": "background_voice_service",
                    "channel": "host_microphone",
                },
            )
        except Exception as exc:
            logger.warning("BackgroundVoiceService | Gagal mempublikasikan event transcript: %s", exc)

    def _get_devices_list(self) -> list:
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            input_devs = []
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0:
                    input_devs.append({
                        "index": i,
                        "name": d.get("name"),
                        "channels": d.get("max_input_channels"),
                    })
            return input_devs
        except Exception:
            return []

    def get_status(self) -> Dict[str, Any]:
        """Mengembalikan status detail operasional layanan suara latar belakang."""
        stats = self._voice_io.stats
        current_state = stats.get("state", STATE_STOPPED)
        return {
            "success": True,
            "service_name": "AIRA Background Voice Service",
            "state": current_state,
            "service_state": current_state,
            "is_running": stats.get("is_active", False),
            "is_listening": current_state == STATE_LISTENING,
            "is_paused": stats.get("is_paused", False),
            "pause_reason": stats.get("pause_reason"),
            "audio_backend": stats.get("audio_backend", "sounddevice (PortAudio)"),
            "active_backend": stats.get("audio_backend", "sounddevice (PortAudio)"),
            "sample_rate": stats.get("sample_rate", 16000),
            "device": stats.get("device", {}),
            "devices": self._get_devices_list(),
            "last_error": stats.get("last_error"),
            "last_capture_at": stats.get("last_capture_at"),
            "last_transcript_at": stats.get("last_transcript_at"),
            "last_transcript_snippet": stats.get("last_transcript_snippet"),
            "stt_engine": "faster-whisper (tiny int8)",
            "supported": True,
        }

    def start(self) -> Dict[str, Any]:
        """Memulai layanan suara latar belakang."""
        with self._lock:
            return self._voice_io.start()

    def stop(self) -> Dict[str, Any]:
        """Menghentikan layanan suara latar belakang."""
        with self._lock:
            return self._voice_io.stop()

    def pause(self, reason: str = "manual") -> Dict[str, Any]:
        """Menjeda penangkapan mikrofon sementara."""
        with self._lock:
            return self._voice_io.pause_mic(reason=reason)

    def resume(self) -> Dict[str, Any]:
        """Melanjutkan penangkapan mikrofon."""
        with self._lock:
            return self._voice_io.resume_mic()


def get_voice_service() -> BackgroundVoiceService:
    """Mengembalikan instance singleton BackgroundVoiceService."""
    global _GLOBAL_VOICE_SERVICE
    if _GLOBAL_VOICE_SERVICE is None:
        with _GLOBAL_LOCK:
            if _GLOBAL_VOICE_SERVICE is None:
                _GLOBAL_VOICE_SERVICE = BackgroundVoiceService()
    return _GLOBAL_VOICE_SERVICE
