"""
api/routers/capabilities.py — REST endpoint tipis untuk Dynamic Capability UI
(Sprint 2.7 W8 / Sprint 2.7.1 P0 recovery).

Murni pintu HTTP di atas core/capability/discovery.py yang SUDAH ADA -
tidak ada registry/discovery baru dibuat di sini. Satu-satunya "logic" di
file ini adalah menerjemahkan `area` (istilah UI: hero/chat_input/
capability_dock/message_actions/file_actions/conversation) menjadi
`context` (istilah W1: conversation/attachment/selection/artifact/
workspace/location/permission) sebelum memanggil CapabilityDiscovery, lalu
menambahkan key "area" ke tiap item hasil karena
core.capability.frontend.capability_to_frontend_dict() sengaja tidak
menyertakannya (area adalah konsep UI, bukan konsep Capability Layer).

CATATAN INTEGRASI: kalau repo Anda SUDAH punya file ini dengan isi
berbeda, JANGAN ditimpa buta - bandingkan dulu, khususnya bagian
AREA_TO_CONTEXT dan penambahan key "area" (dua hal yang dibutuhkan
CapabilityContext.jsx::forArea() di frontend).
"""

from typing import Optional

from fastapi import APIRouter, Query

from core.capability import (
    CONTEXT_ARTIFACT,
    CONTEXT_ATTACHMENT,
    CONTEXT_CONVERSATION,
    CONTEXT_LOCATION,
    CONTEXT_SELECTION,
    CONTEXT_WORKSPACE,
    DiscoverySettings,
    capabilities_to_frontend_list,
    get_capability_discovery,
)

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])

_BASE_CONTEXT_FOR_AREA = {
    "hero": [CONTEXT_CONVERSATION],
    "chat_input": [CONTEXT_CONVERSATION],
    "capability_dock": [CONTEXT_CONVERSATION],
    "conversation": [CONTEXT_CONVERSATION],
    "message_actions": [CONTEXT_SELECTION],
    "file_actions": [CONTEXT_WORKSPACE],
}


def _available_tools() -> Optional[set]:
    """Tool yang saat ini benar-benar resolvable, dari
    core.orchestrator.AGENT_TOOL_MAP yang SUDAH ADA - dipakai discovery
    untuk menyaring capability yang tool_binding-nya tidak tersedia."""
    try:
        from core.orchestrator import AGENT_TOOL_MAP
        return set(AGENT_TOOL_MAP.keys())
    except Exception:
        return None


@router.get("")
def list_capabilities(
    area: str = Query(default="conversation"),
    conversation_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    message_id: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    has_selection: bool = Query(default=False),
    has_attachment: bool = Query(default=False),
    has_artifact: bool = Query(default=False),
    has_location: bool = Query(default=False),
):
    context = list(_BASE_CONTEXT_FOR_AREA.get(area, [CONTEXT_CONVERSATION]))

    # Sinyal dari frontend (CapabilityContext.jsx) menambah context type,
    # tidak menggantikannya - satu capability bisa cocok lewat lebih dari
    # satu context sekaligus (lihat Capability.supports_context: ANY match).
    if has_attachment and CONTEXT_ATTACHMENT not in context:
        context.append(CONTEXT_ATTACHMENT)
    if has_artifact and CONTEXT_ARTIFACT not in context:
        context.append(CONTEXT_ARTIFACT)
    if has_location and CONTEXT_LOCATION not in context:
        context.append(CONTEXT_LOCATION)
    if has_selection and CONTEXT_SELECTION not in context:
        context.append(CONTEXT_SELECTION)

    discovery = get_capability_discovery()
    discovered = discovery.discover(
        context=context,
        available_tools=_available_tools(),
        settings=DiscoverySettings(),
    )

    payload = capabilities_to_frontend_list(discovered)
    for item in payload:
        item["area"] = area

    return {"capabilities": payload}
