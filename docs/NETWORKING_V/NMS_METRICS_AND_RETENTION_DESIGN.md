# AIRA OS — NMS METRICS & RETENTION DESIGN
## Time-Series Metrics Pipeline, Counter Normalization & Multi-Tier SQLite Retention

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target:** `AIRA_ECOSYSTEM/core/nms/metrics_store.py` Specification  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Metric Naming Taxonomy & Dimensions

Metrics follow a hierarchical, dot-separated naming convention:

```
aira.nms.<domain>.<entity>.<metric_name>
```

### 1.1 Core Metric Catalog

| Metric Identifier | Unit | Description | Dimensions / Labels |
|---|---|---|---|
| `aira.nms.device.availability` | Enum (0, 1) | Device reachable state (0=Down, 1=Up) | `device_id`, `protocol` |
| `aira.nms.device.rtt_ms` | Milliseconds | ICMP Round-Trip Latency | `device_id`, `target_ip` |
| `aira.nms.device.packet_loss_pct` | Percent | Probed ICMP Packet Loss | `device_id`, `sample_count` |
| `aira.nms.device.cpu_util_pct` | Percent | Average Host/Processor CPU Load | `device_id`, `core_id` |
| `aira.nms.device.memory_used_pct` | Percent | Memory Utilization Percentage | `device_id` |
| `aira.nms.device.storage_used_pct` | Percent | Primary Disk/NAND Utilization | `device_id`, `volume` |
| `aira.nms.device.uptime_sec` | Seconds | Continuous System Uptime | `device_id` |
| `aira.nms.device.temp_celsius` | Celsius | System Board Temperature | `device_id`, `sensor` |
| `aira.nms.interface.oper_status` | Enum (0, 1) | Operational Status (0=Down, 1=Up) | `device_id`, `interface_name` |
| `aira.nms.interface.rx_rate_bps` | Bits/sec | Inbound Bandwidth Rate | `device_id`, `interface_name` |
| `aira.nms.interface.tx_rate_bps` | Bits/sec | Outbound Bandwidth Rate | `device_id`, `interface_name` |
| `aira.nms.interface.rx_util_pct` | Percent | Inbound Link Saturation | `device_id`, `interface_name`, `speed` |
| `aira.nms.interface.tx_util_pct` | Percent | Outbound Link Saturation | `device_id`, `interface_name`, `speed` |
| `aira.nms.interface.rx_errors_delta` | Integer | Inbound Cyclic Redundancy Errors | `device_id`, `interface_name` |
| `aira.nms.interface.tx_errors_delta` | Integer | Outbound Collision/Buffer Errors | `device_id`, `interface_name` |

---

## 2. Counter Delta & Bandwidth Rate Computation

Physical network interfaces report cumulative monotonically increasing octet counters (`ifInOctets`, `ifHCInOctets`). Translating raw counters into instantaneous bitrates requires strict mathematical normalization.

### 2.1 The Rate Formula
For two consecutive samples $(T_1, C_1)$ and $(T_2, C_2)$ where $\Delta T = T_2 - T_1 > 0$:

$$\text{Rate (bps)} = \frac{(C_2 - C_1) \times 8}{\Delta T}$$

$$\text{Utilization (\%)} = \left( \frac{\text{Rate (bps)}}{\text{Interface Speed (bps)}} \right) \times 100$$

### 2.2 Counter Wraparound & Reboot Discontinuity Handling

Implemented via [`calculate_traffic_rate`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/nms_models.py):

1. **Normal Monotonic Delta ($C_2 \ge C_1$):**
   $$\Delta C = C_2 - C_1$$
2. **32-Bit Counter Wraparound ($C_2 < C_1$ and $C_1 \ge 2^{31}$):**
   $$\Delta C = (2^{32} - C_1) + C_2 + 1$$
3. **64-Bit Counter Wraparound ($C_2 < C_1$ and $C_1 \ge 2^{64} - 10^{11}$):**
   $$\Delta C = (2^{64} - C_1) + C_2 + 1$$
4. **Counter Reset / Router Reboot ($C_2 < C_1$ and $C_1 < 2^{31}$):**
   - Declared as `COUNTER_DISCONTINUITY_REBOOT`.
   - $\Delta C$ is suppressed for that single sampling interval. Rate is reported as `None` or interpolated from prior steady-state; it is **never** calculated as a negative number or anomalous spike.
5. **Missing Telemetry Semantics:**
   - If a poll cycle fails or times out, the missing interval is tagged `TELEMETRY_GAP`.
   - **Critical Rule:** AIRA OS **never** interprets missing samples as `0.0 bps` (which would falsely indicate an idle network).

---

## 3. Storage Architecture: SQLite WAL & Batching

Rather than running an external time-series database (such as Prometheus or InfluxDB) which consumes 400–800 MB RAM and introduces background daemons, Networking V implements an optimized, self-contained time-series engine directly in SQLite.

```
       [Polling Threads / Collectors]
                     │
                     ▼ Enqueue (non-blocking in-memory queue)
       [MetricsBatchWriter (Queue Buffer)]
                     │
                     ▼ Every 1,000 ms (or 200 items)
       ┌─────────────────────────────────────────────────┐
       │ BEGIN IMMEDIATE TRANSACTION;                    │
       │ INSERT INTO nms_raw_device_metrics VALUES (...);│
       │ INSERT INTO nms_raw_iface_metrics VALUES (...); │
       │ COMMIT;                                         │
       └─────────────────────────────────────────────────┘
                     │ Written to
                     ▼
       [topology.db (SQLite WAL Mode, synchronous=NORMAL)]
```

### Performance Invariants:
- **Lock Contention Elimination:** All metric writes route through `MetricsBatchWriter` leveraging `TopologyWriteCoordinator._lock`.
- **Transaction Duration:** Batched bulk inserts complete in `< 5 ms`, eliminating database lock contention with UI queries.
- **WAL Auto-Checkpoint:** SQLite `wal_autocheckpoint = 1000`, keeping WAL file size under `10 MB`.

---

## 4. Multi-Tier Retention & Automated Downsampling

To prevent database bloat on the 8 GB RAM / limited SSD development machine, telemetry is stored across three retention tiers:

| Tier | Table Name | Resolution | Retention Window | Aggregations Computed |
|---|---|---:|---:|---|
| **Tier 1: Raw** | `nms_raw_metrics` | **10–15 s** | **48 Hours** | Raw measured sample points |
| **Tier 2: Rollup-5m** | `nms_5m_rollups` | **5 Minutes** | **30 Days** | `avg`, `min`, `max`, `p95`, `sample_count` |
| **Tier 3: Rollup-1h** | `nms_1h_rollups` | **1 Hour** | **365 Days** | `avg`, `min`, `max`, `sample_count` |
| **Tier 4: Archive** | Cold SQLite DB | **1 Day** | **Permanent** | Optional export manifest |

### 4.1 Downsampling Worker Job
A background task runs every 5 minutes:
1. Aggregates Tier 1 raw records older than 10 minutes into Tier 2 buckets (`5-minute` intervals).
2. Aggregates Tier 2 records older than 2 hours into Tier 3 buckets (`1-hour` intervals).
3. Deletes Tier 1 records older than 48 hours and Tier 2 records older than 30 days using indexed chunked deletions:
   ```sql
   DELETE FROM nms_raw_metrics WHERE timestamp < ? LIMIT 5000;
   ```
4. **Estimated Database Footprint:** For a 20-device lab environment, total SQLite storage consumed by all tiers combined is bounded to **`< 85 MB`**.
