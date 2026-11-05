# AIRA OS — NETWORKING VIII: CUSTOMER PORTAL API SPECIFICATION
## REST Endpoints, Request Schemas & Response Contracts (WP 8.9)

**Document Reference:** `docs/NETWORKING_VIII/CUSTOMER_PORTAL_API_SPECIFICATION.md`  
**Milestone:** Networking VIII — Phase D  
**Scope:** Public API Contract for `/api/v1/portal/*`  
**Date:** 2026-11-04  
**Status:** **AUTHORITATIVE API SPECIFICATION**

---

### 1. API Architecture & Standards

All Customer Portal endpoints reside under the `/api/v1/portal` namespace.
- **Protocol:** HTTPS / TLS 1.3
- **Authentication:** `Authorization: Bearer aira_tok_<32_bytes>`
- **Content-Type:** `application/json`
- **Timezone Standard:** ISO 8601 UTC strings (`YYYY-MM-DDTHH:MM:SSZ`)
- **Default Pagination:** `limit=50`, `offset=0`

---

### 2. Endpoints Inventory

#### 2.1 Authentication & Profile
- `POST /api/v1/portal/auth/login`
  - Body: `{"username_or_email": "...", "password": "..."}`
  - Response: `{"token": "aira_tok_...", "user": {...}, "tenant": {...}}`
- `POST /api/v1/portal/auth/logout`
  - Headers: `Authorization: Bearer aira_tok_...`
  - Response: `{"success": true, "message": "Session invalidated."}`
- `GET /api/v1/portal/auth/me`
  - Headers: `Authorization: Bearer aira_tok_...`
  - Response: Current user profile, tenant information, active role, and granted permissions.

#### 2.2 Operational Dashboard
- `GET /api/v1/portal/dashboard/overview`
  - Summary metrics: total devices, online devices, offline devices, active incidents, critical incidents, gateway liveness, tenant overall health state (`HEALTHY`, `DEGRADED`, `CRITICAL`, `UNKNOWN`), monthly SLA availability %.
- `GET /api/v1/portal/dashboard/health`
  - Health score cards across 6 architectural dimensions (`DEVICE`, `INTERFACE`, `SITE`, `SERVICE`, `GATEWAY`, `TENANT`).

#### 2.3 Inventory (Sites & Devices)
- `GET /api/v1/portal/sites`
  - Returns list of authorized customer sites, address, timezone, and device counts.
- `GET /api/v1/portal/devices`
  - Query Params: `site_id`, `status`, `device_type`, `limit`, `offset`
  - Returns customer devices (name, management_ip, type, vendor, model, status, last_seen, gateway_id).
- `GET /api/v1/portal/devices/{device_id}`
  - Returns single device details with redacted credentials.

#### 2.4 Incidents
- `GET /api/v1/portal/incidents`
  - Query Params: `state`, `severity`, `limit`, `offset`
  - Returns tenant incidents (incident_id, title, severity, state, summary, affected_services, affected_devices, created_at, resolved_at).
- `GET /api/v1/portal/incidents/{incident_id}`
  - Returns incident details with customer-visible timeline.
- `POST /api/v1/portal/incidents/{incident_id}/acknowledge`
  - Permission: `incident.acknowledge`
  - Acknowledges active incident for customer.

#### 2.5 SLA & Reports
- `GET /api/v1/portal/sla/summary`
  - Returns summary of active services and their measured SLA compliance.
- `GET /api/v1/portal/sla/reports`
  - Query Params: `service_id`, `start_time`, `end_time`
  - Generates or retrieves SLA measurement report (measured_availability, total_downtime_seconds, maintenance_excluded_seconds, data_coverage_percent, error_budget_remaining_percent, status).

#### 2.6 Support & Service Requests
- `GET /api/v1/portal/support/requests`
  - Query Params: `status`, `category`, `limit`, `offset`
  - Returns customer support requests.
- `POST /api/v1/portal/support/requests`
  - Body: `{"category": "INCIDENT|SERVICE_REQUEST|BILLING|GENERAL|CHANGE", "subject": "...", "description": "...", "priority": "LOW|MEDIUM|HIGH|CRITICAL"}`
  - Permission: `support.create`
  - Creates new support ticket in `OPEN` state.
- `GET /api/v1/portal/support/requests/{request_id}`
  - Returns ticket details and chronological comments.
- `POST /api/v1/portal/support/requests/{request_id}/comments`
  - Body: `{"message": "..."}`
  - Permission: `support.comment`
  - Adds customer comment to active ticket.

#### 2.7 User Management & Notification Preferences
- `GET /api/v1/portal/users`
  - Permission: `user.manage`
  - Returns customer organization users.
- `POST /api/v1/portal/users`
  - Permission: `user.manage`
  - Body: `{"username": "...", "email": "...", "password": "...", "role_type": "CUSTOMER_ADMIN|CUSTOMER_OPERATOR|CUSTOMER_VIEWER"}`
- `GET /api/v1/portal/notifications/preferences`
  - Returns active user notification preferences.
- `PATCH /api/v1/portal/notifications/preferences`
  - Updates notification preference toggles.
