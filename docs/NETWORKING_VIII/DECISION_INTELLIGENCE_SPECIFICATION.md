# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.5
# OPERATIONAL DECISION INTELLIGENCE SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.5 — Operational Decision Intelligence  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. MISSION & DOMAIN OVERVIEW

The Operational Decision Intelligence engine provides deterministic, evidence-grounded operational guidance for NOC operators.

It transforms complex raw telemetry, multi-layer topology graphs, RCA hypotheses, predictive capacity horizons, and customer SLA exposure into actionable, prioritized operational decisions.

### Key Architectural Invariants
1. **Strict Epistemic Integrity:** The engine never presents a hypothesis as confirmed fact. When evidence is incomplete or stale, it explicitly returns `INSUFFICIENT_EVIDENCE` and identifies missing data points.
2. **Zero Live Device Mutation:** Recommendations are strictly advisory and human-in-the-loop. No automatic command execution, configuration changes, or reboots are permitted.
3. **Deterministic Prioritization:** Decision priority scoring is computed via a transparent, documented algebraic formula. It does not rely on opaque LLM weights.
4. **Tenant-Safe Context:** Every decision is strictly bound to `(tenant_id, site_id)`. Customer users can only view their own decisions and cannot approve NOC-only actions.

---

## 2. DOMAIN DATA MODELS

### 2.1 Decision Status & Transitions
```
                +--------------+
                |  GENERATED   |
                +--------------+
                       |
                       v
                +--------------+
   +----------->| UNDER_REVIEW |<----------+
   |            +--------------+           |
   |              /    |     \             |
   |             /     |      \            |
   |            v      v       v           |
   |     +----------+ +--------+ +------+  |
   |     | APPROVED | |REJECTED| |DEFER.|--+
   |     +----------+ +--------+ +------+
   |          |
   |          v
   |     +-----------+
   |     | COMPLETED |
   |     +-----------+
   |          |
   |          v
   |     +----------+
   +-----| VERIFIED |
         +----------+
```

Valid transitions:
- `GENERATED` $\rightarrow$ `UNDER_REVIEW`, `EXPIRED`, `REJECTED`
- `UNDER_REVIEW` $\rightarrow$ `APPROVED`, `REJECTED`, `DEFERRED`
- `DEFERRED` $\rightarrow$ `UNDER_REVIEW`, `EXPIRED`, `REJECTED`
- `APPROVED` $\rightarrow$ `COMPLETED`, `REJECTED`
- `COMPLETED` $\rightarrow$ `VERIFIED`, `UNDER_REVIEW`
- `VERIFIED` $\rightarrow$ Terminal (or `UNDER_REVIEW` on regression)
- `REJECTED` $\rightarrow$ Terminal
- `EXPIRED` $\rightarrow$ Terminal

