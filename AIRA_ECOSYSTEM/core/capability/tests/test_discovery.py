import unittest

from core.capability.constants import (
    CONTEXT_CONVERSATION, CONTEXT_WORKSPACE,
    PERMISSION_CONFIRMATION_REQUIRED, PERMISSION_RESTRICTED, PERMISSION_SAFE,
    STATE_AVAILABLE, STATE_DISABLED, STATE_ENABLED,
    STATE_REQUIRES_CONFIRMATION, STATE_UNAVAILABLE,
)
from core.capability.discovery import CapabilityDiscovery, DiscoverySettings
from core.capability.models import Capability, ToolBinding
from core.capability.registry import CapabilityRegistry


def _build_registry():
    registry = CapabilityRegistry()

    registry.register(Capability(
        id="chat.echo", name="Echo", permission=PERMISSION_SAFE,
        supported_context=[CONTEXT_CONVERSATION],
    ))
    registry.register(Capability(
        id="workspace.write_file", name="Write File",
        permission=PERMISSION_CONFIRMATION_REQUIRED,
        supported_context=[CONTEXT_WORKSPACE],
        tool_binding=ToolBinding(tool_names=["files_write"]),
    ))
    registry.register(Capability(
        id="net.ping", name="Ping", permission=PERMISSION_SAFE,
        supported_context=[CONTEXT_CONVERSATION],
        tool_binding=ToolBinding(tool_names=["ping"]),
    ))
    registry.register(Capability(
        id="danger.reset", name="Factory Reset", permission=PERMISSION_RESTRICTED,
        supported_context=[CONTEXT_CONVERSATION],
    ))
    return registry


class TestDiscoverBasics(unittest.TestCase):

    def setUp(self):
        self.registry = _build_registry()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_no_context_or_tools_given_everything_resolves(self):
        results = self.discovery.discover()
        states = {r.capability.id: r.effective_state for r in results}
        self.assertEqual(states["chat.echo"], STATE_ENABLED)
        self.assertEqual(states["net.ping"], STATE_ENABLED)  # tool not checked when available_tools=None
        self.assertEqual(states["danger.reset"], STATE_ENABLED)
        self.assertEqual(states["workspace.write_file"], STATE_REQUIRES_CONFIRMATION)

    def test_context_mismatch_excluded_by_default(self):
        results = self.discovery.discover(context=[CONTEXT_CONVERSATION])
        ids = {r.capability.id for r in results}
        self.assertNotIn("workspace.write_file", ids)  # only supports "workspace"

    def test_context_mismatch_included_with_include_unavailable(self):
        results = self.discovery.discover(context=[CONTEXT_CONVERSATION], include_unavailable=True)
        matched = next(r for r in results if r.capability.id == "workspace.write_file")
        self.assertEqual(matched.effective_state, STATE_UNAVAILABLE)
        self.assertIn("context_mismatch", matched.reasons)

    def test_tool_unavailable_excluded_by_default(self):
        results = self.discovery.discover(available_tools=[])
        ids = {r.capability.id for r in results}
        self.assertNotIn("net.ping", ids)
        self.assertIn("chat.echo", ids)  # no tool binding -> unaffected

    def test_tool_available_enables_it(self):
        results = self.discovery.discover(available_tools=["ping"])
        matched = next(r for r in results if r.capability.id == "net.ping")
        self.assertEqual(matched.effective_state, STATE_ENABLED)

    def test_category_filter(self):
        results = self.discovery.discover(category="nonexistent-category")
        self.assertEqual(results, [])

    def test_category_filter_matches_default_category(self):
        # capabilities in _build_registry() don't set `category`, so they default to "general"
        results = self.discovery.discover(category="general")
        ids = {r.capability.id for r in results}
        self.assertEqual(ids, {"chat.echo", "workspace.write_file", "net.ping", "danger.reset"})


class TestPermissionGating(unittest.TestCase):

    def setUp(self):
        self.registry = _build_registry()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_disallowed_permission_becomes_unavailable(self):
        settings = DiscoverySettings(allowed_permissions=frozenset({PERMISSION_SAFE}))
        results = self.discovery.discover(settings=settings, include_unavailable=True)
        matched = {r.capability.id: r for r in results}
        self.assertEqual(matched["danger.reset"].effective_state, STATE_UNAVAILABLE)
        self.assertEqual(matched["chat.echo"].effective_state, STATE_ENABLED)

    def test_confirmation_required_without_confirmation(self):
        results = self.discovery.discover(context=[CONTEXT_WORKSPACE])
        matched = next(r for r in results if r.capability.id == "workspace.write_file")
        self.assertEqual(matched.effective_state, STATE_REQUIRES_CONFIRMATION)

    def test_confirmation_required_with_confirmation_granted(self):
        settings = DiscoverySettings(confirmed_ids=frozenset({"workspace.write_file"}))
        results = self.discovery.discover(context=[CONTEXT_WORKSPACE], settings=settings)
        matched = next(r for r in results if r.capability.id == "workspace.write_file")
        self.assertEqual(matched.effective_state, STATE_ENABLED)

    def test_disabled_via_settings_overrides_everything_else(self):
        settings = DiscoverySettings(disabled_ids=frozenset({"chat.echo"}))
        results = self.discovery.discover(settings=settings, include_unavailable=True)
        matched = next(r for r in results if r.capability.id == "chat.echo")
        self.assertEqual(matched.effective_state, STATE_DISABLED)

    def test_registry_level_disabled_state_respected(self):
        self.registry.set_state("chat.echo", STATE_DISABLED)
        results = self.discovery.discover(include_unavailable=True)
        matched = next(r for r in results if r.capability.id == "chat.echo")
        self.assertEqual(matched.effective_state, STATE_DISABLED)


class TestResolveEnablementFalse(unittest.TestCase):

    def setUp(self):
        self.registry = _build_registry()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_structural_check_only_stops_at_available(self):
        results = self.discovery.discover(context=[CONTEXT_WORKSPACE], resolve_enablement=False)
        matched = next(r for r in results if r.capability.id == "workspace.write_file")
        self.assertEqual(matched.effective_state, STATE_AVAILABLE)

    def test_still_reports_unavailable_when_structurally_blocked(self):
        results = self.discovery.discover(
            context=[CONTEXT_CONVERSATION], resolve_enablement=False, include_unavailable=True,
        )
        matched = next(r for r in results if r.capability.id == "workspace.write_file")
        self.assertEqual(matched.effective_state, STATE_UNAVAILABLE)


class TestIsUsable(unittest.TestCase):

    def setUp(self):
        self.registry = _build_registry()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_usable_capability(self):
        self.assertTrue(self.discovery.is_usable("chat.echo", context=[CONTEXT_CONVERSATION]))

    def test_missing_capability_is_not_usable(self):
        self.assertFalse(self.discovery.is_usable("does.not.exist"))

    def test_confirmation_pending_is_not_usable(self):
        self.assertFalse(self.discovery.is_usable("workspace.write_file", context=[CONTEXT_WORKSPACE]))

    def test_confirmation_granted_is_usable(self):
        settings = DiscoverySettings(confirmed_ids=frozenset({"workspace.write_file"}))
        self.assertTrue(self.discovery.is_usable(
            "workspace.write_file", context=[CONTEXT_WORKSPACE], settings=settings,
        ))


class TestDefaultRegistrySingletonWiring(unittest.TestCase):

    def test_discovery_defaults_to_global_registry_when_none_injected(self):
        from core.capability.registry import get_capability_registry
        discovery = CapabilityDiscovery()
        self.assertIs(discovery.registry, get_capability_registry())


if __name__ == "__main__":
    unittest.main()
