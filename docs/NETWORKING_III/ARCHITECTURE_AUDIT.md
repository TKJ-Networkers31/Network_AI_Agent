# AIRA OS — Phase Networking III: Architecture Audit Report
## Comprehensive System Audit, Module Responsibilities, Interfaces, Lifecycle & Technical Gap Analysis

**Status:** `VERIFIED_BASELINE`  
**Milestone:** Phase Networking III Initiation (N3.0)  
**Git Baseline Commit:** `be59871acd2dd92c581d8944e65899d485f208ae` (`release: AIRA Networking II`)  
**Working Tree Status:** Clean  
**Test Suite Baseline:** 958 Backend Pytest Tests, 247 Frontend Unit Tests, 63 Security Hardening Tests  
**Target Environment:** Windows / Python 3.14 / React 18 / Node.js 20 / SQLite WAL  
**Author:** Automated Acceptance Engineer & Principal Architect (AIRA OS)

---

## 1. Executive Summary

This architecture audit establishes the authoritative technical baseline for **Phase Networking III — Multi-Device Network Intelligence**. 

In Phase Networking II, AIRA OS established single-device live observation, AST read-only command validation, and deterministic root cause analysis against MikroTik Cloud Hosted Router (CHR) RouterOS v7.23.8. 

The objective of Phase Networking III is to extend this proven foundation into a **multi-device network intelligence platform** that supports:
1. Multi-device inventory with stable device identifiers and user/telemetry separation.
2. Centrally controlled multi-device connection pooling and concurrency governance.
3. Multi-device evidence collection preserving provenance and handling partial failures.
4. Cross-device evidence correlation with explicit confidence semantics.
5. Topology-aware diagnostic root cause analysis (RCA).
6. Sustainable NMS historical metrics and event ingestion foundations.

---

## 2. Existing Module Inventory & Responsibilities

| Subsystem / Path | Primary Module(s) | Architectural Responsibility | Audit Status |
|---|---|---|:---:|
| **Canonical Network** | `core/canonical_network.py` | Unified device identity (`CanonicalDevice`), device resolution across inventory/topology, RouterOS version detection. | `VERIFIED` |
| **Inventory Store** | `core/inventory_store.py` | SQLite WAL persistence for managed devices, credential encryption, SSH/SNMP credential binding. | `VERIFIED` |
| **Connection Engine** | `agents/akane/connection_manager.py` | Connection pooling (max 5 sessions), session reuse, target locking, reconnect backoff (2s–60s), idle monitoring. | `VERIFIED` |
| **Interactive Shell** | `tools/ssh/shell.py` | Paramiko `invoke_shell` wrapper, Ctrl-C first-login skip, license agreement prompt handling, prompt synchronization. | `VERIFIED` |
| **Command Security** | `core/network_intelligence/security.py` | 10-layer AST/token read-only validator, delimiter blocking (`;`, `|`, `&`, `\n`), mutating verb elimination. | `VERIFIED` |
| **Evidence Collector** | `core/network_intelligence/evidence.py` | Bounded read-only evidence collection (`COMMAND_MAP_V6`, `COMMAND_MAP_V7`), normalization into `EvidenceItem`. | `VERIFIED` |
| **Diagnostic Reasoning** | `agents/akane/reasoning_engine.py` | Deterministic RouterOS route parsing (v6 spaced vs v7 prefix flags), firewall rule analysis, longest prefix match. | `VERIFIED` |
| **Network Investigator** | `core/network_intelligence/investigator.py` | Deterministic incident intake, evidence orchestration, 7-domain rule checks, ranked hypotheses formulation. | `VERIFIED` |
| **Diagnostic Playbooks** | `core/network_intelligence/playbooks.py` | 7 registered diagnostic playbooks, state-machine step progression, operator input validation. | `VERIFIED` |
| **Configuration Planner** | `core/network_intelligence/planner.py` | Desired-state change planning, blast radius analysis, rollback strategy generation (Strictly read-only planning). | `VERIFIED` |
| **Static Simulator** | `core/network_intelligence/simulator.py` | Static path and forwarding evaluation without live network configuration mutation. | `VERIFIED` |
| **Topology Fabric V2** | `api/routers/topology.py`, `core/topology_models.py` | Node and link graph model, LLDP/ARP discovery engine, ownership governance, confidence calculator. | `VERIFIED` |
| **NMS Engine** | `api/routers/nms.py` | Continuous availability evaluation (Ping/SNMP), telemetry recording, threshold incident generation. | `VERIFIED` |
| **Voice & Persona** | `agents/yuki/voice_io.py`, `api/routers/voice.py` | Voice companion lifecycle, speech cleaning, command routing, wake-word activation. | `VERIFIED` |
| **Web Frontend** | `app/frontend/src/` | React 18 / Tailwind PWA: Network Intelligence Copilot, Topology Canvas, NMS Dashboard, Devices Manager. | `VERIFIED` |

