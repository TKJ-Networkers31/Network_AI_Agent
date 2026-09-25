"""
core/unified_context/models.py — Unified Context data contract
(Sprint 2.7 / Wave 2 / W9).

Pure data + serialization (dataclasses only) - no I/O, no reasoning, same
split as core/context/models.py and core/dio/models.py. UnifiedContext is
a COMPOSITION of context sources that already exist elsewhere in AIRA
(see builder.py for who owns each source); this module only defines the
packet shape every consumer (REI, Capability Discovery) agrees on.

Design goals (Sprint 2.7 / W9 brief):
    - provenance       : every item records where it came from
                          (`provenance`, at minimum {"origin": ...})
    - source identity   : every item is tagged with its owning `source`
    - dedup             : items sharing the same id within one source
                          collapse to one; the duplicate's origin is
                          recorded, never silently dropped
    - JSON-safe         : to_dict()/to_json() never raise on odd input
                          (uses core.events.json_safe, the SAME helper
                          core.context.models already relies on)
    - optional sources  : an absent/failed source is simply missing
                          (available=False) - never a hard error for the
                          whole packet
    - no binary         : this module never carries bytes; every producer
                          feeding it (core.attachments.context,
                          core.artifacts.models, core.selection.models) is
                          already metadata/reference-only by its OWN
                          contract - this module doesn't need to re-strip
                          anything, it just never invents a new path that
                          could
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.events import json_safe
from core.capability.constants import (
    CONTEXT_ARTIFACT,
    CONTEXT_ATTACHMENT,
    CONTEXT_CONVERSATION,
    CONTEXT_LOCATION,
    CONTEXT_PERMISSION,
    CONTEXT_SELECTION,
)

CONTEXT_SCHEMA_VERSION = "1.0"

SOURCE_CONVERSATION = "conversation"
SOURCE_ATTACHMENT = "attachment"
SOURCE_SELECTION = "selection"
SOURCE_ARTIFACT = "artifact"
SOURCE_LOCATION = "location"
SOURCE_PERMISSION = "permission"

# Canonical order (used by present_sources()/all_items()/to_dict()).
ALL_SOURCES = (
    SOURCE_CONVERSATION, SOURCE_ATTACHMENT, SOURCE_SELECTION,
    SOURCE_ARTIFACT, SOURCE_LOCATION, SOURCE_PERMISSION,
)

# Unified Context source name -> the W1 Capability Layer's own
# context-type vocabulary (core.capability.constants.CONTEXT_*). This is
# what makes UnifiedContext.context_types() usable DIRECTLY as
# CapabilityDiscovery.discover(context=...) without CapabilityDiscovery or
# CapabilityRegistry ever needing to know Unified Context exists.
SOURCE_TO_CAPABILITY_CONTEXT: dict[str, str] = {
    SOURCE_CONVERSATION: CONTEXT_CONVERSATION,
    SOURCE_ATTACHMENT: CONTEXT_ATTACHMENT,
    SOURCE_SELECTION: CONTEXT_SELECTION,
    SOURCE_ARTIFACT: CONTEXT_ARTIFACT,
    SOURCE_LOCATION: CONTEXT_LOCATION,
    SOURCE_PERMISSION: CONTEXT_PERMISSION,
}


def _json_dict(value: Any) -> dict:
    safe = json_safe(value)
    return safe if isinstance(safe, dict) else {"value": safe}


# ============================================================ ContextItem

@dataclass
class ContextItem:
    """
    One discrete fact/reference within a source (one attachment, one
    selection, one artifact, one conversation section, the location
    snapshot, ...).

    id         : stable within its OWN source - dedup key is (source, id),
                 not global uniqueness across sources.
    data       : structured, JSON-safe payload. Never binary - every
                 producer of `data` already guarantees this at its own
                 boundary (see module docstring).
    text       : optional prompt-ready text (conversation/location items
                 carry prose their owning module already produced;
                 selection carries the selected text itself).
    provenance : where this item came from - at minimum {"origin": ...}.
                 dedupe_items() appends "duplicate_origins" here rather
                 than dropping the fact that an item repeated.
    """

    id: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "data": _json_dict(self.data),
            "text": self.text,
            "provenance": _json_dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextItem":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            data=dict(data.get("data") or {}),
            text=str(data.get("text") or ""),
            provenance=dict(data.get("provenance") or {}),
        )


def dedupe_items(items: list) -> list:
    """
    Collapse items sharing the same id within one source, PRESERVING
    first-seen order. A duplicate's origin is appended to the kept item's
    provenance (`duplicate_origins`) instead of being silently discarded -
    provenance must survive dedup, not become a casualty of it.
    """
    kept: dict[str, ContextItem] = {}
    order: list[str] = []

    for item in items:
        if item is None:
            continue

        if item.id not in kept:
            kept[item.id] = item
            order.append(item.id)
            continue

        existing = kept[item.id]
        duplicates = existing.provenance.setdefault("duplicate_origins", [])
        origin = item.provenance.get("origin") or item.source

        if origin not in duplicates:
            duplicates.append(origin)

    return [kept[key] for key in order]


# ==================================================== UnifiedContextSource

@dataclass
class UnifiedContextSource:
    """
    One source's contribution to the packet. A source that failed to
    build is still REPRESENTED (available=False, error set) rather than
    silently vanishing - callers can tell "empty" from "broken", and an
    absent source never breaks the rest of the packet.
    """

    name: str
    items: list[ContextItem] = field(default_factory=list)
    text: str = ""
    available: bool = True
    error: Optional[str] = None

    def __post_init__(self) -> None:
        self.items = dedupe_items(self.items)

    @property
    def is_present(self) -> bool:
        return self.available and (bool(self.items) or bool(self.text.strip()))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "error": self.error,
            "count": len(self.items),
            "items": [i.to_dict() for i in self.items],
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedContextSource":
        data = data if isinstance(data, dict) else {}
        raw_items = data.get("items") or []

        return cls(
            name=str(data.get("name") or ""),
            items=[ContextItem.from_dict(i) for i in raw_items if isinstance(i, dict)],
            text=str(data.get("text") or ""),
            available=bool(data.get("available", True)),
            error=data.get("error"),
        )


# ========================================================= UnifiedContext

@dataclass
class UnifiedContext:
    """
    The single composed context packet for one turn - REI and Capability
    Discovery both consume THIS, not each source's own module directly.

    system_prompt         : passthrough of the underlying
                             core.context.AIRAContext.system_prompt -
                             UNCHANGED prompt-building contract. Planner/
                             PersonaEngine keep working exactly as before;
                             Unified Context adds a view on top, it does
                             not replace how the prompt is built.
    conversation_context   : the full underlying AIRAContext.to_dict()
                             (prompt excluded, it's already on
                             `system_prompt`) - kept whole as a backward-
                             compatible escape hatch for callers that want
                             the original shape.
    """

    session_id: Optional[str] = None
    user_input: str = ""
    sources: dict[str, UnifiedContextSource] = field(default_factory=dict)
    system_prompt: str = ""
    conversation_context: Optional[dict] = None
    task: Optional[dict] = None
    warnings: list[str] = field(default_factory=list)
    version: str = CONTEXT_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------ inspect

    def present_sources(self) -> list[str]:
        """Source names that actually contributed something this turn,
        canonical order."""
        return [
            name for name in ALL_SOURCES
            if name in self.sources and self.sources[name].is_present
        ]

    def get(self, source_name: str) -> Optional[UnifiedContextSource]:
        return self.sources.get(source_name)

    def items(self, source_name: str) -> list[ContextItem]:
        source = self.sources.get(source_name)
        return list(source.items) if source else []

    def all_items(self) -> list[ContextItem]:
        flat: list[ContextItem] = []
        for name in ALL_SOURCES:
            flat.extend(self.items(name))
        return flat

    def context_types(self) -> list[str]:
        """Capability-Layer context vocabulary for the sources actually
        PRESENT this turn - ready to pass to
        CapabilityDiscovery.discover(context=unified.context_types())."""
        types = {
            SOURCE_TO_CAPABILITY_CONTEXT[name]
            for name in self.present_sources()
            if name in SOURCE_TO_CAPABILITY_CONTEXT
        }
        return sorted(types)

    def for_discovery(self) -> dict:
        """Ready-to-spread kwargs:
        CapabilityDiscovery.discover(**unified.for_discovery())."""
        return {"context": self.context_types()}

    def summary(self) -> dict:
        return {
            "present_sources": self.present_sources(),
            "context_types": self.context_types(),
            "item_counts": {name: len(s.items) for name, s in self.sources.items()},
            "warnings": len(self.warnings),
        }

    # -------------------------------------------------------- serialize

    def to_dict(self, include_prompt: bool = True) -> dict:
        data: dict[str, Any] = {
            "version": self.version,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "task": _json_dict(self.task) if self.task is not None else None,
            "sources": {name: source.to_dict() for name, source in self.sources.items()},
            "present_sources": self.present_sources(),
            "context_types": self.context_types(),
            "warnings": list(self.warnings),
        }

        if include_prompt:
            data["system_prompt"] = self.system_prompt

        if self.conversation_context is not None:
            data["conversation_context"] = _json_dict(self.conversation_context)

        return data

    def to_json(self, include_prompt: bool = True) -> str:
        return json.dumps(self.to_dict(include_prompt), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedContext":
        """Toleran: field hilang/rusak -> default, tidak pernah raise
        (same contract as core.context.models.AIRAContext.from_dict)."""
        data = data if isinstance(data, dict) else {}
        raw_sources = data.get("sources") or {}

        sources = {
            name: UnifiedContextSource.from_dict(value)
            for name, value in raw_sources.items()
            if isinstance(value, dict)
        }

        task = data.get("task")
        created_at = data.get("created_at")

        return cls(
            session_id=data.get("session_id"),
            user_input=str(data.get("user_input") or ""),
            sources=sources,
            system_prompt=str(data.get("system_prompt") or ""),
            conversation_context=(
                dict(data["conversation_context"])
                if isinstance(data.get("conversation_context"), dict) else None
            ),
            task=dict(task) if isinstance(task, dict) else None,
            warnings=[str(w) for w in (data.get("warnings") or [])],
            version=str(data.get("version") or CONTEXT_SCHEMA_VERSION),
            created_at=float(created_at) if created_at is not None else time.time(),
        )