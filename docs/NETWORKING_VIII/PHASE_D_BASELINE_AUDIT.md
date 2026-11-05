# AIRA OS — NETWORKING VIII: PHASE D BASELINE ARCHITECTURE AUDIT
## Customer Self-Service Portal & Secure External Access (WP 8.9)

**Document Reference:** `docs/NETWORKING_VIII/PHASE_D_BASELINE_AUDIT.md`  
**Milestone:** Networking VIII — Phase D (WP 8.9)  
**Workspace:** `D:\data\agent_ai`  
**Current Branch:** `main` | **Baseline HEAD:** `be59871acd2dd92c581d8944e65899d485f208ae`  
**Author:** Principal Software Architect, Senior Backend Engineer, Senior Application Security Engineer  
**Date:** 2026-11-04  
**Status:** **APPROVED FOR IMPLEMENTATION**

---

### 1. Executive Mission & Scope Authorization

You are authorized to extend AIRA OS with **WP 8.9: Customer Self-Service Portal & Secure External Access**.

The customer portal provides authorized customer personnel (Owners, Admins, Operators, Viewers) with an intuitive, secure, tenant-scoped window into their network services, active incidents, dynamic multi-dimensional health scores, SLA compliance reports, device inventory, support requests, and notification preferences.

Customers must **NEVER** gain access to internal Central NOC tools, unrestricted router shells, raw secrets, or cross-tenant data.

---

### 2. Comprehensive Inventory of Existing Subsystems & Reusable Components

Phase D builds directly on the foundations established in Phases A, B, and C:

| Subsystem | Existing Module | Current Status | Reusability in Phase D (Customer Portal) |
| :--- | :--- | :--- | :--- |
| **Multi-Tenant Core** | `core/tenant/manager.py` (`TenantManager`) | Active (WP 8.1) | **100% Reusable:** Provides tenant lifecycle, quota queries, and tenant profile retrieval. |
| **Identity & RBAC** | `core/tenant/manager.py` (`IdentityManager`) | Active (WP 8.2) | **100% Reusable:** Password hashing (PBKDF2/SHA-256), session tokens (`aira_tok_...`), session validation, role assignment, and user management. |
| **Tenant Context** | `core/tenant/context.py` (`TenantContext`, `tenant_scope`) | Active (WP 8.2) | **100% Reusable:** ContextVar binding, ownership verification, and thread-local scoping. |
| **Customer Inventory** | `core/tenant/manager.py` (`InventoryManager`) | Active (WP 8.3) | **100% Reusable:** Scoped device and site lookup, RFC 1918 overlap safe. |
| **Edge Gateways** | `core/edge_gateway/manager.py` (`EdgeGatewayManager`) | Active (WP 8.4) | **100% Reusable:** Gateway liveness, heartbeat telemetry, and queue depth inspection. |
| **Health Scoring** | `core/operations/health_scoring_engine.py` | Active (WP 8.5.1) | **100% Reusable:** 6-dimensional health evaluation (Device, Interface, Site, Service, Gateway, Tenant). |
| **SLA Management** | `core/operations/sla_engine.py` | Active (WP 8.7) | **100% Reusable:** Availability percentage calculation, maintenance exclusions, error budgets, and data coverage validation. |
| **Incident Engine** | `core/operations/multi_tenant_incident_engine.py` | Active (WP 8.8) | **100% Reusable:** Scoped incidents, SHA-256 deduplication, customer-visible summaries. |
| **Notifications** | `core/operations/notification_hub.py` | Active (WP 7.7 / 8.8) | **100% Reusable:** Scoped alerts and quiet hours enforcement. |

---

### 3. Missing Capabilities & Identified Gaps

To fulfill WP 8.9, the following new capabilities must be engineered:

