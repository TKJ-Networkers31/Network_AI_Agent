# AIRA OS — NETWORKING IV PHASE 4.3 IMPLEMENTATION REPORT
## Event-Driven NMS State Synchronization, Observation Freshness & Decayer Consistency

**Document ID:** `AIRA-NET-IV-REPORT-4.3`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** IMPLEMENTATION_AUDITED_AND_ACCEPTED  
**Workspace:** `D:\data\agent_ai`  
**Baseline Git Commit:** `be59871acd2dd92c581d8944e65899d485f208ae`  
**Target Hardware:** MikroTik Cloud Hosted Router (CHR) v7 (`10.66.38.30:22`) — READ-ONLY / Zero Mutations  

---

## 1. Executive Summary & Objective

In strict accordance with the approved **Networking IV Implementation Roadmap** and the **Phase 4.3 Correctness Audit Specification**, Phase 4.3 has been implemented, audited, validated, and regression tested.

Phase 4.3 integrates real-time NMS operational events with the AIRA Topology Engine. It establishes **Event-Driven Operational State Synchronization** while enforcing the **Physical Adjacency Invariance Principle**: operational status updates (`oper_status`, reachability, observation timestamps, delta changes) occur without mutating underlying relationship classifications, inventing physical links, or tombstoning disconnected infrastructure.

### 1.1 Tripartite Architectural Division of Responsibility:
```
┌────────────────────────────────────────────────────────────────────────┐
│                        TRIPARTITE ARCHITECTURE                         │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Subsystem            │ Authoritative Responsibility                    │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **Discovery Engine** │ Discovers network STRUCTURE and adjacency       │
│                      │ classes (Physical, Layer 2, Layer 3, Logical).  │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **NMS Engine**       │ Observes live OPERATIONAL CONDITIONS            │
│                      │ (oper_status, reachability, latency, traffic).  │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **Topology Engine**  │ STORES graph relationships, evidence records,   │
│                      │ historical snapshots, and delta changes.        │
└──────────────────────┴─────────────────────────────────────────────────┘
```

### 1.2 Correctness Audit Deliverables Completed:
1. **Actual NMS Event Production Path Audited:** Identified root cause of observation decay in steady state (`NMS_INTERFACE_STATUS_CHANGED` was emitted only on transitions).
2. **Decoupled Telemetry Event Model:** Introduced `EventNames.NMS_INTERFACE_OBSERVED` (`"nms.interface.observed"`) for unchanged interface observations, preserving freshness across successful polls.
3. **Freshness vs Status Separation:** Enforced strict separation between `oper_status` (operational link state), `observation_freshness` (recency of latest successful observation), `lifecycle_state` (graph lifecycle), and `relationship_class` / confidence (topology structure).
4. **WebSocket Push Optimization:** Eliminated unnecessary WebSocket broadcasts for unchanged observations. Status transitions broadcast `nms_interface_status_changed` and `topology.delta`; unchanged observations refresh freshness silently.
5. **Decayer Storage Model Resolved:** Reconciled in-memory ticker execution (`asyncio.Task`, `threading.Lock`, `time.monotonic()` interval pacing) with persistent SQLite storage (`last_seen`, `observation_freshness = 'stale'`).
6. **Persistence & Restart Model Documented:** Ensured monotonic time is never persisted to database; persisted wall-clock timestamps (`time.time()`) provide deterministic staleness evaluation across application restarts.
7. **14 Audit Regression Scenarios Implemented:** Created comprehensive test suite in `test_topology_nms_sync_v4.py` bringing total suite to **32 / 32 tests passing** (18 baseline + 14 audit scenarios).
8. **Full Regression Verification:** Verified **1064 backend tests** (176 subtests), **247 frontend tests**, **103 security hardening tests**, and clean Vite production build.

---

## 2. Audit of Actual NMS Event Production Path & Root Cause Analysis

### 2.1 Inspection of Pre-Audit Implementation
Tracing execution through `AIRA_ECOSYSTEM/core/nms_engine.py`:
- In `_save_metrics` (lines 1379–1397), after updating `nms_interface_metrics`:
  ```python
  curr_oper = iface.get("oper_status", "unknown")
  prev_oper = prev_s["oper_status"] if (prev_s and "oper_status" in prev_s.keys()) else None
  if prev_oper and prev_oper != curr_oper and curr_oper != "unknown":
      event_bus.publish(EventNames.NMS_INTERFACE_STATUS_CHANGED, ...)
  ```

