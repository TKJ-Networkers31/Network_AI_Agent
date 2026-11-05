# AIRA OS — NETWORKING V: ARCHITECTURE DECISION RECORD (ADR)
## Formal Architecture Decision Records for Full Network Management System

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target:** Architecture Governance & Design Decisions (ADR-01 to ADR-10)  
**Status:** `APPROVED_ARCHITECTURE_RECORD`

---

## ADR-01: SQLite WAL with Multi-Tier Rollups vs. External TSDB

### Context
An NMS requires storing time-series telemetry (interface bitrates, CPU load, latency, packet loss) across days, weeks, and months. Mainstream monitoring platforms typically embed external time-series databases like Prometheus, InfluxDB, or TimescaleDB (PostgreSQL).

### Decision
**Adopt SQLite in WAL mode with native multi-tier rollup tables (`nms_raw_metrics`, `nms_5m_rollups`, `nms_1h_rollups`). Reject external TSDB engines.**

### Rationale & Trade-offs
1. **Host Footprint:** Prometheus or TimescaleDB consumes 400–800 MB RAM and runs background daemon services, severely constraining the target 8 GB ThinkPad X270 development machine.
2. **Zero Setup / Portability:** SQLite requires zero daemon installation, runs embedded in-process, and aligns with the existing [`TopologyDatabaseManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_db.py) WAL configuration.
3. **Write Efficiency:** Utilizing `MetricsBatchWriter` (1,000 ms commit window) keeps SQLite write transactions under 5 ms, easily supporting up to 50 devices (400 interfaces) with negligible I/O overhead.

---

## ADR-02: Capability-Based Hybrid Interrogation vs. Single-Protocol Agent

### Context
Network devices across lab and enterprise environments vary widely: high-end MikroTik routers support RouterOS API and SSH; distribution switches support SNMP v2c/v3; unmanaged access points respond only to ICMP; Linux servers support SSH or node metrics.

### Decision
**Implement a capability-driven collection hierarchy: Fast ICMP Ping -> SNMP UDP Walk -> Persistent RouterOS SSH (`ConnectionManager`). Reject single-protocol or agent-only mandates.**

### Rationale & Trade-offs
- A device must never be marked unhealthy or down simply because an unsupported interrogation method failed.
- SNMP UDP is prioritized for interface streaming because it avoids the CPU overhead of repetitive SSH handshakes on low-power MIPS/ARM routerboards.
- Persistent SSH is utilized as an authoritative fallback for RouterOS devices where SNMP is disabled or unconfigured.

---

## ADR-03: Topology-Aware Upstream Root-Cause Suppression

### Context
A failure on a core router or distribution switch typically renders all downstream devices unreachable, generating dozens of simultaneous alarms that overwhelm operators (alert storms).

### Decision
**Integrate the Alert Engine with [`TopologyEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_engine.py) to automatically suppress downstream alarms into `SUPPRESSED_DOWNSTREAM_UNREACHABLE` when an upstream adjacency is failed.**

### Rationale & Trade-offs
- Reduces operator cognitive fatigue by consolidating cascading failures into a single root incident.
- Retains downstream impact visibility in an attached impact tree without firing separate critical notifications.

---

## ADR-04: Counter Delta Rate Calculation with Wraparound & Reset Protection

### Context
Network interface hardware counters are cumulative integers that overflow periodically (wraparound) or drop to zero during router reboots. Naive subtraction produces catastrophic negative rates or gigabit false spikes.

### Decision
**Enforce strict 32-bit and 64-bit wraparound detection and reboot discontinuity handling via [`calculate_traffic_rate`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/nms_models.py). Treat missing samples as `TELEMETRY_GAP`, never zero traffic.**

### Rationale & Trade-offs
- Eliminates erroneous bandwidth spike graphs on monthly or daily 32-bit counter rollovers.
- Distinguishes device reboots from true network saturation.

---

## ADR-05: Per-Device Single-Flight Exclusion Lock

### Context
Under high packet loss or network degradation, device responses slow down. If the scheduler dispatches new polling ticks while the previous cycle is still awaiting timeout, thread queues explode and routers are subjected to connection flooding.

### Decision
**Implement an in-memory `asyncio.Lock` per device in `DevicePollCoordinator`. If an ongoing poll cycle is active when the next tick fires, the new tick is immediately dropped with `POLL_OVERRUN_SKIPPED`.**

### Rationale & Trade-offs
- Prevents stacking overlapping SSH or SNMP sessions to struggling network targets.
- Preserves host and target stability during severe network congestion.

---

## ADR-06: Epistemic Separation of WAN Reachability vs. Device Availability

### Context
A local branch router can be fully operational and accessible on the management network while its upstream fiber provider or WAN gateway is completely down.

### Decision
**Explicitly separate `device_availability` (local management reachability) from `wan_reachability` (upstream egress/gateway probing).**

### Rationale & Trade-offs
- Prevents incorrect diagnosis: a router is not reported "dead" when the problem is an upstream ISP outage.
- Allows AutoOrchestrator to correlate local operational health with external route analytics.

---

## ADR-07: Rollup Downsampling and Cold Archival Partitioning

### Context
Storing high-frequency 15-second telemetry indefinitely leads to multi-gigabyte SQLite databases, slow queries, and memory exhaustion. However, compliance policies require long-term visibility.

### Decision
**Implement a 3-tier in-database retention model (Raw: 48h, 5m Rollups: 30d, 1h Rollups: 365d) combined with cold SQLite export partitioning for permanent history.**

### Rationale & Trade-offs
- Keeps operational `topology.db` size under 100 MB permanently.
- Eliminates lock contention during vacuuming by using chunked indexed deletions.
- Respects the Networking IV immutability rule: operational metric pruning is kept completely separate from immutable forensic route/topology snapshots.

---

## ADR-08: Zero-Mutation Read-Only Boundary for Telemetry Polling

### Context
NMS background engines often blur the boundary between monitoring and remediation, risking unintended service disruptions during polling.

### Decision
**Hardcode a 100% read-only boundary across all NMS collectors. All CLI executions are filtered through [`validate_readonly_command`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/security.py); SNMP SET PDUs are strictly excluded from the codebase.**

### Rationale & Trade-offs
- Guarantees zero risk of automated reboots, interface toggling, or firewall mutations during monitoring.
- Preserves trust in production enterprise environments.

---

## ADR-09: Reusing Existing Frontend React & SVG Components

### Context
Building a rich NMS dashboard might prompt introducing external heavy charting libraries (such as D3, Chart.js, or ECharts) which bloat Vite bundle size and complicate styling.

### Decision
**Extend the existing React frontend architecture (`NmsPage.jsx`, `TopologyPage.jsx`) using lightweight inline SVG visualization and CSS grid heatmaps already established in the codebase.**

### Rationale & Trade-offs
- Keeps Vite production build fast (< 4 seconds) and bundle size compact.
- Eliminates React runtime incompatibilities and maintains consistent visual theme.

---

## ADR-10: Single-Pass Evidence Integration with AutoOrchestrator

### Context
When an incident is investigated, the engineering assistant (Akane/Rei) needs current metrics, interface states, and topology adjacencies. Polling the network anew during diagnosis is redundant and slow.

### Decision
**Expose the live NMS telemetry cache directly to [`AutoOrchestrationEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py) via `NmsHistoricalMetricsService`, allowing single-pass bundle reuse without redundant network roundtrips.**

### Rationale & Trade-offs
- Accelerates natural-language root-cause diagnosis from 10+ seconds to < 2 seconds.
- Correlates live traffic anomalies directly with route dependency blast radiuses.
