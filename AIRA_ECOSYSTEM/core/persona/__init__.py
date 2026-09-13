"""
core/persona/ — Dynamic Persona Engine (Phase 1.3).

Public API:
    from core.persona import get_engine
    system_prompt = get_engine().build(extra_context)

Backward-compat shim `build_system_prompt()` disediakan supaya tidak ada
caller lama yang patah, tapi caller BARU (agents/rei/planner.py) memakai
get_engine().build() langsung sesuai spek "Chat Session memanggil
PersonaEngine.build()".
"""

from core.persona.engine import PersonaEngine, get_engine


def build_system_prompt(extra_context: str = "") -> str:
    return get_engine().build(extra_context)


__all__ = ["PersonaEngine", "get_engine", "build_system_prompt"]