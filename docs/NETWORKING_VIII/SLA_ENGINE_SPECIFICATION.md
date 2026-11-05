# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.7
# SLA AND SERVICE MANAGEMENT ENGINE SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.7 — SLA & Service Management  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. OBJECTIVE & SERVICE OWNERSHIP

The SLA & Service Management engine evaluates customer service availability, tracks downtime attribution, enforces maintenance exclusions, and computes real-time error budget burn rates.

Every SLA policy and measurement is hard-scoped to `(tenant_id, service_id)`.

---

## 2. MEASUREMENT SEMANTICS & EPISTEMIC RULES

Telemetry samples over a measurement window are categorized into disjoint temporal states:
1. `MEASURED_UPTIME`: Direct telemetry proves service endpoints were responsive.
2. `MEASURED_DOWNTIME`: Direct telemetry proves service endpoints were unresponsive or unreachable.
3. `INFERRED_DOWNTIME`: Confirmed correlated device or link outage directly serving this endpoint.
4. `PLANNED_MAINTENANCE`: Outage occurring during an approved, scheduled maintenance window (`operational_maintenance_windows`).
5. `EXCLUDED_PERIOD`: Excluded force majeure or third-party upstream events.
6. `UNKNOWN`: Telemetry gap where no observations were recorded.
7. `INSUFFICIENT_COVERAGE`: Measurement window where $\text{Coverage} < 80\%$.

### Epistemic Invariants:
- **Never treat `UNKNOWN` as Uptime:** A communication loss between Gateway and Central NOC does not guarantee customer service uptime.
- **Never treat Gateway Reconnection as Immediate Service Recovery:** Recovery timestamp is grounded in direct post-reconnection telemetry.
- **Explicit Coverage Reporting:** If data coverage is below 80%, the report emits status `INSUFFICIENT_COVERAGE` with data gap metrics rather than inventing a false percentage.

---

## 3. FORMULAS & ERROR BUDGET CALCULATIONS

### 3.1 Data Coverage Ratio
$$\text{Coverage} = \frac{T_{\text{measured\_up}} + T_{\text{measured\_down}} + T_{\text{inferred\_down}}}{T_{\text{total\_window}} - T_{\text{maintenance}}} \times 100\%$$

### 3.2 Measured Availability Percentage
When $\text{Coverage} \ge 80\%$:

$$\text{Availability} = \frac{T_{\text{measured\_up}}}{T_{\text{measured\_up}} + T_{\text{measured\_down}} + T_{\text{inferred\_down}}} \times 100\%$$

### 3.3 Error Budget Accounting
Given a monthly window $T_{\text{window}} = 2,592,000\text{ seconds}$ (30 days) and target availability $A_{\text{target}} = 99.9\%$:

$$\text{AllowedDowntimeSeconds} = T_{\text{window}} \times (1.0 - \frac{A_{\text{target}}}{100.0}) = 2,592\text{ seconds } (43.2\text{ minutes})$$

$$\text{RemainingBudgetSeconds} = \text{AllowedDowntimeSeconds} - (T_{\text{measured\_down}} + T_{\text{inferred\_down}})$$

$$\text{RemainingBudgetPercent} = \frac{\text{RemainingBudgetSeconds}}{\text{AllowedDowntimeSeconds}} \times 100\%$$

---

## 4. RELATIONAL DATABASE SCHEMA

```sql
-- SLA Policies
CREATE TABLE IF NOT EXISTS operational_sla_policies (
    policy_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    service_id TEXT NOT NULL REFERENCES operational_services(service_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_availability REAL NOT NULL DEFAULT 99.9,
    target_response_time_ms REAL DEFAULT 150.0,
    target_mttr_minutes INTEGER DEFAULT 60,
    window_type TEXT NOT NULL DEFAULT 'MONTHLY' CHECK(window_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'ROLLING_30D')),
    maintenance_excluded INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, service_id)
);

-- SLA Measurement Reports
CREATE TABLE IF NOT EXISTS operational_sla_reports (
    report_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    service_id TEXT NOT NULL REFERENCES operational_services(service_id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL REFERENCES operational_sla_policies(policy_id) ON DELETE CASCADE,
    period_start_utc TEXT NOT NULL,
    period_end_utc TEXT NOT NULL,
    target_availability REAL NOT NULL,
    measured_availability REAL,
    total_downtime_seconds REAL NOT NULL DEFAULT 0.0,
    maintenance_excluded_seconds REAL NOT NULL DEFAULT 0.0,
    data_coverage_percent REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('COMPLIANT', 'AT_RISK', 'BREACHED', 'INSUFFICIENT_COVERAGE')),
    error_budget_remaining_percent REAL,
    incident_count INTEGER NOT NULL DEFAULT 0,
    details_json TEXT DEFAULT '{}',
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sla_report_lookup ON operational_sla_reports(tenant_id, service_id, period_start_utc DESC);
```
