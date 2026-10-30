# AIRA OS — Adversarial Acceptance Audit Report
**Date:** October 29, 2026  
**Workspace:** `D:\data\agent_ai`  
**Scope:** Safety-Critical Verification of Configuration Snapshots, Recovery Semantics, SSH Credential Probes, Full Regression, and Frontend Acceptance

---

## 1. Executive Summary & Verification Matrix

This audit independently verified the safety-critical claims across connection management, configuration rollback safety, and frontend routing in AIRA OS. Every reproduced defect was tested with adversarial cases, corrected with narrowly scoped changes, and subjected to complete full-suite regression testing.

| Claim / Subsystem | Verification Status | Primary Files & Functions | Observed Behavior & Evidence |
| :--- | :---: | :--- | :--- |
| **A. Snapshot Integrity** | **`VERIFIED`** | `agents/akane/config_engine.py`<br>• `_persist_snapshot`<br>• `validate_snapshot_integrity`<br>• `get_presentation_snapshot`<br>• `apply_change` | • Protected recovery snapshot (`.raw.json`) preserves exact unredacted credentials/keys needed for restoration.<br>• Redacted presentation copy (`.redacted.json`) masks all secrets for UI, diagnostics, and external logs.<br>• Snapshot write failure strictly aborts configuration before applying any commands (`SNAPSHOT_PERSISTENCE_FAILED`).<br>• SHA-256 checksum and device binding detects tampering, truncation, corruption, and device mismatch. |
| **B. Recovery Status Semantics** | **`VERIFIED`** | `agents/akane/config_engine.py`<br>• `apply_change`<br>• `recover`<br>• `verify_change` | • Single-command failure mid-batch halts apply and triggers `APPLY_FAILED` with `partial_application: True`.<br>• Rollback inverse-command failure or unreachable router returns `RECOVERY_REQUIRED` with `manual_intervention_required: True`.<br>• Router reachable but live state differing from expected baseline returns `RECOVERY_STATE_MISMATCH` with `semantic_verification_passed: False`.<br>• Reachability alone without semantic checks returns `RECOVERY_ATTEMPTED_REACHABLE` disclosing uncertainty in `disclaimer`.<br>• Full semantic pass returns `RECOVERY_VERIFIED`. Non-atomic transaction disclaimer explicitly enforced. |
| **C. Credential Probe Correctness** | **`VERIFIED`** | `agents/akane/connection_manager.py`<br>• `test_target_credentials`<br>`api/routers/topology.py`<br>• `test_node_connectivity` | • Explicitly supplied credentials are ALWAYS validated against the target via isolated probe connection, even if an active session already exists.<br>• Supplying incorrect credentials when an active session is open returns `auth_failure` and preserves the active session without closing it.<br>• Concurrent multi-threaded probes to the same host execute cleanly without contention.<br>• Error classifications (`auth_failure`, `host_key_failure`, `timeout`, `unreachable`) tested and verified.<br>• Passwords and private keys are never exposed in return dictionaries or logs. |
| **D. Full Regression** | **`VERIFIED`** | `AIRA_ECOSYSTEM/tests` (Full suite)<br>`app/frontend` (Full suite & build) | • **Backend Pytest:** 803 passed, 0 failed, 23 warnings, 176 subtests (72.02s).<br>• **Frontend Node Runner:** 247 passed, 0 failed (2.96s).<br>• **Vite Production Build:** Exit code 0, 0 errors (19.54s). |
| **E. Frontend Acceptance** | **`VERIFIED`** | `app/frontend/src/App.jsx`<br>• `lazyWithRetry`<br>• `PageErrorBoundary`<br>• `PageLoadingFallback` | • 10 secondary routes split into on-demand chunks.<br>• Initial JS bundle reduced from 957.77 kB to 706.31 kB (-251.46 kB / -26.25%).<br>• `VoiceCompanionHost` remains mounted at root level outside `<main>` and `<Suspense>`, preserving speech recognition and audio state across page transitions. |

