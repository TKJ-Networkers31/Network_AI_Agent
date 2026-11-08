"""
agents/rei/maps_tools.py — peta/lokasi sebagai kemampuan chat AIRA.

Provider peta AKTIF (default OpenStreetMap) lewat get_maps_provider().
maps_route: rute + alternatif, plus avoid_via (hindari jalan yang ditutup/
diperbaiki), via_point (paksa lewat titik tertentu), dan
blocked_near_origin (user bilang "jalan di dekat sini diperbaiki" tanpa
menyebut nama jalan -> sistem menebak jalan dari langkah rute).

FIX (ronde 2):
  1. Rute alternatif: kalau OSRM tidak punya alternatif natural, sistem
     membuat JALUR MEMUTAR otomatis lewat titik perantara di kiri/kanan
     garis asal-tujuan, lalu memilih yang tidak melewati jalan bermasalah.
     Rute lama ikut ditampilkan di peta sebagai rute terblokir.
  2. Nama tempat: singkatan (SMPN/SMKN/SMAN/SDN/MTsN) diperluas dan dicari
     dengan bias lokasi user lalu tanpa bias, SEBELUM menghitung rute.
     Nama yang ditemukan dikembalikan (origin_resolved_as /
     destination_resolved_as) supaya LLM bisa mengonfirmasi ke user.
"""

import logging
import math
import re
from typing import Any, Optional
from urllib.parse import quote_plus

from agents.rei.dio_tools import request_location_permission, request_structured_input
from core.external_context import get_maps_provider
from core.external_context.map_block import build_map_block
from core.location import location_service
from core.location.models import SOURCE_BROWSER, SOURCE_MANUAL

logger = logging.getLogger("aira.rei.maps_tools")

MAX_PLACES = 5
DEFAULT_SEARCH_RADIUS_METERS = 3000
MAX_ROUTE_STEPS = 8
MAX_AUTO_AVOID_CANDIDATES = 3
DETOUR_OFFSETS_METERS = (300, 600, 1000)
DETOUR_MAX_VALID = 2
GEOCODE_BIAS_RADIUS_METERS = 15000
PRECISE_SOURCES = (SOURCE_BROWSER, SOURCE_MANUAL)
_HERE_WORDS = {
    "", "lokasi saya", "lokasiku", "posisiku", "posisi saya",
    "sini", "dari sini", "my location", "here", "lokasi saat ini", "lokasi sekarang",
}

# Pertanyaan tentang JALAN/RUTE salah kirim ke maps_search -> arahkan ke maps_route.
_ROUTE_INTENT_RE = re.compile(
    r"\b(rute|alternatif|ditutup|diperbaiki|perbaikan|macet|banjir|lewat mana|bypass|memutar)\b",
    re.IGNORECASE,
)
_STREET_QUERY_RE = re.compile(r"^\s*(jalan|jl\.?|jln\.?|ruas)\b", re.IGNORECASE)
_STREET_LIKE_RE = re.compile(r"^\s*(jalan|jl\.?|jln\.?|gang|gg\.?)\b", re.IGNORECASE)
_STREET_AFTER_KE_RE = re.compile(r"\bke\s+(.+)$", re.IGNORECASE)
_COORD_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")

# Singkatan nama sekolah/instansi yang di OSM biasanya ditulis lengkap.
_ABBREVIATIONS = (
    (re.compile(r"\bsmpn\b", re.IGNORECASE), "SMP Negeri"),
    (re.compile(r"\bsmkn\b", re.IGNORECASE), "SMK Negeri"),
    (re.compile(r"\bsman\b", re.IGNORECASE), "SMA Negeri"),
    (re.compile(r"\bsdn\b", re.IGNORECASE), "SD Negeri"),
    (re.compile(r"\bmtsn\b", re.IGNORECASE), "MTs Negeri"),
    (re.compile(r"\bsmk\s+(\d+)\b", re.IGNORECASE), r"SMK Negeri \1"),
    (re.compile(r"\bsmp\s+(\d+)\b", re.IGNORECASE), r"SMP Negeri \1"),
    (re.compile(r"\bsma\s+(\d+)\b", re.IGNORECASE), r"SMA Negeri \1"),
)

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

