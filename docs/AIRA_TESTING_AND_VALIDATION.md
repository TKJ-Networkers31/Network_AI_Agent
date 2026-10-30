# AIRA OS — Testing, Verification & Validation Framework
## Authoritative Verification Protocols, Baselines, and Test Suite Catalog

---

## 1. Testing Philosophy & Verification Strategy

AIRA OS implements an evidence-driven verification strategy prioritizing mathematical and deterministic correctness over stochastic assertions:

1. **Deterministic Unit Verification**: Packet traversal, Longest Prefix Match (LPM), firewall rule ordering, and subnet overlaps are validated via pure mathematical functions with zero external dependencies.
2. **Adversarial Resilience**: Every parser, preflight check, and command dispatcher is subjected to corrupted inputs, shell injections, partial outputs, and timeout conditions.
3. **Strict Non-Mutation Assurance**: All diagnostics suites verify that `SafeConfigEngine.apply_change` is never called.
4. **Honest Boundary Reporting**: When hardware or network telemetry is unavailable, tests mandate `INSUFFICIENT_EVIDENCE` or `BLOCKED` rather than speculative assertions.

---

## 2. Test Execution Baselines & Commands

### 2.1. Backend Test Suite (Pytest)
- **Command**:
  ```powershell
  $env:PYTHONPATH="AIRA_ECOSYSTEM"
  .venv\Scripts\python.exe -m pytest AIRA_ECOSYSTEM/tests -q
  ```
- **Latest Verified Execution**:
  - **Result**: `895 passed, 23 warnings, 176 subtests passed in 99.32s`
  - **Pass Rate**: 100%
  - **Environment**: Windows 10/11, Python 3.10+, Intel Core i7-7500U, CPU-only.

### 2.2. Frontend Test Suite (Node.js Test Runner)
- **Command**:
  ```powershell
  npm --prefix AIRA_ECOSYSTEM/app/frontend test
  ```
- **Latest Verified Execution**:
  - **Result**: `247 passed, 0 failed in 5.73s`
  - **Pass Rate**: 100%

### 2.3. Frontend Production Build (Vite)
- **Command**:
  ```powershell
  npm --prefix AIRA_ECOSYSTEM/app/frontend run build
  ```
- **Latest Verified Execution**:
  - **Result**: Succeeded in 37.91s (`NetworkIntelligencePage` chunk 32.38 kB / gzip 7.14 kB).

---

## 3. Test Suites Catalog

| Test Category / File | Tests | Primary Scope & Verified Capabilities |
| :--- | :--- | :--- |
| **`tests/test_phase7_decision_engine.py`** | 10 | RankedHypothesis schema, deterministic ranking rationale, decision engine recommendations (prerequisites, cost risk, zero mutation), and all 7 adversarial diagnostic scenarios. |
| **`tests/test_phase7_live_verification.py`** | 7 | Zero mutation guarantee across preflight and investigation, read-only command dispatch trace, SSH banner timeout handling, offline lab handling, and zero credential leakage. |
| **`tests/test_phase6_diagnostic_validation.py`** | 8 | 7 diagnostic domain investigations (LAN no internet, default route, NAT mismatch, firewall block, OSPF adjacency, BGP missing prefixes, VLAN trunk) + full failure handling. |
| **`tests/test_phase6_lab_preflight.py`** | 4 | Preflight state machine (7 statuses), identity resolution, RouterOS v6/v7 major version detection, and credential masking. |
| **`tests/test_phase6_observability_and_security.py`** | 3 | Correlation ID propagation across investigations, multi-target evidence isolation, and token authorization guard. |
| **`tests/test_phase5_read_only_enforcement.py`** | 10 | Allowlist regex validation, injection delimiter rejection (`&`, `<`, `>`, `;`, `|`), and SafeConfigEngine isolation. |
| **`tests/test_phase5_adversarial_evidence.py`** | 16 | Malformed CLI tables, corrupted headers, truncation, and contradiction detection. |
| **`tests/test_phase5_ros_compatibility.py`** | 18 | RouterOS v6 vs v7 syntax parity (BGP, OSPF, routing tables, filter rules). |
| **`tests/test_phase5_simulator_correctness.py`** | 16 | Before/after LPM diffs, shadow detection, and unmodeled forwarding disclosures. |
| **`tests/test_network_intelligence_*.py`** | 16 | End-to-end intelligence pipeline, state storage, playbooks runner, config planner diffs, and REST API. |
| **Baseline Core, APCE & Agent Tests** | 787 | APCE session reuse, single-flight locks, backoff storm prevention, topology engine, NMS polling, voice lifecycle, and chat sessions. |
| **Total Backend Tests** | **895** | **100% passing across the entire repository.** |

---

## 4. Acceptance Criteria & Verification Boundaries

### 4.1. Offline Acceptance Criteria (`VERIFIED_OFFLINE`)
- All 895 backend tests and 247 frontend tests pass without errors.
- Read-only allowlist and delimiter sanitization block 100% of mutating or malicious command strings.
- Static simulation surfaces explicit disclosures for unmodeled datapath effects.
- Zero credentials leak into serialized records, logs, or UI payloads.
- Correlation IDs track diagnostic runs from API request to evidence persistence.

### 4.2. Live Device Integration Boundary (`BLOCKED (LAB_OFFLINE)`)
- Live testing against a physical router or CHR is strictly contingent upon:
  1. An explicitly configured and operator-authorized lab IP address and SSH port.
  2. Successful TCP socket connection AND complete SSH banner acquisition (`SSH-2.0-...`).
  3. Successful cryptographic key/password authentication.
  4. Verified `/system identity print` response matching expected lab router identity.
- In the absence of an authorized live target, all live tests are honestly reported as `BLOCKED (LAB_OFFLINE)` or `NOT_TESTED`.
