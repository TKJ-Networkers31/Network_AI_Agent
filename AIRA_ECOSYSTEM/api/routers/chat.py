"""
api/routers/chat.py

Endpoint /api/chat menangani:
1. Chat teks biasa (dan slash command lewat core/slash_commands.py).
2. dio_submission (form/pilihan interaktif, termasuk izin lokasi) lewat
   resolve_submission() - helper yang SAMA dengan WebSocket (ws.py),
   sehingga kedua jalur tidak bisa berbeda perilaku.
"""

from fastapi import APIRouter, HTTPException

from api.schemas import ChatRequest, ChatResponse, ResetRequest
from api.state import get_memory, persist_memory, drop_cache, add_global_usage, get_global_usage
from core.brain import Brain
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP
from core.slash_commands import apply_slash_command
from agents.rei.dio_tools import resolve_submission

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    session_id = payload.session_id

    if not session_id or not store.get_session_row(session_id):
        session = store.create_session()
        session_id = session["id"]

    if payload.dio_submission:
        display_message, llm_message = resolve_submission(payload.dio_submission)
    else:
        display_message = payload.message.strip()
        llm_message = apply_slash_command(display_message, AGENT_TOOL_MAP)

    memory = get_memory(session_id)

    try:
        brain = Brain(memory)
        result = brain.think(llm_message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    persist_memory(session_id, memory)
    add_global_usage(result.token_usage)

    store.add_turn(session_id, "user", display_message)
    store.add_turn(
        session_id, "assistant", result.answer,
        steps=result.steps, interaction_schema=result.interaction_schema,
    )
    store.maybe_autotitle(session_id, display_message)

    row = store.get_session_row(session_id)

    return {
        "answer": result.answer,
        "steps": result.steps,
        "duration": result.duration,
        "token_usage": result.token_usage,
        "error": result.error,
        "session_id": session_id,
        "session_title": row["title"] if row else "Chat baru",
        "interaction_schema": result.interaction_schema,
    }


@router.post("/reset")
def reset(payload: ResetRequest):
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id wajib diisi.")

    store.save_raw_history(payload.session_id, [])
    drop_cache(payload.session_id)

    return {"success": True}


@router.get("/token-usage")
def token_usage():
    return get_global_usage()