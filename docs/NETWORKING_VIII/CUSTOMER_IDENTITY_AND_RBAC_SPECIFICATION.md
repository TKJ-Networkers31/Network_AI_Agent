# AIRA OS — NETWORKING VIII: CUSTOMER IDENTITY & RBAC SPECIFICATION
## Customer Roles, Least Privilege & Session Security (WP 8.9.1 & WP 8.9.2)

**Document Reference:** `docs/NETWORKING_VIII/CUSTOMER_IDENTITY_AND_RBAC_SPECIFICATION.md`  
**Milestone:** Networking VIII — Phase D  
**Scope:** Customer Identity, Authentication, Role-Based Access Control, Session Lifecycle  
**Date:** 2026-11-04  
**Status:** **AUTHORITATIVE SECURITY SPECIFICATION**

---

### 1. Identity Model & Authentication Mechanics

Customer authentication is integrated with the existing `operational_users` and `operational_user_sessions` tables.

#### Password Security & Hashing
- Algorithm: **PBKDF2 with HMAC-SHA256** (100,000 iterations).
- Salt: 16-byte cryptographically secure random salt generated via `secrets.token_hex(16)`.
- Verification: Constant-time comparison using `secrets.compare_digest` to prevent timing attacks.
- Plaintext Passwords: **Never stored, logged, or serialized.**

#### Session Lifecycle & Security
1. **Login:** Successful verification of username/email and password generates a 32-byte cryptographically secure token:
   $$\text{Token} = \texttt{"aira\_tok\_"} + \text{secrets.token\_urlsafe}(32)$$
2. **Token Storage:** The plaintext token is returned **only once** to the client upon login. The database stores only the SHA-256 hash of the token:
   $$\text{Token Hash} = \text{hashlib.sha256}(\text{Token}).\text{hexdigest}()$$
3. **Session Expiration:** Default 24-hour lifetime. Sessions older than `expires_at_utc` fail authentication automatically.
4. **Session Invalidation:** Revoked immediately upon explicit logout, account deactivation, or organization suspension.
5. **No Plaintext Tokens in Logs:** Application logs sanitize all authentication headers (`Authorization: Bearer [REDACTED]`).

---

### 2. Customer RBAC Hierarchy & Permission Matrix

Customer roles are explicitly separated from internal NOC roles:

```
INTERNAL NOC ROLES (NOC Admin, NOC Operator, Network Engineer)
   ▲
   │ [NON-BYPASSABLE PRIVILEGE BOUNDARY]
   ▼
CUSTOMER ROLES
   ├── CUSTOMER_OWNER      (Full organizational control, user management, billing/SLA, support)
   ├── CUSTOMER_ADMIN      (Operational administration, user management, support)
   ├── CUSTOMER_OPERATOR   (Read inventory, view incidents, submit support requests)
   ├── CUSTOMER_TECHNICIAN (Read inventory & diagnostics, submit/update support requests)
   └── CUSTOMER_VIEWER     (Strictly read-only visibility into dashboards, devices, and SLA)
```

#### Detailed Permission Assignment Matrix:

| Permission Identifier | Description | CUSTOMER_OWNER | CUSTOMER_ADMIN | CUSTOMER_OPERATOR | CUSTOMER_TECHNICIAN | CUSTOMER_VIEWER |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `tenant.read` | View organization profile | **YES** | **YES** | **YES** | **YES** | **YES** |
| `site.read` | View customer sites | **YES** | **YES** | **YES** | **YES** | **YES** |
| `site.manage` | Add or update site details | **YES** | **YES** | NO | NO | NO |
| `device.read` | View network devices & status | **YES** | **YES** | **YES** | **YES** | **YES** |
| `incident.read` | View customer-scoped alerts | **YES** | **YES** | **YES** | **YES** | **YES** |
| `incident.acknowledge` | Acknowledge tenant incident | **YES** | **YES** | **YES** | NO | NO |
| `sla.read` | View SLA & availability reports | **YES** | **YES** | **YES** | **YES** | **YES** |
| `report.read` | View operational reports | **YES** | **YES** | **YES** | **YES** | **YES** |
| `report.export` | Export SLA / incident CSV/PDF | **YES** | **YES** | NO | NO | NO |
| `support.read` | View support requests | **YES** | **YES** | **YES** | **YES** | **YES** |
| `support.create` | Create new support requests | **YES** | **YES** | **YES** | **YES** | NO |
| `support.comment` | Comment on support requests | **YES** | **YES** | **YES** | **YES** | NO |
| `notification.manage` | Update notification prefs | **YES** | **YES** | **YES** | **YES** | NO |
| `user.manage` | Create/deactivate tenant users | **YES** | **YES** | NO | NO | NO |
| `recommendation.approve` | Approve internal NOC actions | **DENIED** | **DENIED** | **DENIED** | **DENIED** | **DENIED** |
| `recommendation.read` | Read internal NOC reasoning | **DENIED** | **DENIED** | **DENIED** | **DENIED** | **DENIED** |
| `tenant.manage` | Modify platform subscriptions | **DENIED** | **DENIED** | **DENIED** | **DENIED** | **DENIED** |

---

### 3. Non-Bypassable Authorization Invariants

1. **Deny-by-Default:** Any customer user missing the requisite permission receives HTTP 403 Forbidden.
2. **Customer Roles Cannot Escalate:** A customer user cannot grant themselves internal NOC roles or create users outside their own `tenant_id`.
3. **No Execution of Router Mutations:** Zero customer endpoints permit sending arbitrary CLI or configuration commands to MikroTik devices.
4. **Mandatory Tenant Scoping:** An authorized user can only query or mutate resources where `entity.tenant_id == user.tenant_id`.