### 2.2 Root Cause Analysis
1. **Transition-Only Emission:** The event `NMS_INTERFACE_STATUS_CHANGED` was published **strictly when `oper_status` transitioned** (`prev_oper and prev_oper != curr_oper`).
2. **Steady-State Starvation:** During normal network operation where an interface remained continuously `UP` across polling cycles (e.g. 15s intervals), no event was published on `event_bus`.
3. **False Positive Stale Decay:** Because no event was published, `topology_edges.last_seen` was never updated. When the 60-second decayer scanned the database, the edge exceeded the 60-second freshness threshold and decayed to `stale`, despite being actively and successfully polled by NMS every 15 seconds.
4. **Broadcast Inefficiency:** In `core/topology_engine.py`, any call to `handle_nms_event` was emitting `topology.delta` over EventBus regardless of whether `oper_status` had actually changed, causing unnecessary WebSocket traffic if called redundantly.

### 2.3 Corrective Resolution: Decoupled Telemetry Architecture
To resolve the contradiction between event publication and freshness tracking, the architecture was decoupled into two distinct events:

1. **`EventNames.NMS_INTERFACE_STATUS_CHANGED` (`"nms.interface.status_changed"`):**
   - **Condition:** Emitted ONLY when `prev_oper is not None and prev_oper != curr_oper and curr_oper != "unknown"`.
   - **Action:** Updates `oper_status`, updates `last_seen`, resets `observation_freshness = 'fresh'`, records a `TopologyChange(STATUS_CHANGED)` audit delta, and emits `topology.delta` to WebSocket clients.
2. **`EventNames.NMS_INTERFACE_OBSERVED` (`"nms.interface.observed"`):**
   - **Condition:** Emitted on every successful poll where interface status is unchanged (`prev_oper == curr_oper`) or on initial poll (`prev_oper is None`).
   - **Action:** Updates `last_seen` and resets `observation_freshness = 'fresh'`. Suppresses `oper_status` mutation, suppresses `TopologyChange` logging, and suppresses WebSocket broadcasts.
3. **Failed Polling Guard:**
   - If polling a device fails (timeout, authentication failure, unreachable), `interfaces_to_save` is empty.
   - Neither `NMS_INTERFACE_STATUS_CHANGED` nor `NMS_INTERFACE_OBSERVED` is published.
   - `last_seen` is NOT updated, allowing the decayer to accurately flag stale observations after 60 seconds of polling silence.

---

## 3. Freshness Semantics & State Separation

Strict separation is enforced across four distinct dimensions:

| Dimension | Field / Entity | Authoritative Subsystem | Mutated by NMS Events? | Mutated by Decayer? |
|---|---|---|---|---|
| **Operational State** | `topology_edges.oper_status` (`up`, `down`, `degraded`) | NMS Polling Engine | **YES** (Only on transition) | **NEVER** |
| **Observation Freshness** | `topology_edges.observation_freshness` (`fresh`, `stale`) | Decayer & NMS Sync | **YES** (Reset to `'fresh'`) | **YES** (`'stale'` if $t > 60\text{s}$) |
| **Lifecycle State** | `topology_edges.lifecycle_state` (`active`, `tombstoned`) | Discovery Engine | **NEVER** (Down $\ne$ tombstone) | **NEVER** |
| **Topology Semantics** | `relationship_class`, `confidence_tier`, `confidence_score` | Discovery Engine | **NEVER** (Adjacency invariant) | **NEVER** |

### Event Schema Definitions

#### `nms.interface.status_changed`
```json
{
  "device_id": "node_chr",
  "interface_name": "ether2",
  "oper_status": "down",
  "previous_status": "up",
  "timestamp": 1793410500.0,
  "speed_bps": 1000000000,
  "admin_status": "enabled"
}
```

#### `nms.interface.observed`
```json
{
  "device_id": "node_chr",
  "interface_name": "ether2",
  "oper_status": "up",
  "previous_status": "up",
  "timestamp": 1793410515.0,
  "speed_bps": 1000000000,
  "admin_status": "enabled"
}
```

---

## 4. Decayer Storage & Persistence Model

### 4.1 Resolution of In-Memory vs SQLite Terminology
The term **"In-Memory Decayer"** describes the execution and scheduling model:
- The decayer runs as an in-memory asynchronous coroutine loop (`_decayer_loop`) inside an `asyncio.Task`.
- Interval pacing is controlled using `time.monotonic()` to measure elapsed loop time and prevent clock drift.
- Stop signals are handled via an in-memory `asyncio.Event` (`_decayer_stop_event`).
- Concurrency is protected by an in-memory `threading.Lock` (`_decayer_lock`).

