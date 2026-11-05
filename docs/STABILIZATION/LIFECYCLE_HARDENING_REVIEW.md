# AIRA OS — PRE-NETWORKING IV LIFECYCLE HARDENING REVIEW
## NMS–SSH Session Ownership, Scheduler Concurrency, Reaper Safety & Read-Only Execution Boundary

**AUDIT MODE:** INVESTIGATION & TEST DESIGN ONLY — ZERO CODE MODIFICATIONS  
**AUDIT DATE:** 2026-10-31  
**WORKSPACE:** `D:\data\agent_ai`  
**MILESTONE BASELINE:** Networking IV Phase 4.1 Completed  
**TARGET FILES INSPECTED:**  
- `AIRA_ECOSYSTEM/agents/akane/connection_manager.py` (APCE)
- `AIRA_ECOSYSTEM/agents/akane/session_state.py`
- `AIRA_ECOSYSTEM/tools/ssh/shell.py` (PersistentShell)
- `AIRA_ECOSYSTEM/core/nms_engine.py` (NMS Daemon)
- `AIRA_ECOSYSTEM/core/nms_models.py`
- `AIRA_ECOSYSTEM/core/network_intelligence/security.py`
- `AIRA_ECOSYSTEM/tests/test_audit_a_ssh_reuse.py`
- `AIRA_ECOSYSTEM/tests/test_audit_b_nms_ws_polling.py`
- `AIRA_ECOSYSTEM/tests/test_nms.py`
- `AIRA_ECOSYSTEM/tests/test_routeros_command_hardening.py`

---

## 1. EXECUTIVE SUMMARY & LIFECYCLE DECISION

Following the completion of Networking IV Phase 4.1 (Graph Data Model & SQLite Foundation) and the Startup Lifecycle Audit, this review evaluates the runtime resilience of the NMS background scheduler, SSH connection pooling, session reaper, and read-only command boundaries before commencing Phase 4.2 (Automatic Topology Discovery & Link Resolution).

### Decision: **SAFE TO PROCEED WITH CONDITIONS**

The platform is **architecturally sound for development and single-worker execution**. Core protections—including per-target single-flight locks, per-session command serialization, and bounded semaphore concurrency—are functional and verified.

However, **three medium-severity lifecycle vulnerabilities and two test gaps** were discovered during code-path tracing that must be hardened before multi-device continuous discovery is enabled in production:
1. **TOCTOU Race Condition during Session Expiration:** A time-of-check to time-of-use window exists between `execute_for_device` checking `session_alive` and the session lock being acquired in `execute()`, which can result in an unhandled `"Session sudah ditutup"` failure if the reaper strikes during this window.
2. **Stale Session Reference on Unhandled Command Failure:** If a command or reconnect encounters an exception, the session status transitions to `STATUS_ERROR`, but remains in `_sessions` and `_host_index`. Subsequent commands treat `status != STATUS_CLOSED` as alive, repeatedly attempting to use a broken session until the 10-minute idle reaper cleans it up.
3. **Missing Reconnect Age Reset:** When auto-reconnect succeeds inside `execute()`, `session.connected_at` is not refreshed, causing the session to be abruptly closed by `MAX_SESSION_LIFETIME` shortly thereafter.
4. **Bypass of Centralized Read-Only Validator:** `NmsEngine._poll_device_routeros_sync` sends hardcoded read-only `print` strings directly to `mgr.execute_command` rather than routing through `execute_safe_readonly_command()`.
5. **Multi-Worker Process Ambiguity:** In multi-worker deployments (`uvicorn --workers > 1`), independent NMS scheduler instances would start in each process without inter-process coordination.

---

## 2. NMS–SSH SESSION OWNERSHIP DEEP-DIVE

### 2.1 Trace of Session Ownership Architecture

