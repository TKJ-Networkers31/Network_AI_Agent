# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.5.1
# DYNAMIC MULTI-DIMENSIONAL HEALTH SCORING SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.5.1 — Dynamic Health Scoring  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. OBJECTIVE & HEALTH DIMENSIONS

The Dynamic Health Scoring engine calculates transparent, deterministic operational health scores across 6 distinct architectural dimensions:

1. **Device Health:** Evaluates physical/virtual device CPU load, memory utilization, uptime stability, and management reachability.
2. **Interface Health:** Evaluates link state, Rx/Tx bandwidth utilization, CRC/drop error rates, and carrier transitions.
3. **Site Health:** Aggregates devices and interfaces within an operational customer site.
4. **Service Health:** Evaluates customer business service endpoints, reachability, and dependency paths.
5. **Gateway Health:** Evaluates edge gateway heartbeat timeliness, daemon CPU/RAM load, and buffer queue depth.
6. **Tenant Operational Health:** Aggregates all customer sites, services, and gateways using criticality-weighted scoring.

---

## 2. HEALTH STATES & EPISTEMIC PRINCIPLES

### 2.1 Explicit Health States
- `HEALTHY`: All indicators normal; score $\in [90.0, 100.0]$.
- `DEGRADED`: Minor performance impairment or non-critical error rate; score $\in [70.0, 89.9]$.
- `WARNING`: Significant threshold breach or capacity risk; score $\in [50.0, 69.9]$.
- `CRITICAL`: Outage, unreachable device, or severe failure; score $\in [0.0, 49.9]$.
- `UNKNOWN`: No telemetry received or state unverified; score is `None`.
- `INSUFFICIENT_DATA`: Telemetry exists but sample count is below minimum threshold ($N < 5$); score is `None`.

### 2.2 Epistemic Invariants
- **Never equate `UNKNOWN` with `HEALTHY`:** Missing telemetry samples are never treated as 100% or healthy.
- **Never convert missing telemetry to `0.0` or `100.0`:** Missing indicators are recorded in `missing_dimensions`.
- **Explainability:** Every score output must include `contributing_factors`, `evidence_freshness`, `confidence`, and `calculation_timestamp`.

---

## 3. AGGREGATION & CRITICALITY WEIGHTING

Simple arithmetic averages across sites can dangerously mask a complete outage of a critical service. The tenant-level health scoring employs **Criticality-Aware Minimum Clamping**:

$$\text{Health}_{\text{Tenant}} = \min\left( \text{Health}_{\text{Tier1\_Services}}, \; \sum_{i} w_i \cdot \text{Health}_{\text{Site}_i} \right)$$

If any Tier 1 (Mission Critical) service enters `CRITICAL` state ($< 50.0$), the Tenant Operational Health state is clamped to `CRITICAL` regardless of how many other non-critical sites are functioning normally.

---

## 4. RELATIONAL DATABASE PERSISTENCE

```sql
CREATE TABLE IF NOT EXISTS operational_health_scores (
    score_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    site_id TEXT REFERENCES operational_sites(site_id) ON DELETE CASCADE,
    dimension TEXT NOT NULL CHECK(dimension IN ('DEVICE', 'INTERFACE', 'SITE', 'SERVICE', 'GATEWAY', 'TENANT')),
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('HEALTHY', 'DEGRADED', 'WARNING', 'CRITICAL', 'UNKNOWN', 'INSUFFICIENT_DATA')),
    score REAL,
    confidence REAL NOT NULL DEFAULT 1.0,
    contributing_factors_json TEXT NOT NULL DEFAULT '[]',
    missing_dimensions_json TEXT NOT NULL DEFAULT '[]',
    calculated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_lookup ON operational_health_scores(tenant_id, dimension, entity_id, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_state ON operational_health_scores(tenant_id, state);
```