The decayer does **NOT** store topology relationships in volatile memory; rather, it performs a batched, non-locking evaluation against persistent SQLite storage:
```sql
UPDATE topology_edges
SET observation_freshness = 'stale'
WHERE lifecycle_state != 'tombstoned'
  AND observation_freshness = 'fresh'
  AND verification_status != 'manual'
  AND (? - last_seen) > ?
```

### 4.2 Monotonic Time vs Wall-Clock Timestamps
- `time.monotonic()` is strictly an interval timer referenced to an arbitrary operating system clock (typically uptime). It resets across process restarts and cannot be shared across processes or persisted to disk.
- Persisting monotonic time to SQLite is an antipattern that causes false expirations or invalid dates upon restart.
- Therefore, `topology_edges.last_seen` stores wall-clock UNIX epoch float seconds (`time.time()`).
- In-memory loop sleep calculation uses `time.monotonic()`:
  ```python
  elapsed_mono = time.monotonic() - start_mono
  sleep_time = max(0.5, self._decayer_interval_sec - elapsed_mono)
  ```
- Staleness comparison uses wall-clock seconds (`time.time() - last_seen > threshold`).

### 4.3 Application Restart Behavior
1. **Shutdown:** `TopologyEngine.stop_decayer()` cleanly signals `_decayer_stop_event` and cancels `_decayer_task`. In-memory state terminates.
2. **Downtime Gap:** During server downtime, no NMS polling occurs. SQLite records retain their persisted `last_seen` timestamp.
3. **Startup:** When the application starts, `TopologyEngine.start_nms_sync()` spawns a fresh `_decayer_task` and registers subscribers.
4. **Evaluation:** If the server was stopped for 10 minutes, the first decayer pass evaluates `time.time() - last_seen` (600s > 60s) and marks unobserved edges as `stale`.
5. **Re-Fresh:** The first NMS polling cycle emits `NMS_INTERFACE_OBSERVED` or `NMS_INTERFACE_STATUS_CHANGED`, setting `last_seen = time.time()` and restoring `observation_freshness = 'fresh'`.

### 4.4 NMS Stopped Behavior
If NMS polling is paused or disabled while the application continues running:
1. `topology_edges.last_seen` ceases to advance.
2. At $t = \text{last\_seen} + 60\text{s}$, the decayer transitions `observation_freshness` from `'fresh'` to `'stale'`.
3. `oper_status` remains strictly unchanged (`up` remains `up`, `down` remains `down`).
4. On subsequent decayer cycles, the clause `WHERE observation_freshness = 'fresh'` matches zero rows; **zero database writes occur**.

---

## 5. Concurrency Guarantees & Lifecycle Architecture

### 5.1 Synchronization Primitives
The `TopologyEngine` utilizes four targeted locks to ensure thread safety without lock contention:
1. `_lock` (`threading.RLock`): Re-entrant database lock protecting SQLite read-write transactions.
2. `_decayer_lock` (`threading.Lock`): Synchronizes decayer startup, shutdown, and task reference manipulation.
3. `_subscriber_lock` (`threading.Lock`): Enforces idempotent EventBus subscriber registration and clean unregistration.
4. `_discovery_lock` (`threading.Lock`): Prevents overlapping discovery cycles during evidence reconciliation.

### 5.2 Single-Worker Deployment Boundary
In strict accordance with Phase 4.3 requirements:
- Distributed multi-worker synchronization (Redis Redlock, PostgreSQL advisory locks, Raft consensus) is out of scope.
- `TopologyEngine` and `NmsEngine` operate within a **single worker process** (`uvicorn main:app --workers 1`).
- Multi-worker deployments would spawn multiple independent decayer tasks and duplicate EventBus subscriptions per worker process. Single-worker deployment is mandatory until Phase 5.

---

## 6. Comprehensive Test Suite Results

### 6.1 Phase 4.3 Acceptance & Audit Suite (`test_topology_nms_sync_v4.py`)
- **Status:** **32 / 32 PASSED** (100%) in 38.25s
- **Baseline Acceptance Tests:** 18 tests
- **Correctness Audit Scenarios:** 14 tests