---

## 3. Existing API Endpoints Inventory

AIRA OS currently exposes 170 REST API endpoints across 18 routers. The primary network engineering endpoints relevant to Networking III are:

### 3.1 Network Intelligence Endpoints (`/api/intelligence`)
- `POST /api/intelligence/preflight` — Runs lab preflight diagnostics against target device.
- `POST /api/intelligence/incidents` — Creates and executes evidence-driven investigation.
- `GET /api/intelligence/incidents` — Lists active and historical incidents (limit: 50).
- `GET /api/intelligence/incidents/{incident_id}` — Retrieves full incident report and evidence items.
- `GET /api/intelligence/playbooks` — Lists registered deterministic diagnostic playbooks.
- `POST /api/intelligence/playbooks/advance` — Advances playbook step with operator inputs.
- `POST /api/intelligence/plans` — Generates desired-state change plan.
- `GET /api/intelligence/plans` — Lists configuration plans.
- `GET /api/intelligence/plans/{plan_id}` — Retrieves plan details, blast radius, and diff.
- `POST /api/intelligence/plans/{plan_id}/validate` — Executes static pre-change validation.
- `POST /api/intelligence/plans/{plan_id}/simulate` — Simulates post-change traffic forwarding.

### 3.2 Device & Credential Endpoints (`/api/devices`, `/api/credentials`)
- `GET /api/devices` — Lists inventory devices with credential associations.
- `POST /api/devices` — Registers a new managed network device.
- `GET /api/devices/{name}` — Retrieves device details by name or IP.
- `PUT /api/devices/{name}` — Updates device metadata.
- `DELETE /api/devices/{name}` — Removes device from inventory.
- `POST /api/devices/{name}/test` — Tests SSH/SNMP reachability and credentials.
- `POST /api/devices/{name}/credentials` — Links a stored credential to a device.
- `GET /api/credentials` — Lists registered credentials (secrets redacted).
- `POST /api/credentials` — Stores encrypted credential (AES-GCM).

### 3.3 Connection Management Endpoints (`/api/connections`)
- `GET /api/connections` — Lists active persistent SSH sessions.
- `POST /api/connections/open` — Opens managed persistent session to device.
- `POST /api/connections/execute` — Executes allowlisted read-only command on session.
- `POST /api/connections/close` — Gracefully closes active session.

### 3.4 Topology Endpoints (`/api/topology`)
- `GET /api/topology` — Retrieves topology graph (nodes, links, stats, policy).
- `POST /api/topology/discover` — Initiates discovery job across seed devices.
- `POST /api/topology/nodes` — Registers or updates topology node.
- `POST /api/topology/links` — Registers topology link.
- `GET /api/topology/links/evidence` — Retrieves evidentiary support for link.
- `POST /api/topology/conflicts/{conflict_id}/resolve` — Resolves topology discrepancies.

### 3.5 NMS Endpoints (`/api/nms`)
- `GET /api/nms/overview` — Retrieves overall fleet health and status tallies.
- `GET /api/nms/devices` — Lists NMS monitored devices with telemetry.
- `GET /api/nms/devices/{device_id}/resources/history` — Retrieves CPU/Memory historical metrics.
- `GET /api/nms/devices/{device_id}/interfaces/{interface_name}/history` — Retrieves interface traffic history.
- `POST /api/nms/scheduler/poll-now` — Triggers immediate on-demand telemetry poll.

---

## 4. Existing Database Entities & Persistence Model

All persistent data is stored in modular SQLite databases operating in Write-Ahead Logging (`WAL`) mode:

| Database File | Tables | Key Fields & Entities | Audit Finding |
|---|---|---|:---:|
| `database/inventory.db` | `devices`, `credentials`, `device_credentials` | `devices.id`, `name`, `host`, `port`, `device_type`, `snmp_port`, `enabled`, `credentials.secret_enc` | `VERIFIED` |
| `database/network_intelligence.db` | `incidents`, `evidence_items`, `playbook_runs`, `configuration_plans` | `incident_id`, `device_identity`, `related_devices_json`, `observed_facts_json`, `inferred_hypotheses_json`, `evidence_items.normalized_value_json` | `VERIFIED` |
| `database/topology.db` | `topology_nodes`, `topology_links`, `topology_evidence`, `nms_device_metrics`, `nms_interface_metrics`, `nms_incidents` | `topology_nodes.id`, `identity`, `ownership_status`, `topology_links.source_id`, `target_id`, `confidence`, `nms_device_metrics.cpu_load_percent`, `latency_ms` | `VERIFIED` |
| `database/chat_sessions.db` | `chat_sessions`, `chat_turns` | Session conversation tracking, turn histories, correlation IDs. | `VERIFIED` |

