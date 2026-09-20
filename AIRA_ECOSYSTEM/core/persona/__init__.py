"""
core/persona/ — Dynamic Persona Engine (Phase 1.3) + Persona configuration (Sprint 2 / Worker 2).

Public API:
    from core.persona import get_engine, get_persona_context
    system_prompt = get_engine().build(extra_context)   # dipakai ContextBuilder
    persona_ctx   = get_persona_context()                # PersonaContext deterministik

Persona hanya mengatur PRESENTASI. Ia tidak mengimpor model router, classifier,
orchestrator, atau modul tool (dijaga oleh tests/test_persona_engine.py).

Backward-compat shim `build_system_prompt()` tetap tersedia.
"""

from core.persona.context import PersonaContext, build_persona_context
from core.persona.engine import PersonaEngine, get_engine
from core.persona.loader import PersonaConfig, get_persona_config, load_persona_config


def build_system_prompt(extra_context: str = "") -> str:
    return get_engine().build(extra_context)


def get_persona_context(engine=None) -> PersonaContext:
    """PersonaContext untuk persona aktif (profile + behavior + preset di database)."""
    engine = engine or get_engine()
    profile = engine.get_profile()

    return build_persona_context(
        profile,
        engine.get_behavior(),
        engine.get_active_preset_text(),
        preset_id=profile.get("active_preset"),
    )


__all__ = [
    "PersonaEngine", "get_engine", "build_system_prompt",
    "PersonaContext", "build_persona_context", "get_persona_context",
    "PersonaConfig", "get_persona_config", "load_persona_config",
]