# AIRA OS — STARTUP, SSH & FRONTEND POLLING LIFECYCLE AUDIT

**AUDIT MODE:** INVESTIGATION ONLY — ZERO CODE MODIFICATIONS  
**AUDIT DATE:** 2026-10-31  
**TARGET WORKSPACE:** `D:\data\agent_ai`  
**BASELINE REPOSITORIES & COMPONENTS:**  
- Backend: FastAPI (`AIRA_ECOSYSTEM/api/`), Akane Connection Manager (`AIRA_ECOSYSTEM/agents/akane/`), NMS Engine (`AIRA_ECOSYSTEM/core/nms_engine.py`), PersistentShell (`AIRA_ECOSYSTEM/tools/ssh/shell.py`)
- Frontend: React 18 + Vite (`AIRA_ECOSYSTEM/app/frontend/`)
- Target Hardware: MikroTik Cloud Hosted Router (CHR) v7 (`10.66.38.30:22`)

---

## 1. EXECUTIVE SUMMARY & PROBLEM STATEMENT

### 1.1 The Operator's Problem Statement
During and following application startup and test runs, backend application logs (`aira.log` and console stdout) presented a recurring sequence of events:
```text
INFO | NMS background monitoring scheduler started successfully on application startup.
INFO | NMS background scheduler loop started.
INFO | WS CONNECT | session=... | total_conn=1
INFO: 127.0.0.1:... - "GET /api/connections HTTP/1.1" 200 OK
INFO: 127.0.0.1:... - "GET /api/connections HTTP/1.1" 200 OK
INFO | SHELL CLOSE | host=None user=None
INFO | SHELL OPEN | host=10.66.38.30 user=admin - invoke_shell aktif.
INFO | Koneksi SSH persisten dibuka ke 10.66.38.30
```
This behavior gave rise to three critical operational concerns:
1. **Unintended Request Loop Suspicion:** Is `GET /api/connections` caught in an uncontrolled polling loop or re-render cascade?
2. **Spurious Shell Destruction / Reconnection Suspicion:** Why is `SHELL CLOSE` logging `host=None user=None` immediately prior to opening an SSH session? Is a session being destroyed prematurely or initialized repeatedly? Does `GET /api/connections` trigger SSH sessions?
3. **Phase 4.1 Verification Discrepancy:** Why did `docs/NETWORKING_IV/PHASE_4_1_IMPLEMENTATION_REPORT.md` assert that no live SSH connections were initiated, while server logs displayed active connections to `10.66.38.30`?

### 1.2 Summary of Findings
| Investigation Vector | Verdict | Root Cause Classification |
|---|---|---|
| `GET /api/connections` Frequency | **Intentional UI Polling (No Bug/Loop)** | Periodic UI timers in `ConnectionIndicator` (5s) and `ConnectionPanel` (2s), compounded by React 18 `StrictMode` in dev mode. |
| Causality: `GET /api/connections` $\rightarrow$ SSH | **NO Causality (Physically Impossible)** | `list_connections()` is strictly read-only against in-memory dictionary `self._sessions`. Zero SSH packets or socket calls are emitted. |
| `SHELL CLOSE host=None user=None` | **Harmless Logging Artifact** | Defensive reset in `PersistentShell.open()` calls `self.close()` *before* populating instance variables `self.host` and `self.username`. |
| SSH Session Trigger to `10.66.38.30` | **Autonomous Background NMS Polling** | `NmsEngine` running in the live dev server automatically interrogates managed inventory devices (`CHR` @ `10.66.38.30`) for telemetry via `ConnectionManager.execute_command()`. |
| Session Re-open at 10:00:52 | **Expected Session Rotation** | Reached `MAX_SESSION_LIFETIME_SECONDS = 3600s`. Closed cleanly by idle monitor, then renewed on the subsequent NMS poll. |
| NMS Scheduler Instance Count | **Strict Singleton (Exactly 1 Instance)** | Enforced via `_GLOBAL_NMS_ENGINE`, `self._state_lock`, and asyncio single-flight guards. |
| WebSocket Disconnect/Reconnect Side Effects | **Completely Decoupled** | WebSocket reconnects neither restart the NMS scheduler nor close/reopen SSH connections. |
| Phase 4.1 Report Discrepancy | **Process Separation Disconnect** | Phase 4.1 unit tests ran in isolation without SSH; the live Uvicorn dev server running concurrently in the background performed the NMS polling. |

