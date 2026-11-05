# AIRA OS — NETWORKING VIII: MASTER ENGINEERING EXECUTION PLAN
## Roadmap, Phased Rollout, Release Gates & Risk Management

**Document ID:** `AIRA-NET8-PLAN-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Target Milestone:** Networking VIII (WP 8.0 through WP 8.17)  
**Organization:** LS Technology

---

## 1. Phased Engineering Execution Strategy

Networking VIII follows a strictly staged, evidence-driven execution model where each phase must pass an explicit **Release Gate** before advancing to subsequent development.

```
┌────────────────────────────────────────────────────────┐
│ PHASE A: ARCHITECTURE & FOUNDATIONS (WP 8.0 – WP 8.3)  │
│ ├── Baseline Audit & Architecture Specifications       │
│ ├── Multi-Tenant Core Models & DB Schema (topology.db) │
│ ├── Identity, RBAC & Tenant Context Middleware         │
│ └── Customer Network Inventory (Overlap RFC1918 Safe)  │
│ RELEASE GATE A: Zero regressions, models stable, isolation verified
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ PHASE B: HYBRID INFRASTRUCTURE (WP 8.4)                │
│ ├── Edge Gateway Architecture & Identity               │
│ ├── Secure Enrollment Token Protocol                   │
│ ├── Outbound WSS Telemetry Ingestion Hub               │
│ └── Bounded Local Buffer & Replay-Safe Deduplication   │
│ RELEASE GATE B: Gateway enrolled, cross-tenant enrollment blocked
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ PHASE C: DECISION INTELLIGENCE (WP 8.5 – WP 8.7)       │
│ ├── Operational Decision Engine & Risk Scoring         │
│ ├── Human Approval State Machine & Audit Trail         │
│ ├── Non-Destructive Scenario & Change Impact Planning  │
│ └── SLA Management, Error Budgets & Exclusions         │
│ RELEASE GATE C: Evidence-grounded decisions, reproducible SLAs
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ PHASE D: OPERATIONAL ORCHESTRATION (WP 8.8 – WP 8.9)   │
│ ├── Tenant-Aware Incident Orchestration & Cross-Site   │
│ ├── Persistent Scheduler Tenant Scoping (Asia/Jakarta) │
│ └── Multi-Tenant Calendar & Maintenance Windows        │
│ RELEASE GATE D: Tenant-isolated jobs, incidents, and calendar
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ PHASE E: PRODUCT EXPERIENCE (WP 8.10 – WP 8.12)        │
│ ├── React Customer Portal Page (`CustomerPortalPage`)   │
│ ├── Extended Internal NOC Operations Center UI         │
│ └── Tenant-Authorized REST API & WebSocket Isolation   │
│ RELEASE GATE E: UI separation verified, production build OK
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ PHASE F: HARDENING & ACCEPTANCE (WP 8.13 – WP 8.17)    │
│ ├── Adversarial Security & IDOR Verification           │
│ ├── Performance & Resource Hardening (ThinkPad X270)   │
│ ├── Observability & Health Endpoints                   │
│ └── Comprehensive Regression & Final Release Report    │
│ RELEASE GATE F: NETWORKING_VIII_COMPLETE_AND_VERIFIED  │
└────────────────────────────────────────────────────────┘
```

---

## 2. Work Package Breakdown & Milestones

### 2.1 Phase A: Architecture and Foundations
- **WP 8.0 Architecture Audit & Design:** (Completed in documentation).
- **WP 8.1 Multi-Tenant Core:**
  - Entities: `Tenant`, `TenantConfiguration`, `TenantSubscription`, `TenantResourceQuota`.
  - Storage: `operational_tenants`, `operational_tenant_subscriptions`, `operational_tenant_quotas` in `topology.db`.
  - Isolation: Centralized `TenantContext` resolution.
- **WP 8.2 Identity and RBAC:**
  - Roles: Internal NOC (`NOC_ADMIN`, `NOC_OPERATOR`, `NETWORK_ENGINEER`, `NOC_ANALYST`, `AUDITOR`) and Customer (`CUSTOMER_OWNER`, `CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR`, `CUSTOMER_VIEWER`).
  - Storage: `operational_users`, `operational_user_roles`, `operational_user_sessions`.
  - Authentication: Cryptographic token generation, expiration, password hashing, permission matrices.
- **WP 8.3 Customer Network Inventory:**
  - Entities: `Site`, `SiteGroup`, `TenantDevice`.
  - Storage: `operational_sites`, `operational_site_groups`, `operational_devices`.
  - Overlap Safety: Scoped lookups `(tenant_id, site_id, management_ip)`.

### 2.2 Phase B: Hybrid Infrastructure
- **WP 8.4 Edge Gateway:**
  - Core Modules: `core/edge_gateway/gateway_models.py`, `gateway_manager.py`, `enrollment.py`, `ingestion.py`.
  - Enrollment Tokens: Single-use, 15-minute expiry, SHA-256 hashed storage.
  - Telemetry Ingestion: Envelope validation, sequence checking, and buffer draining.
  - Zero Mutation: Strict command allowlisting.

### 2.3 Phase C: Operational Decision Intelligence
- **WP 8.5 Operational Decision Engine:**
  - Model: `OperationalDecision`, deterministic risk scoring (0–100) based on severity, blast radius, SLA tier, and evidence confidence.
  - Approval: State machine (`GENERATED` $\rightarrow$ `UNDER_REVIEW` $\rightarrow$ `APPROVED` $\rightarrow$ `REJECTED` $\rightarrow$ `COMPLETED`).
- **WP 8.6 Risk, Impact and Scenario Planning:**
  - Multi-tenant in-memory graph simulation with before/after state hashing.
- **WP 8.7 SLA and Service Management:**
  - Configurable SLA policies (`sla_target_percent`, error budgets, MTTD/MTTR).
  - Deterministic availability calculations excluding planned maintenance.

### 2.4 Phase D: Operational Orchestration
- **WP 8.8 Incident Orchestration:**
  - Multi-tenant incident state transitions with cross-site intra-tenant correlation.
- **WP 8.9 Maintenance and Capacity Planning:**
  - Tenant-isolated jobs in `OperationalSchedulerEngine` (`Asia/Jakarta`).
  - Tenant-scoped maintenance windows in `CalendarManager`.

### 2.5 Phase E: Product Experience
- **WP 8.10 Customer Portal:**
  - React page for customer users showing only authorized tenant telemetry, incidents, and SLA metrics.
- **WP 8.11 Internal NOC Operations Center:**
  - Extended multi-tenant fleet overview with tenant switcher, cross-tenant operational indicators, and decision approval console.
- **WP 8.12 API and Event Architecture:**
  - REST endpoints mounted under `/api/v1/tenant/`, `/api/v1/gateway/`, `/api/v1/decision/`.
  - WebSocket event bridge filtering by `tenant_id`.

### 2.6 Phase F: Hardening and Acceptance
- **WP 8.13 Security and Adversarial Audit:** IDOR penetration testing, token replay, privilege escalation tests.
- **WP 8.14 Performance and Resource Optimization:** Benchmark under 10, 25, 50 tenants on ThinkPad X270 profile.
- **WP 8.15 Observability:** Central platform health endpoints (`/api/v1/health/platform`, `/api/v1/health/gateways`).
- **WP 8.16 Testing Strategy:** Unit, integration, E2E acceptance tests.
- **WP 8.17 Documentation:** Comprehensive final release report and roadmap update.

---

## 3. Risk Management & Mitigation Register

| Risk ID | Risk Description | Severity | Probability | Architectural Mitigation |
| :--- | :--- | :---: | :---: | :--- |
| **R1** | **Cross-Tenant Data Leakage (IDOR)** | CRITICAL | Low | Centralized `TenantContext` middleware; repository-level `WHERE tenant_id = ?` enforcement; automated IDOR test suite. |
| **R2** | **RFC 1918 IP Collision Across Tenants** | HIGH | High | Device identity composite key `(tenant_id, site_id, device_id)`; device IDs generated with globally unique UUIDs. |
| **R3** | **Memory Exhaustion on ThinkPad X270** | HIGH | Medium | Shared SQLite database in WAL mode; LRU caching for in-memory graphs (max 5 active); bounded thread pools (`max_workers=2`). |
| **R4** | **Edge Gateway Replay or Impersonation** | HIGH | Low | Single-use enrollment tokens; mutual TLS / certificate fingerprints; strictly increasing sequence numbers. |
| **R5** | **Accidental Router Mutation** | CRITICAL | Low | 100% read-only policy preserved; zero mutating verbs in codebase; human approval cannot trigger configuration pushes. |
| **R6** | **Unbounded Local Telemetry Queue at Edge** | MEDIUM | Medium | Hard cap of 5,000 samples / 24 hours; oldest drop FIFO policy; backpressure alert to Central NOC. |
