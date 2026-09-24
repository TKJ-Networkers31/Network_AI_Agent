"""
core/external_context/tests/test_provider_contract.py — unit tests for the
ExternalContextProvider base contract, exercised against a minimal dummy
provider so the contract is tested independently of Google Maps
(Sprint 2.7 / W7).

Run from AIRA_ECOSYSTEM/:
    python -m unittest core.external_context.tests.test_provider_contract -v
"""

import unittest

from core.external_context.constants import (
    CAPABILITY_LOOKUP,
    CAPABILITY_NEARBY,
    CAPABILITY_ROUTE,
    CAPABILITY_SEARCH,
    ERROR_INVALID_REQUEST,
    ERROR_PROVIDER_UNAVAILABLE,
)
from core.external_context.models import (
    NormalizedPlace,
    ProviderCapabilities,
    ProviderIdentity,
    QueryResult,
)
from core.external_context.provider import ExternalContextProvider


class DummyProvider(ExternalContextProvider):
    """Minimal provider used only to exercise the base class contract -
    implements search() only, and can be toggled available/unavailable."""

    def __init__(self, available: bool = True):
        self._available = available
        self.calls: list = []

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name="dummy", display_name="Dummy Provider")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capabilities=(CAPABILITY_SEARCH,))

    def is_available(self) -> bool:
        return self._available

    def _search(self, query: str, **kwargs) -> QueryResult:
        self.calls.append(("search", query))
        return QueryResult.ok("dummy", CAPABILITY_SEARCH, places=[NormalizedPlace(id="1", name=query)])


class BrokenProvider(ExternalContextProvider):
    """Provider whose capability method misbehaves, to prove the base
    class never lets a subclass crash the caller."""

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(name="broken", display_name="Broken Provider")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capabilities=(CAPABILITY_SEARCH, CAPABILITY_LOOKUP))

    def is_available(self) -> bool:
        return True

    def _search(self, query: str, **kwargs) -> QueryResult:
        raise RuntimeError("boom")

    def _lookup(self, place_id: str, **kwargs) -> QueryResult:
        return "not a QueryResult"  # type: ignore[return-value]


class TestSupportedCapability(unittest.TestCase):

    def test_search_delegates_to_subclass(self):
        provider = DummyProvider()
        result = provider.search("bakso")

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].name, "bakso")
        self.assertEqual(provider.calls, [("search", "bakso")])


class TestUnsupportedCapability(unittest.TestCase):

    def test_unimplemented_capability_returns_invalid_request_not_crash(self):
        provider = DummyProvider()
        result = provider.route("A", "B")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)
        self.assertEqual(result.provider, "dummy")
        self.assertEqual(result.capability, CAPABILITY_ROUTE)

    def test_default_nearby_and_lookup_also_report_unsupported(self):
        provider = DummyProvider()
        self.assertFalse(provider.nearby(1.0, 2.0).success)
        self.assertFalse(provider.lookup("x").success)


class TestAvailability(unittest.TestCase):

    def test_unavailable_provider_short_circuits_before_calling_subclass(self):
        provider = DummyProvider(available=False)
        result = provider.search("bakso")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)
        self.assertTrue(result.error.retryable)
        self.assertEqual(provider.calls, [])  # never reached _search


class TestExecuteDispatch(unittest.TestCase):

    def test_execute_routes_to_matching_public_method(self):
        provider = DummyProvider()
        result = provider.execute(CAPABILITY_SEARCH, query="bakso")

        self.assertTrue(result.success)
        self.assertEqual(result.places[0].name, "bakso")

    def test_execute_unknown_capability_is_invalid_request(self):
        provider = DummyProvider()
        result = provider.execute("not.a.capability")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_INVALID_REQUEST)


class TestMisbehavingProviderIsContained(unittest.TestCase):

    def test_raising_subclass_is_converted_to_provider_unavailable(self):
        provider = BrokenProvider()
        result = provider.search("x")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)

    def test_subclass_returning_non_query_result_is_converted(self):
        provider = BrokenProvider()
        result = provider.lookup("x")

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ERROR_PROVIDER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
