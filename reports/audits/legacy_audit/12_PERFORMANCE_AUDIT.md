# PHASE 12 — PERFORMANCE & SCALABILITY AUDIT (`12_PERFORMANCE_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM`  
**Audit Mode**: Read-Only Code & Architectural Bottleneck Analysis

---

## 1. Backend Performance Audit (Section A)

### 1.1 Blocking Operations on `async def` FastAPI / WebSocket Paths (`CONFIRMED — HIGH`)
1. **Synchronous File I/O, Zip/Extract & Attachment Processing Inside `async def` Handlers**:
   - [`api/routers/attachments.py:73-170`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/attachments.py#L73-L170): `upload_attachment` and `upload_multiple_attachments` are declared `async def`, read uploaded file bytes (`await file.read()`), and then call `_service.ingest_upload(...)` **synchronously on the main asyncio event loop**! Because `ingest_upload` runs synchronous PDF/DOCX/ZIP extraction, SQLite inserts, and synchronous HTTP calls to the Vision LLM (`vision_llm.py:78`), a single image/PDF upload freezes the entire FastAPI event loop (blocking all WebSockets and other HTTP requests) for 2–30 seconds!
   - [`api/routers/ws.py:355-377`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/ws.py#L355-L377): `ws_nms` is an `async def` WebSocket handler that calls `_build_nms_snapshot()` (`L255-312`) synchronously on the event loop, executing synchronous SQLite queries across `TopologyEngine` and `NmsEngine`.
2. **Sequential Single-Threaded Multi-Device Polling in `NmsEngine.poll_all_enabled()` (`CONFIRMED — HIGH`)**:
   - [`core/nms_engine.py:619-662`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/nms_engine.py#L619-L662): `_scheduler_loop` calls `poll_all_enabled()`, which iterates `for profile in profiles:` sequentially (`L631`) in a single thread.
   - **Impact**: If 40 devices are configured and 10 are unreachable (5s SNMP timeout + 5s SSH timeout + 2s ping timeout = 12s each), a single "60-second" polling cycle takes **120+ seconds**, starving healthy devices of telemetry updates. Meanwhile, the concurrent `HardenedNmsScheduler` (`core/nms/scheduler.py:49`, which uses `ThreadPoolExecutor(max_workers=16)` and per-device circuit breakers) is unused in production!
3. **Heavy Module-Level & Startup Initialization (`CONFIRMED — MEDIUM`)**:
   - Across `api/routers/*.py` (`auth.py:25-29`, `admin_platform.py:31-36`, `operations.py:50-58`, `decisions.py:34-39`, `gateways.py:28`, `portal.py:55-64`), over **25 service singletons** are instantiated at module import time, each running `ensure_*_schema()` DDL transactions against `topology.db` before FastAPI even starts listening.
   - `api/main.py:144-298` registers 9 separate `@app.on_event("startup")` hooks that spawn multiple daemon threads (`NmsEngine`, `AutomationScheduler`, `OperationalSchedulerEngine`, `MemoryCompactor`, `ws_bridge`).
4. **Unbounded In-Memory Structures (`CONFIRMED — MEDIUM`)**:
   - `tools/ssh/client.py:30`: `_connections = {}` caches `paramiko.SSHClient` instances forever with no idle timeout, no max size, and no shutdown cleanup.
   - `api/ws_manager.py:42-58`: Failed WebSocket sends remove dead sockets from `self._connections[session_id]` without deleting empty `session_id` keys or `self._session_tenants[session_id]` entries.
   - `core/security/rate_limiter.py:25`: `self._requests: Dict[str, List[float]] = defaultdict(list)` grows unboundedly when attackers spoof random `X-Forwarded-For` IPs (`api/routers/auth.py:76-78`).

---

## 2. Frontend Performance Audit (Section B)

### 2.1 Synchronous Per-Chunk React Re-Renders Bypassing `streamBatcher` (`CONFIRMED — HIGH`)
- **Evidence**: [`app/frontend/src/context/ChatRuntimeContext.jsx:43, 203-209, 253-270`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/context/ChatRuntimeContext.jsx#L203-L209).
- **Root Cause**: `ChatRuntimeContext.jsx` imports `createStreamBatcher` and `isStreamEvent` from `src/utils/streamBatcher.js` and initializes `batcherRef.current` at lines `203-209` to coalesce token chunks into one `requestAnimationFrame` (~60fps) update. **However, `batcherRef.current.push()` is never called anywhere in `ChatRuntimeContext.jsx`!**
- **Impact**: Every single WebSocket `stream_chunk` event (`L253-270`) immediately calls `updateSession(..., { streamText: nextText })`, triggering a full React context re-render and incremental Markdown parse (`streamMarkdownParser.js`) up to 50–100 times per second during fast LLM streaming.

### 2.2 Duplicate & Uncoordinated Polling Loops (`CONFIRMED — MEDIUM`)
1. **Duplicate 5-Second Polling of `/api/connections`**:
   - [`src/components/connection/ConnectionIndicator.jsx:33`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/connection/ConnectionIndicator.jsx#L33) (mounted in `<TopBar>` on `ChatPage`) polls `api.connections.list()` every `5,000 ms`.
   - [`src/hooks/useCockpitData.js:90`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/hooks/useCockpitData.js#L90) (also mounted on `ChatPage`) simultaneously polls `api.connections.list()` every `5,000 ms`.
2. **Continuous 6-Second Voice Status Polling (`src/hooks/useVoiceCompanion.js:76`)**:
   - Polls `GET /api/voice/service/status` every `6,000 ms` for every browser tab because `<VoiceCompanionHost />` is mounted unconditionally in `src/App.jsx:334`.
3. **Redundant NMS Polling When WebSocket is Open (`src/pages/NmsPage.jsx:293`)**:
   - Continues polling `/api/nms/*` every `30,000 ms` via `setInterval` even when `/ws/nms` (`L304`) is connected and pushing live updates.

### 2.3 Eager Main Bundle Bloat & Monolithic Page Components (`CONFIRMED — MEDIUM`)
- **Heavy Synchronous Landing Bundle**: `src/App.jsx:23` imports `ChatPage.jsx` eagerly. `ChatPage.jsx` statically imports `MessageBubble.jsx` -> `Markdown.jsx`, which pulls in `mermaid`, `katex`, `leaflet`, and `dompurify` on initial page load before the user even sends a message.
- **Monolithic Components Without List Virtualization**:
  - `src/pages/WorkspacePage.jsx` (`1,860` lines), `src/pages/AdminPlatformPage.jsx` (`1,754` lines), `src/pages/TopologyPage.jsx` (`1,751` lines), and `src/pages/NmsPage.jsx` (`1,546` lines) render full tables/logs/nodes in the DOM without windowing (`react-window` / `@tanstack/react-virtual`).

---

## 3. Database Performance & Lock Contention Audit (Section C)

### 3.1 Write-on-Read Lock Contention in `validate_session_token()` (`CONFIRMED — CRITICAL BOTTLENECK`)
- **Evidence**: [`core/tenant/manager.py:1032-1035`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/manager.py#L1032-L1035).
- **Root Cause**: Every authenticated HTTP request calls `validate_session_token(token)`, which opens a write transaction (`with topology_transaction(self.db_path) as conn:`) and executes:
  ```sql
  UPDATE operational_user_sessions SET last_active_at = ? WHERE session_id = ?
  ```
- **Impact**: When a frontend page loads (e.g., `NmsPage` or `AdminPlatformPage` firing 5–8 parallel `GET` requests) while background NMS polling and heartbeat loops are running, **every `GET` request contends for the single global `RLock` and SQLite write lock on `topology.db`** (`TopologyWriteCoordinator` in `core/topology_db.py:38-68`). Since `POST /api/v1/auth/heartbeat` (`api/routers/auth.py:140`) already updates session activity every 30 seconds, updating `last_active_at` on every `GET` request is redundant and severely degrades concurrency.

### 3.2 N+1 Query Loops & Synchronous Write Amplification on Read Endpoints (`CONFIRMED — HIGH`)
1. **Synchronous `INSERT` Loops Inside `GET` Health Summary Endpoints**:
   - [`core/operations/health_scoring_engine.py:181-190, 299-330, 358-383`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/operations/health_scoring_engine.py#L299-L330): Calling `GET /api/v1/portal/dashboard/overview` (`portal.py:85`) or `GET /api/v1/decisions/health/summary` (`decisions.py:216`) invokes `score_tenant(tenant_id)`.
   - `score_tenant()` loops over every device, site, service, and gateway in the tenant, calling `score_device()`, `score_site()`, `score_service()`, and `score_gateway()`, each of which opens multiple SQLite connections and executes an **`INSERT INTO operational_health_scores` write transaction**! For a tenant with 50 devices and 10 services, a single `GET` dashboard request executes **60+ sequential SQLite write transactions**!
2. **Classic N+1 `SELECT` Loops**:
   - `ServiceIntelligenceEngine.list_services()` (`core/operations/service_intelligence.py:153-167`): Executes `SELECT service_id FROM operational_services`, then calls `self.get_service(r[0])` in a Python `for` loop (2 queries per service).
   - `ProactiveIncidentEngine.list_incidents()` (`core/operations/incident_engine.py:117-147`): Executes `SELECT incident_id FROM operational_incidents`, then calls `self.get_incident(r[0])` in a loop.
   - `OperationalSchedulerEngine.list_jobs()` (`core/operations/scheduler.py:300-316`): Executes `SELECT job_id FROM operational_jobs`, then calls `self.get_job(r[0])` in a loop.
3. **Unbounded Table Growth (`CONFIRMED — MEDIUM`)**:
   - `operational_health_scores` (`core/operations/db.py:182`) and `operational_gateway_heartbeats` (`core/edge_gateway/db.py:69`) have no retention pruning job, growing indefinitely until disk space is exhausted or queries degrade.
   - `topology_snapshots` (`core/topology_engine.py:348`) and `route_snapshots` (`core/routing/route_history.py:673`) store full serialized JSON graphs (`nodes_json`, `edges_json`, `routes_json`) per snapshot and have SQLite triggers (`BEFORE DELETE RAISE(ABORT, ...)`) that **forbid deleting old snapshots**, preventing standard retention cleanup without dropping the trigger!
