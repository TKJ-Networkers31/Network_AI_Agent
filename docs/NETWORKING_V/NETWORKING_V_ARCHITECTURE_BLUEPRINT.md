# AIRA OS — NETWORKING V: FULL NMS ARCHITECTURE BLUEPRINT
## Comprehensive System Blueprint for Proactive Network Management & Operational Observability

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target Environment:** Local-First AI Network Engineering Assistant (Windows, Intel i7-7500U, 8 GB RAM)  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY` (Non-Mutating)

---

## 1. Executive Mission & Strategic Context

AIRA OS Networking IV established a mathematically rigorous, tamper-proof foundation for network topology visualization, historical topology graph snapshots, and multi-device route analytics. However, Networking IV operates primarily on an **on-demand or reactive discovery model**.

**Networking V: FULL NETWORK MANAGEMENT SYSTEM (NMS)** transforms AIRA OS into a **continuous, proactive, resource-bounded operational observability platform**. It unites:
1. **Capability-based telemetry polling** (ICMP ping, SNMP v2c/v3, persistent RouterOS SSH, and agentless Linux telemetry).
2. **High-frequency interface and hardware resource monitoring** with counter-wraparound safety and discontinuity detection.
3. **Multi-tier time-series metrics pipeline** natively embedded in SQLite WAL with automated rollup aggregation.
4. **Topology-aware alert correlation & root-cause suppression**, ensuring an upstream transit link failure does not trigger downstream alarm storms across dozens of dependent switches and hosts.
5. **Seamless bidirectional integration with Networking III/IV intelligence**, empowering Akane and the AutoOrchestrator to cross-reference real-time telemetry with historical snapshots and control-plane route dependencies.

---

## 2. Preservation & Reuse of Existing Architecture

To prevent architectural bloat and parallel duplicate implementations, Networking V strictly preserves and extends existing subsystems:

```
+---------------------------------------------------------------------------------------------------+
|                                  AIRA OS EXISTING SUBSYSTEMS                                       |
+---------------------------------------------------------------------------------------------------+
|  [InventoryStore]       Canonical device inventory (devices.db, CanonicalDevice, credentials)    |
|  [ConnectionManager]    Managed SSH connection pool with persistent session reuse & locking      |
|  [UnifiedCommandExec]   Strict read-only allowlist validation (validate_readonly_command)         |
|  [TopologyEngine]       Canonical graph, 4-layer semantics, immutable snapshots (topology.db)    |
|  [RouteAnalytics]       UnifiedRouteParser, LPM evaluation, RouteDependencyAnalyzer, blast-radius |
|  [AutoOrchestrator]     MultiDeviceEvidenceBundle, single-pass diagnosis, DIO InteractionPlans    |
|  [EventBus]             In-process publish/subscribe (EventNames, correlation_id, contextvars)    |
|  [WebSocket Bridge]     Real-time frontend state push (/api/ws_bridge.py, useAiraSocketPool)      |
|  [NmsEngine (v1)]       Existing SQLite schema (nms_device_profiles, nms_settings, etc.)          |
|  [MetricsService]       NmsHistoricalMetricsService, downsampling, anomaly detection             |
+---------------------------------------------------------------------------------------------------+
```

### Architectural Guarantees:
- **No Parallel Inventory:** Devices are sourced exclusively from [`InventoryStore`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/inventory_store.py) and registered as [`CanonicalDevice`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/canonical_network.py).
- **No Duplicate SSH Sessions:** Reuses [`ConnectionManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/agents/akane/connection_manager.py) single-flight leases; telemetry polling never spawns redundant concurrent SSH connections to the same target.
- **No Separate Time-Series Database:** Embeds metric rollups in SQLite WAL mode via [`TopologyDatabaseManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_db.py) and [`NmsHistoricalMetricsService`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/metrics_service.py).
- **No Untracked Configuration Mutation:** Operates under a 100% read-only monitoring contract; zero automatic rebooting, interface disabling, or firewall modifications.

---

## 3. High-Level System Architecture

Networking V is structured into six layered functional domains operating on an asynchronous event-driven pipeline:

```
       +-------------------------------------------------------------------+
       |                       REACT FRONTEND / OPERATOR                   |
       |  NmsPage (Heatmaps, Charts) | TopologyPage (Operational Overlays) |
       +---------------------------------+---------------------------------+
                                         ^ WebSocket / REST
                                         v
       +-------------------------------------------------------------------+
       |                    AIRA OS REST API & WS BRIDGE                   |
       |  /api/routers/nms.py | /api/routers/topology.py | ws_bridge.py    |
       +---------------------------------+---------------------------------+
                                         ^
                                         | Internal Event Dispatch
       +---------------------------------+---------------------------------+
       |             EVENT, ALERT & ROOT-CAUSE CORRELATION ENGINE          |
       |  - Alert State Machine (DETECTED -> ACTIVE -> RESOLVED)           |
       |  - Upstream Alert Suppression (via TopologyEngine Adjacency)      |
       |  - Route Blast-Radius Pinning (via FailurePropagationAnalyzer)    |
       +---------------------------------+---------------------------------+
                                         ^
                                         | Ingested Metrics & State Events
       +---------------------------------+---------------------------------+
       |                  METRICS & DATA NORMALIZATION PIPELINE            |
       |  - Counter Delta & Wraparound Engine (calculate_traffic_rate)     |
       |  - Multi-Tier SQLite Store (Raw -> 5m Rollup -> 1h Rollup)       |
       |  - Bounded Batch Write Coordinator (WAL mode, zero lock storms)   |
       +---------------------------------+---------------------------------+
                                         ^
                                         | Normalized Telemetry Items
       +---------------------------------+---------------------------------+
       |               TELEMETRY POLLER & SCHEDULER ENGINE                 |
       |  - Async Poller Scheduler (Adaptive Intervals, Priority Tiers)    |
       |  - Per-Device Single-Flight Lock & Circuit Breaker                |
       |  - Capability Prober (ICMP -> SNMP v2c/v3 -> SSH -> Linux)        |
       +---------------------------------+---------------------------------+
                                         ^
                                         | Read-Only Protocol Interrogation
       +---------------------------------+---------------------------------+
       |                     PHYSICAL & VIRTUAL NETWORK                    |
       |     MikroTik ROS v6/v7 | Linux Hosts | Switches | Gateways        |
       +-------------------------------------------------------------------+
```

---

## 4. Subsystem Breakdown & Component Contracts

### 4.1 Telemetry Poller & Scheduler (`core/nms/poller.py`)
- **Lifecycle:** Schedules periodic asynchronous polling jobs across registered devices based on assigned profile intervals (`Critical`: 10–15s, `Standard`: 30–60s, `Bulk`: 120–300s).
- **Single-Flight Per-Device Concurrency:** Maintains a per-device `asyncio.Lock`. If an ongoing poll cycle exceeds the profile interval, the subsequent cycle is dropped with a `POLL_OVERRUN_SKIPPED` warning; a slow device can **never** stack concurrent polling tasks.
- **Capability-Driven Interrogation:** Prioritizes lightweight protocols:
  1. Fast ICMP echo probe for operational reachability.
  2. SNMP UDP requests for counter streaming (low device CPU).
  3. Persistent SSH command execution via [`ConnectionManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/agents/akane/connection_manager.py) when SNMP is unavailable or unconfigured.

