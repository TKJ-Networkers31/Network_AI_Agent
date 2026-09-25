"""
core/vision/context.py — visual context packet untuk Image & Visual Input
(Sprint 2.7 / Wave 2 / Worker 3).

Mengikuti core/attachments/context.py persis: menghasilkan dict polos yang
berbentuk untuk core.context.models.ContextSection (`data=` saja, kecuali
caller secara sadar memilih `text=`). Ini BUKAN Context Builder kedua - ini
batas "metadata/reference, tidak pernah binary, tidak pernah analisis yang
dikarang" yang sama, diperluas mencakup dimensi gambar dan status vision
yang jujur.

Packet yang dibangun modul ini adalah yang "can later feed Vision" (sesuai
brief): deskripsi self-contained, JSON-safe dari satu attachment gambar
yang bisa dipakai provider vision asli (atau langkah orchestrator nanti)
tanpa menyentuh byte file lewat modul ini.
"""

from __future__ import annotations

from typing import Any, Optional

from core.attachments.context import attachment_to_context_dict
from core.attachments.models import Attachment
from core.vision.models import ImageMetadata, VisionResult


def image_metadata_from_attachment(attachment: Attachment) -> ImageMetadata:
    """Attachment (+ key 'image' pada metadata bag-nya, diisi
    core.vision.engine.ImageVisionEngine saat pembuatan) -> ImageMetadata.
    Tidak pernah menyentuh file itu sendiri - hanya membentuk ulang apa
    yang sudah tersimpan."""
    image_meta = attachment.metadata.get("image") if isinstance(attachment.metadata, dict) else None
    image_meta = image_meta if isinstance(image_meta, dict) else {}

    return ImageMetadata(
        attachment_id=attachment.id,
        storage_reference=attachment.storage_reference,
        name=attachment.name,
        mime_type=attachment.mime_type,
        size=attachment.size,
        width=image_meta.get("width"),
        height=image_meta.get("height"),
        is_screenshot=bool(attachment.metadata.get("capture_type") == "screenshot"),
    )


def visual_placeholder_text(metadata: ImageMetadata, vision: VisionResult) -> str:
    """Satu baris, aman dimasukkan ke `text` ContextSection JIKA caller
    memilih include_text - tidak pernah mendeskripsikan isi gambar (tidak
    ada yang dideskripsikan), hanya fakta + status vision yang jujur."""
    dims = f"{metadata.width}x{metadata.height}" if metadata.has_dimensions else "dimensi tidak diketahui"
    kind = "screenshot" if metadata.is_screenshot else "gambar"

    return f"- {metadata.name} ({metadata.mime_type}, {dims}, {kind}) - vision: {vision.status}"


def build_visual_context_packet(
    attachment: Attachment,
    vision: Optional[VisionResult] = None,
    *,
    include_text: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Payload siap-pakai untuk ContextSection(**packet), begitu caller
    memutuskan menyambungkannya ke core.context.builder.ContextBuilder
    (pola "disambungkan oleh caller, bukan oleh modul ini" yang sama
    seperti core.attachments.context.attachments_context_section).

    Mengembalikan None kalau `attachment` sudah dihapus atau bukan gambar -
    caller bisa melewati pembuatan section sama sekali.
    """
    if attachment is None or attachment.is_deleted:
        return None

    if not (attachment.mime_type or "").startswith("image/"):
        return None

    metadata = image_metadata_from_attachment(attachment)
    vision = vision or VisionResult()  # default UNAVAILABLE - tidak pernah mengarang hasil

    base = attachment_to_context_dict(attachment)

    payload: dict[str, Any] = {
        "data": {
            "attachment": base,
            "image": metadata.to_dict(),
            "vision": vision.to_dict(),
        },
    }

    if include_text:
        payload["text"] = visual_placeholder_text(metadata, vision)

    return payload