```
+----------------------------------------------------------------------------------------------------+
|                                    NMS - SSH INTERACTION CHAIN                                     |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [NmsEngine._scheduler_loop] (core/nms_engine.py:1540)                                             |
|        |                                                                                           |
|        v                                                                                           |
|  [NmsEngine.poll_all_devices_cycle] (core/nms_engine.py:1442)                                      |
|        |  (Single-flight guard: self._async_lock + self._is_polling)                                |
|        |  (Concurrency bounded: asyncio.Semaphore(10))                                              |
|        v                                                                                           |
|  [NmsEngine.poll_single_device] (core/nms_engine.py:959)                                           |
|        |  (Step 1: ICMP Ping check via bounded_icmp_ping)                                          |
|        |  (Step 2: If ping_ok and managed/routeros_enabled -> Query telemetry)                     |
|        v                                                                                           |
|  [NmsEngine._poll_device_routeros_sync] (core/nms_engine.py:820)                                    |
|        |  (Resolves credentials via inventory_store.resolve_ssh())                                 |
|        |  Calls: mgr.execute_command(cmd, device_name=resolved_dev_name)                           |
|        v                                                                                           |
|  [ConnectionManager.execute_command] (agents/akane/connection_manager.py:508)                      |
|        |  Delegates to: execute_for_device(device_name, command)                                    |
|        v                                                                                           |
|  [ConnectionManager.execute_for_device] (agents/akane/connection_manager.py:481)                   |
|        |  Checks: session_alive = (session_id in _sessions and status != CLOSED and not expired)   |
|        |  If alive: _total_sessions_reused += 1                                                    |
|        |  If not alive: open_connection_for_device() -> acquires per-target single-flight lock     |
|        v                                                                                           |
|  [ConnectionManager.execute] (agents/akane/connection_manager.py:379)                             |
|        |  Acquires: lock = self._get_lock(session_id) (Serializes execution on this session)        |
|        |  Auto-reconnects if transport dropped (session.shell.is_alive() == False)                 |
|        |  Sets: session.status = STATUS_BUSY                                                       |
|        v                                                                                           |
|  [PersistentShell.execute] (tools/ssh/shell.py:178)                                                |
|        |  Drains leftover buffers, sends command\r\n, reads until prompt                           |
|        v                                                                                           |
|  [ConnectionSession.record_command] (agents/akane/session_state.py:69)                             |
|        |  Updates latency, command_count, calls touch() -> status = STATUS_CONNECTED               |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 2.2 Answers to Specific Operational Questions

#### 1. Does NMS reuse an existing valid SSH session?
**YES.**  
In `agents/akane/connection_manager.py:489-506`:
```python
with self._lock:
    session_id = self._host_index.get(key)
    session_alive = (
        session_id in self._sessions
        and self._sessions[session_id].status != STATUS_CLOSED
        and not self._sessions[session_id].is_expired()
    )

if not session_alive:
    opened = self.open_connection_for_device(device_name)
    session_id = opened["session"]["session_id"]
else:
    with self._lock:
        self._total_sessions_reused += 1

return self.execute(session_id, command, timeout=timeout)
```
When `session_alive` is True, no new transport is created. The session is reused, and `_total_sessions_reused` is incremented. Verified by `test_audit_a_concurrent_single_flight` in `tests/test_audit_a_ssh_reuse.py`.

#### 2. Can concurrent NMS jobs execute commands on the same session safely?
**YES (Serialized).**  
In `agents/akane/connection_manager.py:389-391`:
```python
lock = self._get_lock(session_id)
with lock:
    ...
    exec_result = session.shell.execute(command, timeout=timeout)
```
Each session has a dedicated `threading.Lock` instantiated via `self._session_locks.setdefault(session_id, threading.Lock())`. If two asynchronous coroutines or threads invoke commands on the same session, they are serialized by `with lock:`. Verified by `test_audit_a_concurrent_command_execution_integrity` (5 concurrent threads, zero output corruption).

#### 3. Can the reaper close a session while a command is executing?
**NO (Direct Close Prevented by Lock, BUT Latent TOCTOU Window Exists).**  
In `agents/akane/connection_manager.py:320-322`:
```python
lock = self._get_lock(session_id)
with lock:
    session.shell.close()
    session.status = STATUS_CLOSED
