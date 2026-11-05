# AIRA OS — Phase 4.6 Route Analytics: Implementation Plan

**Date:** 2026-11-03
**Status:** Architecture Decisions 1-9 RESOLVED. WP 4.6.0 Specification Authoring COMPLETE (`docs/NETWORKING_IV/PHASE_4_6_0_REAL_FIXTURE_AND_UNIFIED_PARSER_SPEC.md`). Lab Validation Gap documented in `docs/STABILIZATION/PHASE_4_6_DECISION_RESOLUTION_REPORT.md`. Implementation readiness gated on fixture import.
**Ordering:** dependency-ordered. A work package (WP) may start only when its dependencies are accepted.

---

## Global constraints (apply to every WP)

- Read-only RouterOS access only, through `EvidenceCollector` → `validate_readonly_command` → ConnectionManager.
- No new graph library. No duplicate collector, parser, investigator, or orchestrator.
- Existing 45 snapshots and 72 changes stay bit-identical. Verify with `AIRA_ECOSYSTEM/database/snapshot_baseline_manifest.json` at the end of every WP.
- Schema changes are additive only, and only after approval (Q3/Q4).
- Each WP ends with: the full backend suite, `test_routeros_command_hardening.py`, frontend tests and build, `git diff --check`, and a secret scan.
- No commit, push, stash, reset, or checkout. Never `git add .`.

---

## WP 4.6.0 — Fixtures, Parser Convergence & Defect Remediation

**Why first:** every later WP consumes parsed routes. The audit demonstrated wrong output from both existing parsers (D1–D5) and from LPM (D6–D8).

| Item | Detail |
|---|---|
| **Scope** | (1) Capture sanitized v6 and v7 fixtures: `/ip route print detail` (active, inactive, disabled, recursive, blackhole, ECMP, multiple tables), `/ip route print` tabular, routing rules, v7 `/routing table print`. (2) One route parser built on `_parse_kv_blocks` plus a tabular fallback, with version-specific flag legends and no case-folding. (3) Fix D1–D8 and D10. (4) Adapters so that `ParsedRoute` and the topology dict are produced from the unified parser. |
| **Dependencies** | Decisions 1 & 6 resolved. Gated on importing sanitized real fixtures per WP 4.6.0 Spec. |
| **Files likely affected** | `core/topology_parsers.py` (route parser home), `agents/akane/reasoning_engine.py` (`parse_routeros_routes` becomes an adapter; LPM fixes), `core/network_intelligence/evidence.py` (version probe, D10), `tests/fixtures/ros_v6/*`, `tests/fixtures/ros_v7/*` |
| **New APIs** | None |
| **Data model changes** | None (adapters keep the existing shapes) |
| **Unit tests** | Per fixture: route count, flags, active/disabled/dynamic, distance on wrapped lines, gateway vs interface split, protocol letter. Explicit regressions for D1–D8 and D10. LPM: "no active route gives `matched=False`"; recursive via default route; table isolation. |
| **Integration tests** | Discovery on the v6 fixture detects the default route correctly. `checks.py`, simulator, and MCP `mikrotik_diagnose_route` contract tests (key set unchanged; values corrected). |
| **Acceptance criteria** | Both call sites use one parser. All D-defects have a failing-then-passing test. No existing test regresses, or every changed expectation is listed and justified under Q6. |
| **Risks** | Behaviour change for consumers (R6); fixture availability (R2) |

---

## WP 4.6.1 — Route Intelligence Data Model & Collection

