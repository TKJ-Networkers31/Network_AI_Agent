# AIRA OS — Phase 4.6 Architecture Decision Resolution & Lab Audit Report

**Document Version:** 1.0.0  
**Phase:** Phase 4.6 (Route Analytics & Network Path Intelligence)  
**Work Package:** Pre-Implementation Review & Decision Resolution  
**Status:** COMPLETE WITH VALIDATION GAPS  
**Author:** Senior Network Automation Architect, MikroTik RouterOS Engineer, Software Reliability Engineer  
**Date:** November 2026  
**Final Acceptance Verdict Target:** `PHASE_4_6_DECISIONS_RESOLVED_WITH_VALIDATION_GAPS`  

---

## 1. Executive Summary & Purpose

Following the completion of the Phase 4.6 Architecture Audit (`PHASE_4_6_ARCHITECTURE_AUDIT_COMPLETE_WITH_GAPS`), this review was commissioned to:
1. Formally record the approval of foundational Decisions 1 through 6.
2. Provide technical analysis and definitive architectural resolutions for remaining Questions 7, 8, and 9 from Section 15 of `docs/NETWORKING_IV/PHASE_4_6_ROUTE_ANALYTICS_ARCHITECTURE.md`.
3. Conduct an empirical audit of the live lab device inventory, RouterOS hardware platforms, and connection status.
4. Establish non-negotiable boundaries preventing data duplication, database corruption, CPU starvation, and breaking changes.
5. Provide a rigorous, implementation-ready blueprint for Work Package 4.6.0.

This review was conducted under strict **Read-Only / Non-Mutating** constraints. Zero production code, zero database schemas, and zero RouterOS configurations were modified.

---

## 2. Comprehensive Resolution of Architecture Decisions (1–9)

### 2.1 Approved Foundation Decisions (Decisions 1–6)

The following six decisions were submitted during the audit and are formally incorporated as architectural mandates:

#### Decision 1: Real-Device Fixture Requirement (v6 and v7)
- **Mandate:** Real-device command outputs are strictly required for both RouterOS v6 and RouterOS v7.
- **Rule:** Synthetic fixtures are prohibited as evidence of parser acceptance.
- **Audit Findings & Lab Reality:**
  - An inspection of `InventoryStore` and `topology.db` confirmed two registered MikroTik devices:
    - `CHR` (10.66.38.30): RouterOS v7 (`os_version: 7.23.8 (long-term)`).
    - `R-1` (192.168.0.1): RouterOS v6 (`os_version: 6.49.18`, hardware model `RB952Ui-5ac2nD` / hAP ac lite).
  - Both devices are currently unreachable live on the active host network adapter (`10.26.213.223` Wi-Fi).
  - Consequently, live SSH capture is temporarily blocked, constituting an explicit **Validation Gap**. Pre-existing sanitized real captures or captures taken immediately upon lab network restoration must be placed under `AIRA_ECOSYSTEM/tests/fixtures/routes/`.

#### Decision 2: Read-Only Allowlist Expansion
- **Mandate:** The following read-only RouterOS command prefixes are approved for inclusion in `APPROVED_PRINT_PREFIXES` (`AIRA_ECOSYSTEM/core/network_intelligence/security.py`):
  1. `/routing route print` (v7 RIB detail and protocol attributes)
  2. `/routing ospf route print` (v6 OSPF routing table)
- **Security Audit:** Both commands are strictly observational `print` variants with no mutation capability. Neither command modifies router configuration, interface state, or forwarding tables.

#### Decision 3: Route Snapshot Storage Architecture
- **Mandate:** Option B is approved. Route snapshots shall be stored in a dedicated, additive, immutable table `route_snapshots` linked to `topology_snapshots.snapshot_id` via foreign key.
- **Integrity Rule:** Route snapshots will possess their own independent SHA-256 content checksum (`route_sha256_hash`), ensuring that routing table changes do not alter or invalidate the SHA-256 baseline of historical `topology_snapshots`.

