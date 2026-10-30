# AIRA OS — Known System & Architectural Limitations
## Authoritative Disclosure of Simulator, Datapath, Hardware, and Lab Boundaries

---

## 1. Executive Summary

AIRA OS is designed as a local-first, evidence-driven **Network Engineering Copilot**. To maintain strict engineering integrity, deterministic software must explicitly state its assumptions and technical boundaries. 

This document provides a single authoritative catalog of:
1. **Unmodeled Data-Plane Forwarding Behaviors** in static simulation.
2. **Operational and Lab Environment Boundaries** (Offline vs. Live verification).
3. **Safety and Mutation Boundaries** (Zero-mutation read-only enforcement).
4. **Hardware and Resource Constraints** on target edge hardware.

---

## 2. Unmodeled Data-Plane Forwarding Behaviors

Static routing analysis and Longest Prefix Match (LPM) verification provide reliable control-plane validation, but they do **not** emulate physical ASIC hardware or the full Linux/RouterOS packet processing pipeline. The following behaviors are explicitly **unmodeled**:

### 2.1. FastTrack Connection Bypass
- **Mechanism**: MikroTik RouterOS uses FastTrack (`action=fasttrack-connection`) to bypass CPU packet inspection for established TCP and UDP streams.
- **Impact on AIRA**: Static inspection evaluates firewall rules sequentially. Packets matching active FastTrack connections bypass filter rules, mangle tables, and queuing trees. AIRA cannot predict runtime packet drops on active streams that bypass firewall evaluation.

### 2.2. Switch ASIC Hardware Offload (`Hw-Offload`)
- **Mechanism**: RouterOS bridge and switch configurations delegate L2 forwarding, VLAN tagging, and STP/RSTP state machines directly to switch chip hardware (e.g., Atheros, Marvell, Realtek).
- **Impact on AIRA**: Static configuration analysis verifies bridge VLAN tables (`/interface bridge vlan`), but does not observe ASIC TCAM tables, MAC address table saturation, or hardware-level ingress filtering drop counters.

### 2.3. Dynamic Connection Tracking (`conntrack`)
- **Mechanism**: Stateful firewall processing depends on the Linux kernel connection tracking table (`ip_conntrack`), tracking states such as `ESTABLISHED`, `RELATED`, `NEW`, and `INVALID`.
- **Impact on AIRA**: AIRA evaluates rule order, interface bindings, and address scopes statically. It cannot determine dynamic connection state, NAT helper ALGs (e.g., SIP, H.323), or connection table exhaustion.

### 2.4. ECMP Hashing and Path Asymmetry
- **Mechanism**: Equal-Cost Multi-Path (ECMP) distributes egress traffic across multiple next-hop gateways using 5-tuple packet header hashing (`src_ip`, `dst_ip`, `protocol`, `src_port`, `dst_port`).
- **Impact on AIRA**: AIRA identifies multiple active default routes and notes ECMP presence, but does not simulate runtime hash allocation, per-flow stickiness, or upstream asymmetric return paths.

### 2.5. Dynamic Routing Protocol Convergence
- **Mechanism**: OSPF (LSA flooding, Dijkstra SPF recalculation, DR/BDR elections) and BGP (route reflectors, MED, local preference, BFD fast failover) dynamically update RIB and FIB.
- **Impact on AIRA**: AIRA parses neighbor states, timers, and static filters. It does not simulate transient convergence delays, micro-loops, route flap dampening, or race conditions during topology churn.

### 2.6. Tunnel Encapsulation and MTU/MSS Overhead
- **Mechanism**: WireGuard, IPsec, EoIP, GRE, and VXLAN encapsulate packets, reducing effective Path MTU (PMTU).
- **Impact on AIRA**: Without active probe traffic, AIRA cannot verify whether TCP MSS clamping (`change-mss`) is correctly applied across all encapsulation boundaries or whether PMTUD blackholes exist.

### 2.7. Quality of Service (QoS) & Queue Disciplines
- **Mechanism**: Simple queues and Queue Trees utilize Hierarchical Token Bucket (HTB) and CoDel to schedule egress bandwidth.
- **Impact on AIRA**: Static analysis inspects queue limits and target subnets, but does not simulate queue latency, tail-drop thresholds, or bufferbloat under live link saturation.

---

## 3. Operational & Lab Environment Boundary

### Current Verification Status: `VERIFIED_OFFLINE` / `BLOCKED (LAB_OFFLINE)`

| Subsystem | Offline Verification | Live Lab Verification | Status Boundary |
| :--- | :--- | :--- | :--- |
| **Evidence Collector** | Tabular v6/v7 parser fixtures verified | Socket connect attempted; SSH banner timeout | **LIVE BLOCKED** |
| **Preflight Checker** | 7 preflight status codes verified in test suite | Inventory targets unreachable or refused | **LIVE BLOCKED** |
| **Incident Investigator** | 7 incident domains verified with mock bundles | Live telemetry requires active SSH | **LIVE BLOCKED** |
| **Diagnostic Playbooks** | State machines & step branches verified | Execution uses mock/local fixtures | **LIVE BLOCKED** |
| **Configuration Planner** | Diffs, validations, and rollbacks verified | Zero commands dispatched to hardware | **SAFE READ-ONLY** |

> [!WARNING]
> No physical MikroTik router or Cloud Hosted Router (CHR) is currently available on port 22 in the workspace environment.
> AIRA OS explicitly marks all live device interactions as `BLOCKED (LAB_OFFLINE)` rather than claiming live hardware compatibility from mock fixtures alone.

---

## 4. Safety & Read-Only Non-Mutation Boundary

1. **Zero Automated Remediation**: AIRA does not support self-healing or unattended configuration application. All remediation requires explicit human operator approval and manual execution.
2. **Read-Only Allowlist**: Commands sent to network devices are restricted to inspection commands (`print`, `export compact`). Mutating verbs (`add`, `set`, `remove`, `enable`, `disable`) are strictly rejected by `validate_readonly_command()`.
3. **Command Injection Defenses**: Shell delimiters (`;`, `|`, `&`, `<`, `>`, `` ` ``, `$`, `\n`, `\r`) are rejected prior to execution.
4. **Credential Protection**: Passwords, pre-shared keys, SNMP community strings, and private keys are redacted (`***REDACTED***`) before writing to logs, evidence stores, or frontend responses.

---

## 5. Hardware Budget & Resource Constraints

AIRA OS is engineered for edge deployment on low-spec hardware:
- **Baseline Hardware**: ThinkPad X270, Intel Core i7-7500U (2 cores / 4 threads @ 2.70 GHz), 8 GB DDR4 RAM, Intel HD Graphics 620, CPU-only.
- **Memory Footprint**:
  - Python FastAPI Backend + SQLite: ~180 MB RSS
  - Node/React Frontend PWA: ~120 MB browser memory
  - Pytest full test suite: peak ~350 MB RAM
- **Storage**: SQLite WAL mode with single-writer serialization ensures zero corruptions without requiring PostgreSQL or external daemon services.
- **No Heavy Local LLMs**: AIRA does not run 70B+ local parameter models in memory. Agent reasoning leverages lightweight local or external inference with deterministic rule pre-filtering.
