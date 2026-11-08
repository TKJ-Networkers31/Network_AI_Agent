"""
tests/test_networking_iii_correlation.py — Unit tests for Phase Networking III Cross-Device Evidence Correlation.
"""

import pytest
from core.network_intelligence.correlation import (
    CorrelatedRelationship,
    CrossDeviceEvidenceCorrelator,
)
from core.network_intelligence.models import EvidenceItem
from core.network_intelligence.network_models import CorrelationConfidence, LinkType


def test_correlate_mutual_arp_and_subnet():
    correlator = CrossDeviceEvidenceCorrelator()

    bundle_r1 = {
        "target": "R1",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev1",
                device_identity="R1",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "10.0.0.1/30", "interface": "ether2"}]},
            ),
            EvidenceItem(
                evidence_id="ev2",
                device_identity="R1",
                observation_type="interfaces",
                source_command="/interface print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether2", "mac_address": "00:11:22:33:44:01", "running": True}]},
            ),
            EvidenceItem(
                evidence_id="ev3",
                device_identity="R1",
                observation_type="arp",
                source_command="/ip arp print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"entries": [{"address": "10.0.0.2", "mac_address": "00:11:22:33:44:02", "interface": "ether2"}]},
            ),
        ],
    }

    bundle_r2 = {
        "target": "R2",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev4",
                device_identity="R2",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "10.0.0.2/30", "interface": "ether1"}]},
            ),
            EvidenceItem(
                evidence_id="ev5",
                device_identity="R2",
                observation_type="interfaces",
                source_command="/interface print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether1", "mac_address": "00:11:22:33:44:02", "running": True}]},
            ),
        ],
    }

    rels = correlator.correlate_bundles({"R1": bundle_r1, "R2": bundle_r2})
    assert len(rels) >= 1
    rel = rels[0]
    assert rel.correlation_rule == "MUTUAL_ARP_AND_SUBNET_MATCH"
    assert rel.confidence == CorrelationConfidence.HIGH.value
    assert rel.relationship_type == LinkType.LAYER2_ADJACENCY.value
    assert rel.source_port == "ether2"
    assert rel.target_port == "ether1"
    assert len(rel.alternative_interpretations) > 0


def test_correlate_subnet_only_is_medium_confidence():
    correlator = CrossDeviceEvidenceCorrelator()

    bundle_a = {
        "target": "DevA",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_a",
                device_identity="DevA",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.100.1/24", "interface": "bridge-lan"}]},
            )
        ],
    }

    bundle_b = {
        "target": "DevB",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_b",
                device_identity="DevB",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.100.50/24", "interface": "eth0"}]},
            )
        ],
    }

    rels = correlator.correlate_bundles({"DevA": bundle_a, "DevB": bundle_b})
    assert len(rels) == 1
    rel = rels[0]
    assert rel.correlation_rule == "SUBNET_OVERLAP_ONLY"
    assert rel.confidence == CorrelationConfidence.MEDIUM.value
    assert rel.relationship_type == LinkType.INFERRED.value


def test_correlate_routed_nexthop():
    correlator = CrossDeviceEvidenceCorrelator()

    bundle_r1 = {
        "target": "Branch-R1",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_r1",
                device_identity="Branch-R1",
                observation_type="routes",
                source_command="/ip route print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"routes": [{"dst_address": "0.0.0.0/0", "gateway": "172.16.1.1", "interface": "wan1"}]},
            )
        ],
    }

    bundle_core = {
        "target": "Core-R1",
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_core",
                device_identity="Core-R1",
                observation_type="ip_addresses",
                source_command="/ip address print detail",
                collection_timestamp=100.0,
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "172.16.1.1/24", "interface": "vlan10"}]},
            )
        ],
    }

    rels = correlator.correlate_bundles({"Branch-R1": bundle_r1, "Core-R1": bundle_core})
    assert len(rels) == 1
    rel = rels[0]
    assert rel.correlation_rule == "ROUTED_NEXT_HOP"
    assert rel.relationship_type == LinkType.ROUTED.value
    assert rel.confidence == CorrelationConfidence.HIGH.value
    assert rel.target_port == "vlan10"
