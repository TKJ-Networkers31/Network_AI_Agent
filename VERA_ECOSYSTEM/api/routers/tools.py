from fastapi import APIRouter

from core.orchestrator import AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
def list_tools():
    items = []

    for entry in AGENT_TOOL_SCHEMAS:
        fn = entry.get("function", {})
        name = fn.get("name")

        if not name:
            continue

        params = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])

        items.append({
            "name": name,
            "description": fn.get("description", ""),
            "category": AGENT_TOOL_CATEGORY.get(name, "tool"),
            "parameters": [{"name": p, "required": p in required} for p in params.keys()],
        })

    return {"tools": items}