1. **Customer Support & Service Requests (WP 8.9.9):**
   - *Current Gap:* No support ticketing data model or lifecycle exists.
   - *Required Solution:* Implement `SupportRequestManager` with lifecycle states (`OPEN` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `WAITING_CUSTOMER` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED`) and append-only customer/operator comments.
2. **Customer Notification Preferences (WP 8.9.8):**
   - *Current Gap:* Customer-level alert preference overrides (critical, major, degradation, gateway offline, SLA breach) are not persisted per user.
   - *Required Solution:* Implement `operational_customer_notification_preferences` table and configuration endpoints.
3. **Dedicated Customer Portal REST API (WP 8.9.1–8.9.9):**
   - *Current Gap:* Existing API routers (`/api/v1/decisions`, `/api/v1/gateways`) are oriented towards internal NOC operators.
   - *Required Solution:* Create dedicated `/api/v1/portal/*` router with mandatory, server-enforced tenant scoping.
4. **Dedicated Customer Portal Frontend Experience (WP 8.9.4):**
   - *Current Gap:* The frontend navigation currently targets NOC operators.
   - *Required Solution:* Create `CustomerPortalPage.jsx` (`/portal`) providing a sleek SaaS dashboard with tenant-aware navigation, overview cards, health dimensions, incident tracker, SLA report viewer, support request desk, and user management.
5. **Secure External Access & Reverse Proxy Specifications (WP 8.9):**
   - *Current Gap:* No production Nginx/Caddy reverse proxy configuration with TLS termination, security headers, and rate limiting exists in `deploy/`.
   - *Required Solution:* Author production-grade configuration files and integrate FastAPI security middleware.

---

### 4. Database Schema Migration Plan

All database schema additions will be made idempotently in [`AIRA_ECOSYSTEM/core/tenant/db.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/tenant/db.py):

```sql
-- 11. Customer Support Requests (WP 8.9.9)
CREATE TABLE IF NOT EXISTS operational_support_requests (
    request_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    requester_id TEXT NOT NULL REFERENCES operational_users(user_id),
    category TEXT NOT NULL CHECK(category IN ('INCIDENT', 'SERVICE_REQUEST', 'BILLING', 'GENERAL', 'CHANGE')),
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'WAITING_CUSTOMER', 'RESOLVED', 'CLOSED')),
    assigned_operator_id TEXT REFERENCES operational_users(user_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

-- 12. Support Request Comments
CREATE TABLE IF NOT EXISTS operational_support_request_comments (
    comment_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES operational_support_requests(request_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    author_id TEXT NOT NULL REFERENCES operational_users(user_id),
    author_name TEXT NOT NULL,
    is_internal INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 13. Customer Notification Preferences (WP 8.9.8)
CREATE TABLE IF NOT EXISTS operational_customer_notification_preferences (
    pref_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    notify_critical_incidents INTEGER NOT NULL DEFAULT 1,
    notify_major_incidents INTEGER NOT NULL DEFAULT 1,
    notify_service_degradation INTEGER NOT NULL DEFAULT 1,
    notify_gateway_offline INTEGER NOT NULL DEFAULT 1,
    notify_sla_breach INTEGER NOT NULL DEFAULT 1,
    email_notifications INTEGER NOT NULL DEFAULT 1,
    in_app_notifications INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_support_tenant ON operational_support_requests(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_support_requester ON operational_support_requests(requester_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_comments ON operational_support_request_comments(request_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_notif_pref ON operational_customer_notification_preferences(tenant_id, user_id);
```

---

### 5. Architectural Invariants & Security Boundaries

1. **Zero Trust in Frontend-Supplied `tenant_id`:**  
   Every portal endpoint automatically derives `tenant_id` from the cryptographically verified `TenantContext` of the authenticated session token. Even if a customer submits `tenant_id: "other_tenant"`, the backend rejects or overrides it with `ctx.tenant_id`.
2. **Deny-by-Default RBAC:**  
   Customer roles (`CUSTOMER_OWNER`, `CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR`, `CUSTOMER_VIEWER`) are strictly barred from:
   - Approving or rejecting operational recommendations (`recommendation.approve`).
   - Accessing or modifying internal NOC configurations or rules.
   - Direct execution of commands on network routers.
   - Accessing internal audit notes, unredacted RCA logs, or other tenants' data.
3. **Epistemic Honesty:**  
   Unknown health or telemetry status remains visibly `UNKNOWN` or `INSUFFICIENT_DATA`. If SLA telemetry coverage is $< 80\%$, the portal displays `INSUFFICIENT_COVERAGE` rather than a fictitious 100% uptime.
4. **100% Read-Only Network Policy:**  
   Customer interactions cannot trigger commands against physical devices (`CHR` @ 10.26.213.30, `R-1` @ 192.168.0.1).

---

### 6. Implementation Risk Analysis & Mitigation

| Risk | Impact | Mitigation Strategy |
| :--- | :---: | :--- |
| **Insecure Direct Object Reference (IDOR)** | **HIGH** | Strict SQL filter `WHERE tenant_id = ? AND entity_id = ?` on every query; verified by negative tests in `test_networking_viii_phase_d.py`. |
| **Session Fixation / Token Exposure** | **HIGH** | Random 32-byte tokens (`aira_tok_...`), SHA-256 token hashing in SQLite, tokens never logged or stored in plaintext. |
| **Customer Role Privilege Escalation** | **CRITICAL** | Hardcoded role boundary check preventing customer roles from granting themselves NOC permissions or mutating other users. |
| **Performance Overhead on Dual-Core Hardware** | **LOW** | All queries indexed; no N+1 database operations; lightweight SQLite transactions via `topology_transaction`. |

---

### 7. Phase D Execution Roadmap

- **Stage 1:** Core models, Support Request subsystem, Notification Preferences, and Schema update in `core/tenant/`.
- **Stage 2:** Customer Portal REST API router (`api/routers/portal.py`) mounted in `api/main.py`.
- **Stage 3:** Frontend Customer Portal UI (`app/frontend/src/pages/CustomerPortalPage.jsx`), navigation registration in `App.jsx` and `navConfig.js`.
- **Stage 4:** External access hardening (Nginx config, CORS, rate limiting, security headers).
- **Stage 5:** Test suite `test_networking_viii_phase_d.py` (Tenant isolation, RBAC, Support lifecycle, SLA visibility), benchmark script, and documentation artifacts.
