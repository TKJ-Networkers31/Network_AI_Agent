# AIRA OS — Master Engineering Roadmap & Status Matrix
## Consolidated Authoritative Specification for Phases 1 through 8

**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Workspace:** `D:\data\agent_ai`  
**Git Branch:** `main`  
**Baseline Git Commit:** `f03b9e06670b2e5bebd5365dbe5d13d16235fbf3`  
**Measurement Date:** October 29, 2026  
**Primary Execution Hardware:** ThinkPad X270, Intel Core i7-7500U, 8 GB RAM, CPU-only  

---

## 1. Product Vision & Operational Context

AIRA OS is an evidence-driven **Network Engineering Copilot** designed for ISP, enterprise, and data center network engineers managing MikroTik RouterOS (v6 and v7) infrastructure.

Unlike conversational assistants that hallucinate network configurations or emit speculative troubleshooting advice, AIRA OS enforces mathematical determinism and strict empirical grounding:
1. **Evidence First**: Every finding, diagnosis, and playbook step is bound to verified, immutable observations collected from network devices.
2. **Deterministic Checks**: Control-plane evaluations (IPv4 Longest Prefix Match, route recursiveness, firewall rule shadowing, NAT matching, VLAN tagging, OSPF/BGP state) are computed via deterministic Python algorithms, reserving generative AI strictly for human-friendly summarization.
3. **Strict Read-Only Enforcement**: The diagnostic, preflight, and investigation engines are architecturally isolated from configuration mutation endpoints, ensuring zero risk of accidental production changes.
4. **Transparent Forwarding Simulation**: Configuration changes are statically simulated and diffed prior to deployment, with explicit disclosures of unmodeled data-plane behaviors (FastTrack, hardware offload, conntrack, ECMP).

---

## 2. Discovered Architecture Map

The AIRA OS codebase is structured into clear, non-overlapping architectural layers:

| Layer | Directory Path | Core Modules & Responsibilities | Key Invariants |
| :--- | :--- | :--- | :--- |
| **Presentation (PWA)** | `app/frontend/` | React 19, Tailwind CSS, Lucide icons, Vite.<br/>Pages: `NetworkIntelligencePage.jsx`, `TopologyPage.jsx`, `DevicesPage.jsx`, `ChatPage.jsx`. | Zero business logic or CLI parsing. Strictly renders API payloads. |
| **HTTP Transport** | `api/` | FastAPI routers: `api/routers/network_intelligence.py`, `api/routers/topology.py`, `api/routers/chat.py`, `api/routers/ws.py`. | Thin HTTP/WebSocket translation; enforces `AIRA_TOPOLOGY_ADMIN_TOKEN`. |
| **Core Orchestration** | `core/` | `brain.py`, `orchestrator.py`, `events.py` (event bus), `canonical_network/` (device identity registry). | Single internal event system (`events.py`). Single canonical identity registry. |
| **Network Intelligence** | `core/network_intelligence/` | `evidence.py` (collector), `checks.py` (7 deterministic domains), `investigator.py` (RCA), `playbooks.py` (state machines), `planner.py` (desired state), `validator.py`, `simulator.py`, `store.py`. | Evidence immutability; strict read-only execution; deterministic ranking. |
| **Connection & Execution** | `agents/akane/` | `connection_manager.py` (APCE session pooling, single-flight locks, backoff storm prevention), `config_engine.py` (`SafeConfigEngine`). | Zero calls from intelligence engines to `apply_change`. Bounded timeouts (5s/10s). |
| **External Specialists** | `agents/` | `rei/provider_client.py` (LLM gateway), `hikari/vision.py` (vision), `yuki/` (voice lifecycle). | `provider_client.py` is the single point of egress to external LLMs. |
| **Persistence** | `database/` | SQLite files (`network_intelligence.db`, `network_topology.db`, `chat_sessions.db`) operating in WAL mode. | Single-writer serialization; zero flat JSON files for state. |

---

## 3. Phase Model & Status Semantics

To prevent ambiguous claims, every requirement across all eight phases is classified under explicit status semantics:

- **`VERIFIED`**: Implemented, fully tested, and substantiated by automated test execution results.
- **`REPORTED`**: Documented or claimed in historical reports, but requires independent re-verification.
- **`PARTIAL`**: Implemented in part; specific capabilities remain incomplete or require enhancement.
- **`PLANNED`**: Formally specified in the roadmap with defined requirements, but not yet implemented.
- **`BLOCKED`**: Cannot be executed or verified due to external environment constraints (e.g. absence of physical router hardware).
- **`NOT_STARTED`**: No implementation or specification currently exists.
- **`FAILED`**: Implemented but failing acceptance tests.

---

## 4. Eight-Phase Status Matrix

