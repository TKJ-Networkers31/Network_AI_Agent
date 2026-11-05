"""
AIRA OS — Personalization & Privacy Data API Router (Phase F).
Handles:
- Memory Management (CRUD, search, summary, clear, toggle)
- Persona Management (Built-in presets, custom personas, active persona, duplication, preview)
- Privacy & Data Management (Overview, export JSON, delete conversations, clear memories, delete personas)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext
from core.tenant.memory_service import UserMemoryService
from core.tenant.persona_service import UserPersonaService
from core import chat_sessions as session_store

router = APIRouter(prefix="/api/v1/personalization", tags=["personalization"])

_id_mgr = IdentityManager()
_memory_svc = UserMemoryService()
_persona_svc = UserPersonaService()


def get_current_user_context(authorization: Optional[str] = Header(None)) -> TenantContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi diperlukan. Silakan masuk terlebih dahulu.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    ctx = _id_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi tidak valid atau telah kedaluwarsa.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class MemoryCreateRequest(BaseModel):
    category: str = Field("general", description="learning, technical, project, communication, workflows, general")
    content: str = Field(..., min_length=2, max_length=2000)
    source: str = "USER"
    importance: float = Field(0.5, ge=0.0, le=100.0)
    metadata: Optional[Dict[str, Any]] = None


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_enabled: Optional[bool] = None


class PreferencesUpdateRequest(BaseModel):
    memory_enabled: Optional[bool] = None
    active_persona_id: Optional[str] = None
    custom_instructions: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class MemoryToggleRequest(BaseModel):
    enabled: bool


class PersonaCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str = ""
    response_style: str = "concise"
    language: str = "id"
    technical_depth: int = Field(80, ge=1, le=100)
    explanation_preference: str = "technical"
    custom_instructions: str = ""


class PersonaUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    response_style: Optional[str] = None
    language: Optional[str] = None
    technical_depth: Optional[int] = None
    explanation_preference: Optional[str] = None
    custom_instructions: Optional[str] = None


class ActivePersonaRequest(BaseModel):
    persona_id: str


class DuplicatePersonaRequest(BaseModel):
    new_name: Optional[str] = None


# -----------------------------------------------------------------------------
# 1. Memory Management Endpoints
# -----------------------------------------------------------------------------

@router.get("/memory/summary")
@router.get("/memories/summary")
def get_memory_summary(ctx: TenantContext = Depends(get_current_user_context)):
    """Provides categorized memory metrics for the current user."""
    return _memory_svc.get_memory_summary(ctx.user_id)


@router.get("/memory")
@router.get("/memories")
def list_memories(
    category: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: TenantContext = Depends(get_current_user_context),
):
    """Lists isolated memories belonging to the authenticated user."""
    memories = _memory_svc.list_memories(ctx.user_id, category=category, query=query, limit=limit)
    return {"success": True, "memories": memories, "count": len(memories)}


@router.post("/memory")
@router.post("/memories")
def add_memory(payload: MemoryCreateRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Creates a new isolated memory entry."""
    imp = float(payload.importance)
    if imp > 1.0:
        imp = imp / 100.0
    mem = _memory_svc.add_memory(
        user_id=ctx.user_id,
        category=payload.category,
        content=payload.content,
        source=payload.source,
        importance=imp,
        metadata=payload.metadata,
    )
    return {"success": True, "memory": mem}


@router.get("/preferences")
def get_preferences(ctx: TenantContext = Depends(get_current_user_context)):
    """Retrieves user personalization preferences."""
    prefs = _memory_svc.get_or_create_user_preferences(ctx.user_id)
    return {"success": True, "preferences": prefs}


