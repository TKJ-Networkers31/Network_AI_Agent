"""
core/runtime_state/ — Runtime State Engine (Sprint 2 / Worker 3).

Public API:
    from core.runtime_state import get_runtime_state, RuntimeState

    engine = get_runtime_state()          # singleton, otomatis subscribe ke Event Bus
    engine.state                          # RuntimeState.IDLE / LISTENING / THINKING / SPEAKING
    engine.snapshot().to_dict()           # {"state", "previous", "since", "seq", "reason", "active"}

Perubahan state dipublish ke Event Bus sebagai "runtime.state_changed".
Engine hanya MENERJEMAHKAN event menjadi state - bukan tempat reasoning.
"""

from core.runtime_state.models import (
    ACTIVITY_PRIORITY,
    ALLOWED_TRANSITIONS,
    DEFAULT_STALE_AFTER,
    RuntimeEvents,
    RuntimeSnapshot,
    RuntimeState,
    is_valid_transition,
    resolve_state,
)
from core.runtime_state.engine import (
    RuntimeStateEngine,
    SUBSCRIBED_EVENTS,
    get_runtime_state,
    runtime_state_snapshot,
)

__all__ = [
    "RuntimeState", "RuntimeEvents", "RuntimeSnapshot",
    "ALLOWED_TRANSITIONS", "ACTIVITY_PRIORITY", "DEFAULT_STALE_AFTER",
    "is_valid_transition", "resolve_state",
    "RuntimeStateEngine", "SUBSCRIBED_EVENTS",
    "get_runtime_state", "runtime_state_snapshot",
]