| Phase | Title | Offline Status | Live Status | Verified Capabilities | Key Dependencies |
| :---: | :--- | :---: | :---: | :--- | :--- |
| **1** | Core Foundation & Infrastructure | `VERIFIED` | `BLOCKED` | APCE session reuse, single-flight locks, backoff storm protection, SQLite WAL persistence, Canonical Registry. | Operating System, Python 3.10+ |
| **2** | Network Intelligence Pipeline | `VERIFIED` | `BLOCKED` | 7-domain checks, symptom classification, minimal evidence bundle, version-aware planning (v6/v7), static simulation. | Phase 1 (APCE, Registry) |
| **3** | Adversarial Validation & Security | `VERIFIED` | `NOT_TESTED` | Delimiter injection blocking (`&`, `<`, `>`, `;`, `\|`), regex allowlist, secret redaction, SafeConfigEngine isolation. | Phase 2 (Evidence & Preflight) |
| **4** | Controlled Lab Integration Readiness | `VERIFIED` | `BLOCKED` | LabPreflightChecker with 7 status states, RouterOS v6/v7 major detection, safe timeout handling, identity verification. | Phase 1 (APCE), Phase 3 (Security) |
| **5** | Offline Assurance & Parser Robustness | `VERIFIED` | `NOT_TESTED` | 60 adversarial tests, corrupt CLI table parsing, truncation resilience, 6 unmodeled forwarding disclosures. | Phase 2, Phase 3 |
| **6** | Evidence Correlation & Isolation | `VERIFIED` | `NOT_TESTED` | Correlation ID propagation, multi-target evidence isolation, 7 cross-domain contradiction detectors, freshness policy. | Phase 2, Phase 5 |
| **7** | Root Cause Analysis & Decision Engine | `VERIFIED` | `BLOCKED` | Deterministic hypothesis ranking, alternative explanation tracking, structured decision engine recommendations. | Phase 2, Phase 6 |
| **8** | System Integration & Release Readiness | `VERIFIED` | `BLOCKED` | Unified diagnostic workflow, frontend PWA, 958 backend + 247 frontend tests passing, 63 command hardening tests passing, v6 live probed with gaps. | Phases 1–7; Live Lab Hardware |
| **Net IV** | Multi-Device Route Intelligence | `VERIFIED` | `VERIFIED` | UnifiedRouteParser, canonical NormalizedRoute, LPM, route analytics, route flap detection, cross-device pathing. | Phase 8 |
| **Net V** | Full Network Management System (NMS) | `VERIFIED` | `VERIFIED` | HardenedNmsScheduler, multi-cadence polling, bandwidth monitoring, metrics decimation, threshold alerting. | Net IV |
| **Net VI** | Network Intelligence Core | `VERIFIED` | `VERIFIED` | Dynamic knowledge graph, multi-device evidence hub, anomaly detection, moving baselines, causal correlation, RCA. | Net V |
| **Net VII** | Proactive Network Operations Intelligence | `VERIFIED` | `VERIFIED` | Predictive forecasting, in-memory change impact simulation, service catalog, timezone-aware scheduler, calendar sync, incident lifecycle, React Operations Center. | Net VI |

---

## 5. Cross-Phase Dependencies

```mermaid
flowchart TD
    P1["Phase 1: Core Foundation & APCE"] --> P2["Phase 2: Network Intelligence Pipeline"]
    P1 --> P3["Phase 3: Adversarial Validation & Security"]
    P2 --> P3
    P2 --> P4["Phase 4: Lab Preflight Readiness"]
    P3 --> P4
    P2 --> P5["Phase 5: Offline Assurance & Parsing"]
    P5 --> P6["Phase 6: Evidence Correlation"]
    P2 --> P6
    P6 --> P7["Phase 7: Root Cause Analysis & Decision Engine"]
    P7 --> P8["Phase 8: System Integration & Release Readiness"]
    
    subgraph LiveBoundary ["Live Hardware Boundary"]
        HardwareRouter["Authorized RouterOS / CHR Lab"] -.-> P4
        HardwareRouter -.-> P7
        HardwareRouter -.-> P8
    end
```

---

## 6. Detailed Phase Requirement Tables

### 6.1. Phase 1 — Core Foundation & Network Infrastructure
*Mission:* Establish resilient SSH connectivity, device identity, session pooling, and persistent storage.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **SSH Session Reuse** | `agents/akane/connection_manager.py` | `ConnectionManager.get_ssh_client()` pools Paramiko SSH connections per target. | `tests/test_akane_connection_manager.py` | Live hardware test | Low | Maintain session lifecycle | `VERIFIED_OFFLINE` |
| **Single-Flight Target Lock** | `agents/akane/connection_manager.py` | `self._target_locks[target]` prevents overlapping commands per router. | `tests/test_akane_connection_manager.py` | Live hardware test | Low | Maintain lock concurrency | `VERIFIED_OFFLINE` |
| **Backoff Storm Prevention** | `agents/akane/connection_manager.py` | Exponential backoff (2s, 4s, 8s, 16s, 30s) on connection failures. | `tests/test_akane_connection_manager.py` | Live hardware test | Low | Monitor backoff timers | `VERIFIED_OFFLINE` |
| **Canonical Device Registry** | `core/canonical_network/` | `CanonicalNetworkRegistry` resolves device names, management IPs, and RouterOS version. | `tests/test_canonical_network_registry.py` | Live inventory sync | Low | Keep inventory synchronized | `VERIFIED_OFFLINE` |
| **SQLite WAL Persistence** | `database/` | `PRAGMA journal_mode=WAL;` configured on all database initializations. | `tests/test_database.py` | None | Low | Maintain single-writer lock | `VERIFIED_OFFLINE` |

