"""
core/external_context/google_maps.py — Google Maps adapter for the
External Context Layer (Sprint 2.7 / W7).

This is the ONLY module in the External Context Layer that knows Google's
endpoint shapes/status codes. Everything else (provider.py, models.py,
capability_bridge.py, and any future caller such as an agent tool) talks
to it exclusively through the ExternalContextProvider contract - swapping
Google Maps for another provider never touches those modules.

HTTP is injected via `fetcher` (Dependency Injection, same convention as
core/context/builder.py::ContextBuilder and
core/selection/builder.py::SelectionBuilder's message_lookup) so tests run
against canned responses with zero live network calls - see
tests/test_google_maps.py. The default fetcher uses `requests`, mirroring
core/location/geo.py::_get_json (same timeout/User-Agent discipline).

Endpoints used (Google Maps Platform, all read-only GET):
    Places Text Search   -> search()
    Place Details        -> lookup()
    Places Nearby Search  -> nearby()
    Directions            -> route()
    Geocoding (reverse)   -> context()  (best-effort locality summary)

Every method maps Google's own `status` field to our closed error
vocabulary (core.external_context.constants.VALID_ERROR_CODES) - Google's
strings are never passed through as-is to a QueryResult.error.code.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.constants import (
    CAPABILITY_CONTEXT,
    CAPABILITY_LOOKUP,
    CAPABILITY_NEARBY,
    CAPABILITY_ROUTE,
    CAPABILITY_SEARCH,
    DEFAULT_NEARBY_RADIUS_METERS,
    DEFAULT_ROUTE_MODE,
    ERROR_AUTHENTICATION_ERROR,
    ERROR_INVALID_REQUEST,
    ERROR_NO_RESULTS,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_RATE_LIMITED,
    ERROR_TIMEOUT,
    VALID_ROUTE_MODES,
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

logger = logging.getLogger("aira.external_context.google_maps")

PROVIDER_NAME = "google_maps"
PROVIDER_DISPLAY_NAME = "Google Maps"

BASE_URL = "https://maps.googleapis.com/maps/api"
TEXT_SEARCH_URL = f"{BASE_URL}/place/textsearch/json"
PLACE_DETAILS_URL = f"{BASE_URL}/place/details/json"
NEARBY_SEARCH_URL = f"{BASE_URL}/place/nearbysearch/json"
DIRECTIONS_URL = f"{BASE_URL}/directions/json"
GEOCODE_URL = f"{BASE_URL}/geocode/json"

USER_AGENT = "AIRA-OS/1.0 (external-context/google-maps)"

# Google Places/Directions `status` field -> our closed error vocabulary.
# ZERO_RESULTS is intentionally NOT an error at the transport level for
# every capability (an empty list can be a valid, successful answer) -
# each method below decides whether ZERO_RESULTS means "no_results error"
# or "success with an empty list", per capability semantics.
_STATUS_ERROR_MAP = {
    "REQUEST_DENIED": ERROR_AUTHENTICATION_ERROR,
    "OVER_QUERY_LIMIT": ERROR_RATE_LIMITED,
    "INVALID_REQUEST": ERROR_INVALID_REQUEST,
    "NOT_FOUND": ERROR_NO_RESULTS,
    "UNKNOWN_ERROR": ERROR_PROVIDER_UNAVAILABLE,
}

Fetcher = Callable[[str, dict], dict]


def _default_fetcher(url: str, params: dict) -> dict:
    """requests-backed fetcher. Only imported lazily so this module (and
    therefore the whole External Context Layer) stays importable in
    environments without `requests` installed for unrelated reasons -
    tests never reach this function because they inject their own
    fetcher."""
    import requests

    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
    response.raise_for_status()
    return response.json()


class GoogleMapsTimeout(Exception):
    """Raised by a fetcher to signal a timeout distinctly from other
    transport failures, so GoogleMapsProvider can map it to
    ERROR_TIMEOUT specifically instead of the generic
    ERROR_PROVIDER_UNAVAILABLE. The default fetcher raises this by
    catching requests.exceptions.Timeout; a test fetcher can raise it
    directly."""


class GoogleMapsProvider(ExternalContextProvider):
    """
    Google Maps Platform adapter. Construction never raises - an
    unconfigured provider (no API key) is a normal, representable state
    (is_available() == False), not an error, following the same
    philosophy as core/location/service.py returning None rather than
    raising when the host location isn't known yet.
    """

    def __init__(
        self,
        config: Optional[GoogleMapsConfig] = None,
        fetcher: Optional[Fetcher] = None,
    ):
        self._config = config if config is not None else load_google_maps_config()
        self._fetcher: Fetcher = fetcher or _default_fetcher

    # ------------------------------------------------------------ identity

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name=PROVIDER_NAME, display_name=PROVIDER_DISPLAY_NAME, version="1.0")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capabilities=(
            CAPABILITY_SEARCH, CAPABILITY_LOOKUP, CAPABILITY_NEARBY,
            CAPABILITY_ROUTE, CAPABILITY_CONTEXT,
        ))

    def is_available(self) -> bool:
        return self._config.is_configured

    @property
    def config(self) -> GoogleMapsConfig:
        """Read-only access for callers that want to display configuration
        state (e.g. a settings page) - api_key itself stays out of
        GoogleMapsConfig.to_dict(), see config.py."""
        return self._config

    # -------------------------------------------------------------- fetch

    def _get(self, url: str, params: dict) -> tuple[Optional[dict], Optional[ExternalContextError]]:
        """One HTTP call -> (json_data, None) on success, or (None, error)
        on any failure - transport, timeout, or a non-OK Google `status`.
        Centralizes exception -> ExternalContextError mapping so every
        capability method below only deals with already-typed errors."""
        request_params = {**params, "key": self._config.api_key}

        try:
            data = self._fetcher(url, request_params)
        except GoogleMapsTimeout as exc:
            return None, ExternalContextError(
                code=ERROR_TIMEOUT, message=f"Permintaan ke Google Maps timeout: {exc}",
                provider=PROVIDER_NAME, retryable=True,
            )
        except Exception as exc:
            # Import lazily to avoid a hard dependency on `requests` at
            # module load time (see _default_fetcher docstring).
            try:
                import requests
                if isinstance(exc, requests.exceptions.Timeout):
                    return None, ExternalContextError(
                        code=ERROR_TIMEOUT, message=f"Permintaan ke Google Maps timeout: {exc}",
                        provider=PROVIDER_NAME, retryable=True,
                    )
            except ImportError:
                pass

            return None, ExternalContextError(
                code=ERROR_PROVIDER_UNAVAILABLE,
                message=f"Gagal menghubungi Google Maps ({type(exc).__name__}): {exc}",
                provider=PROVIDER_NAME, retryable=True,
            )

        if not isinstance(data, dict):
            return None, ExternalContextError(
                code=ERROR_PROVIDER_UNAVAILABLE,
                message="Respons Google Maps bukan JSON object yang valid.",
                provider=PROVIDER_NAME, retryable=True,
            )

        status = str(data.get("status") or "UNKNOWN_ERROR")

        if status in ("OK", "ZERO_RESULTS"):
            return data, None

        code = _STATUS_ERROR_MAP.get(status, ERROR_PROVIDER_UNAVAILABLE)

        return None, ExternalContextError(
            code=code,
            message=str(data.get("error_message") or f"Google Maps status: {status}"),
            provider=PROVIDER_NAME,
            retryable=code in (ERROR_PROVIDER_UNAVAILABLE, ERROR_RATE_LIMITED, ERROR_TIMEOUT),
            details={"google_status": status},
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _place_from_result(entry: dict, distance_meters: Optional[float] = None) -> NormalizedPlace:
        location = ((entry.get("geometry") or {}).get("location")) or {}

        return NormalizedPlace(
            id=str(entry.get("place_id") or ""),
            name=str(entry.get("name") or entry.get("formatted_address") or "Tempat tanpa nama"),
            address=entry.get("formatted_address") or entry.get("vicinity"),
            latitude=location.get("lat"),
            longitude=location.get("lng"),
            distance_meters=distance_meters,
            metadata={
                k: v for k, v in {
                    "rating": entry.get("rating"),
                    "user_ratings_total": entry.get("user_ratings_total"),
                    "types": entry.get("types"),
                    "business_status": entry.get("business_status"),
                    "open_now": ((entry.get("opening_hours") or {}).get("open_now")),
                }.items() if v is not None
            },
        )

    # ------------------------------------------------------------ search

    def _search(self, query: str, location: Optional[str] = None, radius: Optional[int] = None, **kwargs) -> QueryResult:
        query = (query or "").strip()

        if not query:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="query tidak boleh kosong.",
                provider=PROVIDER_NAME, capability=CAPABILITY_SEARCH,
            ))

        params: dict[str, Any] = {"query": query}
        if location:
            params["location"] = location
        if radius:
            params["radius"] = radius

        data, error = self._get(TEXT_SEARCH_URL, params)

        if error is not None:
            error.capability = CAPABILITY_SEARCH
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_SEARCH, error)

        results = data.get("results") or []
        places = [self._place_from_result(r) for r in results]

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_SEARCH, places=places, metadata={"query": query})

    # ------------------------------------------------------------ lookup

    def _lookup(self, place_id: str, **kwargs) -> QueryResult:
        place_id = (place_id or "").strip()

        if not place_id:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="place_id tidak boleh kosong.",
                provider=PROVIDER_NAME, capability=CAPABILITY_LOOKUP,
            ))

        data, error = self._get(PLACE_DETAILS_URL, {"place_id": place_id})

        if error is not None:
            error.capability = CAPABILITY_LOOKUP
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, error)

        result = data.get("result")

        if not result:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_LOOKUP, ExternalContextError(
                code=ERROR_NO_RESULTS, message=f"place_id '{place_id}' tidak ditemukan.",
                provider=PROVIDER_NAME, capability=CAPABILITY_LOOKUP,
            ))

        place = self._place_from_result(result)

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_LOOKUP, places=[place])

    # ------------------------------------------------------------ nearby

    def _nearby(
        self, latitude: float, longitude: float,
        radius: int = DEFAULT_NEARBY_RADIUS_METERS, keyword: Optional[str] = None, **kwargs,
    ) -> QueryResult:
        if latitude is None or longitude is None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="latitude dan longitude wajib diisi.",
                provider=PROVIDER_NAME, capability=CAPABILITY_NEARBY,
            ))

        params: dict[str, Any] = {"location": f"{latitude},{longitude}", "radius": radius}
        if keyword:
            params["keyword"] = keyword

        data, error = self._get(NEARBY_SEARCH_URL, params)

        if error is not None:
            error.capability = CAPABILITY_NEARBY
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_NEARBY, error)

        results = data.get("results") or []
        places = [self._place_from_result(r) for r in results]

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_NEARBY, places=places,
            metadata={"latitude": latitude, "longitude": longitude, "radius": radius},
        )

    # ------------------------------------------------------------- route

    def _route(self, origin: str, destination: str, mode: str = DEFAULT_ROUTE_MODE, **kwargs) -> QueryResult:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        mode = (mode or DEFAULT_ROUTE_MODE).strip().lower()

        if not origin or not destination:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="origin dan destination wajib diisi.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        if mode not in VALID_ROUTE_MODES:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_INVALID_REQUEST,
                message=f"mode '{mode}' tidak dikenal. Pilihan: {sorted(VALID_ROUTE_MODES)}.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        data, error = self._get(DIRECTIONS_URL, {"origin": origin, "destination": destination, "mode": mode})

        if error is not None:
            error.capability = CAPABILITY_ROUTE
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, error)

        routes = data.get("routes") or []

        if not routes:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_ROUTE, ExternalContextError(
                code=ERROR_NO_RESULTS,
                message=f"Tidak ada rute dari '{origin}' ke '{destination}'.",
                provider=PROVIDER_NAME, capability=CAPABILITY_ROUTE,
            ))

        legs = (routes[0].get("legs") or [])[:1]
        leg = legs[0] if legs else {}

        segments = [
            RouteSegment(
                instruction=_strip_html(step.get("html_instructions") or ""),
                distance_meters=(step.get("distance") or {}).get("value"),
                duration_seconds=(step.get("duration") or {}).get("value"),
            )
            for step in (leg.get("steps") or [])
        ]

        normalized = NormalizedRoute(
            origin=origin, destination=destination,
            distance_meters=(leg.get("distance") or {}).get("value"),
            duration_seconds=(leg.get("duration") or {}).get("value"),
            segments=segments,
            metadata={"mode": mode, "summary": routes[0].get("summary")},
        )

        return QueryResult.ok(PROVIDER_NAME, CAPABILITY_ROUTE, route=normalized)

    # ----------------------------------------------------------- context

    def _context(self, latitude: float, longitude: float, radius: int = 500, **kwargs) -> QueryResult:
        """Best-effort "what's around here" summary: reverse-geocodes the
        coordinate for an address label, then folds in a small nearby()
        list as metadata. This is intentionally NOT a full place detail
        or a map UI (see BOUNDARIES) - just enough for a text answer like
        "you're near X, close to Y and Z"."""
        if latitude is None or longitude is None:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, ExternalContextError(
                code=ERROR_INVALID_REQUEST, message="latitude dan longitude wajib diisi.",
                provider=PROVIDER_NAME, capability=CAPABILITY_CONTEXT,
            ))

        geo_data, geo_error = self._get(GEOCODE_URL, {"latlng": f"{latitude},{longitude}"})

        if geo_error is not None:
            geo_error.capability = CAPABILITY_CONTEXT
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, geo_error)

        geo_results = geo_data.get("results") or []

        if not geo_results:
            return QueryResult.fail(PROVIDER_NAME, CAPABILITY_CONTEXT, ExternalContextError(
                code=ERROR_NO_RESULTS,
                message=f"Tidak ada informasi lokasi untuk {latitude},{longitude}.",
                provider=PROVIDER_NAME, capability=CAPABILITY_CONTEXT,
            ))

        primary = self._place_from_result(geo_results[0])
        primary.metadata["role"] = "reverse_geocode"

        nearby_result = self._nearby(latitude, longitude, radius=radius)
        nearby_names = [p.name for p in nearby_result.places[:5]] if nearby_result.success else []

        return QueryResult.ok(
            PROVIDER_NAME, CAPABILITY_CONTEXT, places=[primary],
            metadata={"latitude": latitude, "longitude": longitude, "nearby": nearby_names},
        )


def _strip_html(text: str) -> str:
    """Google's `html_instructions` contains simple inline tags (<b>, <div>).
    Minimal, dependency-free strip - not a general HTML sanitizer."""
    out = []
    in_tag = False

    for ch in text:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            out.append(ch)

    return "".join(out).strip()
