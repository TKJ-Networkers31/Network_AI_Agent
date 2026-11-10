"""
VERA_ECOSYSTEM/tests/test_historical_heritage.py

Acceptance tests for VERA Historical Knowledge & Heritage Engine.
Validates that VERA understands:
  1. What AIRA was (Genesis & Prototype).
  2. Why the transformation into VERA occurred.
  3. Why billing, token quotas, and Stripe paywalls were excised.
  4. What the 15-stage remediation accomplished.
  5. How network capabilities (RCA, The Dude, NMS) evolved.
  6. The VAE dynamic interaction architecture.
  7. The Jet Black Cyber Glass design restoration.
  8. Context injection and REI agent tool functionality.
  9. Non-interference with regular non-historical network operations.
"""

import unittest
from core.knowledge.heritage import get_heritage_service
from core.context.builder import ContextBuilder
from agents.rei.registry import REI_TOOLS, REI_TOOL_CATEGORY


class TestHistoricalHeritageService(unittest.TestCase):
    def setUp(self):
        self.service = get_heritage_service()

    def test_all_seven_canonical_records_loaded(self):
        records = self.service.list_records()
        self.assertEqual(len(records), 7)
        ids = {r["record_id"] for r in records}
        expected = {
            "HERITAGE-01-ORIGIN",
            "HERITAGE-02-EVOLUTION",
            "HERITAGE-03-REMEDIATION-STAGES",
            "HERITAGE-04-BILLING-REMOVAL",
            "HERITAGE-05-VERA-EMERGENCE",
            "HERITAGE-06-VAE-ARCHITECTURE",
            "HERITAGE-07-DESIGN-SYSTEM-RESTORATION",
        }
        self.assertEqual(ids, expected)

    def test_query_aira_origin_and_transformation(self):
        res = self.service.query_heritage("siapa itu AIRA dan kenapa berganti nama ke VERA?")
        self.assertTrue(len(res) > 0)
        found_ids = [r["record_id"] for r in res]
        self.assertIn("HERITAGE-05-VERA-EMERGENCE", found_ids)
        self.assertIn("HERITAGE-01-ORIGIN", found_ids)

    def test_query_billing_and_quota_removal(self):
        res = self.service.query_heritage("kenapa sistem billing dan kuota token dihapus?")
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertEqual(top["record_id"], "HERITAGE-04-BILLING-REMOVAL")
        self.assertIn("kuota", top["key_takeaways"].lower())

    def test_query_stage_14_remediation(self):
        res = self.service.query_heritage("apa yang dikerjakan pada Stage 14 remediasi?")
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertEqual(top["record_id"], "HERITAGE-03-REMEDIATION-STAGES")

    def test_query_network_rca_and_evolution(self):
        res = self.service.query_heritage("bagaimana evolusi 14-step RCA dan the dude topology fabric?")
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertEqual(top["record_id"], "HERITAGE-02-EVOLUTION")

    def test_query_vae_architecture(self):
        res = self.service.query_heritage("jelaskan arsitektur VAE adaptive experience")
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertEqual(top["record_id"], "HERITAGE-06-VAE-ARCHITECTURE")

    def test_query_design_system_restoration(self):
        res = self.service.query_heritage("kenapa palet jet black cyber glass dipulihkan?")
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertEqual(top["record_id"], "HERITAGE-07-DESIGN-SYSTEM-RESTORATION")

    def test_answer_heritage_query_tool_format(self):
        payload = self.service.answer_heritage_query("sejarah platform")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["tool"], "recall_heritage")
        self.assertTrue(payload["count"] > 0)
        self.assertIn("=== HISTORICAL ENGINEERING HERITAGE", payload["context_block"])
        self.assertIn("NOTE: This is verified historical provenance. The active product is VERA.", payload["context_block"])


class TestHeritageAgentToolIntegration(unittest.TestCase):
    def test_recall_heritage_registered_in_rei(self):
        self.assertIn("recall_heritage", REI_TOOLS)
        self.assertEqual(REI_TOOL_CATEGORY.get("recall_heritage"), "heritage")

    def test_recall_heritage_execution(self):
        fn = REI_TOOLS["recall_heritage"]
        result = fn("mengapa AIRA menjadi VERA?")
        self.assertTrue(result["success"])
        self.assertEqual(result["tool"], "recall_heritage")
        self.assertTrue(len(result["records"]) > 0)


class TestContextBuilderHeritageIntegration(unittest.TestCase):
    def setUp(self):
        self.builder = ContextBuilder(
            memory_text=lambda: "=== LONG-TERM MEMORY ===\n- Standard memory item"
        )

    def test_context_injects_heritage_on_relevant_queries(self):
        ctx = self.builder.build("siapa itu AIRA dan bagaimana transformasi menjadi VERA?")
        self.assertIsNotNone(ctx.memory)
        self.assertIn("HISTORICAL ENGINEERING HERITAGE", ctx.memory.text)
        self.assertIn("HERITAGE-01-ORIGIN", ctx.memory.text)
        self.assertIn("HERITAGE-05-VERA-EMERGENCE", ctx.memory.text)

    def test_context_does_not_inject_heritage_on_normal_network_queries(self):
        ctx = self.builder.build("cek status interface ether1 pada router 192.168.88.1")
        self.assertIsNotNone(ctx.memory)
        self.assertNotIn("HISTORICAL ENGINEERING HERITAGE", ctx.memory.text)


if __name__ == "__main__":
    unittest.main()