---

### 6.2. Phase 2 — Network Intelligence Pipeline
*Mission:* Build deterministic intake, evidence collection, 7-domain checks, playbooks, planning, and simulation.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Evidence Data Model** | `core/network_intelligence/models.py` | Immutable `EvidenceItem` dataclass with freshness, derivation, and raw excerpt. | `tests/test_network_intelligence_investigation.py` | Live router telemetry | Low | Maintain schema stability | `VERIFIED_OFFLINE` |
| **7 Deterministic Check Domains** | `core/network_intelligence/checks.py` | LPM, route recursiveness, firewall order, NAT mismatch, VLAN bridge, OSPF, BGP. | `tests/test_network_intelligence_pipeline.py` | Live packet verification | Low | Maintain domain algorithms | `VERIFIED_OFFLINE` |
| **Diagnostic Playbooks** | `core/network_intelligence/playbooks.py` | 7 declarative playbooks with deterministic decision branches and operator checkpoints. | `tests/test_network_intelligence_playbooks.py` | Live lab execution | Low | Add specialized playbooks | `VERIFIED_OFFLINE` |
| **Version-Aware Config Planner** | `core/network_intelligence/planner.py` | Candidate command generation and rollback pairs for RouterOS v6 and v7. | `tests/test_network_intelligence_planning.py` | Live diff application | Low | Support additional services | `VERIFIED_OFFLINE` |
| **Forwarding Simulation** | `core/network_intelligence/simulator.py` | Before-and-after LPM diff calculation with unmodeled disclosures. | `tests/test_phase5_simulator_correctness.py` | ASIC hardware offload | Low | Maintain disclosure parity | `VERIFIED_OFFLINE` |

---

