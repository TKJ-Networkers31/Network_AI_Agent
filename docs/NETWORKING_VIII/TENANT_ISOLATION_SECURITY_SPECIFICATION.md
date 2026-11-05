# AIRA OS — NETWORKING VIII: TENANT ISOLATION SECURITY SPECIFICATION
## Strict Context Derivation, Anti-IDOR & Zero Data Leakage (WP 8.9.3)

**Document Reference:** `docs/NETWORKING_VIII/TENANT_ISOLATION_SECURITY_SPECIFICATION.md`  
**Milestone:** Networking VIII — Phase D  
**Scope:** Multi-Tenant Isolation Architecture, Defense Against Insecure Direct Object References (IDOR), Horizontal & Vertical Boundary Enforcement  
**Date:** 2026-11-04  
**Status:** **AUTHORITATIVE ISOLATION SPECIFICATION**

---

### 1. Threat Definition & Scope of Defense

The Customer Portal exposes network intelligence and inventory to multiple external organizations. Under no circumstances may an external customer observe or affect:
1. Another customer's registered sites, devices, or management IPs.
2. Another customer's active incidents or alarms.
3. Another customer's SLA performance and error budgets.
4. Another customer's support requests, comments, or attachments.
5. Another customer's user accounts or notification preferences.
6. Overlapping RFC 1918 private subnets belonging to different organizations.

---

### 2. Multi-Layer Defense Architecture

```
Layer 1: Edge / Transport Layer
  └── Validates HTTPS, TLS ciphers, CORS allowlist, and Rate Limiting.

Layer 2: Authentication & Context Resolution
  └── Decodes `Bearer aira_tok_...`
  └── Looks up SHA-256 token hash in `operational_user_sessions`
  └── Enforces active checks on User and Tenant
  └── Binds `TenantContext` containing verified `tenant_id` to request scope.

Layer 3: REST API Dependency Layer
  └── `get_current_portal_context`: rejects unauthenticated requests (HTTP 401).
  └── Derives `effective_tenant_id = ctx.tenant_id`.
  └── IGNORES any `tenant_id` provided in request query params or body by external clients.

Layer 4: Tenant-Scoped Repository Layer
  └── Every SQL query incorporates mandatory tenant parameter:
      `SELECT ... FROM table WHERE tenant_id = ? AND entity_id = ?`
  └── If an entity exists in another tenant, SQL returns 0 rows $\rightarrow$ HTTP 404 (IDOR Defense).

Layer 5: Database Layer
  └── Relational foreign keys with ON DELETE CASCADE scoped to `operational_tenants(tenant_id)`.
  └── Composite UNIQUE constraints: `UNIQUE(tenant_id, site_id, management_ip)`.
```

---

### 3. Anti-IDOR (Insecure Direct Object Reference) Rules

1. **Never Accept Entity IDs in Isolation:**  
   When fetching a device, incident, SLA report, or support request by ID:
   ```python
   # INCORRECT (Vulnerable to IDOR):
   conn.execute("SELECT * FROM operational_devices WHERE device_id = ?", (device_id,))
   
   # AUTHORITATIVE AIRA DEFENSE (Strict Tenant Binding):
   conn.execute(
       "SELECT * FROM operational_devices WHERE tenant_id = ? AND device_id = ?",
       (ctx.tenant_id, device_id),
   )
   ```
2. **Fail Closed with HTTP 404:**  
   If a user requests an ID belonging to another tenant, the system returns HTTP 404 Not Found rather than HTTP 403 Forbidden to prevent resource enumeration.
3. **RFC 1918 Overlap Isolation:**  
   Two distinct tenants (`Acme Corp` and `Globex Corp`) can both have devices configured with `192.168.1.1` or `10.0.0.1`. All inventory queries index `(tenant_id, site_id, management_ip)`, eliminating collision or cross-talk.

---

### 4. Verification & Testing Requirements

To ensure zero regressions, `test_networking_viii_phase_d.py` must test:
- **Test IDOR-01:** Tenant A authenticates and attempts to read Tenant B's devices $\rightarrow$ returns 404 / `None`.
- **Test IDOR-02:** Tenant A attempts to read Tenant B's incidents $\rightarrow$ returns 404 / `None`.
- **Test IDOR-03:** Tenant A attempts to read Tenant B's SLA reports $\rightarrow$ returns 404 / `None`.
- **Test IDOR-04:** Tenant A attempts to comment on Tenant B's support request $\rightarrow$ returns 404 / `None`.
- **Test IDOR-05:** Tenant A attempts to list or mutate Tenant B's users $\rightarrow$ returns 404 / `None`.
- **Test RFC1918:** Both tenants query `192.168.1.1` simultaneously and receive only their respective records.
