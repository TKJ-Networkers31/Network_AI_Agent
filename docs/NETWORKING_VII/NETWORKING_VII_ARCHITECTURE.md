# AIRA OS — NETWORKING VII
# PROACTIVE NETWORK OPERATIONS INTELLIGENCE
## System Architecture, Domain Specifications & Technical Blueprints (WP 7.0)

**Document Version:** 1.0.0  
**Phase:** Phase A — Architecture & Domain Audit  
**Work Package:** WP 7.0  
**Status:** AUTHORITATIVE SPECIFICATION  
**Target Environment:** Windows 10/11, ThinkPad X270 (Intel Core i7-7500U @ 2.70GHz, 2 Cores / 4 Threads, 8 GB RAM, CPU-Only)  
**Primary Timezone:** `Asia/Jakarta` (WIB, UTC+07:00) | **Internal Storage:** UTC ISO-8601  
**Security Posture:** 100% Read-Only Network Inspection (Zero Device Mutation Policy)

---

## 1. Executive Summary & Vision

Networking VI successfully transformed AIRA into a verified, evidence-driven **Network Intelligence Core** capable of multi-device topology understanding, cross-device path reasoning, deterministic anomaly detection, and automated root cause analysis (RCA).

**Networking VII (Proactive Network Operations Intelligence)** advances AIRA from an *investigative and diagnostic* assistant into a *proactive operations partner*. It equips network operators, NOC engineers, and administrators with forward-looking operational intelligence:

1. **Predictive Operations (WP 7.1):** Forecasting saturation horizons, error growth trends, and capacity bottlenecks using transparent, explainable statistics (Rolling Median, MAD, EWMA, Linear Trend Regressions) with strict epistemic limits (no fortune-telling, no synthetic data replacement for missing samples).
2. **Change Impact Intelligence (WP 7.2):** Pre-change blast-radius and service degradation simulation in memory on cloned knowledge graphs prior to maintenance execution, maintaining zero mutation of real devices.
3. **Service Dependency Intelligence (WP 7.3):** Bridging layer-3/layer-2 network infrastructure to business services, applications, and endpoints, evaluating high-availability redundancy and downstream service blast radiuses.
4. **Operational Scheduler Engine (WP 7.4):** A persistent, timezone-aware (`Asia/Jakarta`) operational job scheduler for maintenance workflows, periodic capacity reviews, and compliance checks, strictly decoupled from the NMS device polling scheduler.
5. **Calendar Integration (WP 7.5):** Bi-directional maintenance window planning supporting local-only schedules, RFC 5545 `.ics` export/import, and Google Calendar OAuth 2.0 integration.
6. **Proactive Incident Intelligence (WP 7.6):** Structured incident lifecycle tracking that bridges predictive alerts to proactive maintenance tasks before end-user degradation occurs.
7. **Controlled Notification Engine (WP 7.7):** Intelligent alert distribution with strict deduplication, quiet hours (`Asia/Jakarta`), severity-based overrides, and WebSocket delivery.
8. **Automated Operational Reporting (WP 7.8):** Deterministic daily, weekly, and monthly health, capacity, and change audit reporting with Markdown and structured export.
9. **Unified Operations Center (WP 7.9 & 7.10):** A comprehensive, responsive React UI providing single-pane-of-glass proactive operational management.

---

