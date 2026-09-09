"""
core/scheduler.py — scheduled/background task untuk AIRA (stub).

Di repo lama belum ada scheduler eksplisit, hanya disebut di komentar
agent/memory_store/long_term.py::build_context_snippet ("kejadian dari
scheduler jika aktif"). File ini adalah tempat resmi untuk fitur itu:
mis. polling resource MikroTik berkala lewat AKANE, lalu log_event() ke
core/memory.py kalau ada anomali (CPU > threshold, dsb).

Belum diimplementasikan - skeleton dulu sesuai keputusan "skeleton semua
module" sebelum isi logic per bagian.
"""

import logging

logger = logging.getLogger("aira.scheduler")


class Scheduler:

    def __init__(self):
        self._jobs: list[dict] = []

    def register(self, name: str, interval_seconds: int, func) -> None:
        """Daftarkan job berkala. TODO: implementasi loop (threading/asyncio)."""
        self._jobs.append({"name": name, "interval": interval_seconds, "func": func})
        logger.info("SCHEDULER | job terdaftar: %s (setiap %ss)", name, interval_seconds)

    def start(self) -> None:
        raise NotImplementedError("TODO: jalankan semua job terdaftar di background thread/asyncio task")

    def stop(self) -> None:
        raise NotImplementedError("TODO: hentikan semua job berjalan")