#### Decision 4: Event Enum Separation (`RouteChangeType`)
- **Mandate:** Route changes shall not be merged into `TopologyChangeType`.
- **Architecture:** A dedicated enum `RouteChangeType` (`ROUTE_ADDED`, `ROUTE_REMOVED`, `ROUTE_METRIC_CHANGED`, `ROUTE_NEXT_HOP_CHANGED`, `ROUTE_STATUS_CHANGED`) and table `route_changes` shall track routing evolutions, preserving the purity and backwards compatibility of existing topology change logs.

#### Decision 5: IPv4 / IPv6 Scope
- **Mandate:** Phase 4.6 is IPv4-focused for initial parsing, LPM, and path analysis.
- **Forward Compatibility:** All data models (`NormalizedRoute`, `NextHopResolution`, `RoutePath`) must accept standard CIDR strings and use Python's `ipaddress` module without protocol hardcoding, ensuring effortless forward compatibility with IPv6 (`::/0`).

#### Decision 6: Inactive Route Handling in `mikrotik_diagnose_route`
- **Mandate:** The legacy bug in `mikrotik_diagnose_route` (Defect D6), where inactive/disabled routes were evaluated and returned as the best forwarding route, must be **fixed directly**.
- **Rationale:** Forwarding Information Base (FIB) path simulation must reflect reality. Presenting an inactive route as the active forwarding path is a safety and diagnostic liability. The response schema will remain backwards-compatible, but the selected best route will accurately reflect active FIB status.

---

### 2.2 Resolution of Remaining Architectural Decisions (Decisions 7–9)

#### Decision 7: Refactoring Double Collection in `AutomaticNetworkOrchestrator`
- **Audit Observation:** In `AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py` (lines 106–116):
  ```python
  # Step 2: Investigation runs multi-device collection internally
  incident = self.investigator.run_multi_device_investigation(...)

  # Step 3: AutoOrchestrator runs multi-device collection AGAIN across all targets
  orchestrator = MultiDeviceEvidenceOrchestrator(self.investigator.collector)
  mbundle = orchestrator.collect_multi_device_bundle(targets=targets)
  relationships = self.correlator.correlate_bundles(mbundle.device_bundles)
  ```
- **SRE & Performance Impact:**
  - Executing full SSH interrogation twice across every network device doubles connection setup overhead, doubles CPU load on low-power routers, and doubles execution time.
  - Crucially, it introduces **temporal race conditions**: routes or BFD sessions flapping between run 1 and run 2 produce mutually contradictory evidence between the `IncidentRecord` and the correlated relationships.
- **Definitive Architectural Resolution:**
  - **APPROVED FOR REFACTORING IN WP 4.6.6.**
  - `AutomaticNetworkOrchestrator` will collect `mbundle` **once** via `MultiDeviceEvidenceOrchestrator.collect_multi_device_bundle(targets=targets)`.
  - It will pass the pre-collected bundle into `investigator.run_multi_device_investigation(..., precollected_bundle=mbundle)`.
  - It will immediately pass the exact same `mbundle.device_bundles` into `correlator.correlate_bundles()`.
  - Backwards Compatibility: `investigator.run_multi_device_investigation` will make `precollected_bundle` optional (default `None`), collecting internally if not supplied.

#### Decision 8: Topology Persistence Boundary for Route-Derived Relationships
- **Architectural Question:** Should route-derived next-hop relationships (`routed_next_hop`) be written into `topology_edges` in `topology.db`, or should they remain dynamic analysis artifacts?
- **Analysis:**
  - Topology represents structural network adjacencies: physical cabling (`PHYSICAL_ADJACENCY`), broadcast domains / switching (`LAYER2_ADJACENCY`), and directly connected IP subnets (`LAYER3_REACHABILITY`).
  - Routing tables represent dynamic traffic policy. Next-hop associations change frequently (metric adjustments, failover, BGP flaps).
  - Writing transient next-hop dependencies into `topology_edges` would:
    1. Pollute core topology with ephemeral multigraph links.
    2. Trigger continuous `TopologyChange` records and snapshot diff noise.
    3. Confuse physical/L2 infrastructure troubleshooting with IP routing states.
