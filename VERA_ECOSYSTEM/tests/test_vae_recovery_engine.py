"""
tests/test_vae_recovery_engine.py — VAE Interaction Lifecycle & Universal Workflow Recovery Engine Tests.

Validates:
1. Error taxonomy classification across operational networking errors.
2. Interaction finite state machine transition rules and safeguards.
3. Duplicate device registration conflict recovery (preserving form context, Route A/B/C generation).
4. Connection failure recovery plans (diagnostic ping probe, IP editing).
5. ExperienceComposer workflow-recovery block generation upon execution failure.
"""

import unittest
from unittest.mock import patch, MagicMock

from core.vae.interaction import (
    InteractionState,
    InteractionStateMachine,
    ErrorTaxonomy,
    ErrorClassification,
    classify_operational_error,
)
from core.vae.recovery import (
    UniversalRecoveryPlanner,
    RecoveryPlan,
    RecoveryAction,
)
from core.vae.models import VaeBlockType
from core.vae.composer import ExperienceComposer
from core.vae.planner import ExperiencePlanner


class TestVaeErrorClassification(unittest.TestCase):

    def test_classify_duplicate_resource(self):
        err = "Device 'CHR-Edge-01' sudah ada. Pakai update_device untuk mengubahnya."
        res = classify_operational_error(err, tool_name="add_device")
        self.assertEqual(res.category, ErrorTaxonomy.DUPLICATE_RESOURCE)
        self.assertEqual(res.target_resource, "CHR-Edge-01")
        self.assertFalse(res.can_retry)
        self.assertTrue(res.can_edit)
        self.assertIn("sudah terdaftar", res.user_message)

    def test_classify_resource_not_found(self):
        err = "Device 'Router-Office' tidak ditemukan dalam inventori."
        res = classify_operational_error(err, tool_name="mikrotik_get_resources")
        self.assertEqual(res.category, ErrorTaxonomy.RESOURCE_NOT_FOUND)
        self.assertEqual(res.target_resource, "Router-Office")

    def test_classify_connection_failed(self):
        err = "Connection refused while connecting to 192.168.88.1:22 (SSH)"
        res = classify_operational_error(err, tool_name="mikrotik_run_command")
        self.assertEqual(res.category, ErrorTaxonomy.CONNECTION_FAILED)
        self.assertTrue(res.can_retry)
        self.assertTrue(res.can_edit)

    def test_classify_timeout(self):
        err = "Operation timed out after 10000ms waiting for socket response."
        res = classify_operational_error(err, tool_name="network_ping")
        self.assertEqual(res.category, ErrorTaxonomy.TIMEOUT)
        self.assertTrue(res.can_retry)

    def test_classify_permission_denied(self):
        err = "Akses ditolak: role 'viewer' tidak memiliki hak akses device.write"
        res = classify_operational_error(err, tool_name="delete_device")
        self.assertEqual(res.category, ErrorTaxonomy.PERMISSION_DENIED)
        self.assertTrue(res.requires_authorization)
        self.assertFalse(res.can_retry)

    def test_classify_authentication_required(self):
        err = "Authentication failed: invalid password for user admin"
        res = classify_operational_error(err, tool_name="mikrotik_run_command")
        self.assertEqual(res.category, ErrorTaxonomy.AUTHENTICATION_REQUIRED)
        self.assertTrue(res.can_edit)

    def test_classify_device_offline(self):
        err = "Host is unreachable: device R-Border is offline"
        res = classify_operational_error(err, tool_name="mikrotik_backup_config")
        self.assertEqual(res.category, ErrorTaxonomy.DEVICE_OFFLINE)
        self.assertEqual(res.target_resource, "R-Border")


class TestInteractionStateMachine(unittest.TestCase):

    def test_valid_lifecycle_transitions(self):
        fsm = InteractionStateMachine("wf_101", initial_state=InteractionState.IDLE)
        self.assertEqual(fsm.state, InteractionState.IDLE)

        # IDLE -> DRAFT
        fsm.transition_to(InteractionState.DRAFT, reason="Form opened")
        self.assertEqual(fsm.state, InteractionState.DRAFT)

        # DRAFT -> VALIDATING
        fsm.transition_to(InteractionState.VALIDATING, reason="User clicked submit")
        self.assertEqual(fsm.state, InteractionState.VALIDATING)

        # VALIDATING -> READY
        fsm.transition_to(InteractionState.READY, reason="Fields valid")
        self.assertEqual(fsm.state, InteractionState.READY)

        # READY -> SUBMITTING
        fsm.transition_to(InteractionState.SUBMITTING, reason="Dispatching API call")
        self.assertEqual(fsm.state, InteractionState.SUBMITTING)

        # SUBMITTING -> PROCESSING
        fsm.transition_to(InteractionState.PROCESSING, reason="Agent executing tool")
        self.assertEqual(fsm.state, InteractionState.PROCESSING)

        # PROCESSING -> FAILED
        fsm.transition_to(InteractionState.FAILED, reason="Duplicate device detected")
        self.assertEqual(fsm.state, InteractionState.FAILED)

        # FAILED -> RECOVERY_AVAILABLE
        fsm.transition_to(InteractionState.RECOVERY_AVAILABLE, reason="Generated recovery plan")
        self.assertEqual(fsm.state, InteractionState.RECOVERY_AVAILABLE)

        # RECOVERY_AVAILABLE -> DRAFT (User chooses to edit form)
        fsm.transition_to(InteractionState.DRAFT, reason="User opened edit form")
        self.assertEqual(fsm.state, InteractionState.DRAFT)

        # Check history contains 1 init + 8 transitions = 9 events
        self.assertEqual(len(fsm.history), 9)

    def test_illegal_transition_rejected(self):
        fsm = InteractionStateMachine("wf_102", initial_state=InteractionState.IDLE)
        # IDLE directly to SUCCEEDED is illegal
        with self.assertRaises(ValueError) as ctx:
            fsm.transition_to(InteractionState.SUCCEEDED, reason="Bypassing lifecycle")
        self.assertIn("Illegal transition", str(ctx.exception))
        self.assertEqual(fsm.state, InteractionState.IDLE)