## 2. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph UI["AIRA Frontend (React / Vite)"]
        OpsCenter["Operations Center (WP 7.10)"]
        subgraph Views["Operational Views"]
            V_Overview["Operations Overview"]
            V_Predictive["Predictive Insights & Trends"]
            V_Change["Change Impact Simulator"]
            V_Services["Service Dependency Catalog"]
            V_Scheduler["Job Scheduler Management"]
            V_Calendar["Calendar & Maintenance Windows"]
            V_Incidents["Proactive Incidents Board"]
            V_Reports["Operational Report Center"]
        end
        OpsCenter --> Views
    end

    subgraph API["FastAPI Operations Gateway (/api/operations/*) (WP 7.9)"]
        RouterPredictive["/predictive"]
        RouterChange["/change-impact"]
        RouterServices["/services"]
        RouterScheduler["/scheduler"]
        RouterCalendar["/calendar"]
        RouterIncidents["/incidents"]
        RouterNotifications["/notifications"]
        RouterReports["/reports"]
        WSBridge["WebSocket Bridge (Realtime Updates)"]
    end

    UI <-->|REST & WebSocket| API

    subgraph CoreOps["AIRA Operations Subsystem (core/operations/)"]
        PredictiveEngine["PredictiveOperationsEngine\n(WP 7.1)"]
        ChangeEngine["ChangeImpactEngine\n(WP 7.2)"]
        ServiceEngine["ServiceIntelligenceEngine\n(WP 7.3)"]
        SchedulerEngine["OperationalSchedulerEngine\n(WP 7.4)"]
        CalendarEngine["CalendarManager & Providers\n(WP 7.5)"]
        IncidentEngine["ProactiveIncidentEngine\n(WP 7.6)"]
        NotificationHub["NotificationHub\n(WP 7.7)"]
        ReportingEngine["OperationalReportingEngine\n(WP 7.8)"]
    end

    API --> CoreOps

    subgraph EventSystem["Event & Communication Fabric"]
        EventBus["Internal EventBus (core/events.py)\nThread-Safe Pub/Sub with Correlation IDs"]
    end

    CoreOps <--> EventBus
    EventBus --> WSBridge

    subgraph NetIntel["Networking VI Foundation (core/network_intelligence/) [READ-ONLY]"]
        EvidenceSvc["UnifiedEvidenceService\n(Cached Evidence Bundles)"]
        KnowledgeGraph["NetworkKnowledgeGraph\n(In-Memory Topology & Relationships)"]
        BaseEngine["BaselineEngine\n(Median, MAD, EWMA Baselines)"]
        AnomEngine["AnomalyEngine\n(Z-Score & Domain Anomaly Detection)"]
        SimCore["FailureSimulator\n(In-Memory Failure Propagation)"]
        ImpAnalyzer["ImpactAnalyzer\n(Graph Blast-Radius Analyzer)"]
        PathEngine["NetworkPathIntelligenceEngine\n(L3/L2 Path Traversal)"]
    end

    PredictiveEngine -->|Reuses Baselines & Telemetry| EvidenceSvc
    PredictiveEngine -->|Calculates Horizons| BaseEngine
    ChangeEngine -->|Clones Graph in Memory| KnowledgeGraph
    ChangeEngine -->|Reuses Simulation Primitives| SimCore
    ChangeEngine -->|Traverses Dependencies| ImpAnalyzer
    ServiceEngine -->|Maps to Graph Nodes| KnowledgeGraph
    SchedulerEngine -->|Reads Cached Bundles (No Device Poll)| EvidenceSvc
    IncidentEngine -->|Ingests Anomalies & Forecasts| AnomEngine
    NotificationHub -->|Dispatches Alerts| EventBus

    subgraph NMS["Networking V Polling Subsystem (core/nms/) [ISOLATED]"]
        NmsScheduler["HardenedNmsScheduler\n(SNMP/SSH Polling Loop)"]
        NmsStore["MetricsStore / SQLite"]
    end

    EvidenceSvc -->|Reads Historical Samples| NmsStore
    NmsScheduler -->|Populates| NmsStore

    subgraph Storage["Persistent Storage Layer (SQLite WAL Mode)"]
        TopologyDB[("topology.db\nServices, Jobs, Runs, Incidents,\nWindows, Notifications, Reports")]
    end

    CoreOps <--> Storage
