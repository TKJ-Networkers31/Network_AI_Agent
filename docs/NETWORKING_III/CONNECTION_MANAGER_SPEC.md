# AIRA OS — Phase Networking III
# Multi-Device Connection Manager Specification

## 1. Executive Summary

This document specifies the architecture, session lifecycle, bounded concurrency, and safety mechanisms of the **Multi-Device Connection Manager** (`agents/akane/connection_manager.py`), delivered under Work Package N3.2 of Phase Networking III.

---

## 2. Session Lifecycle & State Machine

### 2.1 State Definitions (`ConnectionState`)

Connections to managed network appliances cycle through formal, deterministic states:

```
[DISCONNECTED] ----(Connect Requested)----> [CONNECTING]
                                                  |
                     +----------------------------+
                     |                            |
            (Auth/TCP Success)            (Timeout/Auth Error)
                     v                            v
               [CONNECTED]                     [FAILED]
                     |                            |
            (Command Dispatch)                    |
                     v                            |
                  [BUSY]                          |
                     |                            |
            (Command Completed)                   |
                     v                            |
               [CONNECTED]                        |
                     |                            |
            (Disconnect / Error)                  |
                     +----------------------------+
                     v
               [DISCONNECTED]
```

Enum definition in `agents/akane/session_state.py`:
- `ConnectionState.DISCONNECTED` ("disconnected")
- `ConnectionState.CONNECTING` ("connecting")
- `ConnectionState.CONNECTED` ("connected")
- `ConnectionState.BUSY` ("busy")
- `ConnectionState.FAILED` ("failed")
- `ConnectionState.DEGRADED` ("degraded")

### 2.2 Backward Compatibility Aliases

Existing single-device and Phase 1–8 modules relying on `STATUS_DISCONNECTED`, `STATUS_CONNECTED`, `STATUS_BUSY`, `STATUS_FAILED` continue to function without modification via exported string constants.

---

## 3. Bounded Concurrency & Target Locking

### 3.1 Host Hardware Constraints (ThinkPad X270, i7-7500U, 8GB RAM)

To prevent resource exhaustion, thread contention, and SSH socket thrashing:
1. **Bounded Worker Pool**: Batch operations utilize a `ThreadPoolExecutor` with a default maximum concurrency of `max_workers = 4`.
2. **Per-Device Target Locking**: Each target device has an independent reentrant mutex (`threading.RLock`). Two concurrent commands directed at the same device are serialized, preventing session corruption and RouterOS terminal buffer corruption.
3. **Session Timeout Bounding**: SSH connection timeouts are capped at 5.0 seconds; command execution timeouts are capped at 10.0 seconds.

### 3.2 Method Signature: `execute_batch`

```python
def execute_batch(
    self,
    targets: List[str],
    command: str,
    max_workers: int = 4,
    timeout: float = 10.0,
) -> Dict[str, Dict[str, Any]]:
    """
    Executes a read-only command concurrently across multiple target devices.
    Returns a dictionary mapping device_identity -> command_result.
    """
```

---

## 4. Error Handling & Partial Failures

When executing across multiple targets:
- If a target fails authentication or is unreachable, its individual result captures `status = "FAILED"` and `error = "..."`.
- Other healthy targets proceed to completion uninterrupted.
- The manager never aborts the entire batch due to a single-node failure.

---

## 5. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/agents/akane/connection_manager.py` & `AIRA_ECOSYSTEM/agents/akane/session_state.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_connection_manager.py` (3 tests passed).
