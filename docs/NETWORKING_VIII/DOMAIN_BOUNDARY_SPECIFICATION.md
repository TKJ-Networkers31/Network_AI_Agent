# AIRA OS — NETWORKING VIII: DOMAIN BOUNDARY SPECIFICATION
## Bounded Contexts, Entity Ownership & Interface Contracts

**Document ID:** `AIRA-NET8-DOMAIN-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Target Milestone:** Networking VIII  
**Organization:** LS Technology

---

## 1. Domain Architecture Overview

To maintain high cohesion, low coupling, and prevent circular dependencies in a modular monolith, the system is partitioned into **16 Bounded Contexts**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TENANT & IDENTITY CONTEXTS                      │
│     ┌─────────────────┐       ┌────────────────┐       ┌─────────────┐ │
│     │ Identity & RBAC │ <---> │  Tenant Core   │ <---> │Organization │ │
│     └─────────────────┘       └────────────────┘       └─────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Provides TenantContext & UserPrincipal)
┌───────────────────────────────────▼────────────────────────────────────┐
│                        INFRASTRUCTURE CONTEXTS                         │
│     ┌─────────────────┐       ┌────────────────┐       ┌─────────────┐ │
│     │   Site & Group  │ <---> │  Edge Gateway  │ <---> │  Inventory  │ │
│     └─────────────────┘       └────────────────┘       └─────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Supplies Device & Telemetry Facts)
┌───────────────────────────────────▼────────────────────────────────────┐
│                        INTELLIGENCE & OPERATIONS                       │
│     ┌─────────────────┐       ┌────────────────┐       ┌─────────────┐ │
│     │ Unified Evidence│ ----> │  Intelligence  │ ----> │  Decision   │ │
│     └─────────────────┘       └────────────────┘       └─────────────┘ │
│              │                         │                       │       │
│     ┌────────▼────────┐       ┌────────▼───────┐       ┌───────▼─────┐ │
│     │    Incidents    │ <---> │   Operations   │ <---> │  SLA & Serv │ │
│     └─────────────────┘       └────────────────┘       └─────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Operational Events & Records)
┌───────────────────────────────────▼────────────────────────────────────┐
│                          GOVERNANCE CONTEXTS                           │
│     ┌─────────────────┐       ┌────────────────┐       ┌─────────────┐ │
│     │   Maintenance   │ <---> │   Reporting    │ <---> │    Audit    │ │
│     └─────────────────┘       └────────────────┘       └─────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Bounded Context Specifications

### 2.1 Identity & RBAC Context (`core.tenant.identity`)
- **Primary Entities:** `User`, `UserRole`, `Permission`, `UserSession`, `AuthToken`.
- **Ownership:** User accounts, password hashes (Argon2 / PBKDF2), session tokens, permission resolution.
- **Invariants:**
  - Password hashes are never returned by any query or serialized in logs.
  - Users are strictly divided into Internal NOC users (`is_internal=True`) and Customer users (`is_internal=False`, bound to exactly one `tenant_id`).
  - Customer users can never be granted NOC operational roles.

### 2.2 Tenant Core Context (`core.tenant.core`)
- **Primary Entities:** `Tenant`, `TenantConfiguration`, `TenantSubscription`, `TenantResourceQuota`.
- **States:** `PROVISIONING`, `ACTIVE`, `SUSPENDED`, `MAINTENANCE`, `DECOMMISSIONED`.
- **Ownership:** Multi-tenant boundaries, organization mapping, feature toggles, quota enforcement (max sites, max devices, max gateways, retention days).
- **Invariants:**
  - `tenant_id` is globally unique, immutable, and prefixed (e.g. `tenant_c1a2...`).
  - Decommissioned tenants immediately reject all API requests, ingestion, and job runs.

### 2.3 Organization & Customer Context (`core.tenant.organization`)
- **Primary Entities:** `CustomerProfile`, `OrganizationContact`, `BillingDetails`.
- **Ownership:** Customer company name, contact phone, primary email, SLA contract tier.

### 2.4 Site & SiteGroup Context (`core.tenant.site`)
- **Primary Entities:** `Site`, `SiteGroup`, `SiteAddress`.
- **Ownership:** Physical and logical network locations within a tenant.
- **Invariants:**
  - Every site belongs to exactly one `tenant_id`.
  - Multiple sites within a tenant can share an identical timezone (default `Asia/Jakarta`).

### 2.5 Edge Gateway Context (`core.edge_gateway`)
- **Primary Entities:** `EdgeGateway`, `GatewayEnrollmentToken`, `GatewayHeartbeat`, `TelemetryIngestionEnvelope`.
- **Ownership:** Outbound gateway connections, short-lived single-use enrollment tokens, mutual TLS certificate fingerprints, gateway health status, buffer metrics.
- **Invariants:**
  - A gateway is bound to exactly one `(tenant_id, site_id)`.
  - Enrollment tokens are single-use, cryptographically random, expire in 15 minutes, and are immediately marked `REVOKED` upon redemption.
  - Gateway commands are strictly allowlisted; arbitrary shell execution is blocked.

### 2.6 Customer Network Inventory Context (`core.tenant.inventory`)
- **Primary Entities:** `TenantDevice`, `DeviceSiteMapping`, `ConnectionProfile`.
- **Ownership:** Scoped device identity, management endpoints, device credentials reference.
- **Invariants:**
  - Uniqueness is scoped: `(tenant_id, site_id, device_id)` or `(tenant_id, site_id, management_ip)`.
  - Overlapping RFC 1918 subnets across separate tenants (e.g. Tenant A `192.168.1.1` vs Tenant B `192.168.1.1`) are cleanly isolated.

### 2.7 Unified Evidence Context (`core.network_intelligence.evidence_service`)
- **Primary Entities:** `CanonicalEvidenceRecord`, `NetworkEvidenceBundle`.
- **Ownership:** Evidence normalization, provenance timestamps, data quality scores, freshness tracking.
- **Invariants:**
  - Assembles evidence strictly from cached NMS bundles without initiating live hardware connections.
  - Bundle projection is filtered by `tenant_id` before handoff to consumers.

### 2.8 Intelligence & RCA Context (`core.network_intelligence`)
- **Primary Entities:** `NetworkKnowledgeGraph`, `RootCauseHypothesis`, `AnomalyRecord`.
- **Ownership:** Graph reachability, dependency topology, causal diagnosis, baseline z-score modeling.
- **Invariants:**
  - Each tenant operates on an isolated graph projection. Causal correlation never crosses tenant boundaries.

### 2.9 Operational Decision Context (`core.decision`)
- **Primary Entities:** `OperationalDecision`, `RecommendationAction`, `RiskAssessment`, `ApprovalRecord`.
- **Ownership:** Operational risk scoring (0–100), explainable decision generation, human approval state machine (`GENERATED` $\rightarrow$ `UNDER_REVIEW` $\rightarrow$ `APPROVED` $\rightarrow$ `REJECTED` $\rightarrow$ `COMPLETED`).
- **Invariants:**
  - Every recommendation must cite underlying evidence IDs and affected service IDs.
  - Approval records capture the operator identity, timestamp, and justification.
  - Approvals never trigger automatic router configuration mutations.

### 2.10 Service & SLA Context (`core.sla`)
- **Primary Entities:** `OperationalService`, `SlaPolicy`, `SlaMeasurementWindow`, `ErrorBudget`.
- **Ownership:** Service catalog, endpoint bindings, availability calculations, SLA compliance reports.
- **Invariants:**
  - Missing telemetry remains explicit (`None`) and cannot be treated as 100% uptime or fabricated downtime.
  - Planned maintenance windows with `suppress_alerts=1` are excluded from SLA downtime calculation.

### 2.11 Operational Incidents Context (`core.operations.incident_engine`)
- **Primary Entities:** `OperationalIncident`, `IncidentAuditTrail`.
- **Ownership:** Multi-tenant incident lifecycle (`DETECTED` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `INVESTIGATING` $\rightarrow$ `MITIGATED` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED`).
- **Invariants:**
  - Incidents are scoped to `(tenant_id, site_id)`.
  - Cross-site correlation is permitted only within the same tenant.