| Item | Detail |
|---|---|
| **Scope** | Extend `NormalizedRoute` (architecture §2.2): safe `None` defaults, `NextHop`, the state group, namespaced `ros.*`, `ospf.*`, `bgp.*`, provenance fields, `fib_state`. Add `RouteCapabilityReport`. Add route requirement sets to `INCIDENT_EVIDENCE_REQUIREMENTS`. Add the TTL cache keyed by (device, observation_type). Add the large-table guard with targeted lookup mode. |
| **Dependencies** | WP 4.6.0; Decision 2 (Allowlist expansion approved); Decision 5 (IPv4 forward-compatible model); Decision 9 (5,000 threshold) |
| **Files likely affected** | `core/network_intelligence/network_models.py`, `core/network_intelligence/evidence.py` (`_normalize_observation` emits extended records while keeping the legacy `routes` dict), `core/network_intelligence/security.py` + `tests/test_routeros_command_hardening.py` (only if Q2 is approved) |
| **New APIs** | None yet (internal) |
| **Data model changes** | Dataclass extension only. **No DB schema change.** `to_dict()` stays backward compatible. |
| **Unit tests** | Serialization round trip; unknown fields stay `None` (not `static`, `1`, or `True`); provenance always present; capability report distinguishes `unsupported`, `not_collected`, and `failed`. |
| **Integration tests** | `MultiDeviceEvidenceOrchestrator` on mocked v6 and v7 devices yields extended records. Partial device failure appears in the capability report. Measure parse time and memory (record as measurements; no targets claimed in advance). |
| **Acceptance criteria** | Existing consumers unchanged. Measurements recorded. Allowlist changes (if any) have hardening tests. |
| **Risks** | Performance on large tables (R5); allowlist expansion review |

---

## WP 4.6.2 — Next-Hop Resolution Engine

| Item | Detail |
|---|---|
| **Scope** | Implement architecture §4: seven statuses, depth limit (default 4), loop detection, ECMP branch cap of 8, a contradiction against device-reported status, out-of-scope handling, rule-based confidence, and the IP-ownership index. |
| **Dependencies** | WP 4.6.1 |
| **Files likely affected** | New module under `core/network_intelligence/` (for example `route_resolution.py`). It is the single home for resolution logic. `reasoning_engine.py` delegates its recursive hint to it. |
| **New APIs** | None yet |
| **Data model changes** | New in-memory result dataclasses only |
| **Unit tests** | One test per status. Recursive chain of depth 2, 3, 4 and above the limit. Self-resolution excluded. Two-route loop. ECMP gives AMBIGUOUS. Gateway owned by an uncollected device gives OUT_OF_SCOPE. Down interface gives UNREACHABLE. Blackhole gives UNREACHABLE. A disagreement with `gateway-status` is recorded as a contradiction. Confidence capped on partial collection. |
| **Integration tests** | Resolution over multi-device fixtures through `MultiDeviceEvidenceOrchestrator` mocks |
| **Acceptance criteria** | No recursion without a bound (property test with random route tables). A recursive route is never reported resolved unless the chain ends at an up connected interface. |
| **Risks** | Unusual RouterOS `scope`/`target-scope` semantics (record them; do not emulate them in v1 unless confirmed with fixtures) |

---

## WP 4.6.3 — Route Path Analysis & Topology Correlation

| Item | Detail |
|---|---|
| **Scope** | Implement architecture §5 and §7: table selection with rule awareness (INDETERMINATE when undeterminable), LPM on active routes, multi-hop traversal across collected devices only, `segment_kind` classification using Phase 4.5 edges and evidence, optional reverse path and asymmetry. Fix D9 in `_correlate_routed_nexthop` (multi-route; subnet-aware; recursive gateways never produce edges). |
| **Dependencies** | WP 4.6.2; Decision 8 resolved (Hybrid Ephemeral-First: route paths are dynamic overlays; never persisted to topology_edges) |
| **Files likely affected** | New `core/network_intelligence/route_path.py`, `core/network_intelligence/correlation.py`, read-only use of `TopologyEngine` edge and evidence queries. `TopologyEngine.find_path` is **not** changed. It stays the topology-only path. |
| **New APIs** | Internal service interface only |
| **Data model changes** | None persisted. If Q8 = persist, edges use the existing `layer3` class with subtype `routed_next_hop` (no schema change). |
| **Unit tests** | COMPLETE 3-hop path. Next hop outside scope gives INCOMPLETE with an UNKNOWN_SEGMENT. Loop gives LOOP_DETECTED. No active route gives NO_ROUTE. Policy rule present gives INDETERMINATE. Shared subnet without an edge gives INFERRED_PATH. Physical edge with evidence gives CONFIRMED_ADJACENCY. Asymmetric fixture detected. Never creates `physical`/`layer2` edges (assert edge counts by class unchanged). |
| **Integration tests** | End to end on mocked 3–5 device topologies. Performance measured for 10 devices (recorded, not assumed). |
| **Acceptance criteria** | No invented devices. No COMPLETE status with any unresolved hop. `assumptions` always state that firewall, NAT, and ARP were not evaluated. |
| **Risks** | Device-to-node ID mapping gaps between the registry and topology (report unmapped nodes; do not guess) |

