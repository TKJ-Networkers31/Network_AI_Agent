# AIRA OS — NETWORKING IV IMPLEMENTATION ROADMAP
## Phased Implementation Sequence, Milestones & Acceptance Criteria

**Document ID:** `AIRA-NET-IV-ROADMAP-001`  
**Date:** 2026-10-31 (Revised)  
**Project:** AIRA OS — Phase Networking IV  
**Status:** IMPLEMENTATION_ROADMAP_SPECIFICATION  

---

## 1. Roadmap Architecture & Safety Principles

The implementation of **Phase Networking IV: Automatic Topology Discovery & Interactive Visualization** is organized into six sequential, test-driven phases.

Each phase produces testable deliverables, preserves backward compatibility with existing systems, and strictly enforces the five core architectural decisions:
1. **Explicit Separation of Relationship Types** (`physical`, `layer2`, `layer3`, `logical`).
2. **Strengthened TopologyEdge Model** (multi-edge, directional, typed, anti-conflation).
3. **Full Evidence Explainability** (provenance, timestamps, sanitization, qualitative rationale).
4. **Snapshot & Historical Integrity** (5 lifecycle failure states, anti-flapping).
5. **Decoupled Responsibilities** (Discovery = structure, NMS = operational condition, Topology = graph storage).

### Engineering Rules:
1. **Zero Greenfield Disruption:** Existing tables (`topology_nodes`, `topology_links`) and APIs remain functional; new multi-edge tables are added via non-destructive migrations.
2. **Read-Only Verification:** Zero configuration pushes to network devices.
3. **Continuous Test Gate:** Every phase requires passing both unit test suites and live single-device verification on `CHR` (`10.66.38.30`).

---

