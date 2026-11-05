"""
tests/test_networking_iii_network_models.py — Unit tests for Phase Networking III Unified Network Data Model.
"""

import pytest
from core.network_intelligence.network_models import (
    CorrelationConfidence,
    InterfaceOperStatus,
    LinkType,
    NormalizedIPAddress,
    NormalizedInterface,
    NormalizedLink,
    NormalizedNeighbor,
    NormalizedRoute,
    NormalizedVLAN,
    parse_interface_item,
    parse_ip_address_item,
)


def test_normalized_interface_and_converter():
    raw_item = {
        "name": "ether1",
        "type": "ether",
        "mac_address": "08:00:27:CC:21:02",
        "running": True,
        "disabled": False,
        "raw": "0 R ether1",
    }
    iface = parse_interface_item("CHR", raw_item)
    assert iface.device_id == "CHR"
    assert iface.interface_name == "ether1"
    assert iface.mac_address == "08:00:27:CC:21:02"
    assert iface.oper_status == InterfaceOperStatus.UP.value
    assert iface.admin_status == "enabled"

    d = iface.to_dict()
    assert d["is_running"] is True
    assert d["interface_type"] == "ether"


def test_normalized_ip_address_and_cidr():
    raw_item = {
        "address": "192.168.43.30/24",
        "interface": "ether1",
        "dynamic": True,
        "disabled": False,
    }
    ip_obj = parse_ip_address_item("CHR", raw_item)
    assert ip_obj is not None
    assert ip_obj.address == "192.168.43.30"
    assert ip_obj.prefix_len == 24
    assert ip_obj.network_cidr == "192.168.43.0/24"
    assert ip_obj.is_dynamic is True

    # Bad format returns None
    assert parse_ip_address_item("CHR", {"address": "bad_ip"}) is None


def test_normalized_route():
    r = NormalizedRoute(
        device_id="CHR",
        dst_prefix="0.0.0.0/0",
        gateway="192.168.43.1",
        interface_name="ether1",
        active=True,
        dynamic=True,
        raw_flags="DAd",
    )
    assert r.prefix_len == 0
    d = r.to_dict()
    assert d["gateway"] == "192.168.43.1"
    assert d["active"] is True
    assert d["raw_flags"] == "DAd"


def test_normalized_link_and_neighbor():
    link = NormalizedLink(
        source_device_id="R1",
        source_port="ether2",
        target_device_id="R2",
        target_port="ether1",
        link_type=LinkType.LAYER2_ADJACENCY.value,
        confidence=CorrelationConfidence.HIGH.value,
        evidence_sources=["mndp_neighbor", "subnet_overlap"],
    )
    assert link.confidence == "HIGH"
    assert link.link_type == "layer2_adjacency"
    assert len(link.evidence_sources) == 2

    neigh = NormalizedNeighbor(
        local_device_id="R1",
        local_interface="ether2",
        remote_device_id="R2",
        remote_ip="10.10.10.2",
        discovery_protocol="mndp",
    )
    assert neigh.discovery_protocol == "mndp"
    assert neigh.remote_ip == "10.10.10.2"
