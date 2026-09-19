"""
core/location/models.py — bentuk data lokasi AIRA.

Dua peran lokasi:
  host   -> tempat AIRA di-hosting (mesin yang menjalankan uvicorn)
  access -> tempat user mengakses AIRA (perangkat/browser yang membuka PWA)
"""

from dataclasses import asdict, dataclass
from typing import Optional

ROLE_HOST = "host"
ROLE_ACCESS = "access"

SOURCE_MANUAL = "manual"     # diisi user lewat halaman Settings
SOURCE_BROWSER = "browser"   # GPS/lokasi browser (akurat, butuh izin + https/localhost)
SOURCE_IP = "ip"             # perkiraan dari IP publik (kasar, bisa meleset kota)
SOURCE_NETWORK = "network"   # klien di jaringan lokal/loopback -> sama dengan hosting


def _num(value) -> Optional[float]:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def compose_label(city, region, country) -> Optional[str]:
    parts: list = []
    for part in (city, region, country):
        if part and part not in parts:
            parts.append(part)
    return ", ".join(parts) or None


@dataclass
class LocationContext:
    role: str = ROLE_ACCESS
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    label: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None

    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None

    source: str = SOURCE_BROWSER
    permission: str = "granted"
    ip: Optional[str] = None
    same_as_host: bool = False
    timestamp: Optional[float] = None

    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def display_name(self) -> str:
        if self.label:
            return self.label
        composed = compose_label(self.city, self.region, self.country)
        if composed:
            return composed
        if self.has_coordinates():
            return f"{self.latitude:.2f}, {self.longitude:.2f}"
        return "tidak diketahui"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["name"] = self.display_name()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "LocationContext":
        return cls(
            role=data.get("role", ROLE_ACCESS),
            latitude=_num(data.get("latitude")),
            longitude=_num(data.get("longitude")),
            label=data.get("label"),
            city=data.get("city"),
            region=data.get("region"),
            country=data.get("country"),
            timezone=data.get("timezone"),
            accuracy=_num(data.get("accuracy")),
            altitude=_num(data.get("altitude")),
            heading=_num(data.get("heading")),
            speed=_num(data.get("speed")),
            source=data.get("source", SOURCE_BROWSER),
            permission=data.get("permission", "granted"),
            ip=data.get("ip"),
            same_as_host=bool(data.get("same_as_host", False)),
            timestamp=_num(data.get("timestamp")),
        )