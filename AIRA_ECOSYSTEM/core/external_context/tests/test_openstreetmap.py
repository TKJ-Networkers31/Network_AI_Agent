"""
Unit test OpenStreetMapProvider - fetcher palsu, TANPA request jaringan nyata.

    python -m unittest core.external_context.tests.test_openstreetmap -v
"""

import unittest

from core.external_context.constants import (
    CAPABILITY_NEARBY, ERROR_INVALID_REQUEST, ERROR_NO_RESULTS, ERROR_PROVIDER_UNAVAILABLE,
)
from core.external_context.openstreetmap import OpenStreetMapProvider


def _hospital_fetcher(url, params=None, post=None):
    assert "overpass" in url
    assert '"amenity"="hospital"' in post["data"]
    return {"elements": [
        {"type": "node", "id": 1, "lat": -6.91, "lon": 107.61,
         "tags": {"name": "RS Jauh", "phone": "022-111"}},
        {"type": "way", "id": 2, "center": {"lat": -6.901, "lon": 107.601}, "tags": {"name": "RS Dekat"}},
        {"type": "node", "id": 3, "lat": -6.9, "lon": 107.6, "tags": {}},  # tanpa nama -> dibuang
    ]}


class TestAvailability(unittest.TestCase):

    def test_always_available_without_api_key(self):
        self.assertTrue(OpenStreetMapProvider().is_available())


class TestNearby(unittest.TestCase):

    def test_hospital_uses_overpass_sorted_by_distance(self):
        provider = OpenStreetMapProvider(fetcher=_hospital_fetcher)
        result = provider.nearby(-6.9, 107.6, radius=3000, keyword="rumah sakit")

        self.assertTrue(result.success)
        self.assertEqual(result.capability, CAPABILITY_NEARBY)
        self.assertEqual([p.name for p in result.places], ["RS Dekat", "RS Jauh"])
        self.assertEqual(result.places[0].id, "W2")
        self.assertEqual(result.places[1].metadata["phone"], "022-111")
        self.assertLess(result.places[0].distance_meters, result.places[1].distance_meters)

    def test_search_with_location_and_known_category_delegates_to_overpass(self):
        provider = OpenStreetMapProvider(fetcher=_hospital_fetcher)
        result = provider.search("rumah sakit terdekat", location="-6.9,107.6", radius=3000)

        self.assertTrue(result.success)
        self.assertEqual(len(result.places), 2)

    def test_missing_coordinates_is_invalid_request(self):
        result = OpenStreetMapProvider(fetcher=_hospital_fetcher).nearby(None, None, keyword="rumah sakit")
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)

    def test_results_are_cached(self):
        calls = []

        def fetcher(url, params=None, post=None):
            calls.append(url)
            return _hospital_fetcher(url, params, post)

        provider = OpenStreetMapProvider(fetcher=fetcher)
        provider.nearby(-6.9, 107.6, radius=3000, keyword="rumah sakit")
        provider.nearby(-6.9, 107.6, radius=3000, keyword="rumah sakit")

        self.assertEqual(len(calls), 1)


class TestSearchAndLookup(unittest.TestCase):

    def test_free_text_search_uses_nominatim(self):
        def fetcher(url, params=None, post=None):
            assert "nominatim" in url and url.endswith("/search")
            return [{"osm_type": "node", "osm_id": 7, "lat": "-6.9", "lon": "107.6",
                     "name": "Gedung Sate", "display_name": "Gedung Sate, Bandung"}]

        result = OpenStreetMapProvider(fetcher=fetcher).search("Gedung Sate")

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].name, "Gedung Sate")
        self.assertEqual(result.places[0].id, "N7")

    def test_lookup_rejects_malformed_id(self):
        result = OpenStreetMapProvider(fetcher=lambda *a, **k: []).lookup("ChIJabc")
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)

    def test_lookup_not_found(self):
        result = OpenStreetMapProvider(fetcher=lambda *a, **k: []).lookup("N999")
        self.assertEqual(result.error.code, ERROR_NO_RESULTS)


class TestRoute(unittest.TestCase):

    def test_route_with_coordinates_skips_geocoding(self):
        def fetcher(url, params=None, post=None):
            assert "osrm" in url
            return {"code": "Ok", "routes": [{
                "distance": 5000, "duration": 600,
                "geometry": {"coordinates": [[107.6, -6.9], [107.61, -6.91]]},
                "legs": [{"steps": [
                    {"name": "Jl. Asia Afrika", "distance": 2000, "duration": 300,
                     "maneuver": {"type": "turn", "modifier": "right"}},
                    {"name": "", "distance": 0, "duration": 0, "maneuver": {"type": "arrive"}},
                ]}],
            }]}

        result = OpenStreetMapProvider(fetcher=fetcher).route("-6.9,107.6", "-6.91,107.61")

        self.assertTrue(result.success)
        self.assertEqual(result.route.distance_meters, 5000)
        self.assertEqual(result.route.segments[0].instruction, "Belok kanan ke Jl. Asia Afrika")
        self.assertEqual(result.route.segments[1].instruction, "Tiba di tujuan")
        self.assertEqual(result.route.metadata["geometry"][0], [-6.9, 107.6])

    def test_transit_not_supported(self):
        result = OpenStreetMapProvider(fetcher=lambda *a, **k: {}).route("-6.9,107.6", "-6.91,107.61", mode="transit")
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)


class TestErrors(unittest.TestCase):

    def test_transport_failure_is_provider_unavailable(self):
        def boom(url, params=None, post=None):
            raise ConnectionError("dns failure")

        result = OpenStreetMapProvider(fetcher=boom).nearby(-6.9, 107.6, keyword="rumah sakit")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()