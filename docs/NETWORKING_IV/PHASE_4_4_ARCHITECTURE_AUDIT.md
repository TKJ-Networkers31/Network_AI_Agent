# AIRA OS — NETWORKING IV PHASE 4.4 ARCHITECTURE AUDIT (REVISED)
## Historical Topology, Consistent Snapshots, Multi-Edge Identity & Change Detection

**Document ID:** `AIRA-NET-IV-AUDIT-4.4-REV2`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_AUDIT_REVISED_FOR_PHASE_4_4A  
**Workspace:** `D:\data\agent_ai`  
**Baseline Git Commit:** `be59871acd2dd92c581d8944e65899d485f208ae`  
**Prerequisites Accepted:**  
- Networking III: Multi-Device Network Intelligence (`ACCEPTED`)  
- Networking IV Phase 4.1: Graph Data Model & SQLite (`ACCEPTED`)  
- Networking IV Phase 4.2: Evidence-Based Discovery Pipeline (`ACCEPTED`)  
- Networking IV Phase 4.3: Event-Driven NMS State Synchronization (`ACCEPTED`)  

---

## 1. Executive Summary & Audit Scope

This revised architecture audit establishes the formal technical contract for **Phase 4.4: Historical Topology & Change Detection**. 

In strict adherence to project instructions, **this is a design audit only. Zero source code has been modified, zero database migrations or resets have been executed, and zero commands have been sent to the live lab hardware.**

Phase 4.4 transitions the AIRA Topology Engine from a live ephemeral graph into an **auditable, versioned temporal graph architecture**. This report establishes:
1. **Deterministic Multi-Edge Identity Resolution:** Resolving parallel edges without corrupting endpoint-interface pairings.
2. **Formal Discovery Completeness Contract:** Explicitly representing complete, partial, timed-out, interrupted, and empty discovery states to prevent false link removal assertions.
3. **SQLite Consistency & Realistic Measurement Targets:** Isolating database read transactions from in-memory CPU diff computations while establishing query and total execution duration benchmarks.
4. **Change Taxonomy Reconciliation:** Explicitly mapping the existing `TopologyChangeType` enum to structural, operational, evidence, freshness, and epistemic states.
5. **Phase 4.4A Backend Implementation Scope & Acceptance Criteria.**

---

## 2. Existing Implementation Inventory (Code & Schema Baseline)

A comprehensive code and schema inspection across `core/topology_models.py`, `core/topology_engine.py`, `core/topology_discovery.py`, and `api/routers/topology.py` confirms the baseline state:

| Component | Code Location | Implemented Status | Verification Notes |
|---|---|---|---|
| **`TopologySnapshot` Dataclass** | `core/topology_models.py` (L984–1039) | **PRESENT** | Typed dataclass with `snapshot_id`, `schema_version`, `created_at`, `node_count`, `edge_count`, `graph_json`, `sha256_hash`, `trigger_type`, `description`, `metadata`. Contains `calculate_checksum()` and `verify_integrity()`. |
| **`TopologyChange` Dataclass** | `core/topology_models.py` (L1041–1080) | **PRESENT** | Typed dataclass tracking `snapshot_id`, `change_type`, `entity_id`, `change_reason`, `attribute_name`, `before_value_json`, `after_value_json`, `detected_at`. |
| **`TopologyChangeType` Enum** | `core/topology_models.py` (L561–572) | **PRESENT** | Explicit enum members: `NODE_ADDED`, `NODE_REMOVED`, `NODE_MODIFIED`, `EDGE_ADDED`, `EDGE_REMOVED`, `EDGE_MODIFIED`, `STATUS_CHANGED`, `EVIDENCE_CHANGED`, `EVIDENCE_EXPIRED`. |
| **`topology_snapshots` Table** | `core/topology_engine.py` (L339–351) | **PRESENT** | SQLite table storing `snapshot_id`, `schema_version`, `discovery_run_id`, `created_at`, `node_count`, `edge_count`, `graph_json`, `sha256_hash`, `trigger_type`, `description`, `metadata_json`. Indexed on `created_at`. |
| **Snapshot Immutability Triggers** | `core/topology_engine.py` (L353–363) | **PRESENT** | Database triggers `trg_snapshot_no_update` and `trg_snapshot_no_delete` abort any `UPDATE` or `DELETE` with `SELECT RAISE(ABORT, '... immutable ...')`. |
| **`topology_changes` Table** | `core/topology_engine.py` (L365–376) | **PRESENT** | SQLite table tracking deltas with foreign key `FOREIGN KEY (snapshot_id) REFERENCES topology_snapshots (snapshot_id) ON DELETE SET NULL`. Indexed on `snapshot_id`, `entity_id`, `change_type`. |
| **Repository CRUD Methods** | `core/topology_engine.py` (L791–985) | **PARTIAL** | Basic `create_snapshot()`, `get_snapshot()`, `list_snapshots()`, `record_change()`, and `list_changes()` exist. |

