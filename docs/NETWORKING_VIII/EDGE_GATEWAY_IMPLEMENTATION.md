# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.4
# HYBRID INFRASTRUCTURE & EDGE GATEWAY IMPLEMENTATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.4 — Hybrid Edge Gateway Subsystem  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  
**Execution Environment:** Windows, ThinkPad X270 (Intel Core i7-7500U, 8 GB RAM, CPU-Only)

---

## 1. ARCHITECTURAL OVERVIEW

The AIRA OS Hybrid Edge Gateway subsystem enables secure, distributed monitoring and diagnostics across customer sites without exposing customer network segments to the public internet.

The architecture strictly adheres to three fundamental design invariants:
1. **Zero Central Telemetry Ingestion Duplicate:** Telemetry collection remains exclusively owned by `HardenedNmsScheduler`. The Edge Gateway acts as a localized, read-only collection proxy for remote customer sites and submits normalized envelopes to Central NOC.
2. **100% Read-Only Network Device Sandbox:** Network devices (`CHR`, `R-1`, customer routers/switches) are never mutated. Arbitrary shell execution and command chaining are strictly blocked at the edge collector boundary.
3. **Strict Multi-Tenant Scoping:** Gateway authorization is cryptographically bound to a single `(tenant_id, site_id)` tuple. Device references in telemetry envelopes are validated against database ownership, completely preventing cross-tenant injection.

```
+-----------------------------------------------------------------------------------------+
|                                CENTRAL NOC (AIRA OS Core)                               |
|                                                                                         |
|  +------------------------+      +------------------------+      +-------------------+  |
|  |  FastAPI Router        |      |  Gateway Ingestion Hub |      |  Hardened NMS     |  |
|  |  /api/v1/gateways/*    | ---> |  - Token Auth          | ---> |  Metrics Store    |  |
|  |                        |      |  - Tenant Scope Guard  |      |  (nms_raw_metrics)|  |
|  +------------------------+      |  - Sequence Monotonic  |      +-------------------+  |
|                                  +------------------------+                             |
|                                              ^                                          |
+----------------------------------------------|------------------------------------------+
                                               | Outbound TLS (mTLS / Bearer)
                                               | Batched Telemetry Envelopes
+----------------------------------------------|------------------------------------------+
|                       CUSTOMER SITE: EDGE GATEWAY DAEMON                                |
|                                                                                         |
|  +------------------------+      +------------------------+      +-------------------+  |
|  | Read-Only Diagnostics  |      | Bounded SQLite Buffer  |      | HTTPS Ingestion   |  |
|  | & Sanitized Collector  | ---> | (edge_buffer.db)       | ---> | Client / Dispatch |  |
|  | - Command Whitelist    |      | - Bounded Cap (5,000)  |      | - Backoff Retry   |  |
|  | - Shell Delim Guard    |      | - FIFO Drop on Full    |      | - Token Refresh   |  |
|  +------------------------+      +------------------------+      +-------------------+  |
|              |                                                                          |
|              v (SSH / REST read-only)                                                   |
|  +-----------------------------------------------------------------------------------+  |
|  |  Local Customer Infrastructure (e.g. 192.168.1.1, RFC 1918 Overlapping Subnets)  |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

---

## 2. SUBSYSTEM COMPONENTS & RESPONSIBILITIES

### 2.1 Domain Models ([`core/edge_gateway/models.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/models.py))
- `GatewayStatus`: `PROVISIONING`, `ENROLLMENT_PENDING`, `ACTIVE`, `DEGRADED`, `OFFLINE`, `REVOKED`, `DECOMMISSIONED`.
- `TokenStatus`: `ACTIVE`, `REDEEMED`, `EXPIRED`, `REVOKED`.
- `TelemetryType`: `INTERFACE_METRICS`, `DEVICE_HEALTH`, `TOPOLOGY_LINK`, `ALERT_EVENT`, `DIAGNOSTIC_SAMPLE`.
- `EdgeGateway`: Core entity dataclass tracking `gateway_id`, `tenant_id`, `site_id`, `name`, `status`, `version`, `certificate_fingerprint`, `auth_token_hash`, and timestamps.
- `TelemetryEnvelope`: Standardized message envelope enforcing monotonic sequence tracking (`sequence_number`), `envelope_id`, `telemetry_type`, `payload`, and `source_timestamp`.

### 2.2 Relational Persistence ([`core/edge_gateway/db.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/db.py))
Manages relational tables and composite indexes in `topology.db`:
- `operational_gateways`: Gateway metadata, cryptographic auth hashes, status, and last contact.
- `operational_gateway_tokens`: Short-lived single-use enrollment tokens with SHA-256 storage and atomic status updates.
- `operational_gateway_sequences`: Sequence tracking cursor per gateway for strict replay attack prevention.
- `operational_gateway_heartbeats`: Heartbeat telemetry logs (CPU, memory, queue depth, collector health).
- `nms_raw_metrics`: Central unaggregated telemetry samples shared with NMS metrics pipeline.

