"""
api/routers/location.py — REST endpoint lokasi hosting & lokasi akses.
Pintu HTTP tipis di atas core/location/service.py.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.location import location_service
from core.location.geo import extract_client_ip
from core.location.models import LocationContext, ROLE_ACCESS, SOURCE_BROWSER

router = APIRouter(prefix="/api/location", tags=["location"])


def _client_ip(request: Request) -> Optional[str]:
    return extract_client_ip(request.headers, request.client.host if request.client else None)


class AccessReportRequest(BaseModel):
    session_id: str
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None
    timestamp: Optional[float] = None


class HostUpdateRequest(BaseModel):
    query: Optional[str] = None
    label: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


@router.get("")
def get_location(request: Request, session_id: str = Query(...)):
    """Snapshot: lokasi hosting + lokasi akses sesi ini + hubungan keduanya."""
    location_service.observe_client(session_id, _client_ip(request))
    return location_service.snapshot(session_id)


@router.post("")
def report_access(payload: AccessReportRequest, request: Request):
    """
    Dipanggil frontend tiap sesi aktif berganti. Tanpa koordinat -> hanya
    mencatat IP klien (lokasi berbasis jaringan/IP). Dengan koordinat ->
    lokasi presisi dari GPS browser.
    """
    ip = _client_ip(request)
    location_service.observe_client(payload.session_id, ip)

    has_lat = payload.latitude is not None
    has_lon = payload.longitude is not None

    if has_lat != has_lon:
        raise HTTPException(status_code=400, detail="latitude dan longitude harus dikirim berpasangan.")

    if has_lat and has_lon:
        location_service.update_access(
            payload.session_id,
            LocationContext(
                role=ROLE_ACCESS, latitude=payload.latitude, longitude=payload.longitude,
                accuracy=payload.accuracy, altitude=payload.altitude,
                heading=payload.heading, speed=payload.speed,
                source=SOURCE_BROWSER, ip=ip, timestamp=payload.timestamp,
            ),
            ip=ip,
        )

    return location_service.snapshot(payload.session_id)


@router.delete("/access")
def clear_access(session_id: str = Query(...)):
    location_service.clear_access(session_id)
    return location_service.snapshot(session_id)


@router.get("/host")
def get_host():
    host = location_service.get_host()
    return {"host": host.to_dict() if host else None}


@router.put("/host")
def set_host(payload: HostUpdateRequest):
    result = location_service.set_host(
        query=payload.query, latitude=payload.latitude,
        longitude=payload.longitude, label=payload.label,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/host/detect")
def detect_host():
    result = location_service.detect_host()

    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error"))

    return result