---

## WP 4.6.4 — Multi-Protocol Correlation (OSPF / BGP)

*Can start after WP 4.6.1, in parallel with WP 4.6.2/4.6.3.*

| Item | Detail |
|---|---|
| **Scope** | Parse protocol attributes where observable (architecture §6): OSPF interface cost and area, route type and metric; BGP route attributes; v7 session state via `/routing bgp session print`. Correlate OSPF neighbor address with route gateway. Separate `bgp.best` from `rib_active`. Report "observed difference" for prefix counts without attributing it to policy. |
| **Dependencies** | WP 4.6.1; Q2 (allowlist); captured protocol fixtures (Q1) |
| **Files likely affected** | `core/network_intelligence/evidence.py` (`_parse_ospf_neighbors`, `_parse_bgp_peers` move to the unified parser module), `COMMAND_MAP_V6`/`V7` (optional protocol entries), `checks.py` (`check_ospf_adjacency`, `check_bgp_prefixes_missing` consume the new fields) |
| **New APIs** | None |
| **Data model changes** | Namespaced `ospf.*` and `bgp.*` fields (dataclass only) |
| **Unit tests** | Attribute extraction per version. Missing attribute stays `None` (never inferred). BGP-best but inactive is shown as two facts. Secret masking on BGP peer config output. |
| **Integration tests** | Investigator OSPF/BGP incident types use the new fields without regressing existing checks |
| **Acceptance criteria** | No attribute appears that was not printed by the device |
| **Risks** | Field-name differences across RouterOS minor versions (fixtures per version) |

---

## WP 4.6.5 — Historical Route Analytics

| Item | Detail |
|---|---|
| **Scope** | Route snapshot capture per the Q3 decision; route diff with the `(device, table, dst, protocol)` key; set-based next-hop comparison; ambiguity handling; incomplete-capture suppression; path comparison between two snapshots. |
| **Dependencies** | WP 4.6.3; Decisions 3 & 4 resolved (Dedicated immutable `route_snapshots` table and `RouteChangeType` enum approved) |
| **Files likely affected** | `core/topology_db.py` (additive table/triggers if Option B), `core/topology_engine.py` (capture and compare entry points following the existing snapshot pattern), `core/topology_models.py` (change-type enum if Q4 = extend) |
| **New APIs** | `GET /api/topology/route-snapshots`, `GET /api/topology/route-snapshots/compare`, `GET /api/topology/route-snapshots/{id}`, `POST /api/topology/route-snapshots` (admin only, `require_topology_admin`). Static routes are declared before parameterized ones, as in 4.4B. |
| **Data model changes** | Additive only, as approved |
| **Unit tests** | Deterministic SHA-256; immutability triggers; each `ROUTE_*` change type; ECMP reorder is not a change; partial capture yields INDETERMINATE, never REMOVED; old snapshots report `routes: not_captured`. |
| **Integration tests** | Concurrent capture with NMS events (reuse the SQLite concurrency harness); restart persistence; live manifest of the 45 existing snapshots unchanged. |
| **Acceptance criteria** | Zero live router queries during historical comparison (assert ConnectionManager is not called). Existing snapshot hashes unchanged. |
| **Risks** | Snapshot size (R5); migration approval (R7) |

