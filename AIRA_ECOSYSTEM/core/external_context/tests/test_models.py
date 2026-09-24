"""
core/external_context/tests/test_models.py — unit tests for normalization
and serialization (Sprint 2.7 / W7).

Run from AIRA_ECOSYSTEM/:
    python -m unittest core.external_context.tests.test_models -v
"""

import unittest

from core.external_context.constants import CAPABILITY_ROUTE, CAPABILITY_SEARCH
from core.external_context.models import (
    ExternalContextError,
    NormalizedPlace,
    NormalizedRoute,
    ProviderCapabilities,
    ProviderIdentity,
    QueryResult,
    RouteSegment,
)


class TestProviderIdentity(unittest.TestCase):

    def test_to_dict(self):
        identity = ProviderIdentity(name="google_maps", display_name="Google Maps", version="1.0")
        self.assertEqual(identity.to_dict(), {
            "name": "google_maps", "display_name": "Google Maps", "version": "1.0",
        })


class TestProviderCapabilities(unittest.TestCase):

    def test_supports(self):
        caps = ProviderCapabilities(capabilities=(CAPABILITY_SEARCH,))
        self.assertTrue(caps.supports(CAPABILITY_SEARCH))
        self.assertFalse(caps.supports(CAPABILITY_ROUTE))

    def test_invalid_capability_name_is_dropped(self):
        caps = ProviderCapabilities(capabilities=(CAPABILITY_SEARCH, "not.a.real.capability"))
        self.assertEqual(caps.capabilities, (CAPABILITY_SEARCH,))

    def test_to_dict(self):
        caps = ProviderCapabilities(capabilities=(CAPABILITY_SEARCH, CAPABILITY_ROUTE))
        self.assertEqual(sorted(caps.to_dict()["capabilities"]), sorted([CAPABILITY_SEARCH, CAPABILITY_ROUTE]))


class TestNormalizedPlace(unittest.TestCase):

    def test_round_trip(self):
        place = NormalizedPlace(
            id="p1", name="Warung Bakso", address="Jl. Merdeka 1",
            latitude=-6.9, longitude=107.6, distance_meters=120.5,
            metadata={"rating": 4.5},
        )
        restored = NormalizedPlace.from_dict(place.to_dict())

        self.assertEqual(restored.id, "p1")
        self.assertEqual(restored.name, "Warung Bakso")
        self.assertEqual(restored.distance_meters, 120.5)
        self.assertEqual(restored.metadata, {"rating": 4.5})

    def test_to_dict_always_has_metadata_key(self):
        place = NormalizedPlace(id="p1", name="X")
        self.assertEqual(place.to_dict()["metadata"], {})

    def test_from_dict_tolerates_garbage(self):
        restored = NormalizedPlace.from_dict({"id": "p1"})
        self.assertEqual(restored.id, "p1")
        self.assertEqual(restored.name, "")
        self.assertIsNone(restored.latitude)

    def test_from_dict_of_non_mapping_does_not_raise(self):
        restored = NormalizedPlace.from_dict(None)
        self.assertEqual(restored.id, "")


class TestNormalizedRoute(unittest.TestCase):

    def test_round_trip_with_segments(self):
        route = NormalizedRoute(
            origin="A", destination="B", distance_meters=1000, duration_seconds=300,
            segments=[RouteSegment(instruction="Belok kanan", distance_meters=500, duration_seconds=150)],
            metadata={"mode": "driving"},
        )
        restored = NormalizedRoute.from_dict(route.to_dict())

        self.assertEqual(restored.origin, "A")
        self.assertEqual(len(restored.segments), 1)
        self.assertEqual(restored.segments[0].instruction, "Belok kanan")
        self.assertEqual(restored.metadata, {"mode": "driving"})

    def test_empty_segments_round_trip(self):
        route = NormalizedRoute(origin="A", destination="B")
        restored = NormalizedRoute.from_dict(route.to_dict())
        self.assertEqual(restored.segments, [])


