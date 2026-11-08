import unittest

from core.capability.constants import (
    CONTEXT_ATTACHMENT, CONTEXT_CONVERSATION, PERMISSION_SAFE,
    STATE_DISABLED, STATE_REGISTERED,
)
from core.capability.models import (
    Capability, CapabilityUIMetadata, ToolBinding, validate_capability,
)


class TestCapabilityDefaults(unittest.TestCase):

    def test_minimal_construction_has_sane_defaults(self):
        cap = Capability(id="wa.echo", name="Echo")
        self.assertEqual(cap.category, "general")
        self.assertEqual(cap.permission, PERMISSION_SAFE)
        self.assertEqual(cap.state, STATE_REGISTERED)
        self.assertEqual(cap.supported_context, [CONTEXT_CONVERSATION])
        self.assertTrue(cap.tool_binding.is_empty)

    def test_invalid_permission_falls_back_to_safe(self):
        cap = Capability(id="wa.x", name="X", permission="not_a_real_permission")
        self.assertEqual(cap.permission, PERMISSION_SAFE)

    def test_invalid_state_falls_back_to_registered(self):
        cap = Capability(id="wa.x", name="X", state="bogus")
        self.assertEqual(cap.state, STATE_REGISTERED)

    def test_empty_supported_context_falls_back_to_conversation(self):
        cap = Capability(id="wa.x", name="X", supported_context=[])
        self.assertEqual(cap.supported_context, [CONTEXT_CONVERSATION])

    def test_ui_and_tool_binding_accept_dicts(self):
        cap = Capability(
            id="wa.x", name="X",
            ui={"label": "Say Hi", "hidden": True},
            tool_binding={"tool_names": ["say_hi"]},
        )
        self.assertIsInstance(cap.ui, CapabilityUIMetadata)
        self.assertEqual(cap.ui.label, "Say Hi")
        self.assertTrue(cap.ui.hidden)
        self.assertIsInstance(cap.tool_binding, ToolBinding)
        self.assertEqual(cap.tool_binding.primary_tool, "say_hi")


class TestSupportsContext(unittest.TestCase):

    def test_single_string(self):
        cap = Capability(id="a", name="A", supported_context=[CONTEXT_CONVERSATION, CONTEXT_ATTACHMENT])
        self.assertTrue(cap.supports_context(CONTEXT_ATTACHMENT))
        self.assertFalse(cap.supports_context("location"))

    def test_iterable_any_match(self):
        cap = Capability(id="a", name="A", supported_context=[CONTEXT_CONVERSATION])
        self.assertTrue(cap.supports_context([CONTEXT_ATTACHMENT, CONTEXT_CONVERSATION]))


class TestWithState(unittest.TestCase):

    def test_with_state_returns_new_instance(self):
        cap = Capability(id="a", name="A")
        updated = cap.with_state(STATE_DISABLED)

        self.assertEqual(cap.state, STATE_REGISTERED)  # original untouched
        self.assertEqual(updated.state, STATE_DISABLED)
        self.assertIsNot(cap, updated)

    def test_with_state_rejects_unknown_state(self):
        cap = Capability(id="a", name="A")
        with self.assertRaises(ValueError):
            cap.with_state("not_a_state")


class TestToolBinding(unittest.TestCase):

    def test_is_satisfied_by_any_by_default(self):
        binding = ToolBinding(tool_names=["ping", "traceroute"])
        self.assertTrue(binding.is_satisfied_by({"ping"}))
        self.assertFalse(binding.is_satisfied_by({"nslookup"}))

    def test_requires_all(self):
        binding = ToolBinding(tool_names=["ping", "traceroute"], requires_all=True)
        self.assertFalse(binding.is_satisfied_by({"ping"}))
        self.assertTrue(binding.is_satisfied_by({"ping", "traceroute"}))

    def test_empty_binding_always_satisfied(self):
        binding = ToolBinding()
        self.assertTrue(binding.is_satisfied_by(set()))

    def test_primary_tool_defaults_to_first(self):
        binding = ToolBinding(tool_names=["b", "a"])
        self.assertEqual(binding.primary_tool, "b")

    def test_non_string_entries_are_dropped(self):
        binding = ToolBinding(tool_names=["ok", 123, None, ""])
        self.assertEqual(binding.tool_names, ["ok"])


class TestSerializationRoundTrip(unittest.TestCase):

    def test_to_dict_from_dict_round_trip(self):
        cap = Capability(
            id="workspace.write_file", name="Write File",
            description="Write a file in the workspace.",
            category="workspace",
            supported_context=["workspace", "conversation"],
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            output_types=["file"],
            permission="confirmation_required",
            ui={"label": "Write File", "icon": "file-plus", "order": 3},
            tool_binding={"tool_names": ["files_write"]},
            metadata={"origin": "fse"},
        )

        restored = Capability.from_dict(cap.to_dict())

        self.assertEqual(restored.id, cap.id)
        self.assertEqual(restored.category, "workspace")
        self.assertEqual(restored.permission, "confirmation_required")
        self.assertEqual(restored.tool_binding.tool_names, ["files_write"])
        self.assertEqual(restored.ui.icon, "file-plus")
        self.assertEqual(restored.metadata, {"origin": "fse"})

    def test_from_dict_tolerates_garbage(self):
        restored = Capability.from_dict({"id": "x", "name": "X", "permission": 123, "ui": "not_a_dict"})
        self.assertEqual(restored.id, "x")
        self.assertEqual(restored.permission, PERMISSION_SAFE)  # invalid input -> safe fallback
        self.assertIsInstance(restored.ui, CapabilityUIMetadata)

    def test_from_dict_of_non_mapping_does_not_raise(self):
        restored = Capability.from_dict(None)  # type: ignore[arg-type]
        self.assertEqual(restored.id, "")
        self.assertEqual(restored.name, "")


class TestValidateCapability(unittest.TestCase):

    def test_valid_capability_passes(self):
        cap = Capability(id="a.b", name="Valid")
        result = validate_capability(cap)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.issues, [])

    def test_missing_id_fails(self):
        result = validate_capability(Capability(id="", name="X"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.field == "id" for i in result.issues))

    def test_whitespace_in_id_fails(self):
        result = validate_capability(Capability(id="bad id", name="X"))
        self.assertFalse(result.is_valid)

    def test_missing_name_fails(self):
        result = validate_capability(Capability(id="a.b", name=""))
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.field == "name" for i in result.issues))

    def test_requires_all_without_tool_names_fails(self):
        cap = Capability(id="a.b", name="X", tool_binding=ToolBinding(requires_all=True))
        result = validate_capability(cap)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.field == "tool_binding" for i in result.issues))

    def test_validator_never_raises_on_garbage(self):
        try:
            result = validate_capability("not a capability")  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            self.fail(f"validator raised: {exc}")
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