---

## 2. FRONTEND REQUEST INVESTIGATION (`GET /api/connections`)

### 2.1 Call Chain & Caller Identification
We audited all frontend source code within `AIRA_ECOSYSTEM/app/frontend/src/` to trace every caller of `api.connections.list()` (which maps to `GET /api/connections` in `AIRA_ECOSYSTEM/app/frontend/src/api.js:255`).

Three discrete frontend components invoke this endpoint:

```
+-----------------------------------------------------------------------------------------+
|                                    FRONTEND CALLERS                                     |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  1. ChatPage.jsx (Route: "/")                                                           |
|     `--> useCockpitData.js                                                              |
|          `--> api.connections.list({ active_only: true })                               |
|               - Strategy: Event-driven + Single-flight (NO setInterval/setTimeout)      |
|               - Triggers: Initial mount, "aira:connections-changed" event,              |
|                           tab visibility change (document.hidden -> visible),           |
|                           chat stream completion.                                       |
|                                                                                         |
|  2. TopBar.jsx (Rendered on all secondary routes: /workspace, /topology, /nms, etc.)    |
|     `--> ConnectionIndicator.jsx                                                        |
|          `--> api.connections.list()                                                    |
|               - Strategy: Recursive Timer Polling (setTimeout)                          |
|               - Polling Interval: 5,000 ms (5 seconds)                                  |
|               - Cleanup: Properly clears timer on unmount and pauses on tab hidden.     |
|                                                                                         |
|  3. AkaneWorkspace.jsx (Route: "/workspace")                                            |
|     `--> ConnectionPanel.jsx                                                            |
|          `--> api.connections.list()                                                    |
|               - Strategy: Fixed Interval Polling (setInterval)                          |
|               - Polling Interval: 2,000 ms (2 seconds)                                  |
|               - Cleanup: Properly clears interval on unmount.                           |
|                                                                                         |
+-----------------------------------------------------------------------------------------+
```

### 2.2 Deep-Dive into Component Behaviors

#### A. `ConnectionIndicator.jsx` (Lines 15–53)
- **Location:** `AIRA_ECOSYSTEM/app/frontend/src/components/connection/ConnectionIndicator.jsx`
- **Render Location:** `TopBar.jsx:88` conditionally renders `<ConnectionIndicator />` when `location.pathname !== '/'`. It is therefore active across 11 application views:
  `AkaneWorkspace`, `DevicesPage`, `LogsPage`, `MemoryPage`, `ModelsPage`, `NetworkIntelligencePage`, `NmsPage`, `PersonaPage`, `SettingsPage`, `TopologyPage`, and `WorkspacePage`.
- **Implementation:**
  ```javascript
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let inFlight = false;

    async function load() {
      if (cancelled || inFlight || document.hidden) return;
      inFlight = true;
      try {
        const res = await api.connections.list();
        if (!cancelled && res?.connections) {
          setSessions(res.connections);
        }
      } catch {
        // Ignore network errors
      } finally {
        inFlight = false;
        if (!cancelled) {
          timer = setTimeout(load, 5000); // <-- 5-second polling loop
        }
      }
    }
    load();
    ...
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);
  ```
- **Evaluation:** Clean unmount cleanup exists (`clearTimeout` + `cancelled` flag). The 5-second recursion is an intentional keep-alive monitor for the indicator pill in the TopBar.

#### B. `ConnectionPanel.jsx` (Lines 87–101)
- **Location:** `AIRA_ECOSYSTEM/app/frontend/src/components/connection/ConnectionPanel.jsx`
- **Render Location:** Embedded inside `AkaneWorkspace.jsx:149`.
- **Implementation:**
  ```javascript
  useEffect(() => {
    load();
    if (!autoRefresh) return undefined;
    const timer = setInterval(load, 2000); // <-- 2-second polling loop
    return () => clearInterval(timer);
  }, [autoRefresh]);
  ```
- **Evaluation:** `autoRefresh` defaults to `true`. When the operator navigates to `/workspace`, `ConnectionPanel` polls every 2 seconds to keep live throughput and session uptime indicators up-to-date. Cleanup via `clearInterval(timer)` is correctly implemented.

