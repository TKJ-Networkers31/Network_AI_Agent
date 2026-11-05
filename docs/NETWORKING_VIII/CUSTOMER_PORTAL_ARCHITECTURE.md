# AIRA OS — NETWORKING VIII: CUSTOMER SELF-SERVICE PORTAL ARCHITECTURE
## Multi-Tenant Presentation Layer & Secure Customer Service Management (WP 8.9)

**Document Reference:** `docs/NETWORKING_VIII/CUSTOMER_PORTAL_ARCHITECTURE.md`  
**Milestone:** Networking VIII — Phase D  
**Scope:** Architectural Blueprint for Customer Self-Service Portal & Edge Visibility  
**Date:** 2026-11-04  
**Status:** **AUTHORITATIVE ARCHITECTURAL SPECIFICATION**

---

### 1. Architectural Vision

The AIRA Customer Self-Service Portal (`/portal`) provides enterprise customers with transparent, real-time visibility into their dedicated network environments.

While the Central NOC operates as the primary operational intelligence cockpit for LS Technology engineers, the Customer Portal functions as a controlled, tenant-isolated window that answers critical customer questions:
1. **Organization Context:** Which tenant organization am I managing?
2. **Infrastructure Health:** Are my registered sites, edge routers, access switches, and edge gateways online and healthy?
3. **Service Quality & SLA:** Are my mission-critical services compliant with agreed-upon availability thresholds, and what is my error budget consumption?
4. **Incidents & Alarms:** What network anomalies are actively affecting my branch locations, and what are their remediation statuses?
5. **Support & Service Management:** How can I open, track, and collaborate on support requests directly with LS Technology NOC operators?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CUSTOMER ORGANIZATIONS & PORTAL                       │
│  [Customer Owner / Admin / Operator / Viewer] via HTTPS / Secure TLS        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EDGE REVERSE PROXY & SECURITY LAYER                      │
│  TLS Termination • HSTS • CSP • CORS Allowlist • Rate Limiting • Proxies    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Authenticated Requests (Bearer Token)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   AIRA CUSTOMER PORTAL API (/api/v1/portal)                 │
│  Strict Tenant Context Resolution • Deny-by-Default RBAC • Non-Bypassable   │
└──────────────┬───────────────────────┬───────────────────────┬──────────────┘
               │                       │                       │
               ▼                       ▼                       ▼
    ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
    │  INVENTORY & SITES │  │  HEALTH & SLA      │  │  INCIDENTS & TIX   │
    │  • Sites & Groups  │  │  • 6-Dim Health    │  │  • Scoped Incidents│
    │  • Scoped Devices  │  │  • Math SLA & Maint│  │  • Support Requests│
    │  • Gateway Status  │  │  • Error Budgets   │  │  • User Management │
    └──────────┬─────────┘  └──────────┬─────────┘  └──────────┬─────────┘
               │                       │                       │
               └───────────────────────┼───────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SHARED CANONICAL REPOSITORIES & DB                      │
│   SQLite (topology.db) with WAL • Indexed Scoping • Append-Only Audit Logs  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Core Architectural Principles

1. **Strict Server-Side Derivation of Scope:**  
   The frontend UI is treated as untrusted. Tenant context is derived strictly from the cryptographically validated session token (`Bearer aira_tok_...`). A customer cannot access or tamper with another organization's records even if URL parameters or request bodies attempt to specify an alternate `tenant_id`.