@router.put("/preferences")
@router.patch("/preferences")
def update_preferences(payload: PreferencesUpdateRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Updates user personalization preferences."""
    if payload.memory_enabled is not None:
        _memory_svc.set_memory_enabled(ctx.user_id, payload.memory_enabled)
    if payload.active_persona_id is not None:
        _persona_svc.set_active_persona(ctx.user_id, payload.active_persona_id)
    prefs = _memory_svc.get_or_create_user_preferences(ctx.user_id)
    return {"success": True, "preferences": prefs}


@router.post("/memory/toggle")
@router.post("/memories/toggle")
def toggle_memory(payload: MemoryToggleRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Enables or disables long-term AI memory for the user."""
    _memory_svc.set_memory_enabled(ctx.user_id, payload.enabled)
    return {"success": True, "memory_enabled": payload.enabled}


@router.get("/memory/{memory_id}")
@router.get("/memories/{memory_id}")
def get_memory(memory_id: str, ctx: TenantContext = Depends(get_current_user_context)):
    """Retrieves a single memory verifying user ownership."""
    mem = _memory_svc.get_memory(memory_id, ctx.user_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memori tidak ditemukan.")
    return mem


@router.patch("/memory/{memory_id}")
@router.patch("/memories/{memory_id}")
@router.put("/memory/{memory_id}")
@router.put("/memories/{memory_id}")
def update_memory(memory_id: str, payload: MemoryUpdateRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Updates memory content or classification verifying user ownership."""
    updated = _memory_svc.update_memory(
        memory_id=memory_id,
        user_id=ctx.user_id,
        content=payload.content,
        category=payload.category,
        importance=payload.importance,
        is_enabled=payload.is_enabled,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Memori tidak ditemukan atau akses ditolak.")
    return {"success": True, "memory": updated}


@router.delete("/memory/{memory_id}")
@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, ctx: TenantContext = Depends(get_current_user_context)):
    """Deletes an individual memory verifying user ownership."""
    ok = _memory_svc.delete_memory(memory_id, ctx.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memori tidak ditemukan atau akses ditolak.")
    return {"success": True, "message": "Memori berhasil dihapus."}


@router.delete("/memory")
@router.delete("/memories")
def clear_all_memories(ctx: TenantContext = Depends(get_current_user_context)):
    """Clears all memories belonging to the user."""
    count = _memory_svc.clear_all_memories(ctx.user_id)
    return {"success": True, "deleted_count": count, "message": f"{count} memori berhasil dibersihkan."}


# -----------------------------------------------------------------------------
# 2. Persona Management Endpoints
# -----------------------------------------------------------------------------

@router.get("/persona")
@router.get("/personas")
def list_personas(ctx: TenantContext = Depends(get_current_user_context)):
    """Lists built-in system presets and the user's custom personas."""
    return _persona_svc.list_personas_for_user(ctx.user_id)


@router.get("/persona/active")
@router.get("/personas/active")
def get_active_persona(ctx: TenantContext = Depends(get_current_user_context)):
    """Retrieves the active persona for the user."""
    persona = _persona_svc.get_active_persona(ctx.user_id)
    preview = _persona_svc.preview_persona_prompt(persona)
    return {"active_persona": persona, "preview": preview}


@router.post("/persona/active")
@router.post("/personas/active")
def set_active_persona(payload: ActivePersonaRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Switches the active persona for the user."""
    try:
        _persona_svc.set_active_persona(ctx.user_id, payload.persona_id)
        return {"success": True, "active_persona_id": payload.persona_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/persona")
@router.post("/personas")
def create_custom_persona(payload: PersonaCreateRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Creates a new custom persona owned exclusively by the user."""
    persona = _persona_svc.create_custom_persona(
        user_id=ctx.user_id,
        name=payload.name,
        description=payload.description,
        response_style=payload.response_style,
        language=payload.language,
        technical_depth=payload.technical_depth,
        explanation_preference=payload.explanation_preference,
        custom_instructions=payload.custom_instructions,
    )
    return {"success": True, "persona": persona}


@router.get("/persona/{persona_id}")
@router.get("/personas/{persona_id}")
def get_persona(persona_id: str, ctx: TenantContext = Depends(get_current_user_context)):
    """Retrieves persona details and prompt preview."""
    persona = _persona_svc.get_persona(persona_id, ctx.user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona tidak ditemukan atau akses ditolak.")
    preview = _persona_svc.preview_persona_prompt(persona)
    return {"persona": persona, "preview": preview}


@router.get("/persona/{persona_id}/preview")
@router.get("/personas/{persona_id}/preview")
def preview_persona(persona_id: str, ctx: TenantContext = Depends(get_current_user_context)):
    """Retrieves prompt preview formatted for system prompt injection."""
    persona = _persona_svc.get_persona(persona_id, ctx.user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona tidak ditemukan atau akses ditolak.")
    preview = _persona_svc.preview_persona_prompt(persona)
    return {"success": True, "prompt_preview": preview}


@router.post("/persona/{persona_id}/duplicate")
@router.post("/personas/{persona_id}/duplicate")
def duplicate_persona(
    persona_id: str,
    payload: Optional[DuplicatePersonaRequest] = None,
    new_name: Optional[str] = Query(None),
    ctx: TenantContext = Depends(get_current_user_context),
):
    """Duplicates an existing preset or custom persona into a user custom persona."""
    target_name = None
    if payload and payload.new_name:
        target_name = payload.new_name
    elif new_name:
        target_name = new_name
    try:
        persona = _persona_svc.duplicate_persona(persona_id, ctx.user_id, target_name)
        return {"success": True, "persona": persona}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/persona/{persona_id}")
@router.patch("/personas/{persona_id}")
@router.put("/persona/{persona_id}")
@router.put("/personas/{persona_id}")
def update_custom_persona(persona_id: str, payload: PersonaUpdateRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Updates a user custom persona. System presets cannot be edited."""
    try:
        updated = _persona_svc.update_custom_persona(
            persona_id=persona_id,
            user_id=ctx.user_id,
            name=payload.name,
            description=payload.description,
            response_style=payload.response_style,
            language=payload.language,
            technical_depth=payload.technical_depth,
            explanation_preference=payload.explanation_preference,
            custom_instructions=payload.custom_instructions,
        )
        return {"success": True, "persona": updated}
    except PermissionError as p_err:
        raise HTTPException(status_code=403, detail=str(p_err))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/persona/{persona_id}")
@router.delete("/personas/{persona_id}")
def delete_custom_persona(persona_id: str, ctx: TenantContext = Depends(get_current_user_context)):
    """Deletes a custom persona. System presets cannot be deleted."""
    try:
        ok = _persona_svc.delete_custom_persona(persona_id, ctx.user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Persona tidak ditemukan atau akses ditolak.")
        return {"success": True, "message": "Persona kustom berhasil dihapus."}
    except PermissionError as p_err:
        raise HTTPException(status_code=403, detail=str(p_err))


# -----------------------------------------------------------------------------
# 3. Privacy & Personal Data Management Endpoints (Section 5.1)
# -----------------------------------------------------------------------------

@router.get("/data/overview")
def get_personal_data_overview(ctx: TenantContext = Depends(get_current_user_context)):
    """Provides comprehensive overview of all data stored for this user."""
    sessions = session_store.list_sessions(ctx.user_id)
    mem_summary = _memory_svc.get_memory_summary(ctx.user_id)
    personas_info = _persona_svc.list_personas_for_user(ctx.user_id)

    return {
        "user_id": ctx.user_id,
        "username": ctx.username,
        "conversations_count": len(sessions),
        "memories_count": mem_summary.get("total_memories", 0),
        "custom_personas_count": len(personas_info.get("custom_personas", [])),
    }


@router.get("/data/export")
def export_personal_data(ctx: TenantContext = Depends(get_current_user_context)):
    """Exports full JSON payload of all personal data owned by this user."""
    sessions = session_store.list_sessions(ctx.user_id)
    full_sessions = []
    for s in sessions:
        sid = s["id"]
        turns = session_store.get_turns(sid)
        full_sessions.append({
            "session_id": sid,
            "title": s["title"],
            "created_at": s["created_at"],
            "messages": turns,
        })

    memories = _memory_svc.list_memories(ctx.user_id, limit=500)
    personas_info = _persona_svc.list_personas_for_user(ctx.user_id)
    prefs = _memory_svc.get_or_create_user_preferences(ctx.user_id)

    export_payload = {
        "user": {
            "user_id": ctx.user_id,
            "username": ctx.username,
            "tenant_id": ctx.tenant_id,
        },
        "export_metadata": {
            "platform": "AIRA OS",
            "version": "Phase F",
            "user_id": ctx.user_id,
            "username": ctx.username,
            "exported_at": _memory_svc.get_or_create_user_preferences(ctx.user_id)["updated_at"],
        },
        "user_preferences": prefs,
        "conversations": full_sessions,
        "chat_sessions": full_sessions,
        "memories": memories,
        "custom_personas": personas_info.get("custom_personas", []),
    }

    content_str = json.dumps(export_payload, indent=2, ensure_ascii=False)
    filename = f"aira_data_export_{ctx.username}_{ctx.user_id[:8]}.json"

    return Response(
        content=content_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/data/conversations")
def delete_all_user_conversations(ctx: TenantContext = Depends(get_current_user_context)):
    """Deletes all chat sessions and messages owned by the authenticated user."""
    count = session_store.delete_all_user_sessions(ctx.user_id)
    return {"success": True, "deleted_sessions": count, "message": f"{count} sesi percakapan berhasil dihapus."}


@router.delete("/data/memories")
def clear_all_user_memories(ctx: TenantContext = Depends(get_current_user_context)):
    """Clears all long-term memories owned by the authenticated user."""
    count = _memory_svc.clear_all_memories(ctx.user_id)
    return {"success": True, "deleted_memories": count, "message": f"{count} memori berhasil dihapus."}


@router.delete("/data/personas")
def delete_all_custom_personas(ctx: TenantContext = Depends(get_current_user_context)):
    """Deletes all custom personas created by the authenticated user."""
    count = _persona_svc.delete_all_custom_personas(ctx.user_id)
    return {"success": True, "deleted_personas": count, "message": f"{count} persona kustom berhasil dihapus."}


@router.post("/data/account-deletion-request")
def request_account_deletion(
    payload: Optional[Dict[str, Any]] = None,
    ctx: TenantContext = Depends(get_current_user_context),
):
    """Initiates an audited request for permanent account deletion."""
    if ctx.username == "lingga_admin" or "PLATFORM_OWNER" in (ctx.roles or []):
        raise HTTPException(status_code=400, detail="Akun Pemilik Platform (PLATFORM_OWNER) tidak dapat dihapus.")

    reason = (payload or {}).get("reason", "User requested self account deletion through Privacy & Data portal.")
    from core.tenant.admin_authorization_service import get_admin_auth_service
    admin_svc = get_admin_auth_service()
    admin_svc.log_administrative_action(
        admin_id=ctx.user_id,
        username=ctx.username,
        action="ACCOUNT_DELETION_REQUESTED",
        resource_type="USER",
        resource_id=ctx.user_id,
        details={"reason": reason},
        tenant_id=ctx.tenant_id or "tenant_default",
    )
    return {
        "success": True,
        "status": "PENDING_VERIFICATION",
        "message": "Permintaan penghapusan akun telah dicatat. Data Anda dijadwalkan untuk dihapus sesuai retention policy.",
    }
