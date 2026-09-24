"""
core/external_context/models.py — External Context Layer data contract
(Sprint 2.7 / W7).

Pure data + serialization, no I/O, no network, no provider-specific
knowledge (same split as core/dio/models.py and core/capability/models.py:
dataclasses build tolerant objects, validation/execution live elsewhere).

    ProviderIdentity      - who a provider is (name/display_name/version)
    ProviderCapabilities  - what capability names a provider implements
    NormalizedPlace       - provider-agnostic "place" shape
    NormalizedRoute       - provider-agnostic "route" shape
    ExternalContextError  - provider-agnostic error shape (see constants.py
                            for the closed vocabulary of `code`)
    QueryResult           - envelope returned by every provider call:
                            success xor error, tagged with provider +
                            capability so callers/logs never need to guess
                            which provider/capability produced a result.

No Capability instance, Event, or SQLite row is built here - that is
capability_bridge.py's and the provider's job respectively.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core.external_context.constants import (
    RETRYABLE_ERROR_CODES,
    VALID_CAPABILITIES,
    VALID_ERROR_CODES,
)


def _clean(data: dict) -> dict:
    """Drop None-valued keys - consistent with core/dio/models.py::_clean
    and core/plugins/models.py::_clean."""
    return {k: v for k, v in data.items() if v is not None}


# ============================================================ IDENTITY

@dataclass(frozen=True)
class ProviderIdentity:
    """Who a provider is. `name` is the stable machine id (e.g.
    'google_maps') used as the dict key everywhere a provider is looked up
    by name; `display_name` is for humans/UI."""

    name: str
    display_name: str
    version: str = "1.0"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCapabilities:
    """What capability names (constants.CAPABILITY_*) a provider
    implements. Unknown/invalid names are silently dropped at
    construction - a provider declaring a typo'd capability should fail
    loudly at test time, not corrupt the vocabulary at runtime."""

    capabilities: tuple = ()

    def __post_init__(self) -> None:
        cleaned = tuple(
            c for c in (self.capabilities or ())
            if isinstance(c, str) and c in VALID_CAPABILITIES
        )
        object.__setattr__(self, "capabilities", cleaned)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def to_dict(self) -> dict:
        return {"capabilities": list(self.capabilities)}


# ============================================================ NORMALIZED PLACE

@dataclass
class NormalizedPlace:
    """Provider-agnostic place shape. `id` is the PROVIDER's own place id
    (opaque outside that provider - a lookup() call must pass it back to
    the SAME provider it came from). `distance_meters` is only populated
    for nearby()-style results where a reference point exists; None
    otherwise (never 0 as a stand-in for "unknown")."""

    id: str
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_meters: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = _clean({
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_meters": self.distance_meters,
        })
        data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NormalizedPlace":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            address=data.get("address"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            distance_meters=data.get("distance_meters"),
            metadata=dict(data.get("metadata") or {}),
        )


# ============================================================ NORMALIZED ROUTE

@dataclass
class RouteSegment:
    """One leg/step of a route. Kept intentionally small (provider-neutral
    turn-by-turn is out of scope for W7 - see BOUNDARIES) - `instruction`
    is a plain-text hint, not a structured maneuver."""

    instruction: str = ""
    distance_meters: Optional[float] = None
    duration_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return _clean(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> "RouteSegment":
        data = data if isinstance(data, dict) else {}
        return cls(
            instruction=str(data.get("instruction") or ""),
            distance_meters=data.get("distance_meters"),
            duration_seconds=data.get("duration_seconds"),
        )


@dataclass
class NormalizedRoute:
    """Provider-agnostic route shape. `origin`/`destination` are echoed
    back as given by the caller (string address or "lat,lon"), not
    re-geocoded here - a provider may enrich them into NormalizedPlace-like
    dicts via `metadata` if it has that detail."""

    origin: str
    destination: str
    distance_meters: Optional[float] = None
    duration_seconds: Optional[float] = None
    segments: list[RouteSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_meters": self.distance_meters,
            "duration_seconds": self.duration_seconds,
            "segments": [s.to_dict() for s in self.segments],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NormalizedRoute":
        data = data if isinstance(data, dict) else {}
        raw_segments = data.get("segments") or []
        return cls(
            origin=str(data.get("origin") or ""),
            destination=str(data.get("destination") or ""),
            distance_meters=data.get("distance_meters"),
            duration_seconds=data.get("duration_seconds"),
            segments=[RouteSegment.from_dict(s) for s in raw_segments if isinstance(s, dict)],
            metadata=dict(data.get("metadata") or {}),
        )


# ============================================================ ERROR

@dataclass
class ExternalContextError:
    """Provider-agnostic error shape. `code` MUST be one of
    constants.VALID_ERROR_CODES - callers branch on `code`, never on
    `message` (message is for logs/humans only, not control flow)."""

    code: str
    message: str
    provider: Optional[str] = None
    capability: Optional[str] = None
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in VALID_ERROR_CODES:
            # Unknown code from a misbehaving provider adapter is itself a
            # provider_unavailable condition - never let it escape as an
            # opaque/unvalidated string a caller might silently mishandle.
            self.details = {**self.details, "_original_code": self.code}
            self.code = "provider_unavailable"

        if not isinstance(self.details, dict):
            self.details = {}

    @property
    def is_retryable_by_default(self) -> bool:
        return self.code in RETRYABLE_ERROR_CODES

    def to_dict(self) -> dict:
        data = _clean({
            "code": self.code,
            "message": self.message,
            "provider": self.provider,
            "capability": self.capability,
        })
        data["retryable"] = self.retryable
        data["details"] = dict(self.details)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExternalContextError":
        data = data if isinstance(data, dict) else {}
        return cls(
            code=str(data.get("code") or "provider_unavailable"),
            message=str(data.get("message") or ""),
            provider=data.get("provider"),
            capability=data.get("capability"),
            retryable=bool(data.get("retryable", False)),
            details=dict(data.get("details") or {}),
        )


# ============================================================ QUERY RESULT

@dataclass
class QueryResult:
    """
    Envelope every ExternalContextProvider method returns. Exactly one of
    (places / route) is meaningfully populated depending on `capability`;
    `error` is set iff success is False. Never raise from provider code to
    signal a normal failure (rate limit, no results, ...) - wrap it in an
    ExternalContextError and return a QueryResult instead; raising is
    reserved for programmer errors (bad arguments to the Python API
    itself), same convention as core/dio (analyzer/builder never raise for
    bad *user* input, only validator flags it).
    """

    success: bool
    provider: str
    capability: str
    places: list[NormalizedPlace] = field(default_factory=list)
    route: Optional[NormalizedRoute] = None
    error: Optional[ExternalContextError] = None
    queried_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.capability not in VALID_CAPABILITIES:
            # Same defensive normalization as ExternalContextError.code -
            # an invalid capability name from a provider is a bug in that
            # provider, but a QueryResult must still serialize safely.
            self.metadata = {**self.metadata, "_original_capability": self.capability}
            self.capability = self.capability if self.capability in VALID_CAPABILITIES else "location.context"

        if self.success and self.error is not None:
            self.error = None

        if not self.success and self.error is None:
            self.error = ExternalContextError(
                code="provider_unavailable",
                message="Provider melaporkan gagal tanpa detail error.",
                provider=self.provider,
                capability=self.capability,
            )

    @property
    def is_empty(self) -> bool:
        return self.success and not self.places and self.route is None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "capability": self.capability,
            "places": [p.to_dict() for p in self.places],
            "route": self.route.to_dict() if self.route is not None else None,
            "error": self.error.to_dict() if self.error is not None else None,
            "queried_at": self.queried_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueryResult":
        data = data if isinstance(data, dict) else {}
        raw_places = data.get("places") or []
        raw_route = data.get("route")
        raw_error = data.get("error")

        return cls(
            success=bool(data.get("success", False)),
            provider=str(data.get("provider") or ""),
            capability=str(data.get("capability") or ""),
            places=[NormalizedPlace.from_dict(p) for p in raw_places if isinstance(p, dict)],
            route=NormalizedRoute.from_dict(raw_route) if isinstance(raw_route, dict) else None,
            error=ExternalContextError.from_dict(raw_error) if isinstance(raw_error, dict) else None,
            queried_at=float(data.get("queried_at") or time.time()),
            metadata=dict(data.get("metadata") or {}),
        )

    # ------------------------------------------------------------ helpers

    @classmethod
    def ok(
        cls, provider: str, capability: str, *,
        places: Optional[list[NormalizedPlace]] = None,
        route: Optional[NormalizedRoute] = None,
        metadata: Optional[dict] = None,
    ) -> "QueryResult":
        return cls(
            success=True, provider=provider, capability=capability,
            places=list(places or []), route=route, metadata=dict(metadata or {}),
        )

    @classmethod
    def fail(
        cls, provider: str, capability: str, error: ExternalContextError,
    ) -> "QueryResult":
        return cls(success=False, provider=provider, capability=capability, error=error)
