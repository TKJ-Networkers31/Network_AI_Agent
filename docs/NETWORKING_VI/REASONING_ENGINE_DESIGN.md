# AIRA OS — DETERMINISTIC REASONING ENGINE DESIGN
## Path, Correlation, RCA, Confidence, Health, Impact & Historical Reasoning (WP 6.0)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Core Design Principle

Layer 4 of Networking VI is **100% deterministic, reproducible, and LLM-independent**. Given identical structured `NetworkEvidenceBundle` and `NetworkKnowledgeGraph` inputs, every reasoning engine produces identical findings, hypotheses, confidence factor breakdowns, and uncertainty disclosures.

---

## 2. Sub-Engine Specifications

### 2.1 Network Path Intelligence Engine (`path_intelligence.py` — WP 6.3)
- **Inputs:** Source IP/device, Destination IP/device, Routing Table, VRF, `NormalizedRoute` sets, `LPMEvaluationResult` (`core/routing/route_analytics.py`), `RoutePathEvaluator` (`core/routing/cross_device_routing.py`), interface operational states, ARP/neighbor tables, VLAN/bridge memberships, tunnels, and OSPF/BGP states.
- **Explicit Reasoning Modes (`PathReasoningMode`):**
  1. `RIB_INFERRED` — Derived strictly from control-plane RIB LPM + recursive gateway resolution + interface/L2/L3 graph traversal. Explicitly labeled as control-plane inference, never a live packet trace.
  2. `FIB_CONFIRMED` — Emitted **only** when explicit RouterOS FIB / hardware-offload forwarding flags (`H` / FIB state verified) are present on every hop along a complete path. Never fabricated from plain RIB entries.
  3. `OBSERVED_FORWARDING` — Emitted **only** when corroborated by direct data-plane observations (validated read-only `/tool traceroute` hops, `/ping` reachability + matching interface/firewall packet-counter progression).
  4. `PARTIAL_PATH` — One or more hops resolved deterministically, followed by an unmanaged hop, external gateway, missing route bundle, or unresolved recursive gateway.
  5. `UNKNOWN_PATH` — Insufficient evidence (no routes collected for starting device, unknown source/destination, or empty RIB).
- **Analysis Dimensions:** LPM specificity, active vs inactive candidate routes, administrative distance & preference, recursive gateway chains (up to depth 16 with loop detection), unresolved gateways, missing/down egress interfaces, blackhole/unreachable/prohibit routes, VRF/table isolation, ECMP multi-path splits, asymmetric forward vs return paths, route flapping/withdrawals, and RouterOS v6 vs v7 semantics.

### 2.2 Multi-Device Correlation Engine (`correlation_engine.py` — WP 6.4)
- **13 Correlation Dimensions:** Device identity, interface identity, shared subnet, topology dependency, routing dependency, next-hop relationship, protocol adjacency (OSPF/BGP), WAN dependency, VLAN relationship, tunnel dependency, bounded time window, incident timeline ordering, and historical recurrence.
- **Anti-Fallacy Rule:** Temporal proximity alone **never** produces a causal correlation; observations are grouped into a causal candidate only when backed by structural, topological, L2/VLAN, routing, or protocol dependency edges in `NetworkKnowledgeGraph` (otherwise marked purely as `CORRELATED_EVENT`).
- **Canonical Scenarios Supported:**
  - *Scenario A:* Shared upstream router failure masking downstream unreachability alerts.
  - *Scenario B:* Control-plane BGP/OSPF route withdrawal while management & physical interfaces remain `UP`.
  - *Scenario C:* Interface FCS/CRC/drop degradation (`oper_status="up"` with accelerating error counters) degrading downstream services.
  - *Scenario D:* Layer-2 / Bridge VLAN tag mismatch isolating a specific VLAN segment while router management stays healthy.
  - *Scenario E:* WAN latency/packet-loss degradation while default routes and LAN links remain intact.

### 2.3 Explainable Confidence Model (`confidence_model.py` — WP 6.5)
- Computes a deterministic multi-factor score $S \in [0.0, 1.0]$ mapped to discrete epistemic labels:
  - `VERY_HIGH` ($S \ge 0.85$, $\ge 2$ independent corroborating sources, `FRESH` evidence, zero unexplained contradictions)
  - `HIGH` ($0.70 \le S < 0.85$)
  - `MODERATE` ($0.50 \le S < 0.70$)
  - `LOW` ($0.30 \le S < 0.50$)
  - `INSUFFICIENT` ($S < 0.30$ or critical required evidence missing)
- **8 Explicit Weighted Factors:**
  1. `evidence_quality` (weight `0.20`)
  2. `evidence_freshness` (weight `0.15`)
  3. `independent_corroboration` (weight `0.20`)
  4. `topology_consistency` (weight `0.15`)
  5. `protocol_consistency` (weight `0.15`)
  6. `historical_consistency` (weight `0.15`)
  7. `contradiction_penalty` (subtractive penalty `0.0` to `-0.45`)
  8. `missing_observation_penalty` (subtractive penalty `0.0` to `-0.40`)
