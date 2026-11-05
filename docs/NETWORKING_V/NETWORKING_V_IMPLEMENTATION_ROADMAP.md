# AIRA OS — NETWORKING V: IMPLEMENTATION ROADMAP
## Phased Work Package Breakdown, Entry/Exit Criteria & Verification Gates

**Document Version:** 5.0.0  
**Phase:** Networking V — Implementation Plan  
**Target:** WP 5.0 through WP 5.7  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Roadmap Architecture & Phasing Strategy

Networking V is structured into **eight focused, testable, and independently reviewable work packages**. Each package builds cumulatively on verified baselines without mutating existing Networking III or Networking IV production systems.

```
+---------------------------------------------------------------------------------------+
|  WP 5.0: Architecture Blueprint & Technical Specification [CURRENT PHASE]             |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.1: Telemetry Data Model, Capability Prober & Collection Contracts               |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.2: Polling Engine & Scheduler Hardening (Single-Flight & Circuit Breakers)      |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.3: Device, Interface & Resource Monitoring (SNMP / SSH / Wraparound Engine)     |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.4: Metrics Pipeline & Multi-Tier SQLite Retention (Batch Writer & Rollups)      |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.5: Topology-Aware Event, Alert & Health Engine (Upstream Root-Cause Suppression)|
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.6: NMS Dashboard & Operational Topology Overlays (React / WebSocket Push)       |
+-------------------------------------------+-------------------------------------------+
                                            │
                                            ▼
+---------------------------------------------------------------------------------------+
|  WP 5.7: Scale, Reliability, Security & Final Acceptance Audit                        |
+---------------------------------------------------------------------------------------+
```

---

## 2. Work Package Specifications

### WP 5.0: Architecture Blueprint & Technical Specification (Current Phase)
- **Scope:** Complete architectural design, capability hierarchy, poller lifecycle, rate calculation, retention tiers, and scale modeling.
- **Deliverables:** 8 architecture documents under `docs/NETWORKING_V/`.
- **Exit Criteria:** Zero production code changes; architectural consistency verified.

---

### WP 5.1: Telemetry Data Model & Collection Contracts
- **Scope:** Define canonical Pydantic and dataclass models for telemetry items, device capability states, and collection results.
- **Key Deliverables:**
  - `core/nms/models.py`: `NormalizedDeviceMetric`, `NormalizedInterfaceMetric`, `DeviceCapabilityProfile`.
  - Capability discovery logic: auto-detects ICMP, SNMP v2c/v3, and RouterOS SSH support per device.
- **Exit Criteria:** `pytest tests/test_wp_5_1_nms_models.py` passes with 100% schema validation.

---

### WP 5.2: Polling Engine & Scheduler Hardening
- **Scope:** Implement the asynchronous scheduler with per-device single-flight exclusion locks, adaptive backoff, and circuit breakers.
- **Key Deliverables:**
  - `core/nms/scheduler.py`: Profile-based interval triggers (`Critical`, `Standard`, `Bulk`).
  - `DevicePollCoordinator`: `asyncio.Lock` per device, `POLL_OVERRUN_SKIPPED` handling, global concurrency semaphore.
  - Graceful cancellation tokens for clean startup and shutdown.
- **Exit Criteria:** Zero concurrent polling overlap on the same device under simulated 10-second lag; tests pass.

---

### WP 5.3: Device, Interface & Resource Monitoring
- **Scope:** Implement lightweight protocol interrogation (ICMP, SNMP v2c/v3, persistent SSH reuse) and rate calculations.
- **Key Deliverables:**
  - `core/nms/collectors/icmp.py`: High-speed bounded echo probe.
  - `core/nms/collectors/snmp.py`: Asynchronous PySNMP/UDP collector for octet counters and CPU.
  - `core/nms/collectors/routeros.py`: Read-only persistent SSH execution using [`ConnectionManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/agents/akane/connection_manager.py).
  - Rate engine: Wraparound (32-bit & 64-bit), reboot discontinuity, and missing-sample handling.
- **Exit Criteria:** Correct bitrates calculated across simulated 32-bit wraps and device reboots without negative or anomalous values.

---

### WP 5.4: Metrics Pipeline & Multi-Tier SQLite Retention
- **Scope:** Build the non-blocking `MetricsBatchWriter`, multi-tier SQLite schemas, automated rollup worker, and downsampling queries.
- **Key Deliverables:**
  - Additive tables in `topology.db`: `nms_raw_metrics`, `nms_5m_rollups`, `nms_1h_rollups`.
  - Multi-tier rollup worker: Aggregates 15s raw samples into 5m rollups; prunes expired raw data.
  - Query API endpoints in `api/routers/nms.py`: Filterable time-series retrieval with auto-resolution selection.
- **Exit Criteria:** Sub-millisecond write transactions; database size remains `< 100 MB` over 48-hour continuous simulation.

---

### WP 5.5: Topology-Aware Event, Alert & Health Engine
- **Scope:** Build the alerting state machine, debouncing, threshold hysteresis, and upstream root-cause suppression.
- **Key Deliverables:**
  - `core/nms/alerts.py`: Alert FSM (`DETECTED` -> `ACTIVE` / `SUPPRESSED` -> `RESOLVED`).
  - Topology Adjacency Correlator: Traverses [`TopologyEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_engine.py) to suppress downstream alarms when parent nodes fail.
  - Automatic Route Snapshot Pinning: Pins immutable route snapshots during `CRITICAL` incidents.
- **Exit Criteria:** In a simulated parent router failure, 10 downstream device alarms are successfully suppressed into 1 parent incident.

---

### WP 5.6: NMS Dashboard & Operational Topology Integration
- **Scope:** Modernize the frontend monitoring UI, integrating live WebSocket feeds, performance charts, and operational topology overlays.
- **Key Deliverables:**
  - Update `app/frontend/src/pages/NmsPage.jsx`: Real-time status cards, interface bandwidth heatmaps, and incident triage panel.
  - Topology Operational Overlay: Renders live link utilization colors (Green/Yellow/Red) and outage badges directly on [`TopologyPage.jsx`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/pages/TopologyPage.jsx).
- **Exit Criteria:** Vitest component tests pass; production bundle builds cleanly.

---

### WP 5.7: Scale, Reliability, Security & Final Acceptance Audit
- **Scope:** End-to-end multi-device validation, stress-testing up to 50 simulated nodes, live RouterOS hardware testing, read-only security audit, and global regression.
- **Key Deliverables:**
  - `tests/test_networking_v_e2e_acceptance.py`.
  - Read-only security audit confirming zero configuration mutation.
  - Comprehensive acceptance report.
- **Exit Criteria:** 100% backend/frontend tests green; live lab hardware validated; final release gate cleared.
