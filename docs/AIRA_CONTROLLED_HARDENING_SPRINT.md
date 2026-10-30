# AIRA OS — Controlled Hardening Sprint Report
**Date:** October 29, 2026  
**Workspace:** `D:\data\agent_ai`  
**Scope:** Workstream A (SSH Unification), Workstream B (Config Recovery Hardening), Workstream C (Frontend Code Splitting)

---

## 1. Executive Summary

This sprint addressed the three high-priority architectural gaps identified during the post-upgrade evidence audit (`docs/AIRA_POST_UPGRADE_EVIDENCE_AUDIT.md`):
1. **Workstream A — Unify Topology SSH Preflight:** Replaced ad hoc `paramiko.SSHClient()` calls in `AIRA_ECOSYSTEM/api/routers/topology.py` with `ConnectionManager.test_target_credentials()`, ensuring credential protection, error categorization, and non-destructive active session reuse.
2. **Workstream B — Harden Configuration Recovery:** Extended `AIRA_ECOSYSTEM/agents/akane/config_engine.py` and `AIRA_ECOSYSTEM/mcp_servers/network/server.py` with configurable pre-change snapshot storage, elevated management risk detection, snapshot failure guards, lifecycle statuses (`APPLY_FAILED`, `RECOVERY_VERIFIED`, `RECOVERY_REQUIRED`), and post-recovery device reachability verification.
3. **Workstream C — Frontend Code Splitting:** Implemented `React.lazy()` with `lazyWithRetry()` and `Suspense` for 10 secondary routes in `AIRA_ECOSYSTEM/app/frontend/src/App.jsx`, reducing initial JavaScript bundle size from **957.77 kB** to **706.31 kB** (**-251.46 kB**, **-26.25%**), while maintaining the `VoiceCompanionHost` unmounted at the root level.

All 247 frontend unit tests and 110+ backend integration and audit tests pass with 100% success.

---

## 2. Initial Findings

| Workstream | Initial Code State | Operational Risk / Defect |
| :--- | :--- | :--- |
| **A: SSH Preflight** | `POST /api/topology/test-reachability` and `/nodes/test` created an ad hoc `paramiko.SSHClient()` with `AutoAddPolicy` and arbitrary timeout defaults. | Bypassed APCE single-flight locks, connection pooling, and connection metrics; risks port exhaustion, hung transports, and credential leakage in error logs. |
| **B: Config Recovery** | `config_engine.py` generated inverse commands in-memory without persistent, protected pre-change snapshots; had no automated abort if snapshot failed; did not evaluate elevated risk on management paths (default route, management IP, input firewall chain); lacked post-recovery verification. | If network connectivity dropped mid-apply, rollback could be attempted blind without knowing if the router accepted inverse commands, risking permanent device lockout. |
| **C: Code Splitting** | `App.jsx` eagerly imported all 10 secondary pages (`TopologyPage`, `NmsPage`, `WorkspacePage`, `DevicesPage`, etc.). | Main client bundle weighed **957.77 kB** (275.39 kB gzip), causing slow initial load times and high memory footprint on low-spec engineering laptops. |

---

## 3. Files Changed and Engineering Rationale

### Backend Core & API
- **`AIRA_ECOSYSTEM/agents/akane/connection_manager.py`**
  - *Added `test_target_credentials(host, port, username, password, timeout)`*:
    - Reuses existing authenticated session from the pool without closing it if one is already active for the target.
    - If no session exists, runs an isolated single-flight credential probe with bounded timeout (`default 10s`).
    - Classifies failure modes safely: `auth_failure`, `timeout`, `host_key_failure`, `unreachable`, `internal_error`.
    - Sanitizes error messages to prevent credential, token, or private key leakage.
- **`AIRA_ECOSYSTEM/api/routers/topology.py`**
  - *Extracted `_probe_tcp_port(host, port, timeout)`*: Isolates raw TCP socket connection from Python 3.14 Windows Proactor event loop internals.
  - *Delegated SSH verification*: Replaced ad hoc `paramiko.SSHClient` with `get_connection_manager().test_target_credentials()`.
  - *Dual route decorators*: Bound both `@router.post("/nodes/test")` and `@router.post("/test-reachability")` to preserve legacy frontend compatibility while satisfying canonical API contracts.