```
Because `close_connection` acquires the exact same `_session_locks[session_id]` lock held by `execute()`, the reaper **cannot** physically close the Paramiko channel while `session.shell.execute()` is actively running.

**However, a TOCTOU Race Condition exists (Detailed in Section 5.1):**
In `execute_for_device()`, `session_alive` is evaluated under `self._lock`, which is then released before calling `self.execute(session_id)`. If the reaper fires between release of `self._lock` and acquisition of `lock` in `execute()`, `execute()` aborts with `{"success": False, "error": "Session sudah ditutup."}`.

#### 4. Is session expiration based on idle time or absolute lifetime?
**BOTH (Dual Expiration Model).**  
- **Absolute Lifetime Cap (`MAX_SESSION_LIFETIME_SECONDS = 3600`):** Enforced via `session.is_expired()`:
  `return (ts - self.connected_at) > self.max_lifetime_seconds`
  Even if continuously busy, every session is refreshed after 1 hour to prevent Paramiko memory or channel sequence exhaustion.
- **Inactivity Idle Timeout (`IDLE_TIMEOUT_SECONDS = 600`):** Enforced in `_check_idle_sessions()`:
  `s.idle_seconds() > IDLE_TIMEOUT_SECONDS` (10 minutes without command execution).

#### 5. Are active sessions protected from premature cleanup?
**PARTIALLY.**  
In `_check_idle_sessions()` (`connection_manager.py:946-955`):
- For lifetime expiry: `s.status != STATUS_CLOSED and s.status != STATUS_BUSY and s.is_expired()` $\rightarrow$ Sessions in `STATUS_BUSY` are **explicitly excluded** from `expired_candidates`.
- For idle expiry: `s.idle_seconds() > IDLE_TIMEOUT_SECONDS` $\rightarrow$ Does not explicitly check `STATUS_BUSY`. However, because command execution resets `last_activity` on completion, and commands have a max timeout of 25s, a busy session will never be idle for 10 minutes.

#### 6. Do failed SSH operations leave stale session references?
**YES (CRITICAL DEFECT IDENTIFIED).**  
In `agents/akane/connection_manager.py:468-479`:
```python
except Exception as exc:
    session.status = STATUS_ERROR
    session.last_error = str(exc)
    return {"success": False, "session_id": session_id, "command": command, "error": str(exc)}
