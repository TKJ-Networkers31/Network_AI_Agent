# AIRA OS — NETWORKING VIII: ARCHITECTURE & SUBSYSTEM AUDIT
## Work Package 8.0 — Baseline Inspection, Capability Inventory & Reuse Matrix

**Document ID:** `AIRA-NET8-AUDIT-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Branch:** `main` (HEAD: `be59871acd2dd92c581d8944e65899d485f208ae`)  
**Hardware Target:** ThinkPad X270 (Intel Core i7-7500U @ 2.70 GHz, 8 GB RAM, CPU-Only)  
**Organization:** LS Technology

---

## 1. Executive Mission

The objective of **Networking VIII** is to evolve AIRA OS from a single-workstation network engineering copilot into a **Hybrid Multi-Tenant Network Operations Center (NOC) and Operational Decision Intelligence Platform**.

This audit inspects the current repository state across all subsystems (Networking IV, V, VI, and VII), establishes an authoritative inventory of existing capabilities, identifies security boundaries and potential architectural conflicts, and defines a strict reuse matrix to ensure zero wasteful duplication.

---

## 2. Existing Subsystem Inventory

### 2.1 Backend Modules (`AIRA_ECOSYSTEM/`)

| Subsystem / Layer | Path | Core Modules & Responsibilities | Current Scope & Status |
| :--- | :--- | :--- | :---: |
| **API Transport** | `api/` | `main.py`, `ws_bridge.py`, `ws_manager.py`, 22 endpoint routers under `api/routers/`. | Single-tenant, local HTTP & WS. |
| **Canonical Network** | `core/canonical_network.py` | Unified device identity (`CanonicalDevice`), observation normalization, freshness tracking. | Single-tenant global device IDs. |
| **Inventory Store** | `core/inventory_store.py` | `inventory.db` manager, Fernet AES-128 secret encryption, device credentials. | Single-tenant global device names. |
| **Network Intelligence** | `core/network_intelligence/` | `evidence_service.py`, `knowledge_graph.py`, `rca_engine.py`, `anomaly_engine.py`, `baseline_engine.py`, `failure_simulator.py`. | Networking VI verified; cluster-scoped bundles. |
| **Route Intelligence** | `core/routing/` | `UnifiedRouteParser`, `NormalizedRoute`, `RouteParseReport`, LPM evaluation, flap detection. | Networking IV verified. |
| **NMS & Telemetry** | `core/nms/` | `HardenedNmsScheduler`, metrics pipeline, 5m/1h rollups, threshold alerts. | Networking V verified; single hardware poller. |
| **Proactive Operations** | `core/operations/` | `predictive_engine.py`, `change_impact_engine.py`, `service_intelligence.py`, `scheduler.py`, `calendar/`, `incident_engine.py`, `notification_hub.py`, `reporting_engine.py`. | Networking VII verified; Asia/Jakarta timezone. |
| **Concurrency & DB** | `core/topology_db.py` | `topology_transaction` context manager, single-writer `RLock`, WAL mode, 30s busy timeout. | Shared `topology.db` persistence. |
| **Internal Event Bus** | `core/events.py` | `EventBus` pub/sub, `event_scope` contextvars, thread-safe async/sync dispatch. | Global broadcast bus. |
| **Agent Core (AKANE/REI)** | `agents/` | `connection_manager.py` (APCE SSH pooling), `dio_tools.py`, `provider_client.py`. | Sandboxed read-only SSH executor. |

### 2.2 Frontend Architecture (`app/frontend/src/`)

- **Framework:** React 19, Tailwind CSS, Lucide Icons, Vite 6.4.1.
- **Routing:** State-based SPA router in `App.jsx` with code-splitting via `lazyWithRetry()` and Suspense.
- **Pages:** `ChatPage.jsx`, `WorkspacePage.jsx`, `TopologyPage.jsx`, `NmsPage.jsx`, `OperationsPage.jsx`, `DevicesPage.jsx`, `NetworkIntelligencePage.jsx`, `AkaneWorkspace.jsx`, `ModelsPage.jsx`, `PersonaPage.jsx`, `MemoryPage.jsx`, `LogsPage.jsx`, `SettingsPage.jsx`.
- **Navigation:** Grouped menu structure defined in `components/navConfig.js`.

---

## 3. Database Schema & Persistence Inventory

AIRA OS currently persists data across dedicated SQLite databases operating in WAL mode:

### 3.1 `topology.db` (Primary Topology, Telemetry & Operations Store)
Contains 30 verified relational tables:
1. **Topology Subsystem:** `topology_nodes`, `topology_edges`, `topology_links`, `topology_evidence`, `topology_edge_evidence`, `topology_snapshots`, `topology_changes`, `topology_conflicts`, `topology_audit_log`, `topology_discovery_jobs`, `topology_policy`, `topology_schema_version`.
2. **Route Intelligence:** `route_snapshots`, `route_changes`.
3. **NMS Subsystem:** `nms_device_profiles`, `nms_settings`, `nms_raw_metrics`, `nms_interface_metrics`, `nms_device_metrics`, `nms_5m_rollups`, `nms_1h_rollups`, `nms_incidents`.
4. **Operations Subsystem (Networking VII):** `operational_services`, `operational_service_endpoints`, `operational_jobs`, `operational_job_runs`, `operational_maintenance_windows`, `operational_incidents`, `operational_notifications`.

### 3.2 `inventory.db` (Encrypted Device Credentials)
Contains:
1. `devices` (configured name, host, port, username, type, notes).
2. `credentials` (Fernet-encrypted secrets: ssh_password, ssh_key, api_key, snmp_community).
3. `device_credentials` (M:N device-to-credential mapping).

### 3.3 `network_intelligence.db` (Analysis, Investigations & Evidence)
Contains:
1. `evidence_items` (canonical raw and normalized evidence records).
2. `intelligence_investigations` (RCA findings, hypotheses, and evidence links).
3. `configuration_plans` (version-aware desired-state plans).
4. `playbook_runs` (state-machine playbook executions).
5. `incidents` (investigation-linked incidents).

---

## 4. Security, Authentication & Tenant Boundaries Audit

### 4.1 Current Authentication Mechanism
- **Finding:** Currently, AIRA OS operates in a single-operator local mode. There is no user login, session cookie, or JWT token system on general FastAPI endpoints.
- **Only Existing Auth Check:** `AIRA_TOPOLOGY_ADMIN_TOKEN` / `AIRA_ADMIN_TOKEN` environment variable check on mutating topology routes in `api/routers/topology.py`.
- **Implication for Networking VIII:** A unified, lightweight, secure Identity and RBAC layer must be introduced to authenticate both Internal NOC Operators (e.g. `NOC_ADMIN`, `NOC_OPERATOR`) and Customer Users (e.g. `CUSTOMER_ADMIN`, `CUSTOMER_VIEWER`).

### 4.2 Current Device Identity & Address Space Handling
- **Finding:** `CanonicalDevice` in `core/canonical_network.py` uses `device_id` as the primary key and resolves devices based on `management_ip` or `inventory_name`.
- **Architectural Conflict:** In a multi-tenant MSP/NOC environment, multiple distinct customers (Tenant A and Tenant B) frequently use identical RFC 1918 private IP subnets (e.g. `192.168.1.1` or `10.0.0.1`). In the current single-tenant model, this would cause catastrophic device identity collisions and cross-tenant data corruption!
- **Resolution for Networking VIII:**
  Device identity must be strictly scoped: `(tenant_id, site_id, device_id)`. The `device_id` must be globally unique (UUID4 or prefixed `dev_{tenant}_{site}_{id}`), and IP-based resolution must always be scoped by `(tenant_id, site_id)`.

### 4.3 WebSocket & Event Bus Isolation
- **Finding:** `core/events.py` broadcasts events across all subscribers. `api/ws_bridge.py` forwards Event Bus events to connected WebSockets at `/ws/chat/{session_id}`.
- **Architectural Conflict:** Without tenant scoping, an event emitted for Customer A (e.g. an interface failure or high-utilization alert) could leak to a connected Customer B session!
- **Resolution for Networking VIII:**
  All event envelopes must mandate `tenant_id` (and optional `site_id`). The WebSocket bridge must filter events before sending them to customer-authenticated connections.

---

## 5. Architectural Capability Reuse Matrix

| Capability | Existing Implementation | Required Change for Networking VIII | Architectural Decision |
| :--- | :--- | :--- | :---: |
| **NMS Hardware Polling** | `core/nms/scheduler.py` (`HardenedNmsScheduler`) | Extend with tenant/site context. Must remain the sole poller. | **REUSE & PRESERVE** (Zero duplicate polling) |
| **Evidence Assembly** | `core/network_intelligence/evidence_service.py` | Add tenant-scoping filter to `assemble_evidence_bundle()`. | **EXTEND** (Add tenant context) |
| **Knowledge Graph** | `core/network_intelligence/knowledge_graph.py` | Tenant-scoped graph instances. Isolated in-memory subgraphs per tenant. | **REUSE** (Instantiate per tenant) |
| **Root Cause Analysis (RCA)** | `core/network_intelligence/rca_engine.py` | Scope hypothesis evaluation to tenant's graph and evidence. | **REUSE** (Do not duplicate RCA) |
| **Predictive Operations** | `core/operations/predictive_engine.py` | Keep single-pass regression engine. Feed tenant-isolated metric series. | **REUSE** (100% reusable as-is) |
| **Change Impact Simulation** | `core/operations/change_impact_engine.py` | Ensure deep cloning operates on tenant-scoped graph. | **REUSE** (Non-destructive guarantee) |
| **Operational Scheduler** | `core/operations/scheduler.py` | Add `tenant_id` to `operational_jobs` and filter job execution. | **EXTEND** (Add tenant scoping) |
| **Calendar Manager** | `core/operations/calendar/` | Add `tenant_id` to `operational_maintenance_windows`. | **EXTEND** (Add tenant scoping) |
| **Incident Engine** | `core/operations/incident_engine.py` | Add `tenant_id` and `site_id` to incident records and state transitions. | **EXTEND** (Add tenant scoping) |
| **Notification Hub** | `core/operations/notification_hub.py` | Add `tenant_id` to notifications; isolate customer vs NOC channels. | **EXTEND** (Add tenant scoping) |
| **Reporting Engine** | `core/operations/reporting_engine.py` | Parameterize report compilation with authenticated `tenant_id`. | **EXTEND** (Tenant-safe generation) |
| **Command Execution & Security** | `core/network_intelligence/security.py` | Retain 10-layer command sanitizer and strict read-only boundary. | **REUSE & PRESERVE** (Zero mutations) |
| **Database Concurrency** | `core/topology_db.py` | Retain `topology_transaction` context manager and WAL concurrency. | **REUSE & PRESERVE** (Single-writer WAL) |
| **Device Credential Storage** | `core/inventory_store.py` | Add `tenant_id` and `site_id` foreign keys to `devices` table. | **EXTEND** (Scope inventory) |
| **Frontend Operations Center** | `pages/OperationsPage.jsx` | Extend for internal NOC operators with cross-tenant filter and navigation. | **EXTEND** (Add multi-tenant selector) |
| **Customer Portal** | *None* | Create dedicated `CustomerPortalPage.jsx` for customer-facing users. | **NEW CAPABILITY** |
| **Edge Gateway Management** | *None* | Create `core/edge_gateway/` for hybrid outbound gateway connections. | **NEW CAPABILITY** |
| **Operational Decision Engine** | *None* | Create `core/decision/` consuming RCA, capacity risks, and SLAs. | **NEW CAPABILITY** |
| **SLA Tracking Engine** | *None* | Create `core/sla/` for deterministic uptime & error budget metrics. | **NEW CAPABILITY** |
| **Identity, RBAC & Context** | *None* | Create `core/tenant/` for tenant context, roles, permissions, JWT/tokens. | **NEW CAPABILITY** |

---

## 6. Resource Budget & Constraints (ThinkPad X270 Profile)

Development & runtime target: **ThinkPad X270 (Intel Core i7-7500U, 8 GB RAM, CPU-Only)**.
To maintain flawless stability without swapping or CPU starvation:
1. **Shared Database Strategy:** Rather than opening 50 separate SQLite database connections and thread-pools simultaneously, use a shared SQLite database architecture with explicit `tenant_id` columns and repository-level scoping.
2. **Bounded Concurrency:** Edge Gateway message processing, predictive regressions, and report generations must be bounded via `ThreadPoolExecutor(max_workers=2)`.
3. **No Unbounded Memory Graphs:** Do not load all 50 customer knowledge graphs simultaneously into memory. Instantiate or cache tenant graphs on demand with LRU eviction (max 5 active tenant graphs).
4. **Deterministic Decision Intelligence First:** Generative LLMs must remain optional and asynchronous; the decision engine and risk calculations must execute deterministically in Python in $< 10$ ms.
