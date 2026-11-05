# AIRA OS — NETWORKING IV ARCHITECTURE AUDIT
## Automatic Topology Discovery & Interactive Visualization

**Document ID:** `AIRA-NET-IV-AUDIT-001`  
**Date:** 2026-10-31  
**Author:** AIRA Core Engineering & Network Architecture Team  
**Status:** ARCHITECTURE_AUDIT_COMPLETE (Draft for Review & Approval)  
**Baseline:** Networking III Accepted (`be59871acd2dd92c581d8944e65899d485f208ae`), Stabilization & Automation Accepted, Live Single-Device Acceptance Passed (`10.66.38.30:22`).

---

## 1. Executive Summary & Audit Context

The purpose of this architecture audit is to thoroughly inspect the existing AIRA OS codebase, determine the exact state of topology and network intelligence capabilities, identify architectural gaps, and establish a rigorous, evidence-based blueprint for **Phase Networking IV: Automatic Topology Discovery & Interactive Visualization**.

AIRA OS is not a generic diagram tool or disconnected network terminal. Its goal is to maintain an accurate, live, evidence-grounded topological graph of an enterprise network that reflects reality, exposes uncertainty, links directly into the Network Management System (NMS), and provides causal graph context to the Network Intelligence diagnostic pipeline.

### Core Architectural Principles for Networking IV:
1. **Preservation of Existing Assets:** Reuse existing SQLite databases, connection managers, canonical models, and UI canvases without destructive rewrites or framework additions.
2. **Strict Read-Only Enforcement:** Zero configuration mutations or state pushes to target network equipment.
3. **Evidence-Based Provenance:** Every node, edge, and status attribute must point to verifiable evidence (MNDP, LLDP, ARP, routing table, ICMP, SNMP, or explicit administrator confirmation).
4. **Epistemic Honesty:** Never equate a shared subnet or cached ARP entry with confirmed physical port-to-port cabling. Distinguish directly observed connections from strongly/weakly inferred relationships.
5. **Continuous Dynamic Synchronization:** Topology must not be a static one-off scan. It must react to live NMS monitoring events (link down, reachability change) and track historical changes across time.

---

## 2. Audit of Existing Components

### 2.1 CanonicalDevice & Inventory Registry (`core/canonical_network.py`, `core/inventory_store.py`)
- **Current State:**
  - `CanonicalDevice` provides a clean unified dataclass separating user-configured identity (`inventory_name`, `user_overrides`) from observed hardware facts (`observed_identity`, `serial_number`, `model`, `ros_major_version`).
  - Precedence in `display_name` is strictly ordered: Custom Name $\rightarrow$ Inventory Name $\rightarrow$ Observed Identity $\rightarrow$ Management IP.
  - Multi-IP and multi-MAC tracking is supported via `all_ips` and `all_macs`.
  - `InventoryStore` provides encrypted secret storage (`.inventory.key` with AES-GCM Fernet) in `AIRA_ECOSYSTEM/database/inventory.db`.
- **Strengths:** Excellent separation of configuration from observation; robust identity precedence.
- **Identified Gaps for Networking IV:**
  - `CanonicalDevice` does not yet store a direct list of active `TopologyEdge` identifiers; edges are maintained separately in `topology.db`.
  - Lacks bidirectional linkage between canonical interface names (e.g., `ether1`) and discovered neighbor chassis/port IDs.

### 2.2 Topology Engine & Models (`core/topology_engine.py`, `core/topology_models.py`, `core/topology_discovery.py`)
- **Current State:**
  - `TopologyEngine` manages `AIRA_ECOSYSTEM/database/topology.db` with non-destructive migrations.
  - Tables implemented:
    - `topology_nodes`: Node metadata, ownership (`owned`, `managed_external`, `third_party`, `unknown`), scope (`enterprise_internal`, `enterprise_edge`, `isp_upstream`, `external`), reachability (`reachable`, `unreachable`, `unknown`), observation freshness (`fresh`, `stale`, `expired`), coordinates (`pos_x`, `pos_y`), and JSON payloads.
    - `topology_links`: Interconnections (`source_id`, `target_id`, `source_port`, `target_port`, `link_type`, `verification_status`, `confidence`).
    - `topology_evidence`: Subject-based evidence records (`subject_type`, `subject_id`, `evidence_type`, `protocol`, `raw_excerpt`, `confidence`, `observed_at`).
    - `topology_policy`: Governance settings (`seed_device_id`, `discovery_mode`, `approved_discovery_scopes`, `excluded_subnets`, `isp_boundary_interfaces`).
    - `topology_discovery_jobs`: Job execution logs with duration, limitations, and errors.
    - `topology_conflicts`: Tracks identity and port wiring conflicts for operator review.
    - `topology_audit_log`: Audit trail for governance changes.
  - `TopologyDiscoveryMixin` executes version-aware read-only RouterOS command sets (v6 vs v7), extracting identity, resources, interfaces, IP addresses, routing tables, neighbor tables (MNDP/LLDP), ARP entries, bridge ports, bridge hosts, DHCP leases, and VLANs.
  - Deterministic node status calculation (`calculate_deterministic_node_status`) enforces reachability logic based on fresh active evidence.
