"""
agents/yuki/voice_io.py — orkestrasi mic listening + VAD + barge-in untuk
YUKI (wake word akan ditambahkan di sini nanti, belum ada di repo lama).

Wrapper/port dari agent/voice/voice_io.py lama. Bedanya dengan versi lama:
VoiceIO di sini TIDAK boleh langsung panggil agent/core/multimodal.py
(fusion visual) - itu sekarang jadi tanggung jawab agents/hikari, dan
YUKI harus lewat core/orchestrator.py untuk gabungan modalitas, bukan
import langsung ke HIKARI (menjaga tiap agent internal tidak saling
kenal implementasi satu sama lain - hanya orchestrator yang tahu semua).

TODO migrasi: git mv agent/voice/voice_io.py -> agents/yuki/voice_io.py
(file ini), lalu:
  - ganti `from agent.core.multimodal import fuse_voice_and_vision`
    menjadi callback yang di-inject dari core/orchestrator.py.
"""

import logging

logger = logging.getLogger("aira.yuki.voice_io")


class VoiceIO:
    """TODO: port isi class VoiceIO dari agent/voice/voice_io.py apa adanya,
    kecuali bagian fusion (lihat catatan di atas)."""

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript

    def start(self) -> None:
        raise NotImplementedError("TODO: port dari agent/voice/voice_io.py")

    def stop(self) -> None:
        raise NotImplementedError("TODO: port dari agent/voice/voice_io.py")