```

---

## 3. Strict Boundary Rules & System Invariants

### 3.1. Zero-Mutation Network Safety Guarantee
- AIRA is an operations *advisor*, *simulator*, and *early-warning engine*.
- **Under NO circumstances** shall any component of Networking VII execute state-altering configuration commands on live network devices (no `/ip route add`, no `set disabled=yes`, no interface shutdowns, no commit operations).
- All inspection commands routed through `ConnectionManager` must pass `validate_readonly_command()`.
- Pre-change simulations (WP 7.2) operate exclusively on deep-cloned in-memory graph objects (`copy.deepcopy(knowledge_graph)`). The actual runtime database and real-device interfaces are untouched.

### 3.2. Strict Scheduler Decoupling
To avoid CPU thrashing, locks, and starvation on the ThinkPad X270 host:
- **`HardenedNmsScheduler` (core/nms/scheduler.py):** Dedicated solely to recurring telemetry collection from hardware via SSH/SNMP (intervals: 15s to 300s).
- **`OperationalSchedulerEngine` (core/operations/scheduler.py):** Dedicated solely to operational maintenance jobs, automated report generation, certificate audits, and calendar synchronizations.
- **Invariant:** The `OperationalSchedulerEngine` **NEVER** connects directly to network devices. It consumes cached evidence from `UnifiedEvidenceService` or queries `MetricsStore`.

### 3.3. Resource Budget & Thin-Client Constraints
The target host is a dual-core Intel Core i7-7500U with 8 GB RAM and no dedicated GPU.
- **CPU Budget:** Background operational jobs and trend calculations must never exceed 25% sustained CPU load.
- **Memory Footprint:** In-memory graph clones for change simulations must be garbage-collected immediately upon scenario completion. Peak delta memory for any simulation < 15 MB.
- **Deterministic Math:** Pure Python / NumPy statistical formulations (rolling medians, MAD, linear trend regressions). No heavy local LLM invocation in time-critical operational loops.
- **Offline Resiliency:** All core engines (Predictive, Change Impact, Scheduler, Reports) must run with 100% functionality when the local Ollama LLM is offline or unreachable.

### 3.4. Epistemic Integrity & Honest Forecasting
- Predictions are **projections**, not prophecies. Every predictive output must declare:
  - `projection_basis`: Exact historical window examined (e.g. `24h`, `7d`).
  - `confidence_score`: 0.0 to 1.0 based on sample count, $R^2$, and variance.
  - `epistemic_limitations`: Explicit assumptions (e.g. *"Assumes linear traffic growth; sudden promotions or DDoS attacks not modeled"*).
- **Missing Telemetry:** If telemetry for a time bucket is missing, it must remain `None`. It is strictly forbidden to treat missing telemetry as `0.0`.
- If sample count < minimum threshold ($N < 10$), the engine must emit status `INSUFFICIENT_DATA` rather than guessing.

---

## 4. Subsystem Specifications

### 4.1. Work Package 7.1 — Predictive Operations Engine
- **Module:** `AIRA_ECOSYSTEM/core/operations/predictive_engine.py`
- **Core Responsibilities:**
  1. **Multi-Window Time Series Analysis:** Analyze historical metrics across 5 canonical windows: `1h` (short-term surge), `6h` (daily cycle), `24h` (diurnal baseline), `7d` (weekly rhythm), `30d` (long-term trend).
  2. **Monitored Operational Signals:**
     - *Bandwidth Saturation:* Rx/Tx Mbps vs interface capacity, projecting time-to-80% and time-to-95% saturation.
     - *Error Rate Acceleration:* Delta CRC errors, packet drops, carrier resets over time.
     - *Device Resource Exhaustion:* CPU load trend and memory consumption growth towards critical thresholds.
     - *Routing Instability:* Route churn rate (withdrawals/re-announcements) and prefix count stability.
     - *Link Quality Degradation:* Latency jitter and packet loss creep on critical transit paths.
  3. **Trend Fitting:** Robust Theil-Sen estimator or standard linear least-squares regression with outlier clipping via MAD.
  4. **Risk Classification:**
     - `INFO`: Normal variation, healthy capacity headroom (> 30 days to warning threshold).
     - `WATCH`: Mild upward trend, projected warning threshold within 7 to 30 days.
     - `WARNING`: Rapid trend, projected saturation within 24 to 168 hours (1 to 7 days).
     - `CRITICAL`: Urgent acceleration, projected threshold breach in < 24 hours or currently > 90%.
     - `UNKNOWN`: Insufficient samples, baseline invalidated, or non-stationary signal.

### 4.2. Work Package 7.2 — Network Change Impact Intelligence
- **Module:** `AIRA_ECOSYSTEM/core/operations/change_impact_engine.py`
- **Core Responsibilities:**
  1. **Pre-Change Scenario Modeling:**
     - Interface shutdown / administrative down.
     - Transit link or WAN disconnection.
     - Static route removal or BGP/OSPF peer teardown.
     - VLAN re-tagging or trunk pruning.
     - Router maintenance / reboot.
  2. **In-Memory Analytical Execution:**
     - Clones active `NetworkKnowledgeGraph`.
     - Applies hypothetical change mutation to the clone.
     - Executes `PathIntelligenceEngine` and `ImpactAnalyzer` graph traversals on the cloned graph.
  3. **Blast-Radius Assessment:**
     - *Directly Impacted:* Endpoints, subnets, and neighbor devices whose next-hop is immediately severed.
     - *Indirectly Impacted:* Upstream/downstream services whose transit path is broken or forced onto a suboptimal/degraded backup link.
     - *Redundancy Loss:* Segments that lose high-availability (HA) redundancy and become single points of failure (SPOF).
     - *Bandwidth Impact:* Shifts in traffic volume to secondary links with projected over-utilization risks.
  4. **Output Contract:** Canonical `ChangeImpactReport` with deterministic severity score, mitigation recommendations, and rollback checklists.

### 4.3. Work Package 7.3 — Service Dependency Intelligence
- **Module:** `AIRA_ECOSYSTEM/core/operations/service_intelligence.py`
- **Core Responsibilities:**
  1. **Service Entity Modeling:** Defines business-level services (e.g. `ERP System`, `VoIP Gateway`, `Guest Wi-Fi`, `Core Banking API`, `Internet Breakout`).
  2. **Multi-Layer Dependency Graph Mapping:**
     $$\text{Business Service} \longrightarrow \text{Endpoints (IP:Port)} \longrightarrow \text{Subnets/VLANs} \longrightarrow \text{Transit Paths} \longrightarrow \text{Devices / Interfaces}$$
  3. **Criticality Tiers:** `TIER_1_MISSION_CRITICAL`, `TIER_2_BUSINESS_OPERATIONAL`, `TIER_3_OFFICE_PRODUCTIVITY`, `TIER_4_DEVELOPMENT_TEST`.
  4. **High-Availability (HA) & Health Evaluation:**
     - Calculates aggregate service health score ($0 - 100$).
     - Evaluates path redundancy (Active-Active, Active-Passive, None/SPOF).
     - Flags at-risk services whenever underlying network interfaces or links show predictive warning signals.

### 4.4. Work Package 7.4 — Operational Scheduler Engine
- **Module:** `AIRA_ECOSYSTEM/core/operations/scheduler.py`
- **Core Responsibilities:**
  1. **Persistent SQLite Job Store:** Jobs defined in `operational_jobs` table and historical executions logged in `operational_job_runs`.
  2. **Scheduling Patterns:**
     - Interval: Run every $N$ seconds/minutes/hours.
     - Cron: Standard 5-field cron syntax (`minute hour day month day-of-week`).
     - Daily / Weekly / Monthly presets aligned to specific time of day in `Asia/Jakarta`.
  3. **Restart Recovery & Missed Execution Handling:**
     - `RUN_IMMEDIATELY`: If scheduled while AIRA was offline, run as soon as AIRA boots up.
     - `SKIP`: Drop the missed run and schedule for the next natural recurrence.
     - `RESCHEDULE`: Postpone to the next available maintenance window.
  4. **Built-in Operational Templates:**
     - `DAILY_NETWORK_HEALTH_AUDIT`: Daily aggregate audit of all devices and paths.
     - `WEEKLY_CAPACITY_FORECAST`: Trend projection for all core transit interfaces.
     - `CERTIFICATE_AND_CREDENTIAL_CHECK`: Warn 30, 14, and 3 days before TLS/SSH certificate expirations.
     - `ROUTE_STABILITY_AUDIT`: Weekly route flap and churn audit.
     - `CONFIG_BACKUP_VERIFICATION`: Verifies backup freshness without mutating devices.

### 4.5. Work Package 7.5 — External Calendar Integration
- **Module:** `AIRA_ECOSYSTEM/core/operations/calendar/`
- **Core Responsibilities:**
  1. **Provider Abstraction (`CalendarProvider`):**
     - `LocalCalendarProvider`: Pure SQLite storage for air-gapped / offline environments.
     - `IcsCalendarProvider`: RFC 5545 compliant `.ics` import and export for Outlook, Apple Calendar, and Thunderbird.
     - `GoogleCalendarProvider`: Google Calendar API v3 integration via OAuth 2.0 with token refresh and scopes strictly limited to calendar events.
  2. **Maintenance Window Synchronization:**
     - Reads planned network maintenance windows from external calendar.
     - Automatically flags corresponding network devices as `IN_MAINTENANCE_WINDOW` during scheduled periods.
     - Suppresses non-critical alerts and excludes maintenance intervals from baseline calculations.

### 4.6. Work Package 7.6 & 7.7 — Incident & Notification Hub
- **Modules:** `AIRA_ECOSYSTEM/core/operations/incident_engine.py`, `AIRA_ECOSYSTEM/core/operations/notification_hub.py`
- **Core Responsibilities:**
  1. **Proactive Incident Management:**
     - Creates proactive incidents from `WARNING` or `CRITICAL` predictive signals before customer impact occurs.
     - State machine: `DETECTED` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `INVESTIGATING` $\rightarrow$ `MITIGATED` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED`.
     - Links incident to affected services, root cause hypotheses, and recommended preventive actions.
  2. **Controlled Notification Delivery:**
     - *Deduplication:* Grouping identical alerts within a configurable sliding window (default 15 minutes).
     - *Cooldown:* Enforcing backoff intervals to prevent alert fatigue.
     - *Quiet Hours:* Configurable quiet hours in `Asia/Jakarta` (e.g. 22:00 – 06:00 WIB) during which low/medium severity notifications are queued, while `CRITICAL` emergency alerts immediately bypass quiet hours.
     - *Delivery Channels:* In-app notification center, real-time WebSocket broadcast, and extensible webhook stubs.

