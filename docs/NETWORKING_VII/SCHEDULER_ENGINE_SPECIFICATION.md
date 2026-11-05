# AIRA OS — NETWORKING VII
# OPERATIONAL SCHEDULER ENGINE SPECIFICATION (WP 7.4)

**Module:** `AIRA_ECOSYSTEM/core/operations/scheduler.py`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Database Tables:** `operational_jobs`, `operational_job_runs`  
**Phase:** Phase E — Operational Scheduler Engine  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Strict Architectural Decoupling

A critical architectural distinction is enforced in AIRA OS:

```
+-------------------------------------------------------------+
|        NMS Telemetry Polling (core/nms/scheduler.py)        |
|  - High frequency: 15s to 300s                             |
|  - Directly connects to MikroTik via SSH/SNMP               |
|  - Adaptive backoff, circuit breaking, fast recovery        |
+-------------------------------------------------------------+
                            VS
+-------------------------------------------------------------+
|     Operational Job Scheduler (core/operations/scheduler.py)|
|  - Low frequency: Hourly, Daily, Weekly, Cron               |
|  - NEVER polls hardware directly                            |
|  - Evaluates cached evidence from UnifiedEvidenceService    |
|  - Timezone-aware (Asia/Jakarta), persistent in SQLite      |
+-------------------------------------------------------------+
```

---

## 2. Supported Schedule Formats & Timezones

- **Default Timezone:** `Asia/Jakarta` (WIB, UTC+07:00). All cron and wall-clock triggers match local business hours in Indonesia.
- **Storage Standard:** All timestamps (`next_due_at`, `last_run_at`, `started_at`, `completed_at`) are saved strictly in UTC ISO-8601.
- **Supported Schedule Types:**
  1. `INTERVAL`: Specified in seconds (e.g. `3600` for every hour).
  2. `DAILY`: Specified as local `HH:MM` (e.g. `08:00` WIB).
  3. `WEEKLY`: Specified as local `D HH:MM` (e.g. `0 08:00` for Monday at 08:00 WIB).
  4. `CRON`: Standard 5-field cron syntax (`minute hour day month day-of-week`).

---

## 3. Missed Execution Handling (Downtime Recovery)

When AIRA OS boots after downtime, the scheduler scans for jobs where `next_due_at <= now()`:
- `RUN_IMMEDIATELY` (default): Runs the overdue job immediately with trigger `MISSED_RECOVERY`, then sets `next_due_at` to the next scheduled interval.
- `SKIP`: Discards the missed run and advances `next_due_at` to the next upcoming slot.
- `RESCHEDULE`: Postpones execution to the next maintenance window.

---

## 4. Built-in Operational Templates

1. `HEALTH_AUDIT`: Daily comprehensive health review of all devices and transit paths.
2. `CAPACITY_FORECAST`: Weekly capacity saturation analysis projecting 30-day horizons.
3. `CERT_CHECK`: Audit of TLS/SSH certificates with warnings 30, 14, and 3 days prior to expiration.
4. `ROUTE_AUDIT`: Weekly route table stability and flap churn analysis.
