# AIRA OS — MikroTik CHR Controlled Live Verification Plan
## 10-Point End-to-End Test Plan for Authorized Lab Verification

**Workspace:** `D:\data\agent_ai`  
**Phase:** Phase 8.1 — Controlled CHR Live Verification Preparation  
**Target Environment:** Isolated Virtual Machine (`Lab-CHR-Core-01`, `10.10.10.10:22`)  
**Target Account:** `aira-audit` (Read-Only Policy Group)  
**Safety Scope:** Strict Read-Only Verification; Zero Configuration Mutations; Zero Reboots  

---

## 1. Executive Protocol & Execution Constraints

This test plan defines the 10 sequential, deterministic test cases that must be executed when an authorized MikroTik Cloud Hosted Router (CHR) instance is provisioned in accordance with `docs/AIRA_CHR_LAB_DEPLOYMENT_GUIDE.md`.

### Absolute Execution Rules
1. **Target Authorization**: Tests may only be run against an explicitly authorized target IP (`10.10.10.10`). Probing arbitrary or public IP addresses is strictly forbidden.
2. **Authentication Restriction**: Tests must exclusively use the dedicated read-only service account (`aira-audit`). The `admin` account is prohibited.
3. **Zero Configuration Mutation**: No test case may send mutating CLI commands (`add`, `set`, `remove`, `enable`, `disable`).
4. **Zero Device Reset / Reboot**: No test case may attempt or trigger device restarts.
5. **Zero Credential Exposure**: Logs, test assertions, and API responses must never contain unmasked passwords, secrets, or SSH keys.
6. **Deterministic Failure Classification**: Every test failure must be explicitly mapped to one of the standard failure classifications (`CRITICAL_SECURITY`, `TRANSPORT_FAILURE`, `IDENTITY_MISMATCH`, `PARSER_ERROR`, `POLICY_VIOLATION`).
7. **Evidence Provenance**: Telemetry acquired during these tests must be tagged as `LIVE_DEVICE_EVIDENCE` and never merged with synthetic mocks.

---

## 2. Failure Classifications

| Failure Code | Description | Action Required |
| :--- | :--- | :--- |
| **`CRITICAL_SECURITY`** | A dangerous command was allowed through validation, credentials leaked, or a mutation occurred. | **ABORT TESTING IMMEDIATELY**. Review security policy and restore VM snapshot. |
| **`TRANSPORT_FAILURE`** | TCP handshake failed, SSH banner timed out, or socket reset unexpectedly. | Check hypervisor virtual switch, interface status, and firewall rules on host/guest. |
| **`IDENTITY_MISMATCH`** | Device identity does not match expected label `Lab-CHR-Core-01`. | Halt preflight. Verify router identity configuration before proceeding. |
| **`PARSER_ERROR`** | CLI output returned successfully but normalizer regex failed to parse structured attributes. | Log raw output excerpt. Update parser regex table without mutating device. |
| **`POLICY_VIOLATION`** | Target router returned `action failed: not enough permissions (9)`. | Verify user group policy assignments on CHR. Ensure read-only rights are properly applied. |

---

## 3. Test Cases (1–10)

---

### Test Case 1: SSH Connection and Authentication
- **ID:** `CHR-TEST-001`
- **Objective:** Verify successful TCP handshake, SSH daemon banner reception, and cryptographic authentication via `ConnectionManager`.
- **Preconditions:**
  1. CHR VM running and reachable at `10.10.10.10:22`.
  2. `aira-audit` account provisioned with password `AiraSecureAudit2026!#`.
- **Test Procedure:**
  1. Trigger preflight via CLI probe:
     ```python
     cm = get_connection_manager()
     result = cm.test_target_credentials(
         host="10.10.10.10",
         port=22,
         username="aira-audit",
         password="AiraSecureAudit2026!#",
         timeout=5.0
     )
     ```
  2. Inspect returned dictionary for `authenticated` and `banner`.
- **Expected Result:**
  - `result["authenticated"] == True`
  - `result["success"] == True`
  - Socket successfully read banner starting with `SSH-2.0-`
  - No plaintext password logged in `aira.log` or console output.
- **Evidence to Collect:**
  - `PreflightResult` JSON payload.
  - Connection latency in milliseconds (`latency_ms`).
  - Redacted application log excerpt showing connection lifecycle event.
