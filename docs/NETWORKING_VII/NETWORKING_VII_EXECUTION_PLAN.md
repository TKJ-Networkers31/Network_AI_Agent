# AIRA OS — NETWORKING VII
# MASTER EXECUTION PLAN & GATED ROADMAP
## Sequential Autonomous Engineering Workflow (WP 7.0–7.13)

**Document Version:** 1.0.0  
**Phase:** Phase A — Architecture & Domain Audit  
**Work Package:** WP 7.0  
**Status:** AUTHORITATIVE EXECUTION BLUEPRINT  
**Total Work Packages:** WP 7.0 through WP 7.13 across 9 Sequential Phases (Phases A through I)  
**Target Environment:** Windows 10/11, ThinkPad X270, Intel i7-7500U, 8 GB RAM, CPU-Only

---

## 1. Execution Principles & Phase Gates

To ensure strict engineering quality, reliability, and zero regression of existing Networking IV, V, and VI capabilities, this campaign proceeds through **9 Sequential Phases**. 

### Universal Quality Invariants:
1. **Gate Enforcement:** A phase cannot be marked complete until all its mandatory unit/integration tests pass 100% and its designated architectural documentation is delivered.
2. **Regression Immutability:** Existing test suites (`test_networking_iv_e2e_acceptance.py`, `test_wp_5_*.py`, `test_networking_vi_*.py`) must continue to pass at 100% throughout the entire campaign.
3. **Zero Device Mutation:** Under no circumstances shall test or production code mutate live RouterOS lab devices (`CHR` @ 10.26.213.30, `R-1` @ 192.168.0.1).
4. **Git Safety:** Zero commits, zero pushes, no destructive git commands (`git reset --hard`, `git clean -fd`).

---

## 2. Phase-by-Phase Roadmap

### Phase A: Architecture, Domain Modeling & Anti-Duplication Audit (WP 7.0)
- **Status:** ACTIVE
- **Deliverables:**
  - `docs/NETWORKING_VII/NETWORKING_VII_ARCHITECTURE.md` (Delivered)
  - `docs/NETWORKING_VII/EXISTING_CAPABILITY_REUSE_MATRIX.md` (Delivered)
  - `docs/NETWORKING_VII/NETWORKING_VII_EXECUTION_PLAN.md` (Delivered)
- **Exit Gate:** Architectural blueprints ratified, anti-duplication proofs verified, database schema finalized.

---

### Phase B: Predictive Operations Engine (WP 7.1)
- **Scope:** Multi-window time series analysis, bandwidth saturation forecasting, error acceleration detection, CPU/memory trend regression, and explainable risk scoring.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/predictive_engine.py`
  - `AIRA_ECOSYSTEM/core/operations/models.py` (Domain models for predictive results, projections, risk levels)
  - `docs/NETWORKING_VII/PREDICTIVE_OPERATIONS_SPECIFICATION.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_predictive.py`
- **Exit Gate:**
  - Robust trend fitting (Rolling Median, MAD, Linear Regression).
  - Time-to-saturation calculations for 80% and 95% thresholds.
  - Epistemic rules verified: `None` missing data preserved, $N < 10$ flagged as `INSUFFICIENT_DATA`, limitations declared.
  - 100% test pass on predictive suite.

---

### Phase C: Network Change Impact Intelligence (WP 7.2)
- **Scope:** Pre-change analytical simulation on in-memory cloned graphs; blast-radius calculation for interface shutdowns, VLAN modifications, route removals, and device reboots.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/change_impact_engine.py`
  - `docs/NETWORKING_VII/CHANGE_IMPACT_INTELLIGENCE_SPECIFICATION.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_change_impact.py`
- **Exit Gate:**
  - Simulation runs exclusively on cloned graphs with zero database or device mutation.
  - Differentiates direct vs indirect blast radius and flags loss of redundancy (SPOF).
  - Generates clear pre-flight checklist and rollback plan.
  - 100% test pass on change impact suite.

---

### Phase D: Service Dependency Intelligence (WP 7.3)
- **Scope:** Mapping business services and endpoints to network transit paths, devices, and interfaces; health aggregation and service-level blast radius.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/service_intelligence.py`
  - `docs/NETWORKING_VII/SERVICE_DEPENDENCY_INTELLIGENCE.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_service_intelligence.py`
- **Exit Gate:**
  - CRUD operations for business services and endpoints in `topology.db`.
  - Ingestion of `SERVICE` and `ENDPOINT` nodes and `SERVES`/`DEPENDS_ON` edges into `NetworkKnowledgeGraph`.
  - Accurate redundancy status (HA vs SPOF) and service health scoring ($0 - 100$).
  - 100% test pass on service intelligence suite.

---

### Phase E: Operational Scheduler Engine (WP 7.4)
- **Scope:** Persistent, timezone-aware (`Asia/Jakarta`) SQLite job store, cron/interval scheduling, missed execution handling, restart recovery, and built-in operational templates.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/scheduler.py`
  - `docs/NETWORKING_VII/SCHEDULER_ENGINE_SPECIFICATION.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_scheduler.py`
