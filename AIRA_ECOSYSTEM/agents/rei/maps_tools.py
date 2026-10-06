"""
agents/rei/maps_tools.py — peta/lokasi sebagai kemampuan chat AIRA.

Memakai provider peta AKTIF (default OpenStreetMap, gratis, tanpa API key)
lewat core.external_context.get_maps_provider(). Tidak ada logic provider di
sini - hanya:
  1. memilih titik asal (lokasi akses user) untuk "terdekat"/"dari sini",
  2. kalau lokasi belum presisi -> mengembalikan FORM IZIN LOKASI (DIO),
  3. meringkas hasil (maks 5 tempat), membuat link OpenStreetMap, dan
     map_block (blok ```map ringkas, dibuat core.external_context.map_block,
     bukan diketik LLM) untuk peta Leaflet di frontend.

Lokasi dianggap presisi kalau bersumber dari GPS/lokasi browser ATAU pin
manual (SOURCE_MANUAL). session_id disisipkan planner (SESSION_AWARE_TOOLS).
"""

import logging
from typing import Any, Optional
from urllib.parse import quote_plus

from agents.rei.dio_tools import request_location_permission
from core.external_context import get_maps_provider
from core.external_context.map_block import build_map_block
from core.location import location_service
from core.location.models import SOURCE_BROWSER, SOURCE_MANUAL

logger = logging.getLogger("aira.rei.maps_tools")

MAX_PLACES = 5
DEFAULT_SEARCH_RADIUS_METERS = 3000
MAX_ROUTE_STEPS = 8
PRECISE_SOURCES = (SOURCE_BROWSER, SOURCE_MANUAL)
_HERE_WORDS = {
    "", "lokasi saya", "lokasiku", "posisiku", "posisi saya",
    "sini", "dari sini", "my location", "here",
}

OSM_DIRECTIONS_ENGINE = {
    "driving": "fossgis_osrm_car",
    "walking": "fossgis_osrm_foot",
    "bicycling": "fossgis_osrm_bike",
}

MAPS_NOTE = (
    "Tampilkan sebagai daftar Markdown dengan link [nama](maps_url) PERSIS dari hasil ini, lalu "
    "TEMPEL field map_block PERSIS apa adanya di akhir jawaban (peta dirender otomatis). "
    "Sebut jarak/telepon/jam buka kalau ada. Jangan mengarang tempat atau alamat."
)