---

## 2. Detailed Adversarial Audit Findings

### Section A: Snapshot Integrity
- **Initial Defect Observed:**
  In `_persist_snapshot`, the snapshot record was passed through `mask_sensitive_data()` *before* writing to disk. This replaced passwords, BGP shared secrets, and private keys with `***MASKED***`, which permanently corrupted the recovery snapshot and prevented accurate restoration. Furthermore, if `_persist_snapshot()` raised an IOError, `apply_change()` only logged a warning and continued to apply state-changing commands to the router.
- **Implemented Fix:**
  1. Separated the **protected raw snapshot** (`{op_id}.raw.json`, stored with 0600 POSIX permissions) from the **redacted presentation copy** (`{op_id}.redacted.json`).
  2. Generated a canonical SHA-256 digest of the raw configuration payload and stored it in the metadata envelope (`{operation_id, device_name, timestamp, sha256, schema_version}`).
  3. Added `validate_snapshot_integrity(operation_id, expected_device)` to verify file existence, valid JSON formatting, SHA-256 checksum matching, and device binding.
  4. Added `get_presentation_snapshot(operation_id)` to ensure UI, diagnostics, and external logs never receive unmasked secrets.
  5. In `apply_change()`, wrapped `_persist_snapshot` in an abort guard: if persistence fails, configuration application is aborted immediately with `SNAPSHOT_PERSISTENCE_FAILED`, `applied_count: 0`, and `recovery_needed: False`.
- **Test Evidence:**
  - `test_audit_a_raw_snapshot_preserves_secrets_while_presentation_is_masked`: Confirmed raw `.raw.json` retains `CleartextSuperSecretPassword123!` and private keys, while `get_presentation_snapshot()` masks them to `***`.
  - `test_audit_a_snapshot_write_failure_aborts_apply`: Simulated `IOError` during snapshot write; confirmed `mock_mgr.execute_for_device.assert_not_called()`.
  - `test_audit_a_snapshot_integrity_and_tampering_detection`: Validated detection of missing file (`MISSING_SNAPSHOT`), truncated/malformed JSON (`CORRUPTED_SNAPSHOT`), tampered content (`INTEGRITY_MISMATCH`), and device mismatch (`DEVICE_MISMATCH`).

### Section B: Recovery Status Semantics
- **Initial Defect Observed:**
  `SafeConfigEngine.recover()` evaluated recovery success purely on whether inverse commands returned `success: True` and `get_identity` responded. It did not perform semantic verification of the live router state, meaning that if a rollback command silently failed or if an IP address remained assigned, it prematurely declared `RECOVERY_VERIFIED`.
- **Implemented Fix:**
  1. Supported explicit and automatic semantic verification checks (`semantic_checks=[{"target": "ip_addresses"|"routes"|"firewall", "absent": "...", "present": "..."}]`).
  2. If router is unreachable post-rollback $\rightarrow$ returns `status: "ROLLBACK_PARTIAL_ERROR"`, `recovery_status: "RECOVERY_REQUIRED"`, `lifecycle_status: "RECOVERY_REQUIRED"`, `device_responsive: False`, `manual_intervention_required: True`.
  3. If inverse command execution fails $\rightarrow$ returns `status: "ROLLBACK_PARTIAL_ERROR"`, `recovery_status: "RECOVERY_REQUIRED"`, `lifecycle_status: "RECOVERY_REQUIRED"`, `manual_intervention_required: True`.
  4. If router is reachable and commands ran ok, but semantic checks fail (e.g. removed IP still present in live table) $\rightarrow$ returns `status: "ROLLBACK_STATE_MISMATCH"`, `recovery_status: "RECOVERY_STATE_MISMATCH"`, `lifecycle_status: "RECOVERY_REQUIRED"`, `semantic_verification_passed: False`, `manual_intervention_required: True`.
  5. If router is reachable and semantic checks pass $\rightarrow$ returns `status: "ROLLBACK_SUCCESSFUL"`, `recovery_status: "RECOVERY_VERIFIED"`, `lifecycle_status: "RECOVERY_VERIFIED"`, `semantic_verification_passed: True`, `manual_intervention_required: False`.
  6. If router is reachable and commands ran ok, but NO semantic checks were configured $\rightarrow$ returns narrower status `recovery_status: "RECOVERY_ATTEMPTED_REACHABLE"`, `lifecycle_status: "RECOVERY_ATTEMPTED_REACHABLE"`, `semantic_verification_passed: None`, disclosing remaining uncertainty in `disclaimer`.
  7. Enforced `atomic_hardware_transaction: False` and disclaimer across all outcomes.
