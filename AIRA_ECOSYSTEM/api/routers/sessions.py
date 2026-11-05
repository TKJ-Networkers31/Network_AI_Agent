from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from api.schemas import SessionRenameRequest
from api.state import drop_cache
from core import chat_sessions as store
from core.tenant.manager import IdentityManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
_identity_mgr = IdentityManager()


def _resolve_user_id(authorization: Optional[str], x_guest_id: Optional[str]) -> str:
    """Resolves authenticated user ID or scoped guest ID for complete session isolation."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        ctx = _identity_mgr.validate_session_token(token)
        if ctx:
            return ctx.user_id
    if x_guest_id and x_guest_id.strip():
        return x_guest_id.strip()
    return "guest_sandbox"


@router.get("")
def list_sessions(
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    uid = _resolve_user_id(authorization, x_guest_id)
    return {"sessions": store.list_sessions(user_id=uid)}


@router.post("")
def create_session(
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    uid = _resolve_user_id(authorization, x_guest_id)
    return store.create_session(user_id=uid)


@router.get("/active")
def get_active_session(
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    """
    Returns the most recently updated session for THIS user/guest,
    or creates a new session scoped to this user/guest if none exist.
    """
    uid = _resolve_user_id(authorization, x_guest_id)
    sessions = store.list_sessions(user_id=uid)

    if sessions:
        return sessions[0]

    return store.create_session(user_id=uid)


@router.get("/{session_id}/messages")
def get_messages(
    session_id: str,
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    uid = _resolve_user_id(authorization, x_guest_id)
    if not store.get_session_row(session_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"turns": store.get_turns(session_id)}


@router.patch("/{session_id}")
def rename(
    session_id: str,
    payload: SessionRenameRequest,
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    uid = _resolve_user_id(authorization, x_guest_id)
    title = (payload.title or "").strip() or "Chat baru"
    ok = store.rename_session(session_id, title, user_id=uid)

    if not ok:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"success": True, "title": title}


@router.delete("/{session_id}")
def delete(
    session_id: str,
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
):
    uid = _resolve_user_id(authorization, x_guest_id)
    ok = store.delete_session(session_id, user_id=uid)
    drop_cache(session_id)

    if not ok:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan atau akses ditolak.")

    return {"success": True}
