# WP 4.6.5 — Cross-Device Route Intelligence

## 1. Overview

Work Package 4.6.5 correlates routing state across multiple registered routers, reconciles routed next-hop relationships with `TopologyEngine` adjacencies and NMS operational states, detects 12 classes of cross-device routing inconsistencies, and renders an ephemeral route overlay on the topology canvas.

## 2. Backend Implementation

- **Evidence Correlator Extension:** Added `correlate_all_routed_nexthops` to [`CrossDeviceEvidenceCorrelator`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/correlation.py) to correlate all active unicast routes (beyond `0.0.0.0/0`) while preserving `correlate_default_gateway`.
- **Cross-Device Engine:** [`CrossDeviceRouteIntelligenceEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/cross_device_routing.py)
  - Builds [`VerifiedRouteRelationship`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/cross_device_routing.py) records classifying next-hop alignment into `TOPOLOGY_CONFIRMED`, `GATEWAY_IP_VERIFIED`, `SUBNET_INFERRED`, `TOPOLOGY_CONFLICT`, and `UNRESOLVED_EXTERNAL` (`is_physical_adjacency=False`).
  - Detects all 12 [`CrossDeviceInconsistencyType`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/routing/cross_device_routing.py) anomalies (`ASYMMETRIC_ROUTING`, `BLACKHOLE_TRANSIT_PATH`, `MISSING_RETURN_ROUTE`, `ROUTING_LOOP_HYPOTHESIS`, `CONFLICTING_DEFAULT_GATEWAYS`, `INCORRECT_VRF_ASSOCIATION`, `NEXT_HOP_INTERFACE_MISMATCH`, `DUPLICATE_SUBNET_OWNERSHIP`, `UNEXPECTED_PATH_DIVERGENCE`, `STALE_ROUTE_EVIDENCE`, `INCOMPLETE_DEVICE_COVERAGE`, `ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP`, plus `MISSING_UPSTREAM_ROUTE`), tagging each with `OBSERVED_FACT`, `STRONG_HYPOTHESIS`, or `HYPOTHESIS`.
  - Generates ephemeral topology overlays (`build_topology_route_overlay`) with typed segments (`INFERRED_ROUTE_PATH`, `RECURSIVE_NEXT_HOP_DEPENDENCY`, `ROUTE_UNCERTAINTY`) where `is_physical_link=False` and `mutates_physical_topology=False`.
- **REST API Endpoints:**
  - `POST /api/intelligence/routes/cross-device` ([network_intelligence.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/network_intelligence.py))
  - `GET /api/topology/route-overlay` ([topology.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/topology.py))

## 3. Frontend Visualization & Inspector

- [routeOverlayApi.js](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/routeOverlayApi.js): Maps overlay segment types to distinct dashed SVG stroke styles (`"8 4"`, `"3 3"`, `"5 5"`), visually separated from solid confirmed physical cabling (`strokeDasharray: "none"`).
- [MultiDeviceRouteInspector.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/MultiDeviceRouteInspector.jsx): Sidecar inspector displaying all 13 mandatory route hop fields (source/target device, destination prefix, routing table, selected candidate, gateway, immediate gateway, egress interface, next-device hypothesis, recursive dependency, evidence sources, confidence & completeness, unresolved/missing info) and cross-device inconsistencies.
- [TopologyPage.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/pages/TopologyPage.jsx): Integrates the Route Overlay toggle, focused destination/VRF query bar, request race-token guard (`routeOverlayReqRef`), ephemeral SVG directional arrow overlay, `MultiDeviceRouteInspector`, and `RouteHistoryModal` launcher.

## 4. Verification Gate (`WP_4_6_5_ACCEPTED`)

Verified by [test_wp_4_6_5_cross_device_routing.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_5_cross_device_routing.py) (**10/10 passed**) and [multiDeviceRouteOverlay.test.js](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/components/topology/multiDeviceRouteOverlay.test.js) (**2/2 passed**).