2. **Zero Duplicate Operational Engines:**  
   The Customer Portal does not implement parallel monitoring, health calculations, or incident pipelines. It invokes the proven canonical engines:
   - [`DynamicHealthScoringEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/health_scoring_engine.py)
   - [`SlaManagementEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/sla_engine.py)
   - [`MultiTenantIncidentEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/operations/multi_tenant_incident_engine.py)
   - [`InventoryManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/tenant/manager.py)
   - [`EdgeGatewayManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/manager.py)
3. **No Disclosure of Internal Operational Secrets:**  
   Customer endpoints systematically redact:
   - Device login credentials, SNMP community strings, and API keys.
   - Internal NOC diagnostic comments and unverified root cause hypotheses.
   - Gateway private authorization tokens.
   - Internal management IP ranges not explicitly assigned to customer sites.
4. **Epistemic Data Representation:**  
   The portal preserves factual telemetry integrity. Missing metric streams display as `UNKNOWN` or `INSUFFICIENT_DATA` rather than fabricated 100% scores. Periods with $< 80\%$ telemetry coverage display `INSUFFICIENT_COVERAGE` on SLA dashboards.

---

### 3. Portal Subsystem Decomposition

```
Customer Portal Subsystems (WP 8.9)
├── 8.9.1: Customer Identity & Session Lifecycle (Login, Logout, Session Token, Active Checks)
├── 8.9.2: Customer RBAC (Owner, Admin, Operator, Viewer, Technician with Least Privilege)
├── 8.9.3: Tenant Context Resolution & IDOR Prevention
├── 8.9.4: Self-Service Overview Dashboard (Real-time operational summary)
├── 8.9.5: Customer Device & Site Inventory (Read-only status, IP, gateway association)
├── 8.9.6: Customer Incident Self-Service (Active alerts, timelines, resolution details)
├── 8.9.7: Customer SLA & Reporting Portal (Availability % calculation, error budgets)
├── 8.9.8: Customer Notifications (Configurable alert criteria, email/in-app preferences)
└── 8.9.9: Customer Support Requests & Collaboration Desk (Ticket lifecycle & customer-operator dialogue)
```

---

### 4. Support Request & Collaboration Lifecycle (WP 8.9.9)

Support requests bridge customer issues with NOC technical response.

#### Lifecycle State Machine:
```
  [OPEN]
     │
     ▼ (NOC Operator Acknowledges)
[ACKNOWLEDGED]
     │
     ▼ (NOC Operator starts troubleshooting)
[IN_PROGRESS] ◄────────────────────────────────┐
     │                                         │
     ├────────► [WAITING_CUSTOMER] ────────────┘
     │          (Customer provides feedback)
     ▼ (NOC resolves issue)
 [RESOLVED]
     │
     ▼ (Customer or Auto-closure)
  [CLOSED]
```

#### Valid Transitions:
- `OPEN` $\rightarrow$ `ACKNOWLEDGED`, `CLOSED`
- `ACKNOWLEDGED` $\rightarrow$ `IN_PROGRESS`, `WAITING_CUSTOMER`, `CLOSED`
- `IN_PROGRESS` $\rightarrow$ `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`
- `WAITING_CUSTOMER` $\rightarrow$ `IN_PROGRESS`, `RESOLVED`, `CLOSED`
- `RESOLVED` $\rightarrow$ `CLOSED`, `IN_PROGRESS` (Re-open)
- `CLOSED` $\rightarrow$ *Terminal state* (No further transitions)

---

### 5. Frontend Visual Experience & Information Architecture

The Customer Portal page (`/portal`) features:
1. **Tenant Context Header:** Displays customer organization name, current user role, subscription tier, and active session status.
2. **Tabbed Navigation:**
   - **Dashboard:** At-a-glance status cards (Registered Devices, Online %, Active Incidents, SLA Compliance, Gateway Liveness).
   - **Sites & Devices:** Filterable inventory table showing sites, devices, vendor, IP, status, and last seen.
   - **Services & SLA:** Service health breakdown across 6 dimensions with monthly availability progress bars.
   - **Incidents:** Customer-facing incident queue with severity badges and status.
   - **Support Desk:** Interactive ticket center where users can submit tickets, view status, and post comments.
   - **User Management & Settings:** Add/manage authorized customer accounts (Owner/Admin only) and configure notification preferences.
