from fastapi import APIRouter, HTTPException

from backend.schemas import ChatRequest, ChatResponse, ResetRequest
from backend.state import get_session, reset_session
from agent.core.engine_web import run_web

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):

    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    session = get_session(payload.session_id or "default")

    try:
        result = run_web(payload.message, session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@router.post("/reset")
def reset(payload: ResetRequest):
    reset_session(payload.session_id or "default")
    return {"success": True}


@router.get("/token-usage")
def token_usage(session_id: str = "default"):
    session = get_session(session_id)
    return {
        "summary_line": session.token_tracker.summary_line(),
        "session_prompt_tokens": session.token_tracker.session_prompt_tokens,
        "session_completion_tokens": session.token_tracker.session_completion_tokens,
        "session_total_tokens": session.token_tracker.session_total_tokens,
    }