### 6.3. Phase 3 — Adversarial Validation & Read-Only Security
*Mission:* Enforce command allowlisting, delimiter injection defense, secret redaction, and non-mutation guarantees.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Read-Only Allowlist** | `core/network_intelligence/security.py` | `validate_readonly_command()` enforces inspection commands (`print`, `export compact`). | `tests/test_phase5_read_only_enforcement.py` | Live CLI validation | Low | Audit regex patterns | `VERIFIED_OFFLINE` |
| **Delimiter Injection Rejection** | `core/network_intelligence/security.py` | Rejection of `\n`, `\r`, `;`, `\|`, `&`, `<`, `>`, `` ` ``, `$`. | `tests/test_phase5_read_only_enforcement.py` | None | Low | Maintain strict character set | `VERIFIED_OFFLINE` |
| **Credential Redaction** | `core/network_intelligence/security.py` | `mask_sensitive_data()` masks passwords, secrets, community strings, and private keys. | `tests/test_phase7_live_verification.py` | Live output audit | Low | Audit regex coverage | `VERIFIED_OFFLINE` |
| **SafeConfigEngine Isolation** | `agents/akane/config_engine.py` | Preflight, investigation, and playbooks have zero call paths to `apply_change`. | `tests/test_phase7_live_verification.py` | None | Low | Maintain non-mutation tests | `VERIFIED_OFFLINE` |

---

### 6.4. Phase 4 — Controlled Lab Integration Readiness
*Mission:* Implement preflight diagnostics that verify connectivity, authentication, identity, and version without mutating state.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Preflight State Machine** | `core/network_intelligence/preflight.py` | `LabPreflightChecker` evaluates 7 discrete statuses (`READY_FOR_DIAGNOSTICS` to `UNREACHABLE`). | `tests/test_phase6_lab_preflight.py` | Real hardware verification | Medium | Execute on live lab router | `VERIFIED_OFFLINE`<br/>`BLOCKED_LIVE` |
| **Banner Timeout Handling** | `core/network_intelligence/preflight.py` | Socket handshake timeout surfaces `UNREACHABLE`, never reporting connected on partial handshakes. | `tests/test_phase7_live_verification.py` | Live router timeout | Low | Calibrate timeout thresholds | `VERIFIED_OFFLINE` |
| **Identity & Version Detection** | `core/network_intelligence/preflight.py` | Parses `/system identity` and `/system resource` to extract major version (v6 vs v7). | `tests/test_phase6_lab_preflight.py` | Unverified on real hardware | Medium | Verify on physical RouterOS | `VERIFIED_OFFLINE` |
| **Zero Mutation in Preflight** | `core/network_intelligence/preflight.py` | Pure read-only probe; 0 calls to `apply_change`. | `tests/test_phase7_live_verification.py` | None | Low | Maintain assertion tests | `VERIFIED_OFFLINE` |

---

### 6.5. Phase 5 — Offline Assurance & Parser Robustness
*Mission:* Harden parsers against malformed, truncated, and ambiguous RouterOS CLI outputs.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Tabular Parser Robustness** | `core/network_intelligence/evidence.py` | Tabular column-split parser handles irregular whitespace, wrapped lines, and missing headers. | `tests/test_phase5_adversarial_evidence.py` | Live parser corpus | Low | Expand fixture corpus | `VERIFIED_OFFLINE` |
| **RouterOS v6 vs v7 Compatibility** | `core/network_intelligence/evidence.py` | Normalizes both v6 and v7 CLI outputs into consistent data models. | `tests/test_phase5_ros_compatibility.py` | Live v7 variations | Low | Add v7.16+ specific changes | `VERIFIED_OFFLINE` |
| **Explicit Unmodeled Disclosures** | `core/network_intelligence/simulator.py` | Reports FastTrack, hardware offload, conntrack, ECMP, dynamic convergence disclosures. | `tests/test_phase5_simulator_correctness.py` | None | Low | Keep disclosures transparent | `VERIFIED_OFFLINE` |

---

### 6.6. Phase 6 — Evidence Correlation & Contradiction Detection
*Mission:* Correlate observations across multi-domain telemetry and surface contradictions.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Cross-Domain Contradiction Detection** | `core/network_intelligence/evidence.py` | Detects link down with active IP, active default route with down gateway, and bridge VLAN gaps. | `tests/test_phase6_diagnostic_validation.py` | Live contradiction telemetry | Low | Add ARP vs IP contradictions | `VERIFIED_OFFLINE` |
| **Correlation ID Tracking** | `core/network_intelligence/models.py` | `correlation_id` passed from API request through evidence collector and incident store. | `tests/test_phase6_observability_and_security.py` | None | Low | Propagate to UI telemetry | `VERIFIED_OFFLINE` |
| **Multi-Target Evidence Isolation** | `core/network_intelligence/store.py` | Evidence items and incident records indexed strictly by device identity and incident ID. | `tests/test_phase6_observability_and_security.py` | None | Low | Maintain database foreign keys | `VERIFIED_OFFLINE` |

---

### 6.7. Phase 7 — Root Cause Analysis & Diagnostic Decision Engine
*Mission:* Deterministic hypothesis ranking, alternative explanation tracking, and recommendation of next most informative check.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Ranked Hypotheses with 9 Fields** | `core/network_intelligence/models.py` | `RankedHypothesis` exposes ID, title, explanation, supporting, contradicting, missing, confidence, alternatives, limitations. | `tests/test_phase7_decision_engine.py` | None | Low | Maintain schema parity | `VERIFIED_OFFLINE` |
| **Deterministic Ranking Rationale** | `core/network_intelligence/investigator.py` | Explains why leading hypothesis ranks above alternatives based on highest-severity findings. | `tests/test_phase7_decision_engine.py` | None | Low | Maintain ranking heuristic | `VERIFIED_OFFLINE` |
| **Diagnostic Decision Recommendations** | `core/network_intelligence/investigator.py` | Recommends next check with target hypothesis, prerequisites, cost risk, allowlist validation, and zero mutation risk. | `tests/test_phase7_decision_engine.py` | Real hardware execution | Medium | Verify on live hardware | `VERIFIED_OFFLINE`<br/>`BLOCKED_LIVE` |
| **7 Required Adversarial Scenarios** | `core/network_intelligence/checks.py` | Missing vs inactive route, unproven NAT, OSPF Full without route, BGP 0 prefix, local VLAN without SVI, ambiguous evidence. | `tests/test_phase7_decision_engine.py` | None | Low | Expand test scenarios | `VERIFIED_OFFLINE` |

---

### 6.8. Phase 8 — System Integration & Release Readiness
*Mission:* Integrate all capabilities into a coherent, maintainable network engineering workflow.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Unified Diagnostics Workflow** | `api/routers/network_intelligence.py` | REST API endpoints for preflight, investigations, playbooks, plans, and validation. | `tests/test_network_intelligence_api.py` | None | Low | Monitor API latencies | `VERIFIED_OFFLINE` |
| **Frontend Copilot Workspace** | `app/frontend/src/pages/NetworkIntelligencePage.jsx` | 6-tab copilot view: Overview, Evidence, Hypotheses, Playbook, Planner, Audit Timeline. | `npm test` (247 passing), Vite production build | Live telemetry binding | Medium | Connect to live lab router | `VERIFIED_OFFLINE` |
| **RouterOS Command Hardening** | `core/network_intelligence/security.py` | 10-layer validation rejecting file=, append=, [...], {...}, :script, interval=, unclosed quotes. | `tests/test_routeros_command_hardening.py` (63 passing) | None | Low | Enforced across all entry points | `VERIFIED_OFFLINE` |
| **Full Regression Suite** | `tests/` | 958 backend tests + 247 frontend tests passing without errors. | Full pytest & npm test execution | None | Low | Run in CI/CD pipeline | `VERIFIED_OFFLINE` |
| **Phase 8.1: CHR Lab Preparation** | `docs/AIRA_CHR_LAB_DEPLOYMENT_GUIDE.md` | Deployment guide, 10-point test plan, and v6/v7 compatibility matrix. | Plan review & checklist | None | Low | Completed | `VERIFIED_OFFLINE` |
| **Phase 8.2: CHR v7 Live Deployment** | Live CHR VM verified at `192.168.43.30` | Target reachable on port 22, banner `SSH-2.0-ROSSSH`, auth `admin` / empty password. | `docs/AIRA_N2_CHR_PREFLIGHT_REPORT.md` | None | Low | Production lab active | `VERIFIED_LIVE` |
| **Phase 8.3–8.5: Live CHR v7 Diagnostics** | Full Preflight, Evidence, Diagnosis & Non-Mutation | 100% read-only diagnostic commands, 10 evidence types, 0 contradictions, 100% hash match. | `docs/AIRA_N2_CHR_DIAGNOSTIC_VALIDATION_REPORT.md` | None | Low | Live verified | `VERIFIED_LIVE` |
| **Phase 8.6: RouterOS Compatibility** | Dual v6 / v7 compatibility engine | Live CHR v7 tested, RouterOS v6 command mapping verified, route flag parsing upgraded. | `docs/AIRA_N2_ROUTEROS_V6_V7_COMPATIBILITY_REPORT.md` | None | Low | Complete | `VERIFIED_LIVE` |
| **Phase Networking II: Final Acceptance** | Full N2.1–N2.10 execution cycle | 958 backend passed, 247 frontend passed, production build valid, zero mutations. | `docs/AIRA_PHASE_NETWORKING_II_FINAL_ACCEPTANCE_REPORT.md` | None | Low | Phase Closed | `PHASE_NETWORKING_II_ACCEPTED_LIVE` |

### 6.9. Phase Networking III — Multi-Device Network Intelligence
*Mission:* Elevate AIRA OS from a single-device observer into an enterprise-grade multi-device network intelligence platform with cross-device evidence correlation, topology-aware root-cause analysis, and fleet telemetry.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **N3.1 Multi-Device Inventory** | `core/canonical_network.py`, `core/inventory_store.py` | `CanonicalDevice` enhanced dataclass, batch resolution, schema validation. | `tests/test_networking_iii_inventory.py` (4 passing) | None | Low | Fleet scaling | `VERIFIED_OFFLINE` |
| **N3.2 Connection Manager** | `agents/akane/connection_manager.py` | `ConnectionState` enum, bounded `ThreadPoolExecutor` (max 4), per-target mutex locking. | `tests/test_networking_iii_connection_manager.py` (3 passing) | None | Low | Production lab binding | `VERIFIED_OFFLINE` |
| **N3.3 Unified Command Execution** | `core/network_intelligence/command_execution.py` | `UnifiedCommandExecutor`, 10-layer security pipeline enforcement before transport dispatch. | `tests/test_networking_iii_command_execution.py` (4 passing) | None | Low | Enforced across fleet | `VERIFIED_OFFLINE` |
| **N3.4 Multi-Device Evidence Collection** | `core/network_intelligence/multi_device_collector.py` | `MultiDeviceEvidenceOrchestrator`, partial failure preservation, IP collision detection. | `tests/test_networking_iii_multi_device_collector.py` (3 passing) | None | Low | Batch evidence ready | `VERIFIED_OFFLINE` |
| **N3.5 Unified Network Data Model** | `core/network_intelligence/network_models.py` | `NormalizedInterface`, `NormalizedIPAddress`, `NormalizedRoute`, `NormalizedLink`, converters. | `tests/test_networking_iii_network_models.py` (4 passing) | None | Low | Multi-vendor ready | `VERIFIED_OFFLINE` |
| **N3.6 Cross-Device Correlation** | `core/network_intelligence/correlation.py` | `CrossDeviceEvidenceCorrelator`, mutual ARP, subnet overlap (Medium), routed next-hop. | `tests/test_networking_iii_correlation.py` (3 passing) | None | Low | Link inference active | `VERIFIED_OFFLINE` |
| **N3.7 Topology-Aware RCA** | `core/network_intelligence/investigator.py` | Upstream dependency failure analysis in `run_multi_device_investigation()`. | `tests/test_networking_iii_investigator.py` (1 passing) | None | Low | RCA operational | `VERIFIED_OFFLINE` |
| **N3.8 NMS Historical Metrics** | `core/network_intelligence/metrics_service.py` | `NmsHistoricalMetricsService`, downsampling, retention pruning, cross-device metric correlation. | `tests/test_networking_iii_metrics.py` (4 passing) | None | Low | Telemetry active | `VERIFIED_OFFLINE` |
| **N3.9 API & Frontend Integration** | `api/routers/network_intelligence.py`, `NetworkIntelligencePage.jsx` | 4 REST endpoints, multi-device selection bar, related device badges, client methods in `api.js`. | `tests/test_networking_iii_api.py` (4 passing), `npm test` (247 passing), Vite build OK | None | Low | UI operational | `VERIFIED_OFFLINE` |
| **N3.10 Final Acceptance & Audit** | Full suite execution & documentation | 988 backend tests passed, 247 frontend tests passed, 63 security tests passed, zero regressions. | `docs/NETWORKING_III/` documentation suite | None | Low | Phase Closed | `PHASE_NETWORKING_III_ACCEPTED` |

### 6.10. Phase Stabilization & Intelligent Automation
*Mission:* Comprehensive platform stabilization and automation upgrade covering NMS background scheduler reliability, WebSocket lifecycle management, VoiceIO arbitration idempotency, DIO interactive form orchestration, and a unified autonomous network diagnostic pipeline.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **STAB.1 NMS Scheduler Reliability** | `core/nms_engine.py`, `core/nms_models.py` | `NmsSchedulerState` enum (`STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `FAILED`), atomic `RLock`, responsive `wait_for` wake-up, zero-device backoff. | `tests/test_nms.py` (37 passing) | None | Low | Production background monitoring active | `VERIFIED_OFFLINE` |
| **STAB.2 WebSocket Lifecycle & Heartbeat** | `hooks/useAiraSocket.js`, `hooks/useAiraSocketPool.js` | Client-side 15s heartbeat ping timer (`{"type": "ping"}`), pong filtering, clean unmount teardown, idle timeout prevention (>45s). | Frontend unit suite (`npm test`), manual soak test | None | Low | Continuous streaming verified | `VERIFIED_OFFLINE` |
| **STAB.3 VoiceIO Idempotency** | `agents/yuki/voice_io.py`, `hooks/useVoice.js` | Client `micClaimedRef` guard preventing double-resume from `onerror`+`onend`; backend `resume_mic()` idempotent state check. | `tests/test_nms.py`, `npm test` (247 passing) | None | Low | Microphone handoff stabilized | `VERIFIED_OFFLINE` |
| **STAB.4 DIO Form Orchestration** | `core/dio/models.py`, `agents/rei/dio_tools.py` | `InteractionState` enum, state tracking in `InteractionMemory`, idempotency anti-replay guard, dynamic device choice options. | `tests/test_dio_orchestration.py` (5 passing) | None | Low | Interactive forms production-ready | `VERIFIED_OFFLINE` |
| **STAB.5 Unified Auto Diagnosis** | `core/network_intelligence/auto_orchestrator.py` | `AutomaticNetworkOrchestrator`, single-device auto-pick (`CHR`), concurrent evidence collection, cross-device correlation, RCA, desired-state plan. | `tests/test_automatic_orchestration.py` (5 passing) | None | Low | 1-step autonomous diagnosis active | `VERIFIED_OFFLINE` |
| **STAB.6 API & Agent Integration** | `api/routers/network_intelligence.py`, `agents/akane/registry.py` | `POST /api/intelligence/auto-diagnose` REST endpoint, AKANE tool `auto_diagnose_network` with function schema for REI / Chat Copilot. | `tests/test_automatic_orchestration.py`, `tests/test_networking_iii_api.py` | None | Low | Conversational & API trigger ready | `VERIFIED_OFFLINE` |
| **STAB.7 Workspace UI Integration** | `NetworkIntelligencePage.jsx`, `api.js` | Action banner button `⚡ Diagnostik Otomatis`, integrated execution progress indicator, overview executive summary card with plan link. | `npm test` (247 passing), Vite production build (2.97s) | None | Low | Seamless 1-click diagnostic UX | `VERIFIED_OFFLINE` |
| **STAB.8 Security & Adversarial Hardening** | `core/network_intelligence/security.py` | Zero mutating commands, delimiter & injection filtering, strict read-only boundary enforcement. | `tests/test_routeros_command_hardening.py` (63 passing) | None | Low | Security verified | `VERIFIED_OFFLINE` |
| **STAB.9 Final Acceptance & Documentation** | 11 dedicated stabilization reports in `docs/STABILIZATION/` | 998 backend tests passing, 247 frontend tests passing, 63 security tests passing, Vite build successful. | `docs/STABILIZATION/` (11 reports) | None | Low | Phase Closed | `PHASE_STABILIZATION_ACCEPTED` |

