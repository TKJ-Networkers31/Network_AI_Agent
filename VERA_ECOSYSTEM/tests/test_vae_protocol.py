"""
tests/test_vae_protocol.py — Unit tests for VAE Protocol & Adapters.
"""

import unittest

from core.vae.models import VaeBlock, VaeBlockType, VaePayload
from core.vae.protocol import validate_vae_block, validate_vae_payload, SUPPORTED_BLOCK_TYPES
from core.vae.adapter import brain_response_to_vae_payload


class TestVaeProtocol(unittest.TestCase):
    def test_supported_block_types(self):
        self.assertIn("markdown", SUPPORTED_BLOCK_TYPES)
        self.assertIn("action-card", SUPPORTED_BLOCK_TYPES)
        self.assertIn("dio-interaction", SUPPORTED_BLOCK_TYPES)
        self.assertIn("graph", SUPPORTED_BLOCK_TYPES)
        self.assertIn("map", SUPPORTED_BLOCK_TYPES)
        self.assertNotIn("unknown", SUPPORTED_BLOCK_TYPES)

    def test_validate_valid_block(self):
        raw = {
            "id": "blk_1",
            "type": "markdown",
            "data": {"content": "Hello VERA"},
        }
        ok, block, err = validate_vae_block(raw)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(block.id, "blk_1")
        self.assertEqual(block.type, "markdown")
        self.assertEqual(block.data["content"], "Hello VERA")

    def test_validate_unsupported_block_falls_back_to_unknown(self):
        raw = {
            "id": "blk_bad",
            "type": "arbitrary_executable_script",
            "data": {"exec": "danger"},
        }
        ok, block, err = validate_vae_block(raw)
        self.assertFalse(ok)
        self.assertEqual(block.type, "unknown")
        self.assertIn("Unsupported block type", err)

    def test_brain_response_adapter_generates_markdown_and_dio_blocks(self):
        schema = {
            "id": "schema_test",
            "mode": "form",
            "sections": [],
            "actions": [],
        }
        payload = brain_response_to_vae_payload(
            answer="Here is your requested form:",
            interaction_schema=schema,
            session_id="sess_123",
        )
        self.assertEqual(payload.protocol, "vae")
        self.assertIn(payload.version, ("1.0", "2.0"))
        self.assertEqual(len(payload.blocks), 2)
        self.assertEqual(payload.blocks[0].type, "markdown")
        self.assertEqual(payload.blocks[1].type, "dio-interaction")
        self.assertEqual(payload.blocks[1].data["schema"]["id"], "schema_test")

    def test_validate_vae_payload_tolerates_corrupted_blocks(self):
        raw_payload = {
            "protocol": "vae",
            "version": "1.0",
            "blocks": [
                {"id": "b1", "type": "markdown", "data": {"content": "ok"}},
                {"id": "b2", "type": "malformed_block"},
                "not_even_a_dict",
            ],
        }
        ok, payload, issues = validate_vae_payload(raw_payload)
        self.assertFalse(ok)
        self.assertEqual(len(payload.blocks), 2)  # b1 (valid) + b2 (fallback unknown)
        self.assertEqual(payload.blocks[0].type, "markdown")
        self.assertEqual(payload.blocks[1].type, "unknown")
        self.assertEqual(len(issues), 2)


if __name__ == "__main__":
    unittest.main()
