# VERA — CHECKPOINT-BASED RESUMPTION & PAUSE/CONTINUE ARCHITECTURE REPORT

**Document ID:** `VERA-REP-CHECKPOINT-RESUME-01`  
**Classification:** Core Execution Architecture & Distributed State Machine  
**Status:** IMPLEMENTED & TEST VERIFIED  
**Date:** 2026-11-10  
**Author:** Staff Distributed Systems Architect & Background Task Lead  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/`

---

## 1. OBJECTIVE & EXECUTIVE SUMMARY

Complex network operations—including multi-hop discovery, automated firmware upgrades, BGP convergence verifications, and multi-step diagnostic investigations—require robust state preservation. 

Operators must be able to:
1. Temporarily **pause** a long-running execution (e.g., waiting for an approved maintenance window, or to inspect intermediate results).
2. Inspect the exact checkpoint of completed tool executions and streamed tokens.
3. **Resume** the operation with additional guidance without re-executing already completed commands.

This overhaul introduces `JobState.PAUSED` to the durable state machine, adds explicit `pause_job` and `resume_job` APIs in `core/job_store.py`, and wires bidirectional pause/resume WebSocket protocol handlers in `api/routers/ws.py`.

---

## 2. STATE MACHINE ARCHITECTURE

```
                  +---------------+
                  |    QUEUED     |
                  +-------+-------+
                          |
                          v
                  +---------------+     pause()      +---------------+
                  |    RUNNING    +----------------->+    PAUSED     |
                  +---+-------+---+                  +-------+-------+
                      |       ^                              |
                      |       +------------------------------+
                      |                   resume()
                      v
         +------------+------------+
         |                         |
         v                         v
  +--------------+          +--------------+
  |  SUCCEEDED   |          |    FAILED    |
  +--------------+          +--------------+
```

### 2.1 State Definitions & Active Set

`core/job_store.py` defines:
```python
class JobState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RETRY_PENDING = "RETRY_PENDING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"

ACTIVE_STATES = {
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.PAUSED.value,
    JobState.WAITING_FOR_INPUT.value,
    JobState.WAITING_FOR_APPROVAL.value,
    JobState.RETRY_PENDING.value,
}
```

A paused job remains in `ACTIVE_STATES` so that session queries (`get_active_job_for_session`) recognize the job as an ongoing workload rather than abandoning it.

---

## 3. CHECKPOINT PERSISTENCE IMPLEMENTATION

### 3.1 `JobStore.pause_job()`
```python
def pause_job(
    self,
    job_id: str,
    checkpoint_data: Optional[Dict[str, Any]] = None,
    reason: str = "Paused by user",
) -> Optional[DurableJob]:
```
- Atomic transition from `RUNNING` to `PAUSED`.
- Stores `checkpoint_data` containing:
  - `accumulated_text`: Generated response text up to the pause point.
  - `live_tools`: List of completed and in-flight tools with their exact inputs, execution statuses, and return values.
  - `pause_reason`: Contextual reason (e.g., "Awaiting maintenance window").
  - `paused_at`: Timestamp.

### 3.2 `JobStore.resume_job()`
```python
def resume_job(
    self,
    job_id: str,
    additional_instructions: Optional[str] = None,
) -> Optional[DurableJob]:
```
- Atomic transition from `PAUSED` back to `RUNNING`.
- Stores `additional_instructions` (operator instructions or parameter overrides).
- Restores `resumed_at` timestamp.

---

## 4. WEBSOCKET PROTOCOL EXTENSIONS (`api/routers/ws.py`)

1. **Client Pause Request:**
   ```json
   { "type": "pause", "job_id": "job_123456" }
   ```
   Server acknowledges with:
   ```json
   {
     "type": "job_paused",
     "data": {
       "session_id": "...",
       "job_id": "job_123456",
       "checkpoint": { ... }
     }
   }
   ```

2. **Client Resume Request:**
   ```json
   { "type": "resume", "job_id": "job_123456", "instruction": "Lanjutkan reboot sekarang" }
   ```
   Server acknowledges with:
   ```json
   {
     "type": "job_resumed",
     "data": {
       "session_id": "...",
       "job_id": "job_123456",
       "instruction": "Lanjutkan reboot sekarang"
     }
   }
   ```

---

## 5. VERIFICATION & VALIDATION

A dedicated test `test_job_pause_and_resume` was implemented in `VERA_ECOSYSTEM/tests/test_durable_jobs.py`:
- Verified job creation in `RUNNING` state.
- Verified transition to `PAUSED` with checkpoint data and `is_active() == True`.
- Verified transition back to `RUNNING` with `additional_instructions`.
- Execution: `4/4 passed in 3.29s`.