### 2.3 Enrollment Service ([`core/edge_gateway/enrollment.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/enrollment.py))
- Generates 256-bit cryptographically secure enrollment tokens (`secrets.token_urlsafe(32)`).
- Sets 15-minute expiration default.
- Implements atomic single-use redemption with conditional database updates (`UPDATE ... WHERE status = 'ACTIVE'`).
- Issues high-entropy Bearer authentication tokens for enrolled gateways.

### 2.4 Telemetry Ingestion Hub ([`core/edge_gateway/ingestion.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/ingestion.py))
- Authenticates incoming edge gateway requests via SHA-256 token verification.
- Enforces strict tenant scoping: Ignores client-supplied tenant headers and resolves ownership exclusively from server database.
- Checks device ownership: Validates target device ID belongs to gateway's `(tenant_id, site_id)`.
- Monotonic sequence verification: Drops duplicates and replayed sequence numbers with zero database pollution.
- Rejection of oversized payloads (> 512 KB) and malformed envelopes.

### 2.5 Bounded Local Buffer ([`core/edge_gateway/buffer.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/buffer.py))
- Embedded SQLite queue (`edge_buffer.db`) operating in WAL mode.
- Bounded capacity (default max 5,000 samples, configurable).
- FIFO drop policy: Drops oldest samples when capacity is reached while maintaining exact dropped sample accounting.
- Survives process restarts and system reboots.
- Reconnection batch draining: Peeks batches, drains to Central NOC, and deletes acknowledged envelopes atomically.

### 2.6 Read-Only Diagnostic Collector Sandbox ([`core/edge_gateway/collector.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/collector.py))
- Diagnostic command whitelist: Only permitted read-only RouterOS commands (`/system/resource/print`, `/interface/print`, `/ip/address/print`, `/ip/route/print`, `/ip/arp/print`, `/ping count=3`).
- Injection sanitizer: Rejects `;`, `&`, `|`, `` ` ``, `$()`, `>`, `<`, `\n`, `\r`, `\x00`.
- Mutation blocker: Blocks `add`, `set`, `remove`, `enable`, `disable`, `reset`, `edit`, `export`, `/file/`.
- Credential masking: Protects RouterOS credentials from ever appearing in telemetry envelopes.

### 2.7 Management Facade ([`core/edge_gateway/manager.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/edge_gateway/manager.py))
- Single access point coordinating enrollment, heartbeat recording, telemetry ingestion, status transitions, and revocation.
- Liveness evaluation: Evaluates offline timeouts (default 180s without heartbeat triggers `OFFLINE` status).
- Tenant suspension enforcement: Suspended tenant automatically revokes all associated gateways.

### 2.8 REST API Router ([`api/routers/gateways.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/api/routers/gateways.py))
Exposes the following endpoints under `/api/v1/gateways`:
- `POST /api/v1/gateways/tokens`: Generate enrollment token (NOC Operator / Admin).
- `POST /api/v1/gateways/enroll`: Redeem enrollment token and register edge gateway.
- `GET /api/v1/gateways`: List gateways (scoped to tenant or NOC view).
- `GET /api/v1/gateways/{gateway_id}`: Retrieve detailed gateway status and health.
- `POST /api/v1/gateways/{gateway_id}/revoke`: Revoke gateway credentials immediately.
- `POST /api/v1/gateways/heartbeat`: Ingest gateway heartbeat (authenticated by Bearer token).
- `POST /api/v1/gateways/telemetry`: Ingest batch of telemetry envelopes.

### 2.9 React GUI Console ([`app/frontend/src/pages/GatewaysPage.jsx`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/pages/GatewaysPage.jsx))
- Tenant-scoped and site-scoped gateway inventory table.
- Real-time status badges (`ACTIVE`, `OFFLINE`, `REVOKED`, etc.).
- Liveness indicators and queue depth monitoring.
- Modal dialog for generating single-use enrollment tokens with 15-minute countdown and copy-to-clipboard.
- One-click gateway credential revocation with confirmation dialog.

---

## 3. VERIFICATION SUMMARY
- **Unit & Security Tests:** 16/16 test scenarios passed in 14.34s ([`tests/test_networking_viii_phase_b.py`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_networking_viii_phase_b.py)).
- **Frontend Build & Tests:** 275/275 tests passed in 3.90s; Vite production build completed in 4.04s.
- **Regression Tests:** All Phase A and Networking VII tests (35/35) passed cleanly.