- **Non-Calibration Disclosure:** Every confidence object carries `is_calibrated_probability = False` and a factor-by-factor breakdown explaining why points were awarded or deducted.

### 2.4 14-Step Root Cause Analysis Engine (`rca_engine.py` — WP 6.5)
- Executes the reproducible 14-step pipeline:
  1. Scope definition $\to$ 2. Evidence reuse/collection $\to$ 3. Freshness validation $\to$ 4. Dependency subgraph extraction $\to$ 5. Affected entity enumeration $\to$ 6. Timeline ordering $\to$ 7. Abnormal observation extraction $\to$ 8. Candidate hypothesis generation $\to$ 9. Supporting evidence scoring $\to$ 10. Contradictory evidence evaluation $\to$ 11. Deterministic ranking $\to$ 12. Missing observation identification $\to$ 13. Structured technical diagnosis $\to$ 14. Persistent reference storage.
- **Role Separation (`FindingClassification`):** Strictly classifies findings into `ROOT_CAUSE`, `CONTRIBUTING_FACTOR`, `SECONDARY_SYMPTOM`, `CORRELATED_EVENT`, or `UNKNOWN_CAUSE`.
- **17 Hypothesis Categories:** `DEVICE_FAILURE`, `INTERFACE_FAILURE`, `PHYSICAL_LINK_FAILURE`, `LAYER2_FAILURE`, `VLAN_MISMATCH`, `ROUTING_FAILURE`, `OSPF_FAILURE`, `BGP_FAILURE`, `NEXT_HOP_FAILURE`, `WAN_DEGRADATION`, `DNS_FAILURE`, `DHCP_FAILURE`, `TUNNEL_FAILURE`, `RESOURCE_EXHAUSTION`, `CONFIGURATION_CHANGE`, `TELEMETRY_FAILURE`, `UNKNOWN`.
- Never classifies into a specific fault category without direct supporting evidence; defaults honestly to `UNKNOWN` or `TELEMETRY_FAILURE` when observations are absent or ambiguous.

### 2.5 Multi-Dimensional Health, Baselines & Anomaly Engine (`health_engine.py`, `baseline_engine.py`, `anomaly_engine.py` — WP 6.6)
- **8 Transparent Health Dimensions:** `overall`, `device`, `interface`, `routing`, `protocol`, `wan`, `dependency`, `telemetry_confidence` — each reporting discrete status (`HEALTHY`, `DEGRADED`, `CRITICAL`, `UNKNOWN`, `INSUFFICIENT_DATA`) + supporting metrics. Missing telemetry yields `UNKNOWN` / `INSUFFICIENT_DATA`, never `0.0` or artificial health inflation/penalization.
- **Reboot- & Change-Aware Baselines:** Computes rolling median, Median Absolute Deviation ($\text{MAD}$), and EWMA ($\alpha = 0.2$) only when sample count $N \ge N_{\min}$ (default `6` clean samples) and contamination ratio $< 0.30$. Automatically versions and invalidates baselines upon device reboot (`uptime` regression), counter wrap/reset (`DISCONTINUOUS`), or topology/interface change.
- **Anomaly Detection:** Evaluates robust modified Z-score via MAD, rate-of-change spikes, error/drop counter acceleration, interface saturation trends, and protocol neighbor flap rates. Traffic spikes without error/latency/drop corroboration are labeled `TRAFFIC_PATTERN_DEVIATION` (informational), not a network fault.

### 2.6 Change Impact & Non-Destructive Failure Simulation (`impact_analyzer.py`, `failure_simulator.py` — WP 6.7)
- **Impact Analysis:** Separates `OBSERVED_IMPACT` (corroborated by active incidents, down links, or withdrawn routes) from `POTENTIAL_IMPACT` (structural blast radius derived from single-point-of-failure vs ECMP/redundant alternate paths).
- **Analytical Simulation:** Clones the relevant `NetworkKnowledgeGraph` and `NormalizedRoute` projections strictly in-memory, injects synthetic entity removal (router down, WAN route loss, OSPF neighbor down, BGP peer withdrawal, VLAN trunk cut, tunnel down), re-runs LPM + recursive route dependency + reachability traversal, and tags every result `is_simulation = True`. Zero live device or SQLite topology mutations occur.

### 2.7 Modular Protocol Analyzers (`protocols/` — WP 6.8) & Historical Intelligence (`historical_intelligence.py` — WP 6.9)
- Each protocol module (`layer2`, `ipv4`, `ipv6`, `static_routing`, `ospf`, `bgp`, `nat_firewall`, `qos`, `tunnels`) implements `BaseProtocolAnalyzer` declaring supported RouterOS versions, required/optional evidence types, normalization rules, diagnostic checks, confidence caps, and explicit limitations.
- `HistoricalIntelligenceEngine` diffs immutable `topology_snapshots` and `route_snapshots`, overlays `nms_incidents` and metric rollups across `[t_start, t_end]`, detects recurring faults/flapping entities, and explicitly surfaces `TELEMETRY_GAP` intervals.
