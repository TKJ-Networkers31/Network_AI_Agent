# AIRA OS — MULTI-DEVICE CORRELATION & ROOT CAUSE ANALYSIS SPECIFICATION
## 13-Dimension Correlation, 8-Factor Confidence & 14-Step Deterministic RCA (WP 6.4 & WP 6.5)

**Document Status:** WP 6.4 & WP 6.5 Specification & Implementation Contract

---

## 1. Multi-Device Correlation Model (`correlation_engine.py`)

### 1.1 Thirteen Correlation Dimensions
1. `device_identity` — Same canonical device across NMS, Topology, Routing, and Protocol stores.
2. `interface_identity` — Same `(device_id, interface_name)` across counters, link state, VLANs, and topology edges.
3. `shared_subnet` — Common L3 broadcast/subnet attachment (`SUBNET` / `NETWORK_SEGMENT`).
4. `topology_dependency` — Physical (`PHYSICAL_ADJACENCY`) or upstream/downstream (`DEPENDS_ON`) link.
5. `routing_dependency` — Recursive route or transit prefix dependency (`ROUTES_TO` / `DEPENDS_ON`).
6. `next_hop_relationship` — Direct RIB gateway reliance (`NEXT_HOP_OF`).
7. `protocol_adjacency` — OSPF neighbor or BGP peer relationship (`PEERS_WITH`).
8. `wan_dependency` — Shared egress `WAN_CONNECTION` or default route gateway.
9. `vlan_relationship` — Shared `VLAN` ID across trunk/access interfaces (`CARRIES`).
10. `tunnel_dependency` — Overlay `TUNNEL` endpoint reliance on underlay reachability.
11. `time_window` — Observations occurring within bounded `window_sec` (default `300s`).
12. `incident_timeline` — Chronological onset ordering ($t_{\text{upstream}} \le t_{\text{downstream}} + \Delta_{\text{poll}}$).
13. `historical_behavior` — Previously observed instability or snapshot transitions.

### 1.2 Strict Causation vs. Temporal Coincidence Rule
Co-occurring alerts within `time_window` that share **zero** structural, topological, L2/VLAN, routing, protocol, tunnel, or WAN relationships in `NetworkKnowledgeGraph` are grouped only as `temporal_coincidence` with `is_causal_candidate = False` and classified `CORRELATED_EVENT`, **never** `ROOT_CAUSE`.

---

## 2. Explainable Multi-Factor Confidence Model (`confidence_model.py`)

Confidence scores $S \in [0.0, 1.0]$ are **deterministic heuristic evidence-support scores** (`is_calibrated_probability = False`), **not** empirically calibrated frequentist probabilities.

$$
S = \operatorname{clamp}_{[0,1]}\Big(
0.20\,q + 0.15\,f + 0.20\,c_{\text{ind}} + 0.15\,t_{\text{cons}} + 0.15\,p_{\text{cons}} + 0.15\,h_{\text{cons}}
- P_{\text{contra}} - P_{\text{missing}}
\Big)
$$

| Label | Score Threshold & Guardrail |
|---|---|
| `VERY_HIGH` | $S \ge 0.85$ AND independent corroboration $\ge 0.75$ AND contradiction penalty $= 0$ AND freshness $\notin \{\text{STALE}, \text{EXPIRED}\}$ |
| `HIGH` | $0.70 \le S < 0.85$ (or capped from `VERY_HIGH` due to minor gap) |
| `MODERATE` | $0.50 \le S < 0.70$ |
| `LOW` | $0.30 \le S < 0.50$ |
| `INSUFFICIENT` | $S < 0.30$ or zero supporting evidence |

---

## 3. Reproducible 14-Step RCA Pipeline (`rca_engine.py`)

1. `DEFINE_SCOPE` — Bound target devices, interfaces, subnets, and investigation time window.
2. `ACQUIRE_OR_REUSE_EVIDENCE` — Consume `NetworkEvidenceBundle` without duplicate polling.
3. `VALIDATE_FRESHNESS` — Flag `STALE`, `EXPIRED`, and `UNKNOWN` records.
4. `BUILD_DEPENDENCY_SUBGRAPH` — Project `NetworkKnowledgeGraph` & `GraphQueryEngine` blast radius.
5. `IDENTIFY_AFFECTED_ENTITIES` — Enumerate impacted devices, interfaces, VLANs, routes, and services.
6. `ESTABLISH_TIMELINE` — Order incidents, interface changes, route/protocol shifts, and anomalies chronologically.
7. `DETECT_ABNORMAL_OBSERVATIONS` — Extract down states, error/drop accelerations, protocol drops, VLAN discrepancies, resource saturation, and WAN latency/loss.
8. `GENERATE_CANDIDATE_HYPOTHESES` — Instantiate evidence-backed hypotheses across the 17 `HypothesisCategory` classes (plus `TELEMETRY_FAILURE` / vantage-point isolation whenever reachability fails).
9. `EVALUATE_SUPPORTING_EVIDENCE` — Link concrete `evidence_id`s to each candidate.
10. `EVALUATE_CONTRADICTORY_EVIDENCE` — Penalize hypotheses contradicted by observed facts (e.g., `PHYSICAL_LINK_FAILURE` contradicted by `oper_status == "up"` and ICMP `UP`).
11. `RANK_HYPOTHESES` — Score via `ConfidenceScorer` and separate `ROOT_CAUSE`, `CONTRIBUTING_FACTOR`, `SECONDARY_SYMPTOM`, `CORRELATED_EVENT`, and `UNKNOWN_CAUSE`.
12. `IDENTIFY_MISSING_EVIDENCE` — Disclose uncollected telemetry or external hops needed to disambiguate top candidates.
13. `PRODUCE_DIAGNOSIS_AND_REMEDIATION_REVIEW` — Synthesize engineer-ready technical diagnosis and strictly human-review-only remediation steps (`auto_execute=False`).
14. `PERSIST_REFERENCES` — Package immutable `evidence_ids` and report metadata for `NetworkIntelligenceStore`.
