# WP 4.6.4 — Historical Route Analytics

## 1. Overview

Work Package 4.6.4 introduces immutable historical route persistence (`route_snapshots`), semantic route change auditing (`route_changes`), incomplete-collection removal suppression, temporal NMS/topology correlation, and interactive frontend diff/timeline exploration.

## 2. Backend & Database Implementation

- **Persistence Engine:** [`RouteHistoryStore`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_history.py)
  - Separate SQLite tables (`route_snapshots` and `route_changes`) with 6 composite indexes (`idx_route_snapshots_device_ts`, `idx_route_snapshots_batch`, `idx_route_snapshots_hash`, `idx_route_changes_device_ts`, `idx_route_changes_snapshot`, `idx_route_changes_prefix`) so `topology_snapshots` and `topology_changes` remain 100% untouched.
  - Enforces SQLite `BEFORE UPDATE` and `BEFORE DELETE` immutability triggers (`trg_route_snapshots_no_update`, `trg_route_snapshots_no_delete`, `trg_route_changes_no_update`, `trg_route_changes_no_delete`).
  - Performs deterministic canonical JSON serialization (`serialize_routes_deterministically`), SHA-256 hashing (`sha256_hash`), and semantic diffing (`compute_route_snapshot_diff`) **outside** the SQLite write lock (`topology_transaction(..., write=True)`) to prevent database contention.
  - **Incomplete-Collection Removal Suppression:** When a snapshot has `completeness != "COMPLETE"`, missing routes from the prior complete baseline are recorded as `ROUTE_STATE_UNKNOWN` instead of false `ROUTE_REMOVED` events, and subsequent complete snapshots compare against the most recent complete baseline (`prev_complete_row`).
  - **Temporal Correlation:** Correlates route changes within a configurable time window against `nms_alerts` and `topology_changes`, explicitly labeling correlations as `TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION`.
- **REST API Endpoints** ([topology.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/topology.py)):
  - `POST /api/topology/route-snapshots`
  - `GET /api/topology/route-snapshots`
  - `GET /api/topology/route-snapshots/{snapshot_id}`
  - `GET /api/topology/route-snapshots/{snapshot_id}/verify`
  - `GET /api/topology/route-snapshots/compare`
  - `GET /api/topology/route-changes`
  - `GET /api/topology/route-history/analytics`
  - `GET /api/topology/route-history/manifest`

## 3. Frontend Components

Located under `AIRA_ECOSYSTEM/app/frontend/src/components/topology/`:
- [routeHistoryApi.js](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/routeHistoryApi.js)
- [RouteSnapshotIntegrityBadge.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/RouteSnapshotIntegrityBadge.jsx)
- [HistoricalRouteTable.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/HistoricalRouteTable.jsx)
- [RouteSnapshotTimeline.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/RouteSnapshotTimeline.jsx)
- [RouteSnapshotDiffViewer.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/RouteSnapshotDiffViewer.jsx)
- [RouteChangeLog.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/RouteChangeLog.jsx)
- [RouteHistoryModal.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/RouteHistoryModal.jsx)

## 4. Verification Gate (`WP_4_6_4_ACCEPTED`)

Verified by [test_wp_4_6_4_route_history.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_4_route_history.py) (**15/15 passed**) and [routeHistory.test.js](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/routeHistory.test.js) (**5/5 passed**).
