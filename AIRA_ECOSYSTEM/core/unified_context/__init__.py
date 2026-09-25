"""
core/unified_context/ — Unified Context (Sprint 2.7 / Wave 2 / W9).

Merges conversation, attachment, selection, artifact, location, and
permission context into ONE composable packet - built on TOP of the
existing core.context.ContextBuilder (not a replacement for it) plus
core.attachments / core.selection / core.artifacts, and using
core.capability's own context-type vocabulary (CONTEXT_*) so the result
can be handed straight to CapabilityDiscovery.discover(context=...).

Public API:
    from core.unified_context import (
        UnifiedContext, UnifiedContextSource, ContextItem, dedupe_items,
        UnifiedContextBuilder, get_unified_context_builder,
        ALL_SOURCES, SOURCE_CONVERSATION, SOURCE_ATTACHMENT,
        SOURCE_SELECTION, SOURCE_ARTIFACT, SOURCE_LOCATION, SOURCE_PERMISSION,
    )

    unified = get_unified_context_builder().build("cek R1", session_id="s1")
    unified.system_prompt      # SAME string Planner/PersonaEngine already produce today
    unified.context_types()    # -> CapabilityDiscovery.discover(context=unified.context_types())
    unified.for_discovery()    # -> ready-to-spread kwargs for CapabilityDiscovery.discover(**...)
    unified.to_dict()          # JSON-safe, for REI / logging / debug

This package does NOT create a second Context Builder, does NOT touch
core.orchestrator, streaming, core.chat_sessions, or
core.capability.CapabilityRegistry (only reads its context-type constants),
and implements no UI.
"""

from core.unified_context.models import (
    ALL_SOURCES,
    CONTEXT_SCHEMA_VERSION,
    ContextItem,
    SOURCE_ARTIFACT,
    SOURCE_ATTACHMENT,
    SOURCE_CONVERSATION,
    SOURCE_LOCATION,
    SOURCE_PERMISSION,
    SOURCE_SELECTION,
    SOURCE_TO_CAPABILITY_CONTEXT,
    UnifiedContext,
    UnifiedContextSource,
    dedupe_items,
)
from core.unified_context.builder import UnifiedContextBuilder, get_unified_context_builder

__all__ = [
    "UnifiedContext", "UnifiedContextSource", "ContextItem", "dedupe_items",
    "ALL_SOURCES", "CONTEXT_SCHEMA_VERSION", "SOURCE_TO_CAPABILITY_CONTEXT",
    "SOURCE_CONVERSATION", "SOURCE_ATTACHMENT", "SOURCE_SELECTION",
    "SOURCE_ARTIFACT", "SOURCE_LOCATION", "SOURCE_PERMISSION",
    "UnifiedContextBuilder", "get_unified_context_builder",
]