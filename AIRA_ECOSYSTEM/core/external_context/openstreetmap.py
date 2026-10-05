"""
core/external_context/openstreetmap.py — adapter OpenStreetMap untuk External
Context Layer (Sprint 2.7 / W7).

Satu-satunya modul yang tahu bentuk endpoint Nominatim, Overpass, dan OSRM.
Modul lain hanya bicara lewat kontrak ExternalContextProvider.

Pemetaan capability -> layanan:
    search()  -> Nominatim /search
    lookup()  -> Nominatim /lookup
    nearby()  -> Overpass (utama), Nominatim bounded-search (fallback)
    route()   -> Nominatim (geocode titik) + OSRM
    context() -> Nominatim /reverse + nearby() tanpa fallback

PERBAIKAN (error Overpass 504 / timeout di log):
  1. Timeout per mirror pendek (OVERPASS_CLIENT_TIMEOUT) dan ada batas total
     waktu semua mirror (OVERPASS_TOTAL_BUDGET), jadi 4 mirror tidak lagi
     bisa menggantung sampai 90+ detik.
  2. Mirror yang baru gagal "diistirahatkan" sebentar (OVERPASS_MIRROR_COOLDOWN)
     supaya request berikutnya tidak menabrak mirror yang sama lagi.
  3. Query dikecilkan: [timeout:N] server pendek dan `out center tags 30`.
  4. Kalau semua mirror gagal (atau hasilnya kosong), _nearby jatuh ke
     pencarian teks Nominatim yang dibatasi bounding box.

HTTP disuntik lewat `fetcher` (Dependency Injection, sama seperti
google_maps.py) supaya test tidak pernah memanggil jaringan sungguhan.
Signature fetcher:  fetcher(url, params=None, post=None) -> dict | list
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

# ------------------------------------------------------------------ endpoint

NOMINATIM = "https://nominatim.openstreetmap.org"

# Mirror Overpass publik. Daftar ini sering berubah - cek dulu mana yang masih
# hidup (mis. buka <mirror>/status di browser) sebelum dipakai di produksi.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
OVERPASS_CLIENT_TIMEOUT = 12     # detik per mirror (sisi client)
OVERPASS_SERVER_TIMEOUT = 10     # [timeout:N] di dalam query (sisi server)
OVERPASS_TOTAL_BUDGET = 30.0     # detik total untuk SEMUA mirror dalam satu panggilan
OVERPASS_MIRROR_COOLDOWN = 60.0  # detik mirror yang baru gagal dilewati
OVERPASS_MAX_ELEMENTS = 30
NEARBY_MAX_RESULTS = 20
MAX_NEARBY_RADIUS_METERS = 15000

DEFAULT_HTTP_TIMEOUT = 20

# Server routing OSRM per mode. CATATAN: server routing.openstreetmap.de
# memakai segmen profil "driving" di URL untuk SEMUA mode (profilnya ditentukan
# oleh prefix routed-foot / routed-bike). Verifikasi sebelum produksi.
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

# mirror -> waktu monotonic sampai kapan dilewati. Race antar-thread tidak
# berbahaya (paling buruk satu mirror dicoba sekali lagi).
_MIRROR_DOWN_UNTIL: dict[str, float] = {}


# ------------------------------------------------------------------ config

@dataclass(frozen=True)
class OpenStreetMapConfig:
    """OSM tidak butuh API key; yang bisa diatur hanya kill switch dan
    User-Agent (kebijakan Nominatim mewajibkan User-Agent yang jelas)."""

    enabled: bool = True
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def is_configured(self) -> bool:
        return self.enabled

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "is_configured": self.is_configured}


def load_openstreetmap_config(env: Optional[dict] = None) -> OpenStreetMapConfig:
    """Tidak pernah raise. Env disuntik untuk test."""
    source = env if env is not None else os.environ

    enabled_raw = source.get(ENV_ENABLED)
    enabled = True if enabled_raw is None else str(enabled_raw).strip().lower() not in _FALSE_VALUES

    agent = source.get(ENV_USER_AGENT)
    agent = agent.strip() if isinstance(agent, str) and agent.strip() else DEFAULT_USER_AGENT

    return OpenStreetMapConfig(enabled=enabled, user_agent=agent)


# ------------------------------------------------------------------ HTTP

class OSMTimeout(Exception):
    """Dilempar fetcher untuk timeout, supaya dipetakan ke ERROR_TIMEOUT
    (bukan ERROR_PROVIDER_UNAVAILABLE generik)."""


Fetcher = Callable[..., Any]


def _default_fetch(
    url: str,
    params: Optional[dict] = None,
    post: Optional[dict] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Any:
    """Fetcher bawaan berbasis `requests` (diimpor lazy). Mirror Overpass
    memakai timeout pendek; layanan lain memakai DEFAULT_HTTP_TIMEOUT."""
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
    """Exception transport -> ExternalContextError (tanpa capability)."""
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

# alias keyword -> filter tag Overpass. Dicocokkan hanya kalau keyword (setelah
# kata pengisi dibuang) SAMA dengan salah satu alias; selain itu dicari lewat nama.
_TAG_FILTERS: tuple[tuple[frozenset, str], ...] = (
    (frozenset({"rumah sakit", "rs", "rsud", "hospital"}), '["amenity"="hospital"]'),
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
    """Huruf kecil, karakter aneh dibuang (aman untuk regex/string Overpass),
    kata pengisi seperti 'terdekat' dibuang."""
    text = re.sub(r"[^\w\s\-]", " ", (keyword or "").lower())
    words = [w for w in text.split() if w not in _FILLER_WORDS]
    return " ".join(words)


def _overpass_filter(keyword: Optional[str]) -> str:
    cleaned = _clean_keyword(keyword)

    if not cleaned:
        return '["amenity"]["name"]'

    for aliases, tag_filter in _TAG_FILTERS:
        if cleaned in aliases:
            return tag_filter

    return f'["name"~"{cleaned}",i]'


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


_MODIFIER_ID = {
    "left": "kiri", "right": "kanan",
    "slight left": "serong kiri", "slight right": "serong kanan",
    "sharp left": "tajam ke kiri", "sharp right": "tajam ke kanan",
    "straight": "lurus", "uturn": "putar balik",
}


def _step_instruction(step: dict) -> str:
    """Satu langkah OSRM -> kalimat singkat (bukan turn-by-turn presisi)."""
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


# ------------------------------------------------------------------ provider

class OpenStreetMapProvider(ExternalContextProvider):
    """
    Konstruksi tidak pernah raise. `nominatim_min_interval` = jeda minimum
    antar request Nominatim (kebijakan publik: maks ~1 request/detik); test
    memberi 0 supaya tidak menunggu.
    """

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

    # ------------------------------------------------------------ identity

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name=PROVIDER_NAME, display_name=PROVIDER_DISPLAY_NAME, version="1.0")

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
        """GET satu layanan (Nominatim / OSRM) -> (data, None) atau (None, error)."""
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
        """
        POST query ke mirror Overpass satu per satu. Berhenti begitu satu
        mirror menjawab. Mirror yang sedang "istirahat" dilewati, dan seluruh
        loop dibatasi OVERPASS_TOTAL_BUDGET.
        """
        started = time.monotonic()
        last_error: Optional[ExternalContextError] = None

        mirrors = [m for m in OVERPASS_MIRRORS if _MIRROR_DOWN_UNTIL.get(m, 0.0) <= started]
        mirrors = mirrors or list(OVERPASS_MIRRORS)  # semua istirahat -> coba semua

        for mirror in mirrors:
            if last_error is not None and time.monotonic() - started >= OVERPASS_TOTAL_BUDGET:
                logger.warning("OVERPASS | anggaran waktu %.0fs habis, berhenti mencoba mirror.", OVERPASS_TOTAL_BUDGET)
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

            # Overpass kadang membalas 200 dengan "remark" runtime error/timeout
            # dan elements kosong - perlakukan sebagai kegagalan mirror itu.
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
        place_id = f"{osm_type}/{osm_id}" if osm_type and osm_id else str(item.get("place_id") or "")

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
        lat, lon = element.get("lat"), element.get("lon")

        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")

        lat, lon = _to_float(lat), _to_float(lon)

        if lat is None or lon is None:
            return None

        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        name = tags.get("name") or tags.get("name:id") or tags.get("brand") or tags.get("operator") or "Tempat tanpa nama"

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
            id=f"{osm_type}/{osm_id}", name=str(name), address=_address_from_tags(tags),
            latitude=lat, longitude=lon,
            distance_meters=round(_haversine_m(ref_lat, ref_lon, lat, lon), 1),
            metadata=metadata,
        )

    # ------------------------------------------------------------ search

    def _search(self, query: str, location: Optional[str] = None, radius: Optional[int] = None, **kwargs) -> QueryResult:
        query = (query or "").strip()

        if not query:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="query tidak boleh kosong.",
                provider=PROVIDER_NAME, capability=CAPABILITY_SEARCH,
            ))

        params: dict[str, Any] = {
            "q": query, "format": "jsonv2", "limit": 10,
            "addressdetails": 1, "accept-language": "id",
        }

        match = _COORD_RE.match(location or "")
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            span = max(1000, int(radius or 5000))
            dlat = span / 111320.0
            dlon = span / (111320.0 * max(0.2, math.cos(math.radians(lat))))
            params["viewbox"] = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"

        data, error = self._call(f"{NOMINATIM}/search", params)

        if error is not None:
            error.capability = CAPABILITY_SEARCH
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, error)

        places = [self._place_from_nominatim(i) for i in (data if isinstance(data, list) else [])]

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_SEARCH, places=places, metadata={"query": query})

    # ------------------------------------------------------------ lookup

    @staticmethod
    def _parse_osm_ref(place_id: str) -> Optional[str]:
        """'node/123' | 'way/9' | 'relation/5' | 'N123' -> 'N123'."""
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
                message="place_id harus berformat 'node/123', 'way/123', atau 'relation/123'.",
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
        overpass_filter = _overpass_filter(keyword)

        query = (
            f"[out:json][timeout:{OVERPASS_SERVER_TIMEOUT}];"
            f"nwr{overpass_filter}(around:{radius_m},{lat},{lon});"
            f"out center tags {OVERPASS_MAX_ELEMENTS};"
        )

        data, error = self._call_overpass(query)

        if error is not None:
            if allow_fallback:
                fallback = self._nearby_via_nominatim(lat, lon, radius_m, keyword)
                if fallback is not None:
                    logger.info("NEARBY | Overpass gagal (%s), memakai fallback Nominatim.", error.code)
                    return fallback

            error.capability = CAPABILITY_NEARBY
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, error)

        places = [
            p for p in (
                self._place_from_overpass(e, lat, lon)
                for e in (data.get("elements") or []) if isinstance(e, dict)
            ) if p is not None
        ]
        places.sort(key=lambda p: p.distance_meters if p.distance_meters is not None else float("inf"))
        places = places[:NEARBY_MAX_RESULTS]

        if not places and allow_fallback:
            fallback = self._nearby_via_nominatim(lat, lon, radius_m, keyword)
            if fallback is not None:
                return fallback

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_NEARBY, places=places,
            metadata={"latitude": lat, "longitude": lon, "radius": radius_m, "source": "overpass"},
        )

    def _nearby_via_nominatim(
        self, lat: float, lon: float, radius: float, keyword: Optional[str],
    ) -> Optional[QueryResult]:
        """Cadangan saat Overpass down/kosong: pencarian teks Nominatim dibatasi
        bounding box. Hasilnya kurang lengkap (tanpa telepon/jam buka) tapi cukup
        untuk menentukan tujuan dan menghitung rute. None kalau tidak ada hasil."""
        query = _clean_keyword(keyword)

        if not query:
            return None

        dlat = radius / 111320.0
        dlon = radius / (111320.0 * max(0.2, math.cos(math.radians(lat))))

        data, error = self._call(f"{NOMINATIM}/search", {
            "q": query, "format": "jsonv2", "limit": 20, "bounded": 1,
            "addressdetails": 1, "accept-language": "id",
            "viewbox": f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}",
        })

        if error is not None or not isinstance(data, list) or not data:
            return None

        places = []
        for item in data:
            place = self._place_from_nominatim(item)
            if place.latitude is None or place.longitude is None:
                continue
            place.distance_meters = round(_haversine_m(lat, lon, place.latitude, place.longitude), 1)
            if place.distance_meters <= radius * 1.2:
                places.append(place)

        if not places:
            return None

        places.sort(key=lambda p: p.distance_meters)

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_NEARBY, places=places[:NEARBY_MAX_RESULTS],
            metadata={
                "latitude": lat, "longitude": lon, "radius": radius,
                "source": "nominatim", "fallback": "nominatim",
            },
        )

    # ------------------------------------------------------------ route

    def _resolve_point(
        self, text: str, capability: str,
    ) -> tuple[Optional[tuple[float, float, str]], Optional[ExternalContextError]]:
        """'lat,lon' dipakai langsung; selain itu di-geocode lewat Nominatim.
        Return ((lat, lon, label), None) atau (None, error)."""
        match = _COORD_RE.match(text or "")

        if match:
            return (float(match.group(1)), float(match.group(2)), text.strip()), None

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

        return (lat, lon, str(data[0].get("display_name") or text)), None

    def _route(self, origin: str, destination: str, mode: str = DEFAULT_ROUTE_MODE, **kwargs) -> QueryResult:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        mode = (mode or DEFAULT_ROUTE_MODE).strip().lower()

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

        data, error = self._call(url, {"overview": "false", "steps": "true", "alternatives": "false"})

        if error is not None:
            error.capability = CAPABILITY_ROUTE
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        code = str(data.get("code") or "") if isinstance(data, dict) else ""

        if code != "Ok":
            mapped = ERROR_NO_RESULTS if code == "NoRoute" else (
                ERROR_INVALID_REQUEST if code in ("InvalidQuery", "InvalidUrl", "InvalidValue") else ERROR_PROVIDER_UNAVAILABLE
            )
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=mapped,
                message=str(data.get("message") or f"OSRM: {code or 'respons tidak valid'}") if isinstance(data, dict) else "Respons OSRM tidak valid.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
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
                "origin_resolved": {"latitude": start[0], "longitude": start[1], "label": start[2]},
                "destination_resolved": {"latitude": end[0], "longitude": end[1], "label": end[2]},
            },
        )

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_ROUTE, route=normalized)

    # ------------------------------------------------------------ context

    def _context(self, latitude: float, longitude: float, radius: int = 500, **kwargs) -> QueryResult:
        """Ringkasan "ada apa di sekitar sini": reverse-geocode untuk label alamat,
        lalu nearby() TANPA fallback (kegagalan nearby tidak menggagalkan context)."""
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