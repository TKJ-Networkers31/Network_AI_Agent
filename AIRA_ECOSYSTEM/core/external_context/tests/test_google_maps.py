"""
core/external_context/tests/test_google_maps.py — unit tests for the
Google Maps adapter (Sprint 2.7 / W7). Every HTTP call is replaced by an
injected fake fetcher - no live Google API request is ever made here.

Run from AIRA_ECOSYSTEM/:
    python -m unittest core.external_context.tests.test_google_maps -v
"""

import unittest

from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.constants import (
    CAPABILITY_CONTEXT,
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
)
from core.external_context.google_maps import GoogleMapsProvider, GoogleMapsTimeout


def _config(api_key="fake-key", enabled=True) -> GoogleMapsConfig:
    return GoogleMapsConfig(api_key=api_key, enabled=enabled)


class _ScriptedFetcher:
    """Deterministic fake fetcher: url substring -> canned response (dict)
    or an Exception instance to raise. Records every call for assertions."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list = []

    def __call__(self, url: str, params: dict) -> dict:
        self.calls.append((url, params))

        for substring, outcome in self.routes.items():
            if substring in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        raise AssertionError(f"No scripted response for url={url}")


TEXT_SEARCH_OK = {
    "status": "OK",
    "results": [
        {
            "place_id": "p1", "name": "Warung Bakso Pak Budi",
            "formatted_address": "Jl. Merdeka 1",
            "geometry": {"location": {"lat": -6.9, "lng": 107.6}},
            "rating": 4.5, "user_ratings_total": 120,
        },
    ],
}

PLACE_DETAILS_OK = {
    "status": "OK",
    "result": {
        "place_id": "p1", "name": "Warung Bakso Pak Budi",
        "formatted_address": "Jl. Merdeka 1",
        "geometry": {"location": {"lat": -6.9, "lng": 107.6}},
    },
}

NEARBY_OK = {
    "status": "OK",
    "results": [
        {"place_id": "p2", "name": "Kopi Kenangan", "vicinity": "Jl. Asia Afrika",
         "geometry": {"location": {"lat": -6.91, "lng": 107.61}}},
    ],
}

DIRECTIONS_OK = {
    "status": "OK",
    "routes": [{
        "summary": "Jl. Asia Afrika",
        "legs": [{
            "distance": {"value": 5000}, "duration": {"value": 600},
            "steps": [
                {"html_instructions": "Belok <b>kanan</b> ke Jl. Asia Afrika",
                 "distance": {"value": 2000}, "duration": {"value": 300}},
                {"html_instructions": "Lurus terus",
                 "distance": {"value": 3000}, "duration": {"value": 300}},
            ],
        }],
    }],
}

GEOCODE_OK = {
    "status": "OK",
    "results": [{
        "place_id": "g1", "formatted_address": "Jl. Merdeka, Bandung",
        "geometry": {"location": {"lat": -6.9, "lng": 107.6}},
    }],
}


class TestIdentityAndCapabilities(unittest.TestCase):

    def test_identity(self):
        provider = GoogleMapsProvider(config=_config())
        self.assertEqual(provider.identity.name, "google_maps")
        self.assertEqual(provider.identity.display_name, "Google Maps")

    def test_capabilities_cover_all_five(self):
        provider = GoogleMapsProvider(config=_config())
        for cap in (CAPABILITY_SEARCH, CAPABILITY_LOOKUP, CAPABILITY_NEARBY, CAPABILITY_ROUTE, CAPABILITY_CONTEXT):
            self.assertTrue(provider.capabilities.supports(cap))


class TestAvailability(unittest.TestCase):

    def test_available_with_key(self):
        provider = GoogleMapsProvider(config=_config(api_key="k"))
        self.assertTrue(provider.is_available())

    def test_unavailable_without_key(self):
        provider = GoogleMapsProvider(config=_config(api_key=None))
        self.assertFalse(provider.is_available())

    def test_unavailable_when_disabled_even_with_key(self):
        provider = GoogleMapsProvider(config=_config(api_key="k", enabled=False))
        self.assertFalse(provider.is_available())

    def test_search_on_unconfigured_provider_reports_provider_unavailable(self):
        provider = GoogleMapsProvider(config=_config(api_key=None))
        result = provider.search("bakso")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)


class TestSearch(unittest.TestCase):

    def test_search_success_normalizes_places(self):
        fetcher = _ScriptedFetcher({"textsearch": TEXT_SEARCH_OK})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso terdekat")

        self.assertTrue(result.success)
        self.assertEqual(result.capability, CAPABILITY_SEARCH)
        self.assertEqual(len(result.places), 1)

        place = result.places[0]
        self.assertEqual(place.id, "p1")
        self.assertEqual(place.name, "Warung Bakso Pak Budi")
        self.assertEqual(place.address, "Jl. Merdeka 1")
        self.assertEqual(place.latitude, -6.9)
        self.assertEqual(place.longitude, 107.6)
        self.assertEqual(place.metadata["rating"], 4.5)

    def test_search_empty_query_is_invalid_request_without_calling_fetcher(self):
        fetcher = _ScriptedFetcher({})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("   ")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)
        self.assertEqual(fetcher.calls, [])

    def test_api_key_never_leaks_into_query_result(self):
        fetcher = _ScriptedFetcher({"textsearch": TEXT_SEARCH_OK})
        provider = GoogleMapsProvider(config=_config(api_key="super-secret-key"), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertNotIn("super-secret-key", str(result.to_dict()))
        # but the key WAS sent to the transport layer, as Google requires
        self.assertEqual(fetcher.calls[0][1]["key"], "super-secret-key")


class TestLookup(unittest.TestCase):

    def test_lookup_success(self):
        fetcher = _ScriptedFetcher({"details": PLACE_DETAILS_OK})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.lookup("p1")

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].id, "p1")

    def test_lookup_missing_place_id_is_invalid_request(self):
        provider = GoogleMapsProvider(config=_config(), fetcher=_ScriptedFetcher({}))
        result = provider.lookup("")
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)

    def test_lookup_not_found_is_no_results(self):
        fetcher = _ScriptedFetcher({"details": {"status": "OK", "result": {}}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.lookup("does-not-exist")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_NO_RESULTS)


class TestNearby(unittest.TestCase):

    def test_nearby_success(self):
        fetcher = _ScriptedFetcher({"nearbysearch": NEARBY_OK})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.nearby(-6.9, 107.6, radius=800)

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].name, "Kopi Kenangan")
        self.assertEqual(fetcher.calls[0][1]["radius"], 800)

    def test_nearby_missing_coordinates_is_invalid_request(self):
        provider = GoogleMapsProvider(config=_config(), fetcher=_ScriptedFetcher({}))
        result = provider.nearby(None, None)
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)


class TestRoute(unittest.TestCase):

    def test_route_success_normalizes_segments(self):
        fetcher = _ScriptedFetcher({"directions": DIRECTIONS_OK})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.route("Bandung", "Jakarta")

        self.assertTrue(result.success)
        self.assertEqual(result.route.origin, "Bandung")
        self.assertEqual(result.route.destination, "Jakarta")
        self.assertEqual(result.route.distance_meters, 5000)
        self.assertEqual(result.route.duration_seconds, 600)
        self.assertEqual(len(result.route.segments), 2)
        self.assertEqual(result.route.segments[0].instruction, "Belok kanan ke Jl. Asia Afrika")

    def test_route_invalid_mode_is_invalid_request(self):
        provider = GoogleMapsProvider(config=_config(), fetcher=_ScriptedFetcher({}))
        result = provider.route("A", "B", mode="teleport")
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)

    def test_route_zero_results_is_no_results(self):
        fetcher = _ScriptedFetcher({"directions": {"status": "ZERO_RESULTS", "routes": []}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.route("A", "B")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_NO_RESULTS)


class TestContext(unittest.TestCase):

    def test_context_success_combines_geocode_and_nearby(self):
        fetcher = _ScriptedFetcher({"geocode": GEOCODE_OK, "nearbysearch": NEARBY_OK})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.context(-6.9, 107.6)

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].metadata["role"], "reverse_geocode")
        self.assertIn("Kopi Kenangan", result.metadata["nearby"])

    def test_context_geocode_failure_propagates(self):
        fetcher = _ScriptedFetcher({"geocode": {"status": "ZERO_RESULTS", "results": []}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.context(0.0, 0.0)

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_NO_RESULTS)


class TestErrorMapping(unittest.TestCase):

    def test_request_denied_is_authentication_error(self):
        fetcher = _ScriptedFetcher({"textsearch": {"status": "REQUEST_DENIED", "error_message": "bad key"}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_AUTHENTICATION_ERROR)
        self.assertFalse(result.error.retryable)

    def test_over_query_limit_is_rate_limited(self):
        fetcher = _ScriptedFetcher({"textsearch": {"status": "OVER_QUERY_LIMIT"}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_RATE_LIMITED)
        self.assertTrue(result.error.retryable)

    def test_invalid_request_status_mapped(self):
        fetcher = _ScriptedFetcher({"textsearch": {"status": "INVALID_REQUEST"}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)

    def test_unknown_status_is_provider_unavailable(self):
        fetcher = _ScriptedFetcher({"textsearch": {"status": "SOMETHING_NEW"}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)
        self.assertTrue(result.error.retryable)

    def test_timeout_is_mapped_via_custom_timeout_exception(self):
        fetcher = _ScriptedFetcher({"textsearch": GoogleMapsTimeout("took too long")})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_TIMEOUT)
        self.assertTrue(result.error.retryable)

    def test_transport_exception_is_provider_unavailable(self):
        fetcher = _ScriptedFetcher({"textsearch": ConnectionError("dns failure")})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)

    def test_non_dict_response_is_provider_unavailable(self):
        fetcher = _ScriptedFetcher({"textsearch": ["not", "a", "dict"]})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)

    def test_error_is_tagged_with_capability_and_provider(self):
        fetcher = _ScriptedFetcher({"textsearch": {"status": "OVER_QUERY_LIMIT"}})
        provider = GoogleMapsProvider(config=_config(), fetcher=fetcher)

        result = provider.search("bakso")

        self.assertEqual(result.error.provider, "google_maps")
        self.assertEqual(result.error.capability, CAPABILITY_SEARCH)


class TestConfigLoading(unittest.TestCase):

    def test_missing_env_produces_unconfigured_config(self):
        config = load_google_maps_config(env={})
        self.assertFalse(config.has_api_key)
        self.assertFalse(config.is_configured)

    def test_env_with_key_is_configured(self):
        config = load_google_maps_config(env={"GOOGLE_MAPS_API_KEY": "abc123"})
        self.assertTrue(config.has_api_key)
        self.assertTrue(config.is_configured)

    def test_explicit_disable_overrides_key_presence(self):
        config = load_google_maps_config(env={"GOOGLE_MAPS_API_KEY": "abc123", "GOOGLE_MAPS_ENABLED": "false"})
        self.assertTrue(config.has_api_key)
        self.assertFalse(config.is_configured)

    def test_malformed_timeout_falls_back_to_default(self):
        config = load_google_maps_config(env={"GOOGLE_MAPS_TIMEOUT_SECONDS": "not-a-number"})
        self.assertGreater(config.timeout_seconds, 0)

    def test_to_dict_never_exposes_api_key(self):
        config = GoogleMapsConfig(api_key="super-secret")
        as_dict = config.to_dict()
        self.assertNotIn("api_key", as_dict)
        self.assertNotIn("super-secret", str(as_dict))
        self.assertTrue(as_dict["has_api_key"])

    def test_provider_built_from_missing_config_is_unavailable(self):
        provider = GoogleMapsProvider(config=load_google_maps_config(env={}))
        self.assertFalse(provider.is_available())
        result = provider.search("bakso")
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
