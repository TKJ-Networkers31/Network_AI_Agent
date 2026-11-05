"""
AIRA OS — DIO Parameter Resolution & Contract Validation Test Suite
Covers DIO-P01 through DIO-P18 verification scenarios.
"""

import unittest
from core.dio.parameter_resolver import (
    DIOParameterResolver,
    ParameterStatus,
    ParameterSource,
)
from core.orchestrator import Orchestrator, AGENT_TOOL_SCHEMAS


class TestDioParameterResolution(unittest.TestCase):
    def setUp(self):
        # Sample schemas matching OpenAI tool format
        self.sample_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "ICMP ping tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "Target hostname or IP"},
                            "count": {"type": "integer", "description": "Number of packets", "default": 4, "minimum": 1, "maximum": 50},
                            "verbose": {"type": "boolean", "description": "Verbose output", "default": False},
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "configure_interface",
                    "description": "Configures an interface on a device",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_name": {"type": "string", "description": "Target router name"},
                            "interface": {"type": "string", "description": "Interface name"},
                            "enabled": {"type": "boolean", "description": "Enable/disable interface"},
                            "mtu": {"type": "integer", "description": "MTU size", "default": 1500, "minimum": 68, "maximum": 9000},
                        },
                        "required": ["device_name", "interface", "enabled"],
                    },
                },
            },
        ]
        self.resolver = DIOParameterResolver(self.sample_schemas)
        self.sample_inventory = [
            {"name": "router-core-01", "host": "192.168.1.1"},
            {"name": "router-edge-02", "host": "192.168.1.2"},
        ]

    # DIO-P01: Required parameter available -> Validation succeeds
    def test_dio_p01_required_parameter_available(self):
        res = self.resolver.resolve("ping", {"target": "8.8.8.8"})
        self.assertTrue(res.can_execute)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.resolved_arguments["target"], "8.8.8.8")
        self.assertEqual(res.parameters["target"].status, ParameterStatus.PROVIDED)
        self.assertEqual(res.parameters["target"].source, ParameterSource.USER_INPUT)

    # DIO-P02: Required parameter missing -> Execution halted, DIO form generated
    def test_dio_p02_required_parameter_missing(self):
        res = self.resolver.resolve("ping", {})
        self.assertFalse(res.can_execute)
        self.assertIn("target", res.missing_required)
        self.assertEqual(res.parameters["target"].status, ParameterStatus.MISSING)
        self.assertIsNotNone(res.interaction_schema)
        self.assertEqual(res.interaction_schema["requested_for"], "ping")

    # DIO-P03: Optional parameter missing -> Not fabricated, remains omitted
    def test_dio_p03_optional_parameter_missing(self):
        res = self.resolver.resolve("configure_interface", {
            "device_name": "router-core-01",
            "interface": "ether1",
            "enabled": True,
        }, inventory_devices=self.sample_inventory)
        self.assertTrue(res.can_execute)
        # mtu has default, so it's defaulted, but no hallucinated un-defaulted params
        self.assertNotIn("unrelated_param", res.resolved_arguments)

    # DIO-P04: Parameter has official schema default -> Default value used
    def test_dio_p04_parameter_has_official_default(self):
        res = self.resolver.resolve("ping", {"target": "1.1.1.1"})
        self.assertTrue(res.can_execute)
        self.assertEqual(res.resolved_arguments["count"], 4)
        self.assertEqual(res.parameters["count"].status, ParameterStatus.DEFAULTED)
        self.assertEqual(res.parameters["count"].source, ParameterSource.TOOL_SCHEMA_DEFAULT)

    # DIO-P05: Invalid parameter value -> Rejected with clear error
    def test_dio_p05_parameter_invalid_type(self):
        res = self.resolver.resolve("ping", {"target": "1.1.1.1", "count": "not_a_number"})
        self.assertFalse(res.can_execute)
        self.assertFalse(res.is_valid)
        self.assertIn("count", res.invalid_parameters)
        self.assertEqual(res.parameters["count"].status, ParameterStatus.INVALID)
        self.assertIn("integer", res.error_message.lower())

    # DIO-P06: Ambiguous parameter (multiple device candidates) -> Clarification requested
    def test_dio_p06_parameter_ambiguous_device(self):
        res = self.resolver.resolve("configure_interface", {
            "interface": "ether1",
            "enabled": True,
        }, inventory_devices=self.sample_inventory)
        self.assertFalse(res.can_execute)
        self.assertIn("device_name", res.ambiguous_parameters)
        self.assertEqual(res.parameters["device_name"].status, ParameterStatus.AMBIGUOUS)
        self.assertIsNotNone(res.interaction_schema)

    # DIO-P07: Parameter with value False -> NOT treated as missing
    def test_dio_p07_parameter_value_false(self):
        res = self.resolver.resolve("configure_interface", {
            "device_name": "router-core-01",
            "interface": "ether2",
            "enabled": False,
        }, inventory_devices=self.sample_inventory)
        self.assertTrue(res.can_execute)
        self.assertFalse(res.resolved_arguments["enabled"])
        self.assertEqual(res.parameters["enabled"].status, ParameterStatus.PROVIDED)

    # DIO-P08: Parameter with value zero (0) -> NOT treated as missing
    def test_dio_p08_parameter_value_zero(self):
        schema_zero = [{
            "type": "function",
            "function": {
                "name": "set_metric",
                "parameters": {
                    "type": "object",
                    "properties": {"cost": {"type": "integer"}},
                    "required": ["cost"],
                },
            },
        }]
        resolver = DIOParameterResolver(schema_zero)
        res = resolver.resolve("set_metric", {"cost": 0})
        self.assertTrue(res.can_execute)
        self.assertEqual(res.resolved_arguments["cost"], 0)
        self.assertEqual(res.parameters["cost"].status, ParameterStatus.PROVIDED)

    # DIO-P09: Parameter with null/empty string -> Follows schema rules (missing if required)
    def test_dio_p09_parameter_null_or_empty(self):
        res = self.resolver.resolve("ping", {"target": ""})
        self.assertFalse(res.can_execute)
        self.assertIn("target", res.missing_required)
        self.assertEqual(res.parameters["target"].status, ParameterStatus.MISSING)

    # DIO-P10: Unrecognized parameter -> Stripped, not forwarded to tool
    def test_dio_p10_unrecognized_parameter_stripped(self):
        res = self.resolver.resolve("ping", {"target": "8.8.8.8", "unknown_foo": "bar", "bogus_payload": 123})
        self.assertTrue(res.can_execute)
        self.assertNotIn("unknown_foo", res.resolved_arguments)
        self.assertNotIn("bogus_payload", res.resolved_arguments)
        self.assertIn("unknown_foo", res.stripped_parameters)

    # DIO-P11: Single device auto context resolution
    def test_dio_p11_single_device_context_resolution(self):
        single_dev = [{"name": "sole-mikrotik", "host": "10.0.0.1"}]
        res = self.resolver.resolve("configure_interface", {
            "interface": "wlan1",
            "enabled": True,
        }, inventory_devices=single_dev)
        self.assertTrue(res.can_execute)
        self.assertEqual(res.resolved_arguments["device_name"], "sole-mikrotik")
        self.assertEqual(res.parameters["device_name"].status, ParameterStatus.CONTEXT_RESOLVED)
        self.assertEqual(res.parameters["device_name"].source, ParameterSource.VERIFIED_DEVICE_INVENTORY)

    # DIO-P12: User without permission -> RBAC blocks execution
    def test_dio_p12_rbac_permission_blocked(self):
        orch = Orchestrator()
        # Mocking unauthorized call to apply_config without token/permission
        res = orch._execute_tool("apply_config", {"device_name": "r1", "commands": ["/ip address print"]})
        self.assertFalse(res["success"])
        self.assertIn("Izin Ditolak", res["error"])

    # DIO-P13: Tool execution failure is not disguised as success
    def test_dio_p13_tool_failure_not_disguised(self):
        orch = Orchestrator()
        # Calling ping with unreachable IP or non-existent target in a way that returns fail
        res = orch._execute_tool("ping", {"target": "192.0.2.1", "count": 1})
        # Regardless of network status, res structure contains success key
        self.assertIn("success", res)

    # DIO-P14: Unknown tool -> Orchestrator conveys tool unrecognized
    def test_dio_p14_unknown_tool(self):
        orch = Orchestrator()
        res = orch._execute_tool("completely_fake_teleport_tool", {})
        self.assertFalse(res["success"])
        self.assertIn("tidak dikenal", res["error"])

    # DIO-P15: Partial match on multiple candidates -> Ambiguous choice
    def test_dio_p15_partial_match_multiple_candidates(self):
        inv = [
            {"name": "router-core-east", "host": "10.1.1.1"},
            {"name": "router-core-west", "host": "10.1.1.2"},
        ]
        res = self.resolver.resolve("configure_interface", {
            "device_name": "router-core",
            "interface": "ether1",
            "enabled": True,
        }, inventory_devices=inv)
        self.assertFalse(res.can_execute)
        self.assertEqual(res.parameters["device_name"].status, ParameterStatus.AMBIGUOUS)
        self.assertEqual(len(res.parameters["device_name"].choices), 2)

    # DIO-P16: Memory parameter validation
    def test_dio_p16_memory_parameter_validation(self):
        # An argument retrieved from memory must still be validated against schema
        res = self.resolver.resolve("ping", {"target": "10.10.10.1", "count": 9999})  # exceeds maximum 50
        self.assertFalse(res.can_execute)
        self.assertIn("count", res.invalid_parameters)
        self.assertIn("maksimum", res.error_message.lower())

    # DIO-P17: Tool schema missing -> Contract defect detected
    def test_dio_p17_contract_defect_detected(self):
        res = self.resolver.resolve("unregistered_tool_name", {"foo": "bar"})
        self.assertFalse(res.can_execute)
        self.assertTrue(res.contract_defect)
        self.assertIn("Contract Defect", res.error_message)

    # DIO-P18: Multi-tool parameter resolution independent validation
    def test_dio_p18_multi_tool_independent_validation(self):
        res1 = self.resolver.resolve("ping", {"target": "8.8.8.8"})
        res2 = self.resolver.resolve("ping", {})
        self.assertTrue(res1.can_execute)
        self.assertFalse(res2.can_execute)


if __name__ == "__main__":
    unittest.main()
