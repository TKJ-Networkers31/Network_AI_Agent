"""
api/routers/voice.py — REST endpoint resmi untuk Background Voice Service (YUKI).

Menyediakan kontrol siklus hidup (start, stop, pause, resume) dan observabilitas
status perangkat audio host dan STT engine.
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from agents.yuki.service import get_voice_service

logger = logging.getLogger("aira.api.voice")

router = APIRouter(prefix="/api/voice", tags=["voice"])


class PauseRequest(BaseModel):
    reason: Optional[str] = "manual"


@router.get("/service/status")
def get_service_status():
    """Mengembalikan status detail operasional layanan suara latar belakang."""
    svc = get_voice_service()
    return svc.get_status()


@router.post("/service/start")
def start_service():
    """Memulai penangkapan suara latar belakang pada perangkat host."""
    svc = get_voice_service()
    res = svc.start()
    status = svc.get_status()
    return {**res, "status": status}


@router.post("/service/stop")
def stop_service():
    """Menghentikan penangkapan suara latar belakang dan melepas stream PortAudio."""
    svc = get_voice_service()
    res = svc.stop()
    status = svc.get_status()
    return {**res, "status": status}


@router.post("/service/pause")
def pause_service(payload: Optional[PauseRequest] = None):
    """Menjeda sementara penangkapan mikrofon host (mis. saat Chat Speech PWA aktif)."""
    svc = get_voice_service()
    reason = payload.reason if payload and payload.reason else "manual"
    res = svc.pause(reason=reason)
    return {**res, "status": svc.get_status()}


@router.post("/service/resume")
def resume_service():
    """Melanjutkan kembali penangkapan mikrofon host setelah jeda selesai."""
    svc = get_voice_service()
    res = svc.resume()
    return {**res, "status": svc.get_status()}
