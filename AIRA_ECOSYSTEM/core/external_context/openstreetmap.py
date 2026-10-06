"""
core/external_context/openstreetmap.py — adapter OpenStreetMap untuk External
Context Layer (Sprint 2.7 / W7).

Nominatim (search/lookup/reverse), Overpass (nearby/kategori), OSRM (rute).

PERBAIKAN:
  1. Query dipecah jadi KATEGORI + NAMA INTI ("rumah sakit welas asih" ->
     amenity=hospital + nama ~ "welas.?asih"), jadi "RSU Welas Asih",
     "RS Al-Ihsan", dst tetap ketemu. Radius melebar bertahap.
  2. Pencarian Nominatim berlokasi dibatasi bounding box (bounded=1). Kalau
     kosong, hasil tanpa batas diurutkan menurut jarak dan yang terlalu jauh
     (mis. Pekanbaru) dibuang.
  3. Rute menyertakan geometry (titik polyline, di-downsample) untuk peta.
  4. Cache hasil Overpass 5 menit; tempat tanpa nama dibuang.
  5. Mirror Overpass: timeout pendek, anggaran waktu total, cooldown mirror gagal.

HTTP disuntik lewat `fetcher(url, params=None, post=None)` supaya test tidak
menyentuh jaringan.
"""

from __future__ import annotations

import functools
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

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
    VALID_ROUTE_MODES,
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

logger = logging.getLogger("aira.external_context.openstreetmap")

PROVIDER_NAME = "openstreetmap"
PROVIDER_DISPLAY_NAME = "OpenStreetMap"

NOMINATIM = "https://nominatim.openstreetmap.org"

OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
OVERPASS_CLIENT_TIMEOUT = 12
OVERPASS_SERVER_TIMEOUT = 10
OVERPASS_TOTAL_BUDGET = 30.0
OVERPASS_MIRROR_COOLDOWN = 60.0
OVERPASS_MAX_ELEMENTS = 30
NEARBY_MAX_RESULTS = 20
MAX_NEARBY_RADIUS_METERS = 15000
SEARCH_WIDE_RADIUS_METERS = 15000   # radius kedua untuk pencarian berdasarkan nama
FAR_RESULT_METERS = 50000           # di atas ini dianggap "jauh" (hasil tanpa batas)
ROUTE_MAX_POINTS = 150
MAX_ALTERNATIVES = 2
GEOCODE_CACHE_TTL_SECONDS = 3600
CACHE_TTL_SECONDS = 300
CACHE_MAX_ENTRIES = 64

DEFAULT_HTTP_TIMEOUT = 20

OSRM_SERVERS = {
    "driving": ("https://router.project-osrm.org", "driving"),
    "walking": ("https://routing.openstreetmap.de/routed-foot", "driving"),
    "bicycling": ("https://routing.openstreetmap.de/routed-bike", "driving"),
}
OSM_DIRECTIONS_ENGINE = {
    "driving": "fossgis_osrm_car",
    "walking": "fossgis_osrm_foot",
    "bicycling": "fossgis_osrm_bike",
}

DEFAULT_USER_AGENT = "AIRA-OS/1.0 (personal network assistant; external-context/openstreetmap)"

ENV_ENABLED = "OSM_ENABLED"
ENV_USER_AGENT = "OSM_USER_AGENT"
_FALSE_VALUES = {"0", "false", "off", "no"}

_MIRROR_DOWN_UNTIL: dict[str, float] = {}


# ------------------------------------------------------------------ config

@dataclass(frozen=True)
class OpenStreetMapConfig:
    enabled: bool = True
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def is_configured(self) -> bool:
        return self.enabled

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "is_configured": self.is_configured}


def load_openstreetmap_config(env: Optional[dict] = None) -> OpenStreetMapConfig:
    source = env if env is not None else os.environ

    enabled_raw = source.get(ENV_ENABLED)
    enabled = True if enabled_raw is None else str(enabled_raw).strip().lower() not in _FALSE_VALUES

    agent = source.get(ENV_USER_AGENT)
    agent = agent.strip() if isinstance(agent, str) and agent.strip() else DEFAULT_USER_AGENT

    return OpenStreetMapConfig(enabled=enabled, user_agent=agent)


# ------------------------------------------------------------------ HTTP

class OSMTimeout(Exception):
    """Timeout dari fetcher -> ERROR_TIMEOUT."""


Fetcher = Callable[..., Any]


