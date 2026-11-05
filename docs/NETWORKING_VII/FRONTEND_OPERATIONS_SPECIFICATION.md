# AIRA OS — NETWORKING VII
# FRONTEND OPERATIONS CENTER SPECIFICATION (WP 7.10)

**Component File:** `AIRA_ECOSYSTEM/app/frontend/src/pages/OperationsPage.jsx`  
**Route / Nav Key:** `operations`  
**Phase:** Phase H — Reporting, API Layer & Frontend Operations Center  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Architectural Role

The **Operations Center** (`OperationsPage.jsx`) provides the unified web experience for proactive network operations, integrating all Networking VII capabilities into a responsive single-pane-of-glass interface.

It is registered as a first-class route in `App.jsx` using `lazyWithRetry` code-splitting, accessible through the `Operations Center` sidebar item under the `network` navigation group.

---

## 2. Tabbed Architecture & Feature Matrix

| Tab ID | View Title | Key Visual Components | Operational Workflows |
| :--- | :--- | :--- | :--- |
| `overview` | Operations Overview | Metric KPI Cards (Health Score, Warnings, Incidents, Windows), Upcoming Horizons Table, Business Services Summary | At-a-glance health triage, quick navigation to degraded domains |
| `predictive` | Predictive Forecasts | Multi-metric trend table, saturation horizons ($T_{\text{warn}}$, $T_{\text{crit}}$), confidence level badges, risk tags (`CRITICAL`, `WARNING`, `WATCH`, `INFO`) | Capacity planning, bandwidth saturation review |
| `change_simulator` | Change Simulator | Scenario builder form (Interface Down, Route Withdrawal, Reboot), in-memory simulation runner, blast-radius visualizer, preflight & rollback command display | Pre-maintenance validation, change advisory board (CAB) reviews |
| `services` | Business Services | Business service cards, criticality tier tags, endpoint list, health status ($0 - 100\%$) | Application dependency mapping, SLA impact analysis |
| `scheduler` | Job Scheduler | Persistent jobs list, cron/interval schedule display, manual "Run Now" triggers, execution logs | Operational workflow automation, maintenance trigger verification |
| `calendar` | Maintenance Calendar | Maintenance window timeline, local/Google/ICS source badge, one-click RFC 5545 `.ics` export download | Maintenance coordination, alert suppression tracking |
| `incidents` | Proactive Incidents | Incident cards, severity badges, remediation plan view, state transition controls | Preventative incident tracking before customer impact |
| `reports` | Operational Reports | Period selector (Daily / Weekly / Monthly), generation trigger, live Markdown viewer | Executive reporting, daily handover summaries |
