"""
Unit tests for AKANE Network Reasoning Engine in agents/akane/reasoning_engine.py
"""

import pytest
from agents.akane.reasoning_engine import (
    evaluate_longest_prefix_match,
    parse_routeros_routes,
    parse_routeros_firewall,
    analyze_firewall_rules,
    analyze_vlan_configuration,
    generate_evidence_contract,
    ParsedRoute,
)


def test_longest_prefix_match_evaluator():
    sample_routes_text = """
Flags: X - disabled, A - active, D - dynamic, C - connect, S - static
 #      DST-ADDRESS        PREF-SRC        GATEWAY            DISTANCE
 0 ADS  0.0.0.0/0                          10.0.0.1                  1
 1 ADC  192.168.1.0/24     192.168.1.1     bridge-lan                0
 2 A S  192.168.1.50/32                    192.168.1.200             1
 3 ADC  10.0.0.0/24        10.0.0.2        ether1-wan                0
"""
    routes = parse_routeros_routes(sample_routes_text)
    assert len(routes) == 4

    # 1. Host route (/32) match
    m_host = evaluate_longest_prefix_match(routes, "192.168.1.50")
    assert m_host["matched"] is True
    assert m_host["best_route"]["dst_address"] == "192.168.1.50/32"
    assert m_host["best_route"]["prefix_len"] == 32

    # 2. Subnet route (/24) match
    m_subnet = evaluate_longest_prefix_match(routes, "192.168.1.100")
    assert m_subnet["matched"] is True
    assert m_subnet["best_route"]["dst_address"] == "192.168.1.0/24"
    assert m_subnet["best_route"]["prefix_len"] == 24

    # 3. Internet IP matches default route (0.0.0.0/0)
    m_internet = evaluate_longest_prefix_match(routes, "8.8.8.8")
    assert m_internet["matched"] is True
    assert m_internet["best_route"]["dst_address"] == "0.0.0.0/0"
    assert m_internet["is_default_route_match"] is True

    # 4. Inactive routes without default
    only_specific = [ParsedRoute(dst_address="172.16.0.0/16", gateway="172.16.0.1", active=True)]
    m_none = evaluate_longest_prefix_match(only_specific, "10.1.1.1")
    assert m_none["matched"] is False


def test_firewall_and_nat_analyzer():
    firewall_sample = """
Flags: X - disabled, I - invalid, D - dynamic
 0  ;;; defconf: accept established,related
    chain=forward action=accept connection-state=established,related
 1  ;;; defconf: fasttrack
    chain=forward action=fasttrack-connection connection-state=established,related
 2  ;;; defconf: drop invalid
    chain=input action=drop connection-state=invalid
 3  ;;; defconf: accept icmp
    chain=input action=accept protocol=icmp
"""
    rules = parse_routeros_firewall(firewall_sample)
    assert len(rules) == 4

    # FastTrack is after accept established, should flag issue
    res = analyze_firewall_rules(rules, nat_raw="")
    assert res["has_fasttrack"] is True
    assert res["has_masquerade"] is False
    assert any("FastTrack" in iss for iss in res["issues_detected"])
    assert any("NAT" in iss for iss in res["issues_detected"])
    assert res["status"] == "CRITICAL"


def test_vlan_configuration_analyzer():
    bridge_raw = "name=bridge1 vlan-filtering=yes"
    vlan_raw = "bridge=bridge1 vlan-ids=10,20 tagged=ether1 untagged=ether2"
    ports_raw = "interface=ether2 bridge=bridge1 pvid=10"

    res = analyze_vlan_configuration(bridge_raw, vlan_raw, ports_raw)
    assert res["status"] == "HEALTHY"
    assert res["vlan_filtering_enabled"] is True
    assert len(res["issues_detected"]) == 0


def test_evidence_contract_generation():
    contract = generate_evidence_contract(
        symptom="Klien tidak dapat mengakses internet",
        affected_device="R1",
        evidence_collected=[{"source": "routes", "default_gateway_present": True}],
        hypotheses=["Missing NAT masquerade rule", "DNS server unreachable"],
        confirmed_facts=["Default route 0.0.0.0/0 is active to 10.0.0.1"],
        unknowns=["Public IP interface lease state"],
        recommended_action="Tambahkan /ip firewall nat add chain=srcnat action=masquerade out-interface=ether1",
        severity="critical",
    )
    assert contract["symptom"] == "Klien tidak dapat mengakses internet"
    assert contract["affected_device"] == "R1"
    assert contract["severity"] == "critical"
    assert len(contract["hypotheses"]) == 2
    assert "recommended_action" in contract
    assert "timestamp" in contract
