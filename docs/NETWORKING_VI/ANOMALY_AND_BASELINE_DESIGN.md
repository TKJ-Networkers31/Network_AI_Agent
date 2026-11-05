# AIRA OS — NETWORKING VI: ANOMALY, BASELINE & MULTI-DIMENSIONAL HEALTH DESIGN (WP 6.6)

## 1. Design Philosophy & Hardware Constraints

Networking VI operates on constrained local hardware (CPU-only, ~8 GB RAM total) and intermittent or partial enterprise RouterOS telemetry. Consequently, WP 6.6 avoids heavy external ML runtimes (`scikit-learn`, `torch`, `prophet`) and instead implements **deterministic, robust non-parametric statistics** (`Rolling Median`, `MAD`, `EWMA`, `Rate-of-Change`, and `Counter Acceleration`) paired with **8-dimension explainable health evaluation**.

---

## 2. Multi-Dimensional Network Health Model (`health_engine.py`)

Health is never collapsed into a single opaque decorative score. `NetworkHealthEngine` evaluates 12 operational factors organized into **8 transparent `DimensionHealthScore` dimensions**:

1. `overall`: Weighted synthesis of measurable operational dimensions, explicitly bounded when critical dimensions are degraded or missing.
2. `device`: Reachability (`UP` / `DEGRADED` / `DOWN` / `MONITORING_UNAVAILABLE`), CPU pressure, memory pressure, and active device incidents.
3. `interface`: Admin-enabled interface operational state, link quality, traffic utilization saturation, and CRC/FCS/drop error levels.
4. `routing`: RIB availability, active default/core route presence, unresolved next-hop absence, and routing stability.
5. `protocol`: OSPF neighbor `Full`/`2-Way` state, BGP session `Established` state, and tunnel operational state (returns `INSUFFICIENT_DATA` when no dynamic protocol evidence exists rather than fabricating `100%` healthy).
6. `wan`: Edge/WAN gateway reachability, probe latency (`latency_ms`), and packet loss (`packet_loss_percent`).
7. `dependency`: Health of critical upstream transit/gateway nodes identified in `NetworkKnowledgeGraph` (`DEPENDS_ON` fan-in).
8. `telemetry_confidence`: Ratio of `FRESH`/`AGING` evidence records, absence of `CollectionGapRecord`s, and absence of cross-source `EvidenceContradiction`s.

### Health Status Semantics (`HealthStatus`)
- `HEALTHY`: Score $\ge 85.0$ with sufficient fresh observations.
- `DEGRADED`: Score $55.0 \le s < 85.0$, or localized non-critical warning conditions.
- `CRITICAL`: Score $< 55.0$, or confirmed outage of critical transit/gateway/device.
- `INSUFFICIENT_DATA`: Fewer observations than required to evaluate the dimension (e.g., no WAN/protocol telemetry collected); `score = None`.
- `UNKNOWN`: Selected scope contains zero devices or only `UNKNOWN`/unreachable collector state; `score = None`.

**Non-Negotiable Missing-Data Rule:** `None` metrics (`cpu_load_percent=None`, `rx_rate_bps=None`, `latency_ms=None`) are **never** coerced to `0.0`. Missing metrics increment `missing_entities` and reduce `telemetry_confidence` without falsely penalizing or inflating `device` or `interface` health.

---

## 3. Adaptive Behavior Baselines (`baseline_engine.py`)

`BaselineEngine` maintains bounded per-entity rolling sample windows (`max_samples = 120`, `min_samples = 5`) for metrics including:
- `cpu_load_percent`, `memory_used_percent`, `latency_ms`, `packet_loss_percent`
- `rx_rate_bps`, `tx_rate_bps`, `rx_utilization_percent`, `tx_utilization_percent`, `error_drop_total`
- `active_route_count`, `established_bgp_peers`, `full_ospf_neighbors`

### Statistical Estimators
- **Rolling Median ($M$):** Resistant to up to 50% outliers during transient spikes.
- **Median Absolute Deviation ($\text{MAD}$):** $\text{MAD} = \text{median}(|x_i - M|)$, scaled by $\sigma_{\text{MAD}} = 1.4826 \cdot \text{MAD}$ for normal-equivalent dispersion.
- **Exponentially Weighted Moving Average ($\text{EWMA}$):** $E_t = \alpha x_t + (1 - \alpha) E_{t-1}$ with $\alpha = 0.25$.

### Contamination Guards, Versioning & Invalidation
1. **Minimum Clean Sample Rule:** No baseline is marked `ACTIVE` with fewer than `min_samples = 5` valid numeric observations (`None` and `NaN` are rejected).
2. **Maintenance Windows:** Observations tagged `in_maintenance = True` are excluded from baseline learning.
3. **Device Reboot Detection:** If `uptime_seconds` regresses (`uptime_t < uptime_{t-1}`), the baseline increments `version`, records `invalidation_reason = "DEVICE_REBOOT_DETECTED"`, resets monotonic counter anchors, and avoids false rate/drop anomalies across the reboot boundary.
4. **Counter Reset Handling (`DISCONTINUOUS`):** If a cumulative counter (`in_errors`, `rx_bytes`, etc.) decreases without a full reboot (`counter_t < counter_{t-1}`), the delta sample is flagged `DISCONTINUOUS` and excluded from baseline updates and negative-rate calculations.
5. **Material Topology Change Invalidation:** When `topology_ref` changes materially on an entity's structural neighborhood (and `invalidate_on_topology_change=True`), the baseline increments `version` (`status = "INVALIDATED"` until `min_samples` post-change samples accumulate).

---

## 4. Resource-Efficient Anomaly Detection & Explanation (`anomaly_engine.py`)

`AnomalyEngine` detects six classes of operational anomalies:
1. `BASELINE_DEVIATION` (Robust Modified Z-Score via Median + MAD).
2. `RATE_OF_CHANGE` (Rapid step jump relative to EWMA / prior sample).
3. `ERROR_ACCELERATION` (Monotonic growth/acceleration in `in_errors`, `out_errors`, `in_drops`, `out_drops`).
4. `UTILIZATION_DEVIATION` (Sustained high link utilization relative to baseline and capacity).
5. `TRAFFIC_PATTERN_DEVIATION` (Unusual `rx_rate_bps` / `tx_rate_bps` surge or collapse).
6. `PROTOCOL_INSTABILITY` (Route count drop, BGP peer loss, or OSPF adjacency loss).

### Non-Fault Traffic Spike Guard
Not every traffic spike is a network fault. When `rx_rate_bps`, `tx_rate_bps`, or `utilization_percent` exceeds the historical baseline (`< 90%` link capacity) **without** accompanying interface errors, packet drops, or latency/packet-loss degradation:
- `is_fault_candidate = False`
- `severity = "info"`
- Explanation explicitly states that elevated traffic volume was observed without forwarding degradation indicators.

### 9-Point Anomaly Explanation Contract
Every `AnomalyObservation` populates:
1. `what_changed`
2. `began_at` & `detected_at`
3. `unusualness_score` (robust MAD multiples / severity index)
4. `baseline_reference` (`baseline_id`, `version`, `median`, `mad`, `ewma`, `sample_count`)
5. `device_id` & `interface_name`
6. `evidence_ids`
7. `is_correlated` & `correlated_with`
8. `potentially_affected` (downstream dependents from `GraphQueryEngine`)
9. `additional_evidence_needed`
