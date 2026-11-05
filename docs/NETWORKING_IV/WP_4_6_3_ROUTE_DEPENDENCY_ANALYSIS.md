# WP 4.6.3 — Route Dependency & Recursive Analysis

## 1. Overview

Work Package 4.6.3 models intra-device recursive gateway chains and inter-device upstream routing dependencies using an ephemeral typed graph and non-mutating hypothetical failure blast-radius engine in [route_dependency.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py).

## 2. Implemented Components

- **Typed Ephemeral Dependency Graph ([`RouteDependencyGraph`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py)):**
  - 9 [`DependencyNodeType`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py) types (`ROUTE`, `NEXT_HOP`, `GATEWAY`, `INTERFACE`, `CONNECTED_NETWORK`, `CANONICAL_DEVICE`, `ROUTING_TABLE`, `RECURSIVE_ROUTE`, `UPSTREAM_DEVICE`) and 9 [`DependencyRelationType`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py) relations.
  - Enforces bounded graph caps (`max_nodes=4000`, `max_edges=8000`) and marks `semantic_domain="ROUTE_DEPENDENCY"`, `persisted_as_topology_edges=False`.
- **Iterative Recursive Resolver ([`RouteDependencyAnalyzer`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py)):**
  - Uses an explicit queue (zero Python call-stack recursion) with `DEFAULT_MAX_DEPTH = 16`, per-branch visited-route and visited-gateway cycle detection (`CYCLE_DETECTED`), alternative backup route tracking (`alternative_gateway_routes`), and multi-branch ECMP resolution (`MULTI_PATH_RESOLVED`).
- **Evidence-Strict Hypothetical Failure Propagation ([`FailurePropagationAnalyzer`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py)):**
  - Evaluates all 8 [`HypotheticalFailureType`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/route_dependency.py) scenarios (`INTERFACE_DOWN`, `GATEWAY_UNREACHABLE`, `INTERMEDIATE_ROUTER_UNAVAILABLE`, `MISSING_ROUTE`, `UPSTREAM_DEFAULT_ROUTE_LOSS`, `ROUTING_TABLE_MISMATCH`, `RECURSIVE_NEXT_HOP_FAILURE`, `ECMP_BRANCH_LOSS`).
  - Separates `direct_dependencies`, `indirect_dependencies`, `potentially_affected_destinations`, `alternative_paths`, and `unknown_dependencies` (for uncollected/partial routers so impact is never fabricated).
- **REST API Endpoints** ([network_intelligence.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/network_intelligence.py)):
  - `POST /api/intelligence/routes/dependencies`
  - `POST /api/intelligence/routes/failure-impact`

## 3. Verification Gate (`WP_4_6_3_ACCEPTED`)

Verified by [test_wp_4_6_3_route_dependency.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_3_route_dependency.py) (**12/12 passed**).
