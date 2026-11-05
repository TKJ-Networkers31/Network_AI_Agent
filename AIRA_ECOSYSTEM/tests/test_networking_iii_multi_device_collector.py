"""
tests/test_networking_iii_multi_device_collector.py — Unit tests for Phase Networking III Multi-Device Evidence Collection.
"""

import pytest
from core.network_intelligence.models import EvidenceItem
from core.network_intelligence.multi_device_collector import (
    DeviceCollectionSummary,
    MultiDeviceCollectionSummary,
    MultiDeviceEvidenceBundle,
    MultiDeviceEvidenceOrchestrator,
)


def test_empty_targets_bundle():
    orchestrator = MultiDeviceEvidenceOrchestrator()
    bundle = orchestrator.collect_multi_device_bundle(targets=[])
    assert bundle.summary.total_devices == 0
    assert bundle.summary.successful_devices == 0
    assert len(bundle.device_bundles) == 0


def test_cross_device_ip_collision_detection():
    orchestrator = MultiDeviceEvidenceOrchestrator()

    # Synthetic bundles with IP collision
    b1 = {
        "target": "R1",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_ip_1",
                device_identity="R1",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.10.1/24", "interface": "ether1"}]},
            )
        ],
    }

    b2 = {
        "target": "R2",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_ip_2",
                device_identity="R2",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.10.1/24", "interface": "ether2"}]},
            )
        ],
    }

    contradictions = orchestrator._detect_cross_device_contradictions({"R1": b1, "R2": b2})
    assert len(contradictions) == 1
    assert "Cross-device IP collision" in contradictions[0]
    assert "192.168.10.1" in contradictions[0]


def test_partial_failure_preservation_with_missing_device():
    orchestrator = MultiDeviceEvidenceOrchestrator()
    targets = ["non_existent_router_1", "non_existent_router_2"]
    bundle = orchestrator.collect_multi_device_bundle(targets=targets, required_types=["identity"])

    # Both fail gracefully without crashing
    assert bundle.summary.total_devices == 2
    assert bundle.summary.failed_devices == 2
    assert "non_existent_router_1" in bundle.device_bundles
    assert "non_existent_router_2" in bundle.device_bundles
    assert len(bundle.summary.device_summaries["non_existent_router_1"].error_details) > 0
