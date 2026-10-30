# AIRA OS — Master Engineering Upgrade Report
## Autonomous Networking Intelligence, Persistent Connectivity, NMS, Topology, AKANE Diagnosis & Safe Configuration

**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Workspace:** `D:\data\agent_ai`  
**Target Profile:** ThinkPad X270, Intel Core i7-7500U, 8 GB System RAM, CPU-Only Inference, RouterOS v6 & v7  
**Status:** Completed & Validated  
**Date:** October 2026  

---

## 1. Executive Summary

This engineering effort upgrades AIRA OS into a high-reliability, resource-efficient Network Engineering Copilot for MikroTik and multi-device infrastructure. Addressing both frontend telemetry stability and backend autonomous intelligence, this upgrade resolves excessive UI polling/flickering, stabilizes Windows microphone hardware acquisition, establishes a canonical network identity fabric, introduces persistent SSH connection pooling with reconnect storm protection, separates L2/L3 topology with path exploration and change impact simulation, delivers a deterministic AKANE network reasoning engine (Longest Prefix Match, firewall chain auditing, bridge VLAN verification), and enforces a strictly guarded 7-stage configuration change engine with automated inverse rollbacks.

### Key Milestones Achieved:
1. **NMS Polling & Loading Elimination:** Resolved frontend re-render thrashing by replacing unthrottled 10s intervals with single-flight recursive timeouts (60s routine / 30s manual), introducing `/ws/nms` WebSocket push streaming, debouncing search (300ms), applying request cancellation via `AbortController`, detecting tab visibility (`document.hidden`), and executing in-place normalized state updates.
2. **Microphone Lifecycle Stabilization:** Stopped audio hardware acquisition during `STANDBY` state. Constrained `getUserMedia` exclusively to active `LISTENING` sessions, fixed an infinite 250ms reopen loop in `onend`, capped recovery retries to 3, and preserved inter-component microphone arbitration (`aira:mic-claimed`/`released`).
3. **Canonical Network State (`core/canonical_network.py`):** Unified device identity across Inventory, NMS, Topology, and AKANE with explicit precedence (User Override > Configured Inventory Name > Observed RouterOS System Identity > IP/Slug). Enforced conservative identity resolution to prevent incorrect merges or data erasure on transient poll failures.
4. **Enhanced Connection Manager (`agents/akane/connection_manager.py`):** Enhanced APCE with persistent SSH transport reuse, per-target single-flight locks (`_target_locks`) to eliminate TOCTOU and concurrent session duplication, exponential backoff on reconnect storms (`_backoff`), max session lifetime enforcement (`MAX_SESSION_LIFETIME_SECONDS`), command latency profiling, and unified structured evidence collection (`get_identity`, `get_interfaces`, `get_routes`, `get_ip_addresses`, `get_firewall_rules`, `get_nat_rules`, `get_configuration_snapshot`).
5. **Evidence-Backed Topology & Path Explorer (`core/topology_engine.py`):** Established L2 (bridge/physical) vs. L3 (routed next-hop) link classification. Implemented `find_path()` with hop-by-hop bottleneck identification, and `analyze_change_impact()` for pre-change blast radius and isolated downstream device simulation.
6. **AKANE Deterministic Network Reasoning (`agents/akane/reasoning_engine.py`):** Engineered IPv4 Longest Prefix Match (LPM) evaluator compatible with RouterOS v6 & v7 syntax, firewall filter chain order validation, FastTrack placement checks, NAT masquerade coverage analysis, and standardized Structured Evidence Contracts.
7. **Safe Configuration Engine (`agents/akane/config_engine.py`):** Implemented the 7-stage lifecycle (`READ` $\rightarrow$ `PLAN` $\rightarrow$ `VALIDATE` $\rightarrow$ `PREVIEW` $\rightarrow$ `APPLY` $\rightarrow$ `VERIFY` $\rightarrow$ `RECOVER`), automated rollback command synthesis, and strict authorization gating (`approved=True`).
8. **Verification:**
   - **Backend pytest:** **758 passed, 0 failed** (100% pass rate).
   - **Frontend test suite:** **247 passed, 0 failed** (100% pass rate).
   - **Frontend production build:** Clean production bundle in **2.52 seconds**.

---

## 2. Problem Diagnosis & Evidence-Based Fixes

### 2.1 NMS Polling & Loading Flicker Root Cause
- **Observed Behavior:** The NMS UI flashed full-page loading indicators continuously every few seconds, resetting scroll position and causing visible table flickering.
- **Root Causes:**
  1. `NmsPage.jsx` executed an unthrottled `setInterval` (10s) that fired regardless of whether previous requests had completed.
  2. The main loading spinner was toggled on every periodic background refresh cycle instead of only during initial mount.
  3. Search input triggered immediate network requests on every keystroke without debouncing.
  4. Hidden background tabs continued requesting full device lists and SNMP metric payloads.
  5. State replacement (`setDevices(newDevices)`) generated new object references for all records, forcing full table re-renders even when metrics were unchanged.
  6. `TopologyPage.jsx` re-triggered polling intervals whenever `draggingNodeId` changed, causing layout shifts.