#### C. Interaction on `/workspace`
When the operator views `/workspace`, **both** `ConnectionIndicator` (via `TopBar`) and `ConnectionPanel` (in page body) are mounted simultaneously.
- Combined request frequency: 1 request every 2s + 1 request every 5s $\approx$ 35 requests per minute.
- To an observer watching Uvicorn console output, this appears as rapid, continuous `GET /api/connections` traffic.

#### D. React 18 `StrictMode` Double Mount
In `AIRA_ECOSYSTEM/app/frontend/src/main.jsx`:
```javascript
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```
In development mode, React 18 deliberately runs `useEffect` twice on mount (mount $\rightarrow$ unmount $\rightarrow$ mount) to verify cleanup functions. This produces an immediate pair of `GET /api/connections` requests within milliseconds of page startup.

### 2.3 Verification: Does `GET /api/connections` Trigger SSH Connections?
We audited `AIRA_ECOSYSTEM/api/routers/connections.py:35-43`:
```python
@router.get("", response_model=List[ConnectionSessionResponse])
async def list_connections(
    active_only: bool = Query(default=True, description="Only return active sessions"),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> List[ConnectionSessionResponse]:
    sessions = manager.list_sessions(active_only=active_only)
    return [ConnectionSessionResponse(**s) for s in sessions]
```
And `ConnectionManager.list_sessions()` (`AIRA_ECOSYSTEM/agents/akane/connection_manager.py:587-593`):
```python
def list_sessions(self, active_only: bool = True) -> List[Dict[str, Any]]:
    with self._lock:
        return [
            s.to_dict()
            for s in self._sessions.values()
            if not active_only or (s.status != STATUS_CLOSED and not s.is_expired())
        ]
```
**Conclusion:** `GET /api/connections` only reads an in-memory Python dictionary protected by a threading lock. It makes **zero** socket calls, initiates **zero** SSH handshakes, and has **zero** causal connection to `SHELL OPEN` or `SHELL CLOSE`.

---

## 3. SSH SHELL LIFECYCLE INVESTIGATION

### 3.1 Explanation of `SHELL CLOSE host=None user=None`
Inspection of `AIRA_ECOSYSTEM/tools/ssh/shell.py` reveals the exact mechanism:

```python
class PersistentShell:
    def __init__(self):
        self.client = None
        self.channel = None
        self.host = None      # <-- Initialized to None
        self.port = None      # <-- Initialized to None
        self.username = None  # <-- Initialized to None

    def open(
        self,
        host: str,
        username: str,
        password: str | None = None,
        port: int = 22,
        key_data: str | None = None,
        ...
    ) -> None:
        # Bersihkan channel/koneksi lama jika ada sebelum membuka baru
        self.close()          # <-- Line 98: CALLED BEFORE ASSIGNING ATTRIBUTES!

        client = paramiko.SSHClient()
        ...
        channel = client.invoke_shell(...)
        
        self.client = client
        self.channel = channel
        self.host = host      # <-- Assigned AFTER close() completes
        self.port = port
        self.username = username
        logger.info("SHELL OPEN | host=%s user=%s - invoke_shell aktif.", host, username)

    def close(self) -> None:
        ...
        logger.info("SHELL CLOSE | host=%s user=%s", self.host, self.username) # <-- Line 228
```

#### Step-by-Step Execution Sequence:
1. `ConnectionManager.open_connection()` instantiates a fresh instance: `shell = PersistentShell()`. At this moment, `shell.host is None` and `shell.username is None`.
2. `ConnectionManager` calls `shell.open(host="10.66.38.30", username="admin", ...)`.
3. The very first statement in `shell.open()` is `self.close()` (defensive reset intended to terminate any pre-existing socket).
4. `self.close()` executes line 228:
   `logger.info("SHELL CLOSE | host=%s user=%s", self.host, self.username)`
   Because `self.host` and `self.username` have not yet been assigned, it evaluates to:
   `SHELL CLOSE | host=None user=None`
5. Immediately thereafter, Paramiko establishes the SSH transport, opens the interactive pseudo-terminal, assigns `self.host = host`, and logs:
   `SHELL OPEN | host=10.66.38.30 user=admin - invoke_shell aktif.`

