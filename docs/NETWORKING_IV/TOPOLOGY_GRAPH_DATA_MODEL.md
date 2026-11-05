# AIRA OS — TOPOLOGY GRAPH DATA MODEL
## Normalized Multi-Layer Graph Schema, Entities & Lifecycle Specification

**Document ID:** `AIRA-NET-IV-MODEL-001`  
**Date:** 2026-10-31 (Revised)  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_DATA_MODEL_SPECIFICATION  

---

## 1. Overview & Data Model Architecture

The Networking IV Graph Data Model provides a normalized, typed representation of complex multi-layer enterprise topologies. It is engineered to represent **incomplete, multi-vendor, and uncertain** network states while maintaining referential integrity in SQLite.

### Architectural Invariants:
1. **Multi-Layer Separation:** Physical cables, Layer 2 VLAN/bonding trunks, Layer 3 routed paths, and virtual tunnels are modeled as distinct, typed edges. They are **never** conflated into generic "links".
2. **Multi-Edge Support:** Multiple parallel edges can exist between the same two nodes (e.g., dual physical uplinks in an LACP bundle, or a physical link alongside a WireGuard overlay).
3. **Decoupled Responsibilities:**
   - **Discovery Engine:** Responsible for discovering network structure and relationship classes.
   - **NMS Engine:** Responsible for observing operational conditions (`oper_status`, reachability, latency).
   - **Topology Engine:** Responsible for storing graph state, evidence references, and historical snapshots.
   - *NMS events can update operational status, but can never mutate physical adjacency or edge structure.*

---

## 2. Entity Definitions & Dataclasses

### 2.1 TopologyNode Model

Represents a network device or boundary endpoint.

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

@dataclass
class TopologyNode:
    id: str                                  # Stable primary key (e.g., 'node_chr' or UUID)
    name: str                                # User-facing display name
    identity: str = ""                       # RouterOS system identity or hostname
    device_id: Optional[str] = None          # Foreign key to inventory.db (devices.id)
    canonical_id: Optional[str] = None       # Reference to CanonicalDevice in memory
    ip: str = ""                             # Primary management IP
    all_ips: List[str] = field(default_factory=list)
    mac: str = ""                            # Primary chassis MAC address
    all_macs: List[str] = field(default_factory=list)
    device_type: str = "router"              # router, switch, access_point, server, wan, client
    device_role: str = "backbone"            # core, distribution, access, edge, backbone, endpoint
    ownership_status: str = "owned"          # owned, managed_external, third_party, unknown
    topology_scope: str = "enterprise_edge"  # enterprise_internal, enterprise_edge, isp_upstream, external
    trust_zone: str = "edge"                 # internal, dmz, edge, isp, external, vpn, unknown
    reachability_status: str = "unknown"     # reachable, unreachable, unknown (managed by NMS / Ping)
    management_status: str = "managed"       # managed, management_unavailable, not_attempted, not_authorized
    observation_freshness: str = "fresh"     # fresh, stale, expired, unknown
    observability: str = "fully_observable"  # fully_observable, partially_observable, not_observable
    latency_ms: float = 0.0                  # Most recent ICMP round-trip latency
    pos_x: float = 0.0                       # Canvas X coordinate
    pos_y: float = 0.0                       # Canvas Y coordinate
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_verified: Optional[float] = None
    last_probe_at: Optional[float] = None
    last_ping_alive: Optional[bool] = None
    serial_number: str = ""
    provenance: str = "discovery_managed"    # discovery_managed, user_managed, hybrid
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 2.2 Strengthened TopologyEdge Model

Represents a specific, typed relationship between two nodes. Strictly separates physical, data-link, routed, and logical relationships:

```python
@dataclass
class TopologyEdge:
    id: str                                  # Unique edge ID (e.g., 'edge_nodeA_eth1_nodeB_eth2_phys')
    source_node_id: str                      # Foreign key to TopologyNode.id
    target_node_id: str                      # Foreign key to TopologyNode.id
    source_interface: str = ""               # Local interface name (e.g. 'ether1', 'sfp-sfpplus1')
    target_interface: str = ""               # Remote interface name (or '' if unobserved/unknown)
    
    # Explicit Semantic Classification (Decision 1 & 2)
    relationship_class: str = "physical"     # physical, layer2, layer3, logical
    relationship_subtype: str = "direct_copper" 
    # Subtypes:
    #   physical: direct_copper, direct_fiber, patch_cable, verified_manual_cable
    #   layer2:   vlan_trunk, vlan_access, bridge_port_member, lacp_bundle_member, shared_switch_domain
    #   layer3:   routed_point_to_point, routed_multiaccess, default_gateway_transit, bgp_peer, ospf_adj
    #   logical:  overlay_tunnel (wireguard/gre/ipip/eoip), parent_child_interface, vpn_session
    
    direction: str = "bidirectional"         # bidirectional, unidirectional, directed_routed
    oper_status: str = "up"                  # up, down, degraded, unknown (UPDATED BY NMS)
    admin_status: str = "enabled"            # enabled, disabled
    verification_status: str = "confirmed"   # confirmed, observed, inferred, manual, conflicting, unknown
    confidence_tier: str = "CONFIRMED"       # CONFIRMED (Tier 1), HIGH (Tier 2), MEDIUM (Tier 3), LOW (Tier 4)
    confidence_score: float = 1.0            # 0.0 to 1.0 mathematical score
    confidence_rationale: str = ""           # Qualitative explanation (NOT score alone)
    bandwidth_bps: int = 1_000_000_000       # Bandwidth capacity in bits/sec (e.g. 1 Gbps)
    vlan_id: Optional[int] = None            # Associated 802.1Q VLAN ID
    is_lag_member: bool = False              # True if member of bonding/LACP trunk
    lag_parent_edge_id: Optional[str] = None # Reference to parent LAG bundle edge
    
    # Timestamps & Lifecycle Tracking (Decision 2 & 4)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_verified: Optional[float] = None
    observation_freshness: str = "fresh"     # fresh, stale, expired
    provenance: str = "discovery_managed"    # discovery_managed, user_managed, hybrid
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 2.3 EdgeEvidence Model (Decision 3: Explainability)

Stores verifiable telemetry supporting an edge. Enables full auditability from UI to raw CLI:

```python
@dataclass
class EdgeEvidence:
    id: Optional[int]                        # Auto-increment database ID
    edge_id: str                             # Foreign key to TopologyEdge.id
    evidence_type: str                       # mndp_neighbor, lldp_neighbor, arp_entry, route_entry, bridge_host
    protocol: str                            # mndp, lldp, cdp, arp, ospf, bgp, icmp, manual
    observing_device_id: str                 # Exact device that collected the telemetry
    local_interface: str                     # Interface on observing device
    remote_interface: str = ""               # Reported remote interface
    remote_chassis_mac: str = ""             # Reported remote chassis MAC
    raw_excerpt: str = ""                    # Redacted, sanitized CLI snippet (passwords removed)
    confidence_contribution: str = "high"    # high, medium, low
    explanation: str = ""                    # Qualitative rationale explaining what this proves
    observed_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None       # Epoch expiration timestamp (TTL)
    is_active: bool = True                   # False if superseded by negative evidence
```

### 2.4 TopologySnapshot & TopologyChange Models (Decision 4: Integrity)

Point-in-time capture and delta change tracking distinguishing transient failures from real structural removals:

```python
@dataclass
class TopologySnapshot:
    snapshot_id: str                         # e.g., 'snap_1793410000'
    discovery_run_id: Optional[str]
    created_at: float = field(default_factory=time.time)
    node_count: int = 0
    edge_count: int = 0
    graph_json: str = "{}"                   # Immutable JSON serialization of graph
    sha256_hash: str = ""                    # Checksum of graph state
    trigger_type: str = "discovery_run"      # discovery_run, manual, pre_maintenance, nms_audit
    description: str = ""

@dataclass
class TopologyChange:
    id: Optional[int]
    snapshot_id: str
    change_type: str                         
    # Types: NODE_ADDED, NODE_REMOVED, NODE_MODIFIED, 
    #        EDGE_ADDED, EDGE_REMOVED, EDGE_MODIFIED,
    #        STATUS_CHANGED, EVIDENCE_EXPIRED
    entity_id: str                           # node_id or edge_id
    change_reason: str                       # OPERATIONAL_DOWN, EVIDENCE_EXPIRED, CONFIRMED_REMOVAL, etc.
    attribute_name: str = ""                 # e.g., 'oper_status', 'reachability_status'
    before_value_json: str = ""
    after_value_json: str = ""
    detected_at: float = field(default_factory=time.time)