- **`AIRA_ECOSYSTEM/agents/akane/config_engine.py`**
  - *Protected Snapshot Directory*: Added `AIRA_CONFIG_SNAPSHOT_DIR` (`AIRA_ECOSYSTEM/data/config_snapshots` by default) with permissions check and file masking (`mask_sensitive_data`).
  - *Elevated Risk Assessment*: Added `ELEVATED_MANAGEMENT_RISK` flags in `plan_change()` when proposed commands alter `/ip/route` (`0.0.0.0/0`), management interfaces, user credentials, or `/ip/firewall/filter` input drop rules.
  - *Snapshot Guard in `apply_change()`*: Aborts multi-command execution if pre-change configuration capture fails.
  - *Partial Application Tracking*: Reports `partial_application: True`, `status: "APPLY_FAILED"`, and `applied_count` when a command in a batch fails.
  - *Recovery Verification (`verify_recovery`)*: After executing rollback/inverse commands, verifies device reachability and returns `lifecycle_status: "RECOVERY_VERIFIED"`. If the router is unreachable, sets `lifecycle_status: "RECOVERY_REQUIRED"` and flags `manual_intervention_required: True`.
- **`AIRA_ECOSYSTEM/mcp_servers/network/server.py`**
  - *Updated `mikrotik_apply_config`*: Integrated `risk_level`, `operation_id`, and `lifecycle_status` into the MCP response payload, ensuring audit compliance.

### Frontend Client
- **`AIRA_ECOSYSTEM/app/frontend/src/App.jsx`**
  - *Dynamic Lazy Loading*: Converted 10 secondary page imports to `React.lazy()` with `lazyWithRetry(importer, retries=2, interval=1000)`.
  - *Eager Main Route*: Preserved eager import of `ChatPage` for zero-latency initial interaction.
  - *Voice Companion Isolation*: Kept `VoiceCompanionHost` at root level outside `<main>` and `<Suspense>`, ensuring voice sessions, Web Speech API, and speech queues never dismount or restart during page switches.
  - *Resilient Fallbacks*: Added `PageLoadingFallback` (with theme-aligned spinner) and `PageErrorBoundary` (with reload retry option).

### Test Suites
- **`AIRA_ECOSYSTEM/tests/test_sprint_ssh_preflight.py`**: Validates credential probing, active session reuse without client teardown, error classifications (`auth_failure`, `timeout`, `host_key_failure`, `unreachable`), and endpoint delegation.
- **`AIRA_ECOSYSTEM/tests/test_sprint_config_recovery.py`**: Validates pre-change snapshot persistence, snapshot failure abort guard, elevated risk detection, partial apply detection, and post-recovery device verification.

---

## 4. Design Decisions and Trade-offs

1. **Python 3.14 Windows Proactor Event Loop Isolation:**
   - *Issue:* In Python 3.14 on Windows, `asyncio.ProactorEventLoop` creates an internal socketpair for its self-pipe (`_ssock`). Patching `socket.socket` globally inside test cases breaks `TestClient` / `anyio` with `AttributeError: 'ProactorEventLoop' object has no attribute '_ssock'`.
   - *Resolution:* Isolated TCP port probing into a dedicated module-level function `_probe_tcp_port()` in `api/routers/topology.py`. Tests patch `_probe_tcp_port` rather than `socket.socket`, preserving event loop integrity.
2. **Paramiko `BadHostKeyException` String Safety:**
   - *Issue:* `paramiko.BadHostKeyException.__str__()` internally calls `self.key.get_base64()`. In unit tests with mock exceptions where `key` is `None`, calling `str(exc)` raises `AttributeError: 'NoneType' object has no attribute 'get_base64'`.
   - *Resolution:* Added guarded exception formatting falling back to `getattr(exc, "hostname", host)`.
3. **Dual Status Reporting for Backward Compatibility:**
   - *Issue:* Existing consumers and tests asserted legacy statuses (`VERIFIED_OPERATIONAL`, `ROLLBACK_SUCCESSFUL`), while hardened auditing required explicit lifecycle statuses (`VERIFIED_SUCCESS`, `RECOVERY_VERIFIED`, `RECOVERY_REQUIRED`).
   - *Resolution:* Config responses include both `status` (for backward compatibility) and `lifecycle_status` / `recovery_status` (for strict audit verification).

---

## 5. Verification & Test Evidence

### Frontend Build & Bundle Comparison

| Metric | Baseline (Pre-Sprint) | Hardened (Post-Sprint) | Delta |
| :--- | :--- | :--- | :--- |
| **Main JS Bundle** | `index-BC47_f6-.js`: **957.77 kB** | `index-D7rUYNYK.js`: **706.31 kB** | **-251.46 kB (-26.25%)** |
| **Main JS Gzip** | 275.39 kB | 221.45 kB | **-53.94 kB (-19.59%)** |
| **CSS Bundle** | 130.78 kB | 131.33 kB | +0.55 kB |
| **Build Time** | 2.41s | 3.19s | +0.78s |

