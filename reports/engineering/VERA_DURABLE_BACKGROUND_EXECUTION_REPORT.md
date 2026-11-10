# VERA Durable Background Execution Architecture & State Machine Report

**Subsystem:** Core Operational Runtime / Durable Job Engine  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P0 Operational Reliability Transformation  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Executive Summary

In enterprise network intelligence platforms, operations such as BGP convergence recalculation, OSPF multi-area SPF recalculations, physical link discovery sweeps, multi-device firmware compliance checks, and live VRRP failover simulations can take seconds to minutes to execute. Previously, VERA relied solely on ephemeral Python `asyncio.Task` references stored in an in-memory dictionary `_ACTIVE_RUNS`. If a network engineer navigated away, refreshed their browser (F5), or closed their laptop lid, the connection was severed. Upon reconnection, the client had no knowledge of the active task, while subsequent requests were rejected with `Chat ini masih memproses permintaan sebelumnya` (a stuck busy lock).

This transformation establishes a durable background job execution framework backed by persistent SQLite storage (`database/jobs.db`), an explicit 10-state lifecycle state machine, real-time stage tracking, checkpointing, and automatic post-crash recovery.

---

## 2. Durable Job State Machine & Schema

The persistent job engine is implemented in `VERA_ECOSYSTEM/core/job_store.py` and exposed via REST in `VERA_ECOSYSTEM/api/routers/jobs.py`.

### 2.1 State Transitions

```
                    ┌────────────┐
                    │   QUEUED   │
                    └─────┬──────┘
                          │ (worker dequeues)
                          ▼
                    ┌────────────┐
             ┌─────►│  RUNNING   ├─────────────┐
             │      └──┬───────┬─┘             │
             │         │       │               │
  (resume)   │         │       ▼ (needs input) │ (cancel)
             │         │   ┌────────────────┐  │
             │         │   │ WAITING_FOR_   │  │
             │         │   │ INPUT/APPROVAL │  │
             │         │   └───────┬────────┘  │
             │         │           │ (input provided)
             │         │           ▼           │
             │         │     ┌───────────┐     │
             │         └────►│  RETRY_   │     │
             │               │  PENDING  │     │
             │               └───────────┘     │
             │                                 │
             ▼                                 ▼
    ┌────────────────┐               ┌────────────────┐
    │  INTERRUPTED   │               │   CANCELLED    │
    │(system restart)│               │  (user action) │
    └────────────────┘               └────────────────┘
             │                                 │
             ▼                                 ▼
    ┌────────────────┐               ┌────────────────┐
    │     FAILED     │               │   SUCCEEDED    │
    │(fatal runtime) │               │(100% complete) │
    └────────────────┘               └────────────────┘
```

### 2.2 Database Schema (`jobs.db`)

#### `durable_jobs`
- `job_id TEXT PRIMARY KEY`: Canonical identifier (`job_<14-hex>`).
- `session_id TEXT`: Associated chat conversation (optional for autonomous jobs).
- `run_id TEXT`: Ephemeral WebSocket run correlation identifier.
- `tenant_id TEXT`: Multi-tenant boundary isolation.
- `user_id TEXT`: Initiating operator identity.
- `job_type TEXT NOT NULL`: Discriminator (e.g., `chat_turn`, `network_diagnostic`, `topology_scan`).
- `title TEXT NOT NULL`: Operator-visible summary of the operation.
- `state TEXT NOT NULL`: Current state machine enum value.
- `progress REAL DEFAULT 0.0`: Normalized completion percentage ($0.0 \dots 100.0$).
- `stage TEXT`: Active milestone (e.g., `fetching_rib`, `calculating_matrix`, `completed`).
- `checkpoint_json TEXT`: Incremental state preservation for resume/recovery.
- `result_json TEXT`: Final payload including VAE v2 payload and turn references.
- `error_json TEXT`: Structured exception telemetry and error codes.
- `idempotency_key TEXT UNIQUE`: Prevents duplicate executions of identical jobs.
- `created_at REAL NOT NULL`: Unix timestamp.
- `updated_at REAL NOT NULL`: Unix timestamp of last progress heartbeat.
- `completed_at REAL`: Unix timestamp of terminal state entry.

#### `job_events`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`: Sequential cursor index.
- `job_id TEXT NOT NULL`: Target job correlation.
- `session_id TEXT`: Chat session correlation.
- `run_id TEXT`: Correlation id.
- `event_type TEXT NOT NULL`: Protocol event type (`thinking`, `tool_start`, `tool_finish`, `stream_delta`).
- `event_data TEXT NOT NULL`: Full event payload for deterministic replay.
- `created_at REAL NOT NULL`: Unix timestamp.

---

## 3. Crash Recovery and Interruption Handling

Upon server startup (`_startup_location()` in `VERA_ECOSYSTEM/api/main.py`), the platform automatically invokes:

```python
get_job_store().recover_interrupted_jobs()
```

Any job that was previously marked `RUNNING` or `QUEUED` when a host power outage or unhandled SIGKILL occurred is safely transitioned to `INTERRUPTED` with `stage='interrupted_system_restart'`. This guarantees that:
1. Dead jobs never block new turn execution.
2. Schedulers and frontend interfaces clearly communicate to operators that the previous job was interrupted by a platform reboot rather than hanging indefinitely.

---

## 4. REST API Endpoints (`/api/v1/jobs`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/jobs` | Lists recent background jobs with optional filtering by `session_id`, `state`, and `limit`. |
| `GET` | `/api/v1/jobs/active` | Retrieves the currently active job for a session without blocking. |
| `GET` | `/api/v1/jobs/{job_id}` | Inspects detailed execution metadata, checkpoint JSON, and progress. |
| `GET` | `/api/v1/jobs/{job_id}/events` | Returns the sequential event replay stream starting from `since_id`. |
| `POST` | `/api/v1/jobs` | Enqueues a new background job with idempotency key protection. |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Safely requests cancellation of an active or queued job. |

---

## 5. Automated Verification Results

Unit tests implemented in `VERA_ECOSYSTEM/tests/test_durable_jobs.py`:
- `test_job_lifecycle`: Validates complete lifecycle (`RUNNING` $\rightarrow$ progress update $\rightarrow$ event recording $\rightarrow$ `SUCCEEDED`).
- `test_job_recovery_on_interruption`: Validates automatic transition of uncompleted jobs to `INTERRUPTED` on engine restart.
- `test_jobs_api_endpoints`: Validates REST endpoints for creation, query, active session inspection, and cancellation.

Result: **PASSED (100%)**
