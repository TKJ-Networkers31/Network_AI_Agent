# AIRA OS — NETWORK INTELLIGENCE API & PERSISTENCE SPECIFICATION
## REST Endpoints, Security Controls & SQLite WAL Schema (WP 6.0 / WP 6.15)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. API Design Principles

All Networking VI endpoints are mounted under `/api/intelligence` in `AIRA_ECOSYSTEM/api/routers/network_intelligence.py` (preserving 100% of existing Networking III/IV endpoints such as `/incidents`, `/investigate/device/{device_id}`, `/auto-diagnose`, `/plans`, and `/metrics`).

Every Networking VI endpoint guarantees:
1. **Strict Input Validation:** Pydantic v2 request models with length caps, IP/CIDR validation, bounded `limit` (`1..200`), and bounded `time_window_sec` (`60..604800`).
2. **Authorization Enforcement:** State-triggering or live-collection POST endpoints enforce `Depends(require_topology_admin)` (`X-AIRA-Admin-Token` when `AIRA_ADMIN_TOKEN` is configured, loopback-safe in local dev).
3. **Bounded Execution & Cooperative Cancellation:** Every deep investigation registers a cancellable token (`POST /api/intelligence/investigations/{investigation_id}/cancel`) and enforces hard `asyncio.wait_for` execution budgets (default `15s` deterministic, `25s` with optional LLM explanation).
4. **Secret Sanitization & Evidence Traceability:** All payloads pass through `redact_sensitive_values`; every response includes `correlation_id`, `freshness_summary`, `completeness`, `evidence_refs`, and explicit `uncertainty_notes`.

---

## 2. Endpoint Catalogue (`/api/intelligence/*`)

| Method & Path | Purpose | Auth | Live SSH Default |
|---|---|---|---|
| `GET /api/intelligence/overview` | Network-wide condition, multi-dimensional health summary, device health distribution, active incidents, critical dependencies, major anomalies, recent snapshot changes, and evidence freshness. | Read | `False` (uses cached NMS/Topology/Route stores) |
| `POST /api/intelligence/investigate` | Natural-language & structured network investigation entry point (intent classification $\to$ plan $\to$ evidence bundle $\to$ graph/path/protocol/correlation/RCA $\to$ optional grounded LLM summary + scoped follow-up `context_id`). | Admin | Configurable (`allow_live_collection: bool = False`) |
| `POST /api/intelligence/investigations/{id}/cancel` | Cooperatively cancels an in-flight investigation. | Admin | `False` |
| `GET /api/intelligence/investigations` | Paginated history of stored Networking VI investigations. | Read | `False` |
| `GET /api/intelligence/investigations/{id}` | Retrieve full stored investigation report & evidence references. | Read | `False` |
| `GET /api/intelligence/graph` | Multi-layer `NetworkKnowledgeGraph` projection with optional layer/entity filtering and consistency validation report, or bounded graph query execution (`connected`, `upstream`, `downstream`, `vlan_carriers`, `next_hop_routes`, `protocol_peers`, `alternate_paths`). | Read | `False` |
| `GET /api/intelligence/devices/{device_id}` | Deep single-device intelligence profile: resolved identity, multi-dimensional health, interfaces, routes, protocol peers, upstream/downstream blast radius, anomalies, and evidence freshness. | Read | `False` |
| `GET /api/intelligence/interfaces/{interface_id}` | Interface intelligence (`<device_id>:<iface_name>` or URL-safe key): oper/admin state, traffic rate & baseline comparison, error/drop acceleration, L2/VLAN/bridge membership, neighbor/peer attachments. | Read | `False` |
| `GET /api/intelligence/routes` | Normalized multi-device routing intelligence summary, protocol breakdown, unresolved/inactive/blackhole routes, and route dependencies. | Read | `False` |
| `POST /api/intelligence/paths` | Multi-mode `NetworkPathIntelligenceEngine` analysis (`RIB_INFERRED` / `FIB_CONFIRMED` / `OBSERVED_FORWARDING` / `PARTIAL_PATH` / `UNKNOWN_PATH`) and optional path comparison across sources, destinations, VRFs, tables, or snapshots. | Admin | `False` |
| `GET /api/intelligence/correlations` | Multi-device correlated observation groups across active incidents, anomalies, topology, and routing dependencies. | Read | `False` |
| `POST /api/intelligence/rca` | Deterministic 14-step Root Cause Analysis for an incident, target device/subnet, or time window, returning ranked hypotheses, confidence factor breakdowns, contradictions, and human-review remediation guidance. | Admin | `False` |
| `GET /api/intelligence/health` | Full 8-dimension network health breakdown (`overall`, `device`, `interface`, `routing`, `protocol`, `wan`, `dependency`, `telemetry_confidence`). | Read | `False` |
| `GET /api/intelligence/anomalies` | Active & historical baseline deviations, error accelerations, and protocol instabilities alongside baseline metadata. | Read | `False` |
| `POST /api/intelligence/impact` | `OBSERVED_IMPACT` vs `POTENTIAL_IMPACT` dependency & redundancy analysis for a device, interface, VLAN, route, WAN link, or protocol peer. | Admin | `False` |
| `POST /api/intelligence/simulations` | Non-destructive in-memory what-if failure simulation (`device_down`, `wan_route_loss`, `ospf_neighbor_loss`, `bgp_peer_withdrawal`, `vlan_trunk_loss`, `tunnel_down`). Explicitly tagged `is_simulation: true`. | Admin | `False` |
| `GET /api/intelligence/history` | Historical intelligence comparison across topology snapshots, route snapshots, metric trends, before/after incident timelines, and recurring fault patterns. | Read | `False` |
| `GET /api/intelligence/evidence/{evidence_id}` | Inspect a specific `CanonicalEvidenceRecord` or persisted `EvidenceItem` with sanitized payload, provenance, parser version, freshness, and limitations. | Read | `False` |

