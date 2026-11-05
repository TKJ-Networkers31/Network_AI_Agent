# AIRA OS — NETWORKING VIII: HYBRID MULTI-TENANT ARCHITECTURE BLUEPRINT
## Central NOC Platform & Customer Edge Gateway Design

**Document ID:** `AIRA-NET8-ARCH-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Target Milestone:** Networking VIII (Work Packages 8.0 through 8.17)  
**Organization:** LS Technology

---

## 1. High-Level Architectural Vision

Networking VIII establishes a **Hybrid Multi-Tenant Network Operations Center (NOC) Platform** engineered for Managed Service Providers (MSP) and enterprise operations teams. It enables LS Technology operators to centrally monitor, analyze, and make evidence-backed operational decisions across 10–50 customer organizations while maintaining absolute tenant isolation and zero-risk read-only boundaries.

```
                              LS TECHNOLOGY CENTRAL NOC
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   │                                           │
          Internal NOC Operator                         Customer Portal
       (Multi-Tenant Fleet View)                     (Tenant-Isolated View)
                   │                                           │
                   └─────────────────────┬─────────────────────┘
                                         │
                             Identity & RBAC Gateway
                         (Session / JWT & Tenant Scope)
                                         │
                           Multi-Tenant Control Plane
                  (Tenant Context • Resource Quotas • Audit Log)
                                         │
      ┌──────────────────────────────────┼──────────────────────────────────┐
      │                                  │                                  │
Decision Intelligence            Proactive Operations               Unified Evidence
(RCA • Risk • Approval)       (Predictive • Jobs • Incidents)    (Normalized • Provenance)
      │                                  │                                  │
      └──────────────────────────────────┼──────────────────────────────────┘
                                         │
                          Edge Gateway Management Layer
                     (Mutual Auth • Heartbeat • Buffer Queue)
                                         │
                 ════════════════════════╪════════════════════════ (TLS / WSS)
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             │                           │                           │
     Customer Org A              Customer Org B              Customer Org C
        (Site A1)                   (Site B1)                   (Site C1)
             │                           │                           │
      Edge Gateway A              Edge Gateway B              Edge Gateway C
    (Local Discovery &          (Local Discovery &          (Local Discovery &
    Telemetry Collector)        Telemetry Collector)        Telemetry Collector)
             │                           │                           │
      Local Network A             Local Network B             Local Network C
   (192.168.1.0/24 CHR/R-1)    (192.168.1.0/24 Overlap!)   (10.0.0.0/16 Core Router)
```

---

## 2. Component Architecture & Responsibilities

### 2.1 Central AIRA NOC
Operates as the centralized multi-tenant management plane:
1. **Tenant & Organization Subsystem:** Manages tenant lifecycle states (`PROVISIONING`, `ACTIVE`, `SUSPENDED`, `MAINTENANCE`, `DECOMMISSIONED`), site configurations, subscriptions, and resource quotas.
2. **Identity & Access Governance (RBAC):** Authenticates internal NOC operators (`PLATFORM_SUPER_ADMIN`, `NOC_ADMIN`, `NOC_OPERATOR`, `NETWORK_ENGINEER`, `NOC_ANALYST`, `AUDITOR`) and customer users (`CUSTOMER_OWNER`, `CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR`, `CUSTOMER_VIEWER`). Resolves request tenant context and enforces explicit permissions.
3. **Multi-Tenant Network Inventory:** Catalogs customer sites, gateways, and devices with hierarchical relationship: `Tenant` $\rightarrow$ `Site` $\rightarrow$ `Gateway` $\rightarrow$ `Device`. Enforces scoped uniqueness: overlapping RFC 1918 subnets across separate tenants are isolated without key collision.
4. **Operational Decision Intelligence:** Consumes RCA hypotheses, evidence freshness, predicted capacity horizons, customer SLA targets, and maintenance schedules to generate explainable, auditable operational recommendations with deterministic risk scores and human approval gates.
5. **SLA & Service Management:** Computes deterministic availability, error budgets, and MTTR/MTTD metrics with transparent maintenance exclusions and missing-telemetry handling.
6. **Timezone-Aware Operational Orchestration:** Multi-tenant persistent job scheduler and calendar synchronizer executing in `Asia/Jakarta` (WIB) with restart survivability.
7. **Controlled Reporting & Notification Hub:** Generates tenant-scoped Daily/Weekly/Monthly and SLA reports in Markdown, HTML, and JSON. Delivers deduplicated notifications with quiet hours enforcement.

### 2.2 Customer Edge Gateway
Operates as a lightweight, secure hybrid telemetry collector deployed within the customer's on-premises environment:
1. **Outbound-Only Connection Model:** Initiates outbound TLS/WebSocket connections to the Central NOC; requires zero open inbound firewall ports on the customer network.
2. **Cryptographic Identity & Enrollment:** Enrolls via short-lived, single-use cryptographically signed enrollment tokens. Establishes mutual certificate identity.
3. **Local Telemetry Collection:** Executes approved, strictly read-only MikroTik RouterOS API/SSH/SNMP telemetry collection adhering to the central collection policy.
4. **Resilient Local Buffering:** Features bounded local queueing (max 5,000 samples / 24 hours) with replay-safe sequence numbering to survive central WAN disconnections without data loss.
5. **Security & Zero Arbitrary Execution:** Completely rejects arbitrary shell execution from Central NOC; only accepts predefined, allowlisted diagnostic probes. Live router configuration mutation is strictly impossible.

---

## 3. Data Flow Architecture

### 3.1 Telemetry Ingestion Flow
```
[Edge Gateway] ──(Read-Only Local Poll)──> [Customer RouterOS]
     │
     └──(Pack into Ingestion Envelope with tenant_id, site_id, seq_num)
     │
     └──(Outbound WSS/TLS)──> [Central Ingestion Gateway]
                                    │
                                    ├──(Validate Gateway Identity & Tenant Scope)
                                    ├──(Deduplicate & Sequence Check)
                                    ├──(Metrics Decimation Pipeline)
                                    └──(Persist to topology.db in WAL mode)
```

### 3.2 Decision & Approval Flow
```
[NMS Telemetry & Predictions] ──> [Unified Evidence Hub]
                                           │
                                           ▼
                                [RCA & Intelligence Core]
                                           │
                                           ▼
                           [Operational Decision Engine]
                                           │
                                           ▼
                 Generate OperationalDecision (Tenant Scoped, Risk Scored)
                                           │
                                           ▼
                               [Human Operator Review]
                                ├── Approve ──> [Schedule Operational Task / Maintenance]
                                └── Reject  ──> [Log Reason in Audit Trail]
```

---

## 4. Hardware Optimization for ThinkPad X270

All architectural components are strictly bounded:
- **Shared SQLite Database:** Prevents file descriptor exhaustion by avoiding 50 individual open database files.
- **LRU In-Memory Knowledge Graphs:** Caches a maximum of 5 active tenant graphs in memory; inactive tenant graphs are lazily reconstructed from database snapshots.
- **Asynchronous Decision Scoring:** Decision scoring runs deterministically in pure Python in $< 10$ ms.
- **Bounded Worker Pool:** Background processing is capped at 2 worker threads.