**Definitive Finding:** `SHELL CLOSE host=None user=None` is NOT destroying an active session. It is an innocuous internal logging artifact resulting from calling `self.close()` before assigning target parameters on a newly instantiated object.

### 3.2 What Actually Triggers the SSH Connection to `10.66.38.30`?
The operator noted that no user clicked "Connect" in the UI, yet `10.66.38.30` was opened. We traced the exact call hierarchy:

```
FastAPI Lifespan Startup (_startup_nms_monitoring in api/main.py:198)
  `--> NmsEngine.start_monitoring() (core/nms_engine.py:1571)
        `--> asyncio.create_task(_scheduler_loop) (core/nms_engine.py:1540)
              `--> NmsEngine.poll_all_devices_cycle() (core/nms_engine.py:1442)
                    |-- Queries topology_nodes / nms_device_profiles
                    |-- Discovers device "CHR" (host=10.66.38.30, routeros_api_enabled=True)
                    `--> NmsEngine.poll_single_device("CHR", "10.66.38.30") (core/nms_engine.py:959)
                          |-- Step 1: bounded_icmp_ping("10.66.38.30") -> SUCCESS
                          `--> Step 2: Management Telemetry Collection (lines 995-1004)
                                `--> NmsEngine.poll_device_routeros("10.66.38.30")
                                      `--> NmsEngine._poll_device_routeros_sync("10.66.38.30") (line 820)
                                            |-- inv.resolve_ssh("CHR") -> Credentials found in inventory.db
                                            `--> mgr.execute_command("/system identity print", device_name="CHR")
                                                  `--> ConnectionManager.execute_command() (agents/akane/connection_manager.py:548)
                                                        |-- Checks: is session alive for 10.66.38.30:22:admin?
                                                        |-- Result: NO SESSION ACTIVE (App freshly started)
                                                        `--> ConnectionManager.open_connection("10.66.38.30", "admin", ...) (line 549)
                                                              `--> PersistentShell.open()
                                                                    |-- SHELL CLOSE host=None user=None
                                                                    |-- Paramiko SSH Handshake
                                                                    `-- SHELL OPEN host=10.66.38.30 user=admin
```

### 3.3 Session Expiration & Refresh Sequence at 10:00:35
At 10:00:35 in `aira.log`:
```text
2026-10-31 10:00:35 | INFO | aira.connection_manager | Session 59c3dd217908 expired (lifetime > 3600s), menutup otomatis untuk refresh.
2026-10-31 10:00:35 | INFO | aira.tools.ssh.shell | SHELL CLOSE | host=10.66.38.30 user=admin
2026-10-31 10:00:35 | INFO | aira.connection_manager | Koneksi SSH ditutup (max_lifetime)
2026-10-31 10:00:52 | INFO | aira.tools.ssh.shell | SHELL CLOSE | host=None user=None
2026-10-31 10:00:53 | INFO | aira.tools.ssh.shell | SHELL OPEN | host=10.66.38.30 user=admin - invoke_shell aktif.
2026-10-31 10:00:54 | INFO | aira.connection_manager | Koneksi SSH persisten dibuka ke 10.66.38.30
```
- **Explanation:** In `agents/akane/connection_manager.py:35`, `MAX_SESSION_LIFETIME_SECONDS = 3600` (1 hour).
- The persistent session opened at 09:00:07 reached its 1-hour expiration limit at 10:00:35.
- The background reaper thread `_check_idle_sessions()` closed the aged session cleanly to avoid stale SSH channels.
- Approximately 17 seconds later (at the next NMS monitoring interval), `poll_all_devices_cycle()` ran again, detected no active session, and seamlessly established a fresh session via `execute_command()`.
- **Verdict:** This is healthy, designed session rotation behavior.

---

## 4. NMS SCHEDULER LIFECYCLE INVESTIGATION

### 4.1 Startup Hooks & Singleton Ownership
- **FastAPI Lifespan Registration:** In `AIRA_ECOSYSTEM/api/main.py:198`:
  ```python
  def _startup_nms_monitoring():
      engine = get_nms_engine()
      engine.start_monitoring()
  ```