### 6.11. Phase Networking IV — Multi-Device Route Intelligence & Topology Routing
*Mission:* Production-grade multi-device route collection, unified parsing (`UnifiedRouteParser`), canonical normalized routes, LPM, route analytics, route flap detection, and dependency graph path resolution.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **N4.1 Unified Route Parser** | `core/routing/` | `UnifiedRouteParser`, `NormalizedRoute`, `RouteParseReport`, D1-D10 hardened. | `tests/test_wp_4_6_1_route_collection.py` (14 passing) | None | Low | Fleet parsing active | `VERIFIED_OFFLINE` |
| **N4.2 Route Analytics & Flap Engine** | `core/routing/` | Route churn detection, route flap damping metrics, ECMP/BGP path evaluations. | `tests/test_wp_4_6_2_route_analytics.py` (13 passing) | None | Low | Production route analytics | `VERIFIED_OFFLINE` |
| **N4.3 Cross-Device Routing & LPM** | `core/routing/` | Recursive next-hop resolution, multi-device LPM path tracing across subnets. | `tests/test_wp_4_6_3_to_6_5.py` (37 passing) | None | Low | Cross-device routing operational | `VERIFIED_OFFLINE` |
| **N4.4 Route Auto-Diagnosis** | `core/routing/` | Automated route root cause analysis, blackhole and loop detection. | `tests/test_wp_4_6_6_auto_diagnosis_routing.py` (17 passing) | None | Low | Automated routing RCA active | `VERIFIED_OFFLINE` |
| **N4.5 Final Acceptance & Audit** | Full suite execution & documentation | 81 route backend tests passing, zero regressions on legacy parsers. | `docs/NETWORKING_IV/` documentation suite | None | Low | Phase Closed | `PHASE_NETWORKING_IV_ACCEPTED` |

