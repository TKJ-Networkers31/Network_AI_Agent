"""
core/vision/ — Image & Visual Input (Sprint 2.7 / Wave 2 / Worker 3).

    ImageMetadata  = fakta file gambar (mime, dimensi, size, filename,
                     referensi attachment) - tidak interpretif.
    VisionResult   = hasil eksplisit percobaan analisis visual - selalu
                     UNAVAILABLE selama tidak ada provider asli terpasang.
    ImageVisionEngine = orkestrasi upload gambar/screenshot di atas
                     core.attachments (TIDAK membuat sistem attachment
                     kedua) + kontrak visual context packet.

Public API:
    from core.vision import (
        ImageMetadata, VisionResult, VisionStatus,
        VisionProvider, UnavailableVisionProvider, get_vision_provider,
        ImageVisionEngine, get_image_vision_engine,
        image_metadata_from_attachment, build_visual_context_packet,
        extract_image_dimensions,
    )
"""

from core.vision.models import ImageMetadata, VisionResult, VisionStatus
from core.vision.metadata import extract_image_dimensions
from core.vision.provider import (
    VisionProvider,
    UnavailableVisionProvider,
    get_vision_provider,
)
from core.vision.context import (
    image_metadata_from_attachment,
    build_visual_context_packet,
    visual_placeholder_text,
)
from core.vision.engine import ImageVisionEngine, get_image_vision_engine

__all__ = [
    "ImageMetadata", "VisionResult", "VisionStatus",
    "extract_image_dimensions",
    "VisionProvider", "UnavailableVisionProvider", "get_vision_provider",
    "image_metadata_from_attachment", "build_visual_context_packet",
    "visual_placeholder_text",
    "ImageVisionEngine", "get_image_vision_engine",
]