```
When an unhandled transport or command error occurs:
1. `session.status` is set to `STATUS_ERROR`.
2. The session is **not** removed from `_sessions`.
3. The host key in `_host_index` is **not** cleared.
4. On the next command call, `execute_for_device()` checks:
   `self._sessions[session_id].status != STATUS_CLOSED`
   Since `STATUS_ERROR != STATUS_CLOSED`, `session_alive` evaluates to **`True`**!
5. `execute_for_device()` does not open a fresh session. It attempts to reuse the error session.
6. The dead session remains in `_host_index` until it reaches `IDLE_TIMEOUT_SECONDS` (10 minutes).

---

## 3. SCHEDULER SAFETY VERIFICATION

### 3.1 Single-Process Scheduler Guarantees

| Invariant | Implementation Mechanism | Code Reference | Verification Status |
|---|---|---|---|
| **Single Scheduler Task** | Atomic check-and-set via `_state_lock` and `NmsSchedulerState.STARTING` | `core/nms_engine.py:1573-1578` | **VERIFIED** |
| **No Overlapping Poll Cycles** | `self._async_lock` + boolean flag `self._is_polling` (Single-Flight Lock) | `core/nms_engine.py:1444-1448` | **VERIFIED** |
| **No Duplicate Jobs Per Device** | Devices gathered via SQL `JOIN topology_nodes` with unique primary keys | `core/nms_engine.py:1466-1474` | **VERIFIED** |
| **Bounded Polling Concurrency** | `asyncio.Semaphore(max_concurrency)` (Default: 10 concurrent tasks) | `core/nms_engine.py:1453` | **VERIFIED** |
| **Graceful Shutdown** | `stop_monitoring()` sets `_stop_event`, cancels task, updates state machine | `core/nms_engine.py:1596-1610` | **VERIFIED** |
| **Zero-Device Quiescence** | When `devices` list is empty, returns immediately and schedules next cycle | `core/nms_engine.py:1485-1490` | **VERIFIED** |

### 3.2 Multi-Worker Deployment Risk Assessment
- **Current Runtime:** Uvicorn dev server running with `--reload`, which strictly enforces `--workers 1`. In this mode, exactly one scheduler runs.
- **Production Multi-Worker Risk:** If Uvicorn or Gunicorn is launched with multiple worker processes (e.g. `uvicorn api.main:app --workers 4`), **each worker process will run its own lifespan hook**.
- **Consequence:** 4 separate OS processes would each instantiate `NmsEngine` and run independent `_scheduler_loop()` tasks. Because SQLite lacks inter-process mutex locks for background tasks, 4 concurrent polling cycles would hammer the network routers simultaneously.
- **Remediation Requirement:** For multi-worker deployments, leader election (via SQLite lock table, OS file lock, or Redis) or running the NMS scheduler as a dedicated standalone background service is required.

---

## 4. SSH REAPER SAFETY ANALYSIS

### 4.1 Parameter Audit
- `MONITOR_INTERVAL_SECONDS = 30`: Reaper runs every 30 seconds on a daemon thread.
- `IDLE_TIMEOUT_SECONDS = 600`: 10 minutes of complete inactivity closes the channel.
- `MAX_SESSION_LIFETIME_SECONDS = 3600`: 1 hour max transport life.

### 4.2 Is 3600 Seconds Truly Safe?
A static 3600-second session lifetime is **not unconditionally safe** without proper lifecycle management:
1. **Network Jitter & NAT Table Drops:** State-tracking firewalls and intermediate routers frequently drop idle TCP connections after 300 to 900 seconds. While Paramiko keep-alives mitigate this if enabled, an absolute 3600s timer does not guarantee the socket is physically intact.
2. **Auto-Reconnect Invalidation:** If a session drops after 3550 seconds, `execute()` detects `not session.shell.is_alive()` and successfully reconnects. However, `session.connected_at` is **not reset**. As a result, 50 seconds later, the reaper sees `uptime > 3600s` and immediately closes the brand-new socket!
3. **Reaper Locking:** The reaper calls `self.close_connection()`, which acquires `lock = self._get_lock(session_id)`. While this prevents cutting a command in half, it introduces a lock contention window where a thread waiting to execute a command is stalled while Paramiko tears down the transport.

---

## 5. READ-ONLY SECURITY AUDIT

### 5.1 NMS Command Execution Path
We verified the complete execution path for telemetry collection:
```
NmsEngine._poll_device_routeros_sync
  |-- cmd 1: "/system identity print"
  |-- cmd 2: "/system resource print"
  |-- cmd 3: "/system routerboard print"
  |-- cmd 4: "/interface print detail"
  `-- cmd 5: "/interface ethernet print detail"
        `--> mgr.execute_command(cmd)
              `--> PersistentShell.execute(cmd)
```
- **Finding:** Every command string in `_poll_device_routeros_sync` is a hardcoded read-only `print` command.
- **Mutation Check:**
  - Zero `/interface ... set ...` commands.
  - Zero `/system reboot` or `/system shutdown` commands.
  - Zero `/ip route ... add/set/remove` commands.
  - Zero `/ip firewall ...` commands.
  - Zero script execution or file writes.

