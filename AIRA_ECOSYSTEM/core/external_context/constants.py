"""
core/external_context/constants.py — External Context Layer constants
(Sprint 2.7 / W7).

Single source of truth for the capability vocabulary an external-context
PROVIDER can implement, and the error-code vocabulary every provider must
report failures through. Kept separate from models.py/provider.py so
anything that only needs the vocabulary (e.g. a future UI) can import
lightly, mirroring the split already used by core/dio/constants.py and
core/capability/constants.py.

IMPORTANT: this is a DIFFERENT vocabulary from core.capability.constants
(STATE_*/PERMISSION_*/CONTEXT_*). Those describe "what AIRA can do" at the
Capability Layer (W1). The names below describe "what an external-context
PROVIDER (e.g. Google Maps) can be asked for" - a provider capability is
exposed to the Capability Layer as one Capability per name below (see
capability_bridge.py), it does not replace or extend W1's own vocabulary.
"""

# ------------------------------------------------------ PROVIDER CAPABILITIES

CAPABILITY_SEARCH = "location.search"
CAPABILITY_LOOKUP = "location.lookup"
CAPABILITY_NEARBY = "location.nearby"
CAPABILITY_ROUTE = "location.route"
CAPABILITY_CONTEXT = "location.context"

VALID_CAPABILITIES = frozenset({
    CAPABILITY_SEARCH, CAPABILITY_LOOKUP, CAPABILITY_NEARBY,
    CAPABILITY_ROUTE, CAPABILITY_CONTEXT,
})

CAPABILITY_LABELS = {
    CAPABILITY_SEARCH: "Cari tempat (text search)",
    CAPABILITY_LOOKUP: "Detail satu tempat (by id)",
    CAPABILITY_NEARBY: "Tempat di sekitar koordinat",
    CAPABILITY_ROUTE: "Rute antar dua titik",
    CAPABILITY_CONTEXT: "Ringkasan konteks sekitar satu koordinat",
}

# ------------------------------------------------------------- ERROR CODES

ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_INVALID_REQUEST = "invalid_request"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_AUTHENTICATION_ERROR = "authentication_error"
ERROR_NO_RESULTS = "no_results"
ERROR_TIMEOUT = "timeout"

VALID_ERROR_CODES = frozenset({
    ERROR_PROVIDER_UNAVAILABLE, ERROR_INVALID_REQUEST, ERROR_RATE_LIMITED,
    ERROR_AUTHENTICATION_ERROR, ERROR_NO_RESULTS, ERROR_TIMEOUT,
})

# Error codes that a caller may reasonably retry (transient); used only as
# a default hint on ExternalContextError.retryable, callers may override.
RETRYABLE_ERROR_CODES = frozenset({
    ERROR_PROVIDER_UNAVAILABLE, ERROR_RATE_LIMITED, ERROR_TIMEOUT,
})

DEFAULT_TIMEOUT_SECONDS = 6.0
DEFAULT_NEARBY_RADIUS_METERS = 1500
DEFAULT_ROUTE_MODE = "driving"

VALID_ROUTE_MODES = frozenset({"driving", "walking", "bicycling", "transit"})
