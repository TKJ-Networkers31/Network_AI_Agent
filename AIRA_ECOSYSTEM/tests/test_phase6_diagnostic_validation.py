"""
tests/test_phase6_diagnostic_validation.py — End-to-End Diagnostic Verification on 7 Domains.

Phase 6: Verifies deterministic investigation and hypothesis ranking across:
1. LAN client no internet access (missing NAT masquerade)
2. Default route next-hop unreachable
3. NAT mismatch (wrong out-interface)
4. Firewall forward blocked
5. OSPF adjacency stuck in Init / ExStart
6. BGP Established but 0 prefixes received
7. VLAN trunk tagging inconsistency
Also verifies strict INSUFFICIENT_EVIDENCE guarantees when evidence is absent,
and correlation ID tracing across investigations.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from core.canonical_network import CanonicalDevice
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import (
    ConfidenceLevel,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceState,
    IncidentRecord,
    IncidentType,
    InvestigationStatus,
    SeverityLevel,
)


@pytest.fixture
def investigator():
    return NetworkInvestigator()


def mock_bundle(obs_dict: dict, dev_name="R1", ros_major=7):
    """Helper to mock collector.collect_evidence_bundle with structured EvidenceItems."""
    items = []
    for obs_type, norm_val in obs_dict.items():
        items.append(EvidenceItem(
            evidence_id=f"ev_{obs_type}",
            device_identity=dev_name,
            observation_type=obs_type,
            source_command=f"/{obs_type} print",
            collection_timestamp=time.time(),
            collection_status="SUCCESS",
            normalized_value=norm_val,
            raw_excerpt=f"Observed {obs_type}",
            freshness=EvidenceFreshness.FRESH.value,
            state=EvidenceState.OBSERVED.value,
        ))
    return {
        "target": dev_name,
        "ros_major_version": ros_major,
        "display_name": dev_name,
        "evidence_items": items,
        "contradictions": [],
        "collection_errors": [],
    }


# ---------------------------------------------------------------------------
# Domain 1: LAN Client Cannot Access the Internet
# ---------------------------------------------------------------------------

def test_domain1_lan_no_internet_missing_nat(investigator):
    """
    Ground truth: LAN subnet 192.168.10.0/24 has IP on ether2, default route on ether1,
    firewall accepts forward, but NAT table has NO masquerade rule.
    Expected: Root cause hypothesis flags missing NAT masquerade rule.
    """
    obs = {
        "ip_addresses": {
            "addresses": [
                {"address": "192.168.10.1/24", "network": "192.168.10.0", "interface": "ether2"},
                {"address": "100.64.1.2/30", "network": "100.64.1.0", "interface": "ether1"},
            ]
        },
        "routes": {
            "routes": [
                {"dst": "0.0.0.0/0", "gateway": "100.64.1.1", "interface": "ether1", "active": True},
                {"dst": "192.168.10.0/24", "gateway": "", "interface": "ether2", "active": True},
            ]
        },
        "interfaces": {
            "interfaces": [
                {"name": "ether1", "running": True, "disabled": False},
                {"name": "ether2", "running": True, "disabled": False},
            ]
        },
        "nat_rules": {"rules": []},  # No NAT rule
        "firewall_filter": {"rules": [{"chain": "forward", "action": "accept"}]},
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.LAN_NO_INTERNET,
                target_ip="192.168.10.55",
                correlation_id="corr_test_domain1",
            )

            assert rec.incident_type == IncidentType.LAN_NO_INTERNET.value
            assert rec.correlation_id == "corr_test_domain1"
            assert rec.confidence in (ConfidenceLevel.HIGH.value, ConfidenceLevel.MEDIUM.value)
            # Verify hypothesis identifies NAT masquerade
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert "nat" in hyp_titles or "masquerade" in hyp_titles


# ---------------------------------------------------------------------------
# Domain 2: Default Route Next-Hop Issue
# ---------------------------------------------------------------------------

def test_domain2_default_route_fails_unreachable_gateway(investigator):
    """
    Ground truth: Default route exists to 10.254.1.1, but no router interface has an IP in 10.254.1.0/24.
    Expected: Root cause hypothesis flags unreachable next-hop gateway.
    """
    obs = {
        "routes": {
            "routes": [
                {"dst": "0.0.0.0/0", "gateway": "10.254.1.1", "interface": "unknown", "active": False},
                {"dst": "192.168.88.0/24", "gateway": "", "interface": "ether1", "active": True},
            ]
        },
        "ip_addresses": {
            "addresses": [
                {"address": "192.168.88.1/24", "network": "192.168.88.0", "interface": "ether1"},
            ]
        },
        "interfaces": {
            "interfaces": [
                {"name": "ether1", "running": True, "disabled": False},
            ]
        },
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
                target_ip="8.8.8.8",
                correlation_id="corr_test_domain2",
            )

            assert rec.incident_type == IncidentType.DEFAULT_ROUTE_FAILS.value
            assert rec.confidence == ConfidenceLevel.HIGH.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert any(w in hyp_titles for w in ["gateway", "next-hop", "route", "rute", "inaktif"])


# ---------------------------------------------------------------------------
# Domain 3: NAT Mismatch (Wrong Out-Interface)
# ---------------------------------------------------------------------------

def test_domain3_nat_mismatch_wrong_interface(investigator):
    """
    Ground truth: WAN route leaves via ether1, but NAT masquerade specifies out-interface=ether2.
    Expected: Identifies NAT out-interface mismatch with actual WAN routing egress.
    """
    obs = {
        "nat_rules": {
            "rules": [
                {"chain": "srcnat", "action": "masquerade", "out_interface": "ether2", "disabled": False},
            ]
        },
        "routes": {
            "routes": [
                {"dst": "0.0.0.0/0", "gateway": "10.0.0.1", "interface": "ether1", "active": True},
            ]
        },
        "interfaces": {
            "interfaces": [
                {"name": "ether1", "running": True},
                {"name": "ether2", "running": True},
            ]
        },
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.NAT_MISMATCH,
                correlation_id="corr_test_domain3",
            )

            assert rec.incident_type == IncidentType.NAT_MISMATCH.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert any(w in hyp_titles for w in ["out-interface", "mismatch", "wan", "nat", "interface", "paket"])


# ---------------------------------------------------------------------------
# Domain 4: Firewall Forward Blocked
# ---------------------------------------------------------------------------

def test_domain4_firewall_forward_blocked(investigator):
    """
    Ground truth: Firewall forward chain has rule 0: action=drop (blanket drop) before accept established.
    Expected: Flags firewall forward chain dropping traffic.
    """
    obs = {
        "firewall_filter": {
            "rules": [
                {"chain": "forward", "action": "drop", "comment": "Drop all forward", "disabled": False},
            ]
        }
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.FIREWALL_FORWARD_BLOCKED,
                target_ip="192.168.1.100",
                correlation_id="corr_test_domain4",
            )

            assert rec.incident_type == IncidentType.FIREWALL_FORWARD_BLOCKED.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert "firewall" in hyp_titles or "drop" in hyp_titles or "forward" in hyp_titles


# ---------------------------------------------------------------------------
# Domain 5: OSPF Adjacency Failure
# ---------------------------------------------------------------------------

def test_domain5_ospf_adjacency_stuck_init(investigator):
    """
    Ground truth: OSPF neighbor state is stuck in 'Init' (one-way hello) or 'ExStart'.
    Expected: Flags OSPF 2-way / MTU / timer mismatch.
    """
    obs = {
        "ospf_neighbors": {
            "neighbors": [
                {"router_id": "10.255.255.2", "address": "10.0.0.2", "interface": "ether1", "state": "Init"},
            ]
        },
        "interfaces": {
            "interfaces": [{"name": "ether1", "running": True}],
        },
        "firewall_filter": {"rules": []},
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.OSPF_ADJACENCY_FAILURE,
                correlation_id="corr_test_domain5",
            )

            assert rec.incident_type == IncidentType.OSPF_ADJACENCY_FAILURE.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert any(w in hyp_titles for w in ["ospf", "init", "state", "hello", "peer"])


# ---------------------------------------------------------------------------
# Domain 6: BGP Established but Missing Prefixes
# ---------------------------------------------------------------------------

def test_domain6_bgp_established_missing_prefixes(investigator):
    """
    Ground truth: BGP session is Established with AS65001, but prefix count is 0.
    Expected: Flags missing prefix announcements or inbound routing filter drop.
    """
    obs = {
        "bgp_peers": {
            "peers": [
                {
                    "name": "upstream-isp",
                    "remote_address": "198.51.100.1",
                    "remote_as": "65001",
                    "state": "Established",
                    "prefix_count": 0,
                    "established": True,
                }
            ]
        },
        "routes": {
            "routes": [{"dst": "192.168.0.0/24", "gateway": "", "interface": "ether1", "active": True}],
        },
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.BGP_PREFIXES_MISSING,
                target_ip="0.0.0.0/0",
                correlation_id="corr_test_domain6",
            )

            assert rec.incident_type == IncidentType.BGP_PREFIXES_MISSING.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert "bgp" in hyp_titles or "prefix" in hyp_titles or "filter" in hyp_titles


# ---------------------------------------------------------------------------
# Domain 7: VLAN Trunk Inconsistency
# ---------------------------------------------------------------------------

def test_domain7_vlan_trunk_inconsistency(investigator):
    """
    Ground truth: Bridge VLAN 100 exists with untagged ether2, but trunk ether1 is missing from tagged list.
    Expected: Flags VLAN tagging inconsistency on bridge trunk.
    """
    obs = {
        "bridge_vlan": {
            "vlans": [
                {"vlan_ids": [100], "tagged": [], "untagged": ["ether2"], "current_tagged": [], "current_untagged": ["ether2"]},
            ]
        },
        "bridge_ports": {
            "ports": [
                {"interface": "ether1", "bridge": "bridge1", "pvid": 1},
                {"interface": "ether2", "bridge": "bridge1", "pvid": 100},
            ]
        },
        "bridge": {
            "bridges": [{"name": "bridge1", "vlan_filtering": True}],
        },
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle(obs)):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.VLAN_TRUNK_FAILURE,
                target_vlan_id="100",
                correlation_id="corr_test_domain7",
            )

            assert rec.incident_type == IncidentType.VLAN_TRUNK_FAILURE.value
            hyp_titles = " ".join([h["title"].lower() for h in rec.inferred_hypotheses])
            assert "vlan" in hyp_titles or "tag" in hyp_titles or "trunk" in hyp_titles


# ---------------------------------------------------------------------------
# Strict INSUFFICIENT_EVIDENCE Guarantee
# ---------------------------------------------------------------------------

def test_insufficient_evidence_when_all_commands_fail(investigator):
    """
    When collector returns failed/empty items for all required commands,
    AIRA MUST return INSUFFICIENT_EVIDENCE and NEVER claim HEALTHY.
    """
    failed_items = [
        EvidenceItem(
            evidence_id="ev_fail_1",
            device_identity="R1",
            observation_type="routes",
            source_command="/ip route print",
            collection_timestamp=time.time(),
            collection_status="FAILED",
            normalized_value=None,
            state=EvidenceState.UNAVAILABLE.value,
        )
    ]
    bundle = {
        "target": "R1",
        "ros_major_version": 7,
        "display_name": "R1",
        "evidence_items": failed_items,
        "contradictions": [],
        "collection_errors": ["Connection timeout"],
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=bundle):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
                correlation_id="corr_test_insufficient",
            )

            assert rec.confidence == ConfidenceLevel.INSUFFICIENT_EVIDENCE.value
            assert rec.investigation_status in (InvestigationStatus.EVIDENCE_PARTIAL.value, InvestigationStatus.BLOCKED.value)
            assert len(rec.missing_evidence) > 0
            assert rec.correlation_id == "corr_test_insufficient"
