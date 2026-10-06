"""
core/external_context/map_block.py — pembuat blok ```map yang ringkas & valid.

Dipakai tool maps_* (agents/rei/maps_tools.py) untuk field `map_block`.
JSON dibuat di sini (bukan oleh LLM): koordinat 5 desimal, rute di-downsample,
tempat dibatasi, tanpa spasi -> kecil dan tidak mudah rusak saat disalin LLM.

Bentuk payload:
  origin, destination{lat,lon,name?}, via{lat,lon}, places[],
  routes[{via,km,min,pts,alt,blocked}]  (utama dulu, lalu alternatif),
  route (alias lama = pts rute utama), steps[{t,m}], avoid{street,ok}
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Optional

MAX_PLACES = 10
MAX_ROUTES = 3
MAX_ROUTE_POINTS = 90
MAX_ALT_POINTS = 60
MAX_STEPS = 12


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
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()[:80]
    return out


def _downsample(points: list, limit: int) -> list:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[int(round(i * step))] for i in range(limit)]


def _line(raw: Any, limit: int) -> list:
    line = []
    for p in raw or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            lat, lon = _num(p[0]), _num(p[1])
            if lat is not None and lon is not None:
                line.append([round(lat, 5), round(lon, 5)])
    return _downsample(line, limit) if len(line) > 1 else []


def build_map_payload(
    origin: Optional[dict] = None,
    places: Optional[Iterable[Any]] = None,
    destination: Optional[dict] = None,
    route: Optional[Iterable[Any]] = None,
    routes: Optional[Iterable[dict]] = None,
    via: Optional[dict] = None,
    steps: Optional[Iterable[dict]] = None,
    avoid: Optional[dict] = None,
) -> dict:
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
        entry = {"name": str(data.get("name") or "Tempat")[:80], "lat": point["lat"], "lon": point["lon"]}
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

    v = _point(via)
    if v:
        payload["via"] = v

    route_items = []
    for index, r in enumerate(list(routes or [])[:MAX_ROUTES]):
        if not isinstance(r, dict):
            continue
        pts = _line(r.get("pts"), MAX_ROUTE_POINTS if index == 0 else MAX_ALT_POINTS)
        if not pts:
            continue
        item: dict[str, Any] = {"via": str(r.get("via") or "")[:60], "pts": pts, "alt": index > 0}
        km, minutes = _num(r.get("km")), _num(r.get("min"))
        if km is not None:
            item["km"] = round(km, 1)
        if minutes is not None:
            item["min"] = round(minutes)
        if r.get("blocked"):
            item["blocked"] = True
        route_items.append(item)

    if route_items:
        payload["routes"] = route_items
        payload["route"] = route_items[0]["pts"]  # alias lama
    else:
        line = _line(route, MAX_ROUTE_POINTS)
        if line:
            payload["route"] = line

    step_items = []
    for s in list(steps or [])[:MAX_STEPS]:
        if isinstance(s, dict) and s.get("t"):
            entry = {"t": str(s["t"])[:80]}
            meters = _num(s.get("m"))
            if meters is not None:
                entry["m"] = round(meters)
            step_items.append(entry)
    if step_items:
        payload["steps"] = step_items

    if isinstance(avoid, dict) and avoid.get("street"):
        payload["avoid"] = {"street": str(avoid["street"])[:60], "ok": bool(avoid.get("ok"))}

    return payload


def build_map_block(**kwargs) -> str:
    """Blok berpagar ```map siap tempel. '' kalau tidak ada data."""
    payload = build_map_payload(**kwargs)
    if not payload:
        return ""
    return "```map\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n```"