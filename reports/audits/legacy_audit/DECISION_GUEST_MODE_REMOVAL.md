# AIRA OS — OWNER DECISION: COMPLETE REMOVAL OF GUEST MODE & GUEST USERS
(`DECISION_GUEST_MODE_REMOVAL.md`)

**Date**: 2026-11-08  
**Status**: APPROVED & MANDATORY  
**Decision Authority**: System Owner  
**Supersedes**: Decision BD-04 (which conditionally contemplated securing guest mode), Phase E.1 Section 1 Guest Access, and all legacy guest backdoors.

---

## 1. PURPOSE AND RATIONALE

AIRA OS controls mission-critical network infrastructure (MikroTik RouterOS, SSH CLI, automated network playbooks, NMS telemetry).
In the original audit package:
1. `?guest=1` in query parameters or `localStorage.getItem("aira_guest_session")` allowed the React frontend to render without backend authentication (`BUG-03`).
2. An anonymous client passing `X-Guest-ID: gst_anything` could receive a synthesized `TenantContext` in `core/tenant/auth_deps.py`, which exposed unauthenticated endpoints to anonymous execution.
3. Attempting to maintain a sanitized "Guest Mode" creates ongoing risk of tenant data leakage, authorization confusion, and privilege escalation.

Therefore, the owner has explicitly ordered the **complete removal of Guest User and Guest Mode across all backend services, database definitions, frontend routes, and client storage**.

---

## 2. SCOPE OF ELIMINATION

The following components and behaviors are **permanently removed**:

### 2.1 Backend Authentication & Context
- Removal of `UserRoleType.GUEST` from `core/tenant/models.py`.
- Removal of `_resolve_guest_or_auth_context()` and guest fallback in `core/tenant/auth_deps.py`.
- Every protected endpoint requires a verified `Bearer <token>` belonging to an active user in `operational_user_sessions`.
- Any unauthenticated request without a valid session token receives `HTTP 401 Unauthorized` with `WWW-Authenticate: Bearer`.
- Removal of synthetic guest usernames (`guest_*`), `tenant_guest`, and guest pool contexts.

### 2.2 Database Structures & Seeds
- Removal of `GUEST` from any SQLite role/tier `CHECK` constraints.
- Removal of `pol_global_guest` seed row in `core/tenant/db.py` (which previously violated `CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM'))`).
- Purge of any guest session or memory logic.

### 2.3 Frontend UI & Storage
- Removal of `localStorage.getItem("aira_guest_id")` and automatic `X-Guest-ID` header generation in `app/frontend/src/api.js`.
- Removal of `?guest=1` URL search parameter checks and `aira_guest_session` storage in `App.jsx`.
- Removal of `continueAsGuest` buttons and handlers in `LoginRequiredModal.jsx`, `RegisterModal.jsx`, and `AuthContext.jsx`.
- All UI routes require an authenticated user; unauthenticated visitors are redirected to the Login page/modal.

---

## 3. STRICT PRESERVATION INVARIANTS

1. **Legitimate Public Endpoints**:
   - `POST /api/v1/auth/login` (Authentication)
   - `POST /api/v1/auth/mfa/verify` (MFA completion)
   - `GET /health` or `/api/health` (Service health check)
   - `GET /api/v1/auth/csrf` (CSRF token retrieval)
2. **Edge Gateway M2M Separation**:
   - Appliance onboarding (`POST /api/v1/gateways/enroll`) validates single-use enrollment tokens.
   - Appliance telemetry heartbeat (`POST /api/v1/gateways/heartbeat`) validates appliance M2M Bearer tokens.
   - Gateway M2M is strictly independent of user browser sessions.

---

## 4. ACCEPTANCE CRITERIA

1. Passing `?guest=1` or setting `aira_guest_session` in localStorage does NOT grant access to any page.
2. Sending `X-Guest-ID` without a valid Bearer token returns `HTTP 401 Unauthorized` on all protected endpoints.
3. No `GUEST` role exists in `ROLE_PERMISSIONS` or `UserRoleType`.
4. Automated tests confirm 100% rejection of anonymous visitors attempting protected operations.
