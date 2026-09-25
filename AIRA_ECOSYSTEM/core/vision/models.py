"""
core/vision/models.py — Image & Visual Input data contracts
(Sprint 2.7 / Wave 2 / Worker 3).

    ImageMetadata = mime + dimensi + size + filename + referensi attachment
                    (fakta yang diekstrak dari file itu sendiri - BUKAN
                    pendapat tentang apa isi gambarnya).
    VisionStatus  = lifecycle dari SATU percobaan analisis visual - terpisah
                    dari apakah file/metadatanya ada.
    VisionResult  = hasil eksplisit dan jujur dari meminta vision provider
                    melihat gambar. Selama tidak ada provider asli
                    terpasang, ini SELALU status=UNAVAILABLE - modul ini
                    tidak pernah mengarang caption/deskripsi.

Pola sama dengan core/attachments/models.py: dataclass murni, tanpa I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class VisionStatus(str, Enum):
    """Hasil percobaan analisis visual. UNAVAILABLE adalah satu-satunya
    status yang pernah diproduksi modul ini (atau provider default-nya) -
    AVAILABLE/ERROR ada agar provider ASLI yang dipasang nanti punya
    tempat jujur untuk melaporkan sukses/gagal, tanpa mengubah kontrak."""

    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    ERROR = "error"

    @classmethod
    def coerce(cls, value: Any) -> "VisionStatus":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        return cls.UNAVAILABLE


@dataclass
class ImageMetadata:
    """Fakta tentang SATU file gambar - tidak ada yang interpretif.
    width/height bernilai None kalau tidak bisa diparse dari header file
    (variant tak didukung, file korup, atau format seperti SVG tanpa
    ukuran raster tetap) - dilaporkan apa adanya, tidak pernah ditebak."""

    attachment_id: Optional[str] = None
    storage_reference: Optional[str] = None
    name: str = "untitled"
    mime_type: str = "application/octet-stream"
    size: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    is_screenshot: bool = False

    @property
    def has_dimensions(self) -> bool:
        return self.width is not None and self.height is not None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ImageMetadata":
        data = data if isinstance(data, dict) else {}
        known = {
            "attachment_id", "storage_reference", "name", "mime_type",
            "size", "width", "height", "is_screenshot",
        }
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


@dataclass
class VisionResult:
    """Hasil eksplisit, tidak dikarang, dari satu percobaan analisis
    visual. `analysis` selalu None kecuali status == AVAILABLE - tidak ada
    jalur di paket ini yang mengisinya tanpa provider asli melakukannya."""

    status: str = VisionStatus.UNAVAILABLE.value
    provider: Optional[str] = None
    reason: Optional[str] = None
    analysis: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.status = VisionStatus.coerce(self.status).value
        if self.status != VisionStatus.AVAILABLE.value:
            self.analysis = None

    @property
    def is_available(self) -> bool:
        return self.status == VisionStatus.AVAILABLE.value

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "provider": self.provider,
            "reason": self.reason,
            "analysis": self.analysis,
        }