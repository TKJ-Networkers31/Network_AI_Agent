"""
api/routers/connections.py — REST endpoint untuk AKANE Persistent
Connection Engine (Phase 2.2).

Murni pintu HTTP tipis di atas agents/akane/connection_manager.py. TIDAK
mengimpor tools/ssh langsung (aturan keras: api/ tidak boleh menyentuh
tools/* sama sekali).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.akane.connection_manager import get_connection_manager

router = APIRouter(prefix="/api/connections", tags=["connections"])


class OpenConnectionRequest(BaseModel):
    host: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
    device_name: Optional[str] = None


class CloseConnectionRequest(BaseModel):
    session_id: str


class ExecuteCommandRequest(BaseModel):
    session_id: str
    command: str


@router.get("")
def list_connections():
    manager = get_connection_manager()
    return {"connections": manager.list_sessions()}


@router.get("/{session_id}")
def get_connection(session_id: str):
    manager = get_connection_manager()
    session = manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' tidak ditemukan.")

    return session


@router.post("/open")
def open_connection(payload: OpenConnectionRequest):
    manager = get_connection_manager()

    if payload.device_name and not payload.host:
        result = manager.open_connection_for_device(payload.device_name)
    else:
        if not payload.host or not payload.username:
            raise HTTPException(status_code=400, detail="host dan username wajib diisi (atau isi device_name).")

        result = manager.open_connection(
            host=payload.host,
            username=payload.username,
            password=payload.password,
            port=payload.port,
            device_name=payload.device_name,
        )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/close")
def close_connection(payload: CloseConnectionRequest):
    manager = get_connection_manager()
    result = manager.close_connection(payload.session_id, reason="manual")

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.post("/execute")
def execute_command(payload: ExecuteCommandRequest):
    manager = get_connection_manager()
    result = manager.execute(payload.session_id, payload.command)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result