### 4.7. Work Package 7.8 — Operational Reporting Engine
- **Module:** `AIRA_ECOSYSTEM/core/operations/reporting_engine.py`
- **Core Responsibilities:**
  1. **Deterministic Aggregation:** Summarizes availability, MTTR, top saturated interfaces, route churn, active incidents, and maintenance completions over specified periods (Daily, Weekly, Monthly, Custom Range).
  2. **Export Formats:**
     - GitHub-Flavored Markdown (rendered cleanly in chat and UI).
     - Structured JSON (for machine-to-machine integrations).
     - Standalone Printable HTML / PDF.

---

## 5. Database Schema & Persistence Design

The operational subsystem utilizes the existing SQLite database `AIRA_ECOSYSTEM/database/topology.db` operating in WAL mode. Seven new tables are defined with strict foreign keys and index optimizations:

```sql
-- 1. Business Services Catalog
CREATE TABLE IF NOT EXISTS operational_services (
    service_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    criticality TEXT NOT NULL CHECK(criticality IN ('TIER_1_MISSION_CRITICAL', 'TIER_2_BUSINESS_OPERATIONAL', 'TIER_3_OFFICE_PRODUCTIVITY', 'TIER_4_DEVELOPMENT_TEST')),
    owner_team TEXT,
    health_score REAL DEFAULT 100.0,
    status TEXT NOT NULL DEFAULT 'HEALTHY' CHECK(status IN ('HEALTHY', 'DEGRADED', 'AT_RISK', 'DOWN', 'UNKNOWN')),
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Service Endpoints & Network Bindings
CREATE TABLE IF NOT EXISTS operational_service_endpoints (
    endpoint_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL REFERENCES operational_services(service_id) ON DELETE CASCADE,
    endpoint_type TEXT NOT NULL CHECK(endpoint_type IN ('IP_PORT', 'SUBNET', 'VLAN', 'URL', 'HOSTNAME')),
    endpoint_value TEXT NOT NULL,
    target_device_id TEXT,
    target_interface TEXT,
    is_primary INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 3. Operational Scheduled Jobs
CREATE TABLE IF NOT EXISTS operational_jobs (
    job_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    description TEXT,
    schedule_type TEXT NOT NULL CHECK(schedule_type IN ('CRON', 'INTERVAL', 'DAILY', 'WEEKLY', 'MONTHLY')),
    schedule_expression TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    missed_strategy TEXT NOT NULL DEFAULT 'RUN_IMMEDIATELY' CHECK(missed_strategy IN ('RUN_IMMEDIATELY', 'SKIP', 'RESCHEDULE')),
    parameters_json TEXT DEFAULT '{}',
    last_run_at TEXT,
    last_status TEXT,
    next_due_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 4. Operational Job Run History
CREATE TABLE IF NOT EXISTS operational_job_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES operational_jobs(job_id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL CHECK(trigger_type IN ('SCHEDULED', 'MANUAL', 'MISSED_RECOVERY')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCESS', 'WARNING', 'FAILED', 'SKIPPED')),
    duration_ms INTEGER,
    result_summary TEXT,
    result_data_json TEXT,
    error_message TEXT
);

-- 5. Maintenance Windows & Calendar Events
CREATE TABLE IF NOT EXISTS operational_maintenance_windows (
    window_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    source_provider TEXT NOT NULL DEFAULT 'LOCAL' CHECK(source_provider IN ('LOCAL', 'GOOGLE', 'ICS')),
    external_event_id TEXT,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('DEVICE', 'SERVICE', 'INTERFACE', 'GLOBAL')),
    target_entities_json TEXT NOT NULL DEFAULT '[]',
    start_time_utc TEXT NOT NULL,
    end_time_utc TEXT NOT NULL,
    start_time_local TEXT NOT NULL,
    end_time_local TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    suppress_alerts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 6. Proactive Operational Incidents
CREATE TABLE IF NOT EXISTS operational_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    state TEXT NOT NULL DEFAULT 'DETECTED' CHECK(state IN ('DETECTED', 'ACKNOWLEDGED', 'INVESTIGATING', 'MITIGATED', 'RESOLVED', 'CLOSED')),
    source_engine TEXT NOT NULL CHECK(source_engine IN ('PREDICTIVE', 'ANOMALY', 'CHANGE_SIMULATION', 'MANUAL')),
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    affected_devices_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    root_cause_analysis TEXT,
    remediation_plan TEXT,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

-- 7. Operational Notifications Log
CREATE TABLE IF NOT EXISTS operational_notifications (
    notification_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'SENT' CHECK(delivery_status IN ('SENT', 'QUEUED_QUIET_HOURS', 'SUPPRESSED_COOLDOWN')),
    target_channels_json TEXT NOT NULL DEFAULT '["IN_APP", "WEBSOCKET"]',
    metadata_json TEXT DEFAULT '{}',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_op_jobs_next_due ON operational_jobs(is_enabled, next_due_at);
CREATE INDEX IF NOT EXISTS idx_op_runs_job_id ON operational_job_runs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_maint_times ON operational_maintenance_windows(start_time_utc, end_time_utc, status);
CREATE INDEX IF NOT EXISTS idx_op_incidents_state ON operational_incidents(state, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_notif_dedup ON operational_notifications(dedup_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_notif_read ON operational_notifications(is_read, created_at DESC);
```

