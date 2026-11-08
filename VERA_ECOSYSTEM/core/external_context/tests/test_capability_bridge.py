"""
core/external_context/tests/test_capability_bridge.py — unit tests for the
External Context <-> W1 Capability Layer bridge, and for the provider
factory's "missing provider/config" behavior (Sprint 2.7 / W7).

Run from AIRA_ECOSYSTEM/:
    python -m unittest core.external_context.tests.test_capability_bridge -v
"""

import unittest

from core.capability.constants import CONTEXT_LOCATION, PERMISSION_SAFE
from core.capability.registry import CapabilityRegistry
from core.external_context.capability_bridge import (
    capability_from_provider,
    capability_id_for,
    register_provider_capabilities,
    unregister_provider_capabilities,
)
from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.constants import CAPABILITY_ROUTE, CAPABILITY_SEARCH
from core.external_context.factory import get_google_maps_provider, reset_google_maps_provider
from core.external_context.google_maps import GoogleMapsProvider


class TestCapabilityIdAndConversion(unittest.TestCase):

    def test_capability_id_format(self):
        self.assertEqual(
            capability_id_for("google_maps", CAPABILITY_SEARCH),
            "external_context.google_maps.location.search",
        )

    def test_capability_from_provider_shape(self):
        provider = GoogleMapsProvider(config=GoogleMapsConfig(api_key="k"))
        cap = capability_from_provider(provider, CAPABILITY_SEARCH)

        self.assertEqual(cap.id, "external_context.google_maps.location.search")
        self.assertEqual(cap.category, "external_context")
        self.assertEqual(cap.supported_context, [CONTEXT_LOCATION])
        self.assertEqual(cap.permission, PERMISSION_SAFE)
        self.assertTrue(cap.tool_binding.is_empty)  # not an orchestrator tool
        self.assertEqual(cap.metadata["provider"], "google_maps")
        self.assertEqual(cap.metadata["capability"], CAPABILITY_SEARCH)


class TestRegistrationUsesExistingRegistry(unittest.TestCase):
    """The bridge MUST reuse whatever CapabilityRegistry it's given /
    the global singleton - it must never construct its own storage."""

    def setUp(self):
        self.registry = CapabilityRegistry()  # isolated instance for this test only
        self.provider = GoogleMapsProvider(config=GoogleMapsConfig(api_key="k"))

    def test_register_all_five_capabilities(self):
        result = register_provider_capabilities(self.provider, registry=self.registry)

        self.assertEqual(len(result["registered"]), 5)
        self.assertEqual(result["errors"], [])
        self.assertEqual(self.registry.count(), 5)
        self.assertTrue(self.registry.exists("external_context.google_maps.location.search"))
        self.assertTrue(self.registry.exists("external_context.google_maps.location.route"))

    def test_register_twice_without_overwrite_skips(self):
        register_provider_capabilities(self.provider, registry=self.registry)
        second = register_provider_capabilities(self.provider, registry=self.registry)

        self.assertEqual(second["registered"], [])
        self.assertEqual(len(second["skipped"]), 5)
        self.assertEqual(self.registry.count(), 5)  # not duplicated

    def test_register_twice_with_overwrite_replaces(self):
        register_provider_capabilities(self.provider, registry=self.registry)
        second = register_provider_capabilities(self.provider, registry=self.registry, overwrite=True)

        self.assertEqual(len(second["registered"]), 5)
        self.assertEqual(self.registry.count(), 5)

    def test_capabilities_are_discoverable_by_location_context(self):
        register_provider_capabilities(self.provider, registry=self.registry)

        found = self.registry.list(context=CONTEXT_LOCATION)
        self.assertEqual(len(found), 5)

    def test_capabilities_are_discoverable_by_category(self):
        register_provider_capabilities(self.provider, registry=self.registry)

        found = self.registry.list(category="external_context")
        self.assertEqual(len(found), 5)

    def test_unregister_removes_only_this_provider(self):
        register_provider_capabilities(self.provider, registry=self.registry)

        removed = unregister_provider_capabilities(self.provider, registry=self.registry)

        self.assertEqual(removed, 5)
        self.assertEqual(self.registry.count(), 0)


class TestGlobalRegistrySingletonReuse(unittest.TestCase):
    """Without an explicit `registry=`, the bridge must fall back to the
    SAME process-wide singleton core.capability.get_capability_registry()
    returns - not a private/new one."""

    def test_default_registry_is_the_global_singleton(self):
        from core.capability import get_capability_registry

        provider = GoogleMapsProvider(config=GoogleMapsConfig(api_key="k"))
        global_registry = get_capability_registry()

        before = global_registry.count()
        register_provider_capabilities(provider, overwrite=True)
        after = global_registry.count()

        try:
            self.assertGreaterEqual(after, before)
            self.assertTrue(global_registry.exists("external_context.google_maps.location.search"))
        finally:
            unregister_provider_capabilities(provider, registry=global_registry)


class TestFactoryMissingProviderConfig(unittest.TestCase):
    """'missing provider/config' scenarios required by the TEST section:
    the factory must hand back a well-formed, self-reporting-unavailable
    provider instead of raising when configuration is absent."""

    def setUp(self):
        reset_google_maps_provider()

    def tearDown(self):
        reset_google_maps_provider()

    def test_singleton_built_from_empty_environment_is_unavailable(self):
        provider = get_google_maps_provider(config=load_google_maps_config(env={}))

        self.assertIsInstance(provider, GoogleMapsProvider)
        self.assertFalse(provider.is_available())

    def test_singleton_is_cached_across_calls(self):
        first = get_google_maps_provider()
        second = get_google_maps_provider()
        self.assertIs(first, second)

    def test_explicit_config_bypasses_singleton_cache(self):
        cached = get_google_maps_provider()
        explicit = get_google_maps_provider(config=GoogleMapsConfig(api_key="only-for-this-call"))

        self.assertIsNot(cached, explicit)

    def test_reset_forces_environment_reread(self):
        first = get_google_maps_provider()
        reset_google_maps_provider()
        second = get_google_maps_provider()

        self.assertIsNot(first, second)

    def test_register_capabilities_for_unavailable_provider_still_succeeds(self):
        """A provider with no API key is still discoverable as EXISTING
        (registration is a structural/declaration concern) - whether it's
        currently USABLE is a discovery-layer (W1) question, not a
        registration-time failure."""
        registry = CapabilityRegistry()
        provider = GoogleMapsProvider(config=load_google_maps_config(env={}))

        result = register_provider_capabilities(provider, registry=registry)

        self.assertEqual(len(result["registered"]), 5)
        self.assertFalse(provider.is_available())


if __name__ == "__main__":
    unittest.main()
