# AIRA OS — AUTOMATION ENGINE SPECIFICATION
## Understandable Natural Language Automations & Hybrid Triggers

**Version:** 1.0.0  
**Status:** Canonical Automation Specification  

---

## 1. Overview and Design Philosophy

AIRA OS replaces the legacy 33-line scheduler stub with an **AI-native automation engine**. 

Engineers configure repetitive tasks either through natural language or a clean interactive builder.

```
Engineer: "Periksa seluruh router setiap 5 menit. Kalau ada yang offline, beri tahu saya dan buat laporan."
                                 │
                                 ▼
                     AIRA AUTOMATION COMPILER
┌────────────────────────────────────────────────────────────────────────┐
│  Name:             Router Health & Offline Alert                       │
│  Trigger:          Interval (Every 5 minutes / 300s)                   │
│  Action:           Check Device Connectivity (`check_connectivity`)   │
│  On Condition:     If unreachable -> `notify_device_offline`           │
│  Target Resources: All Routers (Tag: `router`)                         │
│  Approval Gate:    Category A (Auto-execute, non-disruptive)           │
│  Notification:     In-app alert & critical toast                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Trigger Models

### 2.1 Interval-Based Triggers (`INTERVAL`)
- **Frequencies Supported:**
  - Preset intervals: 1 minute (`60s`), 5 minutes (`300s`), 15 minutes (`900s`), 1 hour (`3600s`), 1 day (`86400s`), 1 week.
  - Standard 5-field cron expressions for wall-clock alignment.
- **Timezone Awareness:**
  - Standard timezone: `Asia/Jakarta` (WIB, UTC+7).
- **Restart Resilience:**
  - Next due timestamp (`next_run_at`) is serialized to SQLite. If AIRA restarts, missed jobs execute based on their configured strategy (`RUN_IMMEDIATELY`).

### 2.2 Event-Driven Triggers (`EVENT`)
Subscribed directly to the AIRA Event Bus (`core/events.py`):
1. **`device_offline`:** Triggered when consecutive reachability or SNMP polls fail.
2. **`device_online`:** Triggered when an unreachable device recovers.
3. **`interface_status_changed`:** Triggered on link flap (down -> up or up -> down).
4. **`cpu_threshold_exceeded`:** Triggered when device CPU exceeds configured warning threshold (e.g. > 85%).
5. **`memory_threshold_exceeded`:** Triggered on memory exhaustion.
6. **`new_device_discovered`:** Triggered when recursive discovery detects a new neighbor MAC or IP.
7. **`monitoring_failed`:** Triggered on SNMP timeout or credential error.
8. **`security_alert`:** Triggered on unauthorized access attempt or brute force lockout.

---

## 3. Action Catalog

| Action Name | Description | Autonomy Risk | Required Parameters |
|---|---|---|---|
| `check_connectivity` | Ping / port reachability sweep | Category A | `devices` (optional) |
| `collect_metrics` | Live SNMP / RouterOS counter pull | Category A | `devices` (optional) |
| `generate_health_report`| Dynamic health scoring compilation | Category A | `format` (md/pdf/docx) |
| `notify_device_offline` | High-priority toast & email alert | Category A | `severity`, `channels` |
| `discover_neighbors` | Recursive LLDP / MNDP scan | Category A | `seed_device`, `depth` |
| `backup_config` | Export running configuration snapshot | Category A | `devices`, `hide_sensitive` |
| `analyze_config_changes`| Compare running configuration to baseline | Category A | `devices` |
| `generate_topology_report`| Graph and connection inventory dump | Category A | `include_inferred` |
| `run_diagnostic` | Ping sweep, traceroute hops | Category A | `target_host`, `test_type` |
| `execute_configuration_workflow` | Mutating config deployment with rollback | Category B | `target_device`, `commands` |

---

## 4. Execution Governance & Idempotency

- **Duplicate Prevention:**
  - Concurrency locks (`_running_jobs` set) ensure that long-running jobs are never triggered simultaneously if the previous iteration has not yet finished.
- **Approval Gate:**
  - If `approval_required` is enabled or the action is Category B, the execution is placed in `APPROVAL_PENDING` state and dispatched to the Centralized Approval Engine. It is not applied to live hardware until approved.
- **Audit Logging:**
  - Every execution records: `execution_id`, `job_id`, `started_at`, `completed_at`, `duration_ms`, `status` (`SUCCESS`, `FAILED`, `APPROVAL_PENDING`), and detailed JSON execution summary.