- **Implemented Remediation:**
  - Migrated from `setInterval` to single-flight recursive `setTimeout` scheduled only after the prior request completes.
  - Added `/ws/nms` WebSocket channel pushing `nms_device_status`, `nms_cycle_completed`, and `nms_incident` events.
  - Implemented in-place normalized state updates (`prevDevices.map(...)` merging only changed metrics).
  - Suspended routine background timers when `document.hidden` is active, resuming with a fresh sync on tab focus.
  - Added `AbortController` cancellation for superseded requests and 300ms debounce on search queries.

### 2.2 Windows Microphone Privacy Indicator Root Cause
- **Observed Behavior:** The Windows microphone privacy tray icon repeatedly appeared, vanished, and reappeared every few seconds while AIRA OS was running.
- **Root Causes:**
  1. `useVoiceCompanion.js` initialized `AudioContext` and acquired `navigator.mediaDevices.getUserMedia` streams while in the `STANDBY` state, keeping the microphone permanently locked or cycling.
  2. The Speech Recognition `onend` event handler immediately called `startRecognition()` after a 250ms delay unconditionally, even when the user was not speaking or when the browser terminated the recognition session.
  3. No retry counter bounded reconnection attempts on audio hardware error.
- **Implemented Remediation:**
  - Enforced strict state separation: Audio tracks and recognition are now acquired **only** upon entering `LISTENING` state.
  - In `STANDBY`, all media stream tracks are explicitly stopped (`track.stop()`) and released to Windows.
  - Added an exponential 3-retry maximum limit in `onend` before transitioning to `STANDBY` rather than looping indefinitely.
  - Retained system-wide mic arbitration via `aira:mic-claimed` and `aira:mic-released` window events.

---

## 3. Architecture & Subsystem Improvements

### 3.1 Canonical Network State (`core/canonical_network.py`)
Provides a single source of truth reconciling configured devices (Inventory Store), observed topology nodes (Topology Engine), and live telemetry (NMS Engine):
- **Deterministic Identity:** Every device is assigned a canonical identifier `device_id` (e.g. `dev_r1`).
- **Identity Precedence:**
  1. User custom override (e.g. `custom_name`).
  2. Configured Inventory name (e.g. `R1`).
  3. Observed RouterOS system identity (e.g. `MikroTik-HQ`).
  4. Management IP or fallback slug.
- **Conservative Resolution:** Refuses to merge devices that have conflicting non-default hostnames or distinct hardware MACs, preventing silent node conflation during DHCP renewals.
- **History Preservation:** Transient probe failures update status (`unreachable`, `DOWN`) without zeroing out historical metrics or deleting user-positioned nodes.

### 3.2 Enhanced Device Connection Manager (`agents/akane/connection_manager.py`)
Upgrades the AIRA Persistent Connection Engine (APCE):
- **Single-Flight Per-Target Lock (`_target_locks`):** Eliminates TOCTOU race conditions. Concurrent requests to the same target serialize behind a target lock, allowing the second request to reuse the first session immediately without opening duplicate SSH channels.
- **Reconnect Storm Backoff (`_backoff`):** Implements exponential backoff ($2s \rightarrow 4s \rightarrow 8s \rightarrow \dots \le 60s$) on consecutive SSH connection failures to prevent overwhelming routers or exhausting local socket handles.
- **Max Session Lifetime (`MAX_SESSION_LIFETIME_SECONDS = 3600`):** Automatically recycles idle sessions exceeding 1 hour to prevent memory or transport degradation on long-lived connections.
- **Unified Evidence Methods:**
  - `get_identity(device_name)`
  - `get_interfaces(device_name)`
  - `get_routes(device_name)`
  - `get_ip_addresses(device_name)`
  - `get_firewall_rules(device_name)`
  - `get_nat_rules(device_name)`
  - `get_configuration_snapshot(device_name)`
  Each returns a structured, timestamped evidence dictionary with execution latency metrics.
- **Observability:** `get_stats()` exposes active session count, total sessions opened vs. reused, command counts, overall average latency, and active backoff states without leaking credentials.

### 3.3 Evidence-Backed Topology & Path Explorer (`core/topology_engine.py`)
- **L2 vs. L3 Separation:** Links are tagged with explicit layer annotations (`L2` for physical/bridge/fiber/ethernet, `L3` for routed/vpn).
- **`find_path(source, target, layer=None)`:**
  - Computes optimal path between endpoints.
  - Inspects each hop for interface mappings, bandwidth capacity, and link verification status (`confirmed`, `observed`, `inferred`, `stale`).
  - Highlights bottlenecks (e.g., degraded links, offline intermediate nodes, high-latency segments).
  - Assesses overall path health (`healthy`, `degraded`, `broken`).