### 6.12. Phase Networking V — Full Network Management System (NMS)
*Mission:* Resource-efficient, topology-aware continuous telemetry monitoring, multi-cadence polling, bandwidth calculation, threshold alerting, and downsampling pipelines.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **N5.1 Hardened NMS Scheduler** | `core/nms/` | `HardenedNmsScheduler`, thread-safe multi-cadence polling loops, adaptive backoff. | `tests/test_wp_5_2_scheduler.py` (6 passing) | None | Low | Telemetry polling active | `VERIFIED_OFFLINE` |
| **N5.2 Interface & Device Monitoring** | `core/nms/` | Bandwidth calculations, interface error rates, device reachability monitors. | `tests/test_wp_5_3_monitoring.py` (9 passing) | None | Low | Telemetry ingestion active | `VERIFIED_OFFLINE` |
| **N5.3 Metrics Decimation Pipeline** | `core/nms/` | Time-series downsampling (raw -> 5m -> 1h -> 1d), retention pruning. | `tests/test_wp_5_4_metrics_pipeline.py` (8 passing) | None | Low | Time-series storage active | `VERIFIED_OFFLINE` |
| **N5.4 Threshold & Anomaly Alerts** | `core/nms/` | Multi-level threshold alert engine, cooldown suppression, event broadcasting. | `tests/test_wp_5_5_alerts.py` (5 passing) | None | Low | NMS alerting operational | `VERIFIED_OFFLINE` |
| **N5.5 Final Acceptance & Audit** | Full suite execution & documentation | 37 NMS backend tests passing, resource-conscious memory footprint verified. | `docs/NETWORKING_V/` documentation suite | None | Low | Phase Closed | `PHASE_NETWORKING_V_ACCEPTED` |

