# AIRA OS — NETWORKING VIII: PHASE C PRE-IMPLEMENTATION AUDIT
## ARCHITECTURE, EVIDENCE DATA FLOWS, REUSE, AND GAP ANALYSIS

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Phase:** Phase C — Operational Decision Intelligence (WP 8.5 – 8.8)  
**Organization:** LS Technology  
**Baseline HEAD:** `be59871acd2dd92c581d8944e65899d485f208ae`  
**Workspace:** `D:\data\agent_ai`  
**Execution Environment Profile:** Windows, ThinkPad X270, Intel Core i7-7500U, 8 GB RAM, CPU-Only  
**Audit Status:** **COMPLETED**

---

## 1. EXECUTIVE AUDIT SUMMARY

Phase C transitions AIRA OS from a multi-tenant monitoring and gateway collection platform into an **evidence-grounded operational decision support system**. 

In strict adherence to the project charter:
- **No duplicate RCA engine** will be introduced. The existing `RootCauseAnalysisEngine` will be reused.
- **No duplicate NMS collector** will be introduced. Telemetry ingestion remains bound to `HardenedNmsScheduler` and `GatewayIngestionHub`.
- **No duplicate scheduler or incident state machine** will be created. The existing `OperationalSchedulerEngine` and `ProactiveIncidentEngine` will be extended.
- **100% Read-Only Network Policy** is maintained. live network devices are never mutated; no arbitrary remote shell execution is permitted.
- **Deterministic-First Intelligence:** All risk scoring, health calculations, SLA measurements, and recommendation ranking will run via deterministic algorithms that execute without requiring local or cloud LLM availability.

---

## 2. SUBSYSTEM REUSE & EXTENSION INVENTORY

| Subsystem / Module | Authoritative File | Current Role | Phase C Architectural Action |
|---|---|---|---|
| **Tenant & Identity Core** | [`core/tenant/`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/tenant/) | Multi-tenant models, RBAC, customer site/device inventory, audit logs | **REUSE AS-IS.** `TenantContext`, `tenant_scope`, and `TenantScopedRepository` will govern all Phase C services. |
| **Edge Gateway Ingestion** | [`core/edge_gateway/`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/) | Ingests branch telemetry envelopes with monotonic sequencing & replay defense | **REUSE AS-IS.** Authoritative source of remote customer telemetry feeding `nms_raw_metrics`. |
| **Unified Evidence Service** | [`core/network_intelligence/evidence_service.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/evidence_service.py) | Assembles Layer 1/2 evidence bundles with freshness evaluation | **REUSE & EXTEND.** Reused as primary evidence provider; add tenant/site filtering so queries assemble scoped evidence bundles. |
| **Root Cause Analysis (RCA)** | [`core/network_intelligence/rca_engine.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/rca_engine.py) | Generates and ranks causal hypotheses against evidence bundles | **REUSE AS-IS.** Consumed directly by the Decision Engine. Output `RCAReport` provides root cause hypotheses for operational decisions. |
| **Knowledge Graph** | [`core/network_intelligence/knowledge_graph.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/knowledge_graph.py) | Directed multi-layer network graph with evidence provenance | **REUSE AS-IS.** Used for blast radius and dependency traversal without in-memory graph cloning. |
| **Predictive Engine** | [`core/operations/predictive_engine.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/predictive_engine.py) | Linear trend forecasting, MAD anomaly filtering, capacity horizons | **REUSE AS-IS.** Consumed by Decision Engine and Risk Assessment to evaluate capacity breach risks. |
| **Health Engine** | [`core/network_intelligence/health_engine.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/health_engine.py) | Evaluates 8-dimension health on network nodes | **REUSE & EXTEND.** Wrap with `DynamicHealthScoringEngine` (WP 8.5.1) to compute Site, Service, Gateway, and Tenant operational scores. |
| **Service Intelligence** | [`core/operations/service_intelligence.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/service_intelligence.py) | Business service catalog and endpoint mappings | **EXTEND.** Add `tenant_id` and `site_id` columns to `operational_services` and `operational_service_endpoints`. |
| **Incident Engine** | [`core/operations/incident_engine.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/incident_engine.py) | Proactive incident lifecycle (`DETECTED` $\rightarrow$ `CLOSED`) | **EXTEND.** Add `tenant_id` and `site_id` columns to `operational_incidents`; add tenant-aware correlation and deduplication. |
| **Notification Hub** | [`core/operations/notification_hub.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/notification_hub.py) | Notification deduplication, rate limiting, Asia/Jakarta quiet hours | **EXTEND.** Add `tenant_id` column to `operational_notifications` and enforce recipient privacy separation. |
| **Decision Engine** | *New in WP 8.5* | Deterministic operational recommendations and risk assessments | **NEW IMPLEMENTATION.** Synthesizes evidence, health, RCA, services, and SLA into explainable `OperationalDecision` entities. |
| **SLA Engine** | *New in WP 8.7* | Customer SLA calculation, downtime attribution, error budgets | **NEW IMPLEMENTATION.** Reproducible availability calculations, maintenance exclusion filtering, and error budget accounting. |

---

## 3. AUTHORITATIVE DATA OWNERSHIP & EVIDENCE CONSUMPTION