- **Strengths:** Non-destructive schema evolution, comprehensive RouterOS parsing, deterministic status calculator, ISP boundary protection.
- **Identified Gaps for Networking IV:**
  - **No Multi-Edge / Directed Edge Support:** `topology_links` is strictly one record per pair of nodes. If two routers share both an untagged trunk and multiple routed subnets, or multiple physical aggregated links (LACP), they cannot be cleanly represented as distinct edges.
  - **No Historical Snapshots (`TopologySnapshot`, `TopologyChange`):** Mutations are performed in-place. There is no point-in-time snapshotting mechanism to compare topology at $T_0$ vs $T_1$.
  - **Single-Host Subject Evidence:** `topology_evidence` links to `subject_id`. For links, `subject_id` is a composite string (`node_a->node_b:port`), which can become brittle if node IDs change.

### 2.3 Cross-Device Evidence Correlator (`core/network_intelligence/correlation.py`)
- **Current State:**
  - `CrossDeviceEvidenceCorrelator` correlates observation bundles across multiple devices.
  - Classifies relationships into 5 confidence tiers: `CONFIRMED`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`.
  - Distinguishes bidirectional protocol neighbor matches (MNDP/LLDP) from mutual ARP matching and single-sided subnet overlap.
  - Rule `_correlate_subnet_only` explicitly marks relationships as candidate links with alternative interpretations (e.g. shared L2 switch domain).
- **Strengths:** Mathematical rigor; zero tolerance for false physical assertions based solely on shared IP subnets.
- **Identified Gaps for Networking IV:**
  - The correlator operates primarily in-memory on `device_bundles` collected during Network Intelligence investigations. It is not currently hooked into the main `TopologyEngine.discover()` pipeline to generate persistent `topology_links`.

### 2.4 Multi-Device Collector (`core/network_intelligence/multi_device_collector.py`)
- **Current State:**
  - ThreadPool-driven concurrent evidence collection across multiple devices.
  - Handles partial failures gracefully (failure on device A does not abort collection on device B).
  - Collects command maps for v6 and v7 RouterOS.
- **Strengths:** Excellent resilience against partial lab timeouts.
- **Identified Gaps for Networking IV:**
  - Operates independently from `TopologyDiscoveryMixin.interrogate_routeros_readonly`. Both perform similar RouterOS commands (`/interface print detail`, `/ip route print detail`, etc.), creating slight redundancy.

### 2.5 Normalized Network Models (`core/network_intelligence/network_models.py`)
- **Current State:**
  - Provides canonical dataclasses: `NormalizedInterface`, `NormalizedIPAddress`, `NormalizedRoute`, `NormalizedNeighbor`, `NormalizedVLAN`, `NormalizedLink`.
  - Typed enums for `InterfaceOperStatus` (`up`, `down`, `unknown`), `LinkType` (`physical`, `layer2_adjacency`, `routed`, `vpn`, `wireless`, `inferred`), and `CorrelationConfidence`.
- **Strengths:** Clean domain representations.
- **Identified Gaps for Networking IV:**
  - `TopologyEngine` still uses untyped dictionaries and raw SQLite rows internally rather than instantiating these normalized dataclasses.

### 2.6 Network Intelligence Investigator (`core/network_intelligence/investigator.py`)
- **Current State:**
  - Classifies symptoms (`OSPF_ADJACENCY_FAILURE`, `BGP_PREFIXES_MISSING`, `VLAN_TRUNK_FAILURE`, `LAN_NO_INTERNET`, `DEFAULT_ROUTE_FAILS`).
  - Executes minimal evidence collection plans and deterministic hypothesis generation.
- **Strengths:** High diagnostic accuracy for single targets.
- **Identified Gaps for Networking IV:**
  - Lacks graph traversal capabilities. When investigating a default route failure, it does not query `TopologyEngine` to find the next-hop node object and its upstream interface status.

### 2.7 NMS Historical Metrics & Background Engine (`core/nms_engine.py`, `core/nms_models.py`)
- **Current State:**
  - Continuous device reachability, RouterOS CPU/memory/uptime metrics, interface bandwidth delta rate calculation (`calculate_traffic_rate`), and incident management.
  - Robust FSM (`NmsSchedulerState`: `STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `FAILED`).
  - Idempotent locking and single-flight execution.
