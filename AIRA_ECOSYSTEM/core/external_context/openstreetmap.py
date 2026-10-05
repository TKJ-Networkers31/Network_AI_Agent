"""
core/external_context/openstreetmap.py — OpenStreetMap provider untuk External Context Layer.

Sumber data (semua gratis, tanpa API key):
    Nominatim  -> search / lookup / reverse geocode
    Overpass   -> tempat terdekat (rumah sakit, SPBU, ATM, dst)
    OSRM       -> rute (driving / walking / bicycling)

Kebijakan layanan publik: wajib User-Agent yang mengidentifikasi aplikasi,
Nominatim maks 1 request/detik (dijaga di sini), hasil di-cache 10 menit.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from typing import Any, Callable, Optional

import requests

from core.external_context.constants import (
    CAPABILITY_CONTEXT,
    CAPABILITY_LOOKUP,
    CAPABILITY_NEARBY,
    CAPABILITY_ROUTE,
    CAPABILITY_SEARCH,
    DEFAULT_NEARBY_RADIUS_METERS,
    DEFAULT_ROUTE_MODE,
    ERROR_INVALID_REQUEST,
    ERROR_NO_RESULTS,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_RATE_LIMITED,
    ERROR_TIMEOUT,
)
from core.external_context.models import (
    ExternalContextError,
    NormalizedPlace,
    NormalizedRoute,
    ProviderCapabilities,
    ProviderIdentity,
    QueryResult,
    RouteSegment,
)
from core.external_context.provider import ExternalContextProvider

logger = logging.getLogger("aira.external_context.osm")

PROVIDER_NAME = "openstreetmap"

NOMINATIM = "https://nominatim.openstreetmap.org"
OVERPASS = "https://overpass-api.de/api/interpreter"
ROUTERS = {
    "driving": "https://router.project-osrm.org/route/v1/driving",
    "walking": "https://routing.openstreetmap.de/routed-foot/route/v1/driving",
    "bicycling": "https://routing.openstreetmap.de/routed-bike/route/v1/driving",
}

# WAJIB diganti dengan kontak kamu - Nominatim memblokir User-Agent generik.
USER_AGENT = "AIRA-OS/1.0 (personal assistant; contact: EMAILKAMU@example.com)"

CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 200

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_OSM_ID_RE = re.compile(r"^[NWR]\d+$")

# kata kunci -> filter Overpass. Urutan penting: yang lebih spesifik di atas.
TAG_MAP = [
    (("rumah sakit", "hospital", "rsud", "rs "), '["amenity"="hospital"]'),
    (("puskesmas", "klinik", "clinic"), '["amenity"~"clinic|doctors"]'),
    (("apotek", "pharmacy"), '["amenity"="pharmacy"]'),
    (("spbu", "pom bensin", "pertamina", "bensin"), '["amenity"="fuel"]'),
    (("atm",), '["amenity"="atm"]'),
    (("bank",), '["amenity"="bank"]'),
    (("kafe", "cafe", "kopi"), '["amenity"="cafe"]'),
    (("restoran", "rumah makan", "warung", "makan"), '["amenity"~"restaurant|fast_food"]'),
    (("masjid",), '["amenity"="place_of_worship"]["religion"="muslim"]'),
    (("minimarket", "indomaret", "alfamart"), '["shop"="convenience"]'),
    (("polisi",), '["amenity"="police"]'),
    (("parkir",), '["amenity"="parking"]'),
    (("sekolah",), '["amenity"="school"]'),
]

_DIRECTION = {
    "left": "kiri", "right": "kanan",
    "slight left": "serong kiri", "slight right": "serong kanan",
    "sharp left": "tajam ke kiri", "sharp right": "tajam ke kanan",
    "straight": "lurus", "uturn": "putar balik",
}

Fetcher = Callable[[str, Optional[dict], Optional[dict]], Any]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _step_text(step: dict) -> str:
    maneuver = step.get("maneuver") or {}
    kind = maneuver.get("type", "")
    modifier = _DIRECTION.get(maneuver.get("modifier", ""), maneuver.get("modifier", ""))
    road = step.get("name") or ""
    onto = f" ke {road}" if road else ""

    if kind == "depart":
        return "Mulai" + (f" di {road}" if road else "")
    if kind == "arrive":
        return "Tiba di tujuan"
    if kind in ("roundabout", "rotary"):
        return "Masuk bundaran" + (f", keluar{onto}" if road else "")
    if kind in ("turn", "end of road", "fork", "on ramp", "off ramp"):
        return f"Belok {modifier}{onto}".strip()

    return f"Lanjut {modifier}{onto}".strip()


class OpenStreetMapProvider(ExternalContextProvider):
    """Konstruksi tidak pernah raise. fetcher bisa disuntik (test tanpa jaringan)."""

    def __init__(self, fetcher: Optional[Fetcher] = None):
        self._fetch: Fetcher = fetcher or self._default_fetch
        self._rate_lock = threading.Lock()
        self._last_nominatim = 0.0
        self._cache: dict = {}

    # ------------------------------------------------------------ identity

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name=PROVIDER_NAME, display_name="OpenStreetMap", version="1.0")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capabilities=(
            CAPABILITY_SEARCH, CAPABILITY_LOOKUP, CAPABILITY_NEARBY,
            CAPABILITY_ROUTE, CAPABILITY_CONTEXT,
        ))

    def is_available(self) -> bool:
        return True  # tidak butuh API key

    # ---------------------------------------------------------------- HTTP

    def _default_fetch(self, url: str, params: Optional[dict] = None, post: Optional[dict] = None):
        if url.startswith(NOMINATIM):  # kebijakan Nominatim: maks 1 request/detik
            with self._rate_lock:
                wait = 1.1 - (time.time() - self._last_nominatim)
                if wait > 0:
                    time.sleep(wait)
                self._last_nominatim = time.time()

        headers = {"User-Agent": USER_AGENT, "Accept-Language": "id"}

        if post is not None:
            response = requests.post(url, data=post, headers=headers, timeout=25)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=10)

        response.raise_for_status()
        return response.json()

    def _call(
        self, url: str, params: Optional[dict] = None, post: Optional[dict] = None,
        ttl: int = CACHE_TTL_SECONDS,
    ) -> "tuple[Any, Optional[ExternalContextError]]":
        key = (url, tuple(sorted((params or {}).items())), tuple(sorted((post or {}).items())))
        hit = self._cache.get(key)

        if hit and hit[0] > time.time():
            return hit[1], None

        try:
            data = self._fetch(url, params, post)
        except requests.exceptions.Timeout as exc:
            return None, ExternalContextError(
                code=ERROR_TIMEOUT, message=f"OpenStreetMap timeout: {exc}",
                provider=PROVIDER_NAME, retryable=True,
            )
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            code = ERROR_RATE_LIMITED if status == 429 else ERROR_PROVIDER_UNAVAILABLE
            return None, ExternalContextError(
                code=code, message=f"OpenStreetMap membalas HTTP {status}.",
                provider=PROVIDER_NAME, retryable=True,
            )
        except Exception as exc:
            return None, ExternalContextError(
                code=ERROR_PROVIDER_UNAVAILABLE,
                message=f"Gagal menghubungi OpenStreetMap ({type(exc).__name__}): {exc}",
                provider=PROVIDER_NAME, retryable=True,
            )

        if len(self._cache) >= CACHE_MAX_ENTRIES:
            self._cache.clear()

        self._cache[key] = (time.time() + ttl, data)

        return data, None

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _fail(capability: str, code: str, message: str) -> QueryResult:
        return QueryResult.fail(PROVIDER_NAME, capability, ExternalContextError(
            code=code, message=message, provider=PROVIDER_NAME, capability=capability,
        ))

    @staticmethod
    def _filters_for(keyword: Optional[str]) -> Optional[str]:
        text = f"{(keyword or '').lower().strip()} "

        for words, overpass_filter in TAG_MAP:
            if any(word in text for word in words):
                return overpass_filter

        return None

    def _geocode(self, text: str) -> "tuple[Optional[tuple[float, float]], Optional[ExternalContextError]]":
        """'lat,lon' atau nama tempat -> ((lat, lon), None) atau (None, error)."""
        match = _LATLON_RE.match(text or "")

        if match:
            return (float(match[1]), float(match[2])), None

        data, error = self._call(f"{NOMINATIM}/search", {"q": text, "format": "jsonv2", "limit": 1})

        if error:
            return None, error

        if not data:
            return None, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"Tempat '{text}' tidak ditemukan.", provider=PROVIDER_NAME,
            )

        return (float(data[0]["lat"]), float(data[0]["lon"])), None

    @staticmethod
    def _place_from_nominatim(item: dict) -> NormalizedPlace:
        display = item.get("display_name") or ""

        return NormalizedPlace(
            id=f"{str(item.get('osm_type', 'n'))[:1].upper()}{item.get('osm_id', '')}",
            name=item.get("name") or display.split(",")[0] or "Tempat tanpa nama",
            address=display or None,
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            metadata={
                k: v for k, v in {"category": item.get("category"), "type": item.get("type")}.items() if v
            },
        )

    # ------------------------------------------------------------- search

    def _search(
        self, query: str, location: Optional[str] = None, radius: Optional[int] = None, **kwargs,
    ) -> QueryResult:
        text = (query or "").strip()

        if not text:
            return self._fail(CAPABILITY_SEARCH, ERROR_INVALID_REQUEST, "query tidak boleh kosong.")

        lat = lon = None
        match = _LATLON_RE.match(location or "")

        if match:
            lat, lon = float(match[1]), float(match[2])

        # "rumah sakit terdekat" dst: Overpass jauh lebih relevan daripada Nominatim.
        if lat is not None and self._filters_for(text):
            return self._nearby(lat, lon, radius=radius or DEFAULT_NEARBY_RADIUS_METERS, keyword=text)

        params: dict[str, Any] = {"q": text, "format": "jsonv2", "limit": 8}

        if lat is not None:
            delta = 0.25  # bias (bukan batas keras) ke sekitar user
            params["viewbox"] = f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}"

        data, error = self._call(f"{NOMINATIM}/search", params)

        if error:
            error.capability = CAPABILITY_SEARCH
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, error)

        places = [self._place_from_nominatim(item) for item in (data or [])]

        if lat is not None:
            for place in places:
                place.distance_meters = _haversine_m(lat, lon, place.latitude, place.longitude)
            places.sort(key=lambda p: p.distance_meters)

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_SEARCH, places=places, metadata={"query": text})

    # ------------------------------------------------------------- nearby

    def _nearby(
        self, latitude: float, longitude: float,
        radius: int = DEFAULT_NEARBY_RADIUS_METERS, keyword: Optional[str] = None, **kwargs,
    ) -> QueryResult:
        if latitude is None or longitude is None:
            return self._fail(CAPABILITY_NEARBY, ERROR_INVALID_REQUEST, "latitude dan longitude wajib diisi.")

        overpass_filter = self._filters_for(keyword)

        if overpass_filter is None:
            if keyword:  # kategori tak dikenal -> cari teks bebas di sekitar titik
                return self._search(keyword, location=f"{latitude},{longitude}")
            return self._fail(
                CAPABILITY_NEARBY, ERROR_INVALID_REQUEST,
                "OpenStreetMap butuh keyword kategori (mis. 'rumah sakit', 'spbu').",
            )

        query = (
            f"[out:json][timeout:20];"
            f"nwr{overpass_filter}(around:{int(radius)},{latitude},{longitude});"
            f"out center tags 60;"
        )

        data, error = self._call(OVERPASS, post={"data": query})

        if error:
            error.capability = CAPABILITY_NEARBY
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, error)

        places: list[NormalizedPlace] = []

        for element in (data or {}).get("elements", []):
            tags = element.get("tags") or {}

            if not tags.get("name"):
                continue

            center = element.get("center") or {}
            plat = element.get("lat") if element.get("lat") is not None else center.get("lat")
            plon = element.get("lon") if element.get("lon") is not None else center.get("lon")

            if plat is None or plon is None:
                continue

            street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
            address = ", ".join(
                x for x in (street, tags.get("addr:city") or tags.get("addr:suburb")) if x
            ) or None

            places.append(NormalizedPlace(
                id=f"{element['type'][:1].upper()}{element['id']}",
                name=tags["name"],
                address=address,
                latitude=plat,
                longitude=plon,
                distance_meters=_haversine_m(latitude, longitude, plat, plon),
                metadata={k: v for k, v in {
                    "phone": tags.get("phone") or tags.get("contact:phone"),
                    "opening_hours": tags.get("opening_hours"),
                    "website": tags.get("website") or tags.get("contact:website"),
                    "emergency": tags.get("emergency"),
                }.items() if v},
            ))

        places.sort(key=lambda p: p.distance_meters)

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_NEARBY, places=places[:20],
            metadata={"latitude": latitude, "longitude": longitude, "radius": radius},
        )

    # ------------------------------------------------------------- lookup

    def _lookup(self, place_id: str, **kwargs) -> QueryResult:
        pid = (place_id or "").strip().upper()

        if not _OSM_ID_RE.match(pid):
            return self._fail(
                CAPABILITY_LOOKUP, ERROR_INVALID_REQUEST, "place_id harus berformat N123 / W123 / R123.",
            )

        data, error = self._call(f"{NOMINATIM}/lookup", {"osm_ids": pid, "format": "jsonv2"})

        if error:
            error.capability = CAPABILITY_LOOKUP
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, error)

        if not data:
            return self._fail(CAPABILITY_LOOKUP, ERROR_NO_RESULTS, f"place_id '{pid}' tidak ditemukan.")

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_LOOKUP, places=[self._place_from_nominatim(data[0])])

    # -------------------------------------------------------------- route

    def _route(self, origin: str, destination: str, mode: str = DEFAULT_ROUTE_MODE, **kwargs) -> QueryResult:
        origin, destination = (origin or "").strip(), (destination or "").strip()
        mode = (mode or DEFAULT_ROUTE_MODE).strip().lower()

        if not origin or not destination:
            return self._fail(CAPABILITY_ROUTE, ERROR_INVALID_REQUEST, "origin dan destination wajib diisi.")

        if mode not in ROUTERS:
            return self._fail(
                CAPABILITY_ROUTE, ERROR_INVALID_REQUEST,
                f"mode '{mode}' belum didukung OpenStreetMap. Pilihan: {sorted(ROUTERS)}.",
            )

        start, error = self._geocode(origin)
        end = None

        if error is None:
            end, error = self._geocode(destination)

        if error:
            error.capability = CAPABILITY_ROUTE
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        url = f"{ROUTERS[mode]}/{start[1]},{start[0]};{end[1]},{end[0]}"
        data, error = self._call(
            url, {"overview": "simplified", "geometries": "geojson", "steps": "true"}, ttl=300,
        )

        if error:
            error.capability = CAPABILITY_ROUTE
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        if not data or data.get("code") != "Ok" or not data.get("routes"):
            return self._fail(
                CAPABILITY_ROUTE, ERROR_NO_RESULTS, f"Tidak ada rute dari '{origin}' ke '{destination}'.",
            )

        route = data["routes"][0]
        leg = (route.get("legs") or [{}])[0]

        coords = (route.get("geometry") or {}).get("coordinates") or []
        stride = max(1, len(coords) // 150)  # jaga payload peta tetap kecil
        geometry = [[round(c[1], 5), round(c[0], 5)] for c in coords[::stride]]

        segments = [
            RouteSegment(
                instruction=_step_text(step),
                distance_meters=step.get("distance"),
                duration_seconds=step.get("duration"),
            )
            for step in (leg.get("steps") or [])
        ]

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_ROUTE, route=NormalizedRoute(
            origin=origin, destination=destination,
            distance_meters=route.get("distance"), duration_seconds=route.get("duration"),
            segments=segments,
            metadata={
                "mode": mode, "geometry": geometry,
                "origin_coords": list(start), "destination_coords": list(end),
            },
        ))

    # ------------------------------------------------------------ context

    def _context(self, latitude: float, longitude: float, **kwargs) -> QueryResult:
        if latitude is None or longitude is None:
            return self._fail(CAPABILITY_CONTEXT, ERROR_INVALID_REQUEST, "latitude dan longitude wajib diisi.")

        data, error = self._call(
            f"{NOMINATIM}/reverse", {"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 17},
        )

        if error:
            error.capability = CAPABILITY_CONTEXT
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, error)

        if not data or data.get("error"):
            return self._fail(
                CAPABILITY_CONTEXT, ERROR_NO_RESULTS, f"Tidak ada info untuk {latitude},{longitude}.",
            )

        place = self._place_from_nominatim(data)
        place.metadata["role"] = "reverse_geocode"

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_CONTEXT, places=[place],
            metadata={"latitude": latitude, "longitude": longitude},
        )