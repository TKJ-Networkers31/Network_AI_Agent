"""
core/location/geo.py — helper geolokasi: IP -> kota, koordinat <-> nama tempat.

- IP lookup   : ipwho.is (HTTPS, tanpa API key). Ganti provider cukup di lookup_ip().
- Geocoding   : Nominatim (OpenStreetMap), wajib User-Agent, dibatasi ~1 req/detik
                -> hasil di-cache.
Semua fungsi TIDAK PERNAH raise. Gagal (offline/rate limit) -> None, dan
kegagalan di-cache 5 menit supaya tidak menahan tiap giliran chat dengan
timeout berulang.
"""

import ipaddress
import logging
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger("aira.location.geo")

HTTP_TIMEOUT = 4
USER_AGENT = "AIRA-OS/1.0 (personal network assistant)"

IP_LOOKUP_URL = "https://ipwho.is/{ip}"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"

_TTL_OK = 24 * 3600
_TTL_FAIL = 300

_cache: dict = {}
_cache_lock = threading.Lock()


# ------------------------------------------------------------------ IP helpers

def _parse_ip(value):
    try:
        ip = ipaddress.ip_address((value or "").strip().split("%")[0])
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def is_loopback_ip(value) -> bool:
    ip = _parse_ip(value)
    return bool(ip and ip.is_loopback)


def is_local_ip(value) -> bool:
    """True untuk loopback, LAN (192.168/10/172.16), link-local, CGNAT/VPN."""
    ip = _parse_ip(value)
    return bool(ip is not None and not ip.is_global)


def extract_client_ip(headers, fallback: Optional[str]) -> Optional[str]:
    """IP klien. Memakai X-Forwarded-For (dari proxy Vite dev) kalau valid."""
    for header in ("x-forwarded-for", "x-real-ip"):
        raw = headers.get(header)
        if raw:
            first = raw.split(",")[0].strip()
            if _parse_ip(first) is not None:
                return first
    return fallback


# ---------------------------------------------------------------------- cache

def _get_json(url: str, params: Optional[dict] = None):
    response = requests.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _cached(key: str, loader):
    now = time.time()

    with _cache_lock:
        item = _cache.get(key)

    if item and item[0] > now:
        return item[1]

    try:
        value = loader()
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
        logger.warning("GEO | %s gagal: %s", key.split(":")[0], exc)
        value = None

    with _cache_lock:
        _cache[key] = (now + (_TTL_OK if value else _TTL_FAIL), value)

    return value


def _address_parts(address: dict) -> dict:
    city = next(
        (address[k] for k in ("city", "town", "municipality", "county", "village", "suburb") if address.get(k)),
        None,
    )
    return {"city": city, "region": address.get("state"), "country": address.get("country")}


# --------------------------------------------------------------------- public

def lookup_ip(ip: Optional[str] = None) -> Optional[dict]:
    """ip=None -> IP publik mesin ini (dipakai untuk mendeteksi lokasi hosting).
    IP privat/loopback tidak bisa di-geolokasi -> None."""
    target = (ip or "").strip()

    if target and (_parse_ip(target) is None or is_local_ip(target)):
        return None

    def load():
        data = _get_json(IP_LOOKUP_URL.format(ip=target))
        if data.get("success") is False or data.get("latitude") is None:
            return None
        tz = data.get("timezone")
        return {
            "ip": data.get("ip") or target or None,
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country"),
            "timezone": tz.get("id") if isinstance(tz, dict) else tz,
        }

    return _cached(f"ip:{target or 'self'}", load)


def reverse_geocode(latitude: float, longitude: float) -> Optional[dict]:
    def load():
        data = _get_json(NOMINATIM_REVERSE_URL, {
            "format": "jsonv2", "lat": latitude, "lon": longitude,
            "zoom": 10, "addressdetails": 1, "accept-language": "id",
        })
        parts = _address_parts(data.get("address") or {})
        return parts if any(parts.values()) else None

    return _cached(f"rev:{round(latitude, 2)}:{round(longitude, 2)}", load)


def forward_geocode(query: str) -> Optional[dict]:
    query = (query or "").strip()
    if not query:
        return None

    def load():
        data = _get_json(NOMINATIM_SEARCH_URL, {
            "format": "jsonv2", "q": query, "limit": 1,
            "addressdetails": 1, "accept-language": "id",
        })
        first = data[0]
        return {
            "latitude": float(first["lat"]),
            "longitude": float(first["lon"]),
            **_address_parts(first.get("address") or {}),
        }

    return _cached(f"fwd:{query.lower()}", load)