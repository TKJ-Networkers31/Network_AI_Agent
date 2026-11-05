# AIRA OS — NETWORKING VIII: TENANT ISOLATION SPECIFICATION
## Comprehensive Multi-Layer Tenant Segregation & IDOR Prevention

**Document ID:** `AIRA-NET8-ISOLATION-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Target Milestone:** Networking VIII  
**Organization:** LS Technology

---

## 1. Executive Security Mandate

In a multi-tenant platform managing 10–50 customer organizations, **tenant isolation is a critical release gate**. A flaw in tenant segregation can leak sensitive network topology, internal RFC 1918 subnets, device credentials, or operational incidents across competitors.

**Fundamental Invariant:**
> Under no circumstance shall Tenant A be capable of observing, creating, mutating, deleting, subscribing to, or exporting any data, telemetry, event, report, or configuration belonging to Tenant B through any backend access path.

---

## 2. Multi-Layer Isolation Architecture

```
Layer 1: Transport & Request Gateway
  ├── Extract Bearer Token / Session Cookie
  ├── Authenticate UserPrincipal & Verify Status (ACTIVE)
  └── Resolve Immutable TenantContext (Never trust raw client-provided tenant_id)
        │
Layer 2: Domain Authorization & RBAC
  ├── Check explicit user permissions (e.g. `device.read`, `incident.manage`)
  └── Enforce Tenant Boundary:
        ├── NOC Operators: Permitted cross-tenant operations if authorized
        └── Customer Users: Restricted strictly to their own UserPrincipal.tenant_id
              │
Layer 3: Repository & Data Access Layer
  ├── TenantScopedRepository enforces `WHERE tenant_id = ?` on every query
  ├── Composite Indexes `(tenant_id, resource_id)` ensure performance and isolation
  └── Write operations verify parent entity ownership before insert/update
        │
Layer 4: In-Memory Subsystems (Graph, Cache, Evidence)
  ├── Graph instances partitioned by `tenant_id` (LRU Cache of max 5 active graphs)
  └── Evidence bundles assembled with explicit `bundle.tenant_id` filter
        │
Layer 5: Asynchronous Event Bus & WebSockets
  ├── All events stamped with `event.tenant_id`
  └── WebSocket connections filtered: client receives ONLY matching tenant events
```

---

## 3. Layered Isolation Enforcement

### 3.1 API & Request Context Layer
1. **Context Resolution:** The FastAPI dependency `get_tenant_context()` extracts the cryptographic identity from the session/token.
2. **Never Trust Client Input:** If an API client passes `?tenant_id=tenant_xyz` in query parameters or request body:
   - For Customer Users: The parameter is rejected with `403 Forbidden` if it differs from the authenticated user's `tenant_id`.
   - For NOC Operators: The parameter is honored only if the operator has `tenant.cross_manage` permission; otherwise, it defaults to the operator's assigned scope.
3. **Session Revocation:** If a tenant is marked `SUSPENDED` or `DECOMMISSIONED`, all associated user sessions are invalidated immediately.

### 3.2 Database Persistence Layer
The persistence architecture utilizes a shared SQLite database (`topology.db` and `network_intelligence.db`) with strict repository-level isolation:
1. **Mandatory Column:** All tenant-owned tables (`sites`, `gateways`, `devices`, `services`, `incidents`, `jobs`, `maintenance_windows`, `notifications`, `decisions`) contain a non-null `tenant_id TEXT NOT NULL` column.
2. **Foreign Key Integrity:** Child records reference tenant-owned parents with `ON DELETE CASCADE`:
   ```sql
   CREATE TABLE IF NOT EXISTS operational_sites (
       site_id TEXT PRIMARY KEY,
       tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
       name TEXT NOT NULL,
       created_at TEXT NOT NULL
   );
   ```
3. **Composite Primary/Unique Indexes:**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_sites_tenant ON operational_sites(tenant_id, site_id);
   CREATE INDEX IF NOT EXISTS idx_devices_tenant_ip ON operational_devices(tenant_id, site_id, management_ip);
   ```
4. **TenantScopedRepository Pattern:** All database queries are constructed through a repository wrapper that automatically binds the tenant context:
   ```python
   def get_site(self, tenant_id: str, site_id: str) -> Optional[Site]:
       with topology_transaction(self.db_path, write=False) as conn:
           row = conn.execute(
               "SELECT * FROM operational_sites WHERE tenant_id = ? AND site_id = ?",
               (tenant_id, site_id),
           ).fetchone()
           return Site.from_row(row) if row else None
   ```

### 3.3 Overlapping RFC 1918 Private IP Address Isolation
In customer networks, RFC 1918 addresses (`192.168.1.1`, `10.0.0.1`, `172.16.0.1`) are ubiquitous.
- **Problem:** If device identity is indexed solely by `management_ip`, Tenant A's router at `192.168.1.1` will collide with Tenant B's router at `192.168.1.1`.
- **Enforcement:**
  - `device_id` is globally unique: `dev_{tenant_id[:8]}_{site_id[:8]}_{uuid4().hex[:8]}`.
  - IP resolution is composite: `resolve_device_by_ip(tenant_id, site_id, ip_address)`.
  - Evidence records and telemetry rollups are stored with `(tenant_id, site_id, device_id)`.

### 3.4 In-Memory Graph & Intelligence Isolation
- The `NetworkKnowledgeGraph` is never shared globally across tenants.
- When an investigation or change simulation is triggered, the system builds an isolated graph containing only nodes and edges with matching `tenant_id`.
- RCA hypotheses evaluated for Tenant A never incorporate symptoms or observations from Tenant B.

### 3.5 Asynchronous EventBus & WebSocket Isolation
- Every event published to `EventBus` must specify `tenant_id`.
- The `WebSocketEventBridge` inspects the authenticated session's `tenant_id`.
- Events are dispatched to a connected client if and only if:
  1. The event's `tenant_id` matches the connection's `tenant_id`, OR
  2. The connected user is an internal NOC operator with global visibility.

---

## 4. Insecure Direct Object Reference (IDOR) Defense Matrix

| Attack Vector | Simulated Scenario | Architectural Defense & Mitigation | Test Verification |
| :--- | :--- | :--- | :---: |
| **Site IDOR** | Customer A requests `GET /api/v1/sites/site_B` | API verifies `WHERE tenant_id = ? AND site_id = ?`. Returns `404 Not Found` (avoids confirming existence). | Automated unit test |
| **Device IDOR** | Customer A requests `GET /api/v1/devices/dev_B` | Query scoped to Customer A's `tenant_id`. Returns `404 Not Found`. | Automated unit test |
| **Incident IDOR** | Customer A attempts `POST /api/v1/incidents/inc_B/ack` | Ownership check denies update; logs security audit alert. | Automated unit test |
| **Report Export IDOR** | Customer A accesses `GET /api/v1/reports/rep_B.pdf` | Pre-signed token or database query checks `tenant_id`. Denies download. | Automated unit test |
| **Scheduler Job IDOR** | Customer A triggers `POST /api/v1/jobs/job_B/run` | Execution rejected with `403 Forbidden`. | Automated unit test |
| **WebSocket Subscription IDOR** | Customer A connects to `/ws` and requests Tenant B telemetry | Server checks connection identity against channel scope; rejects subscription. | Automated unit test |
| **Gateway Token Hijacking** | Customer B attempts to redeem Customer A's gateway token | Token metadata encodes `target_tenant_id`; cross-tenant redemption blocked. | Automated unit test |