### 5.2 Security Boundary Finding: Missing Wrapper Enforcement
- **Audited Protection:** `core/network_intelligence/security.py:execute_safe_readonly_command` contains an AST-like token validator that strictly blocks command substitution (`[reboot]`), code blocks (`do={reboot}`), file writes (`file=foo.txt`), and streaming modifiers (`follow`, `interval=`).
- **Defect:** `NmsEngine._poll_device_routeros_sync` calls `mgr.execute_command(cmd)` **directly**, bypassing `execute_safe_readonly_command()`.
- **Risk Level:** **LOW currently** (because command strings are hardcoded literals), but **ARCHITECTURALLY FRAGILE**. If dynamic arguments or user-specified parameters are added to NMS polling in the future without routing through `execute_safe_readonly_command()`, the security boundary could be bypassed.

---

## 6. POTENTIAL RACE CONDITIONS & RISK SEVERITY MATRIX

| ID | Vulnerability / Race Condition | Mechanism | Likelihood | Impact | Severity |
|---|---|---|---|---|---|
| **RC-01** | **TOCTOU Session Closure during Execution Hand-off** | `execute_for_device()` checks `session_alive` under `_lock`, releases `_lock`. Reaper runs before `execute()` acquires session lock. Command fails with `"Session sudah ditutup"`. | Low | Medium | **MEDIUM** |
| **RC-02** | **Stale `STATUS_ERROR` Session Trapping** | Command error sets `session.status = STATUS_ERROR`. Subsequent calls see `status != STATUS_CLOSED` and reuse dead session, failing repeatedly until 10m idle timeout. | Medium | High | **MEDIUM** |
| **RC-03** | **Premature Reconnection Reaper Eviction** | Auto-reconnect in `execute()` re-opens `PersistentShell` but fails to reset `session.connected_at`. Reaper destroys new connection seconds later. | Low | Medium | **LOW** |
| **RC-04** | **Multi-Worker Scheduler Duplication** | Uvicorn with `--workers > 1` launches independent NMS schedulers in every worker process, causing concurrent polling storms. | Low (in Dev) / High (in Prod) | High | **MEDIUM** |
| **RC-05** | **Direct Raw Execution Bypass in NMS** | `NmsEngine` bypasses `execute_safe_readonly_command()` validator, relying solely on call-site string cleanliness. | Low | High | **LOW** |

---

## 7. REGRESSION TEST MATRIX & MISSING TEST BLUEPRINTS

### 7.1 Existing vs. Missing Test Matrix

| Test Requirement | Existing Test File | Coverage Status | Gap / Missing Aspect |
|---|---|---|---|
| **Concurrent Command Execution** | `test_audit_a_ssh_reuse.py` | **COVERED** | 5 concurrent threads on single session verified. |
| **Session Reuse** | `test_audit_a_ssh_reuse.py` | **COVERED** | 10 concurrent calls, single-flight verified. |
| **Duplicate Scheduler Startup** | `test_nms.py:483` | **COVERED** | Sequential `start_monitoring()` idempotent verified. |
| **Scheduler Shutdown** | `test_nms.py:494` | **COVERED** | `stop_monitoring()` clean shutdown verified. |
| **Single-Flight Polling Overlap** | `test_audit_b_nms_ws_polling.py` | **COVERED** | `_is_polling` lock prevents concurrent cycles. |
| **Read-Only Command Hardening** | `test_routeros_command_hardening.py` | **COVERED** | Audited bypasses blocked at security layer. |
| **Reaper vs In-Flight Command Race** | *None* | **MISSING** | Verify reaper waits for in-flight command before close. |
| **TOCTOU Expired Session Auto-Retry** | *None* | **MISSING** | Verify `execute_for_device` recovers if session closes right before execute. |
| **Stale `STATUS_ERROR` Recovery** | *None* | **MISSING** | Verify dead session in `STATUS_ERROR` is evicted or reconnected. |
| **No Eligible Devices Quiescence** | *None* | **MISSING** | Verify empty inventory does not poll or spike CPU. |
| **NMS Routing via Read-Only Validator** | *None* | **MISSING** | Verify NMS interrogation calls strictly pass security validation. |

