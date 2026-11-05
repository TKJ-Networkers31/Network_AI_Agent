# AIRA OS — AAA & IDENTITY ARCHITECTURE SPECIFICATION
## Authentication, Authorization, and Accounting in an AI-Native Workspace

**Version:** 1.0.0  
**Status:** Canonical AAA Specification  

---

## 1. Authentication (AuthN)

AIRA OS provides dual-mode identity authentication for engineers and platform operators:

### 1.1 Local Email & Password Flow
- **Registration (`POST /api/v1/auth/register`):**
  - Accepts `username`, `email`, `password`, optional `organization_name`.
  - Validates password complexity (minimum 8 characters, non-trivial).
  - Employs cryptographically secure salt generation (`secrets.token_hex(16)`) and PBKDF2-HMAC-SHA256 password hashing with 100,000 rounds.
  - Automatically provisions a customer organization and tenant context if not joining an existing organization.
  - Generates email verification token (`verification_token_hash`).
- **Email Verification (`POST /api/v1/auth/verify-email`):**
  - Confirms token validity and marks `email_verified = 1`.
- **Session Establishment (`POST /api/v1/auth/login`):**
  - Authenticates credentials against `operational_users`.
  - Enforces account lockout: 5 consecutive failed attempts lock the account for 15 minutes.
  - Generates cryptographically secure session token: `aira_tok_<urlsafe_token>`.
  - Stores SHA-256 hash of token in `operational_user_sessions` with expiry (default: 24 hours).
  - Returns bearer token for API authorization.
- **Session Revocation (`POST /api/v1/auth/logout`):**
  - Marks session token as `REVOKED` in `operational_user_sessions`.
- **Password Reset (`POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password`):**
  - Generates time-bounded cryptographic reset token (1-hour validity).

### 1.2 Google OAuth 2.0 Integration
- Fully decoupled, zero-hardcoding architecture configured via environment variables:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI`
- Endpoints:
  - `GET /api/v1/auth/google/url`: Returns Google OAuth 2.0 consent URL with requested scopes (`openid email profile`). If credentials are not configured in environment, returns `{ "configured": false, "message": "Google OAuth credentials not configured in environment." }`.
  - `POST /api/v1/auth/google/callback`: Exchanges authorization code for verified Google identity token, maps Google subject ID to `operational_users.google_id`, and issues an active AIRA bearer session token.

---

## 2. Authorization (AuthZ) & RBAC

AIRA OS implements role-based access control (RBAC) enforced at the API dependency layer.

### 2.1 Standardized Roles
1. **`PLATFORM_SUPER_ADMIN`:** Full administrative control over all tenants, global token policies, and platform configurations.
2. **`NOC_ADMIN`:** Internal operations manager, incident coordination, and tenant provisioning.
3. **`NETWORK_ENGINEER`:** Infrastructure operations, topology management, device configuration push, and diagnostics.
4. **`CUSTOMER_OWNER`:** Organization owner on customer site; user management, subscription management, and full organization infrastructure control.
5. **`CUSTOMER_ADMIN`:** Organization administrator on customer site.
6. **`CUSTOMER_OPERATOR`:** Day-to-day network operator; reads inventory, triggers approved diagnostics, manages automations.
7. **`CUSTOMER_VIEWER`:** Read-only access to customer topology, NMS telemetry, and reports.

### 2.2 Granular Permissions Matrix
All protected endpoints declare dependency on `require_permission(Permission.<NAME>)`. Client-supplied roles and tenant overrides are strictly disregarded.

| Permission | Description | Assigned Default Roles |
|---|---|---|
| `tenant.read` | View organization details | All roles |
| `tenant.manage` | Update organization settings | `SUPER_ADMIN`, `NOC_ADMIN`, `CUSTOMER_OWNER` |
| `device.read` | Inspect device inventory & status | All roles |
| `device.manage` | Create, update, or delete devices | `SUPER_ADMIN`, `NOC_ADMIN`, `NETWORK_ENGINEER`, `CUSTOMER_OWNER`, `CUSTOMER_ADMIN` |
| `topology.read` | Access network topology graph | All roles |
| `topology.manage`| Trigger discovery, edit links | `SUPER_ADMIN`, `NOC_ADMIN`, `NETWORK_ENGINEER`, `CUSTOMER_ADMIN` |
| `nms.read` | Read live and historical NMS telemetry | All roles |
| `nms.manage` | Configure polling intervals, thresholds | `SUPER_ADMIN`, `NOC_ADMIN`, `NETWORK_ENGINEER`, `CUSTOMER_ADMIN` |
| `automation.read`| View automations and run logs | All roles |
| `automation.manage`| Create/edit automated workflows | `SUPER_ADMIN`, `NOC_ADMIN`, `NETWORK_ENGINEER`, `CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR` |
| `plan.manage` | Assign tiers & grant Networking++ | `SUPER_ADMIN`, `NOC_ADMIN` |
| `token.manage` | Configure token policies & quotas | `SUPER_ADMIN`, `NOC_ADMIN` |

---

## 3. Accounting & Audit Logging

All security-sensitive operations generate append-only audit events in `operational_audit_log`:
- **Audited Events:**
  - `auth.login.success`, `auth.login.failed`, `auth.logout`
  - `device.created`, `device.updated`, `device.deleted`
  - `credential.attached`, `credential.rotated`
  - `config.push.requested`, `config.push.approved`, `config.push.executed`
  - `automation.created`, `automation.executed`
  - `plan.assigned`, `entitlement.granted`
  - `token_policy.updated`
- **Zero-Secret Invariant:**
  - Password fields, private keys, authorization tokens, and raw SNMP community strings are stripped prior to serialization.
- **Search & Filter:**
  - Accessible to platform admins at `GET /api/v1/admin/audit-logs?tenant_id=...&action=...&start_time=...`.
