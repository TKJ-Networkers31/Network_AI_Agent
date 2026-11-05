# AIRA OS — Networking IV Remaining Limitations

In accordance with AIRA OS's epistemic integrity standards, the following technical and operational limitations remain explicitly visible in code (`DEFAULT_ANALYSIS_LIMITATIONS`), API responses, UI inspectors, and engineering documentation:

## 1. Live Lab Hardware Validation Pending (`dev_chr`, `dev_r-1`)

- During the Networking IV finalization campaign, non-invasive TCP reachability probes against the two authorized inventory devices (`dev_chr` at `10.66.38.30:22` and `dev_r-1` at `192.168.0.1:22`) timed out (`TimeoutError` — lab subnet currently offline/disconnected from host).
- All parser, collection, cross-device correlation, and E2E acceptance suites were verified against historical RouterOS v6 (`6.49.x`) and RouterOS v7 (`7.14.x`–`7.23.x`) captures and realistic multi-router fixtures.
- **Required Follow-Up Condition:** Execute read-only live verification (`POST /api/intelligence/routes/collect` and `POST /api/intelligence/auto-diagnose`) when `dev_chr` and `dev_r-1` are powered on and reachable on the management LAN.

## 2. Calculated RIB Selection ≠ Confirmed Kernel/Hardware FIB Installation

- `evaluate_longest_prefix_match` and `evaluate_route_lookup` compute control-plane route selection from RouterOS RIB CLI outputs (`/ip route print detail`, `/routing route print detail`).
- While RouterOS `H` (`hw-offloaded`) and `A` (`active`) flags are preserved on `NormalizedRoute`, AIRA does not directly inspect ASIC hardware forwarding tables or Linux kernel netlink FIB state (`verified_fib_status = "UNVERIFIED_RIB_ONLY"`).

## 3. Inferred Control-Plane Path ≠ Observed Data-Plane Packet Path

- Multi-hop paths reconstructed by `RoutePathEvaluator` and `CrossDeviceRouteIntelligenceEngine` represent **control-plane forwarding intent**, not observed packet-by-packet flow telemetry (`observed_packet_path_status = "NOT_OBSERVED"` unless explicit traceroute evidence is supplied).
- Equal-Cost Multi-Path (`ECMP`) per-connection hash selection cannot be deterministically predicted from static RIB snapshots alone; AIRA surfaces all ECMP branches and marks per-flow path selection as ambiguous where appropriate.

## 4. Policy Routing, Mangle Marks, and FastTrack Scope

- Standard LPM and VRF path evaluation honor explicit `routing-table` / `routing-mark` attributes on routes, `/routing rule print`, and `/ip route rule print` observations when collected, but do **not** dynamically simulate packet-level `/ip firewall mangle` `mark-routing` mutations, NAT translation rewrites mid-flight, or FastTrack connection-tracking bypasses.

## 5. IPv4 Production Scope (IPv6-Ready Data Model)

- `NormalizedRoute` and `RouteHistoryStore` schemas are IPv6-ready, while active LPM/next-hop correlation and path evaluation in Phase 4.6 target IPv4 (`0.0.0.0/0` and IPv4 CIDR prefixes). Full dual-stack IPv6 next-hop link-local (`fe80::%iface`) correlation is scheduled for future expansion.

## 6. Temporal Event Correlation ≠ Proven Causation

- `RouteHistoryStore.get_historical_analytics` correlates `route_changes` with `nms_alerts` and `topology_changes` within a bounded timestamp window and explicitly tags every match with `TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION`.
