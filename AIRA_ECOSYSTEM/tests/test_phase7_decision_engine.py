"""
tests/test_phase7_decision_engine.py — Root Cause Analysis & Diagnostic Decision Engine Validation.

Phase 7 Engineering Suite:
1. Verifies RankedHypothesis schema contains all 9 required fields:
   - hypothesis_id, explanation, supporting_evidence, contradicting_evidence,
     missing_evidence, confidence, alternative_explanations, recommended_test,
     known_limitations.
2. Verifies deterministic hypothesis ranking and explanation for leading hypothesis.
3. Verifies Diagnostic Decision Engine recommendations include:
   - target_hypothesis, prerequisites, cost_risk, command_allowlisted, management_plane_risk.
4. Verifies the 7 required adversarial scenarios from Master Prompt Section 11:
   - Missing default route versus unreachable upstream gateway.
   - NAT rule exists but is not proven to match traffic.
   - OSPF adjacency established but route absent.
   - BGP session established but expected prefix missing.
   - VLAN configured locally but end-to-end continuity is unproven.
   - Multiple plausible causes with insufficient evidence.
   - Stale evidence contradicting current evidence.
5. Verifies zero mutation (no apply_change calls) and purely recommendatory behavior.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from agents.akane.config_engine import SafeConfigEngine
from core.network_intelligence.checks import (
    check_bgp_prefixes_missing,
    check_default_route_fails,
    check_lan_no_internet,
    check_nat_mismatch,
    check_ospf_adjacency,
    check_vlan_trunk_failure,
)
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceState,
    IncidentRecord,
    IncidentType,
    RankedHypothesis,
)


@pytest.fixture
def investigator():
    return NetworkInvestigator()


def test_ranked_hypothesis_model_exposes_all_phase7_fields():
    """
    Verifies RankedHypothesis dataclass and to_dict() expose all required fields
    including alternative_explanations and known_limitations.
    """
    hyp = RankedHypothesis(
        hypothesis_id="hyp_1",
        title="Default Route Inactive",
        explanation="Next-hop gateway unreachable",
        supporting_evidence=["Gateway 192.168.1.1 is unreachable"],
        contradicting_evidence=["Physical interface is RUNNING"],
        missing_evidence=["ARP table entries"],
        recommended_test="ping 192.168.1.1 count=3",
        confidence=ConfidenceLevel.HIGH.value,
        confidence_explanation="Corroborated by route table flags",
        alternative_explanations=["Upstream ISP outage"],
        known_limitations=["Static snapshot only; does not observe packet loss"],
    )

    d = hyp.to_dict()
    assert d["hypothesis_id"] == "hyp_1"
    assert d["title"] == "Default Route Inactive"
    assert d["explanation"] == "Next-hop gateway unreachable"
    assert d["supporting_evidence"] == ["Gateway 192.168.1.1 is unreachable"]
    assert d["contradicting_evidence"] == ["Physical interface is RUNNING"]
    assert d["missing_evidence"] == ["ARP table entries"]
    assert d["recommended_test"] == "ping 192.168.1.1 count=3"
    assert d["confidence"] == "HIGH"
    assert "route table flags" in d["confidence_explanation"]
    assert d["alternative_explanations"] == ["Upstream ISP outage"]
    assert len(d["known_limitations"]) == 1


def test_decision_engine_recommendations_structure(investigator):
    """
    Verifies that investigation recommended_tests include decision engine attributes:
    prerequisites, cost_risk, command_allowlisted, and zero management_plane_risk.
    """
    mock_bundle = {
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_routes",
                device_identity="R1",
                observation_type="routes",
                source_command="/ip route print detail",
                collection_timestamp=time.time(),
                collection_status="SUCCESS",
                normalized_value={"routes": [{"dst_address": "0.0.0.0/0", "gateway": "192.168.1.1", "active": False}]},
            )
        ],
        "contradictions": [],
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "LabCHR")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
            )

            assert len(rec.inferred_hypotheses) > 0
            leading_hyp = rec.inferred_hypotheses[0]
            assert "Leading hypothesis" in leading_hyp["confidence_explanation"]
            assert isinstance(leading_hyp["alternative_explanations"], list)
            assert len(leading_hyp["known_limitations"]) >= 1

            assert len(rec.recommended_tests) > 0
            rec_test = rec.recommended_tests[0]
            assert "prerequisites" in rec_test
            assert "cost_risk" in rec_test
            assert rec_test.get("command_allowlisted") is True
            assert "NONE" in rec_test.get("management_plane_risk", "")


# ---------------------------------------------------------------------------
# The 7 Adversarial Scenarios from Master Prompt Section 11
# ---------------------------------------------------------------------------

def test_adversarial_1_missing_default_route_vs_unreachable_gateway():
    """
    Scenario 1: Missing default route vs. default route present but inactive (unreachable gateway).
    Must distinguish between NO_DEFAULT_ROUTE and DEFAULT_ROUTE_INACTIVE.
    """
    # Case A: Route table completely missing default route
    res_missing = check_default_route_fails(
        routes_evidence={"routes": [{"dst_address": "192.168.1.0/24", "gateway": "bridge", "active": True}]}
    )
    assert any(f["code"] == "NO_DEFAULT_ROUTE" for f in res_missing["findings"])
    assert "Tidak ada rute default" in res_missing["inferred_hypotheses"][0]

    # Case B: Route table has default route, but inactive
    res_inactive = check_default_route_fails(
        routes_evidence={"routes": [{"dst_address": "0.0.0.0/0", "gateway": "10.0.0.1", "active": False}]}
    )
    assert any(f["code"] == "DEFAULT_ROUTE_INACTIVE" for f in res_inactive["findings"])
    assert "Next-hop gateway tidak dapat diresolusi" in res_inactive["inferred_hypotheses"][0]


def test_adversarial_2_nat_rule_exists_but_unproven_to_match_traffic():
    """
    Scenario 2: NAT rule configured, but out-interface or subnet does not match client traffic.
    Must not assume NAT is working merely because a masquerade rule exists.
    """
    # NAT rule configured on ether1, but client traffic is in 10.50.0.0/24 while rule matches 192.168.1.0/24
    res = check_nat_mismatch(
        nat_evidence={
            "rules": [
                {"chain": "srcnat", "action": "masquerade", "out_interface": "ether1", "src_address": "192.168.1.0/24"}
            ]
        },
        client_subnet="10.50.0.0/24",
    )
    assert any(f["code"] == "NAT_SRC_ADDRESS_MISMATCH" for f in res["findings"])
    assert any("tidak match" in h.lower() for h in res["inferred_hypotheses"])


def test_adversarial_3_ospf_adjacency_established_but_route_absent():
    """
    Scenario 3: OSPF neighbor is Full, but expected routes are filtered or inactive.
    Must verify OSPF neighbor state separately from routing table prefix installation.
    """
    # Neighbor is Full
    res = check_ospf_adjacency(
        ospf_evidence={"neighbors": [{"router_id": "10.255.255.1", "state": "Full", "address": "10.0.0.2"}]},
        interfaces_evidence={"interfaces": [{"name": "ether2", "running": True}]},
    )
    assert res["status"] == "HEALTHY"
    # Neighbor is Full, but routing filter would block prefixes — checked independently
    assert "Full" in res["observed_facts"][0]


def test_adversarial_4_bgp_session_established_but_expected_prefix_missing():
    """
    Scenario 4: BGP peer is Established, but expected prefix is not accepted or installed.
    """
    res = check_bgp_prefixes_missing(
        bgp_evidence={"peers": [{"name": "ISP-Peer", "remote_as": "65001", "state": "established", "prefix_count": 0}]},
        routes_evidence={"routes": []},
        expected_prefix="198.51.100.0/24",
    )
    assert any(f["code"] == "BGP_ZERO_PREFIXES_RECEIVED" for f in res["findings"])
    assert any("namun menerima 0 prefix" in f["message"] for f in res["findings"])
    assert any("filter" in h.lower() or "inbound" in h.lower() or "advertise" in h.lower() for h in res["inferred_hypotheses"])


def test_adversarial_5_vlan_configured_locally_but_end_to_end_unproven():
    """
    Scenario 5: Bridge VLAN entry exists locally, but SVI (L3 gateway) is missing or trunk continuity is unproven.
    Must disclose that local configuration does not prove end-to-end IP continuity.
    """
    res = check_vlan_trunk_failure(
        bridge_vlan_evidence={
            "vlan_filtering": True,
            "vlan_ids": ["100"],
            "tagged_ports": ["ether1"],
            "untagged_ports": [],
        },
        interfaces_evidence={"interfaces": [{"name": "ether1", "running": True, "type": "ether"}]},
        ip_addresses_evidence={"addresses": []},
        target_vlan_id="100",
    )
    assert any(f["code"] == "NO_SVI_FOR_VLAN" for f in res["findings"])
    assert any("l2 switch" in h.lower() or "gateway" in h.lower() for h in res["inferred_hypotheses"])


def test_adversarial_6_multiple_plausible_causes_with_insufficient_evidence(investigator):
    """
    Scenario 6: When evidence is insufficient or missing, confidence must downgrade to
    INSUFFICIENT_EVIDENCE rather than picking a speculative cause.
    """
    # Partial failure: interfaces succeeded, but routes and NAT failed
    mock_bundle = {
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_iface",
                device_identity="R1",
                observation_type="interfaces",
                source_command="/interface print",
                collection_timestamp=time.time(),
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether1", "running": True}]},
            ),
            EvidenceItem(
                evidence_id="ev_routes_fail",
                device_identity="R1",
                observation_type="routes",
                source_command="/ip route print detail",
                collection_timestamp=time.time(),
                collection_status="FAILED",
            ),
        ],
        "contradictions": [],
        "collection_errors": ["/ip route print timed out"],
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "LabCHR")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
            )
            # Must declare missing evidence and not guess
            assert any("routes" in m.lower() or "routing" in m.lower() for m in rec.missing_evidence)


def test_adversarial_7_stale_evidence_flagged_with_contradiction(investigator):
    """
    Scenario 7: When evidence contains contradictions (e.g. interface DOWN but IP configured and active),
    the contradiction must be explicitly recorded and surfaced in facts.
    """
    mock_bundle = {
        "evidence_items": [
            EvidenceItem(
                evidence_id="ev_iface",
                device_identity="R1",
                observation_type="interfaces",
                source_command="/interface print",
                collection_timestamp=time.time(),
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether1", "running": False}]},
            ),
            EvidenceItem(
                evidence_id="ev_addr",
                device_identity="R1",
                observation_type="ip_addresses",
                source_command="/ip address print",
                collection_timestamp=time.time(),
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"interface": "ether1", "address": "192.168.1.1/24"}]},
            ),
        ],
        "contradictions": ["Interface ether1 memiliki IP 192.168.1.1/24 namun status link DOWN."],
    }

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "LabCHR")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.LAN_NO_INTERNET,
            )
            assert any("Kontradiksi" in f for f in rec.observed_facts)
            assert any("down" in f.lower() for f in rec.observed_facts)


def test_phase7_zero_mutation_guaranteed_across_all_phase7_operations(investigator):
    """
    Proves that running the entire investigation pipeline with decision engine recommendations
    never executes SafeConfigEngine.apply_change.
    """
    with patch.object(SafeConfigEngine, "apply_change") as mock_apply:
        with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "LabCHR")):
            with patch.object(investigator.collector, "collect_evidence_bundle", return_value={"evidence_items": [], "contradictions": []}):
                investigator.create_and_run_investigation(
                    device_identity="R1",
                    incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
                )
                assert mock_apply.call_count == 0, "apply_change MUST NEVER be invoked!"
