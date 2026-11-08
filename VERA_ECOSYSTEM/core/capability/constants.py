"""
core/capability/constants.py — Capability Layer constants (Sprint 2.7 / W1).

Single source of truth for the finite vocabularies the Capability Layer
uses: states, permissions, and the context types a capability can declare
support for. Kept separate from models.py so registry/discovery code that
only needs the vocabulary (not the dataclasses) can import lightly - the
same split already used by core/dio (constants.py vs models.py).
"""

# ------------------------------------------------------------ STATES

STATE_REGISTERED = "registered"
STATE_AVAILABLE = "available"
STATE_ENABLED = "enabled"
STATE_DISABLED = "disabled"
STATE_REQUIRES_CONFIRMATION = "requires_confirmation"
STATE_UNAVAILABLE = "unavailable"

VALID_STATES = frozenset({
    STATE_REGISTERED, STATE_AVAILABLE, STATE_ENABLED, STATE_DISABLED,
    STATE_REQUIRES_CONFIRMATION, STATE_UNAVAILABLE,
})

# --------------------------------------------------------- PERMISSIONS

PERMISSION_SAFE = "safe"
PERMISSION_CONFIRMATION_REQUIRED = "confirmation_required"
PERMISSION_RESTRICTED = "restricted"
PERMISSION_UNAVAILABLE = "unavailable"

VALID_PERMISSIONS = frozenset({
    PERMISSION_SAFE, PERMISSION_CONFIRMATION_REQUIRED,
    PERMISSION_RESTRICTED, PERMISSION_UNAVAILABLE,
})

# ------------------------------------------------------ CONTEXT TYPES
# A capability declares which of these contexts it can operate under
# (supported_context). This list is intentionally open-ended - future
# Sprint 2.7 workers add capabilities in these areas, but implementing
# them is explicitly out of scope for W1 (Capability Foundation).

CONTEXT_CONVERSATION = "conversation"
CONTEXT_ATTACHMENT = "attachment"
CONTEXT_SELECTION = "selection"
CONTEXT_ARTIFACT = "artifact"
CONTEXT_WORKSPACE = "workspace"
CONTEXT_LOCATION = "location"
CONTEXT_PERMISSION = "permission"

KNOWN_CONTEXT_TYPES = frozenset({
    CONTEXT_CONVERSATION, CONTEXT_ATTACHMENT, CONTEXT_SELECTION,
    CONTEXT_ARTIFACT, CONTEXT_WORKSPACE, CONTEXT_LOCATION, CONTEXT_PERMISSION,
})

# ------------------------------------------------------------ CATEGORY
# Category groups capabilities for discovery/UI (distinct from context,
# which is about WHEN a capability applies). Open-ended: a capability may
# declare a category outside this default - unknown categories are
# accepted, not rejected.
DEFAULT_CATEGORY = "general"

# --------------------------------------------------------------- EVENTS
# String literals (deliberately NOT added to core.events.EventNames),
# following the established pattern for optional/feature-scoped modules
# publishing to the existing Event Bus without growing the central
# registry (see core/global_settings.py::_publish_settings_changed,
# core/filesystem/operations.py's "file.created", etc.)

EVENT_CAPABILITY_REGISTERED = "capability.registered"
EVENT_CAPABILITY_UPDATED = "capability.updated"
EVENT_CAPABILITY_UNREGISTERED = "capability.unregistered"
EVENT_CAPABILITY_STATE_CHANGED = "capability.state_changed"
EVENT_CAPABILITY_DISCOVERED = "capability.discovered"
