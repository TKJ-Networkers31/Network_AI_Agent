# VERA NETWORK DIAGNOSTICS AUDIT
## Active & Passive Diagnostics, Ping Probes, Traceroute Engines & Preflight Readiness

**Document Version:** 1.0.0  
**Audit Target:** VERA Network Diagnostics Subsystem  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Network Diagnostics & Diagnostic Preflight Audit  
**Status:** VALIDATED — PASS  

---

## 1. DIAGNOSTICS PIPELINE ARCHITECTURE

VERA provides an enterprise diagnostics framework spanning host-level diagnostics, router-delegated diagnostics, and comprehensive preflight verification:

```
  +-------------------------------------------------------------+
  |                     Diagnostics Request                     |
  +------------------------------+------------------------------+
                                 |
         +-----------------------+-----------------------+
         |                                               |
         v                                               v
  +---------------------------+             +---------------------------+
  | Host-Initiated Probe      |             | Router-Delegated Probe    |
  | (ICMP Echo / Traceroute)  |             | (PersistentShell Execution|
  +-------------+-------------+             +-------------+-------------+
                |                                         |
                +--------------------+--------------------+
                                     |
                                     v
                      +-----------------------------+
                      | Output Regex Normalizer     |
                      | (Latency, Packet Loss, Hops)|
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Diagnostic Evidence Store   |
                      |        (ni_evidence)        |
                      +-----------------------------+
```

---

## 2. PREFLIGHT DIAGNOSTIC READINESS

Before executing diagnostic playbooks or root-cause evaluations, VERA mandates a **Preflight Interrogation** ([core/network_intelligence/preflight.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/network_intelligence/preflight.py)).

### 2.1 Live Hardware Preflight Run
Invoked `POST /api/intelligence/preflight` with target `"MikroTik-hAP-ac-lite"`:
- **HTTP Status:** `200 OK`
- **Reachability Status:** `True`
- **Authenticated:** `True`
- **Preflight Verdict:** `READY_FOR_DIAGNOSTICS`
- **Commands Evaluated:** 7 foundational diagnostics:
  1. `/system identity print`
  2. `/system resource print`
  3. `/interface print brief`
  4. `/ip address print detail`
  5. `/ip route print`
  6. `/ip firewall filter print count-only`
  7. `/ip firewall nat print count-only`
- **Output Quality:** 0 prompt mismatches, 0 truncated outputs, mean command latency: **51.42ms**.

---

## 3. PING & REACHABILITY PROBING

The ping engine ([tools/network/diagnostics.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tools/network/diagnostics.py) and [core/topology_engine.py:bounded_icmp_ping](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_engine.py)) provides deterministic ICMP probing:

### 3.1 Live Node Ping API Test
Invoked `POST /api/topology/nodes/node_mikrotik-hap-ac-lite/ping`:
```json
{
  "success": true,
  "node_id": "node_mikrotik-hap-ac-lite",
  "alive": true,
  "latency_ms": 0.43,
  "reachability_status": "reachable",
  "observation_freshness": "fresh",
  "availability_reason": "Authenticated SSH management interrogation succeeded.",
  "status": "online"
}
```

### 3.2 Safety Enforcements:
- Maximum packet count is bounded (default: 3-5 packets).
- Bounded timeout: 2.0s per echo packet to prevent thread starvation.
- Strict target sanitization: Prevents shell injection in `subprocess.Popen`.

---

## 4. TRACEROUTE & PATH HOP EXTRACTION

The traceroute engine supports both Linux host probing (`traceroute -n -q 1 -m 30 <target>`) and RouterOS-delegated `/tool traceroute`:
- **Hop Parsing:** Extracts hop index, router IP, and round-trip time.
- **Loop Detection:** Detects repeated IP addresses across hops to flag forwarding loops.
- **Timeout Handling:** Replaces unresponsive hops (`* * *`) with structured unknown hop markers rather than aborting the trace.