---

## 3. Critical Architecture Gaps Identified

1. **Evidence Serialization Omission:**
   `create_snapshot()` in `core/topology_engine.py` queries `topology_nodes` and `topology_edges`, but **omits `topology_edge_evidence`**. Without evidence serialization, historical snapshots cannot prove *why* a relationship was established or how confidence $S(e)$ was scored.
2. **Absence of Semantic Graph Diff Engine:**
   There is currently zero diffing logic in `TopologyEngine`. No capability exists to compare Snapshot A to Snapshot B, reconcile parallel multi-edges, or detect additions/removals.
3. **Discovery Pipeline Disconnect:**
   [`TopologyDiscoveryMixin`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_discovery.py) does not automatically create snapshots upon run completion, nor does it record `NODE_ADDED` or `EDGE_ADDED` deltas.
4. **Epistemic Incompleteness Unrepresented:**
   `TopologySnapshot` metadata does not record which seed routers timed out or failed authentication, creating a dangerous risk of falsely asserting that unreachable devices were removed.
5. **API & UI Absence:**
   No REST endpoints exist in `api/routers/topology.py` for snapshots or diffs, and no snapshot timeline UI exists in `TopologyPage.jsx`.

---

## 4. Stable Multi-Edge Identity Resolution

### 4.1 The Endpoint-Interface Pairing Problem
In naive undirected edge sorting, sorting device names independently:
$$\min(u, v), \max(u, v)$$
destroys endpoint-interface pairing. 

**Example of the Naive Sorting Bug:**
- Suppose Edge $E$ connects:
  - Device $u = \text{"node\_B"}$ on interface $I_u = \text{"ether1"}$
  - Device $v = \text{"node\_A"}$ on interface $I_v = \text{"ether2"}$
- Sorting devices alone yields $\min(u, v) = \text{"node\_A"}$ and $\max(u, v) = \text{"node\_B"}$.
- If interfaces are uncoordinated, $\text{"node\_A"}$ is falsely associated with $\text{"ether1"}$ and $\text{"node\_B"}$ with $\text{"ether2"}$, inverting the physical pinout and breaking parallel multi-edge disambiguation.

### 4.2 Canonical Endpoint-Interface Tuple Sorting
To preserve pairing, the sorting unit must be the **Endpoint-Interface Tuple**:
$$T_1 = \big(u,\, \text{normalize\_iface}(I_u)\big), \quad T_2 = \big(v,\, \text{normalize\_iface}(I_v)\big)$$

The canonical undirected pair is defined by sorting the tuples lexicographically:
$$(T_A, T_B) = \begin{cases} (T_1, T_2) & \text{if } T_1 \le T_2 \\ (T_2, T_1) & \text{if } T_2 < T_1 \end{cases}$$
where tuple comparison evaluates `(node_id, interface_name)`.

### 4.3 Relationship-Class Specific Identity Semantics