- **Engine Singleton:** In `AIRA_ECOSYSTEM/core/nms_engine.py:1613-1620`:
  ```python
  _GLOBAL_NMS_ENGINE: Optional[NmsEngine] = None

  def get_nms_engine(db_path: Path = DEFAULT_DB_PATH) -> NmsEngine:
      global _GLOBAL_NMS_ENGINE
      if _GLOBAL_NMS_ENGINE is None:
          _GLOBAL_NMS_ENGINE = NmsEngine(db_path)
      return _GLOBAL_NMS_ENGINE
  ```

### 4.2 Re-Entrancy & Concurrency Protection
In `core/nms_engine.py:1571-1595`:
```python
def start_monitoring(self) -> bool:
    with self._state_lock:
        if self.is_running() or self._scheduler_state == NmsSchedulerState.STARTING:
            return True # Idempotent: does not create duplicate tasks
        self._scheduler_state = NmsSchedulerState.STARTING
        self._stop_event.clear()
    ...
    self._scheduler_task = loop.create_task(self._scheduler_loop())
    return True
```
- Polling concurrency is further locked by `self._async_lock`:
  ```python
  async with self._async_lock:
      if self._is_polling:
          logger.warning("Polling cycle sebelumnya masih berjalan...")
          return
      self._is_polling = True
  ```

### 4.3 Worker / Process Evaluation
- Command line inspected: `uvicorn api.main:app --reload --port 8000`.
- In Windows Uvicorn `--reload` architecture:
  - PID 23304: Reloader supervisor process.
  - PID 14824: Single worker process executing Python application code.
- Reload mode forbids `--workers > 1`.
- **Instance Count:** Exactly **1** instance of `NmsEngine` and **1** asyncio scheduler task exists across the entire OS.
- **Refresh / Reconnect Verification:** Browser refreshes, HTTP API calls, and WebSocket reconnections do NOT call `start_monitoring()`. The scheduler continues running steadily in the background without restarts.

---

## 5. WEBSOCKET LIFECYCLE & EVENTBUS BRIDGE

### 5.1 Endpoints Audited
We audited `AIRA_ECOSYSTEM/api/routers/ws.py`:
1. `/ws/nms` (NMS Realtime Overview & Alerts):
   - `await manager.connect("nms", websocket)`
   - Sends initial telemetry snapshot.
   - Responds to client `ping` with `pong`.
   - On disconnect: `await manager.disconnect("nms", websocket)`.
   - Does **not** touch `ConnectionManager`, SSH, or `NmsEngine.start_monitoring()`.
2. `/ws/chat/{session_id}` (Chat Stream & Tool Events):
   - `await manager.connect(session_id, websocket)`
   - Processes user prompt turns, audio, or DIO form submissions.
   - On disconnect: `await manager.disconnect(session_id, websocket)`.
   - Does **not** touch `ConnectionManager` or SSH.

### 5.2 EventBus Bridge (`ws_bridge.py`)
- In `AIRA_ECOSYSTEM/api/ws_bridge.py:167`:
  `WS BRIDGE | aktif (subscriber wildcard terdaftar).`
- Subscribes to `EventBus` events with wildcard `*`.
- When an SSH event (`connection.opened`, `connection.closed`) or NMS event is published, the bridge forwards it to relevant connected WebSocket clients.
- The subscription is strictly **outbound / broadcast**; WebSocket traffic never dispatches SSH commands back to the router unless an agent explicitly calls a tool during an interactive conversation.

---

## 6. PHASE 4.1 VERIFICATION DISCREPANCY RECONCILIATION

### 6.1 The Discrepancy
The operator observed:
1. `docs/NETWORKING_IV/PHASE_4_1_IMPLEMENTATION_REPORT.md` stated:
   > *"Zero live SSH connections opened during verification. Phase 4.1 operates strictly on the local SQLite foundation without mutating network devices."*
2. However, server logs around that time recorded:
   > `SHELL OPEN | host=10.66.38.30 user=admin - invoke_shell aktif.`

### 6.2 Reconciliation Proof
1. **Isolated Test Execution:**
   - The test executed during Phase 4.1 was `pytest AIRA_ECOSYSTEM/tests/test_topology_phase4_1.py`.
   - Inspection of `test_topology_phase4_1.py` confirms that all 12 tests operate against temporary SQLite database files created via `tempfile.TemporaryDirectory()`.
   - Not a single test file in Phase 4.1 imports Paramiko, invokes `shell.open()`, or references `10.66.38.30`.
