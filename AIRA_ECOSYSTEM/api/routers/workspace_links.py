"""
api/routers/workspace_links.py — REST endpoint tipis untuk Workspace
Integration (Sprint 2.7 / Wave 2 / W6).

Murni "pintu HTTP" di atas core/workspace_links/service.py - tidak ada
logic ownership/lifecycle di sini, mengikuti pola api/routers/files.py dan
api/routers/attachments.py.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.workspace_links import get_workspace_integration_service

router = APIRouter(prefix="/api/workspace/links", tags=["workspace-integration"])


class SaveConversationFileRequest(BaseModel):
    session_id: str
    relative_path: str
    content: str = ""
    message_id: Optional[str] = None
    note: Optional[str] = None


class AdoptWorkspaceFileRequest(BaseModel):
    session_id: str
    relative_path: str
    message_id: Optional[str] = None
    note: Optional[str] = None


def _raise_for_errors(errors: list[str]) -> None:
    raise HTTPException(status_code=400, detail="; ".join(errors) or "Permintaan tidak valid.")


@router.post("")
def save_conversation_file(payload: SaveConversationFileRequest):
    """conversation -> workspace: tulis konten baru ke Workspace dan catat
    kepemilikan sesi."""
    result = get_workspace_integration_service().save_conversation_file(
        session_id=payload.session_id, relative_path=payload.relative_path,
        content=payload.content, message_id=payload.message_id, note=payload.note,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.post("/adopt")
def adopt_workspace_file(payload: AdoptWorkspaceFileRequest):
    """conversation -> workspace: klaim kepemilikan file yang SUDAH ada di
    Workspace, tanpa menulis ulang isinya."""
    result = get_workspace_integration_service().adopt_workspace_file(
        session_id=payload.session_id, relative_path=payload.relative_path,
        message_id=payload.message_id, note=payload.note,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.get("")
def list_session_links(session_id: str = Query(...)):
    """workspace -> conversation: semua path yang terhubung ke satu sesi,
    digabung dari conversation link, artifact, dan attachment."""
    links = get_workspace_integration_service().list_for_session(session_id)
    return {"links": [link.to_dict() for link in links]}


@router.get("/owner")
def get_owner(path: str = Query(...)):
    """workspace -> conversation: sesi mana (kalau ada) yang memiliki path
    ini - dicek lewat conversation link dulu, lalu artifact, lalu attachment."""
    owner = get_workspace_integration_service().resolve_owner(path)

    if owner is None:
        raise HTTPException(status_code=404, detail=f"Path '{path}' tidak memiliki pemilik sesi.")

    return owner.to_dict()


@router.delete("")
def release_link(path: str = Query(...)):
    """Hapus conversation link untuk satu path (tidak menyentuh kepemilikan
    artifact/attachment - itu ranah engine masing-masing)."""
    removed = get_workspace_integration_service().release(path)
    return {"success": True, "removed": removed}