The immutable `edge.id` (e.g. `edge_r1_r2_ether1_ether1_physical`) remains the **primary identity**. When matching edges across different snapshots where IDs may differ, the engine applies the **Semantic Edge Key** specific to each relationship class:

#### 1. Physical Adjacency (`relationship_class == 'physical'`)
- **Semantics:** Direct physical medium (copper patch, direct fiber). Strictly undirected.
- **Identity Key:**
  $$\text{Key}_{\text{phys}} = \Big(\text{"physical"},\, \text{subtype},\, T_A,\, T_B\Big)$$
- Both interfaces MUST be present. If an interface is missing or `"unknown"`, it cannot match a physical edge where parallel links exist.

#### 2. Layer 2 Adjacency (`relationship_class == 'layer2'`)
- **Semantics:** Bridged, switched, or VLAN segmentation.
- **Discriminators:** Subtype, $(T_A, T_B)$, and optional `vlan_id`.
- **Identity Key:**
  $$\text{Key}_{\text{L2}} = \Big(\text{"layer2"},\, \text{subtype},\, T_A,\, T_B,\, \text{vlan\_id}\Big)$$

#### 3. Layer 3 Reachability (`relationship_class == 'layer3'`)
- **Semantics:** Point-to-point routed subnet vs next-hop routing adjacency.
- **Point-to-Point (`subtype == 'routed_point_to_point'`):** Undirected subnet pairing:
  $$\text{Key}_{\text{L3\_p2p}} = \Big(\text{"layer3"},\, \text{"routed_point_to_point"},\, T_A,\, T_B,\, \text{subnet\_cidr}\Big)$$
- **Directed Next-Hop (`subtype == 'next_hop_reachability'`):** Directional relationship from source node $u$ traversing towards next-hop gateway $v$:
  $$\text{Key}_{\text{L3\_directed}} = \Big(\text{"layer3"},\, \text{"next_hop_reachability"},\, u,\, v,\, \text{nexthop\_ip}\Big)$$

#### 4. Logical & Overlay Relationships (`relationship_class == 'logical'`)
- **Semantics:** Tunnels, VPNs, WireGuard peers, IPsec, EoIP, VXLAN.
- **Discriminators:** Subtype, tunnel endpoints, and overlay identifiers (`tunnel_id`, `overlay_id`, `peer_public_key`).
- **Identity Key:**
  $$\text{Key}_{\text{logical}} = \Big(\text{"logical"},\, \text{subtype},\, T_A,\, T_B,\, \text{overlay\_id}\Big)$$

### 4.4 Missing Interfaces & Ambiguity Detection Rules

1. **Missing Interface Handling:**
   - If an edge record has `source_interface == ""` or `target_interface == ""` (e.g. inferred from global routing table without interface resolution):
   - **Single-Link Case:** If between Node $A$ and Node $B$ there is strictly **exactly one edge** of that class in both snapshots, the engine matches them provisionally.
   - **Parallel Multi-Edge Case:** If between Node $A$ and Node $B$ there exist **two or more parallel edges** of that class, an edge with missing interfaces **cannot be disambiguated**.
2. **Ambiguous Match Policy (Never Force a Match):**
   - When candidate matching produces 1-to-many or many-to-many semantic key overlaps:
   - **Strict Rule:** The diff engine MUST NOT arbitrarily pick one edge!
   - The ambiguous candidates MUST be tagged as `INDETERMINATE_AMBIGUOUS_MATCH`.
   - They are excluded from being reported as false `EDGE_ADDED`, `EDGE_REMOVED`, or `EDGE_MODIFIED`.

---

## 5. Discovery Completeness Contract

### 5.1 Snapshot Discovery Metadata Contract
Every snapshot captured by `TopologyEngine` must record the discovery context in `metadata_json`:

