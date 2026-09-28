"""
agents/rei/maps_tools.py — Google Maps sebagai kemampuan chat AIRA.

Wrapper tipis di atas core/external_context (GoogleMapsProvider) + core/location.
Tidak ada logic Google di sini: provider tetap satu-satunya yang tahu endpoint
Google. File ini hanya:
  1. memilih titik asal (lokasi akses user) untuk "terdekat"/"dari sini",
  2. kalau lokasi belum presisi -> mengembalikan FORM IZIN LOKASI (DIO) alih-alih
     menebak. Planner otomatis menampilkan form itu ke user,
  3. meringkas hasil (maks 5 tempat) + membuat link Google Maps (maps_url)
     supaya jawaban AIRA bisa menampilkan hasil Maps sebagai link Markdown.

API key TIDAK PERNAH masuk hasil tool (QueryResult tidak membawanya).

session_id disisipkan planner (SESSION_AWARE_TOOLS) - LLM tidak menyebutkannya.

Didaftarkan di core/orchestrator.py (MAPS_TOOLS / MAPS_TOOL_CATEGORY /
MAPS_TOOL_SCHEMAS) tanpa mengubah agents/rei/registry.py.
"""

import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv

from agents.rei.dio_tools import request_location_permission
from core.external_context import get_google_maps_provider
from core.location import location_service
from core.location.models import SOURCE_BROWSER

logger = logging.getLogger("aira.rei.maps_tools")

_AIRA_ROOT = Path(__file__).resolve().parents[2]

# Provider membaca GOOGLE_MAPS_API_KEY dari environment saat pertama dipakai.
load_dotenv(_AIRA_ROOT / ".env", override=False)
load_dotenv(_AIRA_ROOT.parent / ".env", override=False)

MAX_PLACES = 5
DEFAULT_SEARCH_RADIUS_METERS = 3000
MAX_ROUTE_STEPS = 8
_HERE_WORDS = {"", "lokasi saya", "lokasiku", "posisiku", "posisi saya", "sini", "dari sini", "my location", "here"}

MAPS_NOTE = (
    "Tampilkan sebagai daftar Markdown dengan link [nama](maps_url) PERSIS dari hasil ini. "
    "Sebut jarak/rating kalau ada. Jangan mengarang tempat atau alamat."
)


# ============================================================ helpers

def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "ya")
    return bool(value)


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _current_location(session_id: Optional[str]):
    """Lokasi akses sesi (GPS > cache > IP). None kalau tidak diketahui."""
    try:
        access = location_service.get_access(session_id, resolve=False)
        if access is None and session_id:
            access = location_service.get_access(session_id)
    except Exception:
        logger.exception("MAPS | gagal membaca lokasi akses (diabaikan).")
        return None

    if access is None or not access.has_coordinates():
        return None

    return access


def _is_precise(access, session_id: Optional[str]) -> bool:
    # Mode terminal (tanpa sesi) = user duduk di mesin hosting.
    return access is not None and (access.source == SOURCE_BROWSER or not session_id)


def _locate(session_id, allow_approximate, request_text, reason):
    """
    Return (access, permission_result). Kalau permission_result tidak None,
    kembalikan itu apa adanya dari tool -> planner menampilkan form izin.
    """
    access = _current_location(session_id)

    if _is_precise(access, session_id):
        return access, None

    if access is not None and allow_approximate:
        return access, None

    if session_id:
        return None, request_location_permission(
            original_request=request_text, reason=reason, session_id=session_id,
        )

    return access, None


def _fail(tool: str, result) -> dict:
    error = result.error
    code = error.code if error else "provider_unavailable"
    message = error.message if error else "Permintaan ke Google Maps gagal."

    if code in ("provider_unavailable", "authentication_error"):
        message += (
            " Pastikan GOOGLE_MAPS_API_KEY sudah diisi di .env dan API Places, "
            "Directions, dan Geocoding aktif di Google Cloud."
        )

    return {"success": False, "tool": tool, "error": message, "error_code": code}


