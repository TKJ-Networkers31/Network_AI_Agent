# WP 4.6.1 — Multi-Device Route Collection Integration

## 1. Overview

Work Package 4.6.1 integrates [`UnifiedRouteParser`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/unified_route_parser.py) with AIRA's multi-device execution pipeline via [`MultiDeviceRouteCollector`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_collector.py), [`CanonicalNetworkRegistry`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/canonical_network.py), and [`UnifiedCommandExecutor`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/command_execution.py).

## 2. Implemented Components

- **Core Collector:** [`MultiDeviceRouteCollector`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_collector.py)
  - Resolves authorized managed targets (`is_managed=True`) via `CanonicalNetworkRegistry`; rejects unauthorized/unmanaged targets and flags management IP or identity collisions.
  - Selects version-aware read-only commands:
    - RouterOS v7: `/ip route print detail without-paging`, `/routing route print detail without-paging`
    - RouterOS v6: `/ip route print detail without-paging`, `/routing ospf route print without-paging`
  - Enforces bounded concurrency (`DEFAULT_MAX_CONCURRENCY = 4`, `ABSOLUTE_MAX_CONCURRENCY = 8`), per-device locking to prevent duplicate overlapping SSH sessions, bounded retries with backoff, per-device timeouts, and cooperative cancellation (`cancel_job(job_id)` / `threading.Event`).
  - Produces [`RouteCollectionResult`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_collector.py) and [`MultiDeviceRouteCollectionReport`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_collector.py) with explicit `status` (`SUCCESS`, `PARTIAL`, `UNREACHABLE`, `AUTH_FAILED`, `TIMEOUT`, `CANCELLED`, `FAILED`) and `completeness` (`COMPLETE`, `PARTIAL`, `TRUNCATED`, `EMPTY`, `UNREACHABLE`, `FAILED`).
  - Supports zero-SSH bundle ingestion via `ingest_bundle_routes(mbundle)` so [`AutomaticNetworkOrchestrator`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py) and [`EvidenceCollector`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/evidence.py) reuse single-pass telemetry.
- **Evidence Integration:** [`EvidenceCollector._collect_routes`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/evidence.py) migrated to `UnifiedRouteParser` so single-device and multi-device bundles emit canonical `NormalizedRoute` dictionaries.
- **REST API Endpoints** ([network_intelligence.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/network_intelligence.py)):
  - `POST /api/intelligence/routes/collect`
  - `POST /api/intelligence/routes/collect/{job_id}/cancel`
  - `GET /api/intelligence/routes/collected`
  - `GET /api/intelligence/routes/collected/{device_id}`

## 3. Verification Gate (`WP_4_6_1_ACCEPTED`)

Verified by [test_wp_4_6_1_route_collection.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_1_route_collection.py) (**14/14 passed**): single/multi-device collection, RouterOS v6 & v7 compatibility, partial fleet availability, truncated table handling, duplicate suppression, retries/timeouts, job cancellation, VRF preservation, collision detection, concurrency bounds, and secret redaction.