### 2.2 Model Definitions
- `DecisionStatus` (Enum): `GENERATED`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, `DEFERRED`, `EXPIRED`, `COMPLETED`, `VERIFIED`.
- `RiskLevel` (Enum): `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- `RecommendationAlternative`:
  * `alternative_id`: str
  * `title`: str
  * `description`: str
  * `risk_level`: RiskLevel
  * `tradeoffs`: List[str]
  * `is_preferred`: bool
- `DecisionRecommendation`:
  * `recommendation_id`: str
  * `title`: str
  * `summary`: str
  * `safest_action`: str
  * `alternatives`: List[RecommendationAlternative]
  * `human_verification_checklist`: List[str]
  * `requires_approval`: bool
  * `approval_role`: str (e.g. `NOC_OPERATOR`, `NETWORK_ENGINEER`)
- `DecisionAssessment`:
  * `problem_statement`: str
  * `root_cause_hypotheses`: List[Dict[str, Any]]
  * `supporting_evidence_ids`: List[str]
  * `contradictory_evidence_ids`: List[str]
  * `missing_evidence_ids`: List[str]
  * `confidence_score`: float ($0.0 - 1.0$)
  * `epistemic_status`: str (`CONFIRMED_BY_EVIDENCE`, `HYPOTHESIS_SUPPORTED`, `INSUFFICIENT_EVIDENCE`)
  * `uncertainty_factors`: List[str]
- `OperationalDecision`:
  * `decision_id`: str (e.g. `dec_12ab34cd56ef`)
  * `tenant_id`: str
  * `site_id`: Optional[str]
  * `title`: str
  * `priority_score`: float ($0.0 - 100.0$)
  * `risk_level`: RiskLevel
  * `status`: DecisionStatus
  * `affected_services`: List[str]
  * `affected_devices`: List[str]
  * `assessment`: DecisionAssessment
  * `recommendation`: DecisionRecommendation
  * `sla_impact_assessment`: Optional[Dict[str, Any]]
  * `created_at`: str (ISO 8601 UTC)
  * `expires_at`: str (ISO 8601 UTC)
  * `updated_at`: str (ISO 8601 UTC)
- `DecisionHistoryRecord`:
  * `history_id`: str
  * `decision_id`: str
  * `tenant_id`: str
  * `actor`: str
  * `from_status`: str
  * `to_status`: str
  * `reason`: str
  * `created_at`: str (ISO 8601 UTC)

---

## 3. DETERMINISTIC PRIORITIZATION ALGORITHM

The decision priority score ($P \in [0.0, 100.0]$) is computed transparently without black-box weights:

$$P = \min\left(100.0, \; w_c \cdot C_{\text{service}} + w_s \cdot S_{\text{incident}} + w_i \cdot I_{\text{blast}} + w_l \cdot L_{\text{sla}} + w_e \cdot E_{\text{conf}}\right)$$

Where:
- $C_{\text{service}} \in [0.0, 1.0]$: Customer Service Criticality (Tier 1 = 1.0, Tier 2 = 0.75, Tier 3 = 0.4, Tier 4 = 0.1). Weight $w_c = 30.0$.
- $S_{\text{incident}} \in [0.0, 1.0]$: Incident Severity (Critical = 1.0, High = 0.75, Medium = 0.45, Low = 0.2, Info = 0.05). Weight $w_s = 25.0$.
- $I_{\text{blast}} \in [0.0, 1.0]$: Blast Radius Fraction ($\min(1.0, \frac{\text{affected\_devices}}{5})$). Weight $w_i = 20.0$.
- $L_{\text{sla}} \in [0.0, 1.0]$: SLA Exposure Severity (Breached = 1.0, Impending At-Risk = 0.7, Safe = 0.0). Weight $w_l = 15.0$.
- $E_{\text{conf}} \in [0.0, 1.0]$: Evidence Confidence ($0.0 - 1.0$). Weight $w_e = 10.0$.

Total maximum potential score: $30 + 25 + 20 + 15 + 10 = 100.0$.

Every priority score output includes the breakdown dictionary:
```json
{
  "total_score": 82.5,
  "factors": {
    "service_criticality_factor": 30.0,
    "incident_severity_factor": 18.75,
    "blast_radius_factor": 15.0,
    "sla_exposure_factor": 10.5,
    "evidence_confidence_factor": 8.25
  }
}
```

---

## 4. RELATIONAL DATABASE SCHEMA

```sql
-- Operational Decisions
CREATE TABLE IF NOT EXISTS operational_decisions (
    decision_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    site_id TEXT REFERENCES operational_sites(site_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    priority_score REAL NOT NULL,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'GENERATED' CHECK(status IN ('GENERATED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'DEFERRED', 'EXPIRED', 'COMPLETED', 'VERIFIED')),
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    affected_devices_json TEXT NOT NULL DEFAULT '[]',
    assessment_json TEXT NOT NULL,
    recommendation_json TEXT NOT NULL,
    sla_impact_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Append-Only Decision History
CREATE TABLE IF NOT EXISTS operational_decision_history (
    history_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES operational_decisions(decision_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON operational_decisions(tenant_id, site_id, status);
CREATE INDEX IF NOT EXISTS idx_decisions_priority ON operational_decisions(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_decision_hist_dec ON operational_decision_history(decision_id, created_at DESC);
```