def _default_fetch(
    url: str,
    params: Optional[dict] = None,
    post: Optional[dict] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Any:
    import requests

    headers = {"User-Agent": user_agent, "Accept": "application/json"}

    try:
        if post is not None:
            timeout = OVERPASS_CLIENT_TIMEOUT if url in OVERPASS_MIRRORS else DEFAULT_HTTP_TIMEOUT
            response = requests.post(url, data=post, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=DEFAULT_HTTP_TIMEOUT)

        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as exc:
        raise OSMTimeout(str(exc)) from exc


def _map_exception(exc: Exception) -> ExternalContextError:
    if isinstance(exc, OSMTimeout):
        return ExternalContextError(
            code=ERROR_TIMEOUT, message=f"Permintaan ke OpenStreetMap timeout: {exc}",
            provider=PROVIDER_NAME, retryable=True,
        )

    status = getattr(getattr(exc, "response", None), "status_code", None)

    if status == 429:
        return ExternalContextError(
            code=ERROR_RATE_LIMITED, message="OpenStreetMap membatasi request (HTTP 429).",
            provider=PROVIDER_NAME, retryable=True, details={"http_status": 429},
        )

    details = {"http_status": status} if status else {}

    return ExternalContextError(
        code=ERROR_PROVIDER_UNAVAILABLE,
        message=f"Gagal menghubungi OpenStreetMap ({type(exc).__name__}): {exc}",
        provider=PROVIDER_NAME, retryable=True, details=details,
    )


# ------------------------------------------------------------------ helper murni

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

_FILLER_WORDS = {
    "terdekat", "dekat", "sekitar", "sini", "di", "yang", "dan", "cari", "carikan",
    "nearest", "near", "nearby", "closest", "the", "a", "me", "around",
}

# alias kategori -> filter tag Overpass
_TAG_FILTERS: tuple[tuple[frozenset, str], ...] = (
    (frozenset({"rumah sakit", "rumah sakit umum", "rs", "rsud", "rsu", "rsia", "hospital"}),
     '["amenity"="hospital"]'),
    (frozenset({"klinik", "clinic", "dokter", "puskesmas"}), '["amenity"~"^(clinic|doctors)$"]'),
    (frozenset({"apotek", "apotik", "pharmacy"}), '["amenity"="pharmacy"]'),
    (frozenset({"spbu", "pom bensin", "pompa bensin", "bensin", "gas station", "fuel"}), '["amenity"="fuel"]'),
    (frozenset({"atm"}), '["amenity"="atm"]'),
    (frozenset({"bank"}), '["amenity"="bank"]'),
    (frozenset({"restoran", "restaurant", "rumah makan", "makan", "warung makan"}),
     '["amenity"~"^(restaurant|fast_food)$"]'),
    (frozenset({"kafe", "cafe", "kopi", "coffee", "coffee shop"}), '["amenity"="cafe"]'),
    (frozenset({"masjid", "mosque"}), '["amenity"="place_of_worship"]["religion"="muslim"]'),
    (frozenset({"gereja", "church"}), '["amenity"="place_of_worship"]["religion"="christian"]'),
    (frozenset({"polisi", "kantor polisi", "polsek", "polres", "police"}), '["amenity"="police"]'),
    (frozenset({"pemadam", "pemadam kebakaran", "damkar", "fire station"}), '["amenity"="fire_station"]'),
    (frozenset({"minimarket", "supermarket", "swalayan"}), '["shop"~"^(convenience|supermarket)$"]'),
    (frozenset({"parkir", "parking"}), '["amenity"="parking"]'),
    (frozenset({"hotel", "penginapan"}), '["tourism"~"^(hotel|guest_house|hostel)$"]'),
    (frozenset({"sekolah", "school"}), '["amenity"="school"]'),
    (frozenset({"toilet", "wc"}), '["amenity"="toilets"]'),
)

_NAME_KEYS = ("name", "alt_name", "official_name", "name:id")


def _to_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clean_keyword(keyword: Optional[str]) -> str:
    text = re.sub(r"[^\w\s\-]", " ", (keyword or "").lower())
    words = [w for w in text.split() if w not in _FILLER_WORDS]
    return " ".join(words)


def _split_category(query: Optional[str]) -> tuple[Optional[str], str, str]:
    """query -> (filter_tag | None, nama_inti, query_bersih).
    'rumah sakit welas asih' -> (hospital, 'welas asih', ...)
    'rumah sakit terdekat'   -> (hospital, '', 'rumah sakit')
    'gedung sate'            -> (None, 'gedung sate', 'gedung sate')"""
    cleaned = _clean_keyword(query)

    if not cleaned:
        return None, "", ""

    best: Optional[tuple[int, str, str]] = None

    for aliases, tag_filter in _TAG_FILTERS:
        for alias in aliases:
            if cleaned == alias:
                candidate = (len(alias), tag_filter, "")
            elif cleaned.startswith(alias + " "):
                candidate = (len(alias), tag_filter, cleaned[len(alias) + 1:].strip())
            else:
                continue

            if best is None or candidate[0] > best[0]:
                best = candidate

    if best is not None:
        return best[1], best[2], cleaned

    return None, cleaned, cleaned


def _name_regex(core: str) -> str:
    """'al ihsan' / 'al-ihsan' -> 'al.?ihsan' (cocok 'Al Ihsan', 'Al-Ihsan', 'AlIhsan')."""
    tokens = [t for t in re.split(r"[\s\-]+", core) if t]
    return ".?".join(tokens)


def _overpass_filters(keyword: Optional[str]) -> list[str]:
    tag_filter, core, cleaned = _split_category(keyword)

    if not cleaned:
        return ['["amenity"]["name"]']

    if tag_filter and not core:
        return [tag_filter]

    regex = _name_regex(core)

    if tag_filter:
        return [f'{tag_filter}["{key}"~"{regex}",i]' for key in _NAME_KEYS]

    return [f'["{key}"~"{regex}",i]' for key in _NAME_KEYS[:3]]


def _address_from_tags(tags: dict) -> Optional[str]:
    street = " ".join(p for p in (tags.get("addr:street"), tags.get("addr:housenumber")) if p)
    parts = [
        street,
        tags.get("addr:suburb") or tags.get("addr:village"),
        tags.get("addr:city") or tags.get("addr:town"),
    ]
    text = ", ".join(p for p in parts if p)
    return text or tags.get("addr:full") or None


def _osm_url(osm_type: Optional[str], osm_id: Any) -> Optional[str]:
    if osm_type in ("node", "way", "relation") and osm_id:
        return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return None


def _short_id(osm_type: Optional[str], osm_id: Any) -> str:
    if osm_type and osm_id:
        return f"{str(osm_type)[0].upper()}{osm_id}"
    return ""


def _downsample(points: list, limit: int) -> list:
    if limit < 2 or len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[int(round(i * step))] for i in range(limit)]