- **Strengths:** High reliability, responsive shutdown, zero polling storms.
- **Identified Gaps for Networking IV:**
  - NMS updates `nms_device_profiles` and `nms_interface_metrics`, but does not automatically emit events to update `topology_nodes.reachability_status` or `topology_links.oper_status` in real-time.

### 2.8 Frontend Topology Canvas (`TopologyPage.jsx`, `TopologyNodeInspector.jsx`, `TopologyGovernanceModals.jsx`)
- **Current State:**
  - Full React canvas with SVG link layer, draggable node cards, search, type filtering, zoom controls, and inspection sidebar.
  - Visual indicators for ownership (`Owned`, `ISP/3rd`, `Unknown`), freshness badges (`Fresh`, `Stale`, `Expired`), and link verification pills.
  - Interactive governance modals: Policy editor, review queue, conflict resolver, manual node and link creators.
- **Strengths:** Comprehensive feature set, responsive UI, zero external canvas bloat (pure SVG/Tailwind).
- **Identified Gaps for Networking IV:**
  - No interactive edge click selection: Clicking a link does not open an Edge Evidence Inspector.
  - No historical topology comparison / timeline slider.
  - Lacks visual representation of parallel links or asymmetric routing.

---

## 3. Detailed Gap Analysis Matrix

| Capability Area | Existing Architecture (Networking III Baseline) | Required for Networking IV | Gap Severity | Proposed Resolution |
|---|---|---|---|---|
| **Graph Model** | Flat `topology_nodes` & `topology_links` in SQLite. Single link per pair. | Rich `TopologyNode`, `TopologyEdge`, `EdgeEvidence`, `TopologySnapshot`, `TopologyChange`. | High | Add new normalized migration tables in `topology.db`. |
| **Edge Evidence** | Subject string in `topology_evidence`. | First-class `EdgeEvidence` with local/remote port, protocol, decay timestamp, raw CLI excerpt. | High | Create dedicated `topology_edge_evidence` table with indexed foreign keys. |
| **Historical Snapshots** | In-place updates only. No historical diffing. | Immutable `TopologySnapshot` and `TopologyChange` log for point-in-time auditing. | Medium | Add snapshot generation on discovery run completion with diff calculation. |
| **Discovery Pipeline** | `TopologyDiscoveryMixin` parses seed router tables. | Unified 4-tier discovery pipeline using `CrossDeviceEvidenceCorrelator` for multi-hop link verification. | High | Integrate correlator directly into discovery reconciliation. |
| **Network Intelligence** | Isolated diagnosis on target device. | Topology-aware diagnosis (upstream graph traversal, root-cause propagation). | High | Inject `TopologyGraphContext` into `investigator.py` and `auto_orchestrator.py`. |
| **NMS Synchronization** | Periodic manual refresh or independent NMS tables. | Event-driven link & node status updates from NMS poll cycles. | Medium | Connect NMS event bus emissions to `TopologyEngine.handle_nms_event()`. |
| **Frontend Visualization** | SVG canvas, node dragging, node inspector sidebar. | Edge evidence inspector, parallel link curves, historical timeline slider, diff overlay. | Medium | Extend `TopologyPage.jsx` and add `TopologyEdgeInspector.jsx` & `TopologyTimeline.jsx`. |

---

## 4. Reusable Components & Non-Duplication Principles

To prevent code bloat and architectural divergence, the following existing assets will be strictly reused:

1. **Database & Storage:**
   - Keep `AIRA_ECOSYSTEM/database/topology.db` as the single authoritative database for topology and NMS data.
   - Use non-destructive `PRAGMA table_info` schema migrations without dropping existing data.