class TestExternalContextError(unittest.TestCase):

    def test_valid_code_kept(self):
        err = ExternalContextError(code="rate_limited", message="too many requests")
        self.assertEqual(err.code, "rate_limited")

    def test_invalid_code_normalized_to_provider_unavailable(self):
        err = ExternalContextError(code="totally_made_up", message="x")
        self.assertEqual(err.code, "provider_unavailable")
        self.assertEqual(err.details.get("_original_code"), "totally_made_up")

    def test_to_dict_round_trip(self):
        err = ExternalContextError(
            code="timeout", message="slow", provider="google_maps",
            capability="location.search", retryable=True, details={"http_status": 504},
        )
        restored = ExternalContextError.from_dict(err.to_dict())
        self.assertEqual(restored.code, "timeout")
        self.assertTrue(restored.retryable)
        self.assertEqual(restored.details, {"http_status": 504})

    def test_is_retryable_by_default(self):
        self.assertTrue(ExternalContextError(code="rate_limited", message="x").is_retryable_by_default)
        self.assertFalse(ExternalContextError(code="invalid_request", message="x").is_retryable_by_default)


class TestQueryResult(unittest.TestCase):

    def test_ok_result_has_no_error(self):
        result = QueryResult.ok("google_maps", CAPABILITY_SEARCH, places=[NormalizedPlace(id="1", name="X")])
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.places), 1)

    def test_fail_result_requires_error_present(self):
        err = ExternalContextError(code="no_results", message="none found")
        result = QueryResult.fail("google_maps", CAPABILITY_SEARCH, err)
        self.assertFalse(result.success)
        self.assertIs(result.error, err)

    def test_success_true_drops_any_passed_error(self):
        err = ExternalContextError(code="timeout", message="x")
        result = QueryResult(success=True, provider="google_maps", capability=CAPABILITY_SEARCH, error=err)
        self.assertIsNone(result.error)

    def test_failure_without_error_gets_a_default_one(self):
        result = QueryResult(success=False, provider="google_maps", capability=CAPABILITY_SEARCH)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "provider_unavailable")

    def test_invalid_capability_normalized(self):
        result = QueryResult.ok("google_maps", "not.a.capability")
        self.assertEqual(result.capability, "location.context")
        self.assertEqual(result.metadata.get("_original_capability"), "not.a.capability")

    def test_is_empty(self):
        empty = QueryResult.ok("google_maps", CAPABILITY_SEARCH)
        self.assertTrue(empty.is_empty)

        nonempty = QueryResult.ok("google_maps", CAPABILITY_SEARCH, places=[NormalizedPlace(id="1", name="X")])
        self.assertFalse(nonempty.is_empty)

    def test_serialization_round_trip_success(self):
        result = QueryResult.ok(
            "google_maps", CAPABILITY_SEARCH,
            places=[NormalizedPlace(id="1", name="X", latitude=1.0, longitude=2.0)],
            metadata={"query": "bakso"},
        )
        restored = QueryResult.from_dict(result.to_dict())

        self.assertTrue(restored.success)
        self.assertEqual(restored.provider, "google_maps")
        self.assertEqual(len(restored.places), 1)
        self.assertEqual(restored.metadata["query"], "bakso")

    def test_serialization_round_trip_failure(self):
        err = ExternalContextError(code="rate_limited", message="slow down", provider="google_maps")
        result = QueryResult.fail("google_maps", CAPABILITY_SEARCH, err)
        restored = QueryResult.from_dict(result.to_dict())

        self.assertFalse(restored.success)
        self.assertEqual(restored.error.code, "rate_limited")

    def test_route_result_round_trip(self):
        route = NormalizedRoute(origin="A", destination="B", distance_meters=100, duration_seconds=60)
        result = QueryResult.ok("google_maps", CAPABILITY_ROUTE, route=route)
        restored = QueryResult.from_dict(result.to_dict())

        self.assertIsNotNone(restored.route)
        self.assertEqual(restored.route.origin, "A")


if __name__ == "__main__":
    unittest.main()
