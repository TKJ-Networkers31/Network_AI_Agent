# AIRA OS — Phase Networking III
# Unified Network Data Model Specification

## 1. Executive Summary

This document specifies the vendor-agnostic, normalized network abstractions implemented in `core/network_intelligence/network_models.py` under Work Package N3.5 of Phase Networking III.

These models decouple higher-level network intelligence (topology inference, root-cause diagnosis, NMS telemetry) from vendor-specific CLI outputs (RouterOS v6, RouterOS v7, Cisco IOS, Linux iproute2).

---

## 2. Normalized Entities

### 2.1 Interface Model: `NormalizedInterface`

```python
@dataclass
class NormalizedInterface:
    interface_name: str
    device_id: str
    mac_address: str = "00:00:00:00:00:00"
    admin_status: str = "enabled"      # enabled, disabled
    oper_status: str = "unknown"       # up, down, unknown
    interface_type: str = "ethernet"   # ethernet, bridge, vlan, wlan, pppoe, vpn
    mtu: int = 1500
    speed_bps: int = 0
    duplex: str = "unknown"            # full, half, unknown
    running: bool = False
    comment: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_drops: int = 0
    tx_drops: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
```

### 2.2 IP Address Model: `NormalizedIPAddress`

```python
@dataclass
class NormalizedIPAddress:
    device_id: str
    interface_name: str
    ip_address: str                    # Host IP, e.g. "192.168.1.1"
    netmask: str                       # e.g. "255.255.255.0"
    prefix_length: int                 # e.g. 24
    network: str                       # Subnet, e.g. "192.168.1.0"
    is_primary: bool = True
    disabled: bool = False
    invalid: bool = False
    dynamic: bool = False
    comment: str = ""
```

Calculates `cidr` automatically as `f"{self.ip_address}/{self.prefix_length}"`.

### 2.3 Route Model: `NormalizedRoute`

```python
@dataclass
class NormalizedRoute:
    device_id: str
    dst_prefix: str                    # e.g. "0.0.0.0/0"
    gateway: str                       # Gateway IP or interface name
    interface_name: str = ""
    metric: int = 1
    protocol: str = "static"           # static, connected, ospf, bgp
    active: bool = True
    dynamic: bool = False
    disabled: bool = False
    unreachable: bool = False
```

Calculates `is_default_route` automatically if `dst_prefix == "0.0.0.0/0"`.

### 2.4 Neighbor & Link Models: `NormalizedNeighbor`, `NormalizedLink`

```python
@dataclass
class NormalizedNeighbor:
    observing_device_id: str
    local_interface: str
    remote_device_id: str = ""
    remote_identity: str = ""
    remote_ip: str = ""
    remote_mac: str = ""
    remote_interface: str = ""
    protocol: str = "mndp"             # mndp, lldp, cdp, arp
    platform: str = ""
    version: str = ""

@dataclass
class NormalizedLink:
    link_id: str
    source_device_id: str
    source_interface: str
    target_device_id: str
    target_interface: str
    link_type: LinkType                # physical, layer2_adjacency, routed, vpn, wireless, inferred
    confidence: CorrelationConfidence  # CONFIRMED, HIGH, MEDIUM, LOW, INFERRED
    confidence_score: float
    verification_status: str           # confirmed, observed, inferred, manual, conflicting
    evidence_types: List[str]
    provenance: str = "discovery_managed"
```

---

## 3. Converters & Parsers

The module includes robust parsers:
- `parse_interface_item(item, device_id)`: Maps RouterOS v6/v7 `/interface print` dictionaries to `NormalizedInterface`.
- `parse_ip_address_item(item, device_id)`: Splits RouterOS address strings (e.g. `"192.168.88.1/24"`) into host IP, prefix length, and calculates subnet network address via `ipaddress.ip_network`.

---

## 4. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/core/network_intelligence/network_models.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_network_models.py` (4 tests passed).
