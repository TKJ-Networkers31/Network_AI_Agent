"""
core/location/ — lokasi HOSTING (tempat AIRA berjalan) dan lokasi AKSES
(tempat user membuka AIRA).

    from core.location import location_service, build_location_context
"""

from core.location.models import LocationContext, ROLE_ACCESS, ROLE_HOST
from core.location.service import LocationService, location_service


def build_location_context(session_id=None) -> str:
    """Blok teks untuk system prompt. Tidak pernah raise."""
    return location_service.build_prompt_block(session_id)


__all__ = [
    "LocationContext", "ROLE_ACCESS", "ROLE_HOST",
    "LocationService", "location_service", "build_location_context",
]