"""
api/routers/persona.py — REST endpoint untuk Persona Engine (Phase 1.3).

Murni "pintu HTTP" tipis di atas core/persona/engine.py::PersonaEngine.
Tidak ada logic persona di sini.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.persona import get_engine

router = APIRouter(prefix="/api/persona", tags=["persona"])


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
def get_persona():
    return get_engine().get_state()


@router.put("/profile")
def update_profile(payload: ProfileUpdateRequest):
    return get_engine().update_profile(_dump(payload))


@router.put("/behavior")
def update_behavior(payload: BehaviorUpdateRequest):
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
def apply_preset(payload: ApplyPresetRequest):
    result = get_engine().apply_preset(payload.preset_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.post("/presets/clone")
def clone_preset(payload: ClonePresetRequest):
    result = get_engine().clone_preset(payload.preset_id, payload.new_name)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/preview")
def preview(payload: PreviewRequest):
    prompt = get_engine().preview(payload.extra_context or "")
    return {"system_prompt": prompt}