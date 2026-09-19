"""
core/context/ — Context Builder (Sprint 2 / Worker 1).

Public API:
    from core.context import ContextBuilder, AIRAContext, get_context_builder

    context = ContextBuilder().build("cek R1", session_id="s1", task=classification)
    context.system_prompt      # dipakai Planner apa adanya
    context.to_dict()          # serialisasi JSON-safe

Builder hanya MENGGABUNGKAN konteks; persona, memory, lokasi, waktu, routing
model, dan eksekusi tool tetap milik modul masing-masing.
"""

from core.context.models import (
    ALL_SECTIONS,
    CONTEXT_SCHEMA_VERSION,
    PROMPT_SECTIONS,
    SECTION_IDENTITY,
    SECTION_LOCATION,
    SECTION_MEMORY,
    SECTION_PERSONA,
    SECTION_RUNTIME_STATE,
    SECTION_TOOL_CONTEXT,
    AIRAContext,
    ContextSection,
)
from core.context.builder import (
    ContextBuilder,
    get_context_builder,
    summarize_tool_schemas,
)

__all__ = [
    "AIRAContext", "ContextSection",
    "ContextBuilder", "get_context_builder", "summarize_tool_schemas",
    "ALL_SECTIONS", "PROMPT_SECTIONS", "CONTEXT_SCHEMA_VERSION",
    "SECTION_IDENTITY", "SECTION_PERSONA", "SECTION_MEMORY",
    "SECTION_RUNTIME_STATE", "SECTION_LOCATION", "SECTION_TOOL_CONTEXT",
]
