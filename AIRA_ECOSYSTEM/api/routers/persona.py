"""
api/routers/persona.py — REST endpoint untuk Persona Engine (Phase 1.3 + Phase F/H).

Murni "pintu HTTP" di atas core/persona/engine.py::PersonaEngine,
disinkronkan dengan UserPersonaService & UserMemoryService jika user login.
"""

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.persona import get_engine
from core.tenant.manager import IdentityManager
from core.tenant.persona_service import get_persona_service
from core.tenant.memory_service import get_memory_service

router = APIRouter(prefix="/api/persona", tags=["persona"])

_id_mgr = IdentityManager()


def _get_user_id(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    ctx = _id_mgr.validate_session_token(token)
    return ctx.user_id if ctx else None


def _dump(payload: BaseModel) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return payload.dict(exclude_unset=True)


class ProfileUpdateRequest(BaseModel):
    assistant_name: Optional[str] = None
    user_name: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    greeting: Optional[str] = None


class BehaviorUpdateRequest(BaseModel):
    professionalism: Optional[int] = None
    friendliness: Optional[int] = None
    playfulness: Optional[int] = None
    verbosity: Optional[int] = None
    empathy: Optional[int] = None
    teaching_depth: Optional[int] = None


class ApplyPresetRequest(BaseModel):
    preset_id: str


class ClonePresetRequest(BaseModel):
    preset_id: str
    new_name: str


class PreviewRequest(BaseModel):
    extra_context: Optional[str] = ""


@router.get("")
def get_persona(authorization: Optional[str] = Header(None)):
    state = get_engine().get_state()
    user_id = _get_user_id(authorization)
    if user_id:
        try:
            mem_svc = get_memory_service()
            ident = mem_svc.get_user_identity(user_id)
            if ident.get("preferred_name") or ident.get("full_name"):
                state["profile"]["user_name"] = ident.get("preferred_name") or ident.get("full_name")
            p_svc = get_persona_service()
            active_p = p_svc.get_active_persona(user_id)
            if active_p and active_p.get("persona_id"):
                state["profile"]["active_preset"] = active_p["persona_id"]
        except Exception:
            pass
    return state


@router.put("/profile")
def update_profile(payload: ProfileUpdateRequest, authorization: Optional[str] = Header(None)):
    res = get_engine().update_profile(_dump(payload))
    user_id = _get_user_id(authorization)
    if user_id:
        try:
            mem_svc = get_memory_service()
            ident_updates = {}
            if payload.user_name:
                ident_updates["preferred_name"] = payload.user_name
            if payload.language:
                ident_updates["language"] = payload.language
            if ident_updates:
                mem_svc.update_user_identity(user_id, ident_updates)
        except Exception:
            pass
    return res


@router.put("/behavior")
def update_behavior(payload: BehaviorUpdateRequest, authorization: Optional[str] = Header(None)):
    return get_engine().update_behavior(_dump(payload))


@router.get("/presets")
def list_presets():
    return {"presets": get_engine().list_presets()}


@router.get("/presets/{preset_id}")
def get_preset(preset_id: str):
    preset = get_engine().get_preset(preset_id)

    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' tidak ditemukan.")

    return preset


@router.post("/presets/apply")
def apply_preset(payload: ApplyPresetRequest, authorization: Optional[str] = Header(None)):
    result = get_engine().apply_preset(payload.preset_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    user_id = _get_user_id(authorization)
    if user_id:
        try:
            p_svc = get_persona_service()
            p_svc.set_active_persona(user_id, payload.preset_id)
        except Exception:
            pass

    return result


@router.post("/presets/clone")
def clone_preset(payload: ClonePresetRequest):
    result = get_engine().clone_preset(payload.preset_id, payload.new_name)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/preview")
def preview(payload: PreviewRequest, authorization: Optional[str] = Header(None)):
    user_id = _get_user_id(authorization)
    if user_id:
        try:
            from core.events import event_scope
            with event_scope(user_id=user_id):
                prompt = get_engine().preview(payload.extra_context or "")
                return {"system_prompt": prompt}
        except Exception:
            pass
    prompt = get_engine().preview(payload.extra_context or "")
    return {"system_prompt": prompt}