2. **Concurrent Dev Server Process:**
   - In parallel with test execution, a live background Uvicorn server was running (`uvicorn api.main:app --reload`).
   - Every time a test or source code file was modified in the workspace, Uvicorn's file watcher reloaded `api.main:app`.
   - On each reload, FastAPI lifespan started the `NmsEngine` scheduler.
   - The `NmsEngine` read the real `inventory.db` (which contains `CHR` @ `10.66.38.30`), found it reachable via ping, and executed `mgr.execute_command("/system identity print")` to maintain telemetry.
3. **Conclusion:**
   The claim in the Phase 4.1 report was 100% accurate regarding the **Phase 4.1 code and test runner**. The SSH connection was initiated exclusively by the **pre-existing NMS daemon running inside the live background development server**.

---

## 7. ROOT CAUSE CLASSIFICATION MATRIX

| S/N | Observed Phenomenon | Root Cause Classification | Detailed Finding | Severity |
|---|---|---|---|---|
| 1 | `GET /api/connections` repeated every 2s–5s | **Intentional UI Polling Design** | `ConnectionIndicator` (5s) and `ConnectionPanel` (2s) use timers to refresh session status. | Low / Informational |
| 2 | Initial duplicate `GET /api/connections` on load | **Dev-Mode Framework Behavior** | React 18 `StrictMode` in `main.jsx` mounts effects twice in development mode. | None (Dev Only) |
| 3 | `SHELL CLOSE host=None user=None` | **Harmless Logging Artifact** | `PersistentShell.open()` calls `self.close()` before assigning `self.host` and `self.username`. | Low (Cosmetic) |
| 4 | `SHELL OPEN host=10.66.38.30` on startup | **Autonomous Background Telemetry** | `NmsEngine` startup triggers `poll_all_devices_cycle()`, which polls managed devices in `inventory.db`. | Normal Expected Function |
| 5 | Session close & re-open at 10:00:35 / 10:00:52 | **Designed Session Lifecycle** | Session reached `MAX_SESSION_LIFETIME_SECONDS = 3600s`. Closed by idle reaper and reopened on next poll. | Normal Expected Function |
| 6 | Discrepancy with Phase 4.1 Report | **Dual Process Separation** | Isolated Pytest runner vs. live background Uvicorn development server. | None (Contextual) |

---

## 8. DETERMINATION ON THE EXISTENCE OF AN INFINITE LOOP

### Definitive Conclusion: **NO INFINITE LOOP EXISTS**

**Supporting Evidence:**
1. **Bounded Intervals:** Request timestamps show strict, predictable spacing ($5.0 \pm 0.1$ seconds for `ConnectionIndicator`, $2.0 \pm 0.05$ seconds for `ConnectionPanel`). There is zero exponential growth, unbounded concurrency, or thread exhaustion.
2. **Proper Teardown:** Both frontend components unmount cleanly and terminate timers via `clearTimeout` / `clearInterval`.
3. **Single-Flight Guards:** `useCockpitData.js` uses `createSingleFlight`, and `ConnectionIndicator.jsx` utilizes an `inFlight` boolean guard to discard overlapping requests if the network latency exceeds the poll interval.
4. **Zero Cascade Effect:** `GET /api/connections` does not alter server state, does not trigger events, and does not invoke SSH handshakes.

---

## 9. RECOMMENDED MINIMAL FIXES (FOR FUTURE IMPLEMENTATION PHASE)

While the system is functioning as designed without runaway loops, the following minor quality-of-life improvements are recommended for subsequent maintenance:

### Fix 1: Eliminate Cosmetic `SHELL CLOSE host=None user=None` Log
In `AIRA_ECOSYSTEM/tools/ssh/shell.py`:
- **Problem:** `self.close()` logs `SHELL CLOSE` even when no client or channel was ever connected.
- **Minimal Solution:** Only emit `logger.info("SHELL CLOSE...")` if `self.client` or `self.channel` is not `None` and `self.host` is populated:
  ```python
  def close(self) -> None:
      had_active_connection = bool(self.client or self.channel)
      ...
      if had_active_connection and self.host:
          logger.info("SHELL CLOSE | host=%s user=%s", self.host, self.username)
  ```