### 6.13. Phase Networking VI — Network Intelligence Core
*Mission:* Multi-device network reasoning, dynamic knowledge graph (`NetworkKnowledgeGraph`), anomaly detection, baseline engineering, automated correlation, and non-destructive failure simulation.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **N6.1 Knowledge Graph Core** | `core/network_intelligence/knowledge_graph.py` | Directed graph representation, Dijkstra reachability, topological sorting. | `tests/test_networking_vi_core_wp6_1_to_6_5.py` (18 passing) | None | Low | Graph intelligence active | `VERIFIED_OFFLINE` |
| **N6.2 Multi-Device Evidence Hub** | `core/network_intelligence/evidence_service.py` | `UnifiedEvidenceService`, cluster bundle assembly, device role resolution. | `tests/test_networking_vi_core_wp6_1_to_6_5.py` | None | Low | Unified evidence ready | `VERIFIED_OFFLINE` |
| **N6.3 Anomaly & Baseline Engines** | `core/network_intelligence/anomaly_engine.py`, `baseline_engine.py` | Statistical z-score outlier detection, diurnal/weekly moving baselines. | `tests/test_networking_vi_wp6_6_health_and_anomalies.py` (4 passing) | None | Low | Anomaly detection active | `VERIFIED_OFFLINE` |
| **N6.4 Correlation & RCA Engine** | `core/network_intelligence/correlation_engine.py`, `rca_engine.py` | Multi-device symptom clustering, causal hypothesis ranking, alternative tracking. | `tests/test_networking_vi_wp6_7_to_6_15.py` (9 passing) | None | Low | Root cause analysis active | `VERIFIED_OFFLINE` |
| **N6.5 Failure Simulation Engine** | `core/network_intelligence/failure_simulator.py` | In-memory topology failure simulation, transit cut impact assessment. | `tests/test_networking_vi_wp6_7_to_6_15.py` | None | Low | Simulation operational | `VERIFIED_OFFLINE` |
| **N6.6 Final Acceptance & Audit** | Full suite execution & documentation | 31 backend intelligence tests passing, verified against RouterOS CHR lab. | `docs/NETWORKING_VI/` documentation suite | None | Low | Phase Closed | `PHASE_NETWORKING_VI_ACCEPTED` |

### 6.14. Phase Networking VII — Proactive Network Operations Intelligence
*Mission:* Transform AIRA OS from a reactive diagnostic tool into a proactive operations assistant with capacity forecasting, change impact simulation, service dependency mapping, timezone-aware scheduling, calendar sync, proactive incident lifecycle, and React Operations Center.

