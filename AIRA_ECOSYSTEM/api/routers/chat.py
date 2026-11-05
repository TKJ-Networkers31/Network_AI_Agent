"""
api/routers/chat.py

Endpoint /api/chat menangani:
1. Chat teks biasa (dan slash command lewat core/slash_commands.py).
2. dio_submission (form/pilihan interaktif, termasuk izin lokasi) lewat
   resolve_submission() - helper yang SAMA dengan WebSocket (ws.py),
   sehingga kedua jalur tidak bisa berbeda perilaku.
3. Token Quota accounting & Guest Access verification.
"""

from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from api.schemas import ChatRequest, ChatResponse, ResetRequest
from api.state import get_memory, persist_memory, drop_cache, add_global_usage, get_global_usage
from core.brain import Brain
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP
from core.slash_commands import apply_slash_command
from core.tenant.manager import IdentityManager
from core.tenant.token_quota_service import TokenQuotaService
from agents.rei.dio_tools import resolve_submission

router = APIRouter(prefix="/api", tags=["chat"])

_identity_mgr = IdentityManager()
_quota_service = TokenQuotaService()


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None),
):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    # 1. Identity Resolution & Guest Isolation
    user_id = None
    tenant_id = None
    is_guest = True
    guest_id = x_guest_id or "guest_anonymous"

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        ctx = _identity_mgr.validate_session_token(token)
        if ctx:
            user_id = ctx.user_id
            tenant_id = ctx.tenant_id
            is_guest = False

    # 2. Token Quota Pre-flight Verification
    has_quota, quota_msg, remaining = _quota_service.check_quota_available(
        user_id=user_id,
        tenant_id=tenant_id,
        estimated_tokens=50,
        is_guest=is_guest,
        guest_id=guest_id if is_guest else None,
    )
    if not has_quota:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "QUOTA_EXCEEDED",
                "code": "LOGIN_REQUIRED" if is_guest else "QUOTA_EXHAUSTED",
                "message": quota_msg,
                "remaining_tokens": remaining,
            },
        )

    # 3. Guest Action Guard (disallow mutating operations without account)
    if is_guest:
        restricted_patterns = [
            "deploy playbook",
            "run playbook",
            "reboot device",
            "delete interface",
            "save credentials",
            "configure bgp",
            "save device",
        ]
        low_msg = payload.message.lower()
        if any(rp in low_msg for rp in restricted_patterns):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "RESTRICTED_OPERATION",
                    "code": "LOGIN_REQUIRED",
                    "message": "Operasi otomatisasi atau konfigurasi perangkat memerlukan autentikasi akun. Silakan masuk atau buat akun untuk melanjutkan.",
                    "remaining_tokens": remaining,
                },
            )

    session_id = payload.session_id

    if not session_id or not store.get_session_row(session_id, user_id=user_id):
        session = store.create_session(user_id=user_id)
        session_id = session["id"]

    if payload.dio_submission:
        display_message, llm_message = resolve_submission(payload.dio_submission)
    else:
        display_message = payload.message.strip()
        llm_message = apply_slash_command(display_message, AGENT_TOOL_MAP)

    memory = get_memory(session_id)

    try:
        from core.events import event_scope
        with event_scope(session_id=session_id, user_id=user_id):
            brain = Brain(memory)
            result = brain.think(llm_message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    persist_memory(session_id, memory)
    add_global_usage(result.token_usage)

    # 4. Token Quota Consumption & Ledger Auditing
    usage = result.token_usage or {}
    p_tokens = usage.get("prompt_tokens", 50) or 50
    c_tokens = usage.get("completion_tokens", 100) or 100
    m_name = usage.get("model", "gemini-2.5-flash") or "gemini-2.5-flash"

    try:
        _quota_service.consume_tokens(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            model_name=m_name,
            input_tokens=p_tokens,
            output_tokens=c_tokens,
            cached_tokens=usage.get("cached_tokens", 0) or 0,
            is_guest=is_guest,
            guest_id=guest_id if is_guest else None,
        )
    except Exception as q_exc:
        import logging
        logging.getLogger("aira.chat").warning("Token consumption tracking warning: %s", q_exc)

    updated_quota = (
        _quota_service.get_guest_quota(guest_id)
        if is_guest
        else _quota_service.get_or_create_user_quota(user_id, tenant_id)
    )

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
        "quota": updated_quota.to_dict() if updated_quota else None,
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