---

### 7.2 Missing Test Blueprints (Ready for Implementation Phase)

#### Test Blueprint 1: Reaper vs. In-Flight Command Race Condition
```python
def test_reaper_vs_inflight_command_mutual_exclusion(isolated_manager):
    """
    Verifies that the session reaper cannot close a session while a command
    is actively executing, and that execution finishes cleanly before closing.
    """
    opened = isolated_manager.open_connection("192.168.10.1", "admin", "pass")
    sid = opened["session"]["session_id"]
    sess = isolated_manager._sessions[sid]

    execution_started = threading.Event()
    execution_can_finish = threading.Event()
    cmd_result = {}

    def slow_command():
        # Custom mock shell execute that holds the lock
        with patch.object(sess.shell, "execute", side_effect=lambda c, timeout: (
            execution_started.set(),
            execution_can_finish.wait(timeout=2.0),
            {"output": "ok", "prompt_matched": True}
        )[2]):
            cmd_result["res"] = isolated_manager.execute(sid, "/system identity print")

    t = threading.Thread(target=slow_command)
    t.start()
    assert execution_started.wait(timeout=1.0)

    # Trigger reaper while command is running
    sess.connected_at = time.time() - (MAX_SESSION_LIFETIME_SECONDS + 10)
    reaper_thread = threading.Thread(target=isolated_manager._check_idle_sessions)
    reaper_thread.start()

    # Reaper must be blocked waiting for sess lock
    time.sleep(0.05)
    assert sess.status == STATUS_BUSY

    # Allow command to finish
    execution_can_finish.set()
    t.join()
    reaper_thread.join()

    # Command succeeded AND THEN reaper closed the session cleanly
    assert cmd_result["res"]["success"] is True
    assert sess.status == STATUS_CLOSED
```

#### Test Blueprint 2: TOCTOU Session Closed Recovery in `execute_for_device`
```python
def test_execute_for_device_recovers_if_session_closed_between_check_and_exec(isolated_manager):
    """
    Simulates a race where a session is closed immediately after passing the
    session_alive check in execute_for_device. It must auto-recover and succeed.
    """
    isolated_manager.open_connection("192.168.10.1", "admin", "pass", device_name="R1")
    
    original_execute = isolated_manager.execute
    def execute_with_injected_close(session_id, command, timeout=25.0):
        # Force session to closed right before execute logic runs
        isolated_manager.close_connection(session_id, reason="simulated_race")
        return original_execute(session_id, command, timeout=timeout)

    with patch.object(isolated_manager, "execute", side_effect=execute_with_injected_close):
        # With hardening fix, execute_for_device catches "Session sudah ditutup" and retries once
        res = isolated_manager.execute_for_device("R1", "/system identity print")
        assert res["success"] is True
```

#### Test Blueprint 3: Eviction of Stale `STATUS_ERROR` Sessions
```python
def test_stale_error_session_is_not_reused_indefinitely(isolated_manager):
    """
    Verifies that a session in STATUS_ERROR does not trap execute_for_device
    in a permanent failure loop.
    """
    opened = isolated_manager.open_connection("192.168.10.1", "admin", "pass", device_name="R1")
    sid = opened["session"]["session_id"]
    sess = isolated_manager._sessions[sid]

    # Force session into error state
    sess.status = STATUS_ERROR
    sess.last_error = "Simulated connection drop"

    # execute_for_device must detect STATUS_ERROR, discard stale session, and open fresh one
    res = isolated_manager.execute_for_device("R1", "/system identity print")
    assert res["success"] is True
    new_sid = isolated_manager._host_index[isolated_manager._host_key("192.168.10.1", 22, "admin")]
    assert new_sid != sid
```