class TestUniversalWorkflowRecoveryPlanner(unittest.TestCase):

    def setUp(self):
        self.planner = UniversalRecoveryPlanner()

    @patch("core.inventory_store.get_inventory_store")
    def test_duplicate_device_registration_recovery(self, mock_get_store):
        # Mock existing inventory device
        mock_store = MagicMock()
        mock_store.get_device.return_value = {
            "success": True,
            "device": {
                "name": "CHR-Core",
                "host": "192.168.1.1",
                "port": 22,
                "username": "admin",
                "device_type": "mikrotik",
                "status": "online",
                "version": "RouterOS 7.15",
            },
        }
        mock_get_store.return_value = mock_store

        tool_input = {
            "name": "CHR-Core",
            "host": "192.168.1.10",
            "port": 2222,
            "username": "superadmin",
            "device_type": "mikrotik",
        }
        error_output = {"error": "Device 'CHR-Core' sudah ada. Pakai update_device untuk mengubahnya."}

        plan = self.planner.plan_recovery(
            tool_name="add_device",
            tool_input=tool_input,
            error_output=error_output,
        )

        self.assertIsInstance(plan, RecoveryPlan)
        self.assertEqual(plan.error_classification.category, ErrorTaxonomy.DUPLICATE_RESOURCE)
        self.assertEqual(plan.original_tool, "add_device")
        self.assertIsNotNone(plan.existing_resource)
        self.assertEqual(plan.existing_resource["name"], "CHR-Core")

        # Verify Routes:
        # Route A: UPDATE_EXISTING
        act_update = next((a for a in plan.recovery_actions if a.action_type == "UPDATE_EXISTING"), None)
        self.assertIsNotNone(act_update)
        self.assertTrue(act_update.is_primary)
        self.assertEqual(act_update.target_tool, "update_device")
        self.assertEqual(act_update.prefilled_data["name"], "CHR-Core")
        self.assertEqual(act_update.prefilled_data["host"], "192.168.1.10")
        self.assertIsNotNone(act_update.schema)

        # Route B: EDIT_FORM
        act_edit = next((a for a in plan.recovery_actions if a.action_type == "EDIT_FORM"), None)
        self.assertIsNotNone(act_edit)
        self.assertEqual(act_edit.target_tool, "add_device")
        self.assertEqual(act_edit.prefilled_data["host"], "192.168.1.10")

        # Route C: INSPECT_RESOURCE
        act_inspect = next((a for a in plan.recovery_actions if a.action_type == "INSPECT_RESOURCE"), None)
        self.assertIsNotNone(act_inspect)
        self.assertEqual(act_inspect.target_tool, "get_device")

        # Route D: CANCEL
        act_cancel = next((a for a in plan.recovery_actions if a.action_type == "CANCEL"), None)
        self.assertIsNotNone(act_cancel)

    def test_connection_failure_recovery_plan(self):
        tool_input = {"device_name": "R-Gateway", "command": "/system resource print"}
        error_output = "Connection refused to R-Gateway on port 22"

        plan = self.planner.plan_recovery(
            tool_name="mikrotik_run_command",
            tool_input=tool_input,
            error_output=error_output,
        )

        self.assertEqual(plan.error_classification.category, ErrorTaxonomy.CONNECTION_FAILED)
        action_types = [a.action_type for a in plan.recovery_actions]
        self.assertIn("DIAGNOSTIC_PROBE", action_types)
        self.assertIn("RETRY", action_types)
        self.assertIn("EDIT_FORM", action_types)
        self.assertIn("CANCEL", action_types)


class TestComposerWorkflowRecoveryIntegration(unittest.TestCase):

    def setUp(self):
        self.planner = ExperiencePlanner()
        self.composer = ExperienceComposer(planner=self.planner)

    @patch("core.inventory_store.get_inventory_store")
    def test_compose_with_failed_tool_generates_workflow_recovery_block(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.get_device.return_value = {"success": True, "device": {"name": "CHR-Test", "host": "10.0.0.1"}}
        mock_get_store.return_value = mock_store

        answer = "Gagal mendaftarkan perangkat CHR-Test karena perangkat dengan nama tersebut sudah ada di inventori."
        steps = [
            {
                "tool": "add_device",
                "args": {"name": "CHR-Test", "host": "10.0.0.2", "port": 22},
                "output": "Device 'CHR-Test' sudah ada. Pakai update_device untuk mengubahnya.",
                "status": "failed",
            }
        ]

        payload = self.composer.compose(
            answer=answer,
            steps=steps,
            query="tambahkan router CHR-Test",
        )

        # Check payload contains markdown narrative and workflow-recovery block
        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.MARKDOWN.value, block_types)
        self.assertIn(VaeBlockType.WORKFLOW_RECOVERY.value, block_types)

        rec_block = next(b for b in payload.blocks if b.type == VaeBlockType.WORKFLOW_RECOVERY.value)
        self.assertEqual(rec_block.data["category"], "DUPLICATE_RESOURCE")
        self.assertEqual(rec_block.data["original_tool"], "add_device")
        self.assertGreater(len(rec_block.data["recovery_actions"]), 0)


if __name__ == "__main__":
    unittest.main()
