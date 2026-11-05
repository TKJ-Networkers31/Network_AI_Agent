# AIRA OS — NETWORKING VIII: PHASE D SECURITY & ISOLATION AUDIT
## Customer Self-Service Portal, Strict Anti-IDOR Scoping, RBAC Boundaries & External Access Hardening

**Document Reference:** `docs/NETWORKING_VIII/PHASE_D_SECURITY_AUDIT.md`  
**Milestone:** Networking VIII — Phase D (WP 8.9)  
**Security Classification:** Highly Confidential / Multi-Tenant SaaS & Central NOC  
**Auditor:** Principal Software Security Architect & Multi-Tenant SaaS Architect  
**Audit Date:** 2026-11-04  
**Status:** **APPROVED & FULLY COMPLIANT**

---

### 1. Executive Summary

Phase D implements the **Customer Self-Service Portal & Secure External Access (WP 8.9)**, extending AIRA OS from internal NOC operations into an enterprise-grade multi-tenant platform serving 10–50 client organizations.

Because the customer portal is directly exposed to external client networks and users via reverse proxy, the security perimeter must withstand sophisticated adversarial attacks:
1. **Zero-Trust Tenant Derivation (Anti-IDOR):** The API must never rely on client-supplied `tenant_id` query parameters or JSON body fields. The customer's identity and tenant isolation boundary are derived strictly server-side from cryptographically signed session tokens.
2. **Strict Multi-Tenant Data Isolation:** Cross-tenant resource queries (devices, gateways, incidents, SLA reports, support tickets, comments) must deterministically fail closed with HTTP 404 (Not Found) to avoid leaking the existence of other tenants' resources.
3. **Hardened RBAC Boundaries:** Customer tenant roles (`CUSTOMER_OWNER`, `CUSTOMER_ADMIN`, `CUSTOMER_OPERATOR`, `CUSTOMER_TECHNICIAN`, `CUSTOMER_VIEWER`) must have strictly scoped permissions. Customer administrators cannot elevate themselves or other users into internal NOC roles (`NOC_SUPERADMIN`, `NOC_ENGINEER`, `NOC_OPERATOR`) or perform operational changes (`RECOMMENDATION_APPROVE`, `TENANT_MANAGE`).
4. **Credential Sanitization & Redaction:** Sensitive device access secrets (RouterOS credentials, SSH keys, SNMP community strings, API secrets) must never be returned across portal endpoints.
5. **Support Ticket Confidentiality:** Internal NOC operator comments marked `is_internal = true` must be strictly withheld from external customer views.
6. **Network Invariant Protection:** The portal strictly enforces a **100% Read-Only Network Policy**. No customer endpoint can mutate physical router state (`CHR` @ 10.26.213.30, `R-1` @ 192.168.0.1).
7. **External Reverse Proxy Hardening:** Nginx front-end configuration provides TLS 1.2/1.3 termination, HSTS preloading, strict Content Security Policy (CSP), body size limiting, rate-limiting on authentication and API endpoints, and secure WebSocket proxying.

Every security control was verified via automated integration tests in `AIRA_ECOSYSTEM/tests/test_networking_viii_phase_d.py` and benchmarked under high-concurrency multi-tenant loads. **Zero cross-tenant leaks, privilege escalations, or unauthorized access vectors were identified.**

---

### 2. Threat Modeling & Boundary Assessment

| Threat ID | Threat Vector | Target Subsystem | Severity | Implemented Defense Mechanism | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **THREAT-D-01** | **Insecure Direct Object Reference (IDOR)** via forged `device_id` or `request_id` | Portal API Router (`portal.py`) | **CRITICAL** | Identity derived server-side via `get_current_tenant_context(token)`. All queries enforce composite database filters `WHERE id = ? AND tenant_id = ?`. Out-of-scope requests return HTTP 404. | Verified by `test_09_anti_idor_device_access`, `test_12_anti_idor_sla_report_rejection`, and `test_14_anti_idor_support_ticket_isolation` |
| **THREAT-D-02** | **Privilege Escalation** by Customer Admin creating internal NOC accounts | User Management (`portal_create_user`) | **CRITICAL** | Customer admins are explicitly restricted to creating roles within `CUSTOMER_ROLES = {"CUSTOMER_ADMIN", "CUSTOMER_OPERATOR", "CUSTOMER_TECHNICIAN", "CUSTOMER_VIEWER"}`. Attempting to assign `NOC_*` roles raises HTTP 403. | Verified by `test_15_customer_rbac_boundaries_and_role_creation` |
| **THREAT-D-03** | **Credential & Secret Leakage** in device/gateway inventories | Inventory Manager (`InventoryManager`) | **HIGH** | `credential_ref` fields are explicitly sanitized to `"[REDACTED]"` on retrieval. Passwords and credentials never enter the portal serialization pipeline. | Verified by `test_08_customer_device_read_only_and_credential_redaction` |
| **THREAT-D-04** | **Information Disclosure** of internal NOC engineering notes | Support Desk (`SupportRequestManager`) | **HIGH** | Support comments flagged with `is_internal = 1` are filtered out server-side by `portal_get_support_request` when accessed by customer tenants. | Verified by `test_13_customer_support_request_lifecycle` |
| **THREAT-D-05** | **Zombie Session Access** after tenant suspension or logout | Identity Manager (`IdentityManager`) | **HIGH** | `validate_session_token()` checks tenant `status == 'ACTIVE'` on every request; suspended tenants receive HTTP 403. `logout` revokes session tokens in the database, preventing replay. | Verified by `test_03_suspended_tenant_rejected_at_auth`, `test_04_session_token_validation_and_lifecycle` |
| **THREAT-D-06** | **Credential Stuffing & DoS Attacks** on customer login | External Gateway / Nginx | **HIGH** | Nginx rate limiting (`zone=portal_login_zone` 5 req/min burst 10; `zone=portal_api_zone` 60 req/min burst 20). PBKDF2-HMAC-SHA256 (100k rounds) enforces cryptographic cost against offline brute forcing. | Verified by `deploy/nginx/aira_customer_portal.conf` & benchmark authentication stress test |
| **THREAT-D-07** | **Unauthorized Mutation of Live Network Infrastructure** | Live Network (`CHR`, `R-1`) | **CRITICAL** | Zero mutating endpoints exist in `/api/v1/portal/*`. All device commands, terminal sessions, and configuration actions are disabled for customer contexts. | Verified by `test_08_customer_device_read_only_and_credential_redaction` & architecture invariant audit |
| **THREAT-D-08** | **Cross-Site Scripting (XSS) & Clickjacking** via external web access | Frontend & Reverse Proxy | **MEDIUM** | Strict HTTP security headers enforced by Nginx: `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, and restrictive `Content-Security-Policy`. | Verified by `deploy/nginx/aira_customer_portal.conf` |

---

### 3. Server-Side Scope Derivation Architecture (Anti-IDOR)

AIRA OS Phase D mandates complete elimination of client-influenced scoping:

```
[External Customer Request]
        │
        ├── Header: Authorization: Bearer <session_token>
        ├── URL: /api/v1/portal/devices/dev_alpha_01
        ▼
