"""
tests/test_phase5_adversarial_evidence.py — Adversarial Evidence & Contradiction Test Suite (Phase 5).

Verifies robustness against:
- Empty, truncated, malformed, and failed CLI outputs.
- Command timeouts, SSH disconnects, and authentication failures.
- Ambiguous / unresolvable device targets.
- Cross-device and cross-timestamp mismatched evidence.
- Stale evidence conflicting with fresh observations.
- Contradictory domain states:
  * Interface DOWN but IP active.
  * Default route active but gateway unresolvable / ARP incomplete.
  * BGP Established but 0 prefixes.
  * OSPF Full but data-plane reachability failure.
  * Bridge VLAN configured but filtering disabled.
- Evidence states: OBSERVED, DERIVED, STALE, CONTRADICTORY, UNAVAILABLE, INVALID.
- INSUFFICIENT_EVIDENCE guarantees (never masquerading as HEALTHY).
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from core.network_intelligence.checks import (
    check_bgp_prefixes_missing,
    check_default_route_fails,
    check_firewall_forward_block,
    check_lan_no_internet,
    check_nat_mismatch,
    check_ospf_adjacency,
    check_vlan_trunk_failure,
)
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import (
    ConfidenceLevel,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceState,
    IncidentType,
    InvestigationStatus,
)


# ---------------------------------------------------------------------------
# 1. Adversarial CLI Output Handling (Empty, Truncated, Malformed)
# ---------------------------------------------------------------------------

def test_evidence_collector_handles_empty_and_truncated_cli():
    collector = EvidenceCollector()

    with patch.object(collector.cm, "execute_for_device") as mock_exec:
        # Simulate truncated and empty responses
        mock_exec.side_effect = [
            {"success": True, "output": ""},  # empty
            {"success": True, "output": "/ip route print detail\n[truncated] ... syntax error"},  # truncated
        ]

        bundle = collector.collect_evidence_bundle("R1-Core", ["ip_addresses", "routes"])
        items = bundle["evidence_items"]

        assert len(items) == 2
        # Empty output must be classified as INVALID, not OBSERVED/HEALTHY
        assert items[0].state == EvidenceState.INVALID.value
        assert items[0].collection_status == "PARTIAL"

        # Truncated output must be classified as INVALID
        assert items[1].state == EvidenceState.INVALID.value
        assert items[1].collection_status == "PARTIAL"
        assert "terpotong" in items[1].limitations or "kosong" in items[1].limitations


def test_evidence_collector_handles_timeout_and_ssh_disconnect():
    collector = EvidenceCollector()

    with patch.object(collector.cm, "execute_for_device") as mock_exec:
        # Simulate timeout and SSH connection drop
        mock_exec.side_effect = [
            {"success": False, "error": "SSH connection timed out after 10.0s"},
            Exception("Remote SSH transport closed abruptly by peer"),
        ]

        bundle = collector.collect_evidence_bundle("R1-Core", ["routes", "nat_rules"])
        items = bundle["evidence_items"]

        assert len(items) == 2
        # Timeout must be UNAVAILABLE
        assert items[0].state == EvidenceState.UNAVAILABLE.value
        assert items[0].collection_status == "FAILED"
        assert "timed out" in items[0].limitations

        # Exception / Disconnect must be UNAVAILABLE
        assert items[1].state == EvidenceState.UNAVAILABLE.value
        assert items[1].collection_status == "FAILED"
        assert "abruptly" in items[1].limitations


# ---------------------------------------------------------------------------
# 2. Ambiguous & Unresolvable Target Device
# ---------------------------------------------------------------------------

def test_investigation_blocked_when_target_unresolvable():
    investigator = NetworkInvestigator()

    with patch.object(investigator.collector, "resolve_target_device", return_value=(None, None, None)):
        record = investigator.create_and_run_investigation(
            device_identity="non-existent-device-999",
            incident_type=IncidentType.LAN_NO_INTERNET,
            symptoms=["Client 192.168.1.50 cannot reach gateway"],
        )

        assert record.investigation_status == InvestigationStatus.BLOCKED.value
        assert record.confidence == ConfidenceLevel.INSUFFICIENT_EVIDENCE.value
        assert len(record.inferred_hypotheses) == 0
        assert any("tidak dapat diresolusi" in m for m in record.missing_evidence)


# ---------------------------------------------------------------------------
# 3. Cross-Device and Stale Evidence Contradiction
# ---------------------------------------------------------------------------

def test_detect_contradiction_cross_device_mismatch():
    collector = EvidenceCollector()

    t_now = time.time()
    items = [
        EvidenceItem(
            evidence_id="ev_1",
            device_identity="Router-HQ-A",
            observation_type="routes",
            source_command="/ip route print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={"routes": [{"dst_address": "0.0.0.0/0", "active": True}]},
        ),
        EvidenceItem(
            evidence_id="ev_2",
            device_identity="Router-Branch-B",  # Mismatch device
            observation_type="interfaces",
            source_command="/interface print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={"interfaces": [{"name": "ether1", "running": True}]},
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert any("perangkat yang berbeda" in c for c in contradictions)
    assert items[0].state == EvidenceState.CONTRADICTORY.value
    assert items[1].state == EvidenceState.CONTRADICTORY.value


def test_detect_contradiction_stale_evidence():
    collector = EvidenceCollector()

    t_now = time.time()
    t_stale = t_now - 450.0  # 7.5 minutes ago

    items = [
        EvidenceItem(
            evidence_id="ev_stale",
            device_identity="Router-HQ-A",
            observation_type="routes",
            source_command="/ip route print detail",
            collection_timestamp=t_stale,
            collection_status="SUCCESS",
            normalized_value={"routes": []},
        ),
        EvidenceItem(
            evidence_id="ev_fresh",
            device_identity="Router-HQ-A",
            observation_type="interfaces",
            source_command="/interface print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={"interfaces": [{"name": "ether1", "running": True}]},
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert any("rentang waktu observasi" in c for c in contradictions)
    assert items[0].state == EvidenceState.STALE.value


# ---------------------------------------------------------------------------
# 4. Domain Contradictions
# ---------------------------------------------------------------------------

def test_contradiction_interface_down_with_ip_assigned():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_ip",
            device_identity="R1",
            observation_type="ip_addresses",
            source_command="/ip address print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "addresses": [{"address": "192.168.10.1/24", "interface": "ether2", "disabled": False}]
            },
        ),
        EvidenceItem(
            evidence_id="ev_if",
            device_identity="R1",
            observation_type="interfaces",
            source_command="/interface print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "interfaces": [{"name": "ether2", "running": False, "disabled": False}]  # DOWN!
            },
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert len(contradictions) == 1
    assert "DOWN (running=no)" in contradictions[0]
    assert items[0].state == EvidenceState.CONTRADICTORY.value
    assert items[1].state == EvidenceState.CONTRADICTORY.value


def test_contradiction_default_route_gateway_unresolvable_arp():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_route",
            device_identity="R1",
            observation_type="routes",
            source_command="/ip route print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "routes": [{"dst_address": "0.0.0.0/0", "gateway": "192.168.1.1", "active": True}]
            },
        ),
        EvidenceItem(
            evidence_id="ev_arp",
            device_identity="R1",
            observation_type="arp",
            source_command="/ip arp print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "entries": [{"ip": "192.168.1.1", "complete": False, "mac": ""}]  # Incomplete ARP!
            },
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert len(contradictions) == 1
    assert "INCOMPLETE" in contradictions[0]
    assert items[0].state == EvidenceState.CONTRADICTORY.value
    assert items[1].state == EvidenceState.CONTRADICTORY.value


def test_contradiction_default_route_next_hop_not_in_connected_subnet():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_route",
            device_identity="R1",
            observation_type="routes",
            source_command="/ip route print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "routes": [{"dst_address": "0.0.0.0/0", "gateway": "10.50.0.1", "active": True}]
            },
        ),
        EvidenceItem(
            evidence_id="ev_ip",
            device_identity="R1",
            observation_type="ip_addresses",
            source_command="/ip address print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "addresses": [{"address": "192.168.1.1/24", "interface": "ether1"}]  # 10.50.0.1 not in subnet!
            },
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert any("tidak berada dalam subnet lokal" in c for c in contradictions)


def test_contradiction_bgp_established_zero_prefixes():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_bgp",
            device_identity="R1",
            observation_type="bgp_peers",
            source_command="/routing bgp peer print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "peers": [
                    {
                        "name": "peer-isp",
                        "remote_ip": "203.0.113.1",
                        "state": "established",
                        "is_established": True,
                        "prefix_count": 0,  # Zero prefixes!
                    }
                ]
            },
        )
    ]

    contradictions = collector.detect_contradictions(items)
    assert len(contradictions) == 1
    assert "ESTABLISHED" in contradictions[0] and "0" in contradictions[0]
    assert items[0].state == EvidenceState.CONTRADICTORY.value


def test_contradiction_ospf_full_with_interface_down():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_ospf",
            device_identity="R1",
            observation_type="ospf_neighbors",
            source_command="/routing ospf neighbor print",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "neighbors": [
                    {
                        "router_id": "10.255.255.2",
                        "address": "10.0.0.2",
                        "interface": "ether3",
                        "state": "Full",
                        "is_full": True,
                    }
                ]
            },
        ),
        EvidenceItem(
            evidence_id="ev_if",
            device_identity="R1",
            observation_type="interfaces",
            source_command="/interface print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "interfaces": [{"name": "ether3", "running": False}]  # DOWN!
            },
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert any("tercatat FULL, namun interface lokal 'ether3' berstatus DOWN" in c for c in contradictions)
    assert items[0].state == EvidenceState.CONTRADICTORY.value


def test_contradiction_bridge_vlan_ids_with_filtering_disabled():
    collector = EvidenceCollector()
    t_now = time.time()

    items = [
        EvidenceItem(
            evidence_id="ev_vlan",
            device_identity="R1",
            observation_type="bridge_vlan",
            source_command="/interface bridge vlan print detail",
            collection_timestamp=t_now,
            collection_status="SUCCESS",
            normalized_value={
                "vlan_filtering": False,  # Disabled!
                "vlan_ids": ["10", "20", "30"],
            },
        )
    ]

    contradictions = collector.detect_contradictions(items)
    assert len(contradictions) == 1
    assert "vlan-filtering=no" in contradictions[0]
    assert items[0].state == EvidenceState.CONTRADICTORY.value


# ---------------------------------------------------------------------------
# 5. Insufficient Evidence Guarantee (Never Masking as Healthy)
# ---------------------------------------------------------------------------

def test_checks_return_insufficient_evidence_when_input_empty():
    # LAN check
    lan_res = check_lan_no_internet(
        routes_evidence=None,
        ip_addresses_evidence=None,
        nat_evidence=None,
        firewall_evidence=None,
    )
    assert lan_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert lan_res["status"] != "HEALTHY"

    # Default route check
    route_res = check_default_route_fails(routes_evidence={})
    assert route_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert route_res["status"] != "HEALTHY"

    # NAT check
    nat_res = check_nat_mismatch(nat_evidence={})
    assert nat_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert nat_res["status"] != "HEALTHY"

    # Firewall check
    fw_res = check_firewall_forward_block(firewall_evidence={})
    assert fw_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert fw_res["status"] != "HEALTHY"

    # OSPF check
    ospf_res = check_ospf_adjacency(ospf_evidence={})
    assert ospf_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert ospf_res["status"] != "HEALTHY"

    # BGP check
    bgp_res = check_bgp_prefixes_missing(bgp_evidence={})
    assert bgp_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert bgp_res["status"] != "HEALTHY"

    # VLAN check
    vlan_res = check_vlan_trunk_failure(bridge_vlan_evidence={})
    assert vlan_res["status"] == "INSUFFICIENT_EVIDENCE"
    assert vlan_res["status"] != "HEALTHY"


def test_investigation_emits_insufficient_evidence_when_all_collections_fail():
    investigator = NetworkInvestigator()

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1-Core", 7, "R1 Core Router")):
        with patch.object(investigator.collector.cm, "execute_for_device") as mock_exec:
            mock_exec.return_value = {"success": False, "error": "SSH authentication failed for admin@192.168.1.1"}

            record = investigator.create_and_run_investigation(
                device_identity="R1-Core",
                incident_type=IncidentType.LAN_NO_INTERNET,
                symptoms=["No internet"],
            )

            assert record.confidence == ConfidenceLevel.INSUFFICIENT_EVIDENCE.value
            assert record.investigation_status == InvestigationStatus.BLOCKED.value
            # Must not have speculative hypotheses
            assert len(record.inferred_hypotheses) == 0
            assert any("gagal" in fact for fact in record.observed_facts)
