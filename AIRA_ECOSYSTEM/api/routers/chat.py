"""
api/routers/chat.py

FIX (Optimalisasi DIO):
Endpoint /api/chat sekarang menangani dua jenis payload:
1. Chat teks biasa (dan slash command) - PERSIS seperti sebelumnya.
2. dio_submission - hasil user mengisi/menekan aksi pada form/pilihan
   interaktif yang dirender dari request_structured_input(). Efek
   sampingnya (simpan ke InteractionMemory + publish event lifecycle)
   dijalankan lewat agents.rei.dio_tools.submit_structured_input()
   SEBELUM Brain.think() dipanggil, supaya tetap tercatat apa pun yang
   LLM lakukan selanjutnya. interaction_schema dari hasil giliran ini
   (kalau LLM memanggil request_structured_input lagi, mis. untuk
   langkah wizard berikutnya) ikut dikembalikan & disimpan.
"""

from fastapi import APIRouter, HTTPException

from api.schemas import ChatRequest, ChatResponse, ResetRequest
from api.state import get_memory, persist_memory, drop_cache, add_global_usage, get_global_usage
from core.brain import Brain
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP
from agents.rei.dio_tools import submit_structured_input, build_submission_message

router = APIRouter(prefix="/api", tags=["chat"])


def _apply_slash_command(raw_message: str) -> str:
    if not raw_message.startswith("/"):
        return raw_message

    parts = raw_message[1:].split(" ", 1)
    tool_name = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not tool_name or tool_name not in AGENT_TOOL_MAP:
        return raw_message

    instruction = rest or f"Jalankan tool {tool_name}."

    return (
        f"[Instruksi eksplisit dari user: WAJIB gunakan tool "
        f"'{tool_name}' untuk memenuhi permintaan berikut. Ambil "
        f"argumen yang diperlukan dari konteks kalimat ini.]\n"
        f"{instruction}"
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    session_id = payload.session_id

    if not session_id or not store.get_session_row(session_id):
        session = store.create_session()
        session_id = session["id"]

    if payload.dio_submission:
        # Efek samping (InteractionMemory + event bus) dijalankan dulu,
        # terlepas dari apa yang LLM lakukan setelahnya.
        submit_structured_input(
            schema_id=payload.dio_submission.get("schema_id", ""),
            action_id=payload.dio_submission.get("action_id", ""),
            values=payload.dio_submission.get("values"),
            cancelled=bool(payload.dio_submission.get("cancelled")),
        )
        display_message, llm_message = build_submission_message(payload.dio_submission)
    else:
        display_message = payload.message.strip()
        llm_message = _apply_slash_command(display_message)

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