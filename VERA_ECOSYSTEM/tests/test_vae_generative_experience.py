"""
tests/test_vae_generative_experience.py — VAE Generative Experience & Planner Tests.

Validates the ExperiencePlanner, ExperienceComposer, Narrative-First policy,
sanitization rules, and structured visual representations across all intent types.
"""

import unittest

from core.vae.models import VaeBlockType, VaePayload
from core.vae.planner import ExperiencePlanner, VaeIntent
from core.vae.composer import ExperienceComposer
from core.vae.adapter import brain_response_to_vae_payload


class TestVaeGenerativeExperience(unittest.TestCase):

    def setUp(self):
        self.planner = ExperiencePlanner()
        self.composer = ExperienceComposer(planner=self.planner)

    def test_intent_planning_resource_inspection(self):
        steps = [
            {
                "tool": "mikrotik_get_resources",
                "args": {"device_name": "hAP-ac-lite"},
                "output": "uptime: 2w4d\ncpu-load: 14%\nfree-memory: 54.2MiB\ntotal-memory: 64.0MiB\nversion: 6.49.10",
            }
        ]
        plan = self.planner.plan(query="cek resource router", steps=steps)
        self.assertEqual(plan.intent, VaeIntent.RESOURCE_INSPECTION)
        self.assertEqual(plan.primary_device, "hAP-ac-lite")
        block_types = [b.block_type for b in plan.planned_blocks]
        self.assertIn("markdown", block_types)
        self.assertIn("resource-gauge", block_types)
        self.assertIn("metric-grid", block_types)

    def test_compose_resource_inspection_generates_gauges_and_grid(self):
        answer = "Router hAP-ac-lite beroperasi optimal dengan CPU load 14%."
        steps = [
            {
                "tool": "mikrotik_get_resources",
                "args": {"device_name": "hAP-ac-lite"},
                "output": "uptime: 2w4d\ncpu-load: 14%\nfree-memory: 54.2MiB\ntotal-memory: 64.0MiB\nfree-hdd-space: 8.0MiB\ntotal-hdd-space: 16.0MiB\nboard-name: hAP ac lite\nversion: 6.49.10",
            }
        ]
        payload = self.composer.compose(answer=answer, steps=steps, query="status cpu")
        self.assertEqual(payload.protocol, "vae")
        self.assertEqual(payload.version, "2.0")

        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.MARKDOWN.value, block_types)
        self.assertIn(VaeBlockType.RESOURCE_GAUGE.value, block_types)
        self.assertIn(VaeBlockType.METRIC_GRID.value, block_types)

        # Validate resource gauge payload
        gauge_block = next(b for b in payload.blocks if b.type == VaeBlockType.RESOURCE_GAUGE.value)
        self.assertEqual(gauge_block.data["cpu"]["value"], 14.0)
        self.assertEqual(gauge_block.data["cpu"]["status"], "healthy")
        self.assertEqual(gauge_block.data["memory"]["total_mb"], 64.0)
        self.assertEqual(gauge_block.data["device"], "hAP ac lite")

    def test_compose_network_diagnostics_traceroute(self):
        answer = "Traceroute ke 8.8.8.8 berhasil mencapai tujuan dalam 3 hop."
        steps = [
            {
                "tool": "network_traceroute",
                "args": {"target": "8.8.8.8"},
                "output": {
                    "target": "8.8.8.8",
                    "reached": True,
                    "total_hops": 3,
                    "hops": [
                        {"hop": 1, "host": "gateway.local", "ip": "192.168.0.1", "avg_rtt_ms": 1.2, "status": "SUCCESS"},
                        {"hop": 2, "host": "isp-core.net", "ip": "10.20.30.1", "avg_rtt_ms": 8.5, "status": "SUCCESS"},
                        {"hop": 3, "host": "dns.google", "ip": "8.8.8.8", "avg_rtt_ms": 14.2, "status": "REACHED"},
                    ],
                },
            }
        ]
        payload = self.composer.compose(answer=answer, steps=steps, query="traceroute ke 8.8.8.8")
        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.MARKDOWN.value, block_types)
        self.assertIn(VaeBlockType.HOP_TRACEROUTE.value, block_types)

        trace_block = next(b for b in payload.blocks if b.type == VaeBlockType.HOP_TRACEROUTE.value)
        self.assertEqual(len(trace_block.data["hops"]), 3)
        self.assertTrue(trace_block.data["reached"])

    def test_compose_interface_inspection(self):
        answer = "Berikut status antarmuka pada router utama:"
        steps = [
            {
                "tool": "mikrotik_get_interfaces",
                "args": {"device_name": "R-Core"},
                "output": "Flags: D - dynamic, X - disabled, R - running, S - slave\n #    NAME      TYPE       ACTUAL-MTU\n 0  R ether1    ether            1500\n 1  R ether2    ether            1500\n 2  X wlan1     wlan             1500",
            }
        ]
        payload = self.composer.compose(answer=answer, steps=steps, query="cek interface")
        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.INTERFACE_STATUS.value, block_types)

        iface_block = next(b for b in payload.blocks if b.type == VaeBlockType.INTERFACE_STATUS.value)
        self.assertEqual(iface_block.data["total_count"], 3)
        self.assertEqual(iface_block.data["up_count"], 2)

    def test_compose_routing_analysis(self):
        answer = "Tabel routing menunjukkan default gateway aktif melalui 192.168.1.1."
        steps = [
            {
                "tool": "mikrotik_get_routes",
                "args": {"device_name": "R-Gateway"},
                "output": "Flags: X - disabled, A - active, D - dynamic, C - connect, S - static\n #      DST-ADDRESS        PREF-SRC        GATEWAY            DISTANCE\n 0 A S  0.0.0.0/0                          192.168.1.1               1\n 1 ADC  192.168.1.0/24     192.168.1.2     ether1                    0",
            }
        ]
        payload = self.composer.compose(answer=answer, steps=steps, query="tampilkan tabel route")
        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.ROUTE_TABLE.value, block_types)

    def test_sanitize_narrative_purges_leaking_tool_artifacts(self):
        dirty_answer = "Pemeriksaan selesai. 1 tool digunakan svg.<br>Router beroperasi dengan normal.<br/><br/>Tidak ada masalah."
        cleaned = ExperienceComposer.sanitize_narrative(dirty_answer)
        self.assertNotIn("1 tool digunakan", cleaned)
        self.assertNotIn("<br>", cleaned)
        self.assertNotIn("<br/>", cleaned)
        self.assertIn("Pemeriksaan selesai.", cleaned)
        self.assertIn("Router beroperasi dengan normal.", cleaned)

    def test_general_explanation_produces_narrative_only(self):
        answer = "OSPF (Open Shortest Path First) adalah protokol link-state IGP yang menggunakan algoritma Dijkstra."
        payload = self.composer.compose(answer=answer, steps=[], query="apa itu ospf")
        self.assertEqual(len(payload.blocks), 1)
        self.assertEqual(payload.blocks[0].type, VaeBlockType.MARKDOWN.value)

    def test_action_card_generated_for_approval_schemas(self):
        answer = "Saya menyiapkan konfigurasi firewall baru untuk di-apply."
        schema = {
            "id": "act_fw_01",
            "mode": "action",
            "title": "Terapkan Aturan Firewall Drop Invalid",
            "command": "/ip firewall filter add chain=input connection-state=invalid action=drop",
            "risk_level": "medium",
        }
        payload = self.composer.compose(answer=answer, interaction_schema=schema, query="pasang firewall")
        block_types = [b.type for b in payload.blocks]
        self.assertIn(VaeBlockType.ACTION_CARD.value, block_types)


if __name__ == "__main__":
    unittest.main()
