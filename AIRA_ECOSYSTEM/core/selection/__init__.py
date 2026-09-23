"""
core/selection/ — Selection Intelligence (Sprint 2.7 / Worker 3, W4).

Public API:
    from core.selection import (
        SelectionContext, SelectionContextPacket, ContextActionRequest, SelectionResult,
        SelectionBuilder, build_context_packet, build_action_request, validate_action,
        SelectionStore, get_selection_store,
        VALID_ACTIONS, VALID_SOURCE_TYPES,
    )

Modul ini TIDAK membuat Context Builder baru (core/context/builder.py tidak
disentuh) dan TIDAK mengubah Event Bus / streaming contract. Ia hanya
menghasilkan SelectionContext + SelectionContextPacket yang siap dipakai
Capability Layer / Planner di masa depan.
"""

from core.selection.constants import (
    SOURCE_MESSAGE, VALID_SOURCE_TYPES, VALID_ACTIONS, ACTION_LABELS,
    ACTION_EXPLAIN, ACTION_SIMPLIFY, ACTION_EXPAND, ACTION_REWRITE,
    ACTION_TRANSLATE, ACTION_CONTINUE, ACTION_CREATE_DOCUMENT, ACTION_ASK,
)
from core.selection.models import (
    SelectionContext, SelectionContextPacket, ContextActionRequest, SelectionResult,
)
from core.selection.builder import (
    SelectionBuilder, build_context_packet, build_action_request, validate_action,
)
from core.selection.store import SelectionStore, get_selection_store

__all__ = [
    "SOURCE_MESSAGE", "VALID_SOURCE_TYPES", "VALID_ACTIONS", "ACTION_LABELS",
    "ACTION_EXPLAIN", "ACTION_SIMPLIFY", "ACTION_EXPAND", "ACTION_REWRITE",
    "ACTION_TRANSLATE", "ACTION_CONTINUE", "ACTION_CREATE_DOCUMENT", "ACTION_ASK",
    "SelectionContext", "SelectionContextPacket", "ContextActionRequest", "SelectionResult",
    "SelectionBuilder", "build_context_packet", "build_action_request", "validate_action",
    "SelectionStore", "get_selection_store",
]