- **Failure Classification:** `TRANSPORT_FAILURE` (if banner timed out) or `POLICY_VIOLATION` (if auth rejected).
- **Cleanup Procedure:** Call `cm.close_all()` to release active transport sockets.

---

### Test Case 2: Device Identity Verification
- **ID:** `CHR-TEST-002`
- **Objective:** Verify that AIRA OS accurately extracts and validates device system identity without ambiguity.
- **Preconditions:**
  1. Test Case 1 passed.
  2. CHR configured with `/system identity set name="Lab-CHR-Core-01"`.
- **Test Procedure:**
  1. Dispatch read-only preflight:
     ```python
     checker = LabPreflightChecker()
     res = checker.run_preflight("10.10.10.10", username="aira-audit", password="AiraSecureAudit2026!#")
     ```
  2. Evaluate `res.identity` and `res.status`.
- **Expected Result:**
  - `res.identity == "Lab-CHR-Core-01"`
  - `res.status != PreflightStatus.IDENTITY_UNVERIFIED`
  - Canonical network registry maps `10.10.10.10` to `Lab-CHR-Core-01`.
- **Evidence to Collect:**
  - `res.to_dict()["identity"]`
  - `PreflightResult.correlation_id`
  - Output excerpt of `/system identity print`.
- **Failure Classification:** `IDENTITY_MISMATCH`
- **Cleanup Procedure:** None required (pure read-only operation).

---

### Test Case 3: RouterOS Version Detection
- **ID:** `CHR-TEST-003`
- **Objective:** Verify that AIRA OS identifies RouterOS major version (v7) and minor build string from live `/system resource print`.
- **Preconditions:**
  1. Test Case 2 passed.
- **Test Procedure:**
  1. Inspect `res.ros_major_version` and `res.routeros_version` from preflight.
  2. Verify version parsing logic:
     ```python
     from core.canonical_network import parse_routeros_major_version
     assert res.ros_major_version == 7
     assert "7." in res.routeros_version
     ```
- **Expected Result:**
  - `ros_major_version == 7`
  - `routeros_version` matches exact installed RouterOS version (e.g. `7.14.3 (stable)`).
  - Normalizer switches command mappings dynamically to RouterOS v7 syntax.
- **Evidence to Collect:**
  - Raw excerpt of `/system resource print` (masked).
  - Version detection metadata block.
- **Failure Classification:** `PARSER_ERROR`
- **Cleanup Procedure:** None required.

---

### Test Case 4: Read-Only Command Execution
- **ID:** `CHR-TEST-004`
- **Objective:** Verify that standard diagnostic inspection commands execute cleanly, respect output caps, and mask sensitive values.
- **Preconditions:**
  1. Test Case 3 passed.
  2. Read-only session established via `ConnectionManager`.
- **Test Procedure:**
  1. Execute canonical inspection commands sequentially:
     - `/interface print brief`
     - `/ip address print detail`
     - `/ip route print detail`
     - `/ip firewall filter print count-only`
  2. Measure execution latency and check output truncation limits (`MAX_OUTPUT_CHARACTERS = 8000`).
- **Expected Result:**
  - All 4 commands return `success == True`.
  - Output contains valid RouterOS table formatting.
  - Latency per command is recorded and bounded (< 3000 ms).
  - Zero sensitive values exposed in CLI responses.
- **Evidence to Collect:**
  - Command audit trail: command text, execution duration, and truncated sanitized output.
  - `ConnectionSession.avg_latency_ms`.
- **Failure Classification:** `POLICY_VIOLATION` (if permission denied) or `PARSER_ERROR`.
- **Cleanup Procedure:** None required.

---

### Test Case 5: Rejection of Dangerous Command Input
- **ID:** `CHR-TEST-005`
- **Objective:** Empirically prove that dangerous commands are intercepted and blocked before dispatching to the live CHR transport.
- **Preconditions:**
  1. Live SSH session active to `Lab-CHR-Core-01`.
- **Test Procedure:**
  1. Attempt execution of adversarial inputs via `execute_safe_readonly_command()`:
     - `/system reboot`
     - `/ip route print file=evil.txt`
     - `/ip route print where [reboot]`
     - `/ip route print where do={reboot}`
     - `/ip route print interval=1`
     - `/ip address add address=192.168.99.1/24 interface=ether1`
     - `/ip route print; /system reboot`
  2. Check return dictionaries for `blocked == True` and verify zero SSH packets sent.
