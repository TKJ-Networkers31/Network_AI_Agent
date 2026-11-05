"""
AIRA OS — Unit and Verification Tests for WP 6.6 (Health, Baselines & Anomaly Intelligence).
"""

from __future__ import annotations

import time
import pytest

from core.network_intelligence.anomaly_engine import AnomalyEngine
from core.network_intelligence.baseline_engine import BaselineEngine
from core.network_intelligence.evidence_service import UnifiedEvidenceService
from core.network_intelligence.health_engine import NetworkHealthEngine
from core.network_intelligence.intelligence_models import HealthStatus
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph


class TestWP66BaselinesAndAnomalies:
    def test_baseline_minimum_clean_sample_and_median_mad(self) -> None:
        engine = BaselineEngine(min_samples=5, max_samples=20)
        now = 1_700_000_000.0

        # Ingest 4 samples -> status must be INSUFFICIENT_SAMPLES
        for i in range(4):
            rec, note = engine.ingest_sample(
                "R1", "device:R1", "cpu_load_percent", 20.0 + i, timestamp=now + i
            )
            assert note == "INGESTED"
            assert rec is not None
            assert rec.status == "INSUFFICIENT_SAMPLES"

        # 5th sample -> status becomes ACTIVE
        rec, note = engine.ingest_sample(
            "R1", "device:R1", "cpu_load_percent", 24.0, timestamp=now + 4
        )
        assert rec is not None
        assert rec.status == "ACTIVE"
        assert rec.sample_count == 5
        assert rec.median_value == 22.0
        assert rec.mad_value == 1.0

        # None value is skipped and does NOT corrupt baseline
        rec_none, note_none = engine.ingest_sample(
            "R1", "device:R1", "cpu_load_percent", None, timestamp=now + 5
        )
        assert note_none == "SKIPPED_MISSING_VALUE"
        assert rec_none.sample_count == 5

    def test_baseline_reboot_invalidation_and_counter_reset_protection(self) -> None:
        engine = BaselineEngine(min_samples=3)
        now = 1_700_000_000.0

        # Ingest 3 clean samples with uptime 1000s, 1010s, 1020s
        for idx, up in enumerate([1000, 1010, 1020]):
            engine.ingest_sample(
                "R1", "device:R1", "cpu_load_percent", 30.0,
                timestamp=now + idx * 10, uptime_seconds=up
            )
        b = engine.get_baseline("R1", "device:R1", "cpu_load_percent")
        assert b.status == "ACTIVE"
        assert b.version == 1

        # Reboot occurs: uptime drops to 15s -> version increments, status INVALIDATED
        rec, note = engine.ingest_sample(
            "R1", "device:R1", "cpu_load_percent", 35.0,
            timestamp=now + 40, uptime_seconds=15
        )
        assert note == "INVALIDATED_REBOOT"
        assert rec.version == 2
        assert rec.sample_count == 1
        assert rec.status == "INVALIDATED"

        # Monotonic counter reset protection (DISCONTINUOUS)
        # Establish anchor
        engine.ingest_sample(
            "R1", "iface:R1:ether1", "rx_bytes", 1000.0,
            timestamp=now, is_monotonic_counter=True
        )
        # Normal delta
        engine.ingest_sample(
            "R1", "iface:R1:ether1", "rx_bytes", 1500.0,
            timestamp=now + 10, is_monotonic_counter=True
        )
        # Counter resets to 200 without reboot -> SKIPPED_COUNTER_RESET_DISCONTINUOUS
        _, note_cnt = engine.ingest_sample(
            "R1", "iface:R1:ether1", "rx_bytes", 200.0,
            timestamp=now + 20, is_monotonic_counter=True
        )
        assert note_cnt == "SKIPPED_COUNTER_RESET_DISCONTINUOUS"

    def test_anomaly_benign_traffic_spike_guard_vs_fault_candidate(self) -> None:
        now = 1_700_000_000.0
        b_engine = BaselineEngine(min_samples=5)
        # Warm baseline for rx_utilization_percent around 20%
        for i in range(10):
            b_engine.ingest_sample(
                "R1", "iface:R1:ether1", "rx_utilization_percent", 20.0 + (i % 3),
                timestamp=now - 100 + i * 5
            )

        anom_engine = AnomalyEngine(baseline_engine=b_engine)
        svc = UnifiedEvidenceService()

        # Case A: Benign traffic spike to 55% (z > 3.5, but no errors, no packet loss, < 90%)
        # MUST have is_fault_candidate = False, severity = info
        bundle_benign = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "R1": {
                        "reachability_status": "UP",
                        "packet_loss_percent": 0.0,
                        "interfaces": [
                            {
                                "interface_name": "ether1",
                                "oper_status": "up",
                                "rx_utilization_percent": 55.0,
                                "in_errors": 0,
                                "in_drops": 0,
                            }
                        ],
                    }
                }
            },
            now=now,
        )
        anoms_benign = anom_engine.detect_anomalies(bundle_benign, now=now)
        util_anoms = [a for a in anoms_benign if a.metric_name == "rx_utilization_percent"]
        assert len(util_anoms) == 1
        assert util_anoms[0].is_fault_candidate is False
        assert util_anoms[0].severity == "info"

        # Case B: Traffic spike accompanied by packet loss or saturation >= 90%
        # MUST have is_fault_candidate = True, severity = warning / critical
        bundle_fault = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "R1": {
                        "reachability_status": "UP",
                        "packet_loss_percent": 8.0,
                        "interfaces": [
                            {
                                "interface_name": "ether1",
                                "oper_status": "up",
                                "rx_utilization_percent": 95.0,
                                "in_errors": 120,
                            }
                        ],
                    }
                }
            },
            now=now,
        )
        anoms_fault = anom_engine.detect_anomalies(bundle_fault, now=now)
        fault_cands = [a for a in anoms_fault if a.is_fault_candidate]
        assert len(fault_cands) >= 1

    def test_health_engine_8_dimensions_and_missing_data_integrity(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        health_engine = NetworkHealthEngine()

        # Healthy small network with WAN and OSPF
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "GW": {
                        "reachability_status": "UP",
                        "cpu_load_percent": 25.0,
                        "memory_used_percent": 40.0,
                        "latency_ms": 12.0,
                        "packet_loss_percent": 0.0,
                        "interfaces": [{"interface_name": "ether1", "oper_status": "up"}],
                        "routes": [{"dst_prefix": "0.0.0.0/0", "gateway": "203.0.113.1", "active": True}],
                        "ospf_neighbors": [{"neighbor_id": "10.0.0.2", "state": "Full"}],
                    },
                    "Core": {
                        "reachability_status": "UP",
                        "cpu_load_percent": 30.0,
                        "memory_used_percent": 50.0,
                        "interfaces": [{"interface_name": "ether1", "oper_status": "up"}],
                        "routes": [{"dst_prefix": "10.0.0.0/24", "gateway": "ether1", "connect": True, "active": True}],
                        "ospf_neighbors": [{"neighbor_id": "10.0.0.1", "state": "Full"}],
                    },
                },
                "topology_edges": [
                    {
                        "source_node_id": "GW",
                        "target_node_id": "Core",
                        "relationship_type": "PHYSICAL_ADJACENCY",
                        "layer": "physical",
                    }
                ],
            },
            now=now,
        )
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)
        rep = health_engine.evaluate_health(bundle, graph, now=now)

        assert rep["overall_status"] == HealthStatus.HEALTHY.value
        assert rep["overall_score"] is not None
        assert rep["overall_score"] >= 85.0

        dims = rep["dimensions"]
        assert set(dims.keys()) == {
            "overall",
            "device",
            "interface",
            "routing",
            "protocol",
            "wan",
            "dependency",
            "telemetry_confidence",
        }
        assert dims["device"]["status"] == HealthStatus.HEALTHY.value
        assert dims["protocol"]["status"] == HealthStatus.HEALTHY.value

        # When a dimension has no telemetry (e.g. protocol missing), score is None and status is INSUFFICIENT_DATA
        bundle_no_proto = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "R1": {
                        "reachability_status": "UP",
                        "cpu_load_percent": 20.0,
                        "interfaces": [{"interface_name": "ether1", "oper_status": "up"}],
                    }
                }
            },
            now=now,
        )
        graph_no_proto = NetworkKnowledgeGraph.from_evidence_bundle(bundle_no_proto, now=now)
        rep_np = health_engine.evaluate_health(bundle_no_proto, graph_no_proto, now=now)
        assert rep_np["dimensions"]["protocol"]["score"] is None
        assert rep_np["dimensions"]["protocol"]["status"] == HealthStatus.INSUFFICIENT_DATA.value