## 2. Phased Implementation Breakdown

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NETWORKING IV PHASING                           │
├─────────┬───────────────────────────────────────────┬──────────────────┤
│ Phase   │ Focus Area                                │ Complexity       │
├─────────┼───────────────────────────────────────────┼──────────────────┤
│ **4.1** │ Multi-Layer Graph Schema & Data Models    │ Moderate         │
│ **4.2** │ Discovery Pipeline & Evidence Correlator  │ High             │
│ **4.3** │ Event-Driven NMS State Synchronization    │ Moderate         │
│ **4.4** │ Topology-Aware Network Intelligence       │ High             │
│ **4.5** │ Frontend Canvas & Evidence Inspector      │ Moderate         │
│ **4.6** │ Full Live Acceptance & Regression Audit   │ High (Strict)    │
└─────────┴───────────────────────────────────────────┴──────────────────┘
```

---

### Phase 4.1: Multi-Layer Graph Schema & Data Models
- **Focus:**
  - Create database migration in `core/topology_engine.py` for new tables: `topology_edges`, `topology_edge_evidence`, `topology_snapshots`, `topology_changes`.
  - Implement typed dataclasses in `core/topology_models.py` (`TopologyEdge`, `EdgeEvidence`, `DiscoveryRun`, `TopologySnapshot`, `TopologyChange`).
  - Implement formal relationship enums per `TOPOLOGY_RELATIONSHIP_SEMANTICS.md` (`relationship_class`: `physical`, `layer2`, `layer3`, `logical`).
  - Implement bidirectional data adapters so legacy endpoints reading `topology_links` can seamlessly query the upgraded graph store.
- **Deliverables:**
  - `AIRA_ECOSYSTEM/core/topology_models.py` (updated).
  - `AIRA_ECOSYSTEM/core/topology_engine.py` (migration routines).
  - `AIRA_ECOSYSTEM/tests/test_topology_graph_models.py`.
- **Acceptance Criteria:**
  - Migration runs idempotently on existing `topology.db` without data loss.
  - Multi-edge support verified: can store parallel physical, VLAN trunk, routed, and tunnel edges between the same two nodes.
  - Unit test suite: 100% pass.

---

### Phase 4.2: Evidence-Based Discovery Pipeline & Evidence Correlator
- **Focus:**
  - Upgrade `TopologyDiscoveryMixin` to populate `topology_edges` and `topology_edge_evidence`.
  - Integrate `CrossDeviceEvidenceCorrelator` into the discovery reconciliation loop.
  - Implement the 4-tier confidence scoring formula ($S(e)$) and mandatory qualitative rationales per `TOPOLOGY_EVIDENCE_CONFIDENCE_MODEL.md`.
  - Implement boundary interface detection and ISP upstream scope isolation.
  - Enforce epistemic prohibition: shared IP subnets and single ARP entries strictly barred from physical adjacency.
- **Deliverables:**
  - `AIRA_ECOSYSTEM/core/topology_discovery.py` (updated).
  - `AIRA_ECOSYSTEM/core/network_intelligence/correlation.py` (hooked into topology engine).
  - `AIRA_ECOSYSTEM/tests/test_topology_discovery_v4.py`.
- **Acceptance Criteria:**
  - Live discovery against `CHR` (`10.66.38.30`) successfully records node, edges, and evidence excerpts.
  - Subnet-only relationships are strictly classified as Tier 3 (`INFERRED`) Layer 3 reachability.
  - Unit tests verify boundary policy stops traversal at ISP interfaces.

---

### Phase 4.3: Event-Driven NMS State Synchronization
- **Focus:**
  - Implement EventBus listener `handle_nms_event()` in `core/topology_engine.py`.
  - Wire NMS events (`nms.interface.status_changed`, `nms.device.status_changed`) to real-time `topology_edges.oper_status` updates per `TOPOLOGY_NMS_INTEGRATION.md`.
  - Enforce NMS Structural Invariance: NMS events update operational status, but cannot mutate physical adjacency or delete edges.
  - Implement the in-memory 60-second Stale Observation Decayer ticker.
  - Expose WebSocket delta frames for live UI updates.
- **Deliverables:**
  - `AIRA_ECOSYSTEM/core/topology_engine.py` (NMS listener).
  - `AIRA_ECOSYSTEM/core/nms_engine.py` (event emission hooks).
  - `AIRA_ECOSYSTEM/tests/test_topology_nms_sync.py`.
- **Acceptance Criteria:**
  - Emitting an interface DOWN event updates the corresponding edge `oper_status` within $< 100\text{ ms}$ while preserving the edge in the graph.
  - Zero redundant SSH sessions spawned.
  - Stale decayer marks unobserved edges as `expired` without network calls.

---

### Phase 4.4: Topology-Aware Network Intelligence & Upstream Traversal
- **Focus:**
  - Implement `TopologyGraphContext` provider in `core/network_intelligence/investigator.py` per `TOPOLOGY_INTELLIGENCE_INTEGRATION.md`.
  - Implement Upstream Dependency Traversal in `AutomaticNetworkOrchestrator`.
  - Update `auto_diagnose_network` tool to project incident symptoms onto the topology graph.
  - Implement causal ordering rules (distinguishing upstream root cause from downstream symptom).
- **Deliverables:**
  - `AIRA_ECOSYSTEM/core/network_intelligence/investigator.py` (updated).
  - `AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py` (updated).
  - `AIRA_ECOSYSTEM/tests/test_topology_aware_investigation.py`.
- **Acceptance Criteria:**
  - Diagnosing an upstream failure correctly identifies next-hop gateway node and classifies downstream router packet loss as a symptom.
  - Hypotheses include the full topological path and qualitative evidence rationale.

---

### Phase 4.5: Frontend Canvas Enhancements & Evidence Inspector
- **Focus:**
  - Create `TopologyEdgeInspector.jsx` to display edge evidence history, confidence scores, qualitative rationales, and raw CLI snippets per `TOPOLOGY_VISUALIZATION_DESIGN.md`.
  - Update `TopologyPage.jsx` to render curved Bezier paths for parallel edges and accessible confidence pills.
  - Implement multi-layer graph view switcher (`Physical`, `Layer 2 Fabric`, `Layer 3 Routing`, `Overlays`).
  - Create `TopologyTimeline.jsx` for scrubbing historical snapshots with visual diff overlays.
  - Implement deep-link navigation from `DevicesPage.jsx` and `NetworkIntelligencePage.jsx`.
- **Deliverables:**
  - `AIRA_ECOSYSTEM/app/frontend/src/components/topology/TopologyEdgeInspector.jsx`.
  - `AIRA_ECOSYSTEM/app/frontend/src/components/topology/TopologyTimeline.jsx`.
  - `AIRA_ECOSYSTEM/app/frontend/src/pages/TopologyPage.jsx` (updated).
- **Acceptance Criteria:**
  - Clicking any link line opens the Edge Evidence Inspector.
  - Parallel links between two nodes curve neatly without visual overlap.
  - Frontend production build (`vite build`) completes cleanly with zero errors.

---

### Phase 4.6: End-to-End Live Acceptance & Regression Audit
- **Focus:**
  - Execute full live verification against the real lab CHR at `10.66.38.30:22`.
  - Execute validation suites defined in `TOPOLOGY_VALIDATION_STRATEGY.md`.
  - Verify zero configuration changes on the router via pre- and post-test SHA-256 export snapshots.
  - Run the entire backend regression suite (998+ tests) and frontend test suite (247+ tests).
  - Author `docs/NETWORKING_IV/NETWORKING_IV_ACCEPTANCE_REPORT.md`.
- **Acceptance Criteria:**
  - Pre- and post-test router configuration hashes match 100%.
  - Zero secrets in logs or git working tree.
  - All test suites pass 100%.