NOT_FOUND_HINT = (
    " Nama tempat tidak ketemu di OpenStreetMap. JANGAN langsung menyerah atau minta koordinat: "
    "panggil maps_route lagi dengan nama LEBIH LENGKAP + area/kelurahan yang disebut user "
    "(mis. 'SMP Negeri 3 Baleendah Rancamanyar'), minimal 2 variasi nama. Baru kalau tetap gagal, "
    "minta user menyebut landmark terdekat atau koordinat."
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
    return access is not None and (access.source in PRECISE_SOURCES or not session_id)


def _locate(session_id, allow_approximate, request_text, reason):
    """(access, permission_result). permission_result != None -> kembalikan apa adanya."""
    access = _current_location(session_id)

    logger.info(
        "MAPS | _locate session=%s source=%s has_coords=%s",
        session_id, getattr(access, "source", None), bool(access and access.has_coordinates()),
    )

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

    if code == "no_results" and tool == "maps_route":
        message += NOT_FOUND_HINT

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
    if place.distance_meters is not None:
        return place.distance_meters

    if origin is not None and place.latitude is not None and place.longitude is not None:
        return location_service._haversine(
            origin.latitude, origin.longitude, place.latitude, place.longitude,
        ) * 1000

    return float("inf")


# ------------------------------------------------ resolusi nama tempat

def _name_variants(text: str) -> list[str]:
    """Teks asli + versi dengan singkatan diperluas (unik, urut)."""
    original = " ".join((text or "").split())
    expanded = original

    for pattern, replacement in _ABBREVIATIONS:
        expanded = pattern.sub(replacement, expanded)

    variants: list[str] = []

    for candidate in (expanded, original):  # versi lengkap lebih dulu
        if candidate and candidate not in variants:
            variants.append(candidate)

    return variants


def _parse_coord(text: str) -> Optional[tuple[float, float]]:
    if not _COORD_RE.match(text or ""):
        return None

    lat, lon = (float(p) for p in text.split(","))
    return lat, lon


def _resolve_text(provider, text: str, bias: Optional[tuple[float, float]]):
    """
    Nama tempat -> ('lat,lon', nama_ditemukan). Koordinat dikembalikan apa
    adanya (label None). Gagal -> (text asli, None): provider yang akan
    melaporkan errornya.
    """
    text = (text or "").strip()

    if not text or _parse_coord(text) is not None:
        return text, None

    for variant in _name_variants(text):
        attempts = [True, False] if bias is not None else [False]

        for use_bias in attempts:
            params: dict[str, Any] = {}

            if use_bias:
                params["location"] = f"{bias[0]},{bias[1]}"
                params["radius"] = GEOCODE_BIAS_RADIUS_METERS

            try:
                result = provider.search(variant, **params)
            except Exception:
                logger.exception("MAPS | resolve '%s' gagal (diabaikan).", variant)
                continue

            if not result.success:
                continue

            for place in result.places:
                if place.latitude is not None and place.longitude is not None:
                    logger.info("MAPS | '%s' -> '%s' (query='%s', bias=%s)", text, place.name, variant, use_bias)
                    return f"{place.latitude},{place.longitude}", place.name

    return text, None


# ------------------------------------------------ rute alternatif

def _norm_street(text: str) -> str:
    t = re.sub(r"^(jalan|jl\.?|jln\.?)\s+", "", (text or "").strip().lower())
    return re.sub(r"[^\w\s]", "", t).strip()


def _street_names(route) -> list[str]:
    """Nama jalan berurutan dari langkah rute (instruksi berbentuk '... ke <nama>')."""
    names: list[str] = []

    for segment in getattr(route, "segments", None) or []:
        match = _STREET_AFTER_KE_RE.search(segment.instruction or "")

        if not match:
            continue

        name = match.group(1).strip()

        if name and name not in names:
            names.append(name)

    return names


def _offset_point(lat: float, lon: float, east_m: float, north_m: float) -> tuple[float, float]:
    dlat = north_m / 111320.0
    dlon = east_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _detour_waypoints(start: dict, end: dict) -> list[str]:
    """Titik perantara di kiri/kanan titik tengah garis asal-tujuan (OSRM menempelkannya ke jalan terdekat)."""
    lat1, lon1 = start["latitude"], start["longitude"]
    lat2, lon2 = end["latitude"], end["longitude"]

    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    cos_lat = max(0.2, math.cos(math.radians(mid_lat)))

    # arah asal->tujuan dalam meter (timur, utara)
    east = (lon2 - lon1) * 111320.0 * cos_lat
    north = (lat2 - lat1) * 111320.0
    length = math.hypot(east, north)

    if length < 1:
        return []

    perp_east, perp_north = -north / length, east / length

    points = []

    for offset in DETOUR_OFFSETS_METERS:
        for side in (1, -1):
            lat, lon = _offset_point(mid_lat, mid_lon, side * offset * perp_east, side * offset * perp_north)
            points.append(f"{lat:.5f},{lon:.5f}")

    return points


def _blocked_extra(base_result) -> dict:
    """Rute lama (yang melewati jalan bermasalah) dalam bentuk alternatif terblokir untuk peta."""
    route = base_result.route
    meta = route.metadata or {}

    return {
        "via": meta.get("via"),
        "distance_m": route.distance_meters,
        "duration_s": route.duration_seconds,
        "geometry": meta.get("geometry"),
        "uses_avoided": True,
    }


def _find_detour(provider, origin_text, destination, mode, street, base):
    """Coba jalur memutar lewat titik perantara otomatis. Return QueryResult atau None."""
    meta = base.route.metadata or {}
    start = meta.get("origin_resolved") or {}
    end = meta.get("destination_resolved") or {}

    if start.get("latitude") is None or end.get("latitude") is None:
        return None

    base_distance = base.route.distance_meters or 0
    limit = max(base_distance * 3, base_distance + 2000)

    valid = []

    for waypoint in _detour_waypoints(start, end):
        result = provider.route(
            origin_text, destination, mode=mode, alternatives=False,
            via_point=waypoint, avoid_via=street,
        )

        if not result.success or result.route is None:
            continue

        avoid = (result.route.metadata or {}).get("avoid") or {}
        distance = result.route.distance_meters or 0

        if avoid.get("found_alternative") and 0 < distance <= limit:
            valid.append(result)

            if len(valid) >= DETOUR_MAX_VALID:
                break

    if not valid:
        return None

    return min(valid, key=lambda r: r.route.distance_meters or float("inf"))


def _resolve_blocked_route(provider, origin_text, destination, mode, avoid_text):
    """
    Cari rute yang menghindari jalan bermasalah TANPA mewajibkan user menyebut
    nama jalan. Return (QueryResult, assumed_street | None, blocked_extras, detour_used).

    Urutan: (1) alternatif natural OSRM -> (2) jalur memutar otomatis lewat
    titik perantara -> (3) hasil jujur "tidak ada alternatif".
    """
    street_given = bool(avoid_text) and bool(_STREET_LIKE_RE.match(avoid_text))

    base = provider.route(origin_text, destination, mode=mode, alternatives=True)

    if not base.success or base.route is None:
        return base, None, [], False

    candidates = [avoid_text] if street_given else _street_names(base.route)[:MAX_AUTO_AVOID_CANDIDATES]

    if not candidates:
        return base, None, [], False

    first = None

    for street in candidates:
        result = provider.route(
            origin_text, destination, mode=mode, alternatives=True, avoid_via=street,
        )

        if not result.success or result.route is None:
            continue

        if first is None:
            first = (result, street)

        avoid = (result.route.metadata or {}).get("avoid") or {}

        if avoid.get("found_alternative"):
            return result, (None if street_given else street), [], False

    # Tidak ada alternatif natural -> jalur memutar otomatis untuk jalan yang dicurigai.
    suspect = candidates[0]
    detour = _find_detour(provider, origin_text, destination, mode, suspect, base)

    if detour is not None:
        return detour, (None if street_given else suspect), [_blocked_extra(base)], True

    if first is not None:
        return first[0], (None if street_given else first[1]), [], False

    return base, None, [], False


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

    # Guard: "jalan dekat X sedang diperbaiki / rute lain" BUKAN pencarian tempat.
    if _as_bool(near_me) and (_ROUTE_INTENT_RE.search(query) or _STREET_QUERY_RE.match(query)):
        return {
            "success": False, "tool": "maps_search", "error_code": "wrong_tool",
            "error": (
                "Ini pertanyaan tentang JALAN/RUTE, bukan pencarian tempat. Pakai maps_route dengan "
                "destination = tujuan awal user (ingat dari percakapan), alternatives=true. Kalau user "
                "menyebut nama jalan yang ditutup/diperbaiki (diawali Jalan/Jl.), isi avoid_via; kalau "
                "tidak ada nama jalan, isi blocked_near_origin=true. JANGAN bertanya nama jalan ke user "
                "dan JANGAN memanggil maps_search lagi."
            ),
        }

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

    provider = get_maps_provider()
    result = None

    # Coba nama asli, lalu singkatan diperluas (SMPN -> SMP Negeri).
    for variant in _name_variants(query):
        result = provider.search(variant, **params)

        if result.success and result.places:
            break

    if not result.success:
        return _fail("maps_search", result)

    raw_places = (
        sorted(result.places, key=lambda p: _distance_key(p, origin))
        if origin is not None else list(result.places)
    )
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
        origin_point = {"lat": origin.latitude, "lon": origin.longitude, "accuracy": origin.accuracy}
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
            f"Tidak ada hasil untuk '{query}'. Coba lagi dengan nama lebih lengkap + area yang disebut "
            "user. Kalau tetap kosong, sampaikan apa adanya. Jangan mengarang tempat."
        )

    return payload


