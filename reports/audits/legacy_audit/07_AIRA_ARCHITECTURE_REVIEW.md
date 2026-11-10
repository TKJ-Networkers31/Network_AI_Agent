# PHASE 7 — AIRA SPECIFIC ARCHITECTURE REVIEW (`07_AIRA_ARCHITECTURE_REVIEW.md`)

**Audit Date**: 2026-11-08  
**Target Directory**: `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM`  
**Audit Mode**: Read-Only Architectural & Operational Boundary Verification

---

## 1. Organization, User, Group & Permission Architecture (Section A)

### 1.1 Role & Group Hierarchy Evaluation
AIRA OS defines a 6-tier RBAC group hierarchy in [`core/tenant/rbac_service.py:30-156`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/rbac_service.py#L30-L156) and [`core/tenant/models.py:2112-2225`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/models.py#L2112-L2225):
1. **Super Admin / Platform Owner (`grp_super_admin` / `SUPER_ADMIN` / `PLATFORM_OWNER`)**: Full wildcard (`*`) access across all tenants, models, billing, and RBAC.
2. **Organization Admin (`grp_admin` / `ADMIN` / `TENANT_ADMIN`)**: User/group management (`users.*`, `groups.*`), device/topology/NMS administration, and audit log viewing.
3. **Network Engineer / Operator (`grp_network_engineer`, `grp_network_operator` / `NOC_ENGINEER`, `OPERATOR`)**: Operational read/write access to devices, connections, topology, NMS, and playbooks.
4. **Member / Standard User (`grp_member` / `MEMBER`)**: Conversational AI, personal memory/persona, and read-only workspace access.
5. **Viewer / Read-Only User (`grp_viewer` / `READ_ONLY`, `CUSTOMER_VIEWER`)**: Read-only access (`*.read` / `*.view`) to dashboards, topology, NMS, and logs.
6. **Guest User (`GUEST`)**: Officially removed in Phase F.1 (`api/routers/auth.py:5`), yet residual guest code remains active in `core/tenant/auth_deps.py:20-37`!

### 1.2 Critical Architectural Failures in RBAC Resolution (`CONFIRMED`)

| Architectural Component | Actual Implementation | Proven Defect & Operational Risk |
|---|---|---|
| **Superadmin Identity Check** | [`core/tenant/models.py:2233`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/models.py#L2233), [`auth_deps.py:111`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/auth_deps.py#L111), [`rbac_service.py:264`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/rbac_service.py#L264) | Hardcodes `username.lower() in ("lingga_admin", "admin")` as an unconditional superadmin bypass before checking RBAC tables. |
| **Platform Admin Guard (`require_platform_admin`)** | [`api/routers/admin_platform.py:62`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/admin_platform.py#L62) | Checks `if not (ctx.is_internal or any(r in admin_roles for r in ctx.roles)):`. Because all users in `tenant_internal` have `ctx.is_internal == True`, **every internal user (even a `READ_ONLY` viewer) has full Platform Admin privileges**, including `POST /api/v1/admin/impersonate` (`L213`)! |
| **Admin Group Privilege Escalation** | [`api/routers/user_management.py:98-184`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/user_management.py#L98-L184) | `create_user` (`users.create`) and `update_user` (`users.update`) allow a lower-tier `ADMIN` to assign `grp_super_admin` to themselves or overwrite `lingga_admin`'s password. |
| **Group `DENY` Rules & Overrides** | [`core/tenant/manager.py:1054-1068`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/manager.py#L1054-L1068) & [`models.py:2249-2254`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/models.py#L2249-L2254) | `validate_session_token()` computes `effective_perms` by unioning legacy `ROLE_PERMISSIONS` with `RbacService.get_effective_permissions()`, re-granting permissions that were explicitly denied by a group `DENY` rule! Furthermore, `TenantContext.has_permission()` expands `PERMISSION_ALIASES` without checking `DENY` overrides. |
| **Frontend vs Backend Permission Aliases** | [`src/context/AuthContext.jsx:285-322`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/context/AuthContext.jsx#L285-L322) vs [`core/tenant/models.py:2177-2225`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/models.py#L2177-L2225) | In `AuthContext.jsx`, `"nms.view": ["nms.read", ...]` is one-way; `hasPermission("nms.read")` (`navConfig.js:21`) returns `false` for users granted `"nms.view"`. Mobile bottom navigation (`MobileNav.jsx:50-52`) skips `hasPermission()` entirely. |
| **Write Endpoints Guarded Only by Read Permissions** | `devices.py`, `models.py`, `logs.py`, `operations.py`, `network_intelligence.py` | `READ_ONLY` viewers with `inventory.read`, `models.read`, `audit.read`, `nms.alerts.read`, or `nms.read` can create/modify/delete device credentials (`devices.py:437-447`), create/delete/reroute LLM models (`models.py:74-166`), wipe system logs (`logs.py:58`), and approve/execute operational actions (`network_intelligence.py:1566-1576`). |

---

## 2. Private User Data Isolation Review (Section B)

| Private User Data Domain | Storage Mechanism | Isolation Status | Evidence & Leakage Vector |
|---|---|---|---|
| **1. Chat Sessions** | `chat_sessions.db` (`sessions.user_id`) | **PARTIALLY ISOLATED (`BROKEN ON WS & RESET`)** | `api/routers/sessions.py` enforces `sess["user_id"] == user.user_id`. **However**, `POST /api/reset` (`api/routers/chat.py:122`) and `WS /ws/chat/{session_id}` (`api/routers/ws.py:385`) have **zero authentication and zero ownership verification**! Any client knowing or guessing a `session_id` can read, truncate (`replace_from_turn_id`), or wipe any user's chat session and execute LLM turns as that user (`ws.py:319-326`). |
| **2. Personal Memory** | `long_term_memory.db` (`core/memory.py`) vs `topology.db:user_memories` (`UserMemoryService`) | **CRITICAL CROSS-USER LEAK (`CONFIRMED`)** | While `topology.db:user_memories` (`/api/v1/personalization/memory`) is scoped by `user_id`, the background chat fact extractor [`agents/rei/auto_extract.py:114`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/rei/auto_extract.py#L114) writes extracted facts to `core.memory.remember_fact()` (`long_term_memory.db:facts`, which has **no `user_id` column**), and [`core/brain.py:233`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/brain.py#L233) injects `core.memory.list_facts()` into **every user's** system prompt! |
| **3. Personal AI Persona** | `persona.db` (`core/persona/store.py`) vs `topology.db:user_personas` (`UserPersonaService`) | **SHARED GLOBAL SINGLETON (`CONFIRMED`)** | `PersonaPage.jsx` calls `/api/persona/*` (`api/routers/persona.py`), which when unauthenticated (or via `PersonaEngine` singleton in `core/persona/engine.py`) mutates `persona.db:active_persona` (`WHERE id = 1`), overwriting the persona for all users sharing the global engine! |
| **4. Personal Preferences & Location** | `topology.db:user_preferences` & `location.db` (`core/location/service.py`) | **CROSS-SESSION GPS LEAK (`CONFIRMED`)** | [`core/location/service.py:202`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/location/service.py#L202): `get_access(session_id)` falls back to `self._clients.get(self._last_session_id or "")` when the current session has not reported GPS, leaking the previous user's physical GPS coordinates! |
| **5. Personal Tokens / Quota Usage** | `topology.db:operational_token_balances` & `core/token_usage.py` | **UNENFORCED & UNSCOPED (`CONFIRMED`)** | `TokenQuotaService` is never called during chat turns (`chat.py:28, 118`); `GET /api/token-usage` (`chat.py:133`) has zero authentication and exposes global or per-session token usage to anyone. |
| **6. Personal Files, Attachments & Artifacts** | `AIRA_ECOSYSTEM/workspace/`, `uploads/`, `attachments.db`, `artifacts.db` | **ZERO ISOLATION (`CONFIRMED`)** | `files.py`, `attachments.py`, `artifacts.py`, and `workspace_links.py` have **zero authentication** and no `user_id` column in their SQLite tables. All users share a single physical `AIRA_ECOSYSTEM/workspace/` directory on the host. |

---

## 3. Guest Mode Isolation Review (Section C)

Even though [`api/routers/auth.py:5`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/auth.py#L5) states *"No Guest Mode"*, **residual Guest Mode backdoors remain active in the backend (`CONFIRMED`)**:

1. **Header Spoofing Backdoor (`core/tenant/auth_deps.py:20-37`)**:
   - `_resolve_guest_or_auth_context()` checks:
     ```python
     if guest_id and guest_id.startswith("gst_"):
         return TenantContext(
             tenant_id="tenant_guest_pool",
             user_id=guest_id,
             username=f"guest_{guest_id[-6:]}",
             roles=["GUEST"],
             is_authenticated=False,
             is_guest=True, ...
         )
     ```
   - Any unauthenticated caller passing header `X-Guest-ID: gst_123456` receives a `TenantContext` on any endpoint using `get_current_user_or_guest`.
2. **Broken Guest Quota Seed (`core/tenant/db.py:212, 753`)**:
   - The `pol_global_guest` row in `operational_token_policies` uses `tier='GUEST'`, which fails `CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM'))` and is silently ignored.
3. **Unauthenticated Access to Operational Subsystems**:
   - Because `connections.py`, `files.py`, `automations.py`, `settings.py`, `voice.py`, `artifacts.py`, `attachments.py`, `memory.py`, and `ws.py` have **zero authentication**, an unauthenticated guest has **full read/write/execute access** to router SSH connections (`/api/connections/execute`), host workspace files (`/files/write`), automation jobs (`/api/v1/automations`), global settings (`/api/settings`), and chat WebSockets (`/ws/chat/{session_id}`)!

---

## 4. Organization / Operational Shared Data Review (Section D)

| Operational Shared Resource | Multi-Tenant / Org Isolation Status | Architectural Findings |
|---|---|---|
| **Devices & Credentials** | **SPLIT-BRAIN (Global vs Tenant-Scoped)** | `inventory.db` (`devices`, `credentials`) has **no `tenant_id` column** and is shared globally across all users of `/api/devices` and `/api/connections`. Conversely, `topology.db:operational_devices` (`core/tenant/inventory_manager.py`) has `tenant_id` and is used by `/api/v1/portal/devices` and `/api/v1/gateways`. |
| **Topology (`topology_nodes`, `topology_edges`, `topology_snapshots`)** | **GLOBAL (No `tenant_id`)** | None of the 12 topology tables or 2 routing snapshot tables in `topology.db` have a `tenant_id` column. All organizations share one global topology graph. |
| **NMS Metrics, Alerts & Incidents** | **GLOBAL (`nms_*`) vs SPLIT (`operational_incidents`)** | `nms_device_profiles`, `nms_device_metrics`, `nms_interface_metrics`, and `nms_incidents` have no `tenant_id`. In `operational_incidents`, `ProactiveIncidentEngine` (`incident_engine.py:51-147`) inserts `tenant_id = NULL` and queries all rows without tenant filtering, leaking incidents across tenants in `/api/operations/incidents`. |
| **Automations & Playbooks** | **BROKEN TENANT ISOLATION** | `/api/v1/automations` has zero auth and accepts arbitrary `tenant_id` in query/body; `PlaybookRunner.get_playbook()` (`core/playbooks/runner.py:149`) and `execute_playbook()` (`L173`) do not filter by `tenant_id` (cross-tenant IDOR). |
| **Shared Workspace** | **SINGLE GLOBAL FOLDER** | `core/tenant/workspace_service.py` was written to provide per-tenant/per-user workspace directories, but is **never imported anywhere in production**; `core/filesystem/manager.py` uses one global `AIRA_ECOSYSTEM/workspace/` folder. |
| **Audit Logs** | **UNSCOPED / DESTRUCTIBLE** | `GET /api/v1/admin/activity` (`user_management.py:389`) does not filter by `ctx.tenant_id`; `DELETE /api/logs` (`logs.py:58`) lets any user with `audit.read` delete all system logs in `logs.db`. |

---

## 5. Network Management & Engineering Capabilities Review (Section E)

1. **Device Inventory & Connection Management (`InventoryStore` + `ConnectionManager`)**:
   - **Strengths**: `ConnectionManager` (`agents/akane/connection_manager.py`) implements a genuine persistent Paramiko `invoke_shell()` pool (`PersistentShell`), prompt detection, ANSI stripping, per-target locking, 15s read-command caching, and idle reaping.
   - **Critical Weaknesses**:
     - `/api/connections/*` is completely unauthenticated.
     - `tools/ssh/client.py` maintains a second, uncoordinated `_connections` pool that is never closed on shutdown.
     - All SSH connections use `paramiko.AutoAddPolicy()` (vulnerable to MITM).
     - `ConnectionManager.open_connection()` (`L200`) falls back to `os.getenv("SSH_PASSWORD")` for any target host when `password` is omitted.
2. **Topology Discovery, Parsing & Routing Analytics (`core/topology_*` & `core/routing/*`)**:
   - **Strengths**: Deterministic RouterOS v6/v7 CLI parsers (`topology_parsers.py`, `unified_route_parser.py`), multi-source edge correlation (`correlate_canonical_edges`), LPM lookup, recursive next-hop resolution, ECMP path tracing, and immutable snapshot diffing are genuinely implemented and well-tested.
   - **Weaknesses**: `TopologyEngine._emit_topology_event` (`topology_engine.py:4946`) fails with `NameError: name 'get_event_bus' is not defined`; `CanonicalNetworkRegistry._fetch_nms_statuses` (`canonical_network.py:500-516`) always sets `nms_status = "UNKNOWN"`.
3. **NMS Polling, Telemetry & Alerting (`core/nms_engine.py` vs `core/nms/`)**:
   - **Strengths**: Pure-Python ASN.1/BER SNMPv2c client (`core/nms_snmp.py`) and SSH/ICMP fallbacks work against live devices.
   - **Critical Weaknesses**:
     - `core/nms_engine.py` polls devices sequentially in a single thread (`poll_all_enabled`, `L631`), while the multi-threaded `HardenedNmsScheduler` (`core/nms/scheduler.py`) and hysteresis `AlertEngine` (`core/nms/alerts.py`) are unused in production.
     - Table schema collisions on `nms_raw_metrics` (`core/edge_gateway/db.py` vs `core/nms/metrics_store.py`) and `nms_device_metrics` (`core/nms_engine.py` vs `core/network_intelligence/metrics_service.py`) crash metric history queries with `sqlite3.OperationalError`.
4. **Safe Execution & Command Validation (`SafeConfigEngine` & `ActionManagementEngine`)**:
   - `SafeConfigEngine` (`agents/akane/config_engine.py`) has a dangerous rollback generation bug (`L72-74`) where rolling back a masquerade rule without a comment executes `/ip firewall nat remove [find action=masquerade]`, deleting **all** masquerade rules on the router.
   - `ActionManagementEngine.execute_action()` (`core/network_intelligence/action_engine.py:439-450`) and `PlaybookRunner.execute_playbook()` (`core/playbooks/runner.py:217-251`) are 100% simulated/mocked.