_MODIFIER_ID = {
    "left": "kiri", "right": "kanan",
    "slight left": "serong kiri", "slight right": "serong kanan",
    "sharp left": "tajam ke kiri", "sharp right": "tajam ke kanan",
    "straight": "lurus", "uturn": "putar balik",
}


def _step_instruction(step: dict) -> str:
    maneuver = step.get("maneuver") or {}
    kind = maneuver.get("type")
    modifier = maneuver.get("modifier")
    name = (step.get("name") or "").strip()
    road = f" ke {name}" if name else ""
    side = _MODIFIER_ID.get(modifier, modifier or "")

    if kind == "depart":
        return f"Mulai{road}"
    if kind == "arrive":
        return "Tiba di tujuan"
    if kind in ("roundabout", "rotary"):
        return f"Masuk bundaran{road}"
    if modifier == "uturn":
        return f"Putar balik{road}"
    if modifier == "straight" or kind == "continue":
        return f"Lurus{road}"
    if side:
        return f"Belok {side}{road}"

    return f"Lanjut{road}"

def _via(route: dict) -> str:
    """Ringkasan rute: dua nama jalan terpanjang pada rute itu."""
    legs = route.get("legs") or []
    steps = (legs[0].get("steps") if legs else None) or []
    named = [s for s in steps if (s.get("name") or "").strip()]
    biggest = sorted(named, key=lambda s: s.get("distance") or 0, reverse=True)[:2]

    names: list[str] = []
    for step in biggest:
        name = step["name"].strip()
        if name not in names:
            names.append(name)

    return ", ".join(names) or "rute tanpa nama"


# ------------------------------------------------------------------ provider