def maps_route(
    destination: str = "",
    origin: Optional[str] = None,
    mode: str = "driving",
    allow_approximate: Any = False,
    alternatives: Any = True,
    avoid_via: Optional[str] = None,
    via_point: Optional[str] = None,
    blocked_near_origin: Any = False,
    session_id: Optional[str] = None,
    **_ignored: Any,
) -> dict:
    """Rute origin -> destination (+ alternatif, avoid_via, via_point, blocked_near_origin)."""
    destination = (destination or "").strip()

    # Tujuan kosong -> aktifkan DIO (form), jangan sekadar error.
    if not destination:
        return request_structured_input(
            intent="route_destination",
            missing_fields=[{
                "key": "destination", "label": "Tujuan", "data_type": "string",
                "placeholder": "mis. SMKN 2 Baleendah", "required": True,
            }],
            title="Mau ke mana?",
            description="Sebutkan tujuan supaya AIRA bisa mencarikan rute dari lokasimu.",
        )

    origin_text = (origin or "").strip()
    origin_label = origin_text
    approximate = False
    bias: Optional[tuple[float, float]] = None

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
        bias = (access.latitude, access.longitude)

    provider = get_maps_provider()

    # Titik acuan pencarian nama: lokasi user kalau ada (walau perkiraan).
    if bias is None:
        current = _current_location(session_id)
        if current is not None:
            bias = (current.latitude, current.longitude)

    # Resolusi nama tempat (singkatan diperluas + bias lokasi).
    origin_resolved_as = None
    if _parse_coord(origin_text) is None:
        origin_text, origin_resolved_as = _resolve_text(provider, origin_text, bias)
        if origin_resolved_as:
            coord = _parse_coord(origin_text)
            bias = coord or bias

    destination_arg, destination_resolved_as = _resolve_text(provider, destination, bias)

    mode = (mode or "driving").strip().lower()
    avoid_text = (avoid_via or "").strip()
    via_text = (via_point or "").strip()
    blocked_near = _as_bool(blocked_near_origin)
    want_alternatives = _as_bool(alternatives) or bool(avoid_text) or blocked_near

    assumed_street: Optional[str] = None
    blocked_extras: list = []
    detour_used = False

    if (blocked_near or avoid_text) and not via_text:
        result, assumed_street, blocked_extras, detour_used = _resolve_blocked_route(
            provider, origin_text, destination_arg, mode, avoid_text,
        )
    else:
        result = provider.route(
            origin_text, destination_arg, mode=mode, alternatives=want_alternatives,
            avoid_via=avoid_text or None, via_point=via_text or None,
        )

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

    raw_alts = list(meta.get("alternatives") or []) + blocked_extras
    alternatives_list = [
        {
            "via": alt.get("via"),
            "distance_km": round(alt["distance_m"] / 1000, 1) if alt.get("distance_m") is not None else None,
            "duration_minutes": round(alt["duration_s"] / 60) if alt.get("duration_s") is not None else None,
            **({"melewati_jalan_yang_dihindari": True} if alt.get("uses_avoided") else {}),
        }
        for alt in raw_alts
    ]

    avoid_info = meta.get("avoid")

    # ---- catatan untuk LLM
    if via_text:
        alt_note = (
            f"Rute ini DIPAKSA lewat titik '{via_text}' sesuai permintaan user. "
            "Jelaskan rute baru ini dan bandingkan singkat dengan rute sebelumnya kalau ada."
        )
    elif avoid_info:
        if avoid_info.get("found_alternative"):
            alt_note = (
                f"Rute ini SUDAH menghindari '{avoid_info['street']}'. Rute lama yang melewatinya "
                "ditampilkan di peta sebagai rute terblokir. Beri tahu bahwa data OSM tidak tahu "
                "status perbaikan jalan, jadi user perlu memastikan di lapangan."
            )
            if detour_used:
                alt_note += (
                    " Rute ini adalah JALUR MEMUTAR yang dibuat otomatis lewat titik perantara "
                    "(ditandai kuning di peta), bukan satu jalan bernama - jelaskan via/jarak/durasinya "
                    "dan bandingkan dengan rute lama."
                )
        else:
            alt_note = (
                f"SEMUA rute dan jalur memutar otomatis yang dicoba tetap melewati "
                f"'{avoid_info['street']}'. Katakan jujur bahwa tidak ada jalur lain yang ditemukan di "
                "data OSM. Tawarkan: user menyebut jalan yang ingin dilewati (via_point). "
                "JANGAN mengarang rute."
            )
    elif want_alternatives:
        alt_note = (
            "Rute alternatif SUDAH termasuk di hasil ini (field 'alternatives'). "
            + ("Bandingkan via/jarak/durasi tiap alternatif secara singkat."
               if alternatives_list else
               "Field 'alternatives' kosong: sampaikan bahwa tidak ada rute alternatif otomatis, lalu "
               "tawarkan via_point (jalan yang ingin dilewati user).")
        )
    else:
        alt_note = "Rute alternatif tidak diminta pada panggilan ini."

    if assumed_street:
        alt_note = (
            f"User tidak menyebut nama jalan, jadi sistem MENEBAK jalan yang bermasalah = "
            f"'{assumed_street}' (jalan terdekat dari titik awal rute). Sebutkan tebakan ini ke user "
            "dengan singkat dan minta koreksi kalau salah. " + alt_note
        )

    resolve_note = ""
    if origin_resolved_as or destination_resolved_as:
        parts = []
        if origin_resolved_as:
            parts.append(f"asal '{origin}' dikenali sebagai '{origin_resolved_as}'")
        if destination_resolved_as:
            parts.append(f"tujuan '{destination}' dikenali sebagai '{destination_resolved_as}'")
        resolve_note = (
            " Nama tempat dicocokkan otomatis: " + "; ".join(parts) + ". Sebutkan nama yang ditemukan "
            "dengan singkat supaya user bisa mengoreksi kalau salah tempat."
        )

    payload: dict[str, Any] = {
        "success": True, "tool": "maps_route",
        "origin": origin_label, "origin_approximate": approximate,
        "destination": destination, "mode": mode,
        "via": meta.get("via"),
        "distance_km": round(route.distance_meters / 1000, 1) if route.distance_meters is not None else None,
        "duration_minutes": round(route.duration_seconds / 60) if route.duration_seconds is not None else None,
        "steps": steps,
        "steps_truncated": len(route.segments) > MAX_ROUTE_STEPS,
        "alternatives": alternatives_list,
        "alternatives_available": bool(alternatives_list),
        "avoid": avoid_info,
        "note": (
            "Ringkas jarak & durasi, tampilkan langkah utama sebagai daftar, beri link "
            "[Buka di OpenStreetMap](maps_url) PERSIS dari hasil ini, lalu TEMPEL map_block "
            "PERSIS apa adanya di akhir jawaban (peta interaktif: bisa pilih rute, lihat langkah, "
            "klik peta untuk titik perantara). " + alt_note + resolve_note
        ),
    }

    if origin_resolved_as:
        payload["origin_resolved_as"] = origin_resolved_as
    if destination_resolved_as:
        payload["destination_resolved_as"] = destination_resolved_as
    if assumed_street:
        payload["assumed_blocked_street"] = assumed_street
    if detour_used:
        payload["detour_auto"] = True

    start = meta.get("origin_resolved") or {}
    end = meta.get("destination_resolved") or {}
    via_pt = meta.get("via_point_resolved") or {}

    payload["maps_url"] = meta.get("osm_url") or (
        f"https://www.openstreetmap.org/search?query={quote_plus(destination)}"
    )

    if start.get("latitude") is not None and end.get("latitude") is not None:
        routes_for_map = [{
            "via": meta.get("via"),
            "km": (route.distance_meters or 0) / 1000,
            "min": (route.duration_seconds or 0) / 60,
            "pts": meta.get("geometry"),
        }]
        for alt in raw_alts:
            routes_for_map.append({
                "via": alt.get("via"),
                "km": (alt.get("distance_m") or 0) / 1000,
                "min": (alt.get("duration_s") or 0) / 60,
                "pts": alt.get("geometry"),
                "blocked": alt.get("uses_avoided"),
            })

        block = build_map_block(
            origin={"lat": start["latitude"], "lon": start["longitude"]},
            destination={"lat": end["latitude"], "lon": end["longitude"], "name": destination},
            via=(
                {"lat": via_pt["latitude"], "lon": via_pt["longitude"]}
                if via_pt.get("latitude") is not None else None
            ),
            routes=routes_for_map,
            steps=[{"t": s.instruction, "m": s.distance_meters} for s in route.segments],
            avoid=(
                {"street": avoid_info["street"], "ok": avoid_info.get("found_alternative")}
                if avoid_info else None
            ),
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
            "Mencari TEMPAT/bisnis/alamat di OpenStreetMap (rumah sakit, apotek, SPBU, ATM, restoran, "
            "masjid, sekolah, dsb), termasuk berdasarkan nama. near_me=true untuk 'terdekat/dekat sini/di "
            "sekitarku'. JANGAN dipakai untuk pertanyaan rute atau jalan (rute lain, jalan ditutup/"
            "diperbaiki, lewat mana) - itu urusan maps_route. Tulis query SEPERTI YANG DIUCAPKAN user "
            "(singkatan SMPN/SMKN diperluas otomatis). "
            "Kalau lokasi user belum presisi, form izin lokasi tampil otomatis (setelah itu JANGAN "
            "menulis apa pun lagi). Kalau user menolak, ulangi dengan allow_approximate=true."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Apa yang dicari, mis. 'rumah sakit' atau 'SPBU Cimahi'."},
            "near_me": {"type": "boolean", "description": "True = cari di sekitar lokasi user.", "default": False},
            "radius": {"type": "integer", "description": "Radius meter untuk near_me (default 3000)."},
            "max_results": {"type": "integer", "description": "Jumlah hasil, maks 5.", "default": 5},
            "allow_approximate": {"type": "boolean", "default": False},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "maps_route",
        "description": (
            "Menghitung rute di OpenStreetMap: jarak, durasi, langkah, dan rute alternatif. Pakai tool "
            "ini (BUKAN maps_search) untuk SEMUA pertanyaan rute, termasuk rute antar dua tempat bernama "
            "(isi origin DAN destination dengan nama tempatnya - tool mencarinya sendiri, jangan "
            "memanggil maps_search dulu). "
            "JANGAN bertanya titik asal ke user: kalau user tidak menyebut asal, KOSONGKAN origin "
            "(otomatis memakai lokasi user; form izin lokasi tampil sendiri kalau belum presisi, "
            "setelah itu jangan menulis apa pun lagi). "
            "destination SELALU diisi tujuan user (ingat dari percakapan sebelumnya). "
            "Kalau nama tempat tidak ketemu, ulangi dengan nama lebih lengkap + area dari user "
            "(mis. 'SMP Negeri 3 Baleendah Rancamanyar') sebelum menyerah. "
            "Untuk rute alternatif/jalan bermasalah JANGAN bertanya nama jalan: "
            "kalau user menyebut nama jalan (diawali Jalan/Jl.) isi avoid_via; kalau user hanya bilang "
            "'jalan di dekat sini/dekat <tempat> diperbaiki' tanpa nama jalan, isi blocked_near_origin=true "
            "(sistem menebak jalan terdekat dari titik awal, mencari alternatif, dan kalau tidak ada "
            "membuat jalur memutar otomatis). Jalan yang ingin DILEWATI user -> via_point. "
            "Bukan untuk traceroute jaringan."
        ),
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "Tujuan (nama tempat atau alamat)."},
            "origin": {"type": "string", "description": "Titik asal (nama tempat/alamat). KOSONGKAN kalau user tidak menyebutnya = lokasi user."},
            "mode": {"type": "string", "description": "driving | walking | bicycling", "default": "driving"},
            "alternatives": {"type": "boolean", "description": "Sertakan rute alternatif.", "default": True},
            "avoid_via": {
                "type": "string",
                "description": "Nama jalan yang HARUS dihindari (ditutup/diperbaiki), mis. 'Jalan Adipati Agung'. Hanya kalau user menyebut nama jalannya.",
            },
            "blocked_near_origin": {
                "type": "boolean",
                "description": "True kalau user bilang jalan di dekat titik awal/lokasinya diperbaiki/ditutup/macet TANPA menyebut nama jalan.",
                "default": False,
            },
            "via_point": {
                "type": "string",
                "description": "Jalan/tempat yang HARUS dilewati rute, mis. 'Jalan Raya Baleendah'.",
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