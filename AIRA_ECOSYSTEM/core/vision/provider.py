"""
core/vision/provider.py — batas Vision provider (Sprint 2.7 / Wave 2 /
Worker 3).

Modul ini TIDAK PERNAH menganalisis gambar sendiri. Ia mendefinisikan
interface yang akan diimplementasikan provider asli nanti, plus SATU
provider yang dikirim di sprint ini: yang selalu, secara jujur, melaporkan
dirinya tidak tersedia. "Do not invent image analysis" ditegakkan secara
struktural - tidak ada jalur kode di paket ini yang menghasilkan
VisionResult dengan status=AVAILABLE.
"""

from __future__ import annotations

import threading
from typing import Optional, Protocol, runtime_checkable

from core.vision.models import ImageMetadata, VisionResult, VisionStatus


@runtime_checkable
class VisionProvider(Protocol):
    """Kontrak duck-typed yang diimplementasikan provider asli nanti.
    `reference` adalah bentuk dict yang dikembalikan
    core.attachments.engine.AttachmentEngine.get_content_reference() -
    path/URL, tidak pernah raw bytes."""

    def analyze(self, reference: Optional[dict], metadata: ImageMetadata) -> VisionResult:
        ...


class UnavailableVisionProvider:
    """Provider default sprint ini. Selalu mengembalikan UNAVAILABLE -
    sesuai persyaratan brief "If a vision provider is unavailable, return
    an explicit unavailable state", tanpa pengecualian."""

    name = "none"

    def analyze(self, reference: Optional[dict], metadata: ImageMetadata) -> VisionResult:
        return VisionResult(
            status=VisionStatus.UNAVAILABLE.value,
            provider=self.name,
            reason="Tidak ada vision provider yang terkonfigurasi untuk Sprint 2.7 Wave 2 W3.",
        )


_provider_singleton: Optional[VisionProvider] = None
_provider_lock = threading.Lock()


def get_vision_provider() -> VisionProvider:
    """Singleton accessor (Dependency Injection default), pola sama dengan
    core.attachments.store.get_attachment_store(). Bisa diganti di test /
    oleh siapa pun yang memasang provider asli nanti."""
    global _provider_singleton

    if _provider_singleton is None:
        with _provider_lock:
            if _provider_singleton is None:
                _provider_singleton = UnavailableVisionProvider()

    return _provider_singleton