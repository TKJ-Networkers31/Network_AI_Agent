"""
tests/test_dio_orchestration.py — Verification of DIO Form Lifecycle, State Transitions,
Idempotency, and Multi-Device Form Orchestration.
"""

import unittest
from core.dio.models import InteractionSchema, InteractionState, MissingField, ChoiceOption
from core.dio.interaction_memory import get_interaction_memory
from agents.rei.dio_tools import (
    request_structured_input,
    submit_structured_input,
    request_device_choice,
)


class TestDioOrchestration(unittest.TestCase):
    def setUp(self):
        self.memory = get_interaction_memory()

    def test_schema_has_initial_state_form_presented(self):
        schema = InteractionSchema(id="test_schema_01", mode="form", title="Test Form")
        self.assertEqual(schema.state, InteractionState.FORM_PRESENTED)
        schema_dict = schema.to_dict()
        self.assertEqual(schema_dict["state"], "FORM_PRESENTED")

    def test_request_structured_input_records_form_presented_state(self):
        res = request_structured_input(
            intent="device_diagnostics",
            missing_fields=[
                {"key": "target_device", "data_type": "string", "label": "Perangkat"},
            ],
            title="Form Diagnostik",
        )
        self.assertTrue(res["success"])
        schema_id = res["interaction_schema"]["id"]
        saved_state = self.memory.load(f"dio_state:{schema_id}")
        self.assertEqual(saved_state, InteractionState.FORM_PRESENTED.value)

    def test_submit_structured_input_lifecycle_and_idempotency(self):
        # 1. Create form
        res = request_structured_input(
            intent="pick_subnet",
            missing_fields=[
                {"key": "subnet", "data_type": "string", "label": "Subnet"},
            ],
            title="Pilih Subnet",
        )
        schema_id = res["interaction_schema"]["id"]

        # 2. First submission -> should succeed and transition to COMPLETED
        sub1 = submit_structured_input(
            schema_id=schema_id,
            action_id="submit",
            values={"subnet": "192.168.43.0/24"},
            cancelled=False,
        )
        self.assertTrue(sub1["success"])
        self.assertEqual(sub1["state"], InteractionState.COMPLETED.value)
        self.assertFalse(sub1.get("already_processed", False))

        # 3. Second submission -> idempotent guard, does not re-process
        sub2 = submit_structured_input(
            schema_id=schema_id,
            action_id="submit",
            values={"subnet": "10.0.0.0/24"},
            cancelled=False,
        )
        self.assertTrue(sub2["success"])
        self.assertTrue(sub2.get("already_processed"))
        self.assertEqual(sub2["state"], InteractionState.COMPLETED.value)

    def test_submit_structured_input_cancelled_transition(self):
        res = request_structured_input(
            intent="confirm_test",
            missing_fields=[{"key": "notes", "data_type": "string"}],
            title="Konfirmasi",
        )
        schema_id = res["interaction_schema"]["id"]

        sub = submit_structured_input(
            schema_id=schema_id,
            action_id="cancel",
            values={},
            cancelled=True,
        )
        self.assertTrue(sub["success"])
        self.assertTrue(sub["cancelled"])
        self.assertEqual(sub["state"], InteractionState.CANCELLED.value)

    def test_request_device_choice_formats_options(self):
        devices = [
            {"name": "CHR", "host": "192.168.43.30"},
            {"name": "SW-Core", "host": "192.168.43.2"},
        ]
        res = request_device_choice("auto_diagnose_network", devices, reason="Pilih router")
        self.assertTrue(res["success"])
        self.assertEqual(res["requested_for"], "auto_diagnose_network")
        schema = res["interaction_schema"]
        self.assertEqual(schema["title"], "Pilih perangkat")
        # Check that options are mapped
        fields = schema["sections"][0]["fields"]
        device_field = [f for f in fields if f["id"] == "device_name"][0]
        self.assertEqual(len(device_field["options"]), 2)
        self.assertEqual(device_field["options"][0]["value"], "CHR")
        self.assertEqual(device_field["options"][0]["label"], "CHR (192.168.43.30)")


if __name__ == "__main__":
    unittest.main()