### 2.12 Maintenance & Calendar Context (`core.operations.calendar`)
- **Primary Entities:** `MaintenanceWindow`, `CalendarEvent`.
- **Ownership:** Local maintenance registry, RFC 5545 `.ics` export/import, Google Calendar sync.
- **Invariants:**
  - Maintenance windows are tenant-isolated. Alerts are suppressed only for target entities within the owning tenant.

### 2.13 Operational Scheduler Context (`core.operations.scheduler`)
- **Primary Entities:** `OperationalJob`, `OperationalJobRun`.
- **Ownership:** Persistent job scheduler in `Asia/Jakarta`, execution history, missed job recovery.
- **Invariants:**
  - Jobs execute in the context of their owning `tenant_id`.
  - Jobs never connect to router hardware directly.

### 2.14 Controlled Reporting Context (`core.operations.reporting_engine`)
- **Primary Entities:** `OperationalReport`, `ReportExport`.
- **Ownership:** Deterministic Daily/Weekly/Monthly/SLA reports in Markdown, HTML, and JSON.
- **Invariants:**
  - Data retrieval is filtered by authenticated `tenant_id` before compilation.

### 2.15 Notification Hub Context (`core.operations.notification_hub`)
- **Primary Entities:** `OperationalNotification`, `QuietHoursPolicy`.
- **Ownership:** Deduplication fingerprints, cooldown intervals, quiet hours queuing (22:00–07:00 WIB).
- **Invariants:**
  - Customer notifications never contain internal NOC-only evidence or secrets.

### 2.16 Audit Context (`core.tenant.audit`)
- **Primary Entities:** `PlatformAuditEntry`.
- **Ownership:** Append-only tamper-resistant log of operator logins, permission changes, gateway enrollments, decision approvals, and configuration exports.
