"""
core/network_intelligence/network_models.py — Unified Network Data Model for AIRA OS.

Provides consistent, canonical dataclasses for network entities across multi-vendor devices:
- NormalizedInterface
- NormalizedIPAddress
- NormalizedRoute
- NormalizedNeighbor
- NormalizedVLAN
- NormalizedLink

Supports optional fields, vendor-specific capability metadata, and serialization.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.topology_models import normalize_ip, normalize_mac, sanitize_untrusted_text


class InterfaceOperStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class LinkType(str, Enum):
    PHYSICAL = "physical"
    LAYER2_ADJACENCY = "layer2_adjacency"
    ROUTED = "routed"
    VPN = "vpn"
    WIRELESS = "wireless"
    INFERRED = "inferred"


class CorrelationConfidence(str, Enum):
    CONFIRMED = "CONFIRMED"  # Bi-directional protocol evidence (e.g. LLDP/MNDP both sides) or operator confirmed
    HIGH = "HIGH"            # Direct protocol neighbor or Subnet + mutual ARP match
    MEDIUM = "MEDIUM"        # Common subnet without mutual ARP or single-sided observation
    LOW = "LOW"              # Inferred from routing next-hop or MAC forwarding entry
    UNKNOWN = "UNKNOWN"      # Insufficient evidence


@dataclass
class NormalizedInterface:
    device_id: str
    interface_name: str
    interface_type: str = "ether"
    mac_address: Optional[str] = None
    oper_status: str = "unknown"
    admin_status: str = "enabled"
    mtu: Optional[int] = 1500
    speed_bps: Optional[int] = None
    description: str = ""
    rx_octets: Optional[int] = None
    tx_octets: Optional[int] = None
    is_running: bool = False
    is_disabled: bool = False
    raw_flags: str = ""
    extra_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "interface_name": self.interface_name,
            "interface_type": self.interface_type,
            "mac_address": self.mac_address,
            "oper_status": self.oper_status,
            "admin_status": self.admin_status,
            "mtu": self.mtu,
            "speed_bps": self.speed_bps,
            "description": self.description,
            "rx_octets": self.rx_octets,
            "tx_octets": self.tx_octets,
            "is_running": self.is_running,
            "is_disabled": self.is_disabled,
            "raw_flags": self.raw_flags,
            "extra_attributes": self.extra_attributes,
        }


@dataclass
class NormalizedIPAddress:
    device_id: str
    address: str
    prefix_len: int
    interface_name: str
    address_family: str = "ipv4"
    network_cidr: str = ""
    is_dynamic: bool = False
    is_disabled: bool = False

    def __post_init__(self):
        try:
            net = ipaddress.ip_network(f"{self.address}/{self.prefix_len}", strict=False)
            self.network_cidr = str(net)
        except Exception:
            self.network_cidr = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "address": self.address,
            "prefix_len": self.prefix_len,
            "interface_name": self.interface_name,
            "address_family": self.address_family,
            "network_cidr": self.network_cidr,
            "is_dynamic": self.is_dynamic,
            "is_disabled": self.is_disabled,
        }


from core.routing.unified_route_parser import (
    NormalizedRoute,
    RouteProtocol,
    RouteType,
)


@dataclass
class NormalizedNeighbor:
    local_device_id: str
    local_interface: str
    remote_device_id: Optional[str] = None
    remote_device_name: Optional[str] = None
    remote_interface: Optional[str] = None
    remote_ip: Optional[str] = None
    remote_mac: Optional[str] = None
    discovery_protocol: str = "mndp"  # mndp, lldp, cdp, arp
    observation_timestamp: float = field(default_factory=time.time)
    confidence: str = CorrelationConfidence.MEDIUM.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "local_device_id": self.local_device_id,
            "local_interface": self.local_interface,
            "remote_device_id": self.remote_device_id,
            "remote_device_name": self.remote_device_name,
            "remote_interface": self.remote_interface,
            "remote_ip": self.remote_ip,
            "remote_mac": self.remote_mac,
            "discovery_protocol": self.discovery_protocol,
            "observation_timestamp": self.observation_timestamp,
            "confidence": self.confidence,
        }


@dataclass
class NormalizedVLAN:
    device_id: str
    vlan_id: int
    name: str = ""
    bridge_name: Optional[str] = None
    tagged_interfaces: List[str] = field(default_factory=list)
    untagged_interfaces: List[str] = field(default_factory=list)
    is_disabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "vlan_id": self.vlan_id,
            "name": self.name,
            "bridge_name": self.bridge_name,
            "tagged_interfaces": list(self.tagged_interfaces),
            "untagged_interfaces": list(self.untagged_interfaces),
            "is_disabled": self.is_disabled,
        }


@dataclass
class NormalizedLink:
    source_device_id: str
    source_port: str
    target_device_id: str
    target_port: str
    link_type: str = LinkType.LAYER2_ADJACENCY.value
    confidence: str = CorrelationConfidence.HIGH.value
    evidence_sources: List[str] = field(default_factory=list)
    last_observed: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_device_id": self.source_device_id,
            "source_port": self.source_port,
            "target_device_id": self.target_device_id,
            "target_port": self.target_port,
            "link_type": self.link_type,
            "confidence": self.confidence,
            "evidence_sources": list(self.evidence_sources),
            "last_observed": self.last_observed,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Converters from raw / parsed RouterOS structures
# ---------------------------------------------------------------------------

def parse_interface_item(dev_id: str, item: Dict[str, Any]) -> NormalizedInterface:
    """Converts a raw parsed interface dict into NormalizedInterface."""
    name = sanitize_untrusted_text(item.get("name") or "")
    itype = sanitize_untrusted_text(item.get("type") or "ether")
    mac = normalize_mac(item.get("mac_address") or item.get("mac"))
    running = bool(item.get("running", True))
    disabled = bool(item.get("disabled", False))
    raw = item.get("raw", "")
    oper = InterfaceOperStatus.UP.value if (running and not disabled) else InterfaceOperStatus.DOWN.value

    return NormalizedInterface(
        device_id=dev_id,
        interface_name=name,
        interface_type=itype,
        mac_address=mac,
        oper_status=oper,
        admin_status="disabled" if disabled else "enabled",
        is_running=running,
        is_disabled=disabled,
        raw_flags=str(item.get("raw_flags") or ""),
        extra_attributes={"raw": raw[:200] if raw else ""},
    )


def parse_ip_address_item(dev_id: str, item: Dict[str, Any]) -> Optional[NormalizedIPAddress]:
    """Converts a raw parsed IP address dict into NormalizedIPAddress."""
    raw_addr = item.get("address", "")
    if "/" not in raw_addr:
        return None
    parts = raw_addr.split("/")
    ip_str = normalize_ip(parts[0])
    if not ip_str:
        return None
    try:
        plen = int(parts[1])
    except ValueError:
        return None

    iface = sanitize_untrusted_text(item.get("interface") or "")
    dyn = bool(item.get("dynamic", False))
    dis = bool(item.get("disabled", False))

    return NormalizedIPAddress(
        device_id=dev_id,
        address=ip_str,
        prefix_len=plen,
        interface_name=iface,
        is_dynamic=dyn,
        is_disabled=dis,
    )