- **Exit Gate:**
  - SQLite persistent jobs survive process restarts.
  - Handles missed jobs with configured strategy (`RUN_IMMEDIATELY`, `SKIP`, `RESCHEDULE`).
  - Timezone conversion to `Asia/Jakarta` verified with zero drift.
  - Zero direct network device polling (only reads cached evidence from `UnifiedEvidenceService`).
  - 100% test pass on scheduler suite.

---

### Phase F: External Calendar Integration (WP 7.5)
- **Scope:** Provider abstraction (`CalendarProvider`), Local SQLite provider, RFC 5545 `.ics` generator and parser, Google Calendar API OAuth 2.0 integration, and maintenance window sync.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/calendar/base.py`
  - `AIRA_ECOSYSTEM/core/operations/calendar/local_provider.py`
  - `AIRA_ECOSYSTEM/core/operations/calendar/ics_provider.py`
  - `AIRA_ECOSYSTEM/core/operations/calendar/google_provider.py`
  - `docs/NETWORKING_VII/CALENDAR_INTEGRATION_SPECIFICATION.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_calendar.py`
- **Exit Gate:**
  - Local provider functions 100% offline.
  - RFC 5545 `.ics` export/import passes validation.
  - Google OAuth token management and maintenance window sync with alert suppression verified.
  - 100% test pass on calendar suite.

---

### Phase G: Proactive Incident & Controlled Notification Intelligence (WP 7.6 & 7.7)
- **Scope:** Structured incident lifecycle (`DETECTED` $\rightarrow$ `CLOSED`), automated linking from predictive risks, alert deduplication, cooldown windows, quiet hours (`Asia/Jakarta`), and WebSocket notifications.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/incident_engine.py`
  - `AIRA_ECOSYSTEM/core/operations/notification_hub.py`
  - `docs/NETWORKING_VII/PROACTIVE_INCIDENT_INTELLIGENCE.md`
  - `docs/NETWORKING_VII/NOTIFICATION_ENGINE_SPECIFICATION.md`
- **Testing:** `AIRA_ECOSYSTEM/tests/test_networking_vii_incidents_notifications.py`
- **Exit Gate:**
  - Incident transitions enforce strict state validation.
  - Notification deduplication eliminates alert storms.
  - Quiet hours hold `INFO`/`LOW`/`MEDIUM` while allowing `CRITICAL` alerts to pass immediately.
  - 100% test pass on incident and notification suite.

---

### Phase H: Operational Reporting, API Layer & React Operations Center (WP 7.8, 7.9, 7.10)
- **Scope:** Deterministic daily/weekly/monthly reports; FastAPI `/api/operations/*` endpoints; React Operations Center UI with 7 rich operational tabs.
- **Key Modules:**
  - `AIRA_ECOSYSTEM/core/operations/reporting_engine.py`
  - `AIRA_ECOSYSTEM/api/routers/operations.py`
  - `AIRA_ECOSYSTEM/app/frontend/src/pages/OperationsPage.jsx`
  - React components under `AIRA_ECOSYSTEM/app/frontend/src/components/operations/`
  - `docs/NETWORKING_VII/OPERATIONAL_REPORTING_SPECIFICATION.md`
  - `docs/NETWORKING_VII/API_SPECIFICATION.md`
  - `docs/NETWORKING_VII/FRONTEND_OPERATIONS_SPECIFICATION.md`
- **Testing:**
  - Backend API integration tests: `AIRA_ECOSYSTEM/tests/test_networking_vii_api.py`
  - Frontend Vitest suite & production build check (`npm run build`).
- **Exit Gate:**
  - All `/api/operations/*` endpoints return compliant schemas.
  - Frontend builds with zero syntax or bundling errors.
  - Interactive simulator, calendar, and trend charts render smoothly.

---

### Phase I: Full System Verification, Performance Hardening & Final Release (WP 7.11–7.13)
- **Scope:** Full regression across all existing suites, CPU/RAM benchmarking on ThinkPad X270 profile, adversarial security audits, and final release gate sign-off.
- **Key Modules & Artifacts:**
  - `AIRA_ECOSYSTEM/tests/test_networking_vii_e2e_acceptance.py`
  - `docs/NETWORKING_VII/BENCHMARK_REPORT.md`
  - `docs/NETWORKING_VII/FINAL_VERIFICATION_AND_RELEASE_REPORT.md`
- **Exit Gate:**
  - 100% pass across all tests (Networking IV, V, VI, VII + Vitest).
  - CPU usage during simulations < 25%, peak RAM delta < 15 MB.
  - Formally authorized release declaration: `NETWORKING_VII_COMPLETE_AND_VERIFIED`.