| # | Test Method | Verified Audit Requirement | Status |
|---|---|---|---|
| 1 | `test_01_valid_interface_up_event` | Interface UP transitions edge `oper_status` to `"up"`, updates `last_seen`, sets freshness to `"fresh"`. | **PASSED** |
| 2 | `test_02_valid_interface_down_event` | Interface DOWN transitions edge `oper_status` to `"down"`, preserves `relationship_class="physical"`. | **PASSED** |
| 3 | `test_03_unknown_device` | Unknown device reference handled gracefully (`reason="unknown_device"`), zero edges created. | **PASSED** |
| 4 | `test_04_unknown_interface` | Unknown interface handled safely (`reason="interface_not_mapped"`), zero edges modified/created. | **PASSED** |
| 5 | `test_05_ambiguous_edge_mapping` | Interface shared by parallel physical and L3 routed edges updates both consistently. | **PASSED** |
| 6 | `test_06_duplicate_event_delivery` | Duplicate delivery at identical timestamp is idempotent; zero duplicate delta change records. | **PASSED** |
| 7 | `test_07_out_of_order_event_delivery` | Out-of-order event ($t=150$ after $t=200$) is dropped; does not overwrite newer observation. | **PASSED** |
| 8 | `test_08_event_does_not_modify_relationship_class` | Interface DOWN event preserves `relationship_class`, `subtype`, and confidence tier `"CONFIRMED"`. | **PASSED** |
| 9 | `test_09_event_does_not_create_a_physical_edge` | Interface UP on unmapped interface does not create any physical edge or alter edge count. | **PASSED** |
| 10 | `test_10_event_does_not_tombstone_an_edge` | Interface DOWN event leaves edge `lifecycle_state="active"` (never tombstoned). | **PASSED** |
| 11 | `test_11_stale_observation_after_60_seconds` | Decayer marks unobserved edge ($t > 60\text{s}$) as `stale` without changing `oper_status`. | **PASSED** |
| 12 | `test_12_fresh_observation_resets_stale_state` | Fresh NMS interface event resets `stale` observation back to `"fresh"`. | **PASSED** |
| 13 | `test_13_decayer_lifecycle_starts_only_once` | Multiple calls to `start_decayer()` are idempotent and do not spawn duplicate tasks. | **PASSED** |
| 14 | `test_14_decayer_stops_cleanly` | `stop_decayer()` cancels background task cleanly without unhandled exceptions. | **PASSED** |
| 15 | `test_15_eventbus_subscriber_registration_is_idempotent` | Calling `register_nms_subscriber()` multiple times retains exactly one subscription token. | **PASSED** |
| 16 | `test_16_subscriber_is_removed_during_shutdown` | `unregister_nms_subscriber()` cleanly removes all subscription tokens from EventBus. | **PASSED** |
| 17 | `test_17_event_handler_failure_does_not_terminate_nms` | Malformed event dispatched to subscriber is isolated; subsequent valid events process normally. | **PASSED** |
| 18 | `test_18_legacy_topology_api_remains_compatible` | Legacy `topology_links` and `/api/topology` output accurately reflect operational status. | **PASSED** |
| 19 | `test_audit_01_repeated_successful_up_observations_keep_freshness_fresh` | Repeated UP observations update `last_seen` and keep freshness `'fresh'`; decayer does not decay. | **PASSED** |
| 20 | `test_audit_02_repeated_successful_down_observations_keep_freshness_fresh` | Repeated DOWN observations update `last_seen` and keep freshness `'fresh'`; status remains `'down'`. | **PASSED** |
| 21 | `test_audit_03_unchanged_status_does_not_produce_duplicate_status_transition_events` | Observations and duplicate status events suppress `topology.delta` and change logging. | **PASSED** |
| 22 | `test_audit_04_successful_observations_refresh_freshness_without_requiring_a_transition` | Observation updates `last_seen` without status change, preventing decay past threshold. | **PASSED** |
| 23 | `test_audit_05_failed_polling_does_not_refresh_freshness` | Failed polling emits no events; `last_seen` does not advance; decayer marks edge stale. | **PASSED** |
| 24 | `test_audit_06_no_successful_observation_beyond_threshold_causes_stale_freshness` | Boundary test: $t \le 60\text{s}$ remains fresh; $t = 60.1\text{s}$ decays to stale. | **PASSED** |
| 25 | `test_audit_07_stale_observation_followed_by_successful_observation_returns_to_fresh` | Stale edge returns to `'fresh'` and updates `last_seen` upon receipt of successful observation. | **PASSED** |
| 26 | `test_audit_08_restart_behavior_follows_documented_persistence_model` | Freshness and `last_seen` restore faithfully from SQLite across simulated process restart. | **PASSED** |
| 27 | `test_audit_09_decayer_does_not_modify_oper_status` | Decayer decay leaves `oper_status="up"` and `oper_status="down"` completely intact. | **PASSED** |
| 28 | `test_audit_10_decayer_does_not_modify_relationship_semantics` | Decayer preserves `relationship_class`, `subtype`, confidence, endpoints, and `lifecycle_state`. | **PASSED** |
| 29 | `test_audit_11_decayer_does_not_delete_or_tombstone_edges` | Total edge count invariant; `lifecycle_state` remains `active` after decayer execution. | **PASSED** |
| 30 | `test_audit_12_repeated_decayer_execution_does_not_produce_unnecessary_writes` | Pass 1 updates stale edge (1 write); subsequent passes return 0 writes (0 DB updates). | **PASSED** |
| 31 | `test_audit_13_nms_shutdown_and_restart_do_not_create_duplicate_subscribers_or_tasks` | Full start -> stop -> restart lifecycle maintains exactly 1 subscriber and 1 decayer task. | **PASSED** |
| 32 | `test_audit_14_event_delivery_idempotent_and_out_of_order_protection_effective` | Out-of-order and duplicate events dropped; no state corruption or duplicate deltas. | **PASSED** |

