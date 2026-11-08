"""
core/capability/registry.py — CapabilityRegistry (Sprint 2.7 / W1).

In-memory, thread-safe registry: the single place capabilities are
registered/looked up/listed/removed. Mirrors the singleton + Lock pattern
already used across the codebase (core/persona/engine.py::PersonaEngine,
core/model_store.py::ModelStore, core/dio/interaction_memory.py, etc.),
but this registry is deliberately NOT persisted to SQLite: capabilities
are a startup/code concept (what modules register when they import), not
user data - the same status as AGENT_TOOL_MAP in core/orchestrator.py,
just capability-shaped instead of tool-shaped.

Publishes to the EXISTING Event Bus (core/events.py::event_bus) using
string event names from core/capability/constants.py - no new event bus,
no change to core.events.EventNames (same convention as
core/global_settings.py).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from core.capability.constants import (
    EVENT_CAPABILITY_REGISTERED,
    EVENT_CAPABILITY_STATE_CHANGED,
    EVENT_CAPABILITY_UNREGISTERED,
    EVENT_CAPABILITY_UPDATED,
    STATE_REGISTERED,
)
from core.capability.models import Capability, ValidationResult, validate_capability

logger = logging.getLogger("aira.capability.registry")


class CapabilityAlreadyRegisteredError(Exception):
    """Raised by register() on a duplicate id when overwrite=False."""


class CapabilityValidationError(Exception):
    """Raised by register() when the capability fails validate_capability()."""

    def __init__(self, result: ValidationResult):
        self.result = result
        messages = "; ".join(f"{i.field}: {i.message}" for i in result.issues)
        super().__init__(f"Capability tidak valid: {messages}")


def _publish(event_name: str, **data: Any) -> None:
    """Best-effort publish to the existing Event Bus. Never raises - a
    missing/broken Event Bus must not break capability registration (same
    defensive pattern as core/global_settings.py::_publish_settings_changed)."""
    try:
        from core.events import event_bus
        event_bus.publish(event_name, source="CAPABILITY", agent="CAPABILITY", data=data)
    except Exception:
        logger.debug("CAPABILITY | gagal publish %s (diabaikan).", event_name, exc_info=True)


class CapabilityRegistry:
    """
    Thread-safe. Read methods (get/list) return SNAPSHOTS - callers can't
    mutate registry state by mutating a returned Capability (Capability is
    effectively immutable via with_state()/replace_capability()).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._capabilities: dict = {}

    # ------------------------------------------------------------ write

    def register(self, capability: Capability, *, overwrite: bool = False) -> Capability:
        """
        Register a new capability. New registrations always start at
        STATE_REGISTERED regardless of what the caller passed in (state is
        a lifecycle fact owned by the registry/discovery layer, not the
        author).

        Raises CapabilityValidationError if the capability fails
        validate_capability(). Raises CapabilityAlreadyRegisteredError on a
        duplicate id unless overwrite=True.
        """
        result = validate_capability(capability)
        if not result.is_valid:
            raise CapabilityValidationError(result)

        registered = capability.with_state(STATE_REGISTERED)

        with self._lock:
            existing = self._capabilities.get(registered.id)

            if existing is not None and not overwrite:
                raise CapabilityAlreadyRegisteredError(
                    f"Capability '{registered.id}' sudah terdaftar. Pakai overwrite=True untuk menimpa."
                )

            self._capabilities[registered.id] = registered

        event = EVENT_CAPABILITY_UPDATED if existing is not None else EVENT_CAPABILITY_REGISTERED
        _publish(event, id=registered.id, category=registered.category)

        logger.info(
            "CAPABILITY %s | id=%s category=%s",
            "OVERWRITE" if existing is not None else "REGISTER",
            registered.id, registered.category,
        )

        return registered

    def unregister(self, capability_id: str) -> bool:
        with self._lock:
            existed = self._capabilities.pop(capability_id, None) is not None

        if existed:
            _publish(EVENT_CAPABILITY_UNREGISTERED, id=capability_id)
            logger.info("CAPABILITY UNREGISTER | id=%s", capability_id)

        return existed

    # alias - spec also calls this "remove"
    remove = unregister

    def set_state(self, capability_id: str, new_state: str) -> Optional[Capability]:
        """Update one capability's state in place (registry-owned mutation,
        unlike Capability.with_state() which returns a detached copy).
        Returns the updated capability, or None if id doesn't exist."""
        with self._lock:
            existing = self._capabilities.get(capability_id)

            if existing is None:
                return None

            updated = existing.with_state(new_state)
            self._capabilities[capability_id] = updated

        _publish(EVENT_CAPABILITY_STATE_CHANGED, id=capability_id, state=new_state)
        logger.info("CAPABILITY STATE | id=%s -> %s", capability_id, new_state)

        return updated

    def clear(self) -> int:
        """Remove ALL capabilities. Mainly for tests; not exposed over HTTP."""
        with self._lock:
            count = len(self._capabilities)
            self._capabilities.clear()
        return count

    # ------------------------------------------------------------- read

    def get(self, capability_id: str) -> Optional[Capability]:
        with self._lock:
            return self._capabilities.get(capability_id)

    def exists(self, capability_id: str) -> bool:
        with self._lock:
            return capability_id in self._capabilities

    def list(
        self,
        *,
        category: Optional[str] = None,
        state: Optional[str] = None,
        permission: Optional[str] = None,
        context: Optional[str] = None,
        predicate: Optional[Callable[[Capability], bool]] = None,
    ) -> list:
        """Snapshot list, filtered. Order: registration order (dict
        insertion order, stable) - deterministic for tests/UI."""
        with self._lock:
            items = list(self._capabilities.values())

        if category is not None:
            items = [c for c in items if c.category == category]
        if state is not None:
            items = [c for c in items if c.state == state]
        if permission is not None:
            items = [c for c in items if c.permission == permission]
        if context is not None:
            items = [c for c in items if c.supports_context(context)]
        if predicate is not None:
            items = [c for c in items if predicate(c)]

        return items

    def count(self) -> int:
        with self._lock:
            return len(self._capabilities)


_registry_singleton: Optional[CapabilityRegistry] = None
_registry_lock = threading.Lock()


def get_capability_registry() -> CapabilityRegistry:
    global _registry_singleton

    if _registry_singleton is None:
        with _registry_lock:
            if _registry_singleton is None:
                _registry_singleton = CapabilityRegistry()

    return _registry_singleton