def _place_url(place) -> str:
    if place.latitude is not None and place.longitude is not None:
        query = f"{place.latitude},{place.longitude}"
    else:
        query = quote_plus(place.name or "")

    url = f"https://www.google.com/maps/search/?api=1&query={query}"

    if place.id:
        url += f"&query_place_id={quote_plus(place.id)}"

    return url


def _place_dict(place, origin) -> dict:
    data: dict[str, Any] = {
        "name": place.name,
        "address": place.address,
        "maps_url": _place_url(place),
        "place_id": place.id,
    }

    meta = place.metadata or {}
    for key, target in (("rating", "rating"), ("user_ratings_total", "reviews"), ("open_now", "open_now")):
        if meta.get(key) is not None:
            data[target] = meta[key]

    if origin is not None and place.latitude is not None and place.longitude is not None:
        data["distance_km"] = round(
            location_service._haversine(origin.latitude, origin.longitude, place.latitude, place.longitude), 2,
        )

    return data


# ============================================================ tools

def maps_search(
    query: str,
    near_me: Any = False,
    radius: Any = None,
    max_results: Any = MAX_PLACES,
    allow_approximate: Any = False,
    session_id: Optional[str] = None,
    **_ignored: Any,
) -> dict:
    """Cari tempat di Google Maps; near_me=True mengurutkan berdasarkan jarak dari user."""
    query = (query or "").strip()

    if not query:
        return {"success": False, "tool": "maps_search", "error": "query wajib diisi."}

    limit = _as_int(max_results, MAX_PLACES, 1, MAX_PLACES)
    origin = None
    params: dict[str, Any] = {}

    if _as_bool(near_me):
        origin, permission = _locate(
            session_id, _as_bool(allow_approximate),
            request_text=f"Cari {query} di dekat lokasiku sekarang",
            reason=f"Untuk mencari '{query}' terdekat, AIRA butuh lokasimu sekarang.",
        )

        if permission is not None:
            return permission

        if origin is None:
            return {
                "success": False, "tool": "maps_search",
                "error": "Lokasi user belum diketahui. Minta user menyebut nama daerah/kota.",
            }

        params["location"] = f"{origin.latitude},{origin.longitude}"
        params["radius"] = _as_int(radius, DEFAULT_SEARCH_RADIUS_METERS, 100, 50000)

    result = get_google_maps_provider().search(query, **params)

    if not result.success:
        return _fail("maps_search", result)

    places = [_place_dict(p, origin) for p in result.places]

    if origin is not None:
        places.sort(key=lambda p: p.get("distance_km", float("inf")))

    payload: dict[str, Any] = {
        "success": True, "tool": "maps_search", "query": query,
        "count": len(places[:limit]), "places": places[:limit], "note": MAPS_NOTE,
    }

    if origin is not None:
        payload["origin"] = {
            "label": origin.display_name(),
            "approximate": not _is_precise(origin, session_id),
        }

    return payload


def maps_route(
    destination: str,
    origin: Optional[str] = None,
    mode: str = "driving",
    allow_approximate: Any = False,
    session_id: Optional[str] = None,
    **_ignored: Any,
) -> dict:
    """Rute dari origin (default: lokasi user) ke destination."""
    destination = (destination or "").strip()

    if not destination:
        return {"success": False, "tool": "maps_route", "error": "destination wajib diisi."}

    origin_text = (origin or "").strip()
    origin_label = origin_text
    approximate = False

    if origin_text.lower() in _HERE_WORDS:
        access, permission = _locate(
            session_id, _as_bool(allow_approximate),
            request_text=f"Rute dari lokasiku ke {destination}",
            reason=f"Untuk menghitung rute ke '{destination}', AIRA butuh lokasimu sekarang.",
        )

        if permission is not None:
            return permission

        if access is None:
            return {
                "success": False, "tool": "maps_route",
                "error": "Lokasi user belum diketahui. Tanyakan titik asal (nama tempat/daerah) ke user.",
            }

        origin_text = f"{access.latitude},{access.longitude}"
        origin_label = access.display_name()
        approximate = not _is_precise(access, session_id)

    mode = (mode or "driving").strip().lower()
    result = get_google_maps_provider().route(origin_text, destination, mode=mode)

    if not result.success:
        return _fail("maps_route", result)

    route = result.route
    steps = [
        {
            "instruction": s.instruction,
            **({"distance_m": s.distance_meters} if s.distance_meters is not None else {}),
        }
        for s in route.segments[:MAX_ROUTE_STEPS]
    ]

    return {
        "success": True, "tool": "maps_route",
        "origin": origin_label, "origin_approximate": approximate,
        "destination": destination, "mode": mode,
        "distance_km": round(route.distance_meters / 1000, 1) if route.distance_meters is not None else None,
        "duration_minutes": round(route.duration_seconds / 60) if route.duration_seconds is not None else None,
        "steps": steps,
        "steps_truncated": len(route.segments) > MAX_ROUTE_STEPS,
        "maps_url": (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(origin_text)}&destination={quote_plus(destination)}"
            f"&travelmode={quote_plus(mode)}"
        ),
        "note": (
            "Ringkas jarak & durasi, tampilkan langkah utama sebagai daftar, lalu beri link "
            "[Buka di Google Maps](maps_url) PERSIS dari hasil ini."
        ),
    }


