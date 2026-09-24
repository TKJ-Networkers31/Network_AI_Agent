"""
core/external_context/ - External Context Layer (Sprint 2.7 / W7).

Provider-neutral location/context layer. Google Maps is ONE adapter
(core/external_context/google_maps.py) behind the ExternalContextProvider
contract (core/external_context/provider.py) - nothing outside this
package (core/orchestrator.py, core/brain.py, agents/*) is meant to import
google_maps.py directly.

Public API:

    from core.external_context import (
        ExternalContextProvider,
        ProviderIdentity, ProviderCapabilities,
        NormalizedPlace, NormalizedRoute, RouteSegment,
        ExternalContextError, QueryResult,
        GoogleMapsProvider, GoogleMapsConfig, load_google_maps_config,
        get_google_maps_provider, reset_google_maps_provider,
        register_provider_capabilities, unregister_provider_capabilities,
    )

    provider = get_google_maps_provider()
    if provider.is_available():
        result = provider.search("bakso terdekat", location="-6.9,107.6")

This package does not implement: map UI, full turn-by-turn navigation,
Workspace/Attachment/Selection/Artifact/Unified Context, Calendar,
Scheduler, voice, or vision - see the W7 task boundaries. It also does not
create a second Capability registry or a second location/provider
registry - it reuses core.capability.get_capability_registry() and
core.location.location_service respectively (the latter untouched by W7).
"""

from core.external_context.constants import (
    CAPABILITY_CONTEXT,
    CAPABILITY_LABELS,
    CAPABILITY_LOOKUP,
    CAPABILITY_NEARBY,
    CAPABILITY_ROUTE,
    CAPABILITY_SEARCH,
    ERROR_AUTHENTICATION_ERROR,
    ERROR_INVALID_REQUEST,
    ERROR_NO_RESULTS,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_RATE_LIMITED,
    ERROR_TIMEOUT,
    VALID_CAPABILITIES,
    VALID_ERROR_CODES,
)
from core.external_context.models import (
    ExternalContextError,
    NormalizedPlace,
    NormalizedRoute,
    ProviderCapabilities,
    ProviderIdentity,
    QueryResult,
    RouteSegment,
)
from core.external_context.provider import ExternalContextProvider
from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.google_maps import GoogleMapsProvider
from core.external_context.factory import get_google_maps_provider, reset_google_maps_provider
from core.external_context.capability_bridge import (
    capability_id_for,
    register_provider_capabilities,
    unregister_provider_capabilities,
)

__all__ = [
    # capability vocabulary
    "CAPABILITY_SEARCH", "CAPABILITY_LOOKUP", "CAPABILITY_NEARBY",
    "CAPABILITY_ROUTE", "CAPABILITY_CONTEXT", "CAPABILITY_LABELS", "VALID_CAPABILITIES",
    # error vocabulary
    "ERROR_PROVIDER_UNAVAILABLE", "ERROR_INVALID_REQUEST", "ERROR_RATE_LIMITED",
    "ERROR_AUTHENTICATION_ERROR", "ERROR_NO_RESULTS", "ERROR_TIMEOUT", "VALID_ERROR_CODES",
    # models
    "ProviderIdentity", "ProviderCapabilities",
    "NormalizedPlace", "NormalizedRoute", "RouteSegment",
    "ExternalContextError", "QueryResult",
    # contract
    "ExternalContextProvider",
    # google maps adapter
    "GoogleMapsProvider", "GoogleMapsConfig", "load_google_maps_config",
    "get_google_maps_provider", "reset_google_maps_provider",
    # W1 capability bridge
    "capability_id_for", "register_provider_capabilities", "unregister_provider_capabilities",
]