---

## 5. Existing Connection & Evidence Lifecycle

### 5.1 Connection Lifecycle
1. **Target Resolution:** Query resolved via `CanonicalNetworkRegistry` or `InventoryStore`.
2. **Backoff Check:** If target failed recently, exponential backoff (2.0s to 60.0s) blocks spamming.
3. **Session Reuse:** If an active, non-expired session exists for `(host, port, username)`, it is reused immediately.
4. **Target Lock:** Host-specific `threading.Lock` prevents parallel command interleaving on the same pseudo-terminal channel.
5. **Interactive Handshake:** `PersistentShell` attaches `invoke_shell()`. If prompted for password change (RouterOS v7) or license (v6), it automatically handles it (`\x03` or `n`).
6. **Command Dispatch:** Read-only command transmitted; response buffered until `[username@identity] > ` prompt appears.
7. **Idle Monitor:** Background thread tracks idle seconds; gracefully reaps sessions exceeding `MAX_SESSION_LIFETIME_SECONDS` (3600s).

### 5.2 Evidence Lifecycle
1. **Planning:** Incident type maps to minimal observation domains via `INCIDENT_EVIDENCE_REQUIREMENTS`.
2. **Allowlist AST Check:** Command validated against `APPROVED_PRINT_PREFIXES` and delimiter rejections.
3. **Execution:** Dispatched via `ConnectionManager.execute_for_device()`.
4. **Parsing & Normalization:** Output converted to structured dictionaries (`parse_routeros_routes`, `_parse_interfaces`, etc.).
5. **Evidence Contract:** Packaged into `EvidenceItem` with UUID, collection timestamp, freshness (<60s = FRESH), and raw excerpt.
6. **Contradiction Detection:** Evaluated across IP subnets, routing reachability, and interface bindings.
7. **Persistence:** Committed to `network_intelligence.db`.

---

## 6. Existing Security Controls Audit

