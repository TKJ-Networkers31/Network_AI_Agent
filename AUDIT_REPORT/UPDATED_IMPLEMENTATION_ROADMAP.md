# AIRA OS — UPDATED IMPLEMENTATION ROADMAP (`UPDATED_IMPLEMENTATION_ROADMAP.md`)

**Date**: 2026-11-08  
**Status**: ACTIVE & AUTHORITATIVE  
**Branch**: `remediation/master-execution`  
**Governing Documents**:
- `AIRA_OS_MASTER_DECISION_AND_EXECUTION_PLAN.md`
- `AUDIT_REPORT/DECISION_USER_TOKEN_QUOTA_REMOVAL.md`
- `AUDIT_REPORT/DECISION_GUEST_MODE_REMOVAL.md`

---

## 1. RECONCILED STAGE OVERVIEW

| Stage | Target Subsystem | Scope & Key Remediations | Test Gate & Artifacts | Status |
|---|---|---|---|:---:|
| **Stage 0** | Baseline Protection | Source tree verification, baseline snapshot, working tree lock. | `IMPLEMENTATION_BASELINE.md` | **PASSED** |
| **Stage 1** | Build, Dependency & CI | FastAPI/Uvicorn in Docker & CI, fix `Optional` in `history.py`, `npm test` fix in `ci.yml`, `.dockerignore`, break MCP layer inversion (`masking.py`), lazy audio models. | `IMPLEMENTATION_STAGE_01_REPORT.md` (100 collected, 240 frontend pass) | **PASSED** |
| **Stage 2** | Security Hardening & Complete Removals | **(A) Complete Billing Removal**: Purged all billing routes, services, tables, tests.<br>**(B) Complete Guest Mode Removal**: Purge `GUEST` role, eliminate `X-Guest-ID` and frontend bypass.<br>**(C) Complete Token Quota Removal**: Purge `operational_token_*` tables, services, deductions.<br>**(D) Critical Security**: Protect unauthenticated endpoints (`connections.py`, `files.py`, `settings.py`, `ws.py`, `automations.py`, `voice.py`), fix `BUG-04` viewer escalation, fix group `DENY` rule evaluation (`BUG-24`), separate M2M tokens, tag NAT comment (`BUG-05`), remove SSH password fallback. | `IMPLEMENTATION_STAGE_02_REPORT.md`<br>`BILLING_REMOVAL_REPORT.md`<br>`GUEST_MODE_REMOVAL_REPORT.md`<br>`USER_TOKEN_QUOTA_REMOVAL_REPORT.md` | **IN PROGRESS** |
| **Stage 3** | Secret Security & Database Safety | Online Backup API (`sqlite3.Connection.backup()`), backup & restore rehearsal on temporary copy, secret encryption vault for router passwords & API keys. | `IMPLEMENTATION_STAGE_03_REPORT.md` | PENDING |
| **Stage 4** | Schema Reconciliation & SSOT | Reconcile `nms_raw_metrics` collision (`BUG-06`), `nms_device_metrics` timestamps, unify device inventory into `operational_devices`, FK integrity check. | `IMPLEMENTATION_STAGE_04_REPORT.md`<br>`DATABASE_MIGRATION_AND_RESTORE_REPORT.md` | PENDING |
| **Stage 5** | User Data, Memory & Persona Isolation | Scoped chat sessions, memories, personas in `topology.db`. Zero cross-user/tenant data leakage. Purge hardcoded GPS fallback. | `IMPLEMENTATION_STAGE_05_REPORT.md` | PENDING |
| **Stage 6** | Core Backend Functional Bugs | Fix confirmed bugs (`BUG-01` to `BUG-45`): route shadowing (`/api/devices/bulk`), VisionResult mismatch (`BUG-09`), Edge Gateway UTC/ping flags, intelligence attribute mismatches. | `IMPLEMENTATION_STAGE_06_REPORT.md` | PENDING |
| **Stage 7** | AI Provider Reliability & Fallback | Multi-provider fallback chain (NEW-01), NVIDIA timeout handling, task classifier resilience, auto-memory extraction error handling. | `IMPLEMENTATION_STAGE_07_REPORT.md`<br>`AI_PROVIDER_RELIABILITY_REPORT.md` | PENDING |
| **Stage 8** | Vision & OCR Subsystem | Ground-truth test fixtures (NEW-02), scanned PDF OCR, table extraction, VisionResult constructor compatibility. | `IMPLEMENTATION_STAGE_08_REPORT.md`<br>`VISION_OCR_REPORT.md` | PENDING |
| **Stage 9** | Network Tools, NMS & Traceroute | Traceroute binary discovery (NEW-03), structured hop parser, honest status labels, NMS poller & alert engine, RouterOS v6/v7 lab safety. | `IMPLEMENTATION_STAGE_09_REPORT.md`<br>`TRACEROUTE_REPORT.md` | PENDING |
| **Stage 10** | Frontend Integration & UX | Fix `NmsPage` crash (`handleSnmpConfigure`), SSE stream parser contract, URL routing, remove legacy billing/guest/quota UI fragments. | `IMPLEMENTATION_STAGE_10_REPORT.md` | PENDING |
| **Stage 11** | Network Intelligence Consolidation | Consolidate 3 overlapping intelligence generations, dry-run & approval gates for risky network actions, RouterOS version detection. | `IMPLEMENTATION_STAGE_11_REPORT.md` | PENDING |
| **Stage 12** | Dead Code & Duplication Cleanup | Verified cleanup of 42 dead source files and legacy backups after checking dynamic references, import verification, and test suite green. | `IMPLEMENTATION_STAGE_12_REPORT.md` | PENDING |
| **Stage 13** | Performance Optimization | Eliminate write-on-read lock contention in `validate_session_token`, optimize `score_tenant()` transactions, debounce `/api/connections` polling. | `IMPLEMENTATION_STAGE_13_REPORT.md` | PENDING |
| **Stage 14** | Production Readiness & Final Verification | Full test suite across all layers, clean Docker build, CI pass, final readiness report. | `IMPLEMENTATION_STAGE_14_REPORT.md`<br>`FINAL_REMEDIATION_REPORT.md` | PENDING |
