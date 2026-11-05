# AIRA OS — Phase Networking III
# Multi-Device Device Inventory Specification

## 1. Executive Summary

This document defines the architectural specification, data schemas, and runtime lifecycle for the **Multi-Device Device Inventory** in AIRA OS, established under Work Package N3.1 of Phase Networking III.

The device inventory transforms AIRA from a single-device observer into an enterprise-grade multi-device platform capable of tracking diverse network appliances across on-premises, cloud, and lab environments.

---

## 2. Conceptual & Schema Architecture

### 2.1 Domain Model: `CanonicalDevice`

The `CanonicalDevice` dataclass (`core/canonical_network.py`) represents the immutable canonical identity and runtime state of every managed or observed network device.

```python
@dataclass
class CanonicalDevice:
    # 1. Identity & Naming
    device_id: str
    inventory_name: str
    observed_identity: str = ""
    hostname: str = ""

    # 2. Management & Reachability
    management_ip: str = ""
    management_port: int = 22
    management_protocol: str = "ssh"  # ssh, winbox, snmp, api, https
    all_ips: List[str] = field(default_factory=list)
    primary_mac: str = "00:00:00:00:00:00"
    all_macs: List[str] = field(default_factory=list)

    # 3. Hardware & Platform
    device_type: str = "mikrotik"
    vendor: str = "MikroTik"
    manufacturer: str = ""
    model: str = ""
    platform: str = ""  # x86_64, tile, mipsbe, arm, arm64
    os_version: str = ""
    firmware_version: str = ""
    ros_major_version: Optional[int] = None
    serial_number: str = ""

    # 4. Operational Status & Health
    connection_status: str = "disconnected"
    device_availability: str = "unknown"
    observation_status: str = "observed"
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    uptime_seconds: Optional[int] = None

    # 5. Network Structural Entities
    interfaces: List[Dict[str, Any]] = field(default_factory=list)
    ip_addresses: List[Dict[str, Any]] = field(default_factory=list)
    vlans: List[Dict[str, Any]] = field(default_factory=list)
    routes_summary: Dict[str, Any] = field(default_factory=dict)
    neighbors: List[Dict[str, Any]] = field(default_factory=list)

    # 6. Classification & Topology Context
    device_role: str = "unspecified"  # core_router, edge_gateway, distribution_switch, access_switch
    tags: List[str] = field(default_factory=list)
    location: str = ""
    site: str = ""
    group: str = ""
    description: str = ""
    notes: str = ""

    # 7. Metadata & Provenance
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    discovered_metadata: Dict[str, Any] = field(default_factory=dict)
    derived_metadata: Dict[str, Any] = field(default_factory=dict)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
```

### 2.2 Precedence Rules for Display Identity

1. **User Override**: If `user_overrides["custom_name"]` is set by the operator, it takes highest precedence.
2. **Observed System Identity**: If telemetric collection succeeds and retrieves `/system/identity`, `observed_identity` is preferred over static inventory labels.
3. **Inventory Name**: Fallback to operator-assigned name at provisioning time.
4. **Management IP**: Ultimate fallback if identity has not been discovered.

---

## 3. Storage & Concurrency Model

### 3.1 SQLite WAL Schema (`inventory.db`)

All device inventory records are persisted in `inventory.db` using SQLite WAL mode (`PRAGMA journal_mode=WAL`).

- **Table**: `devices`
- **Fields**: `id`, `name`, `host`, `port`, `username`, `password_encrypted`, `use_ssh_key`, `ssh_key_path`, `timeout`, `role`, `status`, `last_seen`, `created_at`, `updated_at`.
- **Validation**: Strict uniqueness on device name, IP address formatting validation, integer port range checks (1-65535).

### 3.2 Thread-Safe Batch Resolution

The `CanonicalNetworkRegistry` provides thread-safe batch resolution (`resolve_devices_batch`):
- Accepts a list of device IDs, inventory names, or IP addresses.
- Queries the underlying store in a single connection.
- Omits unresolvable queries gracefully without throwing exceptions.
- Deduplicates results to prevent redundant parallel collection tasks.

---

## 4. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/core/canonical_network.py` & `AIRA_ECOSYSTEM/core/inventory_store.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_inventory.py` (4 tests passed).
- Integration: Fully integrated with `CanonicalNetworkRegistry` and `ConnectionManager`.
