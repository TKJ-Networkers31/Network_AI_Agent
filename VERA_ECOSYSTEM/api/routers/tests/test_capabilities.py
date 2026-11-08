"""
api/routers/tests/test_capabilities.py — regression tests for
GET /api/capabilities (Sprint 2.7 / W8 Dynamic Capability API).

Exercises the real core.capability.CapabilityRegistry /
CapabilityDiscovery (an isolated instance, not the process-wide
singleton - same isolation pattern already used by
core/capability/tests/test_discovery.py) through
api.routers.capabilities_logic.list_capabilities(), which is exactly the
function api.routers.capabilities.get_capabilities() calls. This proves
the endpoint's actual behavior (200 shape, area filtering, empty/error
resilience) without needing a FastAPI test client.

Run:
    python -m unittest api.routers.tests.test_capabilities -v
"""

import unittest

from core.capability.constants import (
    CONTEXT_ATTACHMENT,
    CONTEXT_CONVERSATION,
    PERMISSION_CONFIRMATION_REQUIRED,
    PERMISSION_SAFE,
)
from core.capability.discovery import CapabilityDiscovery
from core.capability.models import Capability, CapabilityUIMetadata, ToolBinding
from core.capability.registry import CapabilityRegistry

from api.routers.capabilities_logic import list_capabilities


def _registry_with_ui_areas() -> CapabilityRegistry:
    registry = CapabilityRegistry()

    registry.register(Capability(
        id="chat.echo", name="Echo",
        permission=PERMISSION_SAFE,
        supported_context=[CONTEXT_CONVERSATION],
        ui=CapabilityUIMetadata(group="chat_input", label="Echo", icon="echo"),
    ))
    registry.register(Capability(
        id="hero.greet", name="Greet",
        permission=PERMISSION_SAFE,
        supported_context=[CONTEXT_CONVERSATION],
        ui=CapabilityUIMetadata(group="hero", label="Sapa"),
    ))
    registry.register(Capability(
        id="attachment.summarize", name="Summarize Attachment",
        permission=PERMISSION_CONFIRMATION_REQUIRED,
        supported_context=[CONTEXT_ATTACHMENT],
        ui=CapabilityUIMetadata(group="message_actions", label="Ringkas Lampiran"),
        tool_binding=ToolBinding(tool_names=["summarize_attachment"]),
    ))
    return registry


class TestEndpointShapeAndSuccess(unittest.TestCase):
    """Equivalent of a 200 response with the W8 contract shape."""

    def setUp(self):
        self.registry = _registry_with_ui_areas()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_returns_capabilities_key_with_expected_item_shape(self):
        items = list_capabilities(discovery=self.discovery)

        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

        for item in items:
            self.assertEqual(
                set(item.keys()),
                {"id", "area", "label", "icon", "enabled", "disabled_reason", "action"},
            )

    def test_enabled_item_has_no_disabled_reason(self):
        items = list_capabilities(discovery=self.discovery)
        echo = next(i for i in items if i["id"] == "chat.echo")

        self.assertTrue(echo["enabled"])
        self.assertIsNone(echo["disabled_reason"])
        self.assertEqual(echo["area"], "chat_input")
        self.assertEqual(echo["action"]["type"], "capability")

    def test_context_mismatched_item_is_disabled_with_reason(self):
        # attachment.summarize requires CONTEXT_ATTACHMENT; no
        # has_attachment signal given here.
        items = list_capabilities(discovery=self.discovery)
        summarize = next(i for i in items if i["id"] == "attachment.summarize")

        self.assertFalse(summarize["enabled"])
        self.assertIsNotNone(summarize["disabled_reason"])

    def test_context_signal_enables_previously_unavailable_capability(self):
        items = list_capabilities(discovery=self.discovery, has_attachment=True)
        summarize = next(i for i in items if i["id"] == "attachment.summarize")

        # still confirmation_required (not context_mismatch) once the
        # attachment signal is present, and tool_binding is surfaced.
        self.assertFalse(summarize["enabled"])
        self.assertEqual(summarize["action"]["type"], "tool")
        self.assertEqual(summarize["action"]["tool"], "summarize_attachment")


class TestAreaFiltering(unittest.TestCase):

    def setUp(self):
        self.registry = _registry_with_ui_areas()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_no_area_returns_everything(self):
        items = list_capabilities(discovery=self.discovery)
        ids = {i["id"] for i in items}
        self.assertEqual(ids, {"chat.echo", "hero.greet", "attachment.summarize"})

    def test_specific_area_filters_to_that_area_only(self):
        items = list_capabilities(discovery=self.discovery, area="message_actions")
        ids = {i["id"] for i in items}
        self.assertEqual(ids, {"attachment.summarize"})

    def test_conversation_scope_returns_union_of_hero_chat_input_dock(self):
        # Mirrors CapabilityContext.jsx: it fetches area="conversation"
        # once and filters client-side by each item's own area.
        items = list_capabilities(discovery=self.discovery, area="conversation")
        ids = {i["id"] for i in items}
        self.assertEqual(ids, {"chat.echo", "hero.greet"})

    def test_unknown_area_returns_empty_not_error(self):
        items = list_capabilities(discovery=self.discovery, area="does_not_exist")
        self.assertEqual(items, [])


class TestEmptyRegistry(unittest.TestCase):

    def test_empty_registry_returns_empty_list(self):
        empty_registry = CapabilityRegistry()
        discovery = CapabilityDiscovery(empty_registry)

        items = list_capabilities(discovery=discovery)

        self.assertEqual(items, [])

    def test_empty_registry_with_area_filter_returns_empty_list(self):
        empty_registry = CapabilityRegistry()
        discovery = CapabilityDiscovery(empty_registry)

        items = list_capabilities(discovery=discovery, area="chat_input")

        self.assertEqual(items, [])


class _BoomDiscovery:
    """Stand-in for CapabilityDiscovery whose discover() raises - proves
    list_capabilities() (and therefore the endpoint) degrades to an empty
    list instead of propagating a 500."""

    def discover(self, *args, **kwargs):
        raise RuntimeError("registry backend unavailable")


class TestDiscoveryErrorIsContained(unittest.TestCase):

    def test_discovery_exception_yields_empty_list_not_raise(self):
        try:
            items = list_capabilities(discovery=_BoomDiscovery())
        except Exception as exc:  # pragma: no cover
            self.fail(f"list_capabilities() propagated an exception: {exc}")

        self.assertEqual(items, [])


class TestAcceptsFrontendQueryParams(unittest.TestCase):
    """Every param the frontend already sends must be accepted without
    raising, even though not all of them gate discovery today."""

    def setUp(self):
        self.registry = _registry_with_ui_areas()
        self.discovery = CapabilityDiscovery(self.registry)

    def test_message_actions_params_accepted(self):
        items = list_capabilities(
            discovery=self.discovery,
            area="message_actions",
            message_id="turn-42",
            conversation_id="sess-1",
            role="assistant",
            has_selection=True,
        )
        self.assertEqual({i["id"] for i in items}, {"attachment.summarize"})

    def test_file_actions_signal_accepted(self):
        items = list_capabilities(
            discovery=self.discovery, area="file_actions", file_path="Documents/a.txt",
        )
        self.assertEqual(items, [])  # no capability registered for file_actions in this fixture


if __name__ == "__main__":
    unittest.main()
