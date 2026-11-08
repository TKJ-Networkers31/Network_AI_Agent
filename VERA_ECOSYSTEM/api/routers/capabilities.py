from typing import Optional
from fastapi import APIRouter, Query
from api.routers.capabilities_logic import list_capabilities

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def _available_tools():
    try:
        from core.orchestrator import AGENT_TOOL_MAP
        return set(AGENT_TOOL_MAP.keys())
    except Exception:
        return None


@router.get("")
def get_capabilities(
    area: str = Query(default="conversation"),
    conversation_id: Optional[str] = None, session_id: Optional[str] = None,
    message_id: Optional[str] = None, file_path: Optional[str] = None,
    role: Optional[str] = None, has_selection: bool = False, has_attachment: bool = False,
    has_artifact: bool = False, has_location: bool = False,
):
    items = list_capabilities(
        area=area, message_id=message_id, conversation_id=conversation_id, role=role,
        has_attachment=has_attachment, has_artifact=has_artifact, has_location=has_location,
        has_selection=has_selection, file_path=file_path, available_tools=_available_tools(),
    )
    return {"capabilities": items}