---

## 3. Persistence Strategy (`database/network_intelligence.db`)

### 3.1 Reuse First, Minimal New Tables
- **Untouched Authoritative Stores in `topology.db`:**
  - `topology_nodes`, `topology_edges`, `topology_snapshots`, `topology_changes`
  - `route_snapshots`, `route_changes`
  - `nms_device_profiles`, `nms_device_metrics`, `nms_interface_metrics`, `nms_raw_metrics`, `nms_rollup_5m`, `nms_rollup_1h`, `nms_incidents`
  - All 4 snapshot immutability triggers remain strictly enforced and unaltered.
- **Additive Tables in `network_intelligence.db` (`core/network_intelligence/store.py`):**
  1. `intelligence_investigations` — Stores `investigation_id` (PK), `correlation_id`, `question`, `intent`, `scope_json`, `status`, `root_cause_category`, `confidence_label`, `confidence_score`, `report_json` (redacted), `evidence_refs_json`, `created_at`, `completed_at`, `duration_ms`. Indexed on `(created_at DESC)` and `(intent, created_at DESC)`.
  2. `intelligence_baselines` — Stores `(entity_key, metric_name, version)` (composite PK), `device_id`, `sample_count`, `median_val`, `mad_val`, `ewma_val`, `min_val`, `max_val`, `last_uptime_sec`, `topology_version_ref`, `status` (`ACTIVE` / `INVALIDATED`), `updated_at`. Indexed on `(device_id, status)`.
  3. `intelligence_anomalies` — Stores `anomaly_id` (PK), `device_id`, `entity_key`, `metric_name`, `anomaly_type`, `severity`, `observed_value`, `baseline_median`, `deviation_score`, `started_at`, `detected_at`, `is_fault_candidate`, `explanation_json`, `evidence_refs_json`. Indexed on `(detected_at DESC)` and `(device_id, detected_at DESC)`.
  4. `intelligence_contexts` — Stores time-bounded follow-up context `context_id` (PK), `created_at`, `expires_at`, `last_investigation_id`, `focus_entities_json` (secret-free), `evidence_snapshot_ts`. Indexed on `(expires_at)`.

### 3.2 Concurrency, Transactions & Retention
- `network_intelligence.db` uses `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA foreign_keys=ON`, and `PRAGMA busy_timeout=5000` with thread-safe `threading.RLock` write serialization.
- Automatic bounded retention pruning keeps at most `500` investigation records, `2,000` anomaly records, and automatically purges expired `intelligence_contexts`, preventing unbounded disk growth on the ThinkPad X270.
