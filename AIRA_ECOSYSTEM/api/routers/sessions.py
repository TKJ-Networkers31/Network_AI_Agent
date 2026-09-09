from fastapi import APIRouter, HTTPException

from api.schemas import SessionRenameRequest
from api.state import drop_cache
from core import chat_sessions as store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
def list_sessions():
    return {"sessions": store.list_sessions()}


@router.post("")
def create_session():
    return store.create_session()


@router.get("/{session_id}/messages")
def get_messages(session_id: str):
    if not store.get_session_row(session_id):
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")

    return {"turns": store.get_turns(session_id)}


@router.patch("/{session_id}")
def rename(session_id: str, payload: SessionRenameRequest):
    title = (payload.title or "").strip() or "Chat baru"
    ok = store.rename_session(session_id, title)

    if not ok:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")

    return {"success": True, "title": title}


@router.delete("/{session_id}")
def delete(session_id: str):
    ok = store.delete_session(session_id)
    drop_cache(session_id)

    if not ok:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")

    return {"success": True}
