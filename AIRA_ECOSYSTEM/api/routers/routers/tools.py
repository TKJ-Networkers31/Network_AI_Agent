from fastapi import APIRouter

from agent.core.engine import TOOLS
from tools.registry import TOOL_CATEGORY

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
def list_tools():
    """
    Menerjemahkan skema function-calling (TOOLS, yang sama persis
    dipakai untuk kirim ke LLM di engine.py) jadi daftar ringkas
    untuk dropdown '/' di frontend - supaya daftar tool otomatis
    ikut sinkron kalau kamu menambah tool baru di engine.py, tanpa
    perlu di-maintain dua kali.
    """

    items = []

    for entry in TOOLS:

        fn = entry.get("function", {})
        name = fn.get("name")

        if not name:
            continue

        params = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])

        items.append({
            "name": name,
            "description": fn.get("description", ""),
            "category": TOOL_CATEGORY.get(name, "tool"),
            "parameters": [
                {"name": p, "required": p in required}
                for p in params.keys()
            ],
        })

    return {"tools": items}
