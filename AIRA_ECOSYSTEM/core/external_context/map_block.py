"""
core/external_context/map_block.py — pembuat blok ```map yang ringkas & valid.

Dipakai tool maps_* (agents/rei/maps_tools.py) untuk mengisi field `map_block`.
JSON dibuat di sini (bukan oleh LLM): koordinat dibulatkan 5 desimal, rute
di-downsample, tempat dibatasi, tanpa spasi berlebih -> kecil dan tidak mudah
terpotong/rusak saat disalin LLM ke jawaban.
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Optional

MAX_PLACES = 10
MAX_ROUTE_POINTS = 150


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _point(value: Any) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    lat = _num(value.get("lat", value.get("latitude")))
    lon = _num(value.get("lon", value.get("longitude", value.get("lng"))))
    if lat is None or lon is None:
        return None
    out = {"lat": round(lat, 5), "lon": round(lon, 5)}
    accuracy = _num(value.get("accuracy"))
    if accuracy is not None:
        out["accuracy"] = round(accuracy)
    return out


def _downsample(points: list, limit: int) -> list:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[int(round(i * step))] for i in range(limit)]


def build_map_payload(
    origin: Optional[dict] = None,
    places: Optional[Iterable[Any]] = None,
    destination: Optional[dict] = None,
    route: Optional[Iterable[Any]] = None,
) -> dict:
    """places: NormalizedPlace atau dict ({name, latitude/lat, longitude/lon,
    distance_meters, metadata.osm_url}). route: [[lat, lon], ...]."""
    payload: dict[str, Any] = {}

    o = _point(origin)
    if o:
        payload["origin"] = o

    items = []
    for place in places or []:
        data = place.to_dict() if hasattr(place, "to_dict") else (place if isinstance(place, dict) else {})
        point = _point(data)
        if not point:
            continue
        entry = {"name": str(data.get("name") or "Tempat")[:80], **point}
        distance = _num(data.get("distance_meters"))
        if distance is not None:
            entry["km"] = round(distance / 1000, 2)
        url = (data.get("metadata") or {}).get("osm_url") or data.get("url")
        if isinstance(url, str) and url.startswith("http"):
            entry["url"] = url
        items.append(entry)
        if len(items) >= MAX_PLACES:
            break
    if items:
        payload["places"] = items

    d = _point(destination)
    if d:
        payload["destination"] = d

    line = []
    for p in route or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            lat, lon = _num(p[0]), _num(p[1])
            if lat is not None and lon is not None:
                line.append([round(lat, 5), round(lon, 5)])
    if len(line) > 1:
        payload["route"] = _downsample(line, MAX_ROUTE_POINTS)

    return payload


def build_map_block(**kwargs) -> str:
    """Kembalikan blok berpagar ```map siap tempel. '' kalau tidak ada data."""
    payload = build_map_payload(**kwargs)
    if not payload:
        return ""
    return "```map\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n```"