```
+-----------------------------------------------------------------------------------------+
|                               AUTHORITATIVE DATA REPOSITORIES                           |
|                                                                                         |
|  [Tenant Core]        [Customer Inventory]    [Edge Gateways]       [NMS & Telemetry]   |
|  - operational_tenants - operational_sites     - operational_gateways- nms_raw_metrics  |
|  - operational_users   - operational_devices   - operational_hb      - nms_5m_rollups   |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
|                              EVIDENCE AGGREGATION & GRAPH                               |
|                                                                                         |
|  UnifiedEvidenceService (NetworkEvidenceBundle) <---> NetworkKnowledgeGraph (GraphNodes)|
+-----------------------------------------------------------------------------------------+
                                           |
         +---------------------------------+--------------------------------+
         |                                 |                                |
         v                                 v                                v
+--------------------+            +--------------------+           +--------------------+
| RootCauseAnalysis  |            | Predictive Engine  |           | Dynamic Health     |
| (RCAReport)        |            | (TrendProjection)  |           | (HealthScores)     |
+--------------------+            +--------------------+           +--------------------+
         \                                 |                               /
          \                                |                              /
           v                               v                             v
+-----------------------------------------------------------------------------------------+
|                             OPERATIONAL DECISION INTELLIGENCE                           |
|                                                                                         |
|  OperationalDecisionEngine (WP 8.5)                                                     |
|  - Synthesizes RCA hypotheses + Health Dimensions + Capacity Risk + SLA Impact          |
|  - Produces prioritized, explainable OperationalDecision with clear alternatives        |
+-----------------------------------------------------------------------------------------+
         |                                                                  |
         v                                                                  v
+----------------------------------+              +------------------------------------+
|  SLA Engine (WP 8.7)             |              |  Multi-Tenant Incidents (WP 8.8)   |
|  - Availability & Downtime       |              |  - Tenant-Scoped Correlation       |
|  - Error Budget & SLA Exposure   |              |  - Notification Hub Filtering      |
+----------------------------------+              +------------------------------------+
```

---

## 4. TENANT CONTEXT RESOLUTION & PROTECTED BOUNDARIES

### 4.1 Resolution Flow
1. **API Requests:** FastAPI dependency extracts Bearer token or session cookie. `IdentityManager.validate_session()` validates the token and extracts `user_id`, `tenant_id`, and `role`.
2. **Context Binding:** The request handler executes within `with tenant_scope(context):`.
3. **Internal NOC vs Customer Scope:**
   - Users with internal NOC roles (`PLATFORM_SUPER_ADMIN`, `NOC_ADMIN`, `NOC_OPERATOR`) can operate globally or assume a specific tenant scope.
   - Users with customer roles (`CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR`, `CUSTOMER_VIEWER`) are strictly locked to their own `tenant_id`. Any request passing a differing `tenant_id` is rejected immediately.
4. **Background / Engine Jobs:** Scheduled jobs run with explicit tenant context attached to job parameters (`parameters_json.tenant_id`).

### 4.2 Data Paths Requiring Schema Extension & Scoping
The audit identified 4 existing operational tables in `core/operations/db.py` that currently lack `tenant_id` columns:
1. `operational_services`: Must be altered or extended to include `tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id)` and `site_id TEXT REFERENCES operational_sites(site_id)`.
2. `operational_service_endpoints`: Automatically inherits tenant via `service_id`, but adding `tenant_id` enables direct indexing.
3. `operational_incidents`: Must be extended to include `tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id)` and `site_id TEXT REFERENCES operational_sites(site_id)`.
4. `operational_notifications`: Must be extended to include `tenant_id TEXT REFERENCES operational_tenants(tenant_id)`.

---

## 5. RESOURCE & PERFORMANCE CONSTRAINTS (THINKPAD X270)

The target hardware profile (Intel Core i7-7500U, 8 GB RAM, CPU-Only) dictates strict performance boundaries:
1. **No In-Memory Graph Cloning:** Scenarios for change impact and blast radius must run virtual non-destructive graph traversals (e.g. tracking temporary excluded node/edge IDs) rather than duplicating the entire knowledge graph in memory.
2. **Deterministic Computation:** Health scoring, risk metrics, and SLA calculations must be pure Python/NumPy arithmetic. No LLM invocation is permitted in telemetry loops or health score queries.
3. **Bounded Database Queries:** All historical metric lookups must use indexed time ranges (`WHERE measured_at BETWEEN ? AND ?`) and 5-minute rollups for windows $> 6\text{ hours}$, avoiding full-table scans.
4. **Pagination and Batching:** API endpoints returning decisions, incidents, or SLA logs must enforce server-side pagination (`LIMIT` / `OFFSET`) with a default limit of 50.

---

## 6. PHASE C WORK PACKAGE EXECUTION ROADMAP

- **WP 8.5:** Operational Decision Intelligence Core (`core/operations/decision_engine.py`, domain models, state machine, prioritization algorithm).
- **WP 8.5.1:** Dynamic Health Scoring (`core/operations/health_scoring_engine.py`, 6-dimension scoring, explanation generator).
- **WP 8.6:** Risk & Impact Assessment (`core/operations/risk_engine.py`, blast radius calculation, scenario comparison without graph mutation).
- **WP 8.7:** SLA & Service Management (`core/operations/sla_engine.py`, reproducible uptime/downtime formulas, maintenance exclusion, error budget tracking).
- **WP 8.8:** Multi-Tenant Incident Orchestration (`core/operations/multi_tenant_incident_engine.py`, tenant-scoped correlation, deduplication, notification scoping).
- **WP 8.9:** REST API Routers & Frontend Decision Center (`api/routers/decisions.py`, `app/frontend/src/pages/DecisionsPage.jsx`).
- **WP 8.10:** Security, Adversarial & Performance Verification Suite (`tests/test_networking_viii_phase_c.py`, `scripts/benchmark_networking_viii_decision.py`).

---

## 7. AUDIT SIGN-OFF
The audit confirms that all prerequisites for Phase C are in place. Existing components (`UnifiedEvidenceService`, `RootCauseAnalysisEngine`, `NetworkKnowledgeGraph`, `PredictiveOperationsEngine`) provide a solid foundation and will be reused without duplicate subsystems.

**Phase C implementation is cleared to begin with Work Package 8.5.**