---

## 6. Timezone Architecture & Handling

- **Internal Storage Standard:** All timestamps stored in database tables, event payloads, and API data contracts are **strictly UTC in ISO-8601 format** (e.g. `2026-11-04T02:45:00Z`).
- **Operational Timezone:** Default timezone for user display, cron scheduling, maintenance windows, and quiet hours evaluation is **`Asia/Jakarta` (WIB, UTC+07:00)**.
- **Conversion Safety:** Uses Python `zoneinfo.ZoneInfo("Asia/Jakarta")` (standard library in Python 3.9+). No unhandled timezone ambiguity or local time drifting.
- **Quiet Hours Logic:**
  - Evaluated against local wall-clock time in `Asia/Jakarta`.
  - Default: `22:00` to `06:00` WIB.
  - Notifications categorized as `INFO`, `LOW`, `MEDIUM` arriving during quiet hours are marked `QUEUED_QUIET_HOURS` and held until `06:00` WIB.
  - Notifications categorized as `HIGH` or `CRITICAL` immediately bypass quiet hours and are dispatched in real-time.

---

## 7. Security & Secret Protection

- **Google OAuth 2.0 Credentials:**
  - Client secrets and refresh tokens are stored in environment variables (`AIRA_GOOGLE_CLIENT_ID`, `AIRA_GOOGLE_CLIENT_SECRET`, `AIRA_GOOGLE_REFRESH_TOKEN`) or an encrypted local credential store.
  - Tokens are never exposed to the frontend or logged in plain text.
  - State tokens with cryptographic nonces (`secrets.token_urlsafe(32)`) validate OAuth callback flows to prevent CSRF.
- **Zero Live Network Writes:**
  - Live device SSH/API credentials remain protected inside `ConnectionManager`.
  - The operations subsystem possesses zero write permissions to any network device.