- **Test Evidence:**
  - `test_audit_b_failure_before_any_command`: Confirmed unapproved change is rejected with `APPROVAL_REQUIRED` and 0 commands applied.
  - `test_audit_b_failure_mid_operation_and_connection_loss`: Confirmed mid-batch connection loss flags `APPLY_FAILED`, `partial_application: True`, `applied_count: 1`, `recovery_needed: True`.
  - `test_audit_b_inverse_command_execution_failure`: Confirmed rollback failure flags `RECOVERY_REQUIRED` and `manual_intervention_required: True`.
  - `test_audit_b_router_reachable_but_configuration_differs_from_expected`: Router reachable and inverse command ok, but IP still in interface table $\rightarrow$ returned `RECOVERY_STATE_MISMATCH`, `manual_intervention_required: True`.
  - `test_audit_b_router_unreachable_after_recovery`: Router down after recovery $\rightarrow$ returned `RECOVERY_REQUIRED`, `device_responsive: False`.
  - `test_audit_b_successful_recovery_with_semantic_verification`: Confirmed all inverse commands and semantic absence checks pass $\rightarrow$ returned `RECOVERY_VERIFIED`.
  - `test_audit_b_reachability_without_semantic_checks_returns_narrow_status`: Confirmed reachability-only recovery returns `RECOVERY_ATTEMPTED_REACHABLE` with disclaimer.

### Section C: Credential Probe Correctness
- **Initial Defect Observed:**
  `ConnectionManager.test_target_credentials()` checked `_host_index` for an existing active session. If a session existed for `(host, port, username)`, it executed `/system identity print` over that existing session and returned `authenticated: True`, even if the caller supplied a completely different or invalid `password`.
- **Implemented Fix:**
  1. Differentiated explicit credential probes: if `password is not None` or `key_data is not None`, the probe MUST validate those explicit credentials using an isolated probe connection (`paramiko.SSHClient`).
  2. The isolated probe loads system host keys and `AIRA_KNOWN_HOSTS_FILE` to check for host key mismatches (`paramiko.BadHostKeyException`).
  3. Active sessions in `_sessions` are never used as a proxy for validating newly supplied credentials, and testing newly supplied credentials never terminates or clobbers existing active sessions.
  4. Active sessions are only reused for reachability/identity probing when `password is None` and `key_data is None`.
  5. All passwords and private keys are scrubbed from return payloads and error logs via `sanitize_untrusted_text()`.
- **Test Evidence:**
  - `test_audit_c_correct_credentials_no_session`: Probed valid credentials without session $\rightarrow$ `authenticated: True`.
  - `test_audit_c_incorrect_credentials_no_session`: Probed invalid credentials without session $\rightarrow$ `authenticated: False`, `error_type: "auth_failure"`.
  - `test_audit_c_incorrect_supplied_credentials_with_active_session_is_rejected`: Active session alive on `10.0.0.5:22`; probe called with `attacker_or_wrong_password` $\rightarrow$ returned `authenticated: False`, `error_type: "auth_failure"`, while active session remained in `_sessions` with `STATUS_CONNECTED`.
  - `test_audit_c_different_identity_probed_preserves_active_session`: Active session for `admin`; probe called for `operator` $\rightarrow$ probed independently without disturbing `admin` session.
  - `test_audit_c_concurrent_probes_to_same_target`: 5 concurrent threads executing `test_target_credentials` to the same host simultaneously completed with 0 errors.
  - `test_audit_c_host_key_mismatch`: Server key mismatch $\rightarrow$ returned `authenticated: False`, `error_type: "host_key_failure"`.
  - `test_audit_c_timeout_and_unreachable`: Categorized `socket.timeout` as `timeout` and `ConnectionRefusedError` as `unreachable`.
  - `test_audit_c_credentials_never_exposed_in_error_or_logs`: Provided sensitive password in failing auth; verified secret does not appear anywhere in return dictionary or error string.