```json
{
  "discovery_status": "complete | partial | failed | interrupted | empty",
  "is_complete": true,
  "collection_scope": "internal | boundary | external | recursive_full",
  "discovery_mode": "seed_only | neighbors | full",
  "seed_devices": ["node_10_66_38_30"],
  "expected_devices": ["node_10_66_38_30", "node_10_66_38_31", "node_10_66_38_32"],
  "successful_devices": ["node_10_66_38_30", "node_10_66_38_31"],
  "failed_devices": [
    {
      "device_id": "node_10_66_38_32",
      "error": "Authentication failed",
      "stage": "ssh_connect"
    }
  ],
  "timed_out_devices": [
    {
      "device_id": "node_10_66_38_32",
      "timeout_sec": 15.0
    }
  ],
  "started_at": 1793410500.123,
  "completed_at": 1793410525.456,
  "duration_sec": 25.333,
  "evidence_included": true
}
```

### 5.2 Deterministic Discovery Scenario Behaviors

| Discovery Condition | `discovery_status` | `is_complete` | Graph Diff Removal Behavior |
|---|---|---|---|
| **Complete Discovery** | `"complete"` | `true` | All in-scope devices interrogated successfully. Nodes or edges absent in Target CAN be classified as `NODE_REMOVED` or `EDGE_REMOVED` **only if** both incident endpoints were polled and neighbor tables confirm absence. |
| **Partial Discovery** | `"partial"` | `false` | One or more devices failed or timed out. Any missing node or edge incident to a failed device **MUST NEVER** be classified as removed. Classified as `INDETERMINATE_UNREACHABLE_DEVICE` or `INDETERMINATE_UNVERIFIED_LINK`. |
| **Timed-Out Seed Device** | `"failed"` | `false` | Primary seed device unreachable; zero neighbor data collected. Diff against baseline is flagged `DISCOVERY_FAILED_NO_DATA`. Structural additions/removals are completely suppressed. |
| **Unreachable Device** | `"partial"` | `false` | A known device does not respond to ping or SSH. Classified as `NODE_UNREACHABLE` (Tier 2 Operational), **NEVER** `NODE_REMOVED` (Tier 1 Structural). |
| **Interrupted Discovery** | `"interrupted"` | `false` | Discovery aborted mid-run (e.g. process restart). Snapshot marked incomplete; automated change detection against this snapshot is rejected. |
| **Empty Discovery Result** | `"empty"` | `false` | Zero nodes discovered. Safety circuit-breaker trips: prohibited from being interpreted as "all network infrastructure was deleted". |
| **Out-of-Scope Devices** | — | — | Devices beyond WAN gateway (`trust_zone = "wan"`) are flagged `topology_scope = "external"`. Upstream IP changes are never treated as internal edge removals. |

---

## 6. SQLite Consistency & Performance Engineering

### 6.1 Transaction Boundaries & Measurement Targets
The claim that database lock duration remains low must be treated as an **engineering measurement target ($< 5\text{ ms}$)**, not an unconditional guarantee.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TRANSACTION BOUNDARY SEPARATION                 │
├────────────────────────────────────────────────────────────────────────┤
│ 1. DATABASE TRANSACTION (Inside Lock, Target: < 5 ms)                  │
│    - Acquire TopologyEngine._lock                                      │
│    - BEGIN TRANSACTION                                                 │
│    - SELECT snapshot records (Base & Target)                           │
│    - COMMIT / Close Connection                                         │
├────────────────────────────────────────────────────────────────────────┤
│ 2. DESERIALIZATION & MEMORY ASSEMBLY (Pure CPU, Outside DB Lock)       │
│    - Parse graph_json into In-Memory Graph Objects                     │
│    - Zero database locks held; Live NMS and Discovery unblocked         │
├────────────────────────────────────────────────────────────────────────┤
│ 3. GRAPH DIFF EXECUTION (Pure CPU, Outside DB Lock, Target: < 30 ms)   │
│    - Keyed dictionary lookup on Node IDs & Semantic Edge Keys          │
│    - 5-Tier change classification & epistemic completeness checks      │
│    - Build GraphDiffReport                                             │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Performance Telemetry & Large Graph Bounding
Every diff report must record deterministic execution telemetry:
- `db_query_ms`: Time spent reading snapshot rows from SQLite (target $< 5\text{ ms}$).
- `deserialization_ms`: Time spent parsing JSON strings into graph objects.
- `diff_compute_ms`: Time spent executing node and multi-edge matching.
- `total_duration_ms`: End-to-end execution time.

