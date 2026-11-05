# AIRA OS — NMS TELEMETRY POLLER SPECIFICATION
## Asynchronous, Capability-Driven, Resource-Bounded Telemetry Polling Engine

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target:** `AIRA_ECOSYSTEM/core/nms/poller.py` Specification  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Complete Telemetry Polling Lifecycle

The telemetry poller executes an explicit 9-stage asynchronous pipeline for every polling tick:

```
[1. Scheduler] 
       │ 
       ▼ Trigger next execution tick per device profile
[2. Poll Job Dispatch]
       │ 
       ▼ Acquire per-device single-flight lock (drop tick if locked)
[3. Capability Assessment]
       │ 
       ▼ Inspect device profile (ICMP, SNMP v2c/v3, SSH, RouterOS API)
[4. Protocol Collector]
       │ 
       ▼ Dispatch protocol probes (ICMP Echo -> SNMP UDP -> SSH Exec)
[5. Normalizer]
       │ 
       ▼ Compute counter deltas, detect wraparounds, build CanonicalMetrics
[6. Metrics Storage]
       │ 
       ▼ Enqueue to Batch Writer (committed to SQLite WAL)
[7. Event & Anomaly Detection]
       │ 
       ▼ Check threshold rules, debounce counters, evaluate hysteresis
[8. EventBus Dispatch]
       │ 
       ▼ Publish structured event (EventNames.NMS_DEVICE_STATUS, etc.)
[9. Frontend Broadcast]
       │ 
       ▼ WebSocket Bridge pushes real-time delta to NmsPage & TopologyPage
```

---

## 2. Concurrency & Overrun Protection (Single-Flight Lock)

### 2.1 The Overrun Hazard
In slow or degrading networks, a device that normally responds to SNMP in 200 ms may suddenly experience packet loss, causing timeout retries of 6 to 10 seconds. In naive schedulers, a new 10-second polling cycle dispatches before the previous cycle finishes, resulting in:
- Cascading thread exhaustion.
- CPU spikes on both the host and the target router.
- Multiple competing SSH channels opened to the same device.

### 2.2 Invariant: Per-Device Single-Flight Lock
Every registered device maintains an in-memory `asyncio.Lock` managed by `DevicePollCoordinator`:

```python
async def execute_device_poll(device_id: str, profile: DeviceMonitoringProfile) -> None:
    device_lock = coordinator.get_device_lock(device_id)
    if device_lock.locked():
        # Single-flight protection: Drop this tick immediately, do not queue
        coordinator.record_poll_overrun(device_id)
        logger.warning(f"Device '{device_id}' poll overrun: previous cycle active. Tick skipped.")
        return

    async with device_lock:
        await coordinator.dispatch_poll_cycle(device_id, profile)
```

### 2.3 Global Concurrency Bounds
To guarantee that background polling never starves the local AI assistant (Akane/Rei) or UI responsiveness on the ThinkPad X270, global polling concurrency is governed by a global `asyncio.Semaphore(max_concurrent_polls)`:
- **Default Limit:** `10` simultaneous active device interrogations.
- **Maximum Ceiling:** `20` concurrent tasks.
- If 50 devices are scheduled simultaneously, they are executed in bounded batches through the semaphore without thrashing.

---

## 3. Capability-Based Protocol Selection Hierarchy

Different devices exhibit different management capabilities. Telemetry collection follows an explicit capability cascade:

