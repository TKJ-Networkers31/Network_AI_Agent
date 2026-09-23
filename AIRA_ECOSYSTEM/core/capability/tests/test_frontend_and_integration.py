import unittest

from core.capability.constants import PERMISSION_CONFIRMATION_REQUIRED, PERMISSION_SAFE, STATE_ENABLED
from core.capability.discovery import DiscoveredCapability
from core.capability.frontend import (
    capabilities_to_frontend_list,
    capability_to_frontend_dict,
    discovered_to_frontend_dict,
)
from core.capability.integration import capability_from_tool_schema, register_tool_capabilities
from core.capability.models import Capability, CapabilityUIMetadata, ToolBinding
from core.capability.registry import CapabilityRegistry


class TestFrontendSerialization(unittest.TestCase):

    def test_internal_fields_are_dropped(self):
        cap = Capability(
            id="workspace.write_file", name="Write File",
            tool_binding=ToolBinding(tool_names=["files_write", "secret_internal_tool"]),
            metadata={"danger": "very yes"},
        )
        out = capability_to_frontend_dict(cap)

        self.assertNotIn("tool_binding", out)
        self.assertNotIn("metadata", out)
        self.assertNotIn("registered_at", out)
        self.assertNotIn("updated_at", out)
        self.assertTrue(out["has_tool_binding"])

    def test_ui_label_falls_back_to_name(self):
        cap = Capability(id="a", name="A Nice Name")
        out = capability_to_frontend_dict(cap)
        self.assertEqual(out["label"], "A Nice Name")

    def test_ui_label_overrides_name_when_present(self):
        cap = Capability(id="a", name="Internal Name", ui=CapabilityUIMetadata(label="Pretty Name"))
        out = capability_to_frontend_dict(cap)
        self.assertEqual(out["label"], "Pretty Name")

    def test_effective_state_overrides_static_state(self):
        cap = Capability(id="a", name="A")
        out = capability_to_frontend_dict(cap, effective_state=STATE_ENABLED)
        self.assertEqual(out["state"], STATE_ENABLED)

    def test_discovered_to_frontend_dict_uses_effective_state(self):
        cap = Capability(id="a", name="A")
        discovered = DiscoveredCapability(capability=cap, effective_state=STATE_ENABLED, reasons=["ok"])
        out = discovered_to_frontend_dict(discovered)
        self.assertEqual(out["state"], STATE_ENABLED)

    def test_hidden_capabilities_excluded_by_default(self):
        visible = Capability(id="a", name="A")
        hidden = Capability(id="b", name="B", ui=CapabilityUIMetadata(hidden=True))
        out = capabilities_to_frontend_list([visible, hidden])
        self.assertEqual([c["id"] for c in out], ["a"])

    def test_hidden_capabilities_included_when_requested(self):
        hidden = Capability(id="b", name="B", ui=CapabilityUIMetadata(hidden=True))
        out = capabilities_to_frontend_list([hidden], include_hidden=True)
        self.assertEqual([c["id"] for c in out], ["b"])

    def test_mixed_list_of_capability_and_discovered(self):
        cap = Capability(id="a", name="A")
        discovered = DiscoveredCapability(capability=Capability(id="b", name="B"), effective_state=STATE_ENABLED)
        out = capabilities_to_frontend_list([cap, discovered])
        self.assertEqual({c["id"] for c in out}, {"a", "b"})


class TestToolSchemaIntegration(unittest.TestCase):

    SCHEMA = {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Ping a host.",
            "parameters": {"type": "object", "properties": {"host": {"type": "string"}}},
        },
    }

    def test_capability_from_tool_schema(self):
        cap = capability_from_tool_schema(self.SCHEMA, category="network")
        self.assertEqual(cap.id, "tool.ping")
        self.assertEqual(cap.category, "network")
        self.assertEqual(cap.tool_binding.tool_names, ["ping"])
        self.assertEqual(cap.permission, PERMISSION_SAFE)
        self.assertEqual(cap.input_schema, self.SCHEMA["function"]["parameters"])

    def test_dangerous_tool_gets_confirmation_required(self):
        cap = capability_from_tool_schema(self.SCHEMA, dangerous=True)
        self.assertEqual(cap.permission, PERMISSION_CONFIRMATION_REQUIRED)

    def test_malformed_schema_returns_none(self):
        self.assertIsNone(capability_from_tool_schema({"type": "function", "function": {}}))
        self.assertIsNone(capability_from_tool_schema("not a dict"))  # type: ignore[arg-type]

    def test_register_tool_capabilities_bridges_a_schema_list(self):
        registry = CapabilityRegistry()
        schemas = [
            self.SCHEMA,
            {"type": "function", "function": {"name": "reset_device", "description": "", "parameters": {}}},
            {"type": "function", "function": {}},  # malformed on purpose
        ]
        result = register_tool_capabilities(
            schemas,
            tool_category={"ping": "network", "reset_device": "network"},
            dangerous_tools={"reset_device"},
            registry=registry,
        )

        self.assertEqual(set(result["registered"]), {"tool.ping", "tool.reset_device"})
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["errors"], [])
        self.assertTrue(registry.exists("tool.ping"))
        self.assertEqual(registry.get("tool.reset_device").permission, PERMISSION_CONFIRMATION_REQUIRED)

    def test_register_tool_capabilities_duplicate_is_skipped_not_raised(self):
        registry = CapabilityRegistry()
        schemas = [self.SCHEMA]
        register_tool_capabilities(schemas, registry=registry)
        result = register_tool_capabilities(schemas, registry=registry)  # second pass, no overwrite

        self.assertEqual(result["registered"], [])
        self.assertEqual(result["skipped"], ["tool.ping"])
        self.assertEqual(registry.count(), 1)


if __name__ == "__main__":
    unittest.main()