**Large Graph Safeguards:**
- Graph comparisons use indexed dictionary lookups: $O(|V| + |E|)$ complexity, avoiding $O(|E|^2)$ pairwise scans.
- Hard bound: Automated synchronous diffing is capped at **10,000 nodes and 50,000 edges**. Graphs exceeding this bound return `413 Payload Too Large` and require scoped/filtered comparison (e.g. per-VLAN or per-zone).

---

## 7. Change Taxonomy Reconciliation

### 7.1 Existing Enum Inspection
Inspection of `AIRA_ECOSYSTEM/core/topology_models.py` (lines 561–572) shows the current enum members:
```python
class TopologyChangeType(str, Enum):
    NODE_ADDED = "NODE_ADDED"
    NODE_REMOVED = "NODE_REMOVED"
    NODE_MODIFIED = "NODE_MODIFIED"
    EDGE_ADDED = "EDGE_ADDED"
    EDGE_REMOVED = "EDGE_REMOVED"
    EDGE_MODIFIED = "EDGE_MODIFIED"
    STATUS_CHANGED = "STATUS_CHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
```

### 7.2 Explicit Taxonomy Mapping
We reconcile the 5-Tier change classification against the existing enum:

| Tier | Change Classification | Mapping to `TopologyChangeType` | Target Model Representation |
|---|---|---|---|
| **Tier 1: Structural** | `NODE_ADDED`, `NODE_REMOVED`, `NODE_MODIFIED`<br>`EDGE_ADDED`, `EDGE_REMOVED`, `EDGE_MODIFIED` | Direct 1:1 match with existing enum members | Recorded as `TopologyChange` in `topology_changes` and reported in `GraphDiffReport`. |
| **Tier 2: Operational** | `OPERATIONAL_STATUS_CHANGED`<br>`NODE_REACHABILITY_CHANGED` | Maps to `STATUS_CHANGED` with `attribute_name="oper_status"` or `attribute_name="reachability_status"` | Recorded as `TopologyChange` (already implemented in Phase 4.3). |
| **Tier 3: Evidence** | `EVIDENCE_ADDED`<br>`EVIDENCE_EXPIRED`<br>`CONFIDENCE_CHANGED` | `EVIDENCE_CHANGED` and `EVIDENCE_EXPIRED` exist. Confidence score changes map to `EVIDENCE_CHANGED` with `attribute_name="confidence_score"`. | Recorded as `TopologyChange` when discovery evidence decays or corroborates. |
| **Tier 4: Freshness** | `OBSERVATION_FRESHNESS_CHANGED` | Maps to `STATUS_CHANGED` with `attribute_name="observation_freshness"` | Recorded when decayer marks an edge `'stale'` or observation restores `'fresh'`. |
| **Tier 5: Epistemic** | `INDETERMINATE_UNREACHABLE`<br>`INDETERMINATE_AMBIGUOUS_MATCH` | **DOES NOT MAP TO `TopologyChange`!** | **Strict Epistemic Rule:** Indeterminate states represent *the absence of certainty*, not a confirmed network mutation. They belong strictly in `GraphDiffReport.indeterminate_items` and **must never be written to `topology_changes`**. |

### 7.3 Enum Extension Verdict for Phase 4.4A
- **No breaking enum change is required.** All persistent delta change records can be represented using the existing 9 enum members by leveraging `attribute_name` (`"oper_status"`, `"observation_freshness"`, `"confidence_score"`).
- In Phase 4.4A, an optional non-breaking alias extension (`FRESHNESS_CHANGED = "FRESHNESS_CHANGED"`, `CONFIDENCE_CHANGED = "CONFIDENCE_CHANGED"`) can be added for clarity without modifying existing database records.

