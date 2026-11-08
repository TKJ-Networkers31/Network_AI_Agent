"""
tests/test_phase5_ros_compatibility.py — RouterOS v6 vs v7 Compatibility Test Suite (Phase 5).

Verifies version-aware CLI fixtures, command mapping, and deterministic parsing across:
- /ip address print
- /ip route print (v6 A S/ADC vs v7 As/DAc flags, Columns headers)
- /ip firewall filter print (FastTrack, drop invalid, accept established)
- /ip firewall nat print (srcnat, masquerade)
- /interface bridge vlan print
- /routing ospf neighbor print
- /routing bgp peer / connection print (v6 remote-address vs v7 remote.address)
- Command mapping dispatch by detected major version (v6 vs v7)
"""

from pathlib import Path
import pytest

from agents.akane.reasoning_engine import parse_routeros_firewall, parse_routeros_routes
from core.network_intelligence.evidence import (
    COMMAND_MAP_V6,
    COMMAND_MAP_V7,
    EvidenceCollector,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ROS_V6_DIR = FIXTURES_DIR / "ros_v6"
ROS_V7_DIR = FIXTURES_DIR / "ros_v7"


# ---------------------------------------------------------------------------
# 1. Command Map Audit: v6 vs v7
# ---------------------------------------------------------------------------

def test_command_maps_distinguish_v6_and_v7_syntax():
    # Routing rules
    assert COMMAND_MAP_V6["routing_rules"] == "/ip route rule print detail"
    assert COMMAND_MAP_V7["routing_rules"] == "/routing rule print detail"

    # OSPF instance
    assert COMMAND_MAP_V6["ospf_instance"] == "/routing ospf instance print detail"
    assert COMMAND_MAP_V7["ospf_instance"] == "/routing ospf instance print"

    # BGP peers / connection
    assert COMMAND_MAP_V6["bgp_peers"] == "/routing bgp peer print detail"
    assert COMMAND_MAP_V7["bgp_peers"] == "/routing bgp connection print detail"


# ---------------------------------------------------------------------------
# 2. IP Route Parsing: v6 vs v7
# ---------------------------------------------------------------------------

def test_parse_routeros_v6_routes():
    v6_file = ROS_V6_DIR / "ip_route.txt"
    content = v6_file.read_text(encoding="utf-8")
    routes = parse_routeros_routes(content)

    assert len(routes) == 3
    # Default route: 0 A S 0.0.0.0/0 192.168.1.1 1
    def_route = next(r for r in routes if r.dst_address == "0.0.0.0/0")
    assert def_route.active is True
    assert def_route.gateway == "192.168.1.1"
    assert def_route.distance == 1

    # Connected routes
    c_route = next(r for r in routes if r.dst_address == "192.168.88.0/24")
    assert c_route.gateway == "ether2"
    assert c_route.distance == 0


def test_parse_routeros_v7_routes():
    v7_file = ROS_V7_DIR / "ip_route.txt"
    content = v7_file.read_text(encoding="utf-8")
    routes = parse_routeros_routes(content)

    assert len(routes) == 3
    # Default route: 0 As 0.0.0.0/0 192.168.1.1 1
    def_route = next(r for r in routes if r.dst_address == "0.0.0.0/0")
    assert def_route.active is True
    assert def_route.gateway == "192.168.1.1"
    assert def_route.distance == 1

    # Dynamic connected route: 1 DAc 192.168.88.0/24 ether2 0
    c_route = next(r for r in routes if r.dst_address == "192.168.88.0/24")
    assert c_route.active is True
    assert c_route.dynamic is True
    assert c_route.gateway == "ether2"


# ---------------------------------------------------------------------------
# 3. IP Address Parsing: v6 vs v7
# ---------------------------------------------------------------------------

def test_parse_ip_addresses_v6_and_v7():
    collector = EvidenceCollector()

    # v6 format
    v6_text = (ROS_V6_DIR / "ip_address.txt").read_text(encoding="utf-8")
    parsed_v6 = collector._parse_ip_addresses(v6_text)
    assert parsed_v6["count"] == 2
    assert parsed_v6["addresses"][0]["address"] == "192.168.88.1/24"
    assert parsed_v6["addresses"][0]["interface"] == "ether2"

    # v7 format
    v7_text = (ROS_V7_DIR / "ip_address.txt").read_text(encoding="utf-8")
    parsed_v7 = collector._parse_ip_addresses(v7_text)
    assert parsed_v7["count"] == 2
    assert parsed_v7["addresses"][0]["address"] == "192.168.88.1/24"
    assert parsed_v7["addresses"][0]["interface"] == "ether2"


# ---------------------------------------------------------------------------
# 4. Firewall Filter & NAT Parsing: v6 vs v7
# ---------------------------------------------------------------------------

def test_parse_firewall_filter_v6_and_v7():
    v6_text = (ROS_V6_DIR / "firewall_filter.txt").read_text(encoding="utf-8")
    rules_v6 = parse_routeros_firewall(v6_text)
    assert len(rules_v6) == 4
    assert any(r.action == "fasttrack-connection" for r in rules_v6)
    assert any(r.action == "drop" and r.connection_state == "invalid" for r in rules_v6)

    v7_text = (ROS_V7_DIR / "firewall_filter.txt").read_text(encoding="utf-8")
    rules_v7 = parse_routeros_firewall(v7_text)
    assert len(rules_v7) == 4
    assert any(r.action == "fasttrack-connection" for r in rules_v7)


def test_parse_firewall_nat_v6_and_v7():
    collector = EvidenceCollector()

    v6_text = (ROS_V6_DIR / "firewall_nat.txt").read_text(encoding="utf-8")
    nat_v6 = collector._parse_nat_rules(v6_text)
    assert nat_v6["count"] == 1
    assert nat_v6["has_masquerade"] is True
    assert nat_v6["rules"][0]["action"] == "masquerade"

    v7_text = (ROS_V7_DIR / "firewall_nat.txt").read_text(encoding="utf-8")
    nat_v7 = collector._parse_nat_rules(v7_text)
    assert nat_v7["count"] == 1
    assert nat_v7["has_masquerade"] is True


# ---------------------------------------------------------------------------
# 5. Bridge VLAN Parsing: v6 vs v7
# ---------------------------------------------------------------------------

def test_parse_bridge_vlan_v6_and_v7():
    collector = EvidenceCollector()

    v6_text = (ROS_V6_DIR / "bridge_vlan.txt").read_text(encoding="utf-8")
    vlan_v6 = collector._parse_bridge_vlan(v6_text)
    assert "10" in vlan_v6["vlan_ids"]
    assert "20" in vlan_v6["vlan_ids"]

    v7_text = (ROS_V7_DIR / "bridge_vlan.txt").read_text(encoding="utf-8")
    vlan_v7 = collector._parse_bridge_vlan(v7_text)
    assert "10" in vlan_v7["vlan_ids"]
    assert "20" in vlan_v7["vlan_ids"]


# ---------------------------------------------------------------------------
# 6. OSPF & BGP Parsing: v6 vs v7
# ---------------------------------------------------------------------------

def test_parse_ospf_neighbor_v6_and_v7():
    collector = EvidenceCollector()

    v6_text = (ROS_V6_DIR / "ospf.txt").read_text(encoding="utf-8")
    ospf_v6 = collector._parse_ospf_neighbors(v6_text)
    assert ospf_v6["count"] == 1
    assert ospf_v6["neighbors"][0]["router_id"] == "10.255.255.2"
    assert ospf_v6["neighbors"][0]["is_full"] is True

    v7_text = (ROS_V7_DIR / "ospf.txt").read_text(encoding="utf-8")
    ospf_v7 = collector._parse_ospf_neighbors(v7_text)
    assert ospf_v7["count"] == 1
    assert ospf_v7["neighbors"][0]["router_id"] == "10.255.255.2"
    assert ospf_v7["neighbors"][0]["is_full"] is True


def test_parse_bgp_peers_v6_and_v7():
    collector = EvidenceCollector()

    # v6 uses remote-address=198.51.100.2
    v6_text = (ROS_V6_DIR / "bgp.txt").read_text(encoding="utf-8")
    bgp_v6 = collector._parse_bgp_peers(v6_text, ros_major=6)
    assert bgp_v6["count"] == 1
    assert bgp_v6["peers"][0]["remote_ip"] == "198.51.100.2"
    assert bgp_v6["peers"][0]["is_established"] is True
    assert bgp_v6["peers"][0]["prefix_count"] == 42

    # v7 uses remote.address=198.51.100.2
    v7_text = (ROS_V7_DIR / "bgp.txt").read_text(encoding="utf-8")
    bgp_v7 = collector._parse_bgp_peers(v7_text, ros_major=7)
    assert bgp_v7["count"] == 1
    assert bgp_v7["peers"][0]["remote_ip"] == "198.51.100.2"
    assert bgp_v7["peers"][0]["is_established"] is True
    assert bgp_v7["peers"][0]["prefix_count"] == 42