- **Expected Result:**
  - 100% of dangerous commands return `success == False` and `blocked == True`.
  - Error messages cite `"Security policy violation"`.
  - Live CHR receives zero command payloads for rejected inputs.
- **Evidence to Collect:**
  - Security audit log entries recording blocked attempts.
  - RouterOS `/log print` confirming no reboot or mutation attempts reached the router.
- **Failure Classification:** `CRITICAL_SECURITY` (if any dangerous command reaches the router).
- **Cleanup Procedure:** Verify device uptime via `/system resource print` to prove no restart occurred.

---

### Test Case 6: SSH Timeout and Recovery
- **ID:** `CHR-TEST-006`
- **Objective:** Verify that network drops, unresponsive sockets, or idle timeouts trigger graceful recovery and exponential backoff.
- **Preconditions:**
  1. Active session in `ConnectionManager`.
- **Test Procedure:**
  1. Temporarily pause or drop traffic from host to CHR management port (or execute probe with `timeout=0.01`).
  2. Attempt command execution and observe error handling.
  3. Re-enable traffic and verify automatic reconnection on subsequent command.
  4. Verify reconnect storm backoff (`_backoff`) cooldown countdown.
- **Expected Result:**
  - System returns `success == False` with structured error message.
  - No uncaught exceptions crash the FastAPI worker thread.
  - Backoff initiates (`cooldown_sec` scales: 2s -> 4s -> 8s up to 60s).
  - Recovery restores session cleanly once connectivity returns.
- **Evidence to Collect:**
  - Error log excerpt showing backoff state and reconnect lifecycle.
  - `ConnectionManager.get_stats()` showing `active_backoffs`.
- **Failure Classification:** `TRANSPORT_FAILURE`
- **Cleanup Procedure:** Reset backoff state via `cm.close_all()`.

---

### Test Case 7: Evidence Collection and Normalization
- **ID:** `CHR-TEST-007`
- **Objective:** Verify that `EvidenceCollector` gathers, normalizes, and packages live telemetry into structured `EvidenceItem` objects.
- **Preconditions:**
  1. CHR live and preflight status is `READY_FOR_DIAGNOSTICS`.
- **Test Procedure:**
  1. Trigger evidence collection bundle:
     ```python
     collector = EvidenceCollector()
     bundle = collector.collect_evidence_bundle(
         target="10.10.10.10",
         required_types=["identity", "resources", "interfaces", "ip_addresses", "routes"]
     )
     ```
  2. Inspect bundle structure:
     - Verify item counts.
     - Verify `collection_status == "SUCCESS"`.
     - Verify `freshness == "fresh"`.
     - Verify normalized models for IP addresses and routes.
- **Expected Result:**
  - All requested evidence types collected without errors.
  - `bundle["collection_errors"] == []`.
  - Routes normalized into structured list containing destination prefix, gateway, and routing table.
  - Contradiction detector runs with zero false-positive contradictions.
- **Evidence to Collect:**
  - Complete JSON serialized `evidence_bundle`.
  - List of normalized objects.
- **Failure Classification:** `PARSER_ERROR`
- **Cleanup Procedure:** None required.

---

### Test Case 8: Diagnostic API and PWA Integration
- **ID:** `CHR-TEST-008`
- **Objective:** Verify end-to-end integration across REST API endpoints (`/api/intelligence/*`) and React PWA UI components.
- **Preconditions:**
  1. AIRA OS backend running on `localhost:8000`.
  2. AIRA OS frontend running on `localhost:5173`.
  3. CHR registered in inventory.
- **Test Procedure:**
  1. Send `POST /api/intelligence/preflight` with payload `{"target": "10.10.10.10"}` and auth token.
  2. Send `POST /api/intelligence/incidents` with incident type `CONNECTIVITY_LOSS` targeting `10.10.10.10`.
  3. Fetch incident detail via `GET /api/intelligence/incidents/{incident_id}`.
  4. Verify UI rendering on `NetworkIntelligencePage.jsx`:
     - Preflight capability badge.
     - Incident evidence timeline.
     - Hypothesis ranking cards.