2. **Connection & Execution Boundary:**
   - Reuse `agents/akane/connection_manager.py` (AIRA Persistent Connection Engine). No new SSH/Telnet harnesses.
   - All discovery commands must pass through `validate_readonly_command()`.
3. **Data Parsers:**
   - Reuse all existing parsers in `core/topology_parsers.py` (`parse_mikrotik_interfaces`, `parse_mikrotik_routes`, `parse_mikrotik_arp`, `parse_mikrotik_neighbors`, `parse_mikrotik_bridge_hosts`).
4. **Correlation Logic:**
   - Reuse `CrossDeviceEvidenceCorrelator` in `core/network_intelligence/correlation.py` as the mathematical core for multi-node link classification.
5. **Frontend Canvas:**
   - Preserve `TopologyPage.jsx` and its custom SVG layer. Do not import heavyweight external graph libraries (e.g. Cytoscape, D3, Vis.js) that would bloat bundle size or break existing custom Tailwind styling.

---

## 5. Architectural Blueprint for Networking IV

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  AIRA OS FRONTEND                                      │
│  TopologyPage.jsx │ TopologyNodeInspector │ TopologyEdgeInspector │ TopologyTimeline   │
└───────────────────────────────────────────▲────────────────────────────────────────────┘
                                            │ HTTP / WebSocket REST & Event Stream
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                                  FASTAPI REST API                                      │
│   GET /api/topology/graph                 POST /api/topology/discover                  │
│   GET /api/topology/edges/{id}/evidence   GET  /api/topology/snapshots                 │
│   GET /api/topology/snapshots/{id}/diff   POST /api/topology/snapshots/compare         │
└───────────────────────────────────────────▲────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                             TOPOLOGY ENGINE V4 (CORE)                                  │
│  ┌───────────────────────┐  ┌────────────────────────┐  ┌────────────────────────────┐ │
│  │   TopologyDiscovery   │  │ CrossDeviceEvidence    │  │     TopologySnapshot       │ │
│  │   Pipeline (4-Tier)   │◄─┤      Correlator        ├──┤         Manager            │ │
│  └───────────┬───────────┘  └────────────────────────┘  └──────────────┬─────────────┘ │
│              │                                                         │               │
│  ┌───────────▼─────────────────────────────────────────────────────────▼─────────────┐ │
│  │               Normalized Graph Store & Schema Migration (topology.db)             │ │
│  │   topology_nodes  │  topology_edges  │  topology_edge_evidence  │  snapshots      │ │
│  └───────────────────────────────────▲───────────────────────────────────────────────┘ │
└──────────────────────────────────────┼─────────────────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┴─────────────────────────────┐
         │                                                           │
┌────────▼─────────────────────────┐       ┌─────────────────────────▼──────────────────┐
│   NMS INTEGRATION (EVENT-DRIVEN) │       │   NETWORK INTELLIGENCE INTEGRATION         │
│  - EventBus listener             │       │  - auto_orchestrator.py                     │
│  - Realtime oper_status update   │       │  - Upstream dependency chain traversal     │
│  - Stale link TTL decayer        │       │  - Topology-aware root cause reasoning     │
└────────▲─────────────────────────┘       └─────────────────────────▲──────────────────┘
         │                                                           │
┌────────┴───────────────────────────────────────────────────────────┴──────────────────┐
│                       AIRA PERSISTENT CONNECTION ENGINE (APCE)                         │
│                  Read-Only Paramiko SSH │ Persistent Sessions │ CHR @ 10.66.38.30      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Audit Conclusion & Next Steps

The existing codebase contains a solid, high-quality foundation:
- Inventory, canonical models, and the connection manager are robust and fully verified on physical/virtual hardware.
- High-level discovery parsers for RouterOS v6/v7 are already implemented and tested.
- The React canvas provides a clean, responsive layout.

The architectural tasks for Networking IV are focused, specific, and achievable without structural risk:
1. Formalize the normalized multi-edge and snapshot data models.
2. Unify the discovery and cross-device evidence correlator pipelines.
3. Wire NMS live events directly into link operational states.
4. Integrate topology graph traversal into the automatic diagnostic orchestrator.
5. Enhance the frontend canvas with edge evidence inspection and snapshot comparison.

**Next Design Deliverable:** `docs/NETWORKING_IV/TOPOLOGY_DISCOVERY_DESIGN.md`.
