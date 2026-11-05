# WP 4.6.2 — Route Analytics & Path Evaluation

## 1. Overview

Work Package 4.6.2 implements single-device and multi-hop route table analysis, five-tier LPM lookup, VRF table isolation, ECMP branch tracking, and multi-router path evaluation in [route_analytics.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py).

## 2. Implemented Components

- **Five-Tier LPM Evaluation (`evaluate_route_lookup` / [`LPMLookupResult`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py)):**
  - Preserves all 5 epistemic tiers: `rib_matching_prefixes`, `eligible_candidates`, `calculated_best_candidates`, `verified_fib_status` (`UNVERIFIED_RIB_ONLY`), and `observed_packet_path_status` (`NOT_OBSERVED`).
  - Strictly excludes `disabled`, `inactive`, `unreachable`, non-matching `routing_table` (VRF isolation), and blackhole/prohibit/reject null routes (reporting `NULL_ROUTE` explicitly).
  - Detects ECMP (`ecmp_gateways`) and ambiguous equal-distance candidates with differing metrics (`ambiguous_selection=True`).
- **Route Anomaly Detection ([`RouteTableAnalyzer`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py)):**
  - Detects all 12 [`RouteFindingType`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py) classes (`MISSING_DESTINATION_ROUTE`, `MISSING_DEFAULT_ROUTE`, `UNEXPECTED_DEFAULT_ROUTE`, `OVERLAPPING_PREFIXES`, `DUPLICATE_ROUTE_CANDIDATES`, `CONFLICTING_ROUTE_ADVERTISEMENTS`, `UNREACHABLE_NEXT_HOP`, `RECURSIVE_GATEWAY_DEPENDENCY`, `UNEXPECTED_ROUTING_TABLE_ASSIGNMENT`, `ASYMMETRIC_ROUTE_HYPOTHESIS`, `ECMP_CONFIGURATION`, `INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES`).
- **Multi-Hop Path Reconstruction ([`RoutePathEvaluator`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py)):**
  - Iteratively traces forwarding hops across collected routers using IP ownership (`build_ip_owner_index`), recursive gateway resolution (`resolve_recursive_next_hop`), interface operational state (`down_interfaces`), and `verified_adjacencies`.
  - Classifies paths into 7 honest [`PathResultState`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_analytics.py) values: `PATH_CONFIRMED_BY_EVIDENCE`, `PATH_INFERRED`, `PATH_PARTIAL`, `PATH_AMBIGUOUS`, `PATH_UNRESOLVED`, `PATH_UNREACHABLE`, and `PATH_NOT_ENOUGH_EVIDENCE`.
  - Never invents unmanaged or missing intermediate routers (`hop_state="EXTERNAL_OR_MISSING_ROUTER"` -> `PATH_PARTIAL`).
- **REST API Endpoints** ([network_intelligence.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/network_intelligence.py)):
  - `POST /api/intelligence/routes/lookup`
  - `POST /api/intelligence/routes/analyze`
  - `POST /api/intelligence/routes/evaluate-path`

## 3. Verification Gate (`WP_4_6_2_ACCEPTED`)

Verified by [test_wp_4_6_2_route_analytics.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_2_route_analytics.py) (**13/13 passed**).
