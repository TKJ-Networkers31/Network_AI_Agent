"""
api/routers/sessions.py — Chat Session Management with strict per-user isolation.
Mandatory authentication enforced: no anonymous/guest bypass.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import SessionRenameRequest
from api.state import drop_cache
from core import chat_sessions as store
from core.tenant.auth_deps import get_current_authenticated_user
from core.tenant.models import TenantContext
from core.tenant.manager import IdentityManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_identity_mgr = IdentityManager()


@router.get("")
def list_sessions(ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Lists all private chat sessions for the authenticated user."""
    return {"sessions": store.list_sessions(user_id=ctx.user_id)}


@router.post("")
def create_session(ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Creates a new private chat session scoped strictly to the authenticated user."""
    return store.create_session(user_id=ctx.user_id)


@router.get("/active")
def get_active_session(ctx: TenantContext = Depends(get_current_authenticated_user)):
    """
    Returns the most recently updated session for THIS user,
    or creates a new session scoped to this user if none exist.
    """
    sessions = store.list_sessions(user_id=ctx.user_id)
    if sessions:
        return sessions[0]
    return store.create_session(user_id=ctx.user_id)


@router.get("/{session_id}/messages")
def get_messages(
    session_id: str,
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    """Retrieves conversation turns for a session owned by the authenticated user."""
    if not store.get_session_row(session_id, user_id=ctx.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"turns": store.get_turns(session_id)}


@router.patch("/{session_id}")
def rename(
    session_id: str,
    payload: SessionRenameRequest,
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    """Renames a private session owned by the authenticated user."""
    title = (payload.title or "").strip() or "Chat baru"
    ok = store.rename_session(session_id, title, user_id=ctx.user_id)

    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"success": True, "title": title}


@router.delete("/{session_id}")
def delete(
    session_id: str,
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    """Deletes a private session owned by the authenticated user."""
    ok = store.delete_session(session_id, user_id=ctx.user_id)
    drop_cache(session_id)

    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"success": True}
