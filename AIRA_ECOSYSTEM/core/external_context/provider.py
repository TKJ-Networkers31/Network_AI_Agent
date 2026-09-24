"""
core/external_context/provider.py — ExternalContextProvider contract
(Sprint 2.7 / W7).

This is the ONE abstraction every external-context adapter (Google Maps
today; any future provider - OpenStreetMap, Bing Maps, a licensing-plate
lookup, whatever - later) must implement. Nothing in core/orchestrator.py,
core/brain.py, or agents/* is allowed to import a concrete provider
(google_maps.py) directly - only this module's contract, so swapping or
adding a provider never touches the conversation/agent engine (see GOAL).

Design mirrors core/host/*  (HostInfo + per-OS adapter, one contract two
implementations) and core/location/geo.py (never raises for a failed
external call - wraps failure into a typed result) rather than
core/model_router.py's "select one true provider" pattern, because W7
providers are explicitly opt-in/queried, not auto-selected per turn.

A concrete provider MUST implement:
    identity            -> ProviderIdentity            (property)
    capabilities         -> ProviderCapabilities         (property)
    is_available()       -> bool
    _search / _lookup / _nearby / _route / _context     (capability impls)

A concrete provider MUST NOT:
    - raise for an ordinary failure (bad key, rate limit, no results,
      timeout, ...) - wrap it in ExternalContextError and return a
      QueryResult via QueryResult.fail()
    - read process-wide config/env itself beyond what its own __init__
      accepts - see config.py for the one sanctioned place API keys are
      read from
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from core.external_context.constants import (
    CAPABILITY_CONTEXT,
    CAPABILITY_LOOKUP,
    CAPABILITY_NEARBY,
    CAPABILITY_ROUTE,
    CAPABILITY_SEARCH,
    ERROR_INVALID_REQUEST,
    ERROR_PROVIDER_UNAVAILABLE,
)
from core.external_context.models import (
    ExternalContextError,
    ProviderCapabilities,
    ProviderIdentity,
    QueryResult,
)

logger = logging.getLogger("aira.external_context.provider")

# capability name -> the method name a subclass overrides for it.
_CAPABILITY_METHODS = {
    CAPABILITY_SEARCH: "_search",
    CAPABILITY_LOOKUP: "_lookup",
    CAPABILITY_NEARBY: "_nearby",
    CAPABILITY_ROUTE: "_route",
    CAPABILITY_CONTEXT: "_context",
}


class ExternalContextProvider(ABC):
    """
    Base class. Public methods (search/lookup/nearby/route/context/execute)
    are the STABLE surface callers use; they never raise for a normal
    provider-side failure and always funnel through `_guarded_call` so
    "capability not supported by this provider" and "provider not
    available right now" are handled identically for every subclass
    instead of each adapter reinventing that check.
    """

    # ------------------------------------------------------------ identity

    @property
    @abstractmethod
    def identity(self) -> ProviderIdentity:
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """True iff this provider is currently usable (has credentials,
        etc.) - never performs a network call itself; a provider that can
        only know availability via a network round-trip should cache the
        last known result instead of blocking every is_available() call."""
        raise NotImplementedError

    # ------------------------------------------------------------ dispatch

    def execute(self, capability: str, **kwargs) -> QueryResult:
        """Generic dispatcher: capability name -> the matching public
        method. Used by capability_bridge.py so the Capability Layer can
        invoke a provider without knowing its concrete method names."""
        method_name = _CAPABILITY_METHODS.get(capability)

        if method_name is None:
            return QueryResult.fail(
                self._provider_name, capability if capability else CAPABILITY_CONTEXT,
                ExternalContextError(
                    code=ERROR_INVALID_REQUEST,
                    message=f"Capability '{capability}' tidak dikenal.",
                    provider=self._provider_name, capability=capability,
                ),
            )

        bound = getattr(self, method_name.lstrip("_"))
        return bound(**kwargs)

    # ------------------------------------------------------------ public API

    def search(self, query: str, **kwargs) -> QueryResult:
        return self._guarded_call(CAPABILITY_SEARCH, self._search, query=query, **kwargs)

    def lookup(self, place_id: str, **kwargs) -> QueryResult:
        return self._guarded_call(CAPABILITY_LOOKUP, self._lookup, place_id=place_id, **kwargs)

    def nearby(self, latitude: float, longitude: float, **kwargs) -> QueryResult:
        return self._guarded_call(
            CAPABILITY_NEARBY, self._nearby, latitude=latitude, longitude=longitude, **kwargs,
        )

    def route(self, origin: str, destination: str, **kwargs) -> QueryResult:
        return self._guarded_call(
            CAPABILITY_ROUTE, self._route, origin=origin, destination=destination, **kwargs,
        )

    def context(self, latitude: float, longitude: float, **kwargs) -> QueryResult:
        return self._guarded_call(
            CAPABILITY_CONTEXT, self._context, latitude=latitude, longitude=longitude, **kwargs,
        )

    # -------------------------------------------------------- default impls
    # Subclasses override whichever of these they actually support; the
    # defaults report an honest provider_unavailable rather than raising
    # NotImplementedError, so a provider that only implements search()
    # still behaves correctly (a normal QueryResult, not a crash) when
    # asked for a route.

    def _search(self, query: str, **kwargs) -> QueryResult:
        return self._unsupported(CAPABILITY_SEARCH)

    def _lookup(self, place_id: str, **kwargs) -> QueryResult:
        return self._unsupported(CAPABILITY_LOOKUP)

    def _nearby(self, latitude: float, longitude: float, **kwargs) -> QueryResult:
        return self._unsupported(CAPABILITY_NEARBY)

    def _route(self, origin: str, destination: str, **kwargs) -> QueryResult:
        return self._unsupported(CAPABILITY_ROUTE)

    def _context(self, latitude: float, longitude: float, **kwargs) -> QueryResult:
        return self._unsupported(CAPABILITY_CONTEXT)

    # ------------------------------------------------------------ internals

    @property
    def _provider_name(self) -> str:
        try:
            return self.identity.name
        except Exception:
            return "unknown"

    def _unsupported(self, capability: str) -> QueryResult:
        return QueryResult.fail(
            self._provider_name, capability,
            ExternalContextError(
                code=ERROR_INVALID_REQUEST,
                message=f"Provider '{self._provider_name}' tidak mengimplementasikan '{capability}'.",
                provider=self._provider_name, capability=capability,
            ),
        )

    def _guarded_call(self, capability: str, method, **kwargs) -> QueryResult:
        if not self.capabilities.supports(capability):
            return self._unsupported(capability)

        if not self.is_available():
            return QueryResult.fail(
                self._provider_name, capability,
                ExternalContextError(
                    code=ERROR_PROVIDER_UNAVAILABLE,
                    message=f"Provider '{self._provider_name}' tidak tersedia saat ini (belum dikonfigurasi?).",
                    provider=self._provider_name, capability=capability, retryable=True,
                ),
            )

        try:
            result = method(**kwargs)
        except Exception as exc:
            # A provider raising is itself a bug (see class docstring), but
            # a bug in one adapter must never crash the caller - convert it
            # to the same shape a well-behaved failure would produce.
            logger.exception(
                "EXTERNAL CONTEXT | provider '%s' raised during %s (converted to provider_unavailable).",
                self._provider_name, capability,
            )
            return QueryResult.fail(
                self._provider_name, capability,
                ExternalContextError(
                    code=ERROR_PROVIDER_UNAVAILABLE,
                    message=f"Provider gagal tak terduga ({type(exc).__name__}).",
                    provider=self._provider_name, capability=capability, retryable=True,
                ),
            )

        if not isinstance(result, QueryResult):
            # Defensive: a subclass that forgot to wrap its return value in
            # a QueryResult must not silently corrupt the contract.
            logger.error(
                "EXTERNAL CONTEXT | provider '%s' returned %s instead of QueryResult for %s.",
                self._provider_name, type(result).__name__, capability,
            )
            return QueryResult.fail(
                self._provider_name, capability,
                ExternalContextError(
                    code=ERROR_PROVIDER_UNAVAILABLE,
                    message="Provider mengembalikan bentuk data yang tidak valid.",
                    provider=self._provider_name, capability=capability,
                ),
            )

        return result