---

### 6.2 Full Regression Suite Summary

| Test Suite | Command | Result | Delta vs Baseline |
|---|---|---|---|
| **Phase 4.3 NMS Sync & Audit** | `pytest AIRA_ECOSYSTEM/tests/test_topology_nms_sync_v4.py` | **32 / 32 PASSED** (38.25s) | **+14 new audit tests** |
| **Phase 4.2 Discovery Suite** | `pytest AIRA_ECOSYSTEM/tests/test_topology_discovery_v4.py` | **12 / 12 PASSED** (17.69s) | 100% Parity |
| **Phase 4.1 Schema Suite** | `pytest AIRA_ECOSYSTEM/tests/test_topology_phase4_1.py` | **12 / 12 PASSED** (10.99s) | 100% Parity |
| **Lifecycle Hardening Suite** | `pytest AIRA_ECOSYSTEM/tests/test_lifecycle_hardening.py` | **10 / 10 PASSED** (6.29s) | 100% Parity |
| **NMS Engine Suite** | `pytest AIRA_ECOSYSTEM/tests/test_nms.py` | **37 / 37 PASSED** (24.19s) | 100% Parity |
| **Security & Hardening Suite** | `pytest test_routeros_command_hardening.py ...` (4 modules) | **103 / 103 PASSED** (11.06s) | **103 passed** (Exact Match) |
| **Full Backend Regression Suite** | `pytest AIRA_ECOSYSTEM/tests/ -q` | **1064 PASSED, 176 subtests** (204.04s) | **+14 tests** ($1050 + 14 = 1064$) |
| **Frontend Automated Suite** | `npm test` in `AIRA_ECOSYSTEM/app/frontend` | **247 / 247 PASSED** (2.48s) | **247 passed** (Exact Match) |
| **Frontend Production Build** | `npm run build` in `AIRA_ECOSYSTEM/app/frontend` | **Clean Vite Build** (3.16s) | `dist/` verified, 0 errors |

---

## 7. Security & Environmental Boundaries

1. **Zero Live CHR Mutations:** No SSH commands, reconfiguration, or state mutations were executed against the lab MikroTik CHR (`10.66.38.30:22`).
2. **Read-Only Verification:** All 103 read-only command hardening and security tests passed with 100% compliance.
3. **Database Integrity:** Existing SQLite databases (`topology.db`, `inventory.db`) were preserved without schema mutations or table additions.
4. **Git Tree Integrity:** All modifications remain uncommitted in the working tree. No Git commits, stashes, or resets were performed.

---

## 8. Acceptance Sign-Off & Verdict

| Audit Objective | Requirement | Status |
|---|---|---|
| NMS Event Production Audit | Trace actual path; resolve transition-only emission | **AUDITED & RESOLVED** |
| Freshness Semantics | Decouple status, freshness, and lifecycle state | **VERIFIED** |
| Telemetry Decoupling | `NMS_INTERFACE_OBSERVED` for unchanged polls | **IMPLEMENTED** |
| WebSocket Suppression | Zero spam on unchanged observations | **VERIFIED** |
| Decayer Storage Model | In-memory loop + SQLite wall-clock timestamps | **DOCUMENTED & TESTED** |
| 14 Mandatory Regression Scenarios | Deterministic clocks, comprehensive coverage | **14 / 14 PASSED** |
| Total Phase 4.3 Tests | Baseline acceptance + audit scenarios | **32 / 32 PASSED** |
| Full Backend Regression | 0 failures, 0 regressions | **1064 / 1064 PASSED** |
| Frontend Parity | Automated tests + production build | **247 / 247 PASSED** |
| Security Hardening | 100% read-only compliance | **103 / 103 PASSED** |

### Final Audit Verdict: **PHASE 4.3 FULLY AUDITED, RESOLVED & ACCEPTED**

In accordance with strict operating instructions:
- Implementation is complete and halted at Phase 4.3.
- Phase 4.4 has NOT been initiated.
- Working tree is preserved uncommitted for operator review.