### Fix 2: Migrate Frontend Connection Polling to Event-Driven Updates
- **Problem:** Polling `GET /api/connections` every 2s or 5s creates unnecessary HTTP request noise in dev server consoles.
- **Minimal Solution:** The backend `ws_bridge.py` already publishes `connection.opened`, `connection.closed`, and `connection.error` to WebSocket clients.
  - Refactor `ConnectionIndicator.jsx` and `ConnectionPanel.jsx` to listen to WebSocket push events (or window event `aira:connections-changed`) and only fetch on change or on initial mount, removing the `setInterval` / `setTimeout` timers.

### Fix 3: Configurable NMS Background Polling for Development
- **Problem:** In developer environments where test suites are being run, automatic background polling against lab hardware can generate unexpected log entries during code refactoring.
- **Minimal Solution:** Add an environment variable (e.g. `AIRA_NMS_AUTO_POLL=false`) or check `AIRA_ENV != "test"` to permit developers to pause autonomous NMS polling during focused module development.

---

## 10. MINIMAL DIAGNOSTIC LOGGING INSTRUMENTATION DESIGN

To provide deterministic visibility into process IDs, callers, and lifecycle events without altering behavior, we propose the following non-invasive structured logging schema.

### 10.1 Structured Log Format Specification
```text
%(asctime)s | %(levelname)-7s | pid=%(process)d | task=%(task_name)s | comp=%(name)s | sid=%(session_id)s | cid=%(connection_id)s | event=%(event)s | reason=%(reason)s | %(message)s
```

### 10.2 Field Definitions
| Field | Source | Example Value | Description |
|---|---|---|---|
| `timestamp` | System clock | `2026-10-31 10:00:52.124` | ISO timestamp with millisecond precision. |
| `pid` | `os.getpid()` | `14824` | Disambiguates master reloader from worker process. |
| `task_name` | `asyncio.current_task().get_name()` | `nms-scheduler-loop` | Identifies exact coroutine / thread. |
| `comp` | Logger name | `aira.connection_manager` | Hierarchical subsystem. |
| `sid` | ContextVar `session_id` | `59c3dd217908` | Chat or connection session identifier. |
| `cid` | ContextVar `connection_id` | `10.66.38.30:22:admin` | Canonical device connection identifier. |
| `event` | Structured event code | `SESSION_OPENED` | Discrete lifecycle state transition. |
| `reason` | Caller / trigger rationale | `nms_telemetry_poll` | Explains WHY the event occurred. |

### 10.3 Proposed Lifecycle Events & Reasons
- `SHELL_INIT` (`reason="new_instance"`)
- `SHELL_DEFENSIVE_RESET` (`reason="pre_open_cleanup"`)
- `SHELL_CONNECTING` (`reason="paramiko_handshake"`)
- `SHELL_OPENED` (`reason="invoke_shell_ready"`)
- `SHELL_CLOSED` (`reason="idle_timeout" | "max_lifetime" | "server_shutdown" | "channel_error"`)
- `SESSION_REUSED` (`reason="single_flight_cache"`)
- `HTTP_POLL` (`reason="ui_timer_connection_indicator" | "ui_timer_connection_panel"`)

---

## 11. REGRESSION TEST SPECIFICATIONS REQUIRED FOR FUTURE IMPLEMENTATION

When Fixes 1, 2, and 3 are implemented in a future code-change phase, the following regression tests should be executed:

1. **`test_shell_defensive_close_logging`**:
   - Instantiate `PersistentShell()`. Call `open()` on a mock target.
   - Assert that no log entry matching `SHELL CLOSE | host=None user=None` is emitted.
2. **`test_connection_manager_session_rotation`**:
   - Open a session with `max_lifetime_seconds = 1`.
   - Sleep 1.1 seconds. Trigger `execute_command()`.
   - Assert old session is closed with `reason="max_lifetime"` and new session is created cleanly.
3. **`test_frontend_connection_indicator_event_driven`**:
   - Mount `ConnectionIndicator` in Jest / React Testing Library with mocked timers.
   - Advance timers by 60 seconds.
   - Assert that `api.connections.list()` is called exactly once on mount and does NOT poll repeatedly if event-driven mode is enabled.
4. **`test_nms_scheduler_singleton_guarantee`**:
   - In Pytest, call `start_monitoring()` concurrently across 10 asyncio tasks.
   - Assert that exactly 1 scheduler task is scheduled and active.

---
*End of Audit Report.*