---

## 8. Proposed API Specification (Read-Only Blueprint)

```
POST   /api/topology/snapshots
       Creates an immutable snapshot.
       Body: { description?: string, trigger_type?: string, include_evidence?: boolean }
       Returns: TopologySnapshot summary (snapshot_id, sha256_hash, counts, is_complete).

GET    /api/topology/snapshots
       Lists historical snapshots (paginated: limit, offset).
       Filters: trigger_type, discovery_run_id, from_time, to_time.
       Returns: Array of snapshot metadata records.

GET    /api/topology/snapshots/{snapshot_id}
       Retrieves full snapshot details including nodes, edges, and evidence.
       Query: ?summary_only=true|false.

POST   /api/topology/snapshots/compare
       Computes semantic graph diff between baseline and target snapshots.
       Body: { base_snapshot_id: string, target_snapshot_id: string }
       Returns: GraphDiffReport (summary, node_diffs, edge_diffs, operational_diffs, indeterminate_items, telemetry).

GET    /api/topology/changes
       Queries chronological delta changes from topology_changes.
       Filters: snapshot_id, entity_id, change_type, since, limit.
       Returns: Array of TopologyChange records.
```

---

## 9. Phase 4.4A Implementation Scope & Acceptance Criteria

### Sub-Phase 4.4A Scope: Backend Snapshot & Graph Diff Engine
1. **Evidence-Complete Snapshots:**
   Update `create_snapshot()` in `TopologyEngine` to query `topology_edge_evidence` and include serialized evidence in `graph_json`.
2. **Discovery Context Metadata:**
   Enforce the Discovery Completeness Contract (`discovery_status`, `successful_devices`, `failed_devices`, `is_complete`).
3. **Semantic Graph Diff Core:**
   Implement `compare_snapshots(base_id, target_id)` in `TopologyEngine` featuring:
   - Canonical endpoint-interface tuple sorting (`T_A, T_B`).
   - Relationship-class specific semantic edge keys.
   - Ambiguity detection (tagging ambiguous parallel edges as indeterminate).
   - Incomplete discovery guards (suppressing removals for unpolled devices).
   - Execution telemetry (`db_query_ms`, `diff_compute_ms`, `total_duration_ms`).
4. **Automated Discovery Hook:**
   Hook snapshot creation and `TopologyChange` delta recording into `TopologyDiscoveryMixin` upon discovery completion.
5. **Acceptance Test Suite:**
   Author dedicated test suite `AIRA_ECOSYSTEM/tests/test_topology_snapshots_v4.py`.

### Phase 4.4A Acceptance Criteria:
1. `create_snapshot()` produces canonical, SHA-256 verifiable JSON containing nodes, edges, and evidence.
2. Immutability triggers abort any `UPDATE` or `DELETE` against `topology_snapshots`.
3. Parallel multi-edges between identical nodes are differentiated and paired deterministically.
4. Partial discovery runs never report false `NODE_REMOVED` or `EDGE_REMOVED` for failed devices.
5. Database read queries complete within the $< 5\text{ ms}$ measurement target.
6. 100% test pass across backend, frontend, and security regression suites.

---

## 10. Audit Sign-Off & Next Steps

### Audit Status: **REVISED & FINALIZED — READY FOR OPERATOR REVIEW**

- [x] Read-only audit completed; zero code or database modifications made.
- [x] Zero commands sent to live lab CHR (`10.66.38.30:22`).
- [x] Canonical endpoint-interface tuple sorting defined with concrete pinout examples.
- [x] Discovery completeness contract specified with exact metadata schema.
- [x] SQLite lock separation from in-memory diff computation documented.
- [x] Change taxonomy reconciled with existing `TopologyChangeType` enum.
- [x] Working tree preserved intact.

**STOPPED. Standing by for operator review and explicit authorization before commencing Phase 4.4A implementation.**
