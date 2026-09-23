"""
core/capability/frontend.py — frontend-safe Capability serialization
(Sprint 2.7 / W1).

The frontend needs enough to RENDER capabilities (pickers, forms, empty
states) but must never become the source of truth for what a capability
IS or whether it's allowed - that stays server-side (registry +
discovery). This module is a one-way, read-only projection:

    Capability / DiscoveredCapability  ->  frontend-safe dict

There is deliberately no `from_frontend_dict`: any mutation (enable,
disable, confirm) goes back through the registry/discovery API by id, not
through data the frontend sent about itself.

Deliberately DROPPED before reaching the frontend:
    - tool_binding.tool_names / primary_tool  (internal wiring - which
      tool executes this is an implementation detail; only whether ANY
      tool is bound is exposed, via has_tool_binding)
    - metadata                                (free-form backend bag -
      may hold plugin origin, danger flags, etc., not meant for display)
    - registered_at / updated_at              (bookkeeping, not UI-relevant)
"""

from __future__ import annotations

from typing import Any, Optional

from core.capability.discovery import DiscoveredCapability
from core.capability.models import Capability


def capability_to_frontend_dict(capability: Capability, effective_state: Optional[str] = None) -> dict:
    ui = capability.ui

    return {
        "id": capability.id,
        "label": ui.label or capability.name,
        "description": ui.description_short or capability.description,
        "category": capability.category,
        "group": ui.group or capability.category,
        "icon": ui.icon,
        "order": ui.order,
        "hidden": ui.hidden,
        "supported_context": list(capability.supported_context),
        "input_schema": dict(capability.input_schema),
        "output_types": list(capability.output_types),
        "permission": capability.permission,
        "state": effective_state or capability.state,
        "has_tool_binding": not capability.tool_binding.is_empty,
    }


def discovered_to_frontend_dict(discovered: DiscoveredCapability) -> dict:
    return capability_to_frontend_dict(discovered.capability, effective_state=discovered.effective_state)


def capabilities_to_frontend_list(items, *, include_hidden: bool = False) -> list:
    """items: iterable of Capability OR DiscoveredCapability (mixed lists are fine)."""
    out: list = []

    for item in items:
        if isinstance(item, DiscoveredCapability):
            entry = discovered_to_frontend_dict(item)
        elif isinstance(item, Capability):
            entry = capability_to_frontend_dict(item)
        else:
            continue

        if entry["hidden"] and not include_hidden:
            continue

        out.append(entry)

    return out