FAR_RESULTS_NOTE = (
    "PERINGATAN: tidak ada tempat yang cocok di sekitar user; hasil di bawah berada JAUH dari "
    "lokasi user. Sampaikan itu dengan jelas (jangan menyebutnya 'terdekat') dan tawarkan "
    "mencari dengan nama lain/lebih lengkap."
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
    """Lokasi akses sesi (GPS/pin > cache > IP). None kalau tidak diketahui."""
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
    return access is not None and (access.source in PRECISE_SOURCES or not session_id)


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
    message = error.message if error else "Permintaan peta gagal."

    if code in ("provider_unavailable", "timeout", "rate_limited"):
        message += " Layanan OpenStreetMap sedang sibuk atau tidak terjangkau dari server; coba lagi sebentar."

    return {"success": False, "tool": tool, "error": message, "error_code": code}


def _place_url(place) -> str:
    if place.latitude is not None and place.longitude is not None:
        return (
            f"https://www.openstreetmap.org/?mlat={place.latitude}&mlon={place.longitude}"
            f"#map=18/{place.latitude}/{place.longitude}"
        )

    return f"https://www.openstreetmap.org/search?query={quote_plus(place.name or '')}"


def _place_dict(place, origin) -> dict:
    data: dict[str, Any] = {
        "name": place.name,
        "address": place.address,
        "maps_url": _place_url(place),
        "place_id": place.id,
        "lat": round(place.latitude, 5) if place.latitude is not None else None,
        "lon": round(place.longitude, 5) if place.longitude is not None else None,
    }

    meta = place.metadata or {}
    for key, target in (
        ("rating", "rating"), ("user_ratings_total", "reviews"), ("open_now", "open_now"),
        ("phone", "phone"), ("opening_hours", "opening_hours"), ("website", "website"),
    ):
        if meta.get(key) is not None:
            data[target] = meta[key]

    if place.distance_meters is not None:
        data["distance_km"] = round(place.distance_meters / 1000, 2)
    elif origin is not None and place.latitude is not None and place.longitude is not None:
        data["distance_km"] = round(
            location_service._haversine(origin.latitude, origin.longitude, place.latitude, place.longitude), 2,
        )

    return data


def _distance_key(place, origin) -> float:
    """Kunci urut: jarak dari provider, atau hitung sendiri dari origin."""
    if place.distance_meters is not None:
        return place.distance_meters

    if origin is not None and place.latitude is not None and place.longitude is not None:
        return location_service._haversine(
            origin.latitude, origin.longitude, place.latitude, place.longitude,
        ) * 1000

    return float("inf")


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
    """Cari tempat; near_me=True mengurutkan berdasarkan jarak dari user."""
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

    result = get_maps_provider().search(query, **params)

    if not result.success:
        return _fail("maps_search", result)

    raw_places = sorted(result.places, key=lambda p: _distance_key(p, origin)) if origin is not None else list(result.places)
    shown_raw = raw_places[:limit]
    shown = [_place_dict(p, origin) for p in shown_raw]

    payload: dict[str, Any] = {
        "success": True, "tool": "maps_search", "query": query,
        "count": len(shown), "places": shown, "note": MAPS_NOTE,
    }

    if (result.metadata or {}).get("far_results"):
        payload["far_results"] = True
        payload["note"] = FAR_RESULTS_NOTE + " " + MAPS_NOTE

    origin_point = None

    if origin is not None:
        origin_point = {
            "lat": origin.latitude, "lon": origin.longitude, "accuracy": origin.accuracy,
        }
        payload["origin"] = {
            "label": origin.display_name(),
            "approximate": not _is_precise(origin, session_id),
            "accuracy_m": origin.accuracy,
        }

    if shown_raw:
        block = build_map_block(origin=origin_point, places=shown_raw)
        if block:
            payload["map_block"] = block

    if not shown:
        payload["note"] = (
            f"Tidak ada hasil untuk '{query}'. Sampaikan apa adanya, lalu tawarkan mencoba nama "
            "lain (mis. singkatan/nama lengkap) atau menyebut nama jalan/daerah. Jangan mengarang tempat."
        )

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
    result = get_maps_provider().route(origin_text, destination, mode=mode)

    if not result.success:
        return _fail("maps_route", result)

    route = result.route
    meta = route.metadata or {}

    steps = [
        {
            "instruction": s.instruction,
            **({"distance_m": round(s.distance_meters)} if s.distance_meters is not None else {}),
        }
        for s in route.segments[:MAX_ROUTE_STEPS]
    ]

    payload: dict[str, Any] = {
        "success": True, "tool": "maps_route",
        "origin": origin_label, "origin_approximate": approximate,
        "destination": destination, "mode": mode,
        "distance_km": round(route.distance_meters / 1000, 1) if route.distance_meters is not None else None,
        "duration_minutes": round(route.duration_seconds / 60) if route.duration_seconds is not None else None,
        "steps": steps,
        "steps_truncated": len(route.segments) > MAX_ROUTE_STEPS,
        "note": (
            "Ringkas jarak & durasi, tampilkan langkah utama sebagai daftar, beri link "
            "[Buka di OpenStreetMap](maps_url) PERSIS dari hasil ini, lalu TEMPEL map_block "
            "PERSIS apa adanya di akhir jawaban."
        ),
    }

    start = meta.get("origin_resolved") or {}
    end = meta.get("destination_resolved") or {}

    payload["maps_url"] = meta.get("osm_url") or (
        f"https://www.openstreetmap.org/search?query={quote_plus(destination)}"
    )

    if start.get("latitude") is not None and end.get("latitude") is not None:
        block = build_map_block(
            origin={"lat": start["latitude"], "lon": start["longitude"]},
            destination={"lat": end["latitude"], "lon": end["longitude"]},
            route=meta.get("geometry"),
        )
        if block:
            payload["map_block"] = block

    return payload


def maps_place_details(place_id: str, **_ignored: Any) -> dict:
    """Detail satu tempat dari place_id hasil maps_search."""
    place_id = (place_id or "").strip()

    if not place_id:
        return {"success": False, "tool": "maps_place_details", "error": "place_id wajib diisi."}

    result = get_maps_provider().lookup(place_id)

    if not result.success:
        return _fail("maps_place_details", result)

    raw = result.places[0]
    payload: dict[str, Any] = {
        "success": True, "tool": "maps_place_details",
        "place": _place_dict(raw, None), "note": MAPS_NOTE,
    }

    block = build_map_block(places=[raw])
    if block:
        payload["map_block"] = block

    return payload


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
            "Mencari tempat/bisnis/alamat di peta OpenStreetMap (rumah sakit, apotek, SPBU, ATM, "
            "restoran, masjid, dsb), termasuk berdasarkan nama (mis. 'rumah sakit al ihsan'). "
            "Set near_me=true untuk 'terdekat', 'dekat sini', 'di sekitarku' - hasil diurutkan dari "
            "jarak ke lokasi user. Tulis query SEPERTI YANG DIUCAPKAN user (jangan diubah/diterjemahkan). "
            "Kalau lokasi user belum presisi, tool otomatis menampilkan form izin lokasi (setelah itu "
            "JANGAN menulis apa pun lagi). Kalau user menolak izin, panggil ulang dengan "
            "allow_approximate=true. Untuk tempat di kota/daerah tertentu, sebut daerahnya di query "
            "dan biarkan near_me=false."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Apa yang dicari, mis. 'rumah sakit' atau 'SPBU Cimahi'."},
            "near_me": {"type": "boolean", "description": "True = cari di sekitar lokasi user.", "default": False},
            "radius": {"type": "integer", "description": "Radius meter untuk near_me (default 3000; melebar otomatis kalau mencari nama)."},
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
            "Menghitung rute di OpenStreetMap: jarak, durasi, dan langkah utama. Kosongkan origin "
            "untuk memakai lokasi user (form izin lokasi tampil otomatis kalau belum presisi). "
            "Bukan untuk traceroute jaringan."
        ),
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "Tujuan (nama tempat atau alamat)."},
            "origin": {"type": "string", "description": "Titik asal. Kosongkan = lokasi user."},
            "mode": {
                "type": "string", "description": "driving | walking | bicycling",
                "default": "driving",
            },
            "allow_approximate": {"type": "boolean", "default": False},
        }, "required": ["destination"]},
    }},
    {"type": "function", "function": {
        "name": "maps_place_details",
        "description": "Detail satu tempat berdasarkan place_id (mis. N123, W456) dari hasil maps_search.",
        "parameters": {"type": "object", "properties": {
            "place_id": {"type": "string"},
        }, "required": ["place_id"]},
    }},
]