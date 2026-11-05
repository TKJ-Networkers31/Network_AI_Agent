# AIRA OS — NMS SECURITY & READ-ONLY BOUNDARY
## Architectural Enforcement of Zero-Configuration Mutation & Secret Protection

**Document Version:** 5.0.0  
**Phase:** Networking V — Work Package 5.0  
**Target:** Read-Only Telemetry Security Specification  
**Status:** `ARCHITECTURE_SPECIFICATION_ONLY`

---

## 1. Zero-Mutation Monitoring Mandate

The fundamental security principle of AIRA OS NMS is:

> [!CAUTION]
> **NMS IS STRICTLY A MONITORING & OBSERVABILITY SYSTEM.**
> Under NO circumstances may the NMS poller, scheduler, anomaly engine, or alert workflow execute configuration modifications on any network device.

### Explicitly Forbidden Operations:
- **No Device Reboots:** Absolutely no `/system reboot`, `/system shutdown`, or SNMP reboot traps.
- **No Interface Toggling:** No `enable`, `disable`, `set`, or `comment` commands dispatched to physical or virtual interfaces.
- **No Routing/IP Alterations:** Zero additions, removals, or edits in `/ip route`, `/routing`, `/ip address`, or `/ip dhcp-server`.
- **No Firewall Manipulations:** Zero changes to `/ip firewall filter`, `nat`, `mangle`, or `raw`.
- **No Script Uploads or Arbitrary Execution:** Completely forbids `:execute`, `/system script run`, `/tool fetch`, or shell escaping.

---

## 2. Protocol Security Controls

### 2.1 RouterOS CLI / SSH Boundary
All SSH interactions route exclusively through [`UnifiedCommandExecutor`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/command_execution.py) and [`validate_readonly_command`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/security.py).

#### Authorized NMS Command Whitelist:
```python
NMS_APPROVED_COMMANDS = frozenset({
    "/system identity print",
    "/system resource print",
    "/system resource print without-paging",
    "/system routerboard print",
    "/system routerboard print without-paging",
    "/system health print",
    "/system health print without-paging",
    "/interface print",
    "/interface print without-paging",
    "/interface print detail without-paging",
    "/interface print stats-detail without-paging",
    "/interface ethernet print without-paging",
    "/interface wireless print without-paging",
    "/ip address print without-paging",
    "/ip route print detail without-paging",
    "/routing route print detail without-paging",
    "/ip neighbor print without-paging",
    "/routing ospf neighbor print without-paging",
    "/log print without-paging",
})
```

#### Rejection Rules:
Any dispatched string containing `;`, `\n`, `\r`, `[`, `]`, `{`, `}`, `file=`, `append=`, `:global`, `:local`, `:put`, `:delay`, or mutating verbs (`add`, `set`, `remove`, `enable`, `disable`, `reset`) is instantly rejected with `SecurityRejectionError` prior to socket transmission.

### 2.2 SNMP Security
- **Read-Only PDU Enforcement:** The poller dispatches exclusively `GetRequest` and `GetNextRequest` / `GetBulkRequest` (SNMPv2c/v3).
- **Prohibition of SetRequest:** PDU type `SetRequest` (0xA3) is strictly excluded from the codebase; no codepath exists to construct or transmit an SNMP SET packet.
- **SNMPv3 Cryptography:** Supports `usmHMACSHAAuthProtocol` and `usmAesCfb128Protocol` for encrypted management channels.

### 2.3 ICMP Echo Restrictions
- Socket payload is fixed to a static 32-byte non-executable ping signature (`AIRA_PING_PROBE_V5`).
- Frequency is rate-limited per device profile to prevent ICMP flood detection on edge firewalls.

---

## 3. Secret Redaction & Log Sanitization

To ensure diagnostic logs, API payloads, and frontend dashboards never leak network authentication materials:

1. **SNMP Community Masking:** Community strings (`snmp_community`) are stored encrypted or masked in database profiles; in logs and API JSON responses, they are replaced with `***MASKED***`.
2. **SSH Credentials:** Passwords, passphrases, and private key bytes are managed solely within the [`InventoryStore`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/inventory_store.py) SQLite boundary. They are never serialized into `nms_device_profiles`, event payloads, or WebSocket notifications.
3. **Regex Scrubbing:** All outgoing log lines pass through [`mask_sensitive_data`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/mcp_servers/network/security.py), automatically scrubbing patterns matching passwords, tokens, auth keys, and private blocks.

---

## 4. API RBAC & Read-Only Exposure

All NMS REST endpoints (`AIRA_ECOSYSTEM/api/routers/nms.py`) enforce explicit operation modes:
- **Telemetry Query Endpoints (`GET`):** Expose read-only metric rollups, device status, and incident records.
- **Administrative Settings (`PUT /settings`, `PUT /profile`):** Modify local polling parameters (such as polling intervals or failure thresholds); they do **not** modify remote router configurations.
- **Incident Acknowledgment (`POST /incidents/{id}/acknowledge`):** Mutates only the local AIRA OS incident database record, recording operator identity and timestamp.