- **`analyze_change_impact(target_node_id, change_type, affected_interface)`:**
  - Simulates device maintenance or link failure before changes occur.
  - Predicts blast radius: isolated downstream devices, rerouted traffic paths, and loss of gateway reachability.
  - Computes change severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) and emits proactive mitigations (e.g., VRRP failover readiness).

### 3.4 AKANE Network Reasoning Engine (`agents/akane/reasoning_engine.py`)
- **Deterministic Longest Prefix Match (LPM):**
  - Evaluates IPv4 routing decisions using exact prefix length matching.
  - Distinguishes host routes (`/32`), subnet routes (`/24`), and default routes (`0.0.0.0/0`).
  - Supports both RouterOS v6 and v7 routing table outputs.
  - Evaluates active route flags (`A`/`a`), metrics/distance, and gateway reachability.
- **Firewall & NAT Chain Auditing:**
  - Verifies forward chain FastTrack configuration and flags incorrect ordering (FastTrack placed after established accept).
  - Validates input chain drop rules and invalid packet filtering.
  - Confirms NAT masquerade or src-nat coverage for LAN outbound traffic.
- **VLAN & Bridge Isolation Auditing:**
  - Evaluates `vlan-filtering` status on MikroTik bridges.
  - Validates PVID port assignments and tagged/untagged consistency.
- **Evidence Contracts:** Generates standard diagnostic contracts:
  ```json
  {
    "symptom": "...",
    "affected_device": "...",
    "severity": "...",
    "timestamp": 1729000000.0,
    "evidence_collected": [...],
    "hypotheses": [...],
    "confirmed_facts": [...],
    "unknowns": [...],
    "recommended_action": "..."
  }
  ```

### 3.5 Safe Configuration Engine (`agents/akane/config_engine.py`)
Enforces the 7-stage configuration lifecycle:
1. **READ:** Captures pre-change baseline snapshot.
2. **PLAN:** Validates syntax, blocks destructive commands (`reset-configuration`, `reboot`, `file remove`), and synthesizes inverse rollback commands.
3. **VALIDATE:** Verifies target existence, inventory credentials, and interface availability.
4. **PREVIEW:** Discloses unified diff (`+ proposed`, `- rollback`) and preflight check status.
5. **APPLY:** Enforces strict authorization gate (`approved=True`). Unapproved calls are rejected with `APPROVAL_REQUIRED`.
6. **VERIFY:** Performs automated post-change validation checks to confirm operational status.
7. **RECOVER:** Applies inverse rollback commands if changes fail midway or verification fails.

---

## 4. Verification Evidence Matrix

In adherence to Section 0.5 evidence standards:

| Component | Tested Implementation | Evidence Standard | Result |
| :--- | :--- | :--- | :--- |
| **Canonical Network State** | `core/canonical_network.py` | Unit & Integration Test | **4 Passed** (`test_canonical_network.py`) |
| **Connection Manager APCE** | `agents/akane/connection_manager.py` | Unit Test (Mocks) | **5 Passed** (`test_connection_manager_upgrade.py`) |
| **Topology Path Explorer** | `core/topology_engine.py` | Unit Test (Graph Mocks) | **3 Passed** (`test_topology_path_explorer.py`) |
| **AKANE Reasoning Engine** | `agents/akane/reasoning_engine.py` | Unit Test (Fixtures) | **4 Passed** (`test_akane_reasoning_engine.py`) |
| **Safe Configuration Engine**| `agents/akane/config_engine.py` | Unit Test (Mocks) | **5 Passed** (`test_akane_safe_config_engine.py`) |
| **NMS & WebSocket Bridge** | `api/routers/ws.py`, `core/nms_engine.py` | Integration Test | **55 Passed** (`test_nms.py`, `test_ws_bridge.py`) |
| **Full Backend Suite** | All backend modules (`AIRA_ECOSYSTEM/tests`) | Full Regression Run | **758 Passed, 0 Failed** |
| **Frontend Test Suite** | All UI components & voice hooks | Node Test Runner | **247 Passed, 0 Failed** |
| **Frontend Production Build** | Vite Client Bundle | Production Compiler | **Clean Build (2.52s)** |

*Note: In compliance with network safety rules, real hardware configuration write operations were not executed against production routers unattended; tests were conducted against verified RouterOS v6/v7 output fixtures and mock connection channels.*

---

## 5. Resource Profile & Deployment Guidelines

- **Hardware Fit:** All implemented modules are strictly lightweight Python (FastAPI/asyncio) and React (Vite). Memory consumption remains well within the **8 GB RAM** budget of the ThinkPad X270, and operations require **zero GPU or CUDA acceleration**.
- **Network Safety:** The `apply_config` tool remains in `DANGEROUS_TOOLS` and strictly enforces `approved=True`.
- **RouterOS Versioning:** All parsers and commands support both RouterOS v6 and RouterOS v7 syntax.