- **Definitive Architectural Resolution:**
  - **HYBRID EPHEMERAL-FIRST POLICY:**
    1. **FIB Next-Hop and Route Paths are Ephemeral Overlays:**
       - Route-derived dependencies (`routed_next_hop`, recursive next-hop chains, end-to-end paths) are computed dynamically by `RoutePathAnalyzer` and returned via API responses as visual overlays.
       - They are **NEVER** persisted to `topology_edges` in `topology.db`.
    2. **Confirmed L3 Subnets Remain in TopologyEngine:**
       - Only directly connected subnets shared between two devices (verified via interface IP matching and ARP/ND) remain persisted under `LAYER3_REACHABILITY`.
       - When `RoutePathAnalyzer` resolves a next-hop that traverses a known `LAYER3_REACHABILITY` edge, it attaches the existing `edge_id_ref` to the path step, enabling seamless frontend highlight without duplicate edge creation.
    3. **Historical Route Persistence via Dedicated Route Snapshots:**
       - Historical routing state is preserved solely in the new `route_snapshots` table (Decision 3).

#### Decision 9: Routing Table Size Thresholds & Resource Boundedness
- **Architectural Question:** Confirm the 5,000-route design threshold and specify bounded processing for large tables.
- **SRE Reliability & Hardware Reality:**
  - AIRA OS is designed for on-premise execution (local server, VM, or engineer laptop with 4–8 GB RAM, CPU-only).
  - In SME, campus, and enterprise branch deployments, internal routing tables typically contain 20 to 2,000 routes.
  - However, enterprise border or ISP edge routers receiving full internet routing tables carry over 900,000 IPv4 routes.
  - Dumping 900,000 routes over SSH produces ~120 MB of raw text, requires 15–30 minutes of SSH streaming, spikes router CPU to 100%, and consumes 4–6 GB of Python memory during regex and JSON serialization, causing out-of-memory (OOM) crashes.
- **Definitive Architectural Resolution:**
  - **THREE-TIER BOUNDED PROCESSING ARCHITECTURE:**
    1. **Tier 1 (Normal Operations: $\le$ 5,000 routes per device):**
       - Full table ingestion via `/ip route print detail`.
       - In-memory Longest Prefix Match (LPM) Patricia trie built per device.
       - Sub-millisecond next-hop resolution and full path tracing.
    2. **Tier 2 (Large Table Operations: 5,001 to 20,000 routes per device):**
       - Table ingested with explicit warning: `ROUTING_TABLE_LARGE_WARNING`.
       - Query execution ceiling: 5.0 seconds per path query.
       - Route snapshot storage retains full hash, but payload stores top 5,000 routes + distribution statistics.
    3. **Tier 3 (Very Large / Full BGP Operations: > 20,000 routes per device):**
       - **Full table dump is strictly prohibited.**
       - Preflight check queries route count via `/ip route print count-only`.
       - Collector shifts to **Targeted Prefix Ingestion**: queries routes on-demand using `/ip route print detail where dst-address in <target_prefix>` or by specific protocol/interface.
       - API and UI set diagnostic flag `PARTIAL_ROUTE_TABLE_INGESTED` with honest user feedback.
    4. **Safety & Timeout Limits:**
       - Memory Cap: Parser and route index operations capped at 256 MB working set.
       - Command Timeout: 15.0 seconds hard timeout per CLI command.

---

## 3. Lab Device & Inventory Audit Findings

An empirical audit of the lab database, inventory store, and network interfaces was conducted:

### 3.1 Registered Inventory Status
```
+---------------+---------------+--------------------+------------------+---------------------+
| Device ID     | Display Name  | Hardware Model     | RouterOS Version | Management IP       |
+---------------+---------------+--------------------+------------------+---------------------+
| dev_chr       | CHR           | CHR VirtualBox     | 7.23.8           | 10.66.38.30:22      |
| dev_r-1       | R-1           | RB952Ui-5ac2nD     | 6.49.18          | 192.168.0.1:22      |
| dev_core-1    | Core-1        | (Manual node)      | Unspecified      | 10.0.0.1:22         |
| dev_isp-1     | ISP-1         | (Manual WAN)       | Unspecified      | 203.0.113.1:22      |
+---------------+---------------+--------------------+------------------+---------------------+
```

