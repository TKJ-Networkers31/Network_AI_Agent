# AIRA_ECOSYSTEM/core/location/models.py

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class LocationContext:
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None

    source: str = "browser"
    permission: str = "granted"

    timestamp: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationContext":
        return cls(
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            accuracy=data.get("accuracy"),
            altitude=data.get("altitude"),
            heading=data.get("heading"),
            speed=data.get("speed"),
            source=data.get("source", "browser"),
            permission=data.get("permission", "granted"),
            timestamp=data.get("timestamp"),
        )