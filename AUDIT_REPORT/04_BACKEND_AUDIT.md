# PHASE 4 — BACKEND DEEP AUDIT (`04_BACKEND_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM`  
**Scope**: All 386 non-test backend Python files across `api/`, `core/`, `agents/`, `tools/`, `mcp_servers/`, and `scripts/`.

---

## 1. API & Routing Audit (Section A)

### 1.1 Registered Route Inventory & Duplicate Mounts
- **Total FastAPI Router Modules**: 34 routers registered in [`api/main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/main.py#L97-L141) plus 2 health endpoints (`GET /health` and `GET /api/health` at `api/main.py:337-340`).
- **Duplicate Router Mount (`CONFIRMED`)**:
  - [`api/main.py:103-104`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/main.py#L103-L104) mounts `files.router` **twice**:
    ```python
    app.include_router(files.router)
    app.include_router(files.router, prefix="/api")
    ```
  - **Impact**: Every one of the 20 file/host endpoints in `api/routers/files.py` is exposed twice (`/files/*` and `/api/files/*`, `/host/info` and `/api/host/info`), doubling the unauthenticated attack surface.
- **Shadowed / Colliding Endpoints (`CONFIRMED`)**:
  1. **`POST /api/v1/admin/permissions/simulate`**:
     - Registered in [`api/routers/admin_platform.py:385`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/admin_platform.py#L385) (`admin_simulate_permissions`, guarded by `Depends(require_platform_admin)`) AND in [`api/routers/user_management.py:368`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/user_management.py#L368) (`simulate_permissions`, guarded by `Depends(require_permission("permissions.read"))`).
     - Because `admin_platform.router` is mounted at `api/main.py:131` before `user_management.router` at `api/main.py:133`, `user_management.py:368` is **100% shadowed and unreachable**.
  2. **`GET /api/intelligence/actions/policy` Shadowed by `GET /api/intelligence/actions/{action_id}`**:
     - In [`api/routers/network_intelligence.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/network_intelligence.py#L1556-L1591), `@router.get("/actions/{action_id}")` is defined at line `1556` **before** `@router.get("/actions/policy")` at line `1586`.
     - **Impact**: Every `GET /api/intelligence/actions/policy` request matches `{action_id} = "policy"` at line `1556` and returns `404 {"detail": "Action 'policy' not found."}`!
  3. **Dual-Decorated Singular/Plural Routes in `api/routers/personalization.py`**:
     - `personalization.py` registers both `/memory/*` and `/memories/*` (`L113-232`) and `/persona/*` and `/personas/*` (`L242-356`). Because `/persona/{persona_id}` (`L331`) captures arbitrary strings, the frontend call `PUT /api/v1/personalization/persona/instructions` (`src/api.js:449`) is captured with `persona_id = "instructions"` and fails with `404`/`400`.

### 1.2 Missing Backend Endpoints Expected by Frontend (`CONFIRMED`)
Cross-checking all frontend API calls against all 34 backend routers reveals **9 endpoints called by the frontend that do not exist on the backend**:
1. `POST /api/v1/auth/change-password` (called by `AccountProfileModal.jsx:71` — only `/change-password-mandatory` exists in `api/routers/auth.py:197`).
2. `POST /api/v1/auth/sessions/revoke-others` (called by `SettingsPage.jsx:937` — does not exist in `auth.py` or `user_management.py`).
3. `POST /api/v1/auth/register` (called by `AuthContext.jsx:181` — removed in Phase F.1 `auth.py`).
4. `GET /api/v1/billing/entitlements` (called by `SettingsPage.jsx:160` on every mount — actual route is `GET /api/settings/entitlements/summary` in `settings.py:92`).
5. `PUT /api/v1/personalization/persona/instructions` (called by `src/api.js:449` / `SettingsPage.jsx:230` — actual route is `PUT /api/v1/personalization/preferences` in `personalization.py:158`).
6. `POST /api/voice/synthesize` (called by `src/api.js:343`, `useVoice.js:244`, `useVoiceCompanion.js:187` — `api/routers/voice.py` only has `/api/voice/service/*`).
7. `POST /api/voice/transcribe` (called by `src/api.js:356` — does not exist in `voice.py`).
8. `GET /api/voice/status` (called by `src/api.js:368` — actual route in `voice.py:25` is `/api/voice/service/status`).
9. `POST /api/voice/tts` (called by `useVoiceCall.js:116` — does not exist in `voice.py`).

### 1.3 Request Validation, Pagination, Rate Limiting, Timeouts & Idempotency
- **Weak / Untyped Request Payloads**:
  - Several mutating routes accept raw `Dict[str, Any]` bodies instead of typed Pydantic models with field bounds:
    - `PUT /api/v1/admin/tokens/plan-policy` (`api/routers/admin_platform.py:305-306, 353`): `updates: Dict[str, Any]`.
    - `POST /api/v1/personalization/data/account-deletion-request` (`api/routers/personalization.py:459`): `payload: Optional[Dict[str, Any]] = None`.
    - `POST /api/intelligence/graph`, `/paths`, `/correlations`, `/rca`, `/anomalies`, `/health`, `/impact`, `/simulations`, `/history`, `/evidence` (`api/routers/network_intelligence.py:1183-1375`): accept raw `Optional[Dict[str, Any]] = Body(default=None)`.
- **Duplicate Pydantic Class Definition (`CONFIRMED`)**:
  - In [`api/routers/persona.py:55-63`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/persona.py#L55-L63), `class PersonaPreviewRequest(BaseModel)` is defined twice in the same file (at line 55 and line 61).
- **Pagination Gaps**:
  - `GET /api/devices` (`devices.py:77`), `GET /api/credentials` (`devices.py:432`), `GET /api/topology` (`topology.py:276`), `GET /api/v1/admin/tenants` (`admin_platform.py:96`), `GET /api/v1/admin/groups` (`user_management.py:217`), and `GET /api/sessions` (`sessions.py:59`) return unbounded lists without `limit`/`offset` pagination.
  - Conversely, `GET /api/logs/{log_id}` (`api/routers/logs.py:44-55`) fetches `log_store.query_logs(limit=500)` and searches in Python (`for entry in all_logs: if entry.get("id") == log_id:`), making any log older than the latest 500 entries unreachable (`404`)!
- **Rate Limiting (`CONFIRMED`)**:
  - [`core/security/rate_limiter.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/security/rate_limiter.py#L14-L82) (`SlidingWindowRateLimiter`) is **only** applied to `POST /api/v1/auth/login` (`api/routers/auth.py:81`).
  - Furthermore, `auth.py:76-78` trusts the client-supplied `X-Forwarded-For` header unconditionally (`if forwarded_for: client_ip = forwarded_for.split(",")[0].strip()`), allowing any attacker to bypass login rate limiting by sending a random `X-Forwarded-For` IP on every request!
  - Zero rate limiting exists on `/api/chat`, `/ws/chat/{session_id}`, `/api/connections/execute`, `/api/topology/discover`, or `/api/v1/billing/webhooks/{provider}`.
- **Idempotency**:
  - `BillingService.process_payment_webhook()` (`core/billing/service.py:224-308`) checks `billing_webhook_events` by `event_id` for idempotency, and `EdgeGateway` checks monotonic sequence numbers (`operational_gateway_sequences`), **but** `POST /api/v1/billing/invoices`, `POST /api/devices`, `POST /api/v1/automations`, and `POST /api/intelligence/actions` have no idempotency keys.

---

## 2. Controllers / Route Handlers Audit (Section B)

1. **Direct SQL & Business Logic in Routers (`CONFIRMED`)**:
   - [`api/routers/admin_platform.py:96-108, 213-223`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/admin_platform.py#L96-L108) and [`api/routers/settings.py:109-125`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/settings.py#L109-L125) open raw SQLite connections (`get_topology_connection`) and run SQL queries directly inside route handlers instead of delegating to `TenantManager` or `IdentityManager`.
2. **Hardcoded Actor Identities in Controllers (`CONFIRMED`)**:
   - [`api/routers/network_intelligence.py:1569`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/network_intelligence.py#L1569): `POST /api/intelligence/actions/{action_id}/resolve` hardcodes `reviewer_id="admin_user"` instead of extracting `ctx.user_id`.
   - [`api/routers/network_intelligence.py:1578`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/network_intelligence.py#L1578): `POST /api/intelligence/actions/{action_id}/execute` hardcodes `operator_id="admin_operator"` instead of extracting `ctx.user_id`.
3. **Internal Exception Message Leakage (`CONFIRMED`)**:
   - Across `api/routers/auth.py:204,214,224,234`, `api/routers/personalization.py:266,326,351`, `api/routers/topology.py`, and `api/routers/network_intelligence.py`, route handlers catch `Exception as exc` and return `raise HTTPException(status_code=400, detail=str(exc))` or `500`, leaking raw SQLite table/column names and internal Python error strings to clients.
4. **Deprecated FastAPI `@app.on_event` Hooks (`CONFIRMED`)**:
   - [`api/main.py:144-333`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/main.py#L144-L333) defines 9 separate `@app.on_event("startup")` handlers and 6 `@app.on_event("shutdown")` handlers instead of a single FastAPI `lifespan` context manager.

---

## 3. Services & Business Logic Audit (Section C)

### 3.1 Simulated / Placeholder / Hardcoded Services in Production Paths (`CONFIRMED`)
1. **`ActionManagementEngine.execute_action()` (`core/network_intelligence/action_engine.py:439-450`)**:
   - Does not execute any command on any device. Calls `time.sleep(0.1)` (`L441`), copies `rec.expected_after_state` into `actual_state` (`L446`), and sets `verification_passed = True` (`L445`).
2. **`PlaybookRunner.execute_playbook()` (`core/playbooks/runner.py:217-251`)**:
   - Never connects to any target device or invokes Ansible/SSH. Returns hardcoded Linux CLI output strings (`" 17:58:12 up 42 days..."`, `"Mem: 16000 4210..."`, `"/dev/sda1 50G..."`).
3. **`EpistemicReasoningEngine.reason()` (`core/ai/reasoning_engine.py:119-350`)**:
   - All 12 epistemic stages are static string templates (`evidence_fresh = True` at `L229`, hardcoded gateway `"10.0.0.1"` at `L275`, hardcoded fallback device `"sw-core-01"` at `L286`).
4. **`OperationalDecisionEngine.synthesize_decision()` (`core/operations/decision_engine.py:190-213`)**:
   - Regardless of the incident or RCA input, always synthesizes the exact same hardcoded SFP fiber-optic transceiver cleaning recommendation (`"Pemeriksaan Jalur Fisik & Transceiver SFP"`).
5. **`AutomationScheduler` (`core/scheduler.py:42-135`) & `OperationalSchedulerEngine` (`core/operations/scheduler.py:84-115`)**:
   - 8 of 10 actions in `core/scheduler.py` (`ACTION_CATALOG`) and all 4 built-in jobs in `core/operations/scheduler.py` (`HEALTH_AUDIT`, `CAPACITY_FORECAST`, `CERT_CHECK`, `ROUTE_AUDIT`) are 1-line dummy lambdas returning static dicts.
   - Furthermore, `core/scheduler.py:265-290` (`_check_and_run_due_jobs`) only evaluates `trigger_type == "INTERVAL"`; `CRON` jobs are never evaluated!
6. **`DeviceOnboardingEngine._discover_device_facts()` (`core/network_intelligence/onboarding.py:178-205`)**:
   - Only tests a raw TCP socket connect (`socket.create_connection`) and hardcodes `"os_family": "RouterOS"` and `"interfaces_count": "NOT_AVAILABLE (Pending First Polling Cycle)"`.
7. **`PlaybookEngine.execute_playbook()` (`core/network_intelligence/playbooks.py:416-417`)**:
   - Hardcodes `is_match = True` for all healthy diagnostic branch conditions (`"no_unwanted_drops"`, `"order_correct"`, `"gateway_directly_connected"`, `"state_is_full"`, `"session_established"`, `"vlan_filtering_enabled"`).
8. **`GoogleCalendarProvider` (`core/operations/calendar/google_provider.py:44-70`)**:
   - Pass-through stub that delegates all operations to `self.local_fallback` even when OAuth credentials are configured.

### 3.2 Confirmed Logic & Runtime Bugs in Services
1. **`core/file_processing/vision_llm.py:93-94`**: Passes `analysis={"description": text}` to `VisionResult(...)`, raising `TypeError: VisionResult.__init__() got an unexpected keyword argument 'analysis'` on 100% of successful Vision LLM calls.
2. **`core/network_intelligence/investigator.py:726-733, 776-777`**:
   - Accesses `d.name` and `d.id` on `dict` elements returned by `InventoryStore.list_devices()` (`AttributeError: 'dict' object has no attribute 'name'`).
   - Calls `analyzer = analyzer_cls()` on elements of `ALL_PROTOCOL_ANALYZERS` which are already instances (`TypeError: 'Layer2Analyzer' object is not callable`).
3. **`core/canonical_network.py:500-516`**: `_fetch_nms_statuses()` iterates `overview.get("devices", [])` on `NmsEngine.get_overview()`, which has no `"devices"` key, leaving `CanonicalDevice.nms_status` permanently `"UNKNOWN"`.
4. **`core/edge_gateway/ingestion.py:194-209`**: Uses `time.mktime()` (local time, UTC+7) to parse UTC timestamps (`"%Y-%m-%dT%H:%M:%SZ"`), shifting `seen_epoch` 7 hours into the past and causing `get_gateway_health()` to permanently report `"OFFLINE"`.
5. **`core/edge_gateway/collector.py:103-119`**: Executes `["ping", "-n", str(safe_count), "-w", str(timeout_ms), valid_ip]` and checks `"Reply from" in res.stdout` (Windows `ping` syntax), which fails 100% of the time on Linux.
6. **`core/topology_engine.py:4946`**: `_emit_topology_event()` calls `get_event_bus()`, which is never imported in `core/topology_engine.py` (`NameError`, silently swallowed by `except Exception: pass` at `L4956`).
7. **`agents/akane/config_engine.py:72-74 & 135-149`**:
   - Line 74 returns `/ip firewall nat remove [find action=masquerade]` for any masquerade command without a comment, deleting **all** masquerade rules on rollback.
   - Line 147 writes unmasked `data` instead of `masked_data` to `{operation_id}.json`.

---

## 4. Authentication & Authorization Audit (Section D)

### 4.1 Unauthenticated Routers & Endpoints (`CONFIRMED`)
Out of 34 routers, **13 routers (plus specific endpoints in 3 other routers) have ZERO authentication**:
1. `api/routers/connections.py` (5 endpoints — **Unauthenticated Router SSH/CLI Execution**).
2. `api/routers/files.py` (20 endpoints mounted twice = 40 paths — **Unauthenticated Host Workspace File Read/Write/Delete/Extract**).
3. `api/routers/automations.py` (8 endpoints — **Unauthenticated Automation Job CRUD & Trigger**).
4. `api/routers/settings.py` (5 of 6 endpoints — **Unauthenticated Global Settings & Approval Safety Policy Mutation**).
5. `api/routers/voice.py` (5 endpoints — **Unauthenticated Host Microphone Control**).
6. `api/routers/artifacts.py` (5 endpoints).
7. `api/routers/attachments.py` (11 routes).
8. `api/routers/workspace_links.py` (5 endpoints).
9. `api/routers/selection.py` (3 endpoints).
10. `api/routers/location.py` (6 endpoints — including `PUT /api/location/host`).
11. `api/routers/memory.py` (4 endpoints — global `long_term_memory.db` facts/events).
12. `api/routers/capabilities.py` (1 endpoint), `api/routers/tools.py` (1 endpoint), `api/routers/providers.py` (1 endpoint).
13. `api/routers/chat.py`: `POST /api/reset` (`L122` — **Unauthenticated Chat Session Wipe**) and `GET /api/token-usage` (`L133`).
14. `api/routers/ws.py`: `WS /ws/nms` (`L355`) and `WS /ws/chat/{session_id}` (`L385` — **Unauthenticated WebSocket Hijacking & User Impersonation**).

### 4.2 Broken Authentication & RBAC Escalation Vectors (`CONFIRMED`)
1. **Chat Form Submission Superadmin Escalation (`core/orchestrator.py:221-233`)**:
   - `Orchestrator.route()` attempts to read `user_id` from `context` (`AIRAContext`, which has no `user_id` field -> `None`) and runs `with event_scope(user_id=user_id_scope or "lingga_admin"): tool_res = self._execute_tool("add_device", sub_values)`, executing `add_device` with `lingga_admin` Superadmin privileges!
2. **Unauthenticated `X-Guest-ID: gst_...` Header Spoofing (`core/tenant/auth_deps.py:20-37`)**:
   - `_resolve_guest_or_auth_context()` fabricates a valid `TenantContext` (`is_authenticated=False`, `is_guest=True`, `roles=["GUEST"]`) whenever a client sends `X-Guest-ID: gst_anything` without an `Authorization` header.
3. **Unauthenticated `NOC_ADMIN` Fallback in `decisions.py:83-98` and `gateways.py:72-89`**:
   - Both `_get_ctx()` helpers contain an unreachable dead condition (`if not authorization or not authorization.startswith("Bearer "): if authorization and authorization.startswith("Bearer aira_tok_"):`) followed by returning a full-privilege internal `NOC_ADMIN` `TenantContext` when no `Authorization` header is provided!
4. **Internal Viewer -> Platform Admin Escalation (`api/routers/admin_platform.py:62`)**:
   - `require_platform_admin` checks `if not (ctx.is_internal or any(r in admin_roles for r in ctx.roles)):`. Because all users in `tenant_internal` have `is_internal=True`, **every internal user (including `READ_ONLY`) has full platform admin access**, including `POST /api/v1/admin/impersonate` (`L213`)!
5. **Group Admin -> Superadmin Escalation (`api/routers/user_management.py:150-177`)**:
   - `create_user` (`L98`) and `update_user` (`L150`) allow any user with `users.create` / `users.update` (`ADMIN` group) to assign `grp_super_admin` (`SUPER_ADMIN`) or overwrite `lingga_admin`'s password.
6. **Group `DENY` Rules Bypassed (`core/tenant/manager.py:1054-1068` & `core/tenant/models.py:2249-2254`)**:
   - `IdentityManager.validate_session_token()` unions legacy `ROLE_PERMISSIONS` (`L1056`) with `RbacService.get_effective_permissions()` (`L1063`), re-granting permissions that were explicitly denied by a group `DENY` rule in `RbacService`. Furthermore, `TenantContext.has_permission()` (`models.py:2249`) expands `PERMISSION_ALIASES` without checking `DENY` overrides.
7. **Localhost / Reverse-Proxy Admin Bypass (`api/routers/topology.py:58-92`)**:
   - `require_topology_admin` (used across `topology.py`, `nms.py`, and `network_intelligence.py`) ignores RBAC permissions completely and grants admin access to all requests from `127.0.0.1` / `::1` / `localhost` when `AIRA_TOPOLOGY_ADMIN_TOKEN` is unset.

---

## 5. WebSocket & Real-Time Audit (Section E)

1. **Zero Handshake Authentication (`api/routers/ws.py:355, 385`)**:
   - Neither `WS /ws/nms` nor `WS /ws/chat/{session_id}` authenticates the client or verifies that `session_id` belongs to the caller.
2. **Cross-User Session Hijacking & Impersonation (`api/routers/ws.py:319-326, 447-460`)**:
   - Connecting to `/ws/chat/{session_id}` allows any client to read live streamed tokens, truncate conversation history via `replace_from_turn_id` (`L447`), and execute LLM turns/tools impersonating `sess.get("user_id")` (`L319-326`).
3. **Broken Tenant Isolation & Global Broadcasts (`api/ws_manager.py:24-30, 60-65` & `api/ws_bridge.py:215-243`)**:
   - `ws.py:357, 387` calls `ws_manager.connect(session_id, websocket)` without passing `tenant_id`, defaulting all sockets to `"tenant_internal"`.
   - `ws_bridge.py:239-243` calls `ws_manager.broadcast(message)` for unscoped events (`settings.changed`, `device.*`, `connection.*`, `voice.*`), broadcasting them to **all connected clients across all tenants**.
4. **Memory Leak on Failed Socket Send (`api/ws_manager.py:42-58`)**:
   - When `ws.send_json()` fails in `ConnectionManager.send()`, dead sockets are removed from `self._connections[session_id]`, but empty `session_id` sets and `self._session_tenants[session_id]` entries are not cleaned up.

---

## 6. AI, Agent, Tooling & External Integrations Audit (Section F)

1. **System Prompt & Cross-User Memory Contamination (`core/brain.py:211-340` & `agents/rei/auto_extract.py`)**:
   - `agents/rei/auto_extract.py` extracts user facts after chat turns and writes them via `core.memory.remember_fact()` into the unscoped global `facts` table in `long_term_memory.db`.
   - `core/brain.py` loads `core.memory.list_facts()` into the system prompt for **every user**, leaking personal/network facts across tenants and users.
2. **Tool Execution Safety & SSH MITM (`tools/ssh/*.py`, `agents/akane/connection_manager.py`)**:
   - All 3 SSH client classes (`tools/ssh/client.py:86`, `tools/ssh/shell.py:101`, `agents/akane/connection_manager.py:867`) hardcode `paramiko.AutoAddPolicy()`.
   - `agents/akane/connection_manager.py:200, 387` falls back to `os.getenv("SSH_PASSWORD")` whenever `password is None`, leaking the server's default SSH password if an ad-hoc connection is opened to an untrusted host.
   - `agents/akane/network_tools.py:16-17` exposes `ping`, `nslookup`, and `traceroute` without `mcp_servers/network/security.py:validate_network_target()`, allowing targets starting with `-` to inject CLI flags into `subprocess.run`.
3. **Unused SSRF Validator (`core/security/ssrf_validator.py`)**:
   - `core/security/ssrf_validator.py` is **never imported anywhere in production code**. Furthermore, when `allow_private_devices=True`, it fails to block IPv4-mapped IPv6 loopback/metadata addresses (`::ffff:127.0.0.1`, `::ffff:169.254.169.254`) because `ip.is_private` is `True` for IPv4-mapped IPv6 addresses in Python's `ipaddress` module, short-circuiting before the loopback/link-local checks!
