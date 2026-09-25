"""
core/vision/engine.py — ImageVisionEngine (Sprint 2.7 / Wave 2 / Worker 3).

    upload (gambar atau screenshot)
        -> reuse core.attachments.engine.AttachmentEngine.create_from_upload
           (TIDAK ADA sistem attachment/storage kedua - validator sama,
           sandbox Workspace sama, attachments.db sama)
        -> ekstrak lebar/tinggi dari byte header
           (core.vision.metadata.extract_image_dimensions - tidak pernah
           men-decode piksel)
        -> selipkan itu + capture_type ke bag Attachment.metadata yang
           SUDAH ADA
        -> AttachmentResult (kontrak identik dengan yang sudah didapat
           caller dari core.attachments)

    get_visual_context(attachment_id)
        -> lookup attachment (ownership-checked, sama seperti
           core.attachments.engine.AttachmentEngine.get)
        -> minta VisionProvider yang terkonfigurasi menganalisis (default:
           selalu UNAVAILABLE - core.vision.provider.UnavailableVisionProvider)
        -> core.vision.context.build_visual_context_packet(...)

Ini SATU-SATUNYA modul baru untuk Wave 2 / W3. Tidak menyentuh file
core/attachments/*, tidak menambah AttachmentSource baru, dan tidak
menambah database baru - "screenshot" sepenuhnya dibawa lewat
metadata["capture_type"] pada record Attachment yang sudah ada.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from core.attachments.constants import EXTENSION_TO_MIME
from core.attachments.engine import AttachmentEngine, get_attachment_engine
from core.attachments.models import AttachmentResult
from core.vision.context import build_visual_context_packet, image_metadata_from_attachment
from core.vision.metadata import extract_image_dimensions
from core.vision.models import ImageMetadata, VisionResult, VisionStatus
from core.vision.provider import VisionProvider, get_vision_provider

logger = logging.getLogger("aira.vision.engine")

_IMAGE_MIME_PREFIX = "image/"


def _infer_mime(name: str, mime_type: Optional[str]) -> str:
    if isinstance(mime_type, str) and mime_type.strip():
        return mime_type.strip().lower()

    extension = Path(name).suffix.lower()
    return EXTENSION_TO_MIME.get(extension, "application/octet-stream")


class ImageVisionEngine:
    """Dependency Injection: `attachment_engine` dan `vision_provider`
    bisa diganti (test menyuntik AttachmentEngine sementara + fake
    VisionProvider), pola sama seperti AttachmentEngine sendiri."""

    def __init__(
        self,
        attachment_engine: Optional[AttachmentEngine] = None,
        vision_provider: Optional[VisionProvider] = None,
    ):
        self._attachment_engine = attachment_engine or get_attachment_engine()
        self._vision_provider = vision_provider or get_vision_provider()

    # ============================================================ CREATE

    def create_image_attachment(
        self,
        *,
        content: bytes,
        name: str,
        session_id: str,
        message_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        is_screenshot: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AttachmentResult:
        """Upload gambar atau screenshot. Menolak mime bukan gambar
        SEBELUM menyentuh storage (batas milik engine ini sendiri - kalau
        tidak, AttachmentEngine/validator di bawahnya akan menerima PDF
        dengan senang hati)."""
        if not isinstance(content, (bytes, bytearray)):
            return AttachmentResult(False, errors=["content harus berupa bytes."])

        resolved_mime = _infer_mime(name, mime_type)

        if not resolved_mime.startswith(_IMAGE_MIME_PREFIX):
            return AttachmentResult(
                False,
                errors=[f"'{resolved_mime}' bukan tipe gambar - Image & Visual Input hanya menerima image/*."],
            )

        width, height = extract_image_dimensions(bytes(content), resolved_mime)

        merged_metadata: dict[str, Any] = dict(metadata or {})
        merged_metadata["image"] = {"width": width, "height": height}

        if is_screenshot:
            merged_metadata["capture_type"] = "screenshot"

        result = self._attachment_engine.create_from_upload(
            content=content, name=name, session_id=session_id,
            mime_type=resolved_mime, message_id=message_id, metadata=merged_metadata,
        )

        if result.success:
            logger.info(
                "IMAGE ATTACHMENT CREATED | id=%s dims=%sx%s screenshot=%s",
                result.attachment.id, width, height, is_screenshot,
            )

        return result

    # ============================================================== READ

    def get_image_metadata(
        self, attachment_id: str, *, session_id: Optional[str] = None,
    ) -> Optional[ImageMetadata]:
        attachment = self._attachment_engine.get(attachment_id, session_id=session_id)

        if attachment is None or not (attachment.mime_type or "").startswith(_IMAGE_MIME_PREFIX):
            return None

        return image_metadata_from_attachment(attachment)

    def get_visual_context(
        self,
        attachment_id: str,
        *,
        session_id: Optional[str] = None,
        invoke_provider: bool = True,
        include_text: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Membangun visual context packet untuk satu attachment gambar.
        Kalau invoke_provider True (default) ia meminta hasil dari
        VisionProvider yang terkonfigurasi - yang UNAVAILABLE kecuali
        provider asli sudah disuntikkan lewat konstruktor."""
        attachment = self._attachment_engine.get(attachment_id, session_id=session_id)

        if attachment is None or not (attachment.mime_type or "").startswith(_IMAGE_MIME_PREFIX):
            return None

        vision_result: Optional[VisionResult] = None

        if invoke_provider:
            metadata = image_metadata_from_attachment(attachment)
            reference = self._attachment_engine.get_content_reference(attachment_id, session_id=session_id)

            try:
                vision_result = self._vision_provider.analyze(reference, metadata)
            except Exception as exc:
                logger.warning(
                    "VISION | provider %s gagal (%s) - dilaporkan sebagai unavailable.",
                    getattr(self._vision_provider, "name", type(self._vision_provider).__name__),
                    type(exc).__name__,
                )
                vision_result = VisionResult(
                    status=VisionStatus.UNAVAILABLE.value,
                    provider=getattr(self._vision_provider, "name", None),
                    reason=f"Provider gagal ({type(exc).__name__}).",
                )

        return build_visual_context_packet(attachment, vision_result, include_text=include_text)


_engine_singleton: Optional[ImageVisionEngine] = None


def get_image_vision_engine() -> ImageVisionEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = ImageVisionEngine()
    return _engine_singleton