### 4.2 Counter Delta & Normalization Engine (`core/nms/normalizer.py`)
- **Wraparound & Discontinuity Detection:** Handles 32-bit and 64-bit integer overflows, device reboot resets, and missing sample intervals via [`calculate_traffic_rate`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/nms_models.py).
- **Invariant:** Missing telemetry is categorized as `SAMPLE_GAP` and never recorded as `0.0 bps`.

### 4.3 Time-Series Metrics Store (`core/nms/metrics_store.py`)
- Extends [`NmsHistoricalMetricsService`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/metrics_service.py) with structured multi-tier tables:
  - `nms_raw_metrics`: 15-second high-resolution retention (48 hours).
  - `nms_5m_rollups`: 5-minute average/min/max/p95 rollups (30 days).
  - `nms_1h_rollups`: 1-hour average/min/max rollups (365 days).
- **Batch Coordinator:** Collects memory buffers across polling threads and commits in single SQLite transactions every 1,000 ms, keeping disk write operations below 15 IOPs.

### 4.4 Topology-Aware Alert & Incident Engine (`core/nms/alerts.py`)
- **Debouncing & Hysteresis:** Requires $N$ consecutive failures (default: 3) to trigger `ACTIVE` alerts; requires $M$ consecutive successes (default: 2) to resolve.
- **Upstream Root-Cause Suppression:** When an alert is detected on Device $D$, the engine queries [`TopologyEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_engine.py) for upstream Layer 2/Layer 3 parent nodes. If an upstream node or transit link is already `DOWN`, downstream alerts are suppressed into `SUPPRESSED_DOWNSTREAM_UNREACHABLE`.
- **Automatic Incident Snapshot Pinning:** When a `CRITICAL` network incident is declared, the engine triggers an automated call to capture and pin an immutable route snapshot (`incident_id = incident.incident_id`), preventing future retention pruning and preserving forensic evidence.

---

## 5. Architectural Alignment with Resource Boundaries

Designed specifically for host hardware **Intel Core i7-7500U (2 cores / 4 threads) with 8 GB RAM**:
- **Concurrency Cap:** Global async task semaphore capped at `10` concurrent device interrogations.
- **Memory Ceiling:** Poller working set bounded to `< 150 MB` RSS; metrics buffers flushed periodically.
- **Disk I/O:** Write-Ahead Logging (`WAL`), `synchronous = NORMAL`, batch commit window `1.0s`.
- **Zero Heavy External Dependencies:** Rejects Prometheus, TimescaleDB, InfluxDB, or Redis daemons; 100% self-contained within Python 3.14 async runtime and SQLite WAL.