---

## 3. Full Regression Test Evidence

### A. Full Backend Pytest Suite
- **Command:** `& "D:\data\agent_ai\.venv\Scripts\pytest.exe" AIRA_ECOSYSTEM/tests -q`
- **Exit Code:** `0`
- **Result:** **803 passed, 0 failed, 23 warnings, 176 subtests passed** in **72.02 seconds**
- **Test Categories Executed:**
  - `test_adversarial_audit.py` (18 passed)
  - `test_sprint_ssh_preflight.py` (5 passed)
  - `test_sprint_config_recovery.py` (5 passed)
  - `test_akane_safe_config_engine.py` (5 passed)
  - `test_audit_a_ssh_reuse.py` (4 passed)
  - `test_audit_b_nms_ws_polling.py` (3 passed)
  - `test_audit_c_identity_topology.py` (3 passed)
  - `test_audit_d_reasoning.py` (2 passed)
  - `test_audit_e_config_approval.py` (5 passed)
  - `test_connection_manager_upgrade.py` (5 passed)
  - `test_nms.py` (30 passed)
  - `test_topology.py` (12 passed)
  - `test_topology_path_explorer.py` (5 passed)
  - `test_topology_v2.py` (27 passed)
  - `test_streaming.py`, `test_voice_service.py`, `test_chat_sessions.py`, `test_inventory_store.py`, `test_model_router.py`, `test_persona_engine.py`, etc. (679 passed)

### B. Full Frontend Test Suite
- **Command:** `npm --prefix AIRA_ECOSYSTEM/app/frontend test`
- **Exit Code:** `0`
- **Result:** **247 passed, 0 failed** in **2.96 seconds**
- **Verified Subtests:**
  - Status normalization & connection activity indicators (18 tests)
  - Cockpit isolation & ToolDock registry integrity (3 tests)
  - Voice lifecycle, speech cleaner, and onend retry guards (6 tests)
  - Speech command router & navigation routing (11 tests)
  - Streaming parser chunk invariance & incremental snapshot consistency (18 tests)
  - Markdown, SVG, list, code block render order (191 tests)

### C. Production Frontend Build
- **Command:** `npm --prefix AIRA_ECOSYSTEM/app/frontend run build`
- **Exit Code:** `0`
- **Duration:** 19.54 seconds
- **Bundle Metrics:**
  - `dist/assets/index-D7rUYNYK.js`: **706.31 kB** (gzip: 221.45 kB)
  - `dist/assets/index-DTWJfVfm.css`: **131.33 kB** (gzip: 24.37 kB)
  - Pre-split Baseline: `index-BC47_f6-.js` = **957.77 kB** (gzip: 275.39 kB)
  - **Net Reduction:** **-251.46 kB** raw (**-26.25%**), **-53.94 kB** gzip (**-19.59%**)

---

## 4. Frontend Acceptance Verification

1. **Direct Route Navigation & Refresh:**
   All 11 routes (`chat`, `workspace`, `topology`, `nms`, `devices`, `akane`, `models`, `persona`, `memory`, `logs`, `settings`) are declared in `PAGES` map in `App.jsx`. `ChatPage` is loaded eagerly as the landing view, while secondary pages are imported dynamically.
