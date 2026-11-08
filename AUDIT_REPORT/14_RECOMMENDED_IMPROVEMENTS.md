# PHASE 14 — RECOMMENDED IMPROVEMENTS & ACTIONABLE REMEDIATION CATALOG (`14_RECOMMENDED_IMPROVEMENTS.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent`  
**Audit Mode**: Specification of Actionable Engineering Recommendations (Zero Direct Code Mutation)

---

## 1. Priority & Area Overview

| Priority Tier | Definition | Recommendation Count | Areas Covered |
|---|---|---:|---|
| **P0 — CRITICAL** | Security vulnerabilities, authentication/RBAC bypasses, data loss/router outage risks, SQLite schema collisions, and Docker/CI build breakers. | **8** (`REC-01` – `REC-08`) | Security, Backend, Database, Network & NMS, DevOps & Deployment |
| **P1 — HIGH** | Incomplete/broken core features, 404 frontend/backend mismatches, cross-user memory/GPS leaks, token quota enforcement, and database centralization. | **8** (`REC-09` – `REC-16`) | AI & Orchestration, Database, Backend, Frontend, Architecture |
| **P2 — MEDIUM** | UI/UX bugs, duplicate component consolidation, URL routing (`react-router-dom`), N+1 & write-on-read performance bottlenecks, and real vs mocked engine completion. | **6** (`REC-17` – `REC-22`) | Frontend, Architecture, Performance, Network & NMS, Testing |
| **P3 — LOW** | Dead/legacy file removal, theme token unification, PWA service worker cache strategy, and documentation/observability polish. | **4** (`REC-23` – `REC-26`) | Cleanup & Consolidation, Frontend, DevOps |
| **TOTAL** | **Complete Engineering Remediation Catalog** | **26** | **All 10 Mandatory Areas Covered** |

---

## 2. P0 — CRITICAL Recommendations (`REC-01` to `REC-08`)