```
                          [Start Device Interrogation]
                                       │
                                       ▼
                             ┌──────────────────┐
                             │ ICMP Echo Check  │
                             └─────────┬────────┘
                                       │
                        Alive? ────────┴──────── No ──┐
                          │                           │
                         Yes                          ▼
                          │             [Mark Device UNREACHABLE]
                          │             [Record Outage Timestamp]
                          ▼             [Skip Sub-Telemetry]
             ┌─────────────────────────┐
             │ Capability: SNMP Enabled?│
             └────────────┬────────────┘
                          │
             Yes ─────────┴──────── No
              │                      │
              ▼                      ▼
     ┌────────────────┐    ┌────────────────────┐
     │ Query SNMP v2c │    │ SSH Interrogation  │
     │ / v3 OIDs      │    │ via ConnectionMgr  │
     └────────┬───────┘    └─────────┬──────────┘
              │                      │
        Success? ─── No (Fallback) ──┤
              │                      ▼
             Yes           ┌────────────────────┐
              │            │ Safe Read-Only ROS │
              │            │ or Linux Telemetry │
              │            └─────────┬──────────┘
              │                      │
              └───────────┬──────────┘
                          │
                          ▼
            [Normalize Extracted Telemetry]
```

### Protocol Guidelines:
1. **ICMP Ping (Fast Path):** Always executed first (timeout: 1.5s, 1 packet). If ICMP fails $N$ times (default: 3), the device is declared `UNREACHABLE` and heavy application-layer protocols (SNMP/SSH) are bypassed immediately to save network overhead.
2. **SNMP UDP (Preferred High-Frequency Telemetry):**
   - High efficiency, zero SSH handshake overhead, minimal router CPU impact.
   - OIDs queried: `sysUpTime`, `sysName`, `ifDescr`, `ifOperStatus`, `ifAdminStatus`, `ifSpeed`, `ifHCInOctets`, `ifHCOutOctets`, `ifInErrors`, `ifOutErrors`, `hrProcessorLoad`.
3. **Persistent SSH (`ConnectionManager` Reuse):**
   - Employed when SNMP is disabled or unavailable.
   - Reuses existing persistent SSH sessions leased from [`ConnectionManager`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/agents/akane/connection_manager.py).
   - Executes strictly read-only commands:
     - RouterOS v7: `/system resource print without-paging`, `/interface print stats-detail without-paging`.
     - RouterOS v6: `/system resource print without-paging`, `/interface print detail without-paging`.

---

## 4. Monitoring Profiles & Adaptive Polling

| Profile Name | Target Device Class | Polling Interval | Protocols Active | Metrics Gathered |
|---|---|---:|---|---|
| **Critical** | Core Routers, Transit Gateways, Internet Firewalls | **10–15 s** | ICMP, SNMP/SSH | Interface octets/packets, CPU, RAM, Latency, Loss |
| **Standard** | Distribution Switches, Access Routers, Servers | **30–60 s** | ICMP, SNMP/SSH | Interface counters, CPU, RAM, Latency |
| **Bulk** | Edge Access Points, Printers, IoT Nodes, Endpoints | **120–300 s** | ICMP | Up/Down Reachability, Latency |

### Adaptive Backoff & Circuit Breakers:
- **Consecutive Failures:** When a device fails 3 consecutive poll cycles, its polling interval automatically backs off to `120 s` to prevent spamming dead networks with ARP/ICMP packets.
- **Circuit Breaker:** If a device remains unreachable for 15 minutes, it transitions to `DORMANT_RETRY` (probed once every 5 minutes).
- **Instant Fast-Recovery:** Once an ICMP echo returns successfully on a dormant device, the circuit breaker resets immediately to its configured profile interval.

---

## 5. Stale Telemetry & Cancellation Tokens

- **Timeout Boundaries:**
  - ICMP Echo: `1.5 s`
  - SNMP UDP Bulk Walk: `3.0 s`
  - SSH Command Execution: `5.0 s`
- **Cancellation Tokens:** All polling operations accept an `asyncio.Event` cancellation token passed down from `NmsScheduler.stop_monitoring()`. On service shutdown, in-flight polling tasks cancel within 500 ms without leaving orphaned background threads.
- **Stale Telemetry Classification:** A metric record older than `2.5 × polling_interval` is marked `is_stale = True` by the query engine; the UI renders a muted amber stale indicator rather than misleading operators into thinking telemetry is real-time.