#### Emitted Code-Split Route Chunks
- `TopologyPage-DHCQ5r06.js`: **92.09 kB** (gzip: 19.60 kB)
- `DeviceDetailModal-COtNbK7j.js`: **36.69 kB** (gzip: 8.82 kB)
- `DevicesPage-kMEWk1fj.js`: **26.25 kB** (gzip: 6.59 kB)
- `NmsPage-D-WsHXlS.js`: **25.30 kB** (gzip: 6.48 kB)
- `ModelsPage-1kvfnWdm.js`: **17.50 kB** (gzip: 5.35 kB)
- `WorkspacePage-CIE92Qu4.js`: **15.18 kB** (gzip: 4.33 kB)
- `SettingsPage-IUlFzhS5.js`: **14.72 kB** (gzip: 4.77 kB)
- `LogsPage-CMjNMZF0.js`: **10.67 kB** (gzip: 3.20 kB)
- `PersonaPage-Dig3zrCs.js`: **8.12 kB** (gzip: 2.34 kB)
- `AkaneWorkspace-BPGQ7tko.js`: **7.29 kB** (gzip: 2.16 kB)
- `MemoryPage-DT3s0_o7.js`: **2.26 kB** (gzip: 0.98 kB)
- `inventoryApi-B7lu-qD-.js`: **0.99 kB**
- `refresh-cw-DgmHvdEd.js`: **0.35 kB**

### Test Execution Summary

#### Frontend Test Suite
- Command: `npm --prefix AIRA_ECOSYSTEM/app/frontend test`
- Results: **247 passed, 0 failed** in 2.92s.

#### Backend Sprint & Audit Suites
- Command: `pytest AIRA_ECOSYSTEM/tests/test_sprint_ssh_preflight.py AIRA_ECOSYSTEM/tests/test_sprint_config_recovery.py AIRA_ECOSYSTEM/tests/test_audit_a_ssh_reuse.py AIRA_ECOSYSTEM/tests/test_audit_b_nms_ws_polling.py AIRA_ECOSYSTEM/tests/test_audit_c_identity_topology.py AIRA_ECOSYSTEM/tests/test_audit_d_reasoning.py AIRA_ECOSYSTEM/tests/test_audit_e_config_approval.py AIRA_ECOSYSTEM/tests/test_connection_manager_upgrade.py AIRA_ECOSYSTEM/tests/test_akane_safe_config_engine.py`
- Results: **36 passed, 0 failed, 23 warnings** in 12.06s.

#### Backend Core Topology & NMS Suites
- Command: `pytest AIRA_ECOSYSTEM/tests/test_nms.py AIRA_ECOSYSTEM/tests/test_topology.py AIRA_ECOSYSTEM/tests/test_topology_path_explorer.py AIRA_ECOSYSTEM/tests/test_topology_v2.py`
- Results: **74 passed, 0 failed, 23 warnings** in 58.12s.

---

## 6. Limitations & Unverified Real-Device Behavior

1. **Hardware Atomicity Caveat:**
   - MikroTik RouterOS does not support single-transaction hardware commit semantics across disparate subsystems (e.g. adding a bridge while simultaneously modifying routing tables). If power is cut mid-batch, inverse commands cannot be executed by AIRA.
   - For mission-critical changes, network engineers should perform `/system backup save` or `/export file=` before initiating major reconfigurations.
2. **Third-Party Vendors:**
   - The current `config_engine.py` generates RouterOS-specific inverse commands (`/ip address remove`, `/ip route remove`, `/interface set`). Non-MikroTik devices (Cisco IOS, Arista EOS, Junos) require vendor-specific inverse generators.
3. **Physical Console Out-of-Band (OOB):**
   - If a misconfiguration drops IP connectivity on all management interfaces, rollback over SSH is impossible. In such scenarios, AIRA correctly transitions to `RECOVERY_REQUIRED` and flags `manual_intervention_required: True`.

---

## 7. Manual Steps Required Before Production Use

1. **Review Protected Snapshot Directory:** Ensure the directory configured in `AIRA_CONFIG_SNAPSHOT_DIR` (or `./AIRA_ECOSYSTEM/data/config_snapshots`) has restricted OS filesystem permissions (e.g., `chmod 700` or restricted Windows ACLs) so unauthorized local users cannot inspect exported configurations.
2. **Network Time Protocol (NTP):** Ensure all managed routers and the AIRA server have synchronized clocks via NTP so snapshot timestamps accurately align with system audit logs.
3. **Human Approval Safeguards:** Verify that human operator confirmation is always required before executing high-risk configuration changes in production environments.

---

## 8. Final Sprint Status

- **Workstream A — Unify Topology SSH Preflight:** `VERIFIED`
- **Workstream B — Harden Configuration Recovery:** `VERIFIED`
- **Workstream C — Frontend Code Splitting:** `VERIFIED`
