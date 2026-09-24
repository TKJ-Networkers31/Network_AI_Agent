"""
core/external_context/factory.py — provider singleton accessors
(Sprint 2.7 / W7).

Deliberately NOT a registry: this is the same "one function per singleton"
shape already used throughout the codebase (core.model_router.get_model_router,
core.filesystem.workspace.get_workspace_manager,
core.location.store.get_host_store, ...) - a plain lazy-constructed
module-level instance behind a getter, with a lock, nothing more. There is
no generic "get_provider(name)" indirection and no dynamic
registration/discovery of providers here; adding a second provider later
means adding one more get_<name>_provider() function, exactly the way
model_registry.VALID_PROVIDERS growing by one entry doesn't require a
"provider registry" of its own (see core/model_registry.py's own comment
to that effect).
"""

from __future__ import annotations

import threading
from typing import Optional

from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.google_maps import GoogleMapsProvider

_google_maps_singleton: Optional[GoogleMapsProvider] = None
_google_maps_lock = threading.Lock()


def get_google_maps_provider(config: Optional[GoogleMapsConfig] = None) -> GoogleMapsProvider:
    """
    Lazy singleton, built from the environment on first use (see
    core/external_context/config.py). Passing an explicit `config`
    forces a fresh instance instead of the singleton - callers that need
    a specific configuration (e.g. tests) should construct
    GoogleMapsProvider(config=...) directly rather than going through this
    accessor at all; this function exists for the common "just give me
    whatever the environment configured" case (mirrors
    core.model_router.get_model_router()'s no-argument singleton use).
    """
    global _google_maps_singleton

    if config is not None:
        return GoogleMapsProvider(config=config)

    if _google_maps_singleton is None:
        with _google_maps_lock:
            if _google_maps_singleton is None:
                _google_maps_singleton = GoogleMapsProvider(config=load_google_maps_config())

    return _google_maps_singleton


def reset_google_maps_provider() -> None:
    """Drop the cached singleton so the next get_google_maps_provider()
    call re-reads the environment. Mainly for tests that mutate env vars
    between cases; not exposed over HTTP."""
    global _google_maps_singleton

    with _google_maps_lock:
        _google_maps_singleton = None
