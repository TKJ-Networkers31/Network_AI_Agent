# AIRA_ECOSYSTEM/core/location/service.py

import logging
import math
from typing import Optional

from .models import LocationContext

logger = logging.getLogger("aira.location")


class LocationService:

    def __init__(self):
        self._locations: dict[str, LocationContext] = {}

    def update(
        self,
        session_id: str,
        location: LocationContext,
    ) -> LocationContext:

        self._locations[session_id] = location

        logger.info(
            "LOCATION | session=%s lat=%.6f lon=%.6f accuracy=%s",
            session_id,
            location.latitude,
            location.longitude,
            location.accuracy,
        )

        return location

    def get(self, session_id: str) -> Optional[LocationContext]:
        return self._locations.get(session_id)

    def clear(self, session_id: str) -> None:
        self._locations.pop(session_id, None)

    def has_location(self, session_id: str) -> bool:
        return session_id in self._locations

    def distance_km(
        self,
        session_id: str,
        latitude: float,
        longitude: float,
    ) -> Optional[float]:

        location = self.get(session_id)

        if not location:
            return None

        return self._haversine(
            location.latitude,
            location.longitude,
            latitude,
            longitude,
        )

    @staticmethod
    def _haversine(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:

        radius = 6371.0

        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)

        dlat = lat2 - lat1
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return radius * c


location_service = LocationService()