### 3.2 Network Reachability Audit
- **Host Network Environment:** Active primary adapter is `Wi-Fi` on subnet `10.26.213.223/24`.
- **CHR (10.66.38.30):** ICMP Echo returned `False`. Target is currently unreachable (host is off the 10.66.38.0/24 lab bridge).
- **R-1 (192.168.0.1):** ICMP Echo returned `False`. Target is currently powered off or off-subnet.
- **NMS Health State:** Device `node_r-1` is recorded as `DOWN` with reason `"ICMP ping timeout (2.0s)"`. Device `node_chr` is recorded with `nms_status: "UP"`, `observation_freshness: "expired"`.

### 3.3 Acceptance Rule & Validation Gap Classification
- Under Decision 1, real-device fixtures are mandatory.
- Because live physical devices cannot be polled over SSH on the current host network subnet, fresh capture commands cannot be executed dynamically in this turn.
- In accordance with SRE integrity standards, this condition is formally reported as a **VALIDATION GAP**.
- Synthetic fixtures will NOT be used to falsely claim real-device acceptance.
- Sanitized real-device fixtures will be imported to `tests/fixtures/routes/` as the first deliverable of WP 4.6.0.

---

## 4. Live Database Integrity Audit

The live production SQLite database `AIRA_ECOSYSTEM/database/topology.db` was audited against the accepted baseline:

- **Database Snapshot Count:** Exactly 45 snapshots.
- **Database Change Log Count:** Exactly 72 changes.
- **Database Pragma Mode:** WAL (Write-Ahead Logging), `busy_timeout = 5000`.
- **Snapshot Manifest Baseline:** `AIRA_ECOSYSTEM/database/snapshot_baseline_manifest.json`.
- **SHA-256 Verification:**
  - Evaluated SHA-256 across all 45 snapshots in chronological order:
    $$\text{Calculated Hash} = \text{9729b243a47b3e8388bbe67dbcb78db002ffbe3d70a1736318bbbdaa879f0fba}$$
  - Baseline Manifest Hash:
    $$\text{Baseline Hash} = \text{9729b243a47b3e8388bbe67dbcb78db002ffbe3d70a1736318bbbdaa879f0fba}$$
  - **Verdict:** **100% BIT-PERFECT MATCH. ZERO DATABASE CORRUPTION OR DRIFT.**

---

## 5. Work Package 4.6.0 Readiness Assessment

The specification for WP 4.6.0 (`docs/NETWORKING_IV/PHASE_4_6_0_REAL_FIXTURE_AND_UNIFIED_PARSER_SPEC.md`) is complete:
- **Parser Architecture:** `UnifiedRouteParser` handles detail folding, columnar alignment, compact flags, and ECMP.
- **Defects Addressed:** Comprehensive resolutions specified for D1 through D10.
- **Data Model:** Canonical `NormalizedRoute` dataclass fully defined with legacy adapter shims.
- **Test Suite:** 15 required unit tests specified, verifying zero mutation, performance $< 350\text{ ms}$, and defect remediation.

---

## 6. Final Acceptance Verdict

Based on the complete resolution of Decisions 1 through 9, the rigorous specification of WP 4.6.0, the bit-perfect verification of the historical database, and the empirical inspection of lab device reachability:

```
========================================================================================
FINAL ACCEPTANCE VERDICT:
PHASE_4_6_DECISIONS_RESOLVED_WITH_VALIDATION_GAPS
========================================================================================
```

### Next Steps for Implementation Approval
1. User reviews this Decision Resolution Report and the WP 4.6.0 Specification.
2. Upon user approval, restore lab network connectivity or load archived real captures to populate `AIRA_ECOSYSTEM/tests/fixtures/routes/`.
3. Proceed to implement WP 4.6.0 (`UnifiedRouteParser` and `test_unified_route_parser.py`).
