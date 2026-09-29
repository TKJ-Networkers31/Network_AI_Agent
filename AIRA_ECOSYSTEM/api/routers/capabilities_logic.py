"""
api/routers/capabilities_logic.py — pure, framework-free logic behind
GET /api/capabilities (Sprint 2.7 / W8 Dynamic Capability API).

Split out from api/routers/capabilities.py so the actual
registry/discovery/serialization logic can be unit-tested without
booting FastAPI, and so the HTTP layer (capabilities.py) stays a thin
adapter, consistent with every other router in api/routers/.

This module does NOT create a second capability registry or discovery
engine - it only projects core.capability's EXISTING
CapabilityRegistry/CapabilityDiscovery output into the flat shape the
Sprint 2.7 W8 frontend (CapabilityContext.jsx / useCapabilities.js)
already expects:

    {"capabilities": [{"id", "area", "label", "icon", "enabled",
                        "disabled_reason", "action"}, ...]}

"area" is derived from the EXISTING Capability.ui.group (falling back to
Capability.category) - core/capability/models.py already documents
`ui.group` as "UI grouping (falls back to Capability.category)", which is
exactly the concept the frontend calls "area" (hero / chat_input /
capability_dock / message_actions / file_actions). No new field is added
to Capability itself.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.capability.constants import (
    CONTEXT_ARTIFACT,
    CONTEXT_ATTACHMENT,
    CONTEXT_CONVERSATION,
    CONTEXT_LOCATION,
    CONTEXT_SELECTION,
    CONTEXT_WORKSPACE,
    STATE_ENABLED,
)
from core.capability.discovery import (
    CapabilityDiscovery,
    DiscoveredCapability,
    DiscoverySettings,
    get_capability_discovery,
)

logger = logging.getLogger("aira.api.capabilities")

# The frontend fetches ONE umbrella scope ("conversation") for the three
# always-visible conversation-level slots and filters client-side by each
# item's own "area" (see app/frontend/src/context/CapabilityContext.jsx:
# `useCapabilities("conversation", context)` + `forArea()`). So an
# area="conversation" query must NOT be filtered down to a single area -
# it returns every conversation-scoped capability, each still tagged with
# its own real area, exactly like the frontend already assumes.
CONVERSATION_SCOPE_AREAS = frozenset({"conversation", "hero", "chat_input", "capability_dock"})

_REASON_LABELS = {
    "disabled": "Kapabilitas ini sedang dinonaktifkan.",
    "permission_unavailable": "Kapabilitas ini tidak tersedia di lingkungan ini.",
    "context_mismatch": "Kapabilitas ini tidak berlaku untuk konteks saat ini.",
    "tool_unavailable": "Tool pendukung kapabilitas ini tidak tersedia.",
    "confirmation_required": "Perlu konfirmasi sebelum kapabilitas ini bisa dipakai.",
}


def _reason_label(reasons: list) -> Optional[str]:
    for reason in reasons:
        key = reason.split(":", 1)[0]
        if key in _REASON_LABELS:
            return _REASON_LABELS[key]
    return reasons[0] if reasons else None


def build_context_signals(
    *,
    has_attachment: bool = False,
    has_artifact: bool = False,
    has_location: bool = False,
    has_selection: bool = False,
    file_path: Optional[str] = None,
) -> frozenset:
    """Capability signals (from CapabilityContext.jsx / per-message /
    per-file hooks) -> the EXISTING core.capability context vocabulary.
    Conversation context is always included: every request to this
    endpoint originates from an active conversation turn."""
    context = {CONTEXT_CONVERSATION}

    if has_attachment:
        context.add(CONTEXT_ATTACHMENT)
    if has_artifact:
        context.add(CONTEXT_ARTIFACT)
    if has_location:
        context.add(CONTEXT_LOCATION)
    if has_selection:
        context.add(CONTEXT_SELECTION)
    if file_path:
        context.add(CONTEXT_WORKSPACE)

    return frozenset(context)


def resolve_area(discovered: DiscoveredCapability) -> str:
    ui = discovered.capability.ui
    return (ui.group or discovered.capability.category or "general").strip() or "general"


def resolve_action(discovered):
    capability = discovered.capability
    meta = capability.metadata.get("action")
    if isinstance(meta, dict):
        return {**meta, "capability_id": capability.id, "permission": capability.permission}
    action = {"capability_id": capability.id, "permission": capability.permission}
    if not capability.tool_binding.is_empty:
        action.update(type="tool", tool=capability.tool_binding.primary_tool)
    else:
        action["type"] = "capability"
    return action


def discovered_to_payload(discovered: DiscoveredCapability) -> dict:
    capability = discovered.capability
    ui = capability.ui
    enabled = discovered.effective_state == STATE_ENABLED

    return {
        "id": capability.id,
        "area": resolve_area(discovered),
        "label": ui.label or capability.name,
        "icon": ui.icon,
        "enabled": enabled,
        "disabled_reason": None if enabled else _reason_label(discovered.reasons),
        "action": resolve_action(discovered),
    }


def list_capabilities(
    *,
    area: Optional[str] = None,
    message_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    has_attachment: bool = False,
    has_artifact: bool = False,
    has_location: bool = False,
    has_selection: bool = False,
    file_path: Optional[str] = None,
    available_tools: Optional[Any] = None,
    discovery: Optional[CapabilityDiscovery] = None,
) -> list:
    """
    Compute the frontend-facing capability list for one W8 area.

    message_id / conversation_id / role are accepted (matching what the
    frontend already sends per area - conversation-level vs
    message_actions vs file_actions requests) but do not gate discovery
    themselves today; no Capability currently declares a dependency on
    them. Accepting and ignoring is intentional: the goal here is to stop
    the endpoint 404ing and return a schema-correct, discovery-backed
    response, not to invent new per-message/per-role capability gating
    that Sprint 2.7 W8 never specified.

    Never raises: a broken registry/discovery call is logged and treated
    as "no capabilities available" (an empty list), matching the
    defensive "never crash the caller" convention used throughout
    core/capability and the other engines in this codebase.
    """
    engine = discovery or get_capability_discovery()
    context = build_context_signals(
        has_attachment=has_attachment, has_artifact=has_artifact,
        has_location=has_location, has_selection=has_selection, file_path=file_path,
    )

    try:
        discovered = engine.discover(
            context=context,
            available_tools=available_tools,
            settings=DiscoverySettings(),
            resolve_enablement=True,
            include_unavailable=True,  # so disabled_reason can be populated
        )
    except Exception:
        logger.exception("CAPABILITIES API | discovery gagal - mengembalikan daftar kosong.")
        return []

    payloads = [discovered_to_payload(d) for d in discovered]

    normalized_area = (area or "").strip()

    if not normalized_area:
        return payloads

    if normalized_area in CONVERSATION_SCOPE_AREAS:
        return [p for p in payloads if p["area"] in CONVERSATION_SCOPE_AREAS]

    return [p for p in payloads if p["area"] == normalized_area]