#### Test Blueprint 4: Quiescence When Zero Eligible Devices Exist
```python
def test_nms_polling_cycle_quiescence_with_no_eligible_devices(isolated_nms):
    """
    Verifies that poll_all_devices_cycle() behaves cleanly when database
    has zero active/monitored devices: zero socket activity, timely timestamp updates.
    """
    async def run_test():
        # Clear all devices from test database
        with isolated_nms._lock, closing(isolated_nms._get_connection()) as conn:
            conn.execute("DELETE FROM topology_nodes")
            conn.execute("DELETE FROM nms_device_profiles")
            conn.commit()

        with patch.object(isolated_nms, "poll_single_device") as mock_poll:
            await isolated_nms.poll_all_devices_cycle()
            assert mock_poll.call_count == 0
            assert isolated_nms.last_poll_timestamp is not None
            assert isolated_nms.next_poll_timestamp > isolated_nms.last_poll_timestamp

    asyncio.run(run_test())
```

---

## 8. RECOMMENDED MINIMAL HARDENING FIXES

To be applied in the subsequent implementation phase:

### Fix 1: Harden `execute_for_device` Against TOCTOU and Stale Error States
In `AIRA_ECOSYSTEM/agents/akane/connection_manager.py:489-506`:
```python
# 1. Reject STATUS_ERROR in session_alive check:
session_alive = (
    session_id in self._sessions
    and self._sessions[session_id].status not in (STATUS_CLOSED, STATUS_ERROR)
    and not self._sessions[session_id].is_expired()
)

# 2. Add 1-shot retry in execute_for_device if session was closed concurrently:
res = self.execute(session_id, command, timeout=timeout)
if not res.get("success") and "sudah ditutup" in str(res.get("error", "")):
    logger.warning("Session %s ditutup saat dispatch, membuka sesi baru...", session_id)
    opened = self.open_connection_for_device(device_name)
    if opened.get("success"):
        res = self.execute(opened["session"]["session_id"], command, timeout=timeout)
return res
```

### Fix 2: Reset `connected_at` on Successful Auto-Reconnect
In `AIRA_ECOSYSTEM/agents/akane/connection_manager.py:407-412`:
```python
session.shell.open(...)
session.connected_at = time.time()  # <-- Reset lifetime clock upon successful reconnection
session.touch()
```

### Fix 3: Route NMS Telemetry Commands Through `execute_safe_readonly_command`
In `AIRA_ECOSYSTEM/core/nms_engine.py:861-868`:
```python
from core.network_intelligence.security import execute_safe_readonly_command

def _exec(cmd: str) -> Tuple[bool, str, str]:
    res = execute_safe_readonly_command(mgr, resolved_dev_name, cmd, timeout=timeout)
    if not res.get("success"):
        return False, "", res.get("error", "Execution failed")
    return True, res.get("output", ""), ""
```

---

## 9. CONCLUSION & VERDICT

| Review Area | Verification Result | Status |
|---|---|---|
| NMS–SSH Session Reuse | Single-flight pooling and session reuse verified | **PASS** |
| Command Serialization | Per-session locks prevent output corruption | **PASS** |
| In-Flight Reaper Protection | Mutex locks prevent cutting active commands | **PASS** |
| Single-Process Scheduler Safety | Single-flight cycle lock and state machine verified | **PASS** |
| Read-Only Execution Boundary | All commands are strictly read-only `print` calls | **PASS** |
| Latent Edge Cases Identified | TOCTOU race, `STATUS_ERROR` trapping, reconnect age reset | **DOCUMENTED** |

**FINAL DECISION: SAFE TO PROCEED WITH CONDITIONS.**  
Architecture and foundation are validated. Proceeding to Networking IV Phase 4.2 design is approved, with the hardening fixes and test blueprints scheduled for inclusion.
