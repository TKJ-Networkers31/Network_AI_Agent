"""
tests/test_topology_nms_sync_v4.py — Acceptance Test Suite for Phase 4.3:
Event-Driven NMS State Synchronization & In-Memory Stale Observation Decayer.

Verifies all 18 mandated acceptance criteria:
1. Valid interface UP event.
2. Valid interface DOWN event.
3. Unknown device.
4. Unknown interface.
5. Ambiguous edge mapping.
6. Duplicate event delivery.
7. Out-of-order event delivery.
8. Event does not modify relationship class.
9. Event does not create a physical edge.
10. Event does not tombstone an edge.
11. Stale observation after 60 seconds.
12. Fresh observation resets stale state.
13. Decayer lifecycle starts only once.
14. Decayer stops cleanly.
15. EventBus subscriber registration is idempotent.
16. Subscriber is removed during shutdown.
17. Event handler failure does not terminate NMS.
18. Legacy topology API remains compatible.
"""

from __future__ import annotations

import asyncio
import gc
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Dict

from core.events import Event, EventBus, EventNames
from core.topology_engine import TopologyEngine
from core.topology_models import (
    ConfidenceTier,
    EdgeLifecycleState,
    RelationshipClass,
    TopologyEdge,
)


class TestTopologyNmsSyncPhase4_3(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_topology_4_3.db"
        self.engine = TopologyEngine(self.db_path)
        self.bus = EventBus()
        self.loop = asyncio.get_running_loop()
        self.bus.bind_loop(self.loop)

    async def asyncTearDown(self):
        self.engine.stop_nms_sync()
        self.bus.unbind_loop()
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _insert_node(self, node_id: str, name: str, ip: str = "192.168.1.1") -> None:
        self.engine.upsert_node(
            node_id=node_id,
            name=name,
            ip=ip,
            device_type="router",
            ownership_status="owned",
            topology_scope="internal",
            trust_zone="lan",
            provenance="discovery_managed",
        )

    def _insert_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        source_iface: str,
        target_iface: str,
        rel_class: str = "physical",
        rel_subtype: str = "direct_copper",
        oper_status: str = "up",
        last_seen: float = 100.0,
        observation_freshness: str = "fresh",
        confidence_score: float = 1.0,
        confidence_tier: str = "CONFIRMED",
    ) -> TopologyEdge:
        edge = TopologyEdge(
            id=edge_id,
            source_node_id=source_id,
            target_node_id=target_id,
            source_interface=source_iface,
            target_interface=target_iface,
            relationship_class=rel_class,
            relationship_subtype=rel_subtype,
            oper_status=oper_status,
            confidence_tier=confidence_tier,
            confidence_score=confidence_score,
            confidence_rationale="Verified direct physical link.",
            first_seen=last_seen - 50.0,
            last_seen=last_seen,
            observation_freshness=observation_freshness,
            lifecycle_state="active",
            provenance="discovery_managed",
            metadata={"last_nms_timestamp": last_seen},
        )
        self.engine.insert_edge(edge)
        return edge

    # -----------------------------------------------------------------------
    # 1. Valid interface UP event
    # -----------------------------------------------------------------------
    async def test_01_valid_interface_up_event(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_r1_r2_eth1", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="down", last_seen=100.0,
        )

        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 200.0,
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["edges_updated"], 1)

        edge = self.engine.get_edge("edge_r1_r2_eth1")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.oper_status, "up")
        self.assertEqual(edge.last_seen, 200.0)
        self.assertEqual(edge.observation_freshness, "fresh")

        # Verify delta record in topology_changes
        changes = self.engine.list_changes(entity_id="edge_r1_r2_eth1")
        self.assertTrue(any(c.change_type == "STATUS_CHANGED" and c.change_reason == "OPERATIONAL_UP" for c in changes))

    # -----------------------------------------------------------------------
    # 2. Valid interface DOWN event
    # -----------------------------------------------------------------------
    async def test_02_valid_interface_down_event(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_r1_r2_eth1", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 200.0,
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["edges_updated"], 1)

        edge = self.engine.get_edge("edge_r1_r2_eth1")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.oper_status, "down")
        self.assertEqual(edge.last_seen, 200.0)
        self.assertEqual(edge.lifecycle_state, "active")
        self.assertEqual(edge.relationship_class, "physical")

    # -----------------------------------------------------------------------
    # 3. Unknown device
    # -----------------------------------------------------------------------
    async def test_03_unknown_device(self):
        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "non_existent_node_999",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 200.0,
        })

        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "unknown_device")
        self.assertEqual(res["edges_updated"], 0)
        # Verify no edges created
        self.assertEqual(len(self.engine.list_edges()), 0)

    # -----------------------------------------------------------------------
    # 4. Unknown interface
    # -----------------------------------------------------------------------
    async def test_04_unknown_interface(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_r1_r2_eth1", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether99",
            "oper_status": "down",
            "timestamp": 200.0,
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["reason"], "interface_not_mapped")
        self.assertEqual(res["edges_updated"], 0)
        # Existing edge remains untouched
        edge = self.engine.get_edge("edge_r1_r2_eth1")
        self.assertEqual(edge.oper_status, "up")
        self.assertEqual(len(self.engine.list_edges()), 1)

    # -----------------------------------------------------------------------
    # 5. Ambiguous edge mapping
    # -----------------------------------------------------------------------
    async def test_05_ambiguous_edge_mapping(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        # Parallel physical cable and Layer 3 routed edge sharing ether1
        self._insert_edge(
            "edge_physical", "node_r1", "node_r2", "ether1", "ether1",
            rel_class="physical", rel_subtype="direct_copper", oper_status="up",
        )
        self._insert_edge(
            "edge_l3", "node_r1", "node_r2", "ether1", "ether1",
            rel_class="layer3", rel_subtype="routed_point_to_point", oper_status="up",
        )

        # Operational down on ether1 must update BOTH edges consistently
        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 250.0,
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["edges_updated"], 2)

        edge_phys = self.engine.get_edge("edge_physical")
        edge_l3 = self.engine.get_edge("edge_l3")
        self.assertEqual(edge_phys.oper_status, "down")
        self.assertEqual(edge_l3.oper_status, "down")
        # Semantics strictly preserved
        self.assertEqual(edge_phys.relationship_class, "physical")
        self.assertEqual(edge_l3.relationship_class, "layer3")

        # Ambiguous empty interface is safely rejected
        res_empty = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "   ",
            "oper_status": "down",
        })
        self.assertFalse(res_empty["success"])
        self.assertEqual(res_empty["error"], "missing_interface_reference")

    # -----------------------------------------------------------------------
    # 6. Duplicate event delivery
    # -----------------------------------------------------------------------
    async def test_06_duplicate_event_delivery(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_r1_r2", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        payload = {
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 300.0,
        }

        # First delivery
        res1 = self.engine.handle_nms_event(payload)
        self.assertEqual(res1["edges_updated"], 1)
        changes_after_1 = len(self.engine.list_changes(entity_id="edge_r1_r2"))
        self.assertEqual(changes_after_1, 1)

        # Duplicate delivery
        res2 = self.engine.handle_nms_event(payload)
        self.assertEqual(res2["edges_updated"], 0)
        changes_after_2 = len(self.engine.list_changes(entity_id="edge_r1_r2"))
        # No duplicate change record logged
        self.assertEqual(changes_after_2, 1)
        self.assertEqual(len(self.engine.list_edges()), 1)

    # -----------------------------------------------------------------------
    # 7. Out-of-order event delivery
    # -----------------------------------------------------------------------
    async def test_07_out_of_order_event_delivery(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_r1_r2", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="down", last_seen=100.0,
        )

        # Newer observation arrives first at t=500 (oper_status = "up")
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 500.0,
        })
        edge = self.engine.get_edge("edge_r1_r2")
        self.assertEqual(edge.oper_status, "up")
        self.assertEqual(edge.last_seen, 500.0)

        # Delayed / out-of-order event arrives with older t=400 (oper_status = "down")
        res_old = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 400.0,
        })
        self.assertEqual(res_old["edges_updated"], 0)

        # Must not overwrite newer observation
        edge_after = self.engine.get_edge("edge_r1_r2")
        self.assertEqual(edge_after.oper_status, "up")
        self.assertEqual(edge_after.last_seen, 500.0)

    # -----------------------------------------------------------------------
    # 8. Event does not modify relationship class
    # -----------------------------------------------------------------------
    async def test_08_event_does_not_modify_relationship_class(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_physical", "node_r1", "node_r2", "ether1", "ether1",
            rel_class="physical", rel_subtype="direct_copper",
            confidence_score=1.0, confidence_tier="CONFIRMED", oper_status="up",
        )

        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 350.0,
        })

        edge = self.engine.get_edge("edge_physical")
        self.assertEqual(edge.oper_status, "down")
        # Invariance verification:
        self.assertEqual(edge.relationship_class, "physical")
        self.assertEqual(edge.relationship_subtype, "direct_copper")
        self.assertEqual(edge.confidence_score, 1.0)
        self.assertEqual(edge.confidence_tier, "CONFIRMED")
        self.assertEqual(edge.source_node_id, "node_r1")
        self.assertEqual(edge.target_node_id, "node_r2")

    # -----------------------------------------------------------------------
    # 9. Event does not create a physical edge
    # -----------------------------------------------------------------------
    async def test_09_event_does_not_create_a_physical_edge(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        initial_edges = len(self.engine.list_edges())

        # UP event on unmapped interface ether5
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether5",
            "oper_status": "up",
            "timestamp": 400.0,
        })

        # Must NOT invent physical cabling
        self.assertEqual(len(self.engine.list_edges()), initial_edges)

    # -----------------------------------------------------------------------
    # 10. Event does not tombstone an edge
    # -----------------------------------------------------------------------
    async def test_10_event_does_not_tombstone_an_edge(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_link", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 300.0,
        })

        edge = self.engine.get_edge("edge_link")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.lifecycle_state, "active")
        self.assertNotEqual(edge.lifecycle_state, "tombstoned")

    # -----------------------------------------------------------------------
    # 11. Stale observation after 60 seconds
    # -----------------------------------------------------------------------
    async def test_11_stale_observation_after_60_seconds(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_stale_test", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Decay ticker with deterministic clock: age is 65s > 60s
        decayed = self.engine.decay_stale_observations(now=165.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 1)

        edge = self.engine.get_edge("edge_stale_test")
        self.assertEqual(edge.observation_freshness, "stale")
        # Invariants:
        self.assertEqual(edge.oper_status, "up")  # Not link down
        self.assertEqual(edge.lifecycle_state, "active")  # Not deleted or tombstoned
        self.assertEqual(edge.relationship_class, "physical")

        # Calling decay again should be a zero-write no-op
        decayed_again = self.engine.decay_stale_observations(now=165.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed_again, 0)

    # -----------------------------------------------------------------------
    # 12. Fresh observation resets stale state
    # -----------------------------------------------------------------------
    async def test_12_fresh_observation_resets_stale_state(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_reset_test", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="stale",
        )

        # Fresh observation arrives
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 200.0,
        })

        edge = self.engine.get_edge("edge_reset_test")
        self.assertEqual(edge.observation_freshness, "fresh")
        self.assertEqual(edge.last_seen, 200.0)

    # -----------------------------------------------------------------------
    # 13. Decayer lifecycle starts only once
    # -----------------------------------------------------------------------
    async def test_13_decayer_lifecycle_starts_only_once(self):
        started1 = self.engine.start_decayer(interval_sec=30.0, loop=self.loop)
        self.assertTrue(started1)
        self.assertTrue(self.engine.is_decayer_running())

        task1 = self.engine._decayer_task

        # Second start is idempotent and does not create duplicate task
        started2 = self.engine.start_decayer(interval_sec=30.0, loop=self.loop)
        self.assertTrue(started2)
        self.assertIs(self.engine._decayer_task, task1)

        self.engine.stop_decayer()

    # -----------------------------------------------------------------------
    # 14. Decayer stops cleanly
    # -----------------------------------------------------------------------
    async def test_14_decayer_stops_cleanly(self):
        self.engine.start_decayer(interval_sec=10.0, loop=self.loop)
        self.assertTrue(self.engine.is_decayer_running())

        stopped = self.engine.stop_decayer()
        self.assertTrue(stopped)
        self.assertFalse(self.engine.is_decayer_running())

        # Second stop is safe and idempotent
        stopped_again = self.engine.stop_decayer()
        self.assertFalse(stopped_again)

    # -----------------------------------------------------------------------
    # 15. EventBus subscriber registration is idempotent
    # -----------------------------------------------------------------------
    async def test_15_eventbus_subscriber_registration_is_idempotent(self):
        reg1 = self.engine.register_nms_subscriber(bus=self.bus)
        self.assertTrue(reg1)
        self.assertTrue(self.engine.is_subscriber_registered())

        token1 = self.engine._subscriber_token

        # Second registration does not add duplicate subscriber
        reg2 = self.engine.register_nms_subscriber(bus=self.bus)
        self.assertTrue(reg2)
        self.assertEqual(self.engine._subscriber_token, token1)

        self.engine.unregister_nms_subscriber()

    # -----------------------------------------------------------------------
    # 16. Subscriber is removed during shutdown
    # -----------------------------------------------------------------------
    async def test_16_subscriber_is_removed_during_shutdown(self):
        self.engine.register_nms_subscriber(bus=self.bus)
        self.assertTrue(self.engine.is_subscriber_registered())

        unreg = self.engine.unregister_nms_subscriber()
        self.assertTrue(unreg)
        self.assertFalse(self.engine.is_subscriber_registered())

        # Verify bus has no remaining subscribers for topic
        self.assertNotIn(
            EventNames.NMS_INTERFACE_STATUS_CHANGED,
            self.bus._subscribers,
        )

    # -----------------------------------------------------------------------
    # 17. Event handler failure does not terminate NMS
    # -----------------------------------------------------------------------
    async def test_17_event_handler_failure_does_not_terminate_nms(self):
        self.engine.register_nms_subscriber(bus=self.bus)

        # Corrupt event payload published on EventBus
        corrupted_event = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data=None,  # Invalid data
        )

        # Publishing must not raise or terminate EventBus
        try:
            self.bus._dispatch(corrupted_event)
        except Exception as exc:
            self.fail(f"EventBus dispatch failed unexpectedly on malformed event: {exc}")

        # Ensure subsequent valid event processes normally through EventBus
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_safe", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        valid_event = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={
                "device_id": "node_r1",
                "interface_name": "ether1",
                "oper_status": "down",
                "timestamp": 300.0,
            },
        )
        self.bus._dispatch(valid_event)

        edge = self.engine.get_edge("edge_safe")
        self.assertEqual(edge.oper_status, "down")

    # -----------------------------------------------------------------------
    # 18. Legacy topology API remains compatible
    # -----------------------------------------------------------------------
    async def test_18_legacy_topology_api_remains_compatible(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_legacy_compat", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )
        # Also create legacy link
        self.engine.upsert_link(
            source_id="node_r1",
            target_id="node_r2",
            source_port="ether1",
            target_port="ether1",
            link_type="ethernet",
            status="up",
        )

        # Trigger interface DOWN
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 300.0,
        })

        # Query legacy topology output
        topo = self.engine.get_topology()
        self.assertIn("nodes", topo)
        self.assertIn("links", topo)
        self.assertIn("edges", topo)

        # Verify legacy link status reflects down
        matching_links = [l for l in topo["links"] if l["source"] == "node_r1" and l["source_port"] == "ether1"]
        self.assertTrue(len(matching_links) > 0)
        self.assertEqual(matching_links[0]["status"], "down")

        # Verify normalized edge is present and down
        matching_edges = [e for e in topo["edges"] if e["id"] == "edge_legacy_compat"]
        self.assertTrue(len(matching_edges) > 0)
        self.assertEqual(matching_edges[0]["oper_status"], "down")
        self.assertEqual(matching_edges[0]["relationship_class"], "physical")



    # =======================================================================
    # PHASE 4.3 FINAL CORRECTNESS AUDIT: 14 MANDATORY REGRESSION SCENARIOS
    # =======================================================================

    # -----------------------------------------------------------------------
    # Audit Scenario 1: Repeated successful UP observations keep freshness fresh
    # -----------------------------------------------------------------------
    async def test_audit_01_repeated_successful_up_observations_keep_freshness_fresh(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_1", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Observation 1 at t=130.0 (status UP unchanged)
        res1 = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 130.0,
        })
        self.assertTrue(res1["success"])
        e1 = self.engine.get_edge("edge_audit_1")
        self.assertEqual(e1.last_seen, 130.0)
        self.assertEqual(e1.observation_freshness, "fresh")
        self.assertEqual(e1.oper_status, "up")

        # Observation 2 at t=160.0 (status UP unchanged)
        res2 = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 160.0,
        })
        self.assertTrue(res2["success"])
        e2 = self.engine.get_edge("edge_audit_1")
        self.assertEqual(e2.last_seen, 160.0)
        self.assertEqual(e2.observation_freshness, "fresh")

        # Decayer check at t=170.0 (age = 10s < 60s threshold)
        decayed = self.engine.decay_stale_observations(now=170.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 0)
        e3 = self.engine.get_edge("edge_audit_1")
        self.assertEqual(e3.observation_freshness, "fresh")

    # -----------------------------------------------------------------------
    # Audit Scenario 2: Repeated successful DOWN observations keep freshness fresh
    # -----------------------------------------------------------------------
    async def test_audit_02_repeated_successful_down_observations_keep_freshness_fresh(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_2", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="down", last_seen=100.0, observation_freshness="fresh",
        )

        # Repeated DOWN observations
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 140.0,
        })
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 180.0,
        })

        e = self.engine.get_edge("edge_audit_2")
        self.assertEqual(e.last_seen, 180.0)
        self.assertEqual(e.observation_freshness, "fresh")
        self.assertEqual(e.oper_status, "down")

        # Decayer at t=190.0 (age = 10s < 60s threshold)
        decayed = self.engine.decay_stale_observations(now=190.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 0)
        self.assertEqual(self.engine.get_edge("edge_audit_2").observation_freshness, "fresh")

    # -----------------------------------------------------------------------
    # Audit Scenario 3: Unchanged status does not produce duplicate status-transition events
    # -----------------------------------------------------------------------
    async def test_audit_03_unchanged_status_does_not_produce_duplicate_status_transition_events(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_3", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        delta_events = []
        def _on_delta(event: Event):
            delta_events.append(event)
        self.bus.subscribe("topology.delta", _on_delta)

        # 1. Observation event where status is unchanged UP
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 150.0,
        })
        self.assertEqual(len(delta_events), 0)
        changes = self.engine.list_changes(entity_id="edge_audit_3")
        self.assertEqual(len(changes), 0)

        # 2. STATUS_CHANGED event arriving but oper_status is identical to current edge status
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 160.0,
        })
        # Must suppress duplicate status-transition event & delta change
        self.assertEqual(len(delta_events), 0)
        changes = self.engine.list_changes(entity_id="edge_audit_3")
        self.assertEqual(len(changes), 0)

    # -----------------------------------------------------------------------
    # Audit Scenario 4: Successful observations refresh freshness without requiring a transition
    # -----------------------------------------------------------------------
    async def test_audit_04_successful_observations_refresh_freshness_without_requiring_a_transition(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_4", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0,
        )

        # Without any status transition, interface observation arrives at t=155.0
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 155.0,
        })

        # Decayer evaluated at t=170.0:
        # If freshness had NOT been refreshed, age would be 170 - 100 = 70s (> 60s -> stale).
        # Because freshness was refreshed at 155.0, age is 170 - 155 = 15s (<= 60s -> fresh).
        decayed = self.engine.decay_stale_observations(now=170.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 0)
        self.assertEqual(self.engine.get_edge("edge_audit_4").observation_freshness, "fresh")

    # -----------------------------------------------------------------------
    # Audit Scenario 5: Failed polling does not refresh freshness
    # -----------------------------------------------------------------------
    async def test_audit_05_failed_polling_does_not_refresh_freshness(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_5", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Polling fails: NMS emits no interface events for node_r1.
        # last_seen remains at 100.0.
        edge = self.engine.get_edge("edge_audit_5")
        self.assertEqual(edge.last_seen, 100.0)

        # At t=165.0 (65s later), decayer marks it stale
        decayed = self.engine.decay_stale_observations(now=165.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 1)
        self.assertEqual(self.engine.get_edge("edge_audit_5").observation_freshness, "stale")

    # -----------------------------------------------------------------------
    # Audit Scenario 6: No successful observation beyond configured threshold causes stale freshness
    # -----------------------------------------------------------------------
    async def test_audit_06_no_successful_observation_beyond_threshold_causes_stale_freshness(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_6", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # At exactly threshold (t=160.0), age = 60s, not strictly > 60s
        decayed = self.engine.decay_stale_observations(now=160.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 0)
        self.assertEqual(self.engine.get_edge("edge_audit_6").observation_freshness, "fresh")

        # At t=160.1, age = 60.1s (> 60s threshold) -> marked stale
        decayed = self.engine.decay_stale_observations(now=160.1, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 1)
        self.assertEqual(self.engine.get_edge("edge_audit_6").observation_freshness, "stale")

    # -----------------------------------------------------------------------
    # Audit Scenario 7: A stale observation followed by a successful observation returns to fresh
    # -----------------------------------------------------------------------
    async def test_audit_07_stale_observation_followed_by_successful_observation_returns_to_fresh(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_7", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Decay to stale
        self.engine.decay_stale_observations(now=170.0, stale_threshold_sec=60.0)
        self.assertEqual(self.engine.get_edge("edge_audit_7").observation_freshness, "stale")

        # New successful observation arrives at t=180.0
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 180.0,
        })

        edge = self.engine.get_edge("edge_audit_7")
        self.assertEqual(edge.observation_freshness, "fresh")
        self.assertEqual(edge.last_seen, 180.0)

    # -----------------------------------------------------------------------
    # Audit Scenario 8: Restart behavior follows documented persistence model
    # -----------------------------------------------------------------------
    async def test_audit_08_restart_behavior_follows_documented_persistence_model(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_8", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Simulate shutdown of previous instance
        self.engine.stop_nms_sync()

        # Simulate fresh process startup reopening same SQLite database
        restarted_engine = TopologyEngine(self.db_path)

        # Freshness and last_seen must be faithfully restored from SQLite
        edge = restarted_engine.get_edge("edge_audit_8")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.last_seen, 100.0)
        self.assertEqual(edge.observation_freshness, "fresh")

        # Decayer evaluated on restarted instance at t=200.0 (gap of 100s across restart)
        decayed = restarted_engine.decay_stale_observations(now=200.0, stale_threshold_sec=60.0)
        self.assertEqual(decayed, 1)
        self.assertEqual(restarted_engine.get_edge("edge_audit_8").observation_freshness, "stale")

        restarted_engine.stop_nms_sync()

    # -----------------------------------------------------------------------
    # Audit Scenario 9: Decayer does not modify oper_status
    # -----------------------------------------------------------------------
    async def test_audit_09_decayer_does_not_modify_oper_status(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_9_up", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )
        self._insert_edge(
            "edge_audit_9_down", "node_r1", "node_r2", "ether2", "ether2",
            oper_status="down", last_seen=100.0, observation_freshness="fresh",
        )

        self.engine.decay_stale_observations(now=200.0, stale_threshold_sec=60.0)

        # Decayer marks both stale but leaves oper_status strictly intact
        e_up = self.engine.get_edge("edge_audit_9_up")
        self.assertEqual(e_up.observation_freshness, "stale")
        self.assertEqual(e_up.oper_status, "up")

        e_down = self.engine.get_edge("edge_audit_9_down")
        self.assertEqual(e_down.observation_freshness, "stale")
        self.assertEqual(e_down.oper_status, "down")

    # -----------------------------------------------------------------------
    # Audit Scenario 10: Decayer does not modify relationship_class, subtype, confidence, endpoints, or lifecycle_state
    # -----------------------------------------------------------------------
    async def test_audit_10_decayer_does_not_modify_relationship_semantics(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        edge = self._insert_edge(
            "edge_audit_10", "node_r1", "node_r2", "ether1", "ether1",
            rel_class="physical", rel_subtype="direct_copper",
            confidence_tier="CONFIRMED", confidence_score=1.0,
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        self.engine.decay_stale_observations(now=300.0, stale_threshold_sec=60.0)

        decayed_edge = self.engine.get_edge("edge_audit_10")
        self.assertEqual(decayed_edge.observation_freshness, "stale")
        self.assertEqual(decayed_edge.relationship_class, "physical")
        self.assertEqual(decayed_edge.relationship_subtype, "direct_copper")
        self.assertEqual(decayed_edge.confidence_tier, "CONFIRMED")
        self.assertEqual(decayed_edge.confidence_score, 1.0)
        self.assertEqual(decayed_edge.source_node_id, "node_r1")
        self.assertEqual(decayed_edge.target_node_id, "node_r2")
        self.assertEqual(decayed_edge.source_interface, "ether1")
        self.assertEqual(decayed_edge.target_interface, "ether1")
        self.assertEqual(decayed_edge.lifecycle_state, "active")

    # -----------------------------------------------------------------------
    # Audit Scenario 11: Decayer does not delete or tombstone edges
    # -----------------------------------------------------------------------
    async def test_audit_11_decayer_does_not_delete_or_tombstone_edges(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_11", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        initial_count = len(self.engine.list_edges())
        self.engine.decay_stale_observations(now=500.0, stale_threshold_sec=60.0)

        # Edge count invariant
        self.assertEqual(len(self.engine.list_edges()), initial_count)
        edge = self.engine.get_edge("edge_audit_11")
        self.assertIsNotNone(edge)
        self.assertNotEqual(edge.lifecycle_state, "tombstoned")
        self.assertEqual(edge.lifecycle_state, "active")

    # -----------------------------------------------------------------------
    # Audit Scenario 12: Repeated decayer execution does not produce unnecessary database writes
    # -----------------------------------------------------------------------
    async def test_audit_12_repeated_decayer_execution_does_not_produce_unnecessary_writes(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_12", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=100.0, observation_freshness="fresh",
        )

        # Pass 1: transitions edge from fresh to stale (1 write)
        c1 = self.engine.decay_stale_observations(now=200.0, stale_threshold_sec=60.0)
        self.assertEqual(c1, 1)

        # Pass 2: edge is already stale -> 0 writes
        c2 = self.engine.decay_stale_observations(now=205.0, stale_threshold_sec=60.0)
        self.assertEqual(c2, 0)

        # Pass 3: edge is already stale -> 0 writes
        c3 = self.engine.decay_stale_observations(now=210.0, stale_threshold_sec=60.0)
        self.assertEqual(c3, 0)

    # -----------------------------------------------------------------------
    # Audit Scenario 13: NMS shutdown and restart do not create duplicate subscribers or decayer tasks
    # -----------------------------------------------------------------------
    async def test_audit_13_nms_shutdown_and_restart_do_not_create_duplicate_subscribers_or_tasks(self):
        # Initial registration & decayer start
        self.engine.register_nms_subscriber(bus=self.bus)
        self.engine.start_decayer(interval_sec=60.0, stale_threshold_sec=60.0, loop=self.loop)
        self.assertTrue(self.engine.is_subscriber_registered())
        self.assertTrue(self.engine.is_decayer_running())

        # Calling start again must be idempotent and not create duplicate tasks
        t1 = self.engine._decayer_task
        self.assertTrue(self.engine.start_decayer(interval_sec=60.0, stale_threshold_sec=60.0, loop=self.loop))
        self.assertIs(self.engine._decayer_task, t1)

        # Shutdown
        self.engine.stop_nms_sync()
        self.assertFalse(self.engine.is_subscriber_registered())
        self.assertFalse(self.engine.is_decayer_running())

        # Restart
        self.engine.start_nms_sync(interval_sec=60.0, stale_threshold_sec=60.0, loop=self.loop, bus=self.bus)
        self.assertTrue(self.engine.is_subscriber_registered())
        self.assertTrue(self.engine.is_decayer_running())

        # Cleanup
        self.engine.stop_nms_sync()

    # -----------------------------------------------------------------------
    # Audit Scenario 14: Event delivery remains idempotent and out-of-order protection remains effective
    # -----------------------------------------------------------------------
    async def test_audit_14_event_delivery_idempotent_and_out_of_order_protection_effective(self):
        self._insert_node("node_r1", "Router1", "10.0.0.1")
        self._insert_node("node_r2", "Router2", "10.0.0.2")
        self._insert_edge(
            "edge_audit_14", "node_r1", "node_r2", "ether1", "ether1",
            oper_status="up", last_seen=200.0,
        )

        # Out-of-order event arriving with t=150.0 (older than edge last_seen 200.0)
        res_ooo = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": 150.0,
        })
        self.assertEqual(res_ooo["edges_updated"], 0)
        edge = self.engine.get_edge("edge_audit_14")
        self.assertEqual(edge.oper_status, "up")
        self.assertEqual(edge.last_seen, 200.0)

        # Duplicate event at exact same timestamp t=200.0 with same status
        res_dup = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_OBSERVED,
            "device_id": "node_r1",
            "interface_name": "ether1",
            "oper_status": "up",
            "timestamp": 200.0,
        })
        self.assertEqual(res_dup["edges_updated"], 0)


if __name__ == "__main__":
    unittest.main()
