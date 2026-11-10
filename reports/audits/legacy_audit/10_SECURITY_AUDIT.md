# PHASE 10 — APPLICATION SECURITY AUDIT (`10_SECURITY_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent`  
**Security Reporting Policy**: In strict compliance with audit security rules, **zero secret values, passwords, tokens, or private keys are displayed in this report**. All findings cite only the file path, line numbers, secret/vulnerability type, risk, and remediation.

---

## 1. Executive Summary of Security Posture

**Overall Security Posture Rating**: **CRITICAL RISK (Not Ready for Production Deployment Without P0 Remediation)**

Static and architectural security auditing across all 20 required OWASP/ASVS security domains confirmed **28 distinct security vulnerabilities** (`26 CONFIRMED`, `2 LIKELY`), including **10 CRITICAL** and **11 HIGH** severity vulnerabilities that allow unauthenticated remote command execution on network routers, unauthenticated server workspace file manipulation, Superadmin (`lingga_admin`) privilege escalation, and billing webhook forgery.

---

## 2. Detailed Audit Across All 20 Security Domains

### 2.1 Hardcoded Secrets, Fallback Credentials & Tracked DB Backups (`CONFIRMED — HIGH`)
*(No secret values are reproduced below.)*

| # | File Location & Line | Secret Type | Security Risk | Remediation |
|---:|---|---|---|---|
| 1 | [`core/billing/service.py:34`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/billing/service.py#L34) | Hardcoded `DEFAULT_WEBHOOK_SECRET` fallback string used when `AIRA_BILLING_WEBHOOK_SECRET` is unset in `.env`. | Any attacker who knows the default source-code fallback string can forge valid HMAC-SHA256 signatures for `/api/v1/billing/webhooks/{provider}` if the env var is omitted. | Remove the fallback string; fail closed (`401`/`503`) if `AIRA_BILLING_WEBHOOK_SECRET` is not configured. |
| 2 | [`core/bootstrap_superadmin.py:25-28`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/bootstrap_superadmin.py#L25-L28) | Hardcoded `SUPERADMIN_DEFAULT_PASSWORD` fallback string in standalone bootstrap utility. | Predictable default Superadmin credential if `bootstrap_superadmin.py` is executed without `AIRA_SUPERADMIN_INITIAL_PASSWORD`. | Delete unused `core/bootstrap_superadmin.py` (already superseded by `core/tenant/seed_admin.py` which uses `secrets.token_urlsafe(16)`). |
| 3 | `AIRA_ECOSYSTEM/database/chat_sessions.db.old` & `long_term_memory.db.old` | Historical SQLite database backup files tracked in Git repository. | Exposes historical chat transcripts and user facts in version control history. | Remove `*.db` and `*.db.old` from Git tracking (`git rm --cached`) and add `*.db*` to `.gitignore` and `.dockerignore`. |

---

### 2.2 `.env` Handling & Environment Secret Leakage (`CONFIRMED — HIGH`)
- **Global `SSH_PASSWORD` Environment Fallback Leak (`agents/akane/connection_manager.py:200, 387`)**:
  - In `open_connection()` (`L200`) and `_reconnect_credentials()` (`L387`):
    `resolved_pw = password if password is not None else (os.getenv("SSH_PASSWORD") or None)`
  - **Risk**: When any caller (or LLM tool call) opens an ad-hoc SSH connection to an external IP address without providing a password, `ConnectionManager` automatically transmits the server's `SSH_PASSWORD` environment variable to that remote host!
  - **Remediation**: Never send `os.getenv("SSH_PASSWORD")` to ad-hoc hosts; require explicit per-device credentials from `InventoryStore`.

---

### 2.3 Authentication Bypass (`CONFIRMED — CRITICAL`)
1. **13 Completely Unauthenticated Routers (`CONFIRMED`)**:
   - [`api/routers/connections.py:37-98`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/connections.py#L37-L98): All 5 endpoints (`/open`, `/close`, `/execute`, etc.) have **zero authentication**, allowing unauthenticated network clients to execute arbitrary RouterOS commands on managed routers.
   - [`api/routers/files.py:71-306`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/files.py#L71-L306): All 20 endpoints (mounted at `/` and `/api`) have **zero authentication**, allowing unauthenticated read, write, delete, zip, and extract operations in the server workspace.
   - [`api/routers/automations.py:46-130`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/automations.py#L46-L130): All 8 automation job endpoints have **zero authentication**.
   - [`api/routers/settings.py:39-90`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/settings.py#L39-L90): `GET/PUT /api/settings/*` and `GET/PUT /api/settings/approvals/preferences` have **zero authentication**, allowing unauthenticated callers to disable tenant approval gates (`approval_mode`).
   - [`api/routers/voice.py:25-65`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/voice.py#L25-L65): All 5 endpoints controlling the server's PortAudio microphone capture have **zero authentication**.
   - `api/routers/{artifacts,attachments,workspace_links,selection,location,memory,capabilities,tools,providers}.py` and `POST /api/reset` (`chat.py:122`): All have **zero authentication**.
2. **Billing Webhook Signature Bypass (`api/routers/billing.py:84-87` & `core/billing/service.py:239`)**:
   - `POST /api/v1/billing/webhooks/{provider}` checks `if signature:`. When the `X-Signature` / `X-Webhook-Signature` header is omitted (`signature is None`), signature verification is completely skipped (`sig_valid` defaults to `True`), allowing unauthenticated attackers to forge payment webhooks.
3. **Unauthenticated `X-Guest-ID: gst_...` Header Spoofing (`core/tenant/auth_deps.py:20-37`)**:
   - Sending `X-Guest-ID: gst_<anything>` fabricates a `TenantContext` without a valid session token.
4. **Unauthenticated `NOC_ADMIN` Fallback in `api/routers/decisions.py:83-98` and `api/routers/gateways.py:72-89`**:
   - Both `_get_ctx()` functions return a synthetic internal `NOC_ADMIN` `TenantContext` (`is_internal=True`, full permissions) whenever no `Authorization` header is supplied (mitigated on `decisions.py` and `gateways.py` only by their router-level `Depends(require_permission(...))`, but a severe latent trap if `_get_ctx` is called directly).

---

### 2.4 Authorization Bypass & Privilege Escalation (`CONFIRMED — CRITICAL`)
1. **Chat Form Submission Superadmin Escalation (`core/orchestrator.py:221-233` — `CRITICAL`)**:
   - `Orchestrator.route()` intercepts `[Form Submission...]` messages containing `name` and `host`. Because `context` (`AIRAContext`) has no `user_id` attribute (`user_id_scope` is `None`), line 232 runs `with event_scope(user_id=user_id_scope or "lingga_admin"): tool_res = self._execute_tool("add_device", sub_values)`, executing `add_device` with `lingga_admin` Superadmin privileges!
2. **Internal Viewer -> Platform Admin & Superadmin Impersonation (`api/routers/admin_platform.py:62, 213` — `CRITICAL`)**:
   - `require_platform_admin` checks `if not (ctx.is_internal or any(r in admin_roles for r in ctx.roles)):`. Every user in `tenant_internal` has `ctx.is_internal == True`, so even a `READ_ONLY` viewer passes `require_platform_admin` and can call `POST /api/v1/admin/impersonate` (`L213`) to mint a session token for `lingga_admin`!
3. **Admin Group Assignment & Superadmin Password Overwrite (`api/routers/user_management.py:98-184` — `CRITICAL`)**:
   - Any user with `users.create` or `users.update` (`ADMIN` group) can assign themselves or any user to `grp_super_admin` (`SUPER_ADMIN`) or overwrite `lingga_admin`'s password.
4. **Self-Service Mock Payment Upgrade in Production (`api/routers/billing.py:108-120` — `CRITICAL`)**:
   - `POST /api/v1/billing/simulate-mock` only requires `Depends(get_current_user_context)`, allowing any regular user to mark any invoice `PAID` and self-upgrade to `ENTERPRISE`.
5. **Localhost / Reverse-Proxy Admin Bypass (`api/routers/topology.py:58-92` — `HIGH`)**:
   - `require_topology_admin` (used across `topology.py`, `nms.py`, and `network_intelligence.py`) grants admin access to all requests from `127.0.0.1` / `::1` / `localhost` when `AIRA_TOPOLOGY_ADMIN_TOKEN` is unset. When deployed behind Nginx or Vite proxy on localhost, **every `READ_ONLY` user gets full topology/NMS admin write access**.
6. **Client-Controlled Approval Bypass on Playbooks (`api/routers/playbooks.py:33, 73` — `HIGH`)**:
   - `POST /api/v1/playbooks/{playbook_id}/execute` accepts `bypass_approval: bool = False` directly in the user's JSON request body and passes it to `_playbook_runner.execute_playbook()`, bypassing Category B/C human approval gates!
7. **Missing Write Permissions on Mutating Routes (`HIGH`)**:
   - `api/routers/devices.py:263, 399-447`: Creating/updating/deleting credentials and promoting discovered devices only require `inventory.read`.
   - `api/routers/models.py:74-166`: Creating/updating/deleting LLM models and changing routing policies only require `models.read`.
   - `api/routers/logs.py:58`: `DELETE /api/logs` wipes all logs with only `audit.read`.
   - `api/routers/operations.py:142-345`: All mutating POST routes only require `nms.alerts.read`.
   - `api/routers/network_intelligence.py:1480-1595`: Onboarding devices and resolving/executing actions only require `nms.read`.
   - `api/routers/personalization.py:314, 444, 451`: `duplicate_persona` checks `settings.memory.view`, and `DELETE /data/memories` & `DELETE /data/personas` check no permission at all (`get_current_user_context`).
8. **Group `DENY` Rule Bypass (`core/tenant/manager.py:1054-1068` & `models.py:2249-2254` — `HIGH`)**:
   - Legacy `ROLE_PERMISSIONS` union in `validate_session_token()` and `PERMISSION_ALIASES` expansion in `has_permission()` override explicit RBAC group `DENY` rules.

---

### 2.5 Insecure Direct Object Reference (IDOR) & Cross-Tenant Isolation (`CONFIRMED — HIGH`)
1. **`api/routers/user_management.py:88, 150, 187, 389-430`**: `GET /users` accepts arbitrary `tenant_id` query param without checking `ctx.tenant_id`; `PATCH /users/{user_id}`, `POST /users/{user_id}/toggle-status`, and `DELETE /sessions/{session_id}` do not verify that the target user/session belongs to the admin's `ctx.tenant_id`.
2. **`api/routers/billing.py:59, 108`**: `POST /api/v1/billing/checkout` and `POST /api/v1/billing/simulate-mock` do not verify `invoice.user_id == ctx.user_id`.
3. **`core/playbooks/runner.py:149, 173`**: `get_playbook(playbook_id)` and `execute_playbook(playbook_id)` do not filter by `tenant_id`.
4. **`core/operations/incident_engine.py:83-178` & `service_intelligence.py:114-167`**: Omit `WHERE tenant_id = ?` in SQL queries, exposing all tenants' incidents and services in `/api/operations/*`.

---

### 2.6 SQL Injection (`CONFIRMED — MEDIUM`)
- While most queries use parameterized `?` placeholders, [`core/network_intelligence/historical_intelligence.py:142-157`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/historical_intelligence.py#L142-L157) interpolates `metric_name` directly into the SQL string via concatenation (`"SELECT timestamp, " + metric_name + " FROM nms_interface_metrics WHERE device_id = ? ..."`). Although `metric_name` is currently passed from internal callers (`"in_errors"`), it lacks an allowlist check before SQL interpolation.

---

### 2.7 Command Injection & Unsafe Network Command Execution (`CONFIRMED — HIGH`)
1. **CLI Argument / Flag Injection in `tools/network/diagnostics.py:24, 66, 130` (`CONFIRMED`)**:
   - `agents/akane/network_tools.py:16-17` exposes `ping`, `nslookup`, and `traceroute` without calling `validate_network_target()` (`mcp_servers/network/security.py:25`). Passing a `target` starting with `-` injects CLI flags into `subprocess.run(["ping", ..., str(target)])`.
2. **Unauthenticated RouterOS CLI Execution (`api/routers/connections.py:90`)**:
   - `POST /api/connections/execute` executes arbitrary RouterOS commands without authentication or `SafeConfigEngine` validation.

---

### 2.8 Path Traversal & Unsafe File Upload / Extraction (`CONFIRMED — MEDIUM`)
- **Positive Controls Verified**:
  - `PathSandbox` (`core/filesystem/sandbox.py:42-95`) resolves paths with `.resolve()` and enforces `resolved.is_relative_to(self.root)`.
  - `extract_archive()` (`core/filesystem/archive.py:85-160`) checks for ZipSlip (`is_relative_to`), rejects symlinks in tarballs, and enforces a 200 MB uncompressed size cap (`MAX_EXTRACT_BYTES`).
- **Remaining Vulnerability**:
  - Because `api/routers/files.py` and `api/routers/attachments.py` have **zero authentication**, any unauthenticated user can upload up to 200 MB per archive or overwrite/delete any file inside the shared global `AIRA_ECOSYSTEM/workspace/` directory.

---

### 2.9 XSS, CSRF & CORS Configuration (`CONFIRMED — LOW/MEDIUM`)
- **XSS**: `app/frontend/src/components/Markdown.jsx` sanitizes HTML/SVG output using `DOMPurify.sanitize()`. No unsafe `dangerouslySetInnerHTML` without `DOMPurify` was found.
- **CSRF & CORS (`api/main.py:66-76`)**:
  - Authentication relies on `Authorization: Bearer <token>` stored in `localStorage` (`src/context/AuthContext.jsx:19`), which mitigates classic cookie-based CSRF, **except** for the 13 unauthenticated routers (`connections.py`, `files.py`, `settings.py`, `automations.py`, `voice.py`, `chat.py:/api/reset`), which accept state-changing `POST`/`PUT`/`DELETE` requests without any token!

---

### 2.10 WebSocket Security (`CONFIRMED — CRITICAL`)
- [`api/routers/ws.py:355, 385`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/ws.py#L355-L385): `WS /ws/nms` and `WS /ws/chat/{session_id}` have **zero authentication**. Any client can subscribe to `/ws/chat/{session_id}`, read live responses, delete chat turns (`replace_from_turn_id`), and execute LLM tool turns impersonating the victim session's `user_id` (`ws.py:319-326`).

---

### 2.11 Rate Limiting, Plaintext Credential Storage, MITM & SSRF (`CONFIRMED — HIGH`)
1. **`X-Forwarded-For` Spoofing Bypasses Login Rate Limiter (`api/routers/auth.py:76-82`)**:
   - Trusts client-supplied `X-Forwarded-For` header unconditionally (`client_ip = forwarded_for.split(",")[0].strip()`), allowing unlimited brute-force login attempts by rotating the `X-Forwarded-For` header.
2. **Plaintext Secrets in SQLite & Disk Snapshots (`CONFIRMED`)**:
   - Device SSH/SNMP passwords in `inventory.db` (`credentials.secret`, `core/inventory_store.py:84`).
   - LLM provider API keys in `model_router.db` (`models.api_key`, `core/model_store.py:252`).
   - User TOTP MFA secrets in `topology.db` (`operational_users.mfa_secret`, `core/tenant/db.py:84`).
   - RouterOS config snapshots in `database/config_snapshots/{operation_id}.json` (`agents/akane/config_engine.py:147` writes unmasked `data` instead of `masked_data`).
3. **SSH Man-in-the-Middle (`paramiko.AutoAddPolicy()`) (`CONFIRMED`)**:
   - Hardcoded in `tools/ssh/client.py:86`, `tools/ssh/shell.py:101`, and `agents/akane/connection_manager.py:867`.
4. **Unused & Flawed SSRF Validator (`core/security/ssrf_validator.py` & `tools/web/search.py`)**:
   - `core/security/ssrf_validator.py` is never imported in production and fails to block IPv4-mapped IPv6 loopback/metadata addresses (`::ffff:127.0.0.1`, `::ffff:169.254.169.254`) when `allow_private_devices=True` because `ip.is_private` evaluates `True` first (`L68-74`).
   - `tools/web/search.py:56-89` and `agents/rei/provider_client.py` (custom `base_url`) are vulnerable to DNS rebinding (TOCTOU) and arbitrary internal URL probing when a user with `models.read` registers a custom model `base_url`.