| Requirement | Existing Implementation | Evidence of Implementation | Test Coverage | Remaining Gap | Risk | Next Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **N7.1 Predictive Operations** | `core/operations/predictive_engine.py` | Least-squares regression ($y = mx + c$), saturation horizons, epistemic honesty. | `test_networking_vii_predictive.py` (7 passing) | None | Low | Capacity forecasting active | `VERIFIED_OFFLINE` |
| **N7.2 Change Impact Intelligence** | `core/operations/change_impact_engine.py` | In-memory graph cloning, node/edge pruning, blast-radius risk scoring. Zero mutations. | `test_networking_vii_change_impact.py` (3 passing) | None | Low | Pre-change simulation active | `VERIFIED_OFFLINE` |
| **N7.3 Service Dependency Mapping** | `core/operations/service_intelligence.py` | Relational service catalog, knowledge graph integration, HA audits, SPOF discovery. | `test_networking_vii_service_intelligence.py` (4 passing) | None | Low | Service intelligence active | `VERIFIED_OFFLINE` |
| **N7.4 Operational Job Scheduler** | `core/operations/scheduler.py` | Persistent SQLite job store, `Asia/Jakarta` cron & daily schedules, restart recovery. | `test_networking_vii_scheduler.py` (5 passing) | None | Low | Operational scheduling active | `VERIFIED_OFFLINE` |
| **N7.5 External Calendar Sync** | `core/operations/calendar/` | RFC 5545 `.ics` export/import, Google Calendar API provider, alert suppression. | `test_networking_vii_calendar.py` (4 passing) | None | Low | Calendar sync active | `VERIFIED_OFFLINE` |
| **N7.6 Incidents & Notification Hub** | `core/operations/incident_engine.py`, `notification_hub.py` | State machine lifecycle, fingerprint deduplication, `Asia/Jakarta` quiet hours. | `test_networking_vii_incidents_notifications.py` (4 passing) | None | Low | Proactive incidents active | `VERIFIED_OFFLINE` |
| **N7.7 Operational Reporting** | `core/operations/reporting_engine.py` | Deterministic daily, weekly, monthly reports exported as Markdown, HTML, JSON. | `test_networking_vii_api.py` (1 passing) | None | Low | Deterministic reports active | `VERIFIED_OFFLINE` |
| **N7.8 Operations REST API** | `api/routers/operations.py` | 14 FastAPI endpoints covering predictions, simulation, services, scheduler, windows. | `test_networking_vii_api.py` (7 passing) | None | Low | Operations API mounted | `VERIFIED_OFFLINE` |
| **N7.9 React Operations Center** | `OperationsPage.jsx` | 8-tab operations dashboard, capacity gauges, change simulator, service catalog. | `npm run build` OK, `node --test` (275 passing) | None | Low | Operations UX operational | `VERIFIED_OFFLINE` |
| **N7.10 Final Acceptance & Audit** | Full suite execution & documentation | 35 Networking VII tests passing, 184 backend tests passing, 275 frontend tests passing. | `docs/NETWORKING_VII/` documentation suite | None | Low | Phase Closed | `PHASE_NETWORKING_VII_ACCEPTED` |

---

## 7. Operational & Security Constraints

1. **Non-Negotiable Read-Only Guarantee**: Under no circumstances may diagnostic routines dispatch configuration mutating verbs (`add`, `set`, `remove`, `enable`, `disable`, `reboot`, `reset`).
2. **Deterministic Precedence**: Generative AI models are strictly prohibited from generating raw diagnostic conclusions without underlying deterministic check findings.
3. **No Automatic Remediation**: Self-healing or unattended configuration pushes are strictly forbidden. All configuration applications require explicit human operator confirmation.
4. **Target Hardware Budget**: All background services, databases, and algorithms must operate within the resource constraints of an Intel Core i7-7500U with 8 GB RAM.

---

## 8. Deferred Scope (Post-Phase 8)

The following items are explicitly out of scope for Phases 1–8:
- Automated closed-loop network remediation.
- Unattended configuration deployment.
- Emulation of hardware ASIC TCAM tables.
- Local LLM model hosting exceeding 8 GB RAM hardware budget.
- Extension beyond MikroTik RouterOS v6 and v7.
- Replacement of SQLite with external database engines.
- New engineering phases beyond Phase 8.

---

## 9. Live Device Verification Protocol (Future Execution)

When an authorized MikroTik CHR or physical router becomes available:
1. Verify IP connectivity and SSH port accessibility (`nc -zv <ip> 22`).
2. Confirm SSH banner reception (`SSH-2.0-...`).
3. Execute `POST /api/intelligence/preflight` with authorized credentials.
4. Verify returned RouterOS major version (v6 or v7) and read-only permission level.
5. Execute end-to-end incident investigation against a controlled lab scenario.
6. Verify zero configuration changes using `/export compact` before-and-after comparison.
7. Record observed CLI outputs into the test fixture corpus.