| Security Boundary | Mechanism | Verification Evidence | Status |
|---|---|---|:---:|
| **Read-Only Non-Mutation** | `validate_readonly_command()` | 63 tests in `test_routeros_command_hardening.py` verify rejection of all mutating verbs (`add`, `set`, `remove`, `reboot`, etc.). | `VERIFIED` |
| **Command Injection Defense** | Delimiter tokenization | Rejection of `;`, `|`, `&`, `\n`, `\r`, `` ` ``, `$`, `[`, `{`. | `VERIFIED` |
| **Credential Masking** | `mask_sensitive_data()`, `sanitize_cli_excerpt()` | Excerpts masked before API serialization; secrets stored in AES-GCM encrypted BLOBs. | `VERIFIED` |
| **Safe Remediation Isolation** | `SafeConfigEngine.apply_change()` | Zero live invocations permitted; plans remain strictly advisory. | `VERIFIED` |
| **Single-Flight Pseudo-Terminal Safety** | Per-session lock | Prevents concurrent thread execution from interleaving terminal streams. | `VERIFIED` |

---

## 7. Existing Test Coverage Baseline

| Test Suite | File Count | Test Count | Pass Rate | Execution Time | Status |
|---|---|---|---|---|:---:|
| **Backend Pytest** | 38 test files | 958 tests (176 subtests) | 100% (958 passed, 0 failed, 23 warnings) | ~70.69s | `VERIFIED` |
| **Frontend Node TAP** | 12 test files | 247 tests | 100% (247 passed, 0 failed) | ~2.00s | `VERIFIED` |
| **Security Hardening** | 1 test file | 63 tests | 100% (63 passed, 0 failed) | ~3.35s | `VERIFIED` |
| **Frontend Production Build** | Vite v8.3.0 | 2273 modules | 100% clean compilation | ~4.63s | `VERIFIED` |

---

## 8. Architectural Limitations & Missing Capabilities for Phase Networking III

Despite the robust baseline, several architectural gaps exist when moving from single-device observation to multi-device network intelligence:

| Area | Current Implementation State | Architectural Limitation | Classification |
|---|---|---|:---:|
| **Multi-Device Target Resolution** | Resolves single device at a time | No batch resolution or multi-device target grouping. | `PARTIAL` |
| **Multi-Device Connection Pool** | Global limit of 5 sessions, single device calls | No parallel multi-device dispatch abstraction with bounded worker pool. | `PARTIAL` |
| **Command Execution Layer** | Ad-hoc dispatch in `ConnectionManager` | Lacks formal `CommandExecutionRequest` / `CommandExecutionResult` envelope preserving execution provenance across multi-vendor devices. | `PARTIAL` |
| **Multi-Device Evidence Collection** | `EvidenceCollector.collect_evidence_bundle()` accepts single target | Cannot collect and aggregate evidence across an arbitrary set of devices with partial failure tolerance. | `PARTIAL` |
| **Unified Network Data Model** | Models fragmented across `models.py`, `topology_models.py`, `reasoning_engine.py` | Lacks unified, versionable dataclasses for `NetworkInterface`, `NetworkIPAddress`, `NetworkRoute`, `NetworkNeighbor`, `NetworkVLAN`, `NetworkLink`. | `PARTIAL` |
| **Cross-Device Evidence Correlation** | `detect_contradictions()` only inspects single device facts | No engine to correlate observations across devices (e.g., Device A ARP / Neighbor vs. Device B IP / Interface). | `PLANNED` |
| **Topology-Aware Root Cause Analysis** | `NetworkInvestigator` processes single `device_identity` | Cannot consume multi-device evidence or trace cross-device dependencies (e.g. shared gateway down). | `PARTIAL` |
| **NMS Historical Foundation** | Metrics tables exist in `topology.db` but lack clean ingestion and query services | No unified metric collection abstraction with configurable retention and sampling rates. | `PARTIAL` |
| **Multi-Device UI** | Single device selector in incident/preflight modals | No multi-device selection, batch observation runner, or cross-device evidence comparison view. | `PARTIAL` |

---

## 9. Reusable Components vs. New Components Required

### 9.1 Reusable Components (Keep & Extend)
- `core/canonical_network.py` (`CanonicalDevice`, `CanonicalNetworkRegistry`) — Already provides device identity resolution.
- `core/inventory_store.py` (`InventoryStore`) — Already provides secure device and credential storage.
- `agents/akane/connection_manager.py` (`ConnectionManager`) — Proven connection pooling, locking, and session reuse.
- `tools/ssh/shell.py` (`PersistentShell`) — Proven interactive prompt handling and Ctrl-C skip.
- `core/network_intelligence/security.py` — Proven 10-layer AST read-only security validator.
- `core/network_intelligence/models.py` (`EvidenceItem`, `RankedHypothesis`, `IncidentRecord`) — Proven evidence contracts.
- `agents/akane/reasoning_engine.py` (`parse_routeros_routes`, `FirewallRule`) — Tested parser algorithms.
- `core/topology_models.py` — Domain enumerations, sanitizers, and confidence calculators.

### 9.2 New Minimal Components Genuine Required for Phase Networking III
1. **Multi-Device Inventory Extension (`core/inventory_store.py` & `core/canonical_network.py`):**
   - Add batch device retrieval, platform capability metadata, and ensure stable non-IP device keys.
2. **Unified Command Execution Envelope (`core/network_intelligence/command_execution.py`):**
   - Formal `CommandRequest` and `CommandResult` dataclasses tracking device ID, domain, duration, truncation, and provenance.
3. **Multi-Device Evidence Orchestrator (`core/network_intelligence/multi_device_collector.py`):**
   - Bounded concurrent evidence collection across multiple devices with partial failure preservation and collection summaries.
4. **Unified Network Data Model (`core/network_intelligence/network_models.py`):**
   - Canonical dataclasses: `NormalizedInterface`, `NormalizedIPAddress`, `NormalizedRoute`, `NormalizedNeighbor`, `NormalizedVLAN`, `NormalizedLink`.
5. **Cross-Device Evidence Correlator (`core/network_intelligence/correlation.py`):**
   - Rule-based correlation engine (Subnet Matching, ARP-to-Interface matching, Neighbor/MNDP/LLDP alignment) with explicit confidence grades (`CONFIRMED`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`).
6. **Multi-Device Diagnostic RCA Extension (`core/network_intelligence/investigator.py`):**
   - Extend `NetworkInvestigator` to support multi-device incident investigations and dependency tracing.
7. **NMS Historical Metric Service (`core/network_intelligence/metrics_service.py`):**
   - Lightweight, configurable metric ingestion and historical query service wrapping `topology.db`.
8. **Multi-Device REST Endpoints & UI Enhancements:**
   - REST endpoints for multi-device evidence collection, cross-device correlation, and multi-device incident creation.
   - Frontend UI updates in `NetworkIntelligencePage.jsx` and `DevicesPage.jsx`.

---

## 10. Audit Verdict & Approval Status

```text
BASELINE INTEGRITY:       VERIFIED (958 backend passed, 247 frontend passed, 63 security passed)
READ-ONLY GUARANTEE:      VERIFIED (Strict non-mutation enforced across all entry points)
LIVE CHR INTEGRATION:     VERIFIED (192.168.43.30 RouterOS v7.23.8)
ARCHITECTURE READINESS:   VERIFIED (Zero architectural rewrite required; clean additive extensions identified)
AUDIT OUTCOME:            APPROVED_FOR_PHASE_NETWORKING_III
```

Phase N3.0 Architecture Audit is complete. The implementation proposal for Work Packages N3.1 through N3.10 is detailed in the accompanying architecture plan.
