# AIRA OS — NETWORKING V: RESOURCE & SCALE MODEL
## Quantitative Resource Modeling, Hardware Boundaries & Capacity Planning

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target Hardware:** Lenovo ThinkPad X270 (Intel i7-7500U, 8 GB RAM, Windows 11)  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Hardware Baseline & Environmental Envelope

AIRA OS runs as a local-first engineering assistant directly on the engineer's workstation. The system must coexist with browser tabs, IDEs, and local AI agent execution without inducing CPU thermal throttling or RAM swapping.

### Workstation Specifications:
- **Processor:** Intel Core i7-7500U (2 cores / 4 threads @ 2.70 GHz base, 3.50 GHz turbo).
- **Installed Memory:** 8.00 GB DDR4 (typical available working headroom: 2.0 to 2.5 GB).
- **Storage:** SATA III SSD (sequential writes ~450 MB/s; random 4K writes ~50 MB/s).
- **Operating System:** Windows 11 Professional (64-bit).
- **Runtime:** Python 3.14.0 (asyncio, ThreadPoolExecutor) + Node/Vite web server.

---

## 2. Mathematical Scaling Model Across Inventory Tiers

Let:
- $N$ = Number of monitored network devices.
- $I_{avg}$ = Average interface count per device (assumed $I_{avg} = 8$).
- $T_{crit}$ = Critical polling interval (15 s, core routers: 20% of inventory).
- $T_{std}$ = Standard polling interval (45 s, switches/servers: 60% of inventory).
- $T_{bulk}$ = Bulk polling interval (180 s, edge/endpoints: 20% of inventory).
- $R_{poll}$ = Aggregate polling jobs dispatched per second:
  $$R_{poll} = N \times \left( \frac{0.20}{15} + \frac{0.60}{45} + \frac{0.20}{180} \right) \approx N \times (0.0133 + 0.0133 + 0.0011) \approx 0.0278 \times N$$

### Quantitative Projections:

| Dimension / Metric | 5 Devices (Lab) | 20 Devices (Branch) | 50 Devices (Campus) | 100 Devices (Ceiling) |
|---|---|---|---|---|
| **Dispatched Polls / Sec ($R_{poll}$)** | `0.14 polls/s` | `0.56 polls/s` | `1.39 polls/s` | `2.78 polls/s` |
| **Active Concurrent Sockets** | 1–2 | 3–5 | 8–10 | 10–15 (capped at 10) |
| **Total Monitored Interfaces** | 40 | 160 | 400 | 800 |
| **Raw Samples / Minute** | 160 | 640 | 1,600 | 3,200 |
| **SQLite Writes / Minute (Batched)** | 60 transactions | 60 transactions | 60 transactions | 60 transactions |
| **Daily Database Growth (Raw)** | `2.4 MB/day` | `9.8 MB/day` | `24.5 MB/day` | `49.0 MB/day` |
| **Daily DB Growth (After Rollup)** | `0.4 MB/day` | `1.6 MB/day` | `4.1 MB/day` | `8.2 MB/day` |
| **Python Heap (`tracemalloc`)** | `12 MB` | `28 MB` | `55 MB` | `95 MB` |
| **Process WorkingSetSize (RSS)** | `95 MB` | `135 MB` | `185 MB` | `260 MB` |
| **Host CPU Overhead (Background)** | `< 1.0%` | `1.5 – 3.0%` | `4.0 – 7.5%` | `10.0 – 16.0%` |
| **Feasibility on ThinkPad X270** | **OPTIMAL** | **EXCELLENT** | **SUSTAINABLE** | **REQUIRES RELAXED INTERVALS** |

---

## 3. Resource Bounds & Architectural Ceilings

### 3.1 Memory Ceiling & Swapping Defense
- **Maximum Allocated Working Set:** The NMS background process is hard-capped at **`< 350 MB`** RSS.
- **Buffer Flush Invariant:** In-memory metric buffers are flushed to SQLite every `1,000 ms` or when buffer length exceeds `250` items. Telemetry records never accumulate unbounded in memory.
- **Garbage Collection:** Explicitly dereferences raw SNMP response PDUs immediately after normalization to enable generational Python GC collection.

### 3.2 Disk I/O & SSD Write Endurance Protection
- **Problem:** Naive monitoring tools commit each ping or interface sample individually, causing 50+ SQLite disk syncs per second that degrade SSD flash longevity.
- **AIRA OS Batch Coordinator:** Telemetry samples are buffered in an in-memory queue. A single batch transaction (`BEGIN IMMEDIATE` ... `COMMIT`) executes once per second.
- **Disk IOPs:** Average disk write operations remain **`< 5 IOPs`**, which is negligible on modern SATA/NVMe SSDs.

### 3.3 Network Bandwidth Overhead
- **SNMP UDP Packet:** ~120 bytes per interface counter request.
- **ICMP Packet:** 64 bytes total.
- **50-Device Overhead:** Generates less than **`35 KB/s`** total network traffic across the management VLAN, ensuring zero impact on user data planes.

---

## 4. Hardware Scaling Evaluation: 50 vs. 100 Devices

### Recommended Operating Sweet Spot: 50 Devices
On the dual-core Intel i7-7500U, an inventory of up to **50 devices (400 interfaces)** runs smoothly in the background, consuming less than 8% CPU and ~185 MB RAM. This leaves ample thermal and memory headroom for running local LLM reasoning tasks and live browser interactions.

### The 100-Device Scale Boundary:
Scaling to 100 devices is feasible, but requires:
1. **Interval Relaxation:** Setting the standard polling interval to `60–90 s` rather than `30–45 s`.
2. **Concurrency Cap:** Retaining the global semaphore limit at `10` simultaneous connections.
3. **SNMP Preference:** Disabling SSH-based polling for access-layer devices in favor of lightweight SNMP UDP queries.
