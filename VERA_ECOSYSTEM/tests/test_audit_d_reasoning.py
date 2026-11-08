import pytest
from agents.akane.reasoning_engine import (
    evaluate_longest_prefix_match,
    parse_routeros_routes,
    analyze_firewall_rules,
    ParsedRoute,
)

def test_audit_d_ecmp_and_recursive_gateway():
    routes = [
        ParsedRoute(dst_address="0.0.0.0/0", gateway="192.168.1.1", distance=1, active=True),
        ParsedRoute(dst_address="10.0.0.0/8", gateway="172.16.0.1", distance=1, active=True),
        # ECMP routes for 10.50.0.0/16
        ParsedRoute(dst_address="10.50.0.0/16", gateway="10.1.1.1", distance=1, active=True),
        ParsedRoute(dst_address="10.50.0.0/16", gateway="10.1.1.2", distance=1, active=True),
        # Recursive route: gateway is 10.50.5.5, which falls under 10.50.0.0/16
        ParsedRoute(dst_address="198.51.100.0/24", gateway="10.50.5.5", distance=1, active=True),
    ]

    # Test ECMP match
    res_ecmp = evaluate_longest_prefix_match(routes, "10.50.12.34")
    assert res_ecmp["matched"] is True
    assert res_ecmp["best_route"]["dst_address"] == "10.50.0.0/16"
    assert res_ecmp["is_ecmp"] is True
    assert len(res_ecmp["ecmp_gateways"]) == 2
    assert "10.1.1.1" in res_ecmp["ecmp_gateways"]
    assert "10.1.1.2" in res_ecmp["ecmp_gateways"]
    assert "observed_facts" in res_ecmp
    assert "missing_evidence" in res_ecmp
    assert "limits_disclosure" in res_ecmp

    # Test recursive gateway detection
    res_recursive = evaluate_longest_prefix_match(routes, "198.51.100.25")
    assert res_recursive["matched"] is True
    assert res_recursive["best_route"]["dst_address"] == "198.51.100.0/24"
    assert res_recursive["recursive_gateway_candidate"] is True
    assert len(res_recursive["inferred_hypotheses"]) > 0

def test_audit_d_evidence_separation_firewall():
    firewall_rules = [
        {"chain": "forward", "action": "drop", "src-address": "192.168.1.50", "disabled": False, "comment": "Block compromised host"},
        {"chain": "input", "action": "accept", "protocol": "tcp", "dst-port": "22", "disabled": False, "comment": "Allow management SSH"},
    ]

    res = analyze_firewall_rules(firewall_rules)
    assert res["summary"]["total_rules"] == 2
    assert "observed_facts" in res
    assert "inferred_hypotheses" in res
    assert "missing_evidence" in res
    assert "recommendations" in res
    assert any("mangle" in item.lower() for item in res["missing_evidence"])
    assert any("192.168.1.50" in fact for fact in res["observed_facts"])