### REC-01: Enforce Mandatory Authentication & RBAC Across All 13 Unauthenticated Routers & Both WebSockets
- **1. Recommendation ID**: `REC-01`
- **2. Title**: Secure All Unauthenticated REST Routers (`connections`, `files`, `automations`, `settings`, `voice`, etc.) and WebSockets (`/ws/chat/{session_id}`, `/ws/nms`)
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Security` / `Backend`
- **5. Related Finding / Bug ID**: `BUG-12`, `FEAT-13`, `FEAT-22`, `FEAT-29`, `FEAT-32`, `FEAT-51`, `FEAT-52`
- **6. Current State**: 13 REST routers (`connections.py`, `files.py`, `automations.py`, `settings.py`, `voice.py`, `artifacts.py`, `attachments.py`, `workspace_links.py`, `selection.py`, `location.py`, `memory.py`, `capabilities.py`, `tools.py`, `providers.py`), `POST /api/reset` (`chat.py:122`), and both WebSocket endpoints (`ws.py:355, 385`) have zero authentication.
- **7. Problem Statement**: Any unauthenticated network client can execute arbitrary RouterOS commands on managed routers (`POST /api/connections/execute`), read/write/delete server workspace files (`/files/*`), wipe any user's chat session (`POST /api/reset`), hijack live chat WebSockets and execute LLM tools as the victim user (`/ws/chat/{session_id}`), or disable tenant approval gates (`PUT /api/settings/approvals/preferences`).
- **8. Proposed Solution**:
  1. Add `Depends(require_permission(...))` to every route in `connections.py` (`devices.connect` / `devices.execute`), `files.py` (`files.read` / `files.write`), `automations.py` (`automations.read` / `automations.write`), `settings.py` (`settings.read` / `settings.update`), `voice.py` (`voice.control`), and ` Depends(get_current_authenticated_user)` with session/resource ownership verification to `chat.py:/api/reset`, `artifacts.py`, `attachments.py`, `workspace_links.py`, `selection.py`, `location.py`, and `memory.py`.
  2. Remove the duplicate root mount `app.include_router(files.router)` at `api/main.py:103` (keep only `prefix="/api"` at `L104`).
  3. In `api/routers/ws.py:355, 385`, require `?token=<bearer_token>` query parameter (or `Sec-WebSocket-Protocol` token), validate via `IdentityManager.validate_session_token(token)`, verify `sess["user_id"] == ctx.user_id` on `/ws/chat/{session_id}`, and pass `tenant_id=ctx.tenant_id` to `ws_manager.connect()`.
- **9. Files to Modify**: `api/main.py`, `api/routers/{connections,files,automations,settings,voice,artifacts,attachments,workspace_links,selection,location,memory,chat,ws}.py`, `api/ws_manager.py`, `api/ws_bridge.py`, `app/frontend/src/hooks/useAiraSocketPool.js`, `app/frontend/src/pages/NmsPage.jsx`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: None.
- **12. Database Impact**: Add `user_id TEXT` and `tenant_id TEXT` columns to `attachments`, `artifacts`, `workspace_links`, and `selections` tables for ownership enforcement.
- **13. API Impact**: Unauthenticated requests to protected REST and WebSocket endpoints will return `401 Unauthorized` / WebSocket close code `1008` (`Policy Violation`).
- **14. Frontend Impact**: `useAiraSocketPool.js:19-22` and `NmsPage.jsx:304` must append `?token=${encodeURIComponent(getAuthToken())}` to WebSocket URLs; remove `/files/*` non-`/api` fallback in `src/api.js:93-128`.
- **15. Security Impact**: Eliminates unauthenticated router RCE, arbitrary workspace file access, and WebSocket session hijacking.
- **16. Risk of Change**: Low-Medium (requires frontend WebSocket URL token update in lockstep with backend `ws.py` validation).
- **17. Verification Plan**: Add FastAPI `TestClient` integration tests verifying `401` on all 13 routers and `1008` WebSocket rejection when unauthenticated or when accessing another user's `session_id`.

---

### REC-02: Eliminate All Privilege Escalation & RBAC Bypass Vectors
- **1. Recommendation ID**: `REC-02`
- **2. Title**: Fix Orchestrator `lingga_admin` Escalation, `require_platform_admin` Bypass, `require_topology_admin` Localhost Bypass, Group `DENY` Bypass, and Missing Write Permissions
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Security` / `Architecture`
- **5. Related Finding / Bug ID**: `BUG-01`, `BUG-04`, `BUG-15`, `BUG-28`, `FEAT-06`, `FEAT-08`
- **6. Current State**:
  - `core/orchestrator.py:232` falls back to `user_id="lingga_admin"` on `[Form Submission...]` turns.
  - `api/routers/admin_platform.py:62` allows any `ctx.is_internal` user (including `READ_ONLY`) to pass `require_platform_admin`.
  - `api/routers/user_management.py:98-184` allows `ADMIN` users to assign `grp_super_admin` or change `lingga_admin`'s password.
  - `core/tenant/auth_deps.py:20-37` accepts `X-Guest-ID: gst_...` without authentication; `decisions.py:83` and `gateways.py:72` have unauthenticated `NOC_ADMIN` fallbacks.
  - `api/routers/topology.py:58-92` (`require_topology_admin`) grants admin access to all `127.0.0.1` requests.
  - `core/tenant/manager.py:1054-1068` unions legacy `ROLE_PERMISSIONS` over RBAC group `DENY` rules.
  - `devices.py`, `models.py`, `logs.py`, `operations.py`, `network_intelligence.py`, and `playbooks.py` allow write/delete/execute actions with read-only permissions (or `bypass_approval=True` in request body).
- **7. Problem Statement**: Any low-privileged user (or guest) can escalate to Superadmin (`lingga_admin`), impersonate any user, modify/delete router credentials, or alter LLM model routing.
- **8. Proposed Solution**:
  1. Add `user_id: Optional[str] = None` and `tenant_id: Optional[str] = None` to `AIRAContext` (`core/context/models.py`), remove `"lingga_admin"` fallback in `core/orchestrator.py:232`, and check `inventory.create` permission before running `add_device`.
  2. In `api/routers/admin_platform.py:62`, require explicit `SUPER_ADMIN` / `PLATFORM_OWNER` role (`any(r in admin_roles for r in ctx.roles)`), removing the standalone `ctx.is_internal` OR condition.
  3. In `api/routers/user_management.py`, forbid non-Superadmin callers from assigning `grp_super_admin`, modifying `SUPER_ADMIN` accounts, or accessing users/sessions outside `ctx.tenant_id`.
  4. Remove `X-Guest-ID` spoofing from `core/tenant/auth_deps.py:20-37` and remove `_get_ctx` `NOC_ADMIN` fallbacks from `decisions.py` and `gateways.py`.
  5. Replace `require_topology_admin` (`topology.py:58-92`) with standard RBAC permission dependencies (`topology.write`, `nms.write`, `intelligence.write`).
  6. In `core/tenant/manager.py:1054-1068` and `models.py:2249`, compute effective permissions strictly via `RbacService.get_effective_permissions(user_id)` so explicit `DENY` rules are always honored.
  7. Enforce granular write permissions (`inventory.credentials.manage`, `models.write`, `audit.delete`, `nms.alerts.write`, `intelligence.actions.resolve`, `intelligence.actions.execute`) on all mutating routes, and remove `bypass_approval` from `ExecutePlaybookRequest` (`api/routers/playbooks.py:33`).
  8. Move `Depends(require_permission("devices.read"))` off the router constructor in `api/routers/gateways.py:25` onto management endpoints only so `/enroll`, `/heartbeat`, and `/telemetry` authenticate via gateway tokens (`BUG-15`).
- **9. Files to Modify**: `core/context/models.py`, `core/context/builder.py`, `core/orchestrator.py`, `core/tenant/{auth_deps,manager,models,rbac_service}.py`, `api/routers/{admin_platform,user_management,topology,nms,network_intelligence,devices,models,logs,operations,playbooks,decisions,gateways,personalization}.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: None.
- **12. Database Impact**: None.
- **13. API Impact**: Enforces proper `403 Forbidden` responses when `READ_ONLY` or lower-tier users attempt administrative or mutating actions; unblocks Edge Gateway `/enroll`, `/heartbeat`, and `/telemetry` endpoints.
- **14. Frontend Impact**: None for legitimate role holders.
- **15. Security Impact**: Closes all 8 vertical and horizontal privilege escalation vectors.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Run RBAC matrix unit tests covering `READ_ONLY`, `MEMBER`, `NOC_ENGINEER`, `ADMIN`, and `SUPER_ADMIN` across all mutating endpoints and verify group `DENY` rules override legacy roles.

---

### REC-03: Lock Down Billing Webhooks & Disable Production Self-Upgrade
- **1. Recommendation ID**: `REC-03`
- **2. Title**: Enforce Mandatory HMAC Webhook Signatures, Remove Hardcoded Secret Fallback, and Restrict `/simulate-mock`
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Security` / `Backend`
- **5. Related Finding / Bug ID**: `BUG-02`, `BUG-03`, `FEAT-10`
- **6. Current State**: `api/routers/billing.py:84-87` only checks `verify_webhook_signature()` `if signature:`, skipping verification when `X-Signature` is omitted (`core/billing/service.py:239` defaults `sig_valid = True`). `service.py:34` has a hardcoded `DEFAULT_WEBHOOK_SECRET`. `POST /api/v1/billing/simulate-mock` (`billing.py:108`) is accessible to any logged-in user and lacks invoice ownership checks.
- **7. Problem Statement**: Anyone can upgrade any account to `ENTERPRISE` for free either by calling `/webhooks/midtrans` without an `X-Signature` header or by calling `/simulate-mock`.
- **8. Proposed Solution**:
  1. In `api/routers/billing.py:84-87` and `core/billing/service.py:239`, require `signature` to be non-empty and `verify_webhook_signature()` to return `True`, raising `401` otherwise.
  2. In `core/billing/service.py:34`, remove `DEFAULT_WEBHOOK_SECRET` and fail closed (`503`/`401`) if `os.getenv("AIRA_BILLING_WEBHOOK_SECRET")` is unset.
  3. Restrict `POST /api/v1/billing/simulate-mock` to `Depends(require_platform_admin)` and `os.getenv("AIRA_ENV", "development") != "production"`, and enforce `invoice["user_id"] == ctx.user_id` on `POST /api/v1/billing/checkout`.
- **9. Files to Modify**: `api/routers/billing.py`, `core/billing/service.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: None.
- **12. Database Impact**: None.
- **13. API Impact**: Unsigned webhooks return `401`; non-admin calls to `/simulate-mock` return `403`.
- **14. Frontend Impact**: None.
- **15. Security Impact**: Prevents fraudulent subscription and quota upgrades.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Test `POST /api/v1/billing/webhooks/midtrans` without `X-Signature` (expect `401`) and `POST /api/v1/billing/simulate-mock` as regular user (expect `403`).

---

### REC-04: Resolve SQLite Schema Collisions & Broken Column References in `topology.db`
- **1. Recommendation ID**: `REC-04`
- **2. Title**: Fix `nms_raw_metrics` & `nms_device_metrics` Schema Collisions, `operational_token_policies` Column Mismatch, `pol_global_guest` CHECK Failure, and `nms_incidents.started_at` Queries
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Database` / `Network & NMS`
- **5. Related Finding / Bug ID**: `BUG-06`, `BUG-07`, `BUG-08`, `BUG-20`
- **6. Current State**:
  - `core/edge_gateway/db.py:85` and `core/nms/metrics_store.py:41` both create `nms_raw_metrics` in `topology.db` with conflicting schemas.
  - `core/nms_engine.py:168` (`polled_at TEXT`) and `core/network_intelligence/metrics_service.py:96` (`timestamp REAL`) conflict on `nms_device_metrics`.
  - `core/tenant/token_quota_service.py:642` inserts `model_cost_multiplier_json, created_at` into `operational_token_policies` (actual column: `model_cost_mult_json`, no `created_at`).
  - `core/tenant/db.py:753` seeds `tier='GUEST'` into `operational_token_policies`, violating `CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM'))`.
  - 4 files in `core/network_intelligence/` query `nms_incidents.started_at` (actual column: `opened_at`), `historical_intelligence.py:204` reads `topology_snapshots.snapshot_data`/`timestamp` (actual: `nodes_json`/`created_at`), `core/nms/alerts.py:373` reads `topology_edges.source, target` (actual: `source_node_id, target_node_id`), and `core/routing/route_history.py:1378` queries `nms_alerts` (actual: `nms_incidents`).
- **7. Problem Statement**: Multiple endpoints (`/api/nms/metrics/query`, `/api/intelligence/metrics/history`, `/api/v1/admin/tokens/plan-policy`, `/api/intelligence/history`) crash with `sqlite3.OperationalError` at runtime!
- **8. Proposed Solution**:
  1. Rename the edge gateway raw telemetry table in `core/edge_gateway/db.py:85` and `ingestion.py:303` to `nms_edge_raw_metrics`, and ensure `init_metrics_tables()` (`core/nms/metrics_store.py`) is called during `nms_raw_metrics` initialization.
  2. Update `NmsHistoricalMetricsService` (`core/network_intelligence/metrics_service.py:96-260`) and `historical_intelligence.py:142-157` to use `polled_at` (with a strict column allowlist for `metric_name`) matching `core/nms_engine.py`.
  3. In `core/tenant/token_quota_service.py:630-660`, replace `model_cost_multiplier_json` with `model_cost_mult_json` and remove `created_at`.
  4. In `core/tenant/db.py:212`, add `'GUEST'` to the `CHECK` constraint or remove the obsolete `pol_global_guest` seed row (`L753`).
  5. Replace `started_at` with `opened_at` in `evidence_service.py:1166`, `correlation_engine.py:80,425`, `historical_intelligence.py:92,97,112`, and `rca_engine.py:119`; fix `nodes_json`/`created_at` in `historical_intelligence.py:204,211`; fix `source_node_id, target_node_id` in `core/nms/alerts.py:373`; and fix `nms_incidents` in `core/routing/route_history.py:1378`.
- **9. Files to Modify**: `core/edge_gateway/{db,ingestion}.py`, `core/nms/{metrics_store,alerts}.py`, `core/network_intelligence/{metrics_service,evidence_service,correlation_engine,historical_intelligence,rca_engine}.py`, `core/routing/route_history.py`, `core/tenant/{db,token_quota_service}.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: None.
- **12. Database Impact**: Resolves all table/column collisions in `topology.db`.
- **13. API Impact**: Restores `200 OK` responses on `/api/nms/metrics/query`, `/api/intelligence/metrics/history`, `/api/v1/admin/tokens/plan-policy`, and `/api/intelligence/history`.
- **14. Frontend Impact**: None.
- **15. Security Impact**: Eliminates raw SQL string interpolation of `metric_name` in `historical_intelligence.py:142`.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Run a unified schema initialization and query test against a single `topology.db` instance exercising all modified services in sequence.

---

### REC-05: Fix Destructive RouterOS NAT Rollback, Unmasked Config Snapshots & SSH Security
- **1. Recommendation ID**: `REC-05`
- **2. Title**: Harden `SafeConfigEngine` Rollback & Snapshot Masking, Consolidate SSH Pools, and Validate Network Targets
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Network & NMS` / `Security`
- **5. Related Finding / Bug ID**: `BUG-05`, `BUG-29`, `FEAT-32`, `FEAT-33`
- **6. Current State**:
  - `agents/akane/config_engine.py:72-74` generates `/ip firewall nat remove [find action=masquerade]` on rollback when no comment was provided.
  - `agents/akane/config_engine.py:147` writes unmasked `data` instead of `masked_data` to `{operation_id}.json`.
  - `agents/akane/connection_manager.py:200, 387` leaks `os.getenv("SSH_PASSWORD")` to ad-hoc hosts.
  - `agents/akane/network_tools.py:16-17` exposes `ping`, `nslookup`, `traceroute` without `validate_network_target()`.
  - `tools/ssh/client.py` duplicates `ConnectionManager` and is never closed on shutdown.
- **7. Problem Statement**: Rolling back a NAT rule can wipe all masquerade rules on a production router; config snapshots leak secrets on disk; ad-hoc SSH connections leak `SSH_PASSWORD`; and targets starting with `-` inject CLI flags into `ping`/`traceroute`.
- **8. Proposed Solution**:
  1. In `agents/akane/config_engine.py:51-101`, automatically append a unique `comment="aira-op-<operation_id>"` when planning `add` commands that lack a comment, and generate rollback exclusively via `[find comment="aira-op-<operation_id>"]`.
  2. In `agents/akane/config_engine.py:147`, write `masked_data` to `{operation_id}.json` and encrypt `.raw.json` (or store in SQLite).
  3. In `agents/akane/connection_manager.py:200, 387`, remove the `os.getenv("SSH_PASSWORD")` fallback for ad-hoc hosts not in `InventoryStore`.
  4. In `tools/network/diagnostics.py:24, 66, 130`, call `validate_network_target(target)` (`rejecting `-` and `/`) and pass `"--"` before `target` in `subprocess.run`.
  5. Retire `tools/ssh/client.py`'s separate `_connections` pool (or call `close_all_connections()` in `api/main.py:301`) and remove the 12 unused wrapper functions in `tools/mikrotik/routeros.py:45-157`.
- **9. Files to Modify**: `agents/akane/{config_engine,connection_manager,network_tools}.py`, `tools/network/diagnostics.py`, `tools/mikrotik/routeros.py`, `tools/ssh/client.py`, `api/main.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: Unused functions in `tools/mikrotik/routeros.py:45-157`.
- **12. Database Impact**: None.
- **13. API Impact**: None.
- **14. Frontend Impact**: None.
- **15. Security Impact**: Prevents router WAN outage on rollback, stops plaintext secret snapshots, prevents `SSH_PASSWORD` exfiltration, and blocks CLI flag injection.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Unit-test `generate_rollback_for_command("/ip firewall nat add chain=srcnat action=masquerade out-interface=ether1")` and verify `{operation_id}.json` contains `***MASKED***`.

---

### REC-06: Fix Runtime Crashes in Vision LLM, Network Intelligence, Operations & Edge Gateway
- **1. Recommendation ID**: `REC-06`
- **2. Title**: Fix `VisionResult` `TypeError`, `NetworkInvestigator` Crashes, `ChangeImpactEngine` / `RiskAssessmentEngine` Graph Bugs, and Edge Gateway UTC / Linux Ping Bugs
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Backend` / `Network & NMS` / `AI & Orchestration`
- **5. Related Finding / Bug ID**: `BUG-09`, `BUG-10`, `BUG-13`, `BUG-16`, `BUG-17`, `BUG-18`, `BUG-21`, `BUG-22`, `BUG-23`, `BUG-24`, `BUG-31`, `BUG-32`, `BUG-34`, `BUG-35`, `BUG-36`
- **6. Current State**: Multiple core backend methods crash with `TypeError`, `AttributeError`, or `NameError`, or return permanent `"OFFLINE"` / `"UNKNOWN"` states due to simple coding bugs.
- **7. Problem Statement**:
  - `core/file_processing/vision_llm.py:93` crashes on 100% of successful Vision LLM calls (`unexpected keyword argument 'analysis'`).
  - `core/network_intelligence/investigator.py:732, 776` crashes with `AttributeError` (`d.name` on dict) and `TypeError` (`analyzer_cls()` on instance).
  - `api/routers/network_intelligence.py:1556 vs 1586` shadows `GET /api/intelligence/actions/policy` with `404`.
  - `core/edge_gateway/ingestion.py:199` uses `time.mktime()` on UTC timestamps, making all gateways permanently `OFFLINE`.
  - `core/edge_gateway/collector.py:105` uses Windows `ping -n` flags on Linux.
- **8. Proposed Solution**:
  1. `core/file_processing/vision_llm.py:93`: Remove `analysis={"description": text}` from `VisionResult(...)`.
  2. `core/network_intelligence/investigator.py:732, 776`: Change `d.name`/`d.id` to `d.get("name")`/`d.get("id")` and iterate `for analyzer in ALL_PROTOCOL_ANALYZERS:` without calling `analyzer()`.
  3. `api/routers/network_intelligence.py`: Move `@router.get("/actions/policy")` (`L1586`) above `@router.get("/actions/{action_id}")` (`L1556`); use a module-level singleton `_investigator = NetworkInvestigator()` so `/investigate/{id}/cancel` works (`L1119, 1172`); and read `health.get("overall_status")` / `health.get("overall_score")` at `L1038-1039`.
  4. `core/network_intelligence/evidence_service.py:1241`: Call `self.route_collector.ingest_bundle_routes(mbundle)`.
  5. `core/network_intelligence/auto_orchestrator.py:384`: Call `unified_svc.assemble_evidence_bundle(target_devices=targets, allow_live_collection=False)`.
  6. `api/routers/operations.py:181` & `core/operations/change_impact_engine.py:110, 135, 178`: Build graph via `graph = NetworkKnowledgeGraph(); graph.build_from_bundle(bundle)`, use `iface:` prefix, and iterate `alt["paths"][0].get("devices", [])`.
  7. `api/routers/decisions.py:257` & `core/operations/risk_engine.py:239, 257`: Pass a populated `NetworkKnowledgeGraph` and check BFS reachability to core/gateway nodes using `"device:" + dev_id`.
  8. `core/edge_gateway/ingestion.py:199`: Replace `time.mktime(...)` with `calendar.timegm(...)` and persist all 5 `TelemetryType` values (`L295-312`).
  9. `core/edge_gateway/collector.py:105`: Use platform-aware `ping` flags (`-c` and `-W` on Linux).
  10. `core/canonical_network.py:500-516`: Call `engine.list_device_profiles()` so `nms_status` is populated; `core/topology_engine.py:4946`: import `event_bus` from `core.events.bus`.
- **9. Files to Modify**: `core/file_processing/vision_llm.py`, `core/network_intelligence/{investigator,evidence_service,auto_orchestrator}.py`, `api/routers/{network_intelligence,operations,decisions}.py`, `core/operations/{change_impact_engine,risk_engine,decision_engine,scheduler}.py`, `core/edge_gateway/{ingestion,collector}.py`, `core/canonical_network.py`, `core/topology_engine.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: None.
- **12. Database Impact**: None.
- **13. API Impact**: Fixes 500/404 crashes across Vision LLM, `/api/intelligence/investigate`, `/api/intelligence/actions/policy`, `/api/operations/change-impact/simulate`, `/api/v1/decisions/risk/simulate`, and `/api/v1/gateways/{id}/health`.
- **14. Frontend Impact**: Action Center policy loads cleanly; Investigator tab completes without crashing; Gateway health displays `ONLINE`.
- **15. Security Impact**: None.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Add unit and endpoint tests for each fixed method.

---

### REC-07: Fix `NmsPage.jsx` `ReferenceError` Crash & All 9 Broken Frontend-to-Backend API Calls
- **1. Recommendation ID**: `REC-07`
- **2. Title**: Fix `refreshAll()` Crash in `NmsPage.jsx` and Align All 9 Frontend 404 Endpoint Calls with Backend Routers
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `Frontend` / `Backend`
- **5. Related Finding / Bug ID**: `BUG-11`, `BUG-19`, `FEAT-03`, `FEAT-05`, `FEAT-10`, `FEAT-20`, `FEAT-28`, `FEAT-38`
- **6. Current State**:
  - `src/pages/NmsPage.jsx:972` calls undefined `refreshAll()` on SNMP wizard completion (`Uncaught ReferenceError`).
  - 9 frontend API calls hit non-existent backend routes (`POST /api/v1/auth/change-password`, `POST /api/v1/auth/sessions/revoke-others`, `GET /api/v1/billing/entitlements`, `PUT /api/v1/personalization/persona/instructions`, `POST /api/voice/synthesize`, `POST /api/voice/transcribe`, `GET /api/voice/status`, `POST /api/voice/tts`, `POST /api/v1/auth/register`).
- **7. Problem Statement**: Users cannot change their password from the Profile modal, cannot revoke other sessions in Settings, hit 404s on every Settings page load and neural voice synthesis request, and crash `NmsPage` when finishing the SNMP wizard.
- **8. Proposed Solution**:
  1. In `src/pages/NmsPage.jsx:972`, replace `refreshAll()` with `fetchAllData()`.
  2. In `api/routers/auth.py`, add `POST /api/v1/auth/change-password` (verifying `current_password` and `new_password` `min_length=8`) and `POST /api/v1/auth/sessions/revoke-others` (revoking all sessions of `ctx.user_id` except `ctx.session_id`). Update `AccountProfileModal.jsx:60` to validate `newPassword.length < 8`.
  3. In `src/pages/SettingsPage.jsx:160`, replace `fetch("/api/v1/billing/entitlements")` with `api.settings.entitlementsSummary()` (`GET /api/settings/entitlements/summary`).
  4. In `src/api.js:449` (`updateInstructions`), call `PUT /api/v1/personalization/preferences` with `{ custom_instructions }` instead of `PUT /api/v1/personalization/persona/instructions`.
  5. In `api/routers/voice.py`, add `POST /api/voice/synthesize` (calling `agents.yuki.tts.synthesize_bytes`) and `POST /api/voice/transcribe` (calling `agents.yuki.stt.transcribe`), and update `src/api.js:368` to call `/api/voice/service/status`.
  6. In `src/pages/OperationsPage.jsx:38`, replace hardcoded `"http://127.0.0.1:8000/api/operations"` with relative `"/api/operations"`.
- **9. Files to Modify**: `app/frontend/src/pages/{NmsPage,SettingsPage,OperationsPage}.jsx`, `app/frontend/src/components/AccountProfileModal.jsx`, `app/frontend/src/api.js`, `api/routers/{auth,voice}.py`, `core/tenant/manager.py`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: Remove dead `register()` method from `src/context/AuthContext.jsx:181`.
- **12. Database Impact**: None.
- **13. API Impact**: Adds `POST /api/v1/auth/change-password`, `POST /api/v1/auth/sessions/revoke-others`, `POST /api/voice/synthesize`, and `POST /api/voice/transcribe`.
- **14. Frontend Impact**: Eliminates all 9 `404 Not Found` errors and the `NmsPage` SNMP wizard crash.
- **15. Security Impact**: Requires current password verification on self-service password change.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Verify all 9 user actions in the UI and via `TestClient` return `200 OK`.

---

### REC-08: Fix Docker Build, `.dockerignore` DB Leak & GitHub Actions CI Pipeline
- **1. Recommendation ID**: `REC-08`
- **2. Title**: Unify Python Requirements in `Dockerfile` & `ci.yml`, Fix `npm test` CI Flag, and Exclude `*.db*` from Docker Image & Git
- **3. Priority**: `P0 — CRITICAL`
- **4. Category / Area**: `DevOps & Deployment`
- **5. Related Finding / Bug ID**: Section 2 of `11_TESTING_AND_VALIDATION_AUDIT.md` & `13_DEPLOYMENT_AND_CONFIGURATION_AUDIT.md`
- **6. Current State**:
  - `Dockerfile:29-30` and `.github/workflows/ci.yml:26` only install `requirements.txt` and omit `requirements-web.txt` (`fastapi`, `uvicorn`).
  - `.github/workflows/ci.yml:64` runs `npm test -- --run`, which fails with exit code `9` on `"test": "node --test"`.
  - `.dockerignore` does not exclude `AIRA_ECOSYSTEM/database/*.db*` or `workspace/`, baking local DBs into the image.
  - `database/chat_sessions.db.old` and `long_term_memory.db.old` are tracked in Git.
- **7. Problem Statement**: Docker containers cannot start (`No module named 'uvicorn'`), CI backend and frontend jobs both fail, and local databases leak into Docker images and Git.
- **8. Proposed Solution**:
  1. Copy and install both `requirements.txt` and `requirements-web.txt` in `Dockerfile:29-30` and `.github/workflows/ci.yml:26` (and add `libportaudio2` to `apt-get install` in `Dockerfile:16`).
  2. Add a multi-stage Node 20 frontend build stage to `Dockerfile` (building `AIRA_ECOSYSTEM/app/frontend/dist`) and mount `dist` in `api/main.py` when present.
  3. Change `.github/workflows/ci.yml:64` from `npm test -- --run` to `npm test`.
  4. Add `AIRA_ECOSYSTEM/database/*.db*`, `AIRA_ECOSYSTEM/workspace/*`, and `AIRA_ECOSYSTEM/uploads/*` to `.dockerignore` and `.gitignore`, and untrack `*.db.old`.
  5. Document all 14 missing env vars in `.env.example`.
- **9. Files to Modify**: `Dockerfile`, `.dockerignore`, `.gitignore`, `.env.example`, `.github/workflows/ci.yml`, `requirements.txt`.
- **10. Files to Create**: None.
- **11. Files to Deprecate / Remove**: Untrack `AIRA_ECOSYSTEM/database/chat_sessions.db.old` and `long_term_memory.db.old`.
- **12. Database Impact**: Prevents local operational DBs from being baked into Docker images.
- **13. API Impact**: None.
- **14. Frontend Impact**: `npm test` runs cleanly in CI after `npm ci`.
- **15. Security Impact**: Prevents credential/session leakage in Docker images and Git history.
- **16. Risk of Change**: Low.
- **17. Verification Plan**: Run `npm test` in `app/frontend` and verify `docker build` and CI steps succeed.

---

## 3. P1 — HIGH Priority Recommendations (`REC-09` to `REC-16`)

| Rec ID | Title & Area | Related Bug / Finding | Current State & Problem | Proposed Solution & Files to Modify/Remove | Impact (DB / API / FE / Security) & Verification |
|---|---|---|---|---|---|
| **REC-09** | **Isolate Private User Memory, Persona & GPS Location**<br>*(Area: AI & Orchestration / Privacy)* | `BUG-25`, `BUG-26`, `BUG-38`, `FEAT-19`, `FEAT-20`, `FEAT-27` | `agents/rei/auto_extract.py` writes chat facts to unscoped `long_term_memory.db`, which `core/brain.py:233` injects into **every user's** prompt. `core/location/service.py:202` leaks `_last_session_id` GPS to other sessions. `PersonaPage.jsx` mutates global `persona.db` (`id=1`). `SettingsPage` vs `MemoryPage` have conflicting `1-100` vs `0.0-1.0` importance scales. | 1. Route `auto_extract.py` and `core/brain.py` exclusively through `UserMemoryService` (`topology.db:user_memories` scoped by `user_id`).<br>2. Route `api/routers/persona.py` and `PersonaEngine` through `UserPersonaService` (`topology.db:user_personas`).<br>3. Remove `self._last_session_id` fallback in `core/location/service.py:202`.<br>4. Normalize `importance` to `0.0–1.0` in `personalization.py` (`update_memory` at `L205` must also divide `>1.0` by `100.0`) and `SettingsPage.jsx`.<br>*Modify*: `agents/rei/auto_extract.py`, `core/brain.py`, `core/location/service.py`, `api/routers/{personalization,persona}.py`, `src/pages/{SettingsPage,MemoryPage}.jsx`.<br>*Deprecate*: `core/memory.py`, `core/persona.py`, `database/{long_term_memory,persona,semantic_memory,interaction_memory}.db`. | **DB**: Consolidates 4 memory DBs & 2 persona DBs into `topology.db` (`user_memories`, `user_personas`).<br>**Security**: Eliminates cross-user fact, persona, and GPS leakage.<br>**Verification**: Test that User A's extracted facts and GPS coordinates never appear in User B's prompt or location context. |
| **REC-10** | **Wire Real-Time Token Quota Enforcement & Unify Plan Catalogs**<br>*(Area: Backend / Billing & Quotas)* | `BUG-27`, `FEAT-10`, `FEAT-11` | `TokenQuotaService` is instantiated at `api/routers/chat.py:28` and never called in `/api/chat` or `/ws/chat/{session_id}`. `DEFAULT_PLAN_LIMITS` (`entitlements.py`: FREE=100k, PRO=2M) contradicts `PLAN_CATALOG` (`user_subscription.py`: FREE=10k, PRO=100k). | 1. Call `_quota_service.check_quota(ctx.user_id, ctx.tenant_id)` before `orchestrator.handle_turn()` in `api/routers/chat.py` and `api/routers/ws.py`, returning `429 Quota Exceeded` when depleted.<br>2. Deduct actual prompt+completion tokens via `_quota_service.record_usage()` after each LLM turn.<br>3. Unify `DEFAULT_PLAN_LIMITS` and `PLAN_CATALOG` into a single DB-backed `subscription_plans` catalog.<br>*Modify*: `api/routers/{chat,ws}.py`, `core/tenant/{entitlements,user_subscription,token_quota_service}.py`. | **DB**: Populates `operational_token_usage_ledger` and updates `operational_token_balances` on every turn.<br>**API**: `ChatResponse.quota` returns live remaining balance.<br>**Verification**: Verify chat turn deducts tokens and blocks when balance reaches `0`. |
| **REC-11** | **Unify Network Device Inventory, Incidents & Models (Eliminate Split-Brain)**<br>*(Area: Database / Architecture)* | `BUG-30`, Section 4 of `06_DATABASE_AND_DATA_CENTRALIZATION_AUDIT.md` | Devices are split between `inventory.db:devices` (global) and `topology.db:operational_devices` (tenant-scoped). Incidents are split across `nms_incidents`, `network_intelligence.db:incidents`, and `operational_incidents` (`ProactiveIncidentEngine` vs `MultiTenantIncidentEngine`). Models are split between `model_router.db` and `model_registry.db`. | 1. Consolidate `InventoryStore` (`core/inventory_store.py`) and `InventoryManager` (`core/tenant/inventory_manager.py`) onto `topology.db` (`operational_devices` + encrypted `operational_credentials`).<br>2. Decommission tenant-unaware `ProactiveIncidentEngine` (`core/operations/incident_engine.py`) in favor of `MultiTenantIncidentEngine` (`multi_tenant_incident_engine.py`), and sync NMS/Intelligence alerts into it.<br>3. Remove `core/model_registry.py`'s separate `model_registry.db` and replace the 13 fictional models in `_BUILTIN_SEED` (`core/model_store.py:42-198`) with real model IDs.<br>*Modify*: `core/inventory_store.py`, `core/tenant/inventory_manager.py`, `core/operations/incident_engine.py`, `api/routers/operations.py`, `core/model_store.py`, `core/model_registry.py`. | **DB**: Retires `inventory.db`, `network_intelligence.db`, and `model_registry.db`.<br>**Security**: Enforces `tenant_id` scoping on devices and incidents.<br>**Verification**: Verify adding a device in `/api/devices` is immediately visible in `/api/v1/portal/devices` and `/api/v1/gateways`. |
| **REC-12** | **Encrypt All Plaintext Secrets at Rest (SSH Passwords, API Keys, MFA Secrets)**<br>*(Area: Security / Database)* | Section 2.11 of `10_SECURITY_AUDIT.md` | `inventory.db:credentials.secret`, `model_router.db:models.api_key`, and `topology.db:operational_users.mfa_secret` are stored in plaintext. | Introduce a central `SecretVault` helper in `core/security/encryption.py` using AES-256-GCM / Fernet keyed by `AIRA_MASTER_KEY` (with automatic migration of existing plaintext values on startup).<br>*Create*: `core/security/encryption.py`.<br>*Modify*: `core/inventory_store.py`, `core/model_store.py`, `core/tenant/manager.py`. | **DB**: Encrypts `secret`, `api_key`, and `mfa_secret` columns.<br>**Security**: Protects router passwords, LLM API keys, and TOTP seeds if SQLite files are exfiltrated.<br>**Verification**: Inspect SQLite rows directly to confirm ciphertext prefix (`enc:v1:...`). |
| **REC-13** | **Eliminate Write-on-Read SQLite Contention & N+1 Loops**<br>*(Area: Performance / Database)* | Section 3 of `12_PERFORMANCE_AUDIT.md` | `IdentityManager.validate_session_token()` (`core/tenant/manager.py:1032`) executes an `UPDATE operational_user_sessions` write transaction on every `GET` request. `DynamicHealthScoringEngine.score_tenant()` (`health_scoring_engine.py:299`) executes 60+ `INSERT` transactions during a single `GET` dashboard load. | 1. Remove `UPDATE operational_user_sessions SET last_active_at = ?` from `validate_session_token()` (or throttle to at most once every 5 minutes in memory, since `POST /api/v1/auth/heartbeat` already updates it).<br>2. Refactor `DynamicHealthScoringEngine` to read cached scores on `GET` requests and batch `INSERT`s in a single transaction.<br>3. Replace N+1 `get_*` loops in `ServiceIntelligenceEngine.list_services()`, `ProactiveIncidentEngine.list_incidents()`, and `OperationalSchedulerEngine.list_jobs()` with single `SELECT` queries (`JOIN` / `WHERE id IN (...)`).<br>4. Run `AttachmentService.ingest_upload()` via `await asyncio.to_thread(...)` in `api/routers/attachments.py:73, 116`.<br>*Modify*: `core/tenant/manager.py`, `core/operations/{health_scoring_engine,service_intelligence,incident_engine,scheduler}.py`, `api/routers/attachments.py`. | **Performance**: Eliminates SQLite write-lock serialization on concurrent `GET` requests and reduces dashboard latency by >10x.<br>**Verification**: Benchmark 20 concurrent `GET /api/v1/portal/dashboard/overview` requests before and after. |
| **REC-14** | **Connect Orphaned Frontend Pages & Fix Navigation/RBAC Guards**<br>*(Area: Frontend / Architecture)* | `BUG-38`, `BUG-39`, `BUG-40`, `BUG-42`, `BUG-43`, `FEAT-12`, `FEAT-48`, `FEAT-49`, `FEAT-50` | `OperationsPage.jsx`, `GatewaysPage.jsx`, `DecisionsPage.jsx`, and `CustomerPortalPage.jsx` are in `App.jsx` `PAGES` but have zero UI navigation links. `MobileNav.jsx:50` ignores `hasPermission()`. `AuthContext.jsx:289` one-way alias hides `NetworkIntelligencePage` from `"nms.view"` users. `SettingsPage.jsx` hides `"subscription"` and `"token_usage"` tabs. | 1. Add navigation entries (or sub-tabs under `InfrastructurePage` / `NetworkIntelligencePage` / `Sidebar`) for `operations`, `gateways`, `decisions`, and `portal`, and add their keys to `PAGE_PERMISSIONS` in `src/App.jsx:192`.<br>2. Make `PERMISSION_ALIASES` bidirectional in `src/context/AuthContext.jsx:285-322` and filter `PRIMARY_ITEMS` by `hasPermission()` in `src/components/MobileNav.jsx:50`.<br>3. Add `"subscription"` and `"token_usage"` to `RAW_TABS` in `src/pages/SettingsPage.jsx:468-475`.<br>4. Pass dynamic `isOnChatPage={active === "workspace" || active === "chat"}` to `<ChatRuntimeProvider>` in `src/App.jsx:332`.<br>5. Fix `TopologyPage.jsx:833` (`onMenuClick`), `#link-gradient-physical` (`L1341`), `TopologyEdgeInspector.jsx:153,221`, `InfrastructurePage.jsx` double header bar, and `DecisionsPage.jsx:30` (`rollback_readiness`).<br>*Modify*: `src/App.jsx`, `src/components/{navConfig,Sidebar,MobileNav}.jsx`, `src/context/AuthContext.jsx`, `src/pages/{SettingsPage,TopologyPage,InfrastructurePage,DecisionsPage}.jsx`, `src/components/topology/{topologyConstants,TopologyEdgeInspector}.jsx`. | **Frontend**: Makes all 4 orphaned operational pages and 2 hidden settings tabs accessible; fixes mobile RBAC, unread badges, and topology visual bugs.<br>**Verification**: Navigate to all 18 pages and sub-tabs across desktop and mobile viewports. |
| **REC-15** | **Wire `HardenedNmsScheduler` & `AlertEngine` Into Production NMS**<br>*(Area: Network & NMS / Architecture)* | `FEAT-38`, `FEAT-39`, Section 3.1 of `08_DUPLICATION_AND_UNUSED_CODE_AUDIT.md` | Production `core/nms_engine.py` polls devices sequentially in a single thread (`poll_all_enabled`, `L631`) with basic threshold alerts, while the concurrent 16-worker `HardenedNmsScheduler` (`core/nms/scheduler.py`) and hysteresis/flapping `AlertEngine` (`core/nms/alerts.py`) sit unused in `core/nms/`. | Integrate `HardenedNmsScheduler` (`ThreadPoolExecutor(max_workers=16)` + per-device circuit breaker) and `AlertEngine` (hysteresis + upstream root-cause suppression) into `NmsEngine.poll_all_enabled()` and `_evaluate_incidents()`.<br>*Modify*: `core/nms_engine.py`, `core/nms/{scheduler,alerts,models}.py` (remove `mcp_servers` import at `core/nms/models.py:35`!). | **Performance & Reliability**: Prevents unreachable devices from blocking the entire NMS polling loop and eliminates flapping alert storms.<br>**Verification**: Test polling 20 devices with 5 unreachable targets in `< 10s`. |
| **REC-16** | **Break Circular Dependencies & Upward Layer Inversions (`core` -> `api`/`agents`/`mcp_servers`)**<br>*(Area: Architecture)* | Section 3.1 of `02_CODEBASE_ARCHITECTURE.md` | `core/tenant/auth_deps.py:46` imports `api.routers.auth`; `core/nms/models.py:35` imports `mcp_servers.network.security` (which imports `mcp` server); `core/file_processing/vision_llm.py:55` imports `agents.rei.provider_client`. | 1. Move `get_current_user_context` from `api/routers/auth.py:48` into `core/tenant/auth_deps.py` so `api` imports `core`, never the reverse.<br>2. Move `mask_sensitive_data` and `validate_network_target` from `mcp_servers/network/security.py` into `core/security/network_safety.py`, and make `mcp_servers/network/__init__.py` lazy.<br>3. Move LLM provider client interface (`provider_client.py`) or inject it into `core/`.<br>*Create*: `core/security/network_safety.py`.<br>*Modify*: `core/tenant/auth_deps.py`, `api/routers/auth.py`, `core/nms/models.py`, `mcp_servers/network/{__init__,security}.py`. | **Architecture**: Restores clean unidirectional layering (`api` -> `core` <- `agents` / `mcp_servers`) and allows importing `core.nms` without `mcp` or `paramiko` installed.<br>**Verification**: Run AST layer-inversion check script (`0` upward imports from `core` to `api`/`mcp_servers`). |

---

## 4. P2 — MEDIUM Priority Recommendations (`REC-17` to `REC-22`)

| Rec ID | Title & Area | Related Bug / Finding | Current State & Problem | Proposed Solution & Files to Modify | Impact & Verification |
|---|---|---|---|---|---|
| **REC-17** | **Adopt URL Routing (`react-router-dom`) in Frontend SPA**<br>*(Area: Frontend / UX)* | Section 1.1 of `05_FRONTEND_AUDIT.md` | Navigation relies on React state `active` in `src/App.jsx:209` and `window.dispatchEvent(new CustomEvent("aira:navigate"))` + `sessionStorage` keys. Browser Back/Forward and `F5` reload lose page state. | Install `react-router-dom` (or use a lightweight URL `history.pushState` / `popstate` sync hook in `App.jsx`) mapping `/chat`, `/infrastructure/:tab`, `/intelligence/:tab`, `/automations`, `/files`, `/models`, `/logs`, `/admin/:tab`, `/settings/:tab`, `/operations`, `/gateways`, `/decisions`, `/portal` while keeping the `aira:navigate` listener as a bridge.<br>*Modify*: `app/frontend/package.json`, `src/App.jsx`, `src/pages/{InfrastructurePage,NetworkIntelligencePage,AdminPlatformPage,SettingsPage}.jsx`. | **Frontend UX**: Browser Back/Forward, `F5` refresh persistence, and shareable deep links work across all pages and tabs.<br>**Verification**: Reload browser on `/infrastructure/topology` and verify it stays on Topology. |
| **REC-18** | **Wire `streamBatcher` in `ChatRuntimeContext` & Deduplicate `/api/connections` Polling**<br>*(Area: Frontend / Performance)* | `BUG-44`, Section 2 of `12_PERFORMANCE_AUDIT.md` | `ChatRuntimeContext.jsx:203` initializes `createStreamBatcher` but never calls `batcherRef.current.push()`. `ConnectionIndicator.jsx:33` and `useCockpitData.js:90` both poll `/api/connections` every 5s. | 1. Route `stream_chunk` events through `batcherRef.current.push(event)` in `ChatRuntimeContext.jsx:253`.<br>2. Lift `/api/connections` state into a shared context or `useCockpitData` and pause `NmsPage.jsx:293` HTTP polling while `/ws/nms` is open.<br>*Modify*: `src/context/ChatRuntimeContext.jsx`, `src/components/connection/ConnectionIndicator.jsx`, `src/pages/NmsPage.jsx`. | **Performance**: Caps streaming DOM updates at 60fps (`requestAnimationFrame`) and cuts background HTTP polling in half.<br>**Verification**: Verify `streamBatcher.test.js` and network tab polling intervals. |
| **REC-19** | **Replace Simulated Action/Playbook/Onboarding Executors & Synthetic Fallbacks with Real Implementations**<br>*(Area: Network & NMS / Backend)* | Section 2.2 of Part 4 Audit (`FEAT-41`–`FEAT-51`) | `ActionManagementEngine.execute_action()` (`action_engine.py:439`), `PlaybookRunner.execute_playbook()` (`playbooks/runner.py:217`), `DeviceOnboardingEngine._discover_device_facts()` (`onboarding.py:178`), and `core/scheduler.py` / `core/operations/scheduler.py` are simulated/mocked. `api/routers/network_intelligence.py:247` defaults to `_build_default_bundle()` synthetic 3-router mock. | 1. Wire `ActionManagementEngine.execute_action()` to `SafeConfigEngine` / `UnifiedCommandExecutor`.<br>2. Wire `DeviceOnboardingEngine._discover_device_facts()` to SSH/SNMP discovery.<br>3. Change `strict_live` default to `True` in `api/routers/network_intelligence.py:247` so production views never silently fabricate `"Core-Router-1"` / `"ISP-Edge"` incidents.<br>4. Dynamically resolve gateway nodes (`role IN ('edge', 'gateway')`) instead of hardcoding `"ISP-Edge"` in `failure_simulator.py:74`, `impact_analyzer.py:108`, and `change_impact_engine.py:174`.<br>*Modify*: `core/network_intelligence/{action_engine,onboarding,failure_simulator,impact_analyzer}.py`, `core/operations/change_impact_engine.py`, `api/routers/network_intelligence.py`. | **Operational Integrity**: Ensures operators see genuine live device state and execute real audited actions.<br>**Verification**: Test action execution and onboarding against mock/live SSH fixture devices. |
| **REC-20** | **Consolidate Generational Triplication in `core/network_intelligence/`**<br>*(Area: Architecture / Cleanup)* | Section 3.2 of Part 4 Audit | `core/network_intelligence/` contains 3 generations of models (`models.py`, `network_models.py`, `intelligence_models.py`), 2 correlators, 2 evidence collectors, 2 security auditors, and 2 NL orchestrators (`auto_orchestrator.py` vs `investigator.py`). | Standardize on Generation 3 (`intelligence_models.py`, `UnifiedEvidenceService`, `MultiDeviceCorrelationEngine`, `NetworkInvestigator`, `SecurityBaselineEngine`) with compatibility aliases in `__init__.py` for legacy callers.<br>*Modify*: `core/network_intelligence/__init__.py`, `api/routers/network_intelligence.py`. | **Architecture**: Reduces maintenance surface in `core/network_intelligence/` by ~35%.<br>**Verification**: Run all `test_network_intelligence*.py` and `test_phase_5_network_intelligence.py` suites. |
| **REC-21** | **Fix `X-Forwarded-For` Rate-Limiter Bypass & Wire SSRF Protection**<br>*(Area: Security / Backend)* | Section 2.11 of `10_SECURITY_AUDIT.md` | `api/routers/auth.py:76-78` trusts `X-Forwarded-For` from any client. `core/security/ssrf_validator.py` is unused in production and fails to block IPv4-mapped IPv6 loopback/link-local addresses (`::ffff:127.0.0.1`, `::ffff:169.254.169.254`) when `allow_private_devices=True`. | 1. Only trust `X-Forwarded-For` in `auth.py:76` when `request.client.host` is in `TRUSTED_PROXY_IPS` (`127.0.0.1`, `::1`).<br>2. In `core/security/ssrf_validator.py:55`, unwrap `ip.ipv4_mapped` (`if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped: ip = ip.ipv4_mapped`) **before** checking `is_loopback`/`is_link_local`/`is_private`, and call `validate_outbound_url()` in `tools/web/search.py` and `agents/rei/provider_client.py`.<br>*Modify*: `api/routers/auth.py`, `core/security/ssrf_validator.py`, `tools/web/search.py`, `agents/rei/provider_client.py`. | **Security**: Prevents login brute-force via header spoofing and blocks IPv4-mapped IPv6 SSRF bypasses.<br>**Verification**: Test `validate_outbound_url("http://[::ffff:169.254.169.254]/", allow_private_devices=True)` -> must return `False`. |
| **REC-22** | **Expand End-to-End FastAPI `TestClient` & Frontend Component Test Coverage**<br>*(Area: Testing)* | Section 1.2 of `11_TESTING_AND_VALIDATION_AUDIT.md` | Phase tests bypass FastAPI routers by instantiating services directly; frontend tests only cover pure utility JS files. | Add FastAPI `TestClient(app)` integration tests covering auth/RBAC enforcement on all 34 routers, and add React component smoke tests for all 18 pages.<br>*Create*: `AIRA_ECOSYSTEM/tests/test_router_auth_matrix.py`. | **Quality**: Catches router-level RBAC bugs, route shadowing, and schema collisions automatically in CI.<br>**Verification**: Run `pytest` and `npm test` in CI. |

---

## 5. P3 — LOW Priority Recommendations (`REC-23` to `REC-26`)

| Rec ID | Title & Area | Related Bug / Finding | Current State & Problem | Proposed Solution & Files to Modify/Remove | Impact & Verification |
|---|---|---|---|---|---|
| **REC-23** | **Remove All 42 Confirmed Dead/Unused Source Files & Legacy Backups**<br>*(Area: Cleanup & Consolidation)* | Section 2 & 4 of `08_DUPLICATION_AND_UNUSED_CODE_AUDIT.md` | 22 backend/scratch `.py` files, 20 frontend `src/` files, `_legacy_backup_20260910_143345/` (27 files), and 2 `.db.old` files are unused/obsolete. | Archive or delete `_legacy_backup_20260910_143345/`, `scratch/*.py`, `core/persona.py`, `core/attachment/main.py`, `agents/yuki/tts_engine.py`, `agents/rei/settings_tools.py`, `core/bootstrap_superadmin.py`, `core/tenant/{context,entitlement_service}.py`, and the 20 unimported files in `app/frontend/src/` (`src/service.js`, `src/capabilities/CapabilityHeroRow (1).jsx`, `src/components/workspace/WorkspacePage.jsx`, `src/pages/dio/DioPreviewPage.jsx`, `src/theme/*.js`, etc.). | **Maintainability**: Removes ~6,500 lines of dead/duplicate code and eliminates developer confusion.<br>**Verification**: Run AST syntax check, `pytest`, `npm test`, and `vite build`. |
| **REC-24** | **Consolidate Duplicate Frontend Components (`BootScreen`, `Hero`/`DynamicHero`, Voice, Settings Persona Modal)**<br>*(Area: Frontend / Cleanup)* | Section 2 of `05_FRONTEND_AUDIT.md` | `ChatPage.jsx` imports both `Hero` and `DynamicHero` (and mounts dead `VoiceOverlay`); `SettingsPage.jsx` has ~250 lines of dead persona modal code. | 1. Rename `src/components/BootScreen.jsx` -> `SuspenseLoader.jsx`.<br>2. Render `<DynamicHero>` in `ChatPage.jsx:572` and remove `VoiceOverlay.jsx` / `useVoiceCall.js`.<br>3. Delete dead persona modal state/JSX from `SettingsPage.jsx`.<br>*Modify*: `src/App.jsx`, `src/pages/{ChatPage,SettingsPage}.jsx`. | **Frontend**: Cleaner bundle and single source of UI truth.<br>**Verification**: Verify `ChatPage` and `SettingsPage` render and pass tests. |
| **REC-25** | **Fix PWA Service Worker Cache Strategy & Lazy-Load Heavy Markdown Renderers**<br>*(Area: Frontend / Performance)* | `BUG-41`, Section 2.3 of `12_PERFORMANCE_AUDIT.md` | `public/service-worker.js` uses Cache-First for `/index.html`, serving stale chunk hashes after deployments. `Markdown.jsx` eagerly imports `mermaid`, `katex`, and `leaflet`. | 1. Change `public/service-worker.js` to Network-First for navigation requests (`event.request.mode === "navigate"`).<br>2. Lazy-load `MermaidBlock`, `MapBlock`, and `GraphBlock` inside `src/components/Markdown.jsx` using `React.lazy()`.<br>*Modify*: `app/frontend/public/service-worker.js`, `app/frontend/src/components/Markdown.jsx`. | **Performance & Reliability**: Prevents stale broken bundles after deploys and reduces initial JS bundle size.<br>**Verification**: Run `vite build` and inspect chunk sizes. |
| **REC-26** | **Use SQLite Online Backup API (`sqlite3.Connection.backup`) & Add Table Retention Pruning**<br>*(Area: DevOps / Database)* | Section 2.6 of `13_DEPLOYMENT_AND_CONFIGURATION_AUDIT.md`, Section 3.3 of `12_PERFORMANCE_AUDIT.md` | `scripts/backup_restore.py:55` uses `shutil.copy2()` on live WAL databases and only backs up `topology.db`. `operational_health_scores` and `operational_gateway_heartbeats` grow unboundedly. | 1. Replace `shutil.copy2()` in `scripts/backup_restore.py` with `src_conn.backup(dst_conn)` across all active `.db` files.<br>2. Add daily pruning (`DELETE ... WHERE computed_at_utc < ?`) for `operational_health_scores` and `operational_gateway_heartbeats` (retain 30 days) in `core/governance/retention_engine.py`.<br>*Modify*: `AIRA_ECOSYSTEM/scripts/backup_restore.py`, `AIRA_ECOSYSTEM/core/governance/retention_engine.py`. | **Operational Reliability**: Guarantees crash-consistent SQLite backups and bounded database disk usage.<br>**Verification**: Test `backup_restore.py` during concurrent write load. |