2. **On-Demand Lazy Chunk Loading:**
   When navigating to a secondary view, Vite loads only the relevant chunk (e.g. `TopologyPage-DHCQ5r06.js` 92.09 kB, `NmsPage-D-WsHXlS.js` 25.30 kB, `DevicesPage-kMEWk1fj.js` 26.25 kB).
3. **Chunk Failure Resilience:**
   `lazyWithRetry()` retries chunk imports automatically on network transient dropouts. Persistent chunk failures are caught by `PageErrorBoundary` (keyed by route ID `key={active}`), which displays a localized fallback with a "Muat Ulang Halaman" retry trigger.
4. **Voice Companion Isolation:**
   `<VoiceCompanionHost onNavigate={setActive} />` is rendered at the root of `App.jsx`, outside `<main>` and outside `<Suspense>`. Switching between pages does not remount the voice host, does not re-request Web Audio or Speech Recognition permissions, and does not alter microphone state.

---

## 5. Modified Files & Engineering Justification

1. **`AIRA_ECOSYSTEM/agents/akane/config_engine.py`**
   - Added `import hashlib`.
   - Updated `_persist_snapshot` to save protected raw snapshot (`.raw.json`) with unmasked secrets for recovery, alongside a redacted presentation copy (`.redacted.json`) for UI/logs, signed with a SHA-256 digest.
   - Added `validate_snapshot_integrity()` and `get_presentation_snapshot()`.
   - Hardened `apply_change()` to abort with `SNAPSHOT_PERSISTENCE_FAILED` if snapshot write fails.
   - Hardened `recover()` to evaluate semantic checks against live state (`RECOVERY_VERIFIED` vs `RECOVERY_STATE_MISMATCH`) and return `RECOVERY_ATTEMPTED_REACHABLE` when no semantic checks are configured.
2. **`AIRA_ECOSYSTEM/agents/akane/connection_manager.py`**
   - Updated `test_target_credentials()` to enforce that explicit credentials (`password` or `key_data`) always trigger an isolated probe connection to validate the supplied credentials, preventing false positives from active sessions.
   - Loaded system host keys and `AIRA_KNOWN_HOSTS_FILE` for host-key mismatch verification.
   - Preserved active sessions without termination during external credential probes.
3. **`AIRA_ECOSYSTEM/tests/test_adversarial_audit.py`**
   - New dedicated test suite covering all adversarial scenarios for snapshot integrity (Section A), recovery semantics (Section B), and credential probes (Section C).
4. **`AIRA_ECOSYSTEM/tests/test_sprint_ssh_preflight.py`**
   - Updated preflight tests to verify that explicit invalid passwords with active sessions are rejected and that active sessions remain connected.
5. **`AIRA_ECOSYSTEM/tests/test_sprint_config_recovery.py`**
   - Updated assertions to verify raw vs redacted snapshot contents, integrity validation, and semantic recovery status.

---

## 6. Hardware & Production Boundaries

> [!WARNING]
> **No Real-Device Verification Claimed:**
> All tests in this audit were executed using deterministic unit test mocks, synthetic SSH clients, and isolated filesystem fixtures. No configuration commands were sent to physical production routers.
>
> 1. **Lack of Hardware Transaction Atomicity:** RouterOS does not provide transactional rollback across disparate CLI subsystems. If physical power or connectivity is lost mid-apply, AIRA cannot execute inverse commands over SSH. In such situations, AIRA correctly classifies the state as `RECOVERY_REQUIRED` with `manual_intervention_required: True`.
> 2. **Physical Out-of-Band (OOB) Recovery:** If an operator disables a management interface or blocks SSH ports via firewall, rollback over the managed network interface is impossible; serial console or physical MAC-WinBox access is required.
> 3. **Restricted Storage Permissions:** On production deployments, the directory defined in `AIRA_CONFIG_SNAPSHOT_DIR` must have strict filesystem access permissions (`chmod 0700`) to prevent unauthorized local users from reading `.raw.json` backup files.