class OpenStreetMapProvider(ExternalContextProvider):

    def __init__(
        self,
        config: Optional[OpenStreetMapConfig] = None,
        fetcher: Optional[Fetcher] = None,
        nominatim_min_interval: float = 1.0,
    ):
        self._config = config if config is not None else load_openstreetmap_config()
        self._fetcher: Fetcher = fetcher or functools.partial(
            _default_fetch, user_agent=self._config.user_agent,
        )
        self._nominatim_min_interval = max(0.0, nominatim_min_interval)
        self._nominatim_lock = threading.Lock()
        self._nominatim_last = 0.0

        self._cache: dict[Any, tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------ identity

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name=PROVIDER_NAME, display_name=PROVIDER_DISPLAY_NAME, version="1.1")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capabilities=(
            CAPABILITY_SEARCH, CAPABILITY_LOOKUP, CAPABILITY_NEARBY,
            CAPABILITY_ROUTE, CAPABILITY_CONTEXT,
        ))

    def is_available(self) -> bool:
        return self._config.is_configured

    @property
    def config(self) -> OpenStreetMapConfig:
        return self._config

    # ------------------------------------------------------------ cache

    def _cache_get(self, key: Any) -> Optional[Any]:
        with self._cache_lock:
            item = self._cache.get(key)

            if item is None:
                return None

            if item[0] < time.monotonic():
                self._cache.pop(key, None)
                return None

            return item[1]

        def _cache_set(self, key: Any, value: Any, ttl: float = CACHE_TTL_SECONDS) -> None:
            with self._cache_lock:
                if len(self._cache) >= CACHE_MAX_ENTRIES:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = (time.monotonic() + ttl, value)

    # ------------------------------------------------------------ transport

    def _throttle_nominatim(self) -> None:
        if self._nominatim_min_interval <= 0:
            return

        with self._nominatim_lock:
            wait = self._nominatim_min_interval - (time.monotonic() - self._nominatim_last)
            if wait > 0:
                time.sleep(wait)
            self._nominatim_last = time.monotonic()

    def _call(self, url: str, params: dict) -> tuple[Optional[Any], Optional[ExternalContextError]]:
        if url.startswith(NOMINATIM):
            self._throttle_nominatim()

        try:
            data = self._fetcher(url, params, None)
        except Exception as exc:
            return None, _map_exception(exc)

        if data is None:
            return None, ExternalContextError(
                code=ERROR_PROVIDER_UNAVAILABLE, message="Respons OpenStreetMap kosong.",
                provider=PROVIDER_NAME, retryable=True,
            )

        return data, None

    def _call_overpass(self, query: str) -> tuple[Optional[dict], Optional[ExternalContextError]]:
        started = time.monotonic()
        last_error: Optional[ExternalContextError] = None

        mirrors = [m for m in OVERPASS_MIRRORS if _MIRROR_DOWN_UNTIL.get(m, 0.0) <= started]
        mirrors = mirrors or list(OVERPASS_MIRRORS)

        for mirror in mirrors:
            if last_error is not None and time.monotonic() - started >= OVERPASS_TOTAL_BUDGET:
                logger.warning("OVERPASS | anggaran waktu %.0fs habis.", OVERPASS_TOTAL_BUDGET)
                break

            try:
                data = self._fetcher(mirror, None, {"data": query})
            except Exception as exc:
                last_error = _map_exception(exc)
                _MIRROR_DOWN_UNTIL[mirror] = time.monotonic() + OVERPASS_MIRROR_COOLDOWN
                logger.warning("OVERPASS | mirror %s gagal: %s", mirror, last_error.message)
                continue

            if not isinstance(data, dict):
                last_error = ExternalContextError(
                    code=ERROR_PROVIDER_UNAVAILABLE, message="Respons Overpass bukan JSON object.",
                    provider=PROVIDER_NAME, retryable=True,
                )
                _MIRROR_DOWN_UNTIL[mirror] = time.monotonic() + OVERPASS_MIRROR_COOLDOWN
                continue

            remark = str(data.get("remark") or "")
            if "error" in remark.lower() and not data.get("elements"):
                last_error = ExternalContextError(
                    code=ERROR_TIMEOUT, message=f"Overpass melaporkan error: {remark[:160]}",
                    provider=PROVIDER_NAME, retryable=True,
                )
                _MIRROR_DOWN_UNTIL[mirror] = time.monotonic() + OVERPASS_MIRROR_COOLDOWN
                continue

            _MIRROR_DOWN_UNTIL.pop(mirror, None)
            return data, None

        return None, last_error or ExternalContextError(
            code=ERROR_PROVIDER_UNAVAILABLE, message="Semua mirror Overpass gagal.",
            provider=PROVIDER_NAME, retryable=True,
        )

    # ------------------------------------------------------------ normalisasi

    @staticmethod
    def _place_from_nominatim(item: dict) -> NormalizedPlace:
        osm_type = item.get("osm_type")
        osm_id = item.get("osm_id")
        place_id = _short_id(osm_type, osm_id) or str(item.get("place_id") or "")

        address = item.get("display_name")
        name = item.get("name") or (address.split(",")[0].strip() if address else "") or "Tempat tanpa nama"

        metadata = {
            k: v for k, v in {
                "category": item.get("category"),
                "type": item.get("type"),
                "osm_url": _osm_url(osm_type, osm_id),
            }.items() if v
        }

        return NormalizedPlace(
            id=place_id, name=str(name), address=address,
            latitude=_to_float(item.get("lat")), longitude=_to_float(item.get("lon")),
            metadata=metadata,
        )

    @staticmethod
    def _place_from_overpass(element: dict, ref_lat: float, ref_lon: float) -> Optional[NormalizedPlace]:
        tags = element.get("tags") or {}

        name = (
            tags.get("name") or tags.get("name:id") or tags.get("official_name")
            or tags.get("alt_name") or tags.get("brand") or tags.get("operator")
        )

        if not name:
            return None  # tempat tanpa nama tidak berguna untuk user

        lat, lon = element.get("lat"), element.get("lon")

        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")

        lat, lon = _to_float(lat), _to_float(lon)

        if lat is None or lon is None:
            return None

        osm_type = element.get("type", "node")
        osm_id = element.get("id")

        metadata = {
            k: v for k, v in {
                "amenity": tags.get("amenity") or tags.get("shop") or tags.get("tourism"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "opening_hours": tags.get("opening_hours"),
                "website": tags.get("website") or tags.get("contact:website"),
                "osm_url": _osm_url(osm_type, osm_id),
            }.items() if v
        }

        return NormalizedPlace(
            id=_short_id(osm_type, osm_id), name=str(name), address=_address_from_tags(tags),
            latitude=lat, longitude=lon,
            distance_meters=round(_haversine_m(ref_lat, ref_lon, lat, lon), 1),
            metadata=metadata,
        )

    # ------------------------------------------------------------ Overpass inti

    def _overpass_places(
        self, lat: float, lon: float, radius_m: int, filters: list[str],
    ) -> tuple[Optional[list[NormalizedPlace]], Optional[ExternalContextError]]:
        parts = "".join(f"nwr{f}(around:{radius_m},{lat},{lon});" for f in filters)
        query = f"[out:json][timeout:{OVERPASS_SERVER_TIMEOUT}];({parts});out center tags {OVERPASS_MAX_ELEMENTS};"

        cached = self._cache_get(("overpass", query))
        if cached is not None:
            return list(cached), None

        data, error = self._call_overpass(query)

        if error is not None:
            return None, error

        seen: set[str] = set()
        places: list[NormalizedPlace] = []

        for element in data.get("elements") or []:
            if not isinstance(element, dict):
                continue

            place = self._place_from_overpass(element, lat, lon)

            if place is None or place.id in seen:
                continue

            seen.add(place.id)
            places.append(place)

        places.sort(key=lambda p: p.distance_meters if p.distance_meters is not None else float("inf"))
        places = places[:NEARBY_MAX_RESULTS]

        if places:
            self._cache_set(("overpass", query), list(places))

        return places, None

    # ------------------------------------------------------------ Nominatim inti

    def _nominatim_search(
        self, query: str, lat: Optional[float] = None, lon: Optional[float] = None,
        radius: Optional[float] = None,
    ) -> tuple[Optional[list[NormalizedPlace]], Optional[ExternalContextError], dict]:
        """Cari teks. Dengan lat/lon: dibatasi bounding box dulu; kalau kosong,
        tanpa batas tapi diurutkan jarak dan yang jauh dibuang."""
        params: dict[str, Any] = {
            "q": query, "format": "jsonv2", "limit": 10,
            "addressdetails": 1, "accept-language": "id",
        }
        meta: dict[str, Any] = {}
        has_ref = lat is not None and lon is not None

        if has_ref:
            span = max(1000, int(radius or 5000))
            dlat = span / 111320.0
            dlon = span / (111320.0 * max(0.2, math.cos(math.radians(lat))))
            params["viewbox"] = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"
            params["bounded"] = 1
            meta["bounded"] = True

        data, error = self._call(f"{NOMINATIM}/search", params)

        if error is not None:
            return None, error, meta

        items = data if isinstance(data, list) else []

        if not items and has_ref:
            params.pop("bounded", None)
            params["limit"] = 15
            meta["bounded"] = False

            data, error = self._call(f"{NOMINATIM}/search", params)

            if error is not None:
                return None, error, meta

            items = data if isinstance(data, list) else []

        places = [self._place_from_nominatim(i) for i in items if isinstance(i, dict)]

        if has_ref:
            for place in places:
                if place.latitude is not None and place.longitude is not None:
                    place.distance_meters = round(_haversine_m(lat, lon, place.latitude, place.longitude), 1)

            places.sort(key=lambda p: p.distance_meters if p.distance_meters is not None else float("inf"))

            if meta.get("bounded") is False:
                near = [p for p in places if p.distance_meters is not None and p.distance_meters <= FAR_RESULT_METERS]

                if near:
                    places = near
                else:
                    places = places[:3]
                    meta["far_results"] = True

        return places, None, meta

    # ------------------------------------------------------------ search

    def _search(self, query: str, location: Optional[str] = None, radius: Optional[int] = None, **kwargs) -> QueryResult:
        query = (query or "").strip()

        if not query:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="query tidak boleh kosong.",
                provider=PROVIDER_NAME, capability=CAPABILITY_SEARCH,
            ))

        match = _COORD_RE.match(location or "")
        lat = lon = None
        base_radius = 5000

        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            base_radius = max(500, min(int(_to_float(radius) or 5000), MAX_NEARBY_RADIUS_METERS))

        # Berlokasi + kategori dikenali -> Overpass dulu (akurat), radius melebar kalau cari nama.
        if lat is not None:
            tag_filter, core, _ = _split_category(query)

            if tag_filter:
                radii = [base_radius]
                if core and SEARCH_WIDE_RADIUS_METERS > base_radius:
                    radii.append(SEARCH_WIDE_RADIUS_METERS)

                for rad in radii:
                    result = self._nearby(lat, lon, radius=rad, keyword=query, allow_fallback=False)

                    if result.success and result.places:
                        return QueryResult.ok(
                            PROVIDER_NAME, CAPABILITY_SEARCH, places=result.places,
                            metadata={"query": query, "radius": rad, "source": "overpass"},
                        )

        places, error, meta = self._nominatim_search(query, lat, lon, base_radius)

        if error is not None:
            error.capability = CAPABILITY_SEARCH
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, error)

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_SEARCH, places=places or [],
            metadata={"query": query, "source": "nominatim", **meta},
        )

    # ------------------------------------------------------------ lookup

    @staticmethod
    def _parse_osm_ref(place_id: str) -> Optional[str]:
        text = (place_id or "").strip()
        match = re.match(r"^(node|way|relation)/(\d+)$", text, re.I)

        if match:
            return match.group(1)[0].upper() + match.group(2)

        if re.match(r"^[NWR]\d+$", text, re.I):
            return text[0].upper() + text[1:]

        return None

    def _lookup(self, place_id: str, **kwargs) -> QueryResult:
        ref = self._parse_osm_ref(place_id)

        if ref is None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, ExternalContextError(
                code=ERROR_INVALID_REQUEST,
                message="place_id harus berformat 'N123', 'W123', 'R123' (atau 'node/123').",
                provider=PROVIDER_NAME, capability=CAPABILITY_LOOKUP,
            ))

        data, error = self._call(f"{NOMINATIM}/lookup", {
            "osm_ids": ref, "format": "jsonv2", "addressdetails": 1, "accept-language": "id",
        })

        if error is not None:
            error.capability = CAPABILITY_LOOKUP
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, error)

        if not isinstance(data, list) or not data:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"place_id '{place_id}' tidak ditemukan.",
                provider=PROVIDER_NAME, capability=CAPABILITY_LOOKUP,
            ))

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_LOOKUP, places=[self._place_from_nominatim(data[0])])

    # ------------------------------------------------------------ nearby

    def _nearby(
        self, latitude: float, longitude: float,
        radius: int = DEFAULT_NEARBY_RADIUS_METERS, keyword: Optional[str] = None,
        allow_fallback: bool = True, **kwargs,
    ) -> QueryResult:
        lat, lon = _to_float(latitude), _to_float(longitude)

        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="latitude/longitude wajib diisi dan harus valid.",
                provider=PROVIDER_NAME, capability=CAPABILITY_NEARBY,
            ))

        radius_m = max(100, min(int(_to_float(radius) or DEFAULT_NEARBY_RADIUS_METERS), MAX_NEARBY_RADIUS_METERS))

        places, error = self._overpass_places(lat, lon, radius_m, _overpass_filters(keyword))

        if error is None and places:
            return QueryResult.ok(
                PROVIDER_NAME, CAPABILITY_NEARBY, places=places,
                metadata={"latitude": lat, "longitude": lon, "radius": radius_m, "source": "overpass"},
            )

        if allow_fallback:
            fallback = self._nearby_via_nominatim(lat, lon, radius_m, keyword)

            if fallback is not None:
                logger.info("NEARBY | Overpass %s, memakai fallback Nominatim.", "gagal" if error else "kosong")
                return fallback

        if error is not None:
            error.capability = CAPABILITY_NEARBY
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, error)

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_NEARBY, places=[],
            metadata={"latitude": lat, "longitude": lon, "radius": radius_m, "source": "overpass"},
        )

    def _nearby_via_nominatim(
        self, lat: float, lon: float, radius: float, keyword: Optional[str],
    ) -> Optional[QueryResult]:
        _, core, cleaned = _split_category(keyword)

        if not cleaned:
            return None

        variants = [cleaned]
        if core and core != cleaned:
            variants.append(core)

        for variant in variants:
            data, error, _ = self._nominatim_search(variant, lat, lon, radius)

            if error is not None or not data:
                continue

            places = [
                p for p in data
                if p.distance_meters is not None and p.distance_meters <= radius * 1.2
            ]

            if places:
                return QueryResult.ok(
                    PROVIDER_NAME, CAPABILITY_NEARBY, places=places[:NEARBY_MAX_RESULTS],
                    metadata={
                        "latitude": lat, "longitude": lon, "radius": radius,
                        "source": "nominatim", "fallback": "nominatim",
                    },
                )

        return None

    # ------------------------------------------------------------ route

    def _resolve_point(
        self, text: str, capability: str,
    ) -> tuple[Optional[tuple[float, float, str]], Optional[ExternalContextError]]:
        match = _COORD_RE.match(text or "")

        if match:
            return (float(match.group(1)), float(match.group(2)), text.strip()), None

        cache_key = ("geocode", (text or "").strip().lower())
        cached = self._cache_get(cache_key)

        if cached is not None:
            return cached, None

        data, error = self._call(f"{NOMINATIM}/search", {
            "q": text, "format": "jsonv2", "limit": 1, "accept-language": "id",
        })

        if error is not None:
            error.capability = capability
            return None, error

        if not isinstance(data, list) or not data:
            return None, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"Lokasi '{text}' tidak ditemukan.",
                provider=PROVIDER_NAME, capability=capability,
            )

        lat, lon = _to_float(data[0].get("lat")), _to_float(data[0].get("lon"))

        if lat is None or lon is None:
            return None, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"Koordinat untuk '{text}' tidak valid.",
                provider=PROVIDER_NAME, capability=capability,
            )

        resolved = (lat, lon, str(data[0].get("display_name") or text))
        self._cache_set(cache_key, resolved, ttl=GEOCODE_CACHE_TTL_SECONDS)

        return resolved, None

    def _route(
        self, origin: str, destination: str, mode: str = DEFAULT_ROUTE_MODE,
        alternatives: bool = False, **kwargs,
    ) -> QueryResult:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        mode = (mode or DEFAULT_ROUTE_MODE).strip().lower()
        want_alternatives = bool(alternatives)

        if not origin or not destination:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="origin dan destination wajib diisi.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        if mode not in VALID_ROUTE_MODES:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_INVALID_REQUEST,
                message=f"mode '{mode}' tidak dikenal. Pilihan: {sorted(VALID_ROUTE_MODES)}.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        if mode not in OSRM_SERVERS:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_INVALID_REQUEST,
                message=f"OpenStreetMap/OSRM belum mendukung mode '{mode}'. Pilihan: {sorted(OSRM_SERVERS)}.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        start, error = self._resolve_point(origin, CAPABILITY_ROUTE)
        if error is not None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        end, error = self._resolve_point(destination, CAPABILITY_ROUTE)
        if error is not None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        base, profile = OSRM_SERVERS[mode]
        url = f"{base}/route/v1/{profile}/{start[1]},{start[0]};{end[1]},{end[0]}"

        cache_key = ("osrm", url, want_alternatives)
        data = self._cache_get(cache_key)

        if data is None:
            data, error = self._call(url, {
                "overview": "full", "geometries": "geojson", "steps": "true",
                "alternatives": "true" if want_alternatives else "false",
            })

            if error is not None:
                error.capability = CAPABILITY_ROUTE
                return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

            if isinstance(data, dict) and data.get("code") == "Ok":
                self._cache_set(cache_key, data)

        code = str(data.get("code") or "") if isinstance(data, dict) else ""

        if code != "Ok":
            mapped = ERROR_NO_RESULTS if code == "NoRoute" else (
                ERROR_INVALID_REQUEST if code in ("InvalidQuery", "InvalidUrl", "InvalidValue")
                else ERROR_PROVIDER_UNAVAILABLE
            )
            message = (
                str(data.get("message") or f"OSRM: {code or 'respons tidak valid'}")
                if isinstance(data, dict) else "Respons OSRM tidak valid."
            )
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=mapped, message=message, provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
                retryable=mapped == ERROR_PROVIDER_UNAVAILABLE, details={"osrm_code": code},
            ))

        routes = data.get("routes") or []

        if not routes:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"Tidak ada rute dari '{origin}' ke '{destination}'.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        best = routes[0]
        legs = best.get("legs") or []
        steps = (legs[0].get("steps") if legs else None) or []

        segments = [
            RouteSegment(
                instruction=_step_instruction(step),
                distance_meters=step.get("distance"), duration_seconds=step.get("duration"),
            )
            for step in steps
        ]

        coordinates = (best.get("geometry") or {}).get("coordinates") or []
        geometry = [
            [round(c[1], 5), round(c[0], 5)]
            for c in coordinates
            if isinstance(c, (list, tuple)) and len(c) >= 2
            and _to_float(c[0]) is not None and _to_float(c[1]) is not None
        ]
        geometry = _downsample(geometry, ROUTE_MAX_POINTS)

        alternative_routes = [
            {
                "via": _via(route),
                "distance_m": route.get("distance"),
                "duration_s": route.get("duration"),
            }
            for route in routes[1:1 + MAX_ALTERNATIVES]
        ] if want_alternatives else []

        directions_url = (
            "https://www.openstreetmap.org/directions"
            f"?engine={OSM_DIRECTIONS_ENGINE[mode]}&route={start[0]}%2C{start[1]}%3B{end[0]}%2C{end[1]}"
        )

        normalized = NormalizedRoute(
            origin=origin, destination=destination,
            distance_meters=best.get("distance"), duration_seconds=best.get("duration"),
            segments=segments,
            metadata={
                "mode": mode, "engine": "osrm", "osm_url": directions_url,
                "geometry": geometry,
                "via": _via(best),
                "alternatives": alternative_routes,
                "alternatives_requested": want_alternatives,
                "origin_resolved": {"latitude": start[0], "longitude": start[1], "label": start[2]},
                "destination_resolved": {"latitude": end[0], "longitude": end[1], "label": end[2]},
            },
        )

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_ROUTE, route=normalized)
    # ------------------------------------------------------------ context

    def _context(self, latitude: float, longitude: float, radius: int = 500, **kwargs) -> QueryResult:
        lat, lon = _to_float(latitude), _to_float(longitude)

        if lat is None or lon is None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="latitude dan longitude wajib diisi.",
                provider=PROVIDER_NAME, capability=CAPABILITY_CONTEXT,
            ))

        data, error = self._call(f"{NOMINATIM}/reverse", {
            "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18,
            "addressdetails": 1, "accept-language": "id",
        })

        if error is not None:
            error.capability = CAPABILITY_CONTEXT
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, error)

        if not isinstance(data, dict) or data.get("error") or not data.get("display_name"):
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"Tidak ada informasi lokasi untuk {lat},{lon}.",
                provider=PROVIDER_NAME, capability=CAPABILITY_CONTEXT,
            ))

        primary = self._place_from_nominatim(data)
        primary.metadata["role"] = "reverse_geocode"

        nearby = self._nearby(lat, lon, radius=radius, allow_fallback=False)
        nearby_names = [p.name for p in nearby.places[:5]] if nearby.success else []

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_CONTEXT, places=[primary],
            metadata={"latitude": lat, "longitude": lon, "nearby": nearby_names},
        )


__all__ = [
    "OpenStreetMapConfig",
    "OpenStreetMapProvider",
    "OSMTimeout",
    "OVERPASS_MIRRORS",
    "load_openstreetmap_config",
]