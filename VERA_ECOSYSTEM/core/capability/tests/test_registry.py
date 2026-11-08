import unittest

from core.capability.constants import STATE_DISABLED, STATE_ENABLED, STATE_REGISTERED
from core.capability.models import Capability
from core.capability.registry import (
    CapabilityAlreadyRegisteredError,
    CapabilityRegistry,
    CapabilityValidationError,
)


def _cap(id="a.b", **kwargs) -> Capability:
    kwargs.setdefault("name", "Test Capability")
    return Capability(id=id, **kwargs)


class TestRegisterAndLookup(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_register_then_get(self):
        registered = self.registry.register(_cap())
        self.assertEqual(registered.state, STATE_REGISTERED)
        self.assertEqual(self.registry.get("a.b").id, "a.b")

    def test_exists(self):
        self.assertFalse(self.registry.exists("a.b"))
        self.registry.register(_cap())
        self.assertTrue(self.registry.exists("a.b"))

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.registry.get("does.not.exist"))

    def test_register_forces_registered_state_regardless_of_input(self):
        registered = self.registry.register(_cap(state=STATE_ENABLED))
        self.assertEqual(registered.state, STATE_REGISTERED)

    def test_register_invalid_capability_raises(self):
        with self.assertRaises(CapabilityValidationError):
            self.registry.register(_cap(id=""))

    def test_register_invalid_capability_is_not_stored(self):
        try:
            self.registry.register(_cap(id=""))
        except CapabilityValidationError:
            pass
        self.assertEqual(self.registry.count(), 0)


class TestDuplicateHandling(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register(_cap(name="First"))

    def test_duplicate_without_overwrite_raises(self):
        with self.assertRaises(CapabilityAlreadyRegisteredError):
            self.registry.register(_cap(name="Second"))

    def test_duplicate_does_not_replace_without_overwrite(self):
        try:
            self.registry.register(_cap(name="Second"))
        except CapabilityAlreadyRegisteredError:
            pass
        self.assertEqual(self.registry.get("a.b").name, "First")

    def test_duplicate_with_overwrite_replaces(self):
        self.registry.register(_cap(name="Second"), overwrite=True)
        self.assertEqual(self.registry.get("a.b").name, "Second")
        self.assertEqual(self.registry.count(), 1)


class TestRemoval(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register(_cap())

    def test_unregister_existing(self):
        self.assertTrue(self.registry.unregister("a.b"))
        self.assertFalse(self.registry.exists("a.b"))

    def test_unregister_missing_returns_false(self):
        self.assertFalse(self.registry.unregister("does.not.exist"))

    def test_remove_is_alias_for_unregister(self):
        self.assertTrue(self.registry.remove("a.b"))
        self.assertFalse(self.registry.exists("a.b"))

    def test_clear(self):
        self.registry.register(_cap(id="a.c"))
        removed = self.registry.clear()
        self.assertEqual(removed, 2)
        self.assertEqual(self.registry.count(), 0)


class TestState(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register(_cap())

    def test_set_state_updates_and_returns(self):
        updated = self.registry.set_state("a.b", STATE_DISABLED)
        self.assertEqual(updated.state, STATE_DISABLED)
        self.assertEqual(self.registry.get("a.b").state, STATE_DISABLED)

    def test_set_state_missing_returns_none(self):
        self.assertIsNone(self.registry.set_state("nope", STATE_DISABLED))

    def test_set_state_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.registry.set_state("a.b", "not_a_state")


class TestListFiltering(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register(_cap(id="a.b", category="network", permission="safe"))
        self.registry.register(_cap(id="a.c", category="workspace", permission="restricted",
                                     supported_context=["workspace"]))
        self.registry.register(_cap(id="a.d", category="network", permission="safe"))

    def test_list_all_preserves_registration_order(self):
        ids = [c.id for c in self.registry.list()]
        self.assertEqual(ids, ["a.b", "a.c", "a.d"])

    def test_list_by_category(self):
        ids = {c.id for c in self.registry.list(category="network")}
        self.assertEqual(ids, {"a.b", "a.d"})

    def test_list_by_permission(self):
        ids = {c.id for c in self.registry.list(permission="restricted")}
        self.assertEqual(ids, {"a.c"})

    def test_list_by_context(self):
        ids = {c.id for c in self.registry.list(context="workspace")}
        self.assertEqual(ids, {"a.c"})

    def test_list_by_predicate(self):
        ids = {c.id for c in self.registry.list(predicate=lambda c: c.id.endswith("d"))}
        self.assertEqual(ids, {"a.d"})

    def test_list_returns_snapshot_not_live_dict(self):
        snapshot = self.registry.list()
        snapshot.clear()
        self.assertEqual(self.registry.count(), 3)


class TestNoEventBusDependency(unittest.TestCase):
    """The registry must work even when core.events is unavailable/broken -
    this sandbox has no core/events.py at all, so this exercises exactly
    that failure path for every mutating operation."""

    def test_full_lifecycle_without_event_bus_present(self):
        registry = CapabilityRegistry()
        registry.register(_cap())
        registry.set_state("a.b", STATE_DISABLED)
        registry.unregister("a.b")
        self.assertEqual(registry.count(), 0)


if __name__ == "__main__":
    unittest.main()