---

## WP 4.6.6 — Investigator Integration, API & Frontend

| Item | Detail |
|---|---|
| **Scope** | Add route incident types and requirement sets to `NetworkInvestigator`. Single-pass collection for route flows (Decision 7 approved: refactor `auto_orchestrator.py` to pass precollected bundle to `investigator`). Expose HTTP endpoints. Re-point MCP `mikrotik_diagnose_route` to the new engine behind the contract chosen in Q6. Build the frontend views in architecture §10 inside existing pages. |
| **Dependencies** | WP 4.6.3, 4.6.4, 4.6.5 |
| **Files likely affected** | `core/network_intelligence/investigator.py`, `core/network_intelligence/models.py` (enums, request models), `api/routers/network_intelligence.py`, `mcp_servers/network/server.py`, `app/frontend/src/api.js`, `pages/NetworkIntelligencePage.jsx`, `pages/TopologyPage.jsx`, `components/topology/TopologyEdgeInspector.jsx` pattern for a route inspector, `components/topology/topologyConstants.js` (segment-kind visuals), `TopologyHistoryModal.jsx` / `SnapshotDiffViewer.jsx` |
| **New APIs** | `GET /api/intelligence/routes?device=&table=&protocol=&state=` (paged), `GET /api/intelligence/routes/{device}/lookup?ip=` (LPM + resolution), `POST /api/intelligence/route-path` (source, destination, options). All read-only; inputs validated as IP/CIDR and known device IDs. |
| **Data model changes** | Pydantic request/response models only |
| **Unit tests** | Endpoint validation (bad IP, unknown device, oversized page); response schemas; the "insufficient evidence" path produces no hypothesis without evidence refs. Frontend: segment-kind rendering, observed/inferred/unresolved/incomplete/historical distinctions, UNKNOWN_SEGMENT renders no node, polling suppressed in historical mode. |
| **Integration tests** | FastAPI TestClient end to end on mocked devices; MCP contract test; `npm test` and `npm run build`. |
| **Acceptance criteria** | No mutation path reachable from route features (assert planner not called). Every UI path has an explanation panel. Historical views make no live calls. |
| **Risks** | UI scope creep (keep to the six views); contract change for MCP consumers (Q6) |

---

## Approval gates & Decision Status

| Gate | Target WP | Governing Decision | Resolution Status | Technical Architecture Summary |
|---|---|---|---|---|
| **G0** | WP 4.6.0 | Decisions 1 & 6 | **RESOLVED WITH GAP** | Real fixtures required (v6 & v7). Bug D6 in `mikrotik_diagnose_route` fixed directly. Physical lab is off-subnet (Validation Gap). Import sanitized real captures. |
| **G1** | WP 4.6.1 / 4.6.4 | Decisions 2, 5, 9 | **RESOLVED** | Read-only allowlist includes `/routing route print` and `/routing ospf route print`. IPv4 focus with IPv6-forward models. 5,000 route LPM threshold with 3-tier bounds. |
| **G2** | WP 4.6.3 | Decision 8 | **RESOLVED** | Hybrid Ephemeral-First policy: `routed_next_hop` and route paths are ephemeral overlays; never written to `topology_edges`. Only confirmed direct L3 subnets persisted. |
| **G3** | WP 4.6.5 | Decisions 3 & 4 | **RESOLVED** | Dedicated immutable `route_snapshots` table with independent SHA-256 and link to `topology_snapshots`. Independent `RouteChangeType` enum and `route_changes` table. |
| **G4** | WP 4.6.6 | Decision 7 | **RESOLVED** | Double collection in `AutomaticNetworkOrchestrator` eliminated. Precollected `MultiDeviceEvidenceBundle` reused across investigation and correlation. |