- **Expected Result:**
  - API responses return HTTP 200 with schema-compliant payloads.
  - UI displays live device identity, version badge, and normalized telemetry.
  - Zero console errors or unhandled React exceptions.
- **Evidence to Collect:**
  - API HTTP request/response JSON payloads.
  - Browser network log showing clean SSE / REST calls.
- **Failure Classification:** `PARSER_ERROR` or `TRANSPORT_FAILURE`.
- **Cleanup Procedure:** None required.

---

### Test Case 9: Session Cleanup and Reconnect
- **ID:** `CHR-TEST-009`
- **Objective:** Verify that persistent sessions are gracefully closed, reused when valid, and refreshed after lifetime expiration.
- **Preconditions:**
  1. Multiple commands executed over persistent session.
- **Test Procedure:**
  1. Inspect `cm.get_stats()`: verify `total_sessions_reused > 0`.
  2. Trigger graceful session closure via `cm.close_connection(session_id, reason="test_cleanup")`.
  3. Verify RouterOS SSH channel is closed on CHR:
     - Run `/ip service print` or check active connections.
  4. Dispatch a new command to verify that session opens cleanly on demand.
- **Expected Result:**
  - Closed session removes session lock and host index.
  - No dangling TCP sockets left in `ESTABLISHED` or `CLOSE_WAIT` on host.
  - Subsequent command seamlessly recreates session.
- **Evidence to Collect:**
  - Output of `cm.get_stats()` before and after closure.
  - Host socket status (`netstat -ano | findstr 10.10.10.10`).
- **Failure Classification:** `TRANSPORT_FAILURE`
- **Cleanup Procedure:** Call `cm.close_all()`.

---

### Test Case 10: Configuration Non-Mutation Guarantee
- **ID:** `CHR-TEST-010`
- **Objective:** Empirically prove that the entire diagnostic, preflight, and investigation pipeline resulted in zero configuration changes on the CHR.
- **Preconditions:**
  1. Full execution of Test Cases 1 through 9 completed.
  2. Clean baseline export saved prior to testing (`clean_baseline_v7.rsc`).
- **Test Procedure:**
  1. Connect to CHR console (out-of-band, outside AIRA OS).
  2. Export post-test configuration:
     ```routeros
     /export file=post_test_verification_v7
     ```
  3. Perform cryptographic and structural diff:
     - Compare MD5 / SHA256 checksums of configuration files.
     - Run `/system history print` to inspect RouterOS change log.
- **Expected Result:**
  - `/system history print` contains zero actions performed by `aira-audit`.
  - Configuration diff between `clean_baseline_v7.rsc` and `post_test_verification_v7.rsc` is strictly empty (`0 lines added, 0 lines removed`).
  - Uptime of router confirms device was never rebooted.
- **Evidence to Collect:**
  - Output of `/system history print`.
  - Zero-diff comparison report.
  - SHA256 hashes of pre-test and post-test configuration backups.
- **Failure Classification:** `CRITICAL_SECURITY`
- **Cleanup Procedure:** Revert VM to `BASELINE_READY` snapshot to maintain pristine environment.

---

## 4. Verification Execution Summary Sheet

| Test Case | Description | Verification Method | Pass Criteria | Status |
| :--- | :--- | :--- | :--- | :--- |
| **CHR-TEST-001** | SSH Connection & Authentication | `test_target_credentials` | Banner valid, Auth OK | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-002** | Device Identity Verification | `LabPreflightChecker.run_preflight` | Matches `Lab-CHR-Core-01` | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-003** | RouterOS Version Detection | Preflight resource check | Detects v7 major | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-004** | Read-Only Command Execution | Sequential print queries | 4/4 queries succeed | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-005** | Dangerous Input Rejection | Security policy injection | 100% blocked, 0 sent | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-006** | SSH Timeout & Recovery | Latency & drop simulation | Backoff active, recovers | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-007** | Evidence Collection | `collect_evidence_bundle` | Bundle valid, 0 errors | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-008** | API & UI Integration | REST API & React PWA | HTTP 200, clean UI | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-009** | Session Cleanup & Reconnect | `close_connection` & reload | Socket clean, reopens | `PENDING_AUTHORIZED_CHR` |
| **CHR-TEST-010** | Zero-Mutation Guarantee | Console `/export` diff | Zero config changes | `PENDING_AUTHORIZED_CHR` |
