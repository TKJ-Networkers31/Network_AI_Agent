# AIRA OS — NETWORK PATH INTELLIGENCE SPECIFICATION
## Multi-Mode Control-Plane & Data-Plane Path Reasoning (WP 6.3)

**Document Status:** WP 6.3 Specification & Implementation Contract

---

## 1. Epistemic Path Reasoning Modes (`PathReasoningMode`)

`NetworkPathIntelligenceEngine` (`core/network_intelligence/path_intelligence.py`) enforces strict separation between control-plane route selection, FIB programming, and data-plane packet observations:

| Mode | Meaning | Required Evidentiary Proof | What It Does NOT Prove |
|---|---|---|---|
| `RIB_INFERRED` | Complete path from starting device to destination subnet/device derived from active RIB routes, LPM, and recursive next-hop resolution. | Complete LPM + active route + resolved egress/next-hop on every hop to destination. | Does **not** prove hardware FIB installation, firewall acceptance, or live packet delivery. |
| `FIB_CONFIRMED` | Every hop along a complete path carries explicit FIB / hardware-offloaded forwarding confirmation. | RouterOS v7 `H` flag or explicit `raw_attributes["fib"] == True` / `selected == True` on **every** hop, with operational (`up`) egress interfaces. | Never fabricated from plain RIB routes; still subject to stateful firewall/ACL filtering. |
| `OBSERVED_FORWARDING` | Path corroborated by direct data-plane forwarding observations. | Validated read-only `/tool traceroute` hops or probe reachability + matching interface/forwarding observation sequence. | Valid at observation timestamp; subject to subsequent ECMP hashing or dynamic reconvergence. |
| `PARTIAL_PATH` | One or more hops resolved deterministically, but end-to-end path terminates at an external ISP gateway, unmanaged hop, unresolved recursive gateway, down egress port, or missing router RIB. | At least one valid RIB hop resolved on the starting device. | Full end-to-end delivery cannot be asserted. |
| `UNKNOWN_PATH` | Insufficient evidence to establish even the first hop. | Triggered when starting device is unknown, RIB snapshot is missing/empty, or no covering route (including `0.0.0.0/0`) exists. | Never guesses a default gateway. |

---

## 2. RouterOS v6 vs. RouterOS v7 Semantics

`NetworkPathIntelligenceEngine` reuses `UnifiedRouteParser` (`4.6.0`) and accounts for key RouterOS version differences:
1. **Flags & FIB State:**
   - RouterOS v6 `/ip route print detail` uses `A` (active in RIB/FIB), `S` (static), `D` (dynamic), `o` (OSPF), `b` (BGP), `C` (connected), `X` (disabled), `B` (blackhole), `U` (unreachable), `P` (prohibit) — without a separate `fib` flag. Consequently, v6 RIB output alone is classified `RIB_INFERRED` unless explicit FIB/forwarding verification is supplied.
   - RouterOS v7 `/ip route print detail` / `/routing route print` distinguishes `A` (active), `H` (hw-offloaded), `+` (ECMP), and explicit `fib` / `immediate-gw` attributes, plus separate named routing tables (`routing-table=vrf_corp`).
2. **Recursive Next-Hop Scope Rules:**
   - Delegates recursive lookup to `resolve_recursive_next_hop` (depth cap `16`, cycle detection, `target-scope >= resolving_route.scope` enforcement).
3. **ECMP & Multi-Path:**
   - Preserves comma-separated gateways (`v6`/`v7`) and RouterOS v7 `+` active equal-cost routes sharing `(dst_prefix, distance, routing_table)`, surfacing all `candidate_paths` and `ecmp_gateways`.

---

## 3. Multi-Dimensional Path Explanation & Comparison

- Every `PathAnalysisResult` documents per-hop: starting device, VRF/routing table, matched prefix, selected route summary, administrative distance & selection rationale (e.g., `/24 > /16` LPM specificity or `distance 1 < distance 110`), recursive chain, outgoing interface & operational state, resolved next router, missing evidence, confidence, and `is_directly_observed`.
- `compare_paths(path_a, path_b, comparison_type)` compares paths across:
  1. Two source devices (`source_comparison`)
  2. Two destinations (`destination_comparison`)
  3. Two VRFs (`vrf_comparison`)
  4. Two routing tables (`table_comparison`)
  5. Current vs. historical snapshots / before & after a route change (`snapshot_comparison`)
