# AIRA OS — SECURITY BASELINE & MULTI-TENANCY SPECIFICATION

**Version:** 1.0.0  
**Status:** Mandatory Security Baseline  
**Auditor:** Principal Security & Systems Architect  

---

## 1. Multi-Tenant Isolation & Anti-IDOR Enforcement

### 1.1 Invariant: Authenticated Server-Side Context
Under no circumstances shall the application trust client-supplied `tenant_id`, `organization_id`, `user_id`, `role`, or `is_admin` parameters from query parameters, request bodies, or unverified headers.
- Every authenticated request must pass through `get_current_tenant_context` dependency.
- The session token (`Bearer aira_tok_...`) is looked up in `operational_user_sessions` via its SHA-256 hash.
- The user's tenant ID, active roles, and granular permissions are loaded directly from authoritative database records.
- For non-internal (customer) accounts, `ctx.tenant_id` is strictly enforced. Any attempt by a customer to query or mutate resources belonging to another tenant produces an immediate `403 Forbidden` response.

### 1.2 Resource Isolation Boundaries
The following resources are strictly segregated by `tenant_id`:
1. **Device Inventory & Credentials:** Devices, credential profiles, SSH keys, SNMP secrets.
2. **Network Topology & Discovery:** Nodes, edges, evidence records, discovery snapshots.
3. **Telemetry & NMS Data:** Device metrics, interface metrics, threshold alerts, incident logs.
4. **Automations & Workflows:** Scheduled jobs, event triggers, execution logs.
5. **Files & Attachments:** Uploaded configs, generated artifacts, session attachments.
6. **AI Conversation Sessions:** Chat sessions, message history, interaction memory, selection contexts.

---

## 2. Credential Security & Secret Vault

### 2.1 Encryption at Rest
All sensitive secrets (SSH passwords, private keys, API tokens, SNMP v2c/v3 credentials) must be encrypted using Fernet symmetric encryption prior to insertion into SQLite:
- Encryption key loaded from `AIRA_SECRET_KEY` environment variable, or initialized securely in `database/.inventory.key`.
- In database tables, passwords and secrets are stored in `secret_enc` binary columns. Plaintext secrets are never stored.

### 2.2 Strict Secret Redaction
- API responses for device listings, credential listings, topology nodes, and telemetry records must NEVER include raw secrets.
- Responses expose only boolean presence flags: `has_secret: true`.
- Logs, telemetry traces, and AI context builders must filter out credentials using regex redaction (`_SECRET_KV_RE`, `_BEARER_RE`, `_PRIVATE_KEY_BLOCK_RE`).
- SSH connection managers retrieve decrypted secrets only in-memory at execution time within the backend process.

---

## 3. File & Archive Security

### 3.1 Path Traversal & Zip-Slip Protection
- All filesystem operations are anchored to the workspace root directory via `WorkspaceManager.resolve()`.
- Archive extraction (`core/file_processing/archive.py`) resolves every entry destination path and validates that `target.relative_to(extraction_root)` succeeds. Any archive entry containing `..`, absolute drive letters (`C:`), or null bytes (`\x00`) raises an immediate traversal error.

### 3.2 Resource Limits & Decompression Bombs
- **Maximum expansion ratio:** Default 1,000x ratio check with a 512 MB floor (`expansion_floor`).
- **Disk margin:** A minimum of 64 MB free disk space is verified before writing each decompression chunk.
- **Max archive entries:** Capped at 100,000 entries; nested archive depth capped at 3 levels.
- Extracted files are treated strictly as data and are never granted executable permissions.

---

## 4. Input Validation, XSS & SVG Sandboxing

- User input and LLM-generated code/markdown are parsed using safe React component trees (`react-markdown`, `remark-gfm`).
- Inline SVG diagrams are rendered within sandboxed wrappers with stripped `<script>`, `onload`, `javascript:`, and external entity tags.
- Dangerous characters and control sequences are filtered via `sanitize_untrusted_text()`.

---

## 5. Network Operation Safety & Autonomy Boundaries

- **Category A (Automatic):** Read-only commands (e.g. `/system resource print`, `/ip address print`).
- **Category B (Confirmation Required):** Mutating network configurations (`/ip route add`, `/system reboot`, firewall changes). Requires explicit engineer approval with visible diff and risk disclosure.
- **Category C (Restricted):** Direct raw command execution outside authorized subnet scopes or destructive partition resets. Blocked automatically.
- Bounded discovery: Recursive discovery must observe max depth (default: 2 hops), IP subnet whitelists, and avoid crossing ISP boundary interfaces (`isp_upstream`).

---

## 6. Audit Accounting & Compliance

All authentication events, administrative role updates, configuration deployments, tool executions, and security rejections must emit structured audit events to `logs.db` and the central Event Bus:
- Fields: `timestamp_utc`, `event_type`, `tenant_id`, `user_id`, `ip_address`, `resource_id`, `action`, `status`, `risk_level`.
- Sensitive parameters and raw passwords must be redacted from audit payloads.
- Audit records are immutable (append-only) and viewable by authorized administrators in `/admin`.
