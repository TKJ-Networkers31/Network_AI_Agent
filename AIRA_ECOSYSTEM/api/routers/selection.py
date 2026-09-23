"""
api/routers/selection.py — REST endpoint tipis untuk Selection Intelligence
(Sprint 2.7 / W4). Pintu HTTP di atas core/selection/*; tidak ada logic di sini.

BELUM didaftarkan di api/main.py (lihat catatan integrasi di final report) -
mengikuti pola api/routers/settings.py.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.selection import (
    SelectionBuilder, build_action_request, get_selection_store,
)

router = APIRouter(prefix="/api/selection", tags=["selection"])


class CreateSelectionRequest(BaseModel):
    selected_text: str
    source_type: str = "message"
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    full_text: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None
    persist: bool = True


class ActionRequestPayload(BaseModel):
    action: str
    user_question: str = ""


@router.post("")
def create_selection(payload: CreateSelectionRequest):
    result = SelectionBuilder().build(
        selected_text=payload.selected_text,
        source_type=payload.source_type,
        message_id=payload.message_id,
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        full_text=payload.full_text,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
        metadata=payload.metadata,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail="; ".join(result.errors))

    if payload.persist:
        get_selection_store().save(result.selection)

    return result.to_dict()


@router.get("/{selection_id}")
def get_selection(selection_id: str):
    selection = get_selection_store().get(selection_id)

    if not selection:
        raise HTTPException(status_code=404, detail=f"Selection '{selection_id}' tidak ditemukan atau kedaluwarsa.")

    return selection.to_dict()


@router.post("/{selection_id}/actions")
def request_action(selection_id: str, payload: ActionRequestPayload):
    selection = get_selection_store().get(selection_id)

    if not selection:
        raise HTTPException(status_code=404, detail=f"Selection '{selection_id}' tidak ditemukan atau kedaluwarsa.")

    request, error = build_action_request(selection, payload.action, payload.user_question)

    if error:
        raise HTTPException(status_code=400, detail=error)

    return {
        **request.to_dict(),
        "llm_instruction": request.packet.to_llm_instruction(),
    }