```

---

## 3. Database Schema Migration Specification (`topology.db`)

Non-destructive schema migrations preserving existing tables and data:

```sql
-- 1. Normalized Multi-Edge Table
CREATE TABLE IF NOT EXISTS topology_edges (
    id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_interface TEXT DEFAULT '',
    target_interface TEXT DEFAULT '',
    relationship_class TEXT DEFAULT 'physical',
    relationship_subtype TEXT DEFAULT 'direct_copper',
    direction TEXT DEFAULT 'bidirectional',
    oper_status TEXT DEFAULT 'up',
    admin_status TEXT DEFAULT 'enabled',
    verification_status TEXT DEFAULT 'unknown',
    confidence_tier TEXT DEFAULT 'MEDIUM',
    confidence_score REAL DEFAULT 0.5,
    confidence_rationale TEXT DEFAULT '',
    bandwidth_bps INTEGER DEFAULT 1000000000,
    vlan_id INTEGER,
    is_lag_member INTEGER DEFAULT 0,
    lag_parent_edge_id TEXT,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    last_verified REAL,
    observation_freshness TEXT DEFAULT 'fresh',
    provenance TEXT DEFAULT 'discovery_managed',
    user_overrides_json TEXT DEFAULT '{}',
    metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY (source_node_id) REFERENCES topology_nodes (id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES topology_nodes (id) ON DELETE CASCADE
);

-- 2. First-Class Edge Evidence Table
CREATE TABLE IF NOT EXISTS topology_edge_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    protocol TEXT DEFAULT '',
    observing_device_id TEXT NOT NULL,
    local_interface TEXT DEFAULT '',
    remote_interface TEXT DEFAULT '',
    remote_chassis_mac TEXT DEFAULT '',
    raw_excerpt TEXT DEFAULT '',
    confidence_contribution TEXT DEFAULT 'medium',
    explanation TEXT DEFAULT '',
    observed_at REAL NOT NULL,
    expires_at REAL,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (edge_id) REFERENCES topology_edges (id) ON DELETE CASCADE
);

-- 3. Snapshots Table
CREATE TABLE IF NOT EXISTS topology_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    discovery_run_id TEXT,
    created_at REAL NOT NULL,
    node_count INTEGER DEFAULT 0,
    edge_count INTEGER DEFAULT 0,
    graph_json TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    trigger_type TEXT DEFAULT 'discovery_run',
    description TEXT DEFAULT ''
);

-- 4. Topology Changes (Delta Log)
CREATE TABLE IF NOT EXISTS topology_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    change_reason TEXT DEFAULT '',
    attribute_name TEXT DEFAULT '',
    before_value_json TEXT DEFAULT '',
    after_value_json TEXT DEFAULT '',
    detected_at REAL NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES topology_snapshots (snapshot_id) ON DELETE CASCADE
);

-- High-performance indexes
CREATE INDEX IF NOT EXISTS idx_edges_rel ON topology_edges(relationship_class, relationship_subtype);
CREATE INDEX IF NOT EXISTS idx_edges_nodes ON topology_edges(source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_edge_ev_edge ON topology_edge_evidence(edge_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON topology_snapshots(created_at);
CREATE INDEX IF NOT EXISTS idx_changes_snap ON topology_changes(snapshot_id);
```

---

## 4. Lifecycle Failure State Discrimination (Decision 4)

To protect graph integrity from transient polling anomalies, the engine strictly distinguishes five failure scenarios:

1. **Operational Link Down:** The physical cable remains connected, but carrier is lost (`oper_status = "down"`). Edge remains in graph.
2. **Temporarily Unreachable:** Node failed 1-2 ICMP pings. Status set to `reachability_status = "unknown"`. Node and edges remain in graph.
3. **Discovery Incomplete:** Partial CLI command timeout during discovery. Limitations logged; existing graph preserved.
4. **Evidence Expired:** Observation older than TTL ($> 3600\text{s}$) without negative contradiction. Edge marked `observation_freshness = "expired"`.
5. **Confirmed Removal:** Explicit operator deletion or verified port re-cabling to another host. Edge transitioned to `tombstoned`.