def maps_place_details(place_id: str, **_ignored: Any) -> dict:
    """Detail satu tempat dari place_id hasil maps_search."""
    place_id = (place_id or "").strip()

    if not place_id:
        return {"success": False, "tool": "maps_place_details", "error": "place_id wajib diisi."}

    result = get_google_maps_provider().lookup(place_id)

    if not result.success:
        return _fail("maps_place_details", result)

    return {
        "success": True, "tool": "maps_place_details",
        "place": _place_dict(result.places[0], None), "note": MAPS_NOTE,
    }


# ============================================================ registry-ready

MAPS_TOOLS: dict = {
    "maps_search": maps_search,
    "maps_route": maps_route,
    "maps_place_details": maps_place_details,
}

MAPS_TOOL_CATEGORY: dict[str, str] = {name: "location" for name in MAPS_TOOLS}

MAPS_TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": "maps_search",
        "description": (
            "Mencari tempat/bisnis/alamat di Google Maps (restoran, SPBU, ATM, toko, dsb). "
            "Set near_me=true untuk 'terdekat', 'dekat sini', 'di sekitarku' - hasil diurutkan "
            "dari jarak ke lokasi user. Kalau lokasi user belum presisi, tool otomatis "
            "menampilkan form izin lokasi (setelah itu JANGAN menulis apa pun lagi). Kalau user "
            "menolak izin, panggil ulang dengan allow_approximate=true. Untuk tempat di kota/"
            "daerah tertentu, sebut daerahnya di query dan biarkan near_me=false."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Apa yang dicari, mis. 'bakso' atau 'SPBU Cimahi'."},
            "near_me": {"type": "boolean", "description": "True = cari di sekitar lokasi user.", "default": False},
            "radius": {"type": "integer", "description": "Radius meter untuk near_me (default 3000)."},
            "max_results": {"type": "integer", "description": "Jumlah hasil, maks 5.", "default": 5},
            "allow_approximate": {
                "type": "boolean",
                "description": "True = boleh pakai lokasi perkiraan (IP) kalau GPS tidak diberikan.",
                "default": False,
            },
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "maps_route",
        "description": (
            "Menghitung rute Google Maps: jarak, durasi, dan langkah utama. Kosongkan origin "
            "untuk memakai lokasi user (form izin lokasi tampil otomatis kalau belum presisi). "
            "Bukan untuk traceroute jaringan."
        ),
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "Tujuan (nama tempat atau alamat)."},
            "origin": {"type": "string", "description": "Titik asal. Kosongkan = lokasi user."},
            "mode": {
                "type": "string", "description": "driving | walking | bicycling | transit",
                "default": "driving",
            },
            "allow_approximate": {"type": "boolean", "default": False},
        }, "required": ["destination"]},
    }},
    {"type": "function", "function": {
        "name": "maps_place_details",
        "description": "Detail satu tempat berdasarkan place_id dari hasil maps_search.",
        "parameters": {"type": "object", "properties": {
            "place_id": {"type": "string"},
        }, "required": ["place_id"]},
    }},
]
