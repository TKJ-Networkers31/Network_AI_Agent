# AIRA OS — Security & Read-Only Governance Model
## Comprehensive Security Architecture, Threat Mitigation, and Policy Enforcement

---

## 1. Executive Security Principles

AIRA OS operates under strict security and reliability principles designed for mission-critical ISP and enterprise environments:

1. **Strict Read-Only Execution**: The diagnostics pipeline and investigation engines are cryptographically and architecturally prevented from modifying network device configurations.
2. **Deterministic Allowlisting**: Only explicitly approved inspection commands are permitted to traverse the network interface layer.
3. **Defense-in-Depth Injection Prevention**: Command sanitization rejects all shell metacharacters before commands reach the SSH transport layer.
4. **Zero Credential Exposure**: Passwords, pre-shared keys, SNMP community strings, and private keys are redacted at ingestion and never written to logs, databases, or UI payloads.
5. **No Auto-Remediation**: All configuration changes are restricted to read-only plans, diffs, and validation packages requiring explicit operator approval.

---

## 2. Threat Model & Mitigations

| Threat Vector | Potential Impact | AIRA OS Mitigation Mechanism | Verification Test |
| :--- | :--- | :--- | :--- |
| **Command Injection (Shell Metacharacters)** | Execution of arbitrary shell/CLI commands via concatenated strings. | Delimiter rejection (`\0`, `\n`, `\r`, `;`, `\|`, `&`, `<`, `>`, `` ` ``, `$`). | `test_delimiters_and_malformed_syntax_rejected` |
| **RouterOS Command Substitution** | Embedded execution of subcommands via square brackets (e.g. `[reboot]`). | Unconditional rejection of `[` and `]` across all read-only diagnostic commands. | `test_audited_bypasses_are_strictly_rejected` |
| **RouterOS Script Code Blocks** | Execution of multiline script blocks via curly braces (e.g. `do={reboot}`). | Unconditional rejection of `{` and `}` across all read-only diagnostic commands. | `test_audited_bypasses_are_strictly_rejected` |
| **RouterOS Colon Script Commands** | Execution of engine scripting builtins (e.g. `:execute`, `:put`, `:delay`). | Regex rejection of script prefixes `:[a-zA-Z]`. | `test_audited_bypasses_are_strictly_rejected` |
| **Filesystem Redirection / Mutation** | Overwriting router flash/disk storage via `file=evil.txt` or `append=`. | Unconditional rejection of `file=`, `append=`, and `stats-file=` parameters. | `test_audited_bypasses_are_strictly_rejected` |
| **Session Freeze / Unbounded Streaming** | Router CPU exhaustion or SSH channel freeze via `interval=1`, `follow`. | Parameter rejection of `interval=` and streaming flags (`follow`, `freeze`, `continuous`). | `test_audited_bypasses_are_strictly_rejected` |
| **Accidental Mutation** | Unintended modification of routing, firewall, or interface state during diagnosis. | Architectural decoupling: diagnostics code has zero import or call paths to `SafeConfigEngine.apply_change`, plus token-level mutating verb checks. | `test_rejected_commands_never_invoke_safe_config_engine_apply` |
| **SSH Storm / DoS** | Router CPU exhaustion caused by rapid concurrent SSH connection attempts. | Target-level concurrency serialization (`asyncio.Lock` / single-flight lock) and session reuse via APCE. | `test_connection_reuse_and_single_flight` |
| **Credential Leakage** | Exposure of router credentials in logs, API responses, or stored evidence items. | Automated regex masking (`mask_sensitive_data()`) on all raw CLI outputs prior to persistence. | `test_phase7_zero_credential_leakage_in_preflight_and_investigation` |
| **Stale / Spoofed Evidence** | Diagnostic decisions based on outdated or cross-contaminated telemetry. | Unique `correlation_id` propagation, timestamp freshness classification, and contradiction detection. | `test_adversarial_7_stale_evidence_flagged_with_contradiction` |
| **Privilege Escalation** | Unauthorized client triggering management-plane actions or topology mutations. | Bearer token authentication via `AIRA_TOPOLOGY_ADMIN_TOKEN` on administrative API routes. | `test_phase6_observability_and_security.py` |

---

## 3. RouterOS Command Allowlisting & Validation Pipeline

Every command dispatched via `ConnectionManager.execute_command()`, `execute_for_device()`, or `execute_safe_readonly_command()` must pass `validate_readonly_command()`:

```mermaid
flowchart TD
    CmdIn["Candidate Command Input"] --> LengthCheck{"Length <= 512 &<br/>Non-empty?"}
    LengthCheck -- No --> RejectLen["REJECT: Empty or Exceeds Length"]
    LengthCheck -- Yes --> DelimCheck{"Contains Shell Metachars?<br/>\0 \n \r ; | & < > ` $"}
    DelimCheck -- Yes --> RejectDelim["REJECT: Shell Delimiter Detected"]
    DelimCheck -- No --> BracketCheck{"Contains Substitution or Blocks?<br/>[ ] or { }"}
    BracketCheck -- Yes --> RejectBracket["REJECT: Square/Curly Brackets Forbidden"]
    BracketCheck -- No --> ColonScriptCheck{"Contains Script Prefix?<br/>:[a-zA-Z]"}
    ColonScriptCheck -- Yes --> RejectColon["REJECT: RouterOS Scripting Forbidden"]
    ColonScriptCheck -- No --> FileRedirectCheck{"Contains File Redirection?<br/>file= or append="}
    FileRedirectCheck -- Yes --> RejectFile["REJECT: File Redirection Forbidden"]
    FileRedirectCheck -- No --> StreamCheck{"Contains Streaming Loop?<br/>interval= or follow/freeze"}
    StreamCheck -- Yes --> RejectStream["REJECT: Unbounded Streaming Forbidden"]
    StreamCheck -- No --> QuoteCheck{"Quotes Balanced?<br/>Even count of ' and \""}
    QuoteCheck -- No --> RejectQuote["REJECT: Unclosed Quotes (Fail Closed)"]
    QuoteCheck -- Yes --> AllowlistCheck{"Matches Approved<br/>Print Namespace / Tool?"}
    AllowlistCheck -- No --> RejectAllow["REJECT: Namespace Not in Allowlist"]
    AllowlistCheck -- Yes --> MutatingVerbCheck{"Tokens Contain<br/>MUTATING_VERBS?"}
    MutatingVerbCheck -- Yes --> RejectVerb["REJECT: Mutating Verb in Arguments"]
    MutatingVerbCheck -- No --> Dispatch["Execute Safe Read-Only Command"]
```

### 3.1. Forbidden Syntactic Constructs
1. **Shell Delimiters & Control Characters**: `\0`, `\n`, `\r`, `;`, `|`, `` ` ``, `$`, `&`, `<`, `>`
2. **Command Substitution**: `[` and `]` (prevents RouterOS embedded evaluations like `[reboot]` or `[find ...]`)
3. **Script Code Blocks**: `{` and `}` (prevents execution of multi-statement blocks like `do={...}`)
4. **Script Prefixes**: `:[a-zA-Z]` (blocks `:execute`, `:put`, `:delay`, `:set`, etc.)
5. **Disk Mutations**: Parameter patterns matching `(?i)\b[\w-]*file\s*=` and `(?i)\bappend\s*=`
6. **Streaming & Freezing Loops**: Parameter patterns matching `(?i)\binterval\s*=` and `(?i)\b(follow|follow-only|freeze|continuous)\b`
7. **Unclosed Quotes**: Fails closed if double or single quotes are odd-numbered.

### 3.2. Approved Read-Only Namespaces
Inspection verbs must start with one of 38 approved namespaces, or bounded tools:
- `/system identity print`
- `/system resource print`
- `/system package print`
- `/system routerboard print`
- `/system clock print`
- `/interface print`
- `/interface bridge print`
- `/interface bridge port print`
- `/interface bridge vlan print`
- `/interface vlan print`
- `/interface ethernet print`
- `/interface wireless print`
- `/ip address print`
- `/ip route print`
- `/ip route rule print`
- `/ip firewall filter print`
- `/ip firewall nat print`
- `/ip firewall mangle print`
- `/ip firewall raw print`
- `/ip firewall address-list print`
- `/ip firewall connection print`
- `/ip arp print`
- `/ip neighbor print`
- `/ip dns print`
- `/ip pool print`
- `/ip dhcp-server print`
- `/ip dhcp-server lease print`
- `/ip dhcp-client print`
- `/routing rule print`
- `/routing table print`
- `/routing filter rule print`
- `/routing filter print`
- `/routing ospf neighbor print`
- `/routing ospf instance print`
- `/routing ospf interface print`
- `/routing ospf interface-template print`
- `/routing bgp peer print`
- `/routing bgp connection print`
- `/routing bgp session print`
- Bounded tools:
  - `/ping <ip> count=[1-5]`
  - `/tool traceroute <ip> count=[1-3]`
  - `/export compact` or `/export verbose=no`

Mutating verbs (`add`, `set`, `remove`, `enable`, `disable`, `reset`, `reboot`, `shutdown`, `edit`, `delete`, `install`, `upgrade`, `downgrade`, `uninstall`, `format`, `flash`, `restore`) are strictly forbidden in arguments outside quoted string literals. String literals (e.g. `comment="reboot target"`) are permitted for filter matching.

---

## 4. Credential Protection & Redaction Standard

Before raw CLI outputs or device configuration exports are persisted to SQLite or serialized over HTTP, the `mask_sensitive_data()` filter is applied:

```python
SENSITIVE_PATTERNS = [
    (r'(password=)[^\s]+', r'\1***REDACTED***'),
    (r'(secret=)[^\s]+', r'\1***REDACTED***'),
    (r'(wpa2-pre-shared-key=)[^\s]+', r'\1***REDACTED***'),
    (r'(community=)[^\s]+', r'\1***REDACTED***'),
    (r'(private-key=)[^\s]+', r'\1***REDACTED***'),
    (r'(preshared-key=)[^\s]+', r'\1***REDACTED***'),
]
```

### Empirical Proof
Unit tests in `tests/test_phase7_live_verification.py` verify that even when simulated passwords are passed into preflight or CLI probes, zero unredacted secrets appear in:
1. `PreflightResult.to_dict()`
2. `EvidenceItem.raw_excerpt`
3. `IncidentRecord.observed_facts`
4. Application log output

---

## 5. API Authentication & Role-Based Access Control

AIRA OS secures administrative and diagnostic endpoints using token authentication:
- **Environment Variable**: `AIRA_TOPOLOGY_ADMIN_TOKEN`
- **Protected Endpoints**:
  - `POST /api/intelligence/preflight`
  - `POST /api/intelligence/incidents`
  - `POST /api/intelligence/plans`
  - `POST /api/topology/*`
- **Workstation Development Fallback**: If `AIRA_TOPOLOGY_ADMIN_TOKEN` is unset in a local non-production environment, requests log a security warning and allow local operation, preventing developer lockouts while securing production deployments.
