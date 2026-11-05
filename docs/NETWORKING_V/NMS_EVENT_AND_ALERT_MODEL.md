# AIRA OS — NMS EVENT & ALERT MODEL
## Topology-Aware Alert Correlation, Debouncing & Incident Lifecycle

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target:** `AIRA_ECOSYSTEM/core/nms/alerts.py` Specification  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Event Taxonomy & EventBus Dispatch

All operational state changes emit structured events via [`EventBus`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/events.py) using the [`EventNames`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/events.py) registry.

```
aira.nms.device.status_changed     -> Device transitions between UP / DEGRADED / UNREACHABLE
aira.nms.interface.status_changed  -> Physical/VLAN interface transitions UP / DOWN
aira.nms.interface.saturated       -> Interface utilization exceeds high threshold (>90%)
aira.nms.resource.threshold_alarm  -> CPU > 85%, RAM > 90%, Temp > 75C
aira.nms.incident.opened           -> Root incident opened or updated
aira.nms.incident.resolved         -> Incident conditions cleared and verified
aira.nms.alert.suppressed          -> Downstream alarm suppressed due to upstream root cause
```

---

## 2. Alert Severity & Threshold Taxonomy

| Severity | Color Code | Condition Definition | Example Scenarios |
|---|---|---|---|
| **`CRITICAL`** | Red (`#EF4444`) | Complete operational outage or service loss | Core router down, transit interface down, default gateway unreachable |
| **`HIGH`** | Orange (`#F97316`) | Severe degradation with impending service impact | CPU > 90% for 5m, packet loss > 15%, interface error rate > 5% |
| **`MEDIUM`** | Yellow (`#FBBF24`) | Performance degradation or failover redundancy lost | Backup link down, RAM > 85%, latency spike > 150 ms |
| **`LOW`** | Blue (`#3B82F6`) | Non-impacting warning or transient event | Interface flapping 3x in 10m, management SSH latency elevated |
| **`INFO`** | Slate (`#64748B`) | Informational baseline or recovery event | Device rebooted, interface administratively brought up |

---

## 3. Debouncing, Hysteresis & Flapping Suppression

Naive monitoring systems create "alert storms" when a link oscillates or ping times out once due to transient queue delay. AIRA OS enforces strict anti-flapping controls:

```
[Sample Point]
       │
       ▼
 ┌───────────┐         Count >= N (3)
 │ Violation │ ──────────────────────────────► [Declare ALERT ACTIVE]
 └─────┬─────┘                                        │
       │                                              ▼
   Count < N                                   ┌──────────────┐
       │                                       │ In Recovery? │
       ▼                                       └──────┬───────┘
  [Increment Failure Counter]                         │
  [Suppress Alert Notification]                 Count >= M (2)
                                                      │
                                                      ▼
                                               [Declare RESOLVED]
```

### Invariants:
1. **Consecutive Sample Requirement:**
   - Declaring an alert requires **$N = 3$ consecutive failing samples** (at 15s intervals = 45s confirmation window).
   - Resolving an alert requires **$M = 2$ consecutive healthy samples** (30s stabilization window).
2. **Hysteresis on Metric Thresholds:**
   - High CPU Alarm activates at `cpu_util >= 85.0%`.
   - High CPU Alarm clears only when `cpu_util <= 75.0%` (10% deadband margin), preventing toggle spam at boundary values.
3. **Flap Damping:**
   - If an interface transitions state more than 3 times within 10 minutes, it enters `FLAPPING_SUPPRESSED` state. Notifications are silenced, and an aggregate `INTERFACE_FLAPPING_DETECTED` incident is raised.

---

## 4. Topology-Aware Upstream Root-Cause Suppression

This is the central intelligence capability separating AIRA OS from basic ping-checkers.

### The Downstream Cascade Problem:
When `Router-A` (Transit) loses power, all 12 switches and 45 access points downstream become unreachable. A naive monitoring tool generates 58 separate `CRITICAL_DEVICE_DOWN` alerts, flooding the engineering team.

### AIRA OS Topology Correlation Solution:
```
                  [Router A (Core Transit)]  <--- FAILS (Power Loss)
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [Switch B (Distribution)]         [Switch C (Access)]
            │                                 │
     (Unreachable)                     (Unreachable)
```

1. **Topology Adjacency Lookup:**
   When `Switch-B` fails ICMP ping, the Alert Engine queries [`TopologyEngine`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/topology_engine.py) to resolve its parent Layer 2 / Layer 3 adjacencies.
2. **Upstream Status Check:**
   The engine discovers that parent `Router-A` is in state `UNREACHABLE`.
3. **Suppression Declaration:**
   The alert on `Switch-B` is classified as `SUPPRESSED_DOWNSTREAM_UNREACHABLE` and attached to `Router-A`'s primary incident as collateral impact.
4. **Operator UI View:**
   - **1 Root Incident:** `Router-A Core Transit Unreachable (CRITICAL)`.
   - **Subordinate Impact Tree:** `12 downstream nodes suppressed (Switch-B, Switch-C, ...)`. Zero false alarms.

---

## 5. Epistemic Separation: Network Fault vs Collection Failure

AIRA OS strictly separates network operational faults from agent interrogation failures:

| Telemetry Finding | Correct Diagnostic Classification | NEVER Classified As |
|---|---|---|
| Ping returns 0%, SNMP times out | `DEVICE_UNREACHABLE` (Network/Power Fault) | Collection script failure |
| Ping alive (1.2 ms), SNMP auth fails | `SNMP_AUTHENTICATION_FAILURE` (Agent Config) | Device Down |
| Ping alive, SSH banner timeout | `MANAGEMENT_SERVICE_DEGRADED` (RouterOS Resource) | Device Down |
| Missing interface byte samples | `TELEMETRY_SAMPLE_GAP` (Poller Dropped Tick) | Zero Traffic (0 bps) |

---

## 6. Incident State Machine

```
               [Threshold Exceeded (N=3)]
                           │
                           ▼
                      [DETECTED]
                           │
              Upstream     │    No Upstream
              Root Cause?  │    Failure
             ┌─────────────┴─────────────┐
             ▼                           ▼
        [SUPPRESSED]                 [ACTIVE]
             │                           │
             │ Operator Action           ▼ Operator Acknowledged
             │                      [ACKNOWLEDGED]
             │                           │
             └─────────────┬─────────────┘
                           │
                           ▼ Metric Healthy (M=2)
                      [RESOLVED]
```
