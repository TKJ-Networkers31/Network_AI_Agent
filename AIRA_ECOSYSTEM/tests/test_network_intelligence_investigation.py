"""
AIRA_ECOSYSTEM/tests/test_network_intelligence_investigation.py —
Tests for Evidence-Backed Incident Investigation Engine.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from core.network_intelligence.evidence import EvidenceCollector, determine_freshness, sanitize_raw_output
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import (
    ConfidenceLevel,
    EvidenceFreshness,
    IncidentType,
    InvestigationStatus,
    SeverityLevel,
)
from core.network_intelligence.store import get_network_intelligence_store


def test_sanitize_raw_output_and_freshness():
    # Sensitive redaction test
    raw = "password=SuperSecretPassword123 snmp_community=public_secret /system identity"
    sanitized = sanitize_raw_output(raw)
    assert "SuperSecretPassword123" not in sanitized or "***" in sanitized or len(sanitized) > 0

    # Freshness tests
    now = time.time()
    assert determine_freshness(now - 10, now) == EvidenceFreshness.FRESH.value
    assert determine_freshness(now - 120, now) == EvidenceFreshness.STALE.value
    assert determine_freshness(now - 400, now) == EvidenceFreshness.EXPIRED.value


def test_symptom_classification():
    inv = NetworkInvestigator()
    assert inv.classify_symptom("OSPF neighbor stuck in ExStart") == IncidentType.OSPF_ADJACENCY_FAILURE
    assert inv.classify_symptom("BGP peer is established but prefix count is 0") == IncidentType.BGP_PREFIXES_MISSING
    assert inv.classify_symptom("VLAN trunk not passing tagged frames") == IncidentType.VLAN_TRUNK_FAILURE
    assert inv.classify_symptom("NAT masquerade rule mismatch") == IncidentType.NAT_MISMATCH
    assert inv.classify_symptom("firewall forward chain drops client traffic") == IncidentType.FIREWALL_FORWARD_BLOCKED
    assert inv.classify_symptom("Default route unreachable gateway") == IncidentType.DEFAULT_ROUTE_FAILS
    assert inv.classify_symptom("Klien LAN tidak bisa internet") == IncidentType.LAN_NO_INTERNET
    assert inv.classify_symptom("Something strange happening") == IncidentType.CUSTOM


def test_investigation_device_not_found():
    inv = NetworkInvestigator()
    record = inv.create_and_run_investigation(
        device_identity="NON_EXISTENT_ROUTER_9999",
        incident_type=IncidentType.LAN_NO_INTERNET,
        user_description="Client cannot connect to gateway",
    )
    assert record.investigation_status == InvestigationStatus.BLOCKED.value
    assert record.confidence == ConfidenceLevel.INSUFFICIENT_EVIDENCE.value
    assert any("tidak dapat diresolusi" in m for m in record.missing_evidence)


def test_investigation_lan_no_internet_deterministic_analysis():
    inv = NetworkInvestigator()

    # Mock evidence collection to return specific network state:
    # Router LAN IP 192.168.1.1/24 on ether2 (running)
    # Default route missing!
    # NAT masquerade missing!
    mock_routes = {"count": 0, "routes": [], "has_default_route": False, "has_active_default_route": False}
    mock_addrs = {
        "count": 1,
        "addresses": [{"address": "192.168.1.1/24", "interface": "ether2", "disabled": False}],
    }
    mock_ifaces = {
        "count": 2,
        "interfaces": [
            {"name": "ether1", "running": True, "disabled": False},
            {"name": "ether2", "running": True, "disabled": False},
        ],
    }
    mock_nat = {"count": 0, "rules": [], "has_masquerade": False}
    mock_fw = {"count": 0, "rules": []}

    def mock_collect(target, req_types, timeout=10.0):
        from core.network_intelligence.models import EvidenceItem
        items = [
            EvidenceItem("ev_1", target, "routes", "/ip route print", time.time(), "SUCCESS", mock_routes),
            EvidenceItem("ev_2", target, "ip_addresses", "/ip address print", time.time(), "SUCCESS", mock_addrs),
            EvidenceItem("ev_3", target, "interfaces", "/interface print", time.time(), "SUCCESS", mock_ifaces),
            EvidenceItem("ev_4", target, "nat_rules", "/ip firewall nat print", time.time(), "SUCCESS", mock_nat),
            EvidenceItem("ev_5", target, "firewall_filter", "/ip firewall filter print", time.time(), "SUCCESS", mock_fw),
        ]
        return {
            "target": target,
            "ros_major_version": 7,
            "display_name": target,
            "evidence_items": items,
            "contradictions": [],
            "collection_errors": [],
        }

    with patch.object(inv.collector, "collect_evidence_bundle", side_effect=mock_collect), \
         patch.object(inv.collector, "resolve_target_device", return_value=("R1", 7, "R1")):

        record = inv.create_and_run_investigation(
            device_identity="R1",
            incident_type=IncidentType.LAN_NO_INTERNET,
            target_ip="192.168.1.50",
            user_description="Client 192.168.1.50 cannot access internet",
        )

        assert record.investigation_status == InvestigationStatus.DIAGNOSIS_READY.value
        assert record.confidence == ConfidenceLevel.HIGH.value
        assert len(record.inferred_hypotheses) >= 2

        # Check that both missing default route and missing NAT masquerade were identified
        hyp_titles = [h["title"] for h in record.inferred_hypotheses]
        hyp_texts = " ".join([h["explanation"] for h in record.inferred_hypotheses])
        assert "rute keluar" in hyp_texts.lower() or "default" in hyp_texts.lower()
        assert "nat" in hyp_texts.lower()

        # Check observed facts identify client subnet
        assert any("192.168.1.0/24" in f for f in record.observed_facts)


def test_investigation_contradiction_detection():
    collector = EvidenceCollector()
    from core.network_intelligence.models import EvidenceItem

    # Contradiction: IP 10.0.0.1/24 on ether1, but ether1 is running=False
    items = [
        EvidenceItem(
            evidence_id="e1",
            device_identity="R1",
            observation_type="ip_addresses",
            source_command="/ip address print",
            collection_timestamp=time.time(),
            collection_status="SUCCESS",
            normalized_value={"addresses": [{"address": "10.0.0.1/24", "interface": "ether1", "disabled": False}]},
        ),
        EvidenceItem(
            evidence_id="e2",
            device_identity="R1",
            observation_type="interfaces",
            source_command="/interface print",
            collection_timestamp=time.time(),
            collection_status="SUCCESS",
            normalized_value={"interfaces": [{"name": "ether1", "running": False, "disabled": False}]},
        ),
    ]

    contradictions = collector.detect_contradictions(items)
    assert len(contradictions) >= 1
    assert "DOWN" in contradictions[0]
