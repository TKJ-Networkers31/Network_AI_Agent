# AIRA OS — TOPOLOGY VALIDATION STRATEGY
## Testing Framework, Epistemic Assertions & Lifecycle Integrity Verification

**Document ID:** `AIRA-NET-IV-VAL-001`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_VALIDATION_SPECIFICATION  

---

## 1. Validation Philosophy & Epistemic Boundaries

Validating an autonomous network topology platform requires strict differentiation between:
1. **Empirical Facts:** Direct, raw, timestamped observations collected from devices (e.g. "Packet received on ether1 advertising chassis MAC 08:00:27:CC:21:02").
2. **Inferences:** Mathematical and rule-based deductions derived from facts (e.g. "Because both devices share an exclusive /30 subnet and resolve each other's MAC in ARP, an active Layer 3 point-to-point link exists").
3. **Uncertainties & Unknowns:** The exact boundaries where telemetry is missing or ambiguous (e.g. "Remote switch port is unobservable because the intermediate switch does not run LLDP").

The validation strategy must prove that AIRA **never confuses an inference for an empirical fact**, and **never hides uncertainty behind a speculative visual link**.

---

## 2. Graph Lifecycle State Distinction Tests

A common failure mode in naive NMS platforms is flappiness: a single dropped packet or temporary SSH timeout immediately deletes an entire branch of the network diagram.

AIRA OS implements five distinct lifecycle failure states. The validation suite must verify each independently:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   GRAPH LIFECYCLE STATE DISTINCTION                    │
├─────────────────────────┬──────────────────┬───────────────────────────┤
│ Failure Classification  │ Triggering Cause │ Graph Engine Reaction     │
├─────────────────────────┼──────────────────┼───────────────────────────┤
│ 1. Operational Link Down│ Carrier lost     │ oper_status = 'down'      │
│                         │ on interface     │ Edge PRESERVED.           │
├─────────────────────────┼──────────────────┼───────────────────────────┤
│ 2. Temp Unreachable     │ 1-2 failed ICMP  │ reachability = 'unknown'  │
│                         │ or SSH timeouts  │ Node PRESERVED.           │
├─────────────────────────┼──────────────────┼───────────────────────────┤
│ 3. Discovery Incomplete │ Partial command  │ limitations logged        │
│                         │ timeout on scan  │ Existing graph PRESERVED. │
├─────────────────────────┼──────────────────┼───────────────────────────┤
│ 4. Evidence Expired     │ Telemetry TTL    │ freshness = 'expired'     │
│                         │ > 3600s exceeded │ Edge marked candidate.    │
├─────────────────────────┼──────────────────┼───────────────────────────┤
│ 5. Confirmed Removal    │ Admin explicit   │ Status = 'tombstoned'     │
│                         │ or port vacated  │ Soft-deleted from canvas. │
└─────────────────────────┴──────────────────┴───────────────────────────┘
```

### 2.1 Test Suite 1: Single-Poll Resiliency (Anti-Flap Assertion)
- **Objective:** Verify that a transient failure during an NMS poll or discovery cycle does **not** delete nodes or edges.
- **Test Procedure:**
  1. Populate graph with Node A, Node B, and Edge $E(A \rightarrow B)$.
  2. Mock 1 failed ICMP poll to Node B (simulating packet loss).
  3. Assert: Node B reachability transitions to `unknown` or `degraded`.
  4. Assert: Node B and Edge $E$ remain present in `topology_nodes` and `topology_edges`.
  5. Mock SSH authentication failure on Node B during discovery.
  6. Assert: Discovery logs limitation `Node B: Authentication timed out`, but **does not purge Edge $E$**.

### 2.2 Test Suite 2: Interface Operational Down vs. Cable Severing
- **Objective:** Verify that when an interface goes down, the physical edge is marked `oper_status = "down"` but remains topologically anchored to its ports.
- **Test Procedure:**
  1. Interrogate live CHR on `ether1`.
  2. Mock NMS event `nms.interface.status_changed(iface="ether1", oper_status="down")`.
  3. Assert: Edge $E$ changes `oper_status` to `"down"`.
  4. Assert: `relationship_class` remains `"physical"`, `source_interface` remains `"ether1"`.
  5. Assert: Edge is rendered with red dashed line and warning badge, not deleted.

---

## 3. NMS and Discovery Boundary Separation Tests

The validation suite enforces strict architectural decoupling between Discovery, NMS, and Topology:

```
┌─────────────────────────┐      ┌────────────────────────┐      ┌─────────────────────────┐
│    DISCOVERY ENGINE     │      │       NMS ENGINE       │      │     TOPOLOGY ENGINE     │
│  - Discovers structure  │      │  - Observes condition  │      │  - Stores relationships │
│  - Establishes edges    │      │  - Tracks oper_status  │      │  - Manages history      │
│  - Assigns confidence   │      │  - Monitors metrics    │      │  - Computes snapshots   │
└────────────┬────────────┘      └───────────┬────────────┘      └────────────▲────────────┘
             │                               │                                │
             │ Physical / Layer 2 / L3 Edge  │ Oper_Status / Reachability     │
             └───────────────────────────────┼────────────────────────────────┘
                                             ▼
                                  [Boundary Guard Rules]
                                  NMS CANNOT mutate edge structure!
```

### 3.1 Test Suite 3: NMS Structural Invariance Assertion
- **Assertion:** An event originating from NMS (`nms.device.*`, `nms.interface.*`) can update `oper_status`, `reachability_status`, or `latency_ms`, but **CANNOT**:
  - Add a new `TopologyEdge`.
  - Delete an existing `TopologyEdge`.
  - Mutate `relationship_class` (e.g. change `physical` to `layer3`).
  - Mutate `source_interface` or `target_interface`.
  - Mutate `verification_status` (e.g. promote an unverified link to `confirmed`).

---

## 4. Evidence Explainability & Provenance Verification

Every edge must be fully explainable to human network operators:

### 4.1 Test Suite 4: Evidence Audit Trail Completeness
For every edge in the topology database, the API endpoint `GET /api/topology/edges/{edge_id}/evidence` must return:
1. **Provenance:** (`discovery_managed`, `user_managed`, `hybrid`).
2. **Observing Device:** Device ID and hostname that executed the telemetry command.
3. **Observation Timestamp:** Epoch timestamp of collection.
4. **Sanitization Proof:** Verified absence of raw passwords, private keys, or SNMP secrets (must contain `[REDACTED]`).
5. **Qualitative Confidence Rationale:** A human-readable text explanation (e.g. *"Bidirectional LLDP frame received on ether1 matching remote chassis MAC 08:00:27:CC:21:02 on ether2"*), not merely an opaque float score like `0.95`.

---

## 5. Live CHR Hardware Validation Protocol

All validation against the real lab MikroTik CHR at `10.66.38.30:22` must strictly follow the **Zero-Mutation Safety Protocol**:

1. **Pre-Test Export:**
   Execute `/export compact` via APCE and record SHA-256 hash $H_{pre}$.
2. **Read-Only Telemetry Execution:**
   Execute full discovery extraction commands (`/system identity print`, `/interface print detail`, `/ip address print detail`, `/ip route print detail`, `/ip neighbor print detail`, `/ip arp print detail`).
3. **Post-Test Export:**
   Execute `/export compact` via APCE and record SHA-256 hash $H_{post}$.
4. **Integrity Assertion:**
   Assert $H_{pre} == H_{post}$ (100% cryptographic identity match).
5. **No Persistent Credentials in Logs:**
   Inspect `topology.db` and log files to assert zero plaintext passwords or secrets were stored.