[FastAPI Dependency: get_current_tenant_context]
        │
        ├── 1. SHA-256 Hash of Bearer Token
        ├── 2. DB Lookup in `operational_sessions` JOIN `operational_users` JOIN `operational_tenants`
        ├── 3. Verification: Token Valid? Not Expired? Tenant Status == 'ACTIVE'?
        ▼
[TenantSecurityContext(tenant_id="tenant_acme", user_id="usr_01", roles=["CUSTOMER_ADMIN"])]
        │
        ▼
[SQL Query Execution via Repository/Manager]
        │
        ├── Parameterized Query:
        │   SELECT * FROM operational_devices 
        │   WHERE device_id = 'dev_alpha_01' AND tenant_id = 'tenant_acme';
        ▼
[Resource Match?]
        ├── YES ──► Sanitize Credentials ──► Return Safe DTO
        └── NO  ──► Raise HTTP 404 ("Device not found") [Zero Leakage of Target Existence]
```

### 4. Role-Based Access Control (RBAC) Matrix

Phase D enforces five distinct customer roles with granular permissions:

| Customer Role | Allowed Permissions | Denied Permissions |
| :--- | :--- | :--- |
| **CUSTOMER_OWNER** | Full tenant scope: `TENANT_READ`, `DEVICE_READ`, `SITE_READ`, `GATEWAY_READ`, `INCIDENT_READ`, `INCIDENT_ACKNOWLEDGE`, `SLA_READ`, `REPORT_READ`, `USER_MANAGE`, `SETTINGS_MANAGE` | `TENANT_MANAGE`, `RECOMMENDATION_APPROVE`, `RECOMMENDATION_REJECT`, `CONFIG_MUTATE` |
| **CUSTOMER_ADMIN** | Organization admin: `DEVICE_READ`, `SITE_READ`, `GATEWAY_READ`, `INCIDENT_READ`, `INCIDENT_ACKNOWLEDGE`, `SLA_READ`, `REPORT_READ`, `USER_MANAGE`, `SETTINGS_MANAGE` | `TENANT_MANAGE`, `RECOMMENDATION_APPROVE`, `RECOMMENDATION_REJECT`, `CONFIG_MUTATE` |
| **CUSTOMER_OPERATOR** | Operations: `DEVICE_READ`, `SITE_READ`, `GATEWAY_READ`, `INCIDENT_READ`, `INCIDENT_ACKNOWLEDGE`, `SLA_READ`, `REPORT_READ` | `USER_MANAGE`, `SETTINGS_MANAGE`, `RECOMMENDATION_APPROVE`, `TENANT_MANAGE` |
| **CUSTOMER_TECHNICIAN**| Field tech: `DEVICE_READ`, `SITE_READ`, `GATEWAY_READ`, `INCIDENT_READ`, `REPORT_READ` | `INCIDENT_ACKNOWLEDGE`, `USER_MANAGE`, `SETTINGS_MANAGE`, `SLA_READ` |
| **CUSTOMER_VIEWER** | Executive/Auditor: `DEVICE_READ`, `SITE_READ`, `INCIDENT_READ`, `SLA_READ`, `REPORT_READ` | All mutation, acknowledge, user management, and setting modifications |

### 5. Reverse Proxy Security Hardening Specification

The Nginx configuration defined in `deploy/nginx/aira_customer_portal.conf` enforces enterprise edge perimeter protection:

```nginx
# Security Headers
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss:; font-src 'self';" always;

# Rate Limiting
limit_req_zone $binary_remote_addr zone=portal_login_zone:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=portal_api_zone:10m rate=60r/m;
```

### 6. Audit Conclusion

The Customer Self-Service Portal (WP 8.9) meets and exceeds all security requirements established for Networking VIII Phase D. With server-side tenant scope derivation, strict anti-IDOR checks, redacted credentials, hardened RBAC boundaries, and enterprise reverse-proxy controls, the subsystem is fully certified for external multi-tenant production deployment.
