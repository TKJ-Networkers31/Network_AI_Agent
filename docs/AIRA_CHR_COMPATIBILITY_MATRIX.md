# AIRA OS — MikroTik RouterOS v6 vs. v7 Compatibility Matrix
## Subsystem Mapping, Parser Differences, Unsupported Commands, and Version Boundaries

**Workspace:** `D:\data\agent_ai`  
**Phase:** Phase 8.1 — Controlled CHR Live Verification Preparation  
**Reference Implementations:**  
- `AIRA_ECOSYSTEM/core/network_intelligence/evidence.py` (`COMMAND_MAP_V6`, `COMMAND_MAP_V7`)  
- `AIRA_ECOSYSTEM/agents/akane/reasoning_engine.py` (`parse_routeros_routes`, `parse_routeros_firewall`)  
- `AIRA_ECOSYSTEM/core/network_intelligence/security.py` (`APPROVED_PRINT_PREFIXES`, `validate_readonly_command`)  

---

## 1. Executive Policy & Architectural Boundary

MikroTik RouterOS version 7 represents a fundamental re-architecture from RouterOS version 6, replacing the legacy Linux 3.3 kernel with Linux 5.6.3+ and introducing an entirely rewritten routing engine (*Routing v7*).

### Non-Negotiable Engineering Rules
1. **No Cross-Version Inference**: Validation or live verification on RouterOS v7 **never** proves or implies compatibility on RouterOS v6. Each major version must be independently tested against dedicated appliances.
2. **Version-Aware Command Dispatch**: AIRA OS must resolve target version prior to dispatching commands (`ros_major_version` 6 vs. 7), selecting the exact syntax accepted by that version.
3. **Fail-Closed on Version Ambiguity**: If a target's RouterOS major version cannot be deterministically verified, AIRA OS defaults to standard baseline syntax and records an `IDENTITY_UNVERIFIED` limitation.

---

## 2. Command Mapping & Syntactic Differences

The table below contrasts the command paths and syntaxes required across RouterOS v6 and RouterOS v7 for all supported diagnostic evidence types:

| Subsystem / Evidence Type | RouterOS v6 Syntax | RouterOS v7 Syntax | Architectural & Parsing Differences |
| :--- | :--- | :--- | :--- |
| **System Identity** | `/system identity print` | `/system identity print` | Identical syntax across v6 and v7. |
| **System Resources** | `/system resource print` | `/system resource print` | v7 outputs updated kernel version, memory architecture, and CPU topology. |
| **System Routerboard** | `/system routerboard print` | `/system routerboard print` | Identical syntax. On virtual CHR appliances, `routerboard: no` is expected. |
| **System Packages** | `/system package print` | `/system package print` | v7 combines routing and wireless packages into single bundle (`routeros`). |
| **Interfaces (Overview)** | `/interface print detail` | `/interface print detail` | v7 includes `Columns:` header in tabular output and new hardware offload flags. |
| **Ethernet Interfaces** | `/interface ethernet print` | `/interface ethernet print` | Identical read-only syntax. |
| **Bridge Configuration** | `/interface bridge print detail` | `/interface bridge print detail` | Identical syntax. v7 adds dynamic IGMP snooping and DHCP snooping state attributes. |
| **Bridge Ports** | `/interface bridge port print detail` | `/interface bridge port print detail` | v7 adds Fast-Leave, Trusted port, and Hardware Offload (`H`) status. |
| **Bridge VLAN Table** | `/interface bridge vlan print detail` | `/interface bridge vlan print detail` | v7 includes dynamic hardware-offload VLANs and CPU bridge mappings. |
| **IP Addresses** | `/ip address print detail` | `/ip address print detail` | Both supported. In tabular mode, v7 uses unified `Columns:` schema. |
| **IP Routing Table** | `/ip route print detail` | `/ip route print detail` | **Major Flag Difference:**<br/>v6 uses spaced flags: `A S`, `ADC`<br/>v7 uses compound acronyms: `As`, `DAc`, `DAo`, `DAb`. |
| **Policy Routing Rules** | `/ip route rule print detail` | `/routing rule print detail` | **Namespace Relocated in v7:**<br/>v6: `/ip route rule`<br/>v7: `/routing rule`. Calling `/ip route rule` in v7 fails with syntax error. |
| **Routing Tables** | N/A (implicit `main`) | `/routing table print` | v7 requires explicit table definitions for VRF and policy routing. |
| **Routing Filters** | `/routing filter print` | `/routing filter rule print` | **Complete Language Redesign in v7:**<br/>v6: Action rules with flat parameters (`action=accept`).<br/>v7: Script expression language (`rule="if (...) { accept; }"`). |
| **OSPF Neighbors** | `/routing ospf neighbor print` | `/routing ospf neighbor print` | v7 tabular layout includes `instance` column and state names (`Full`, `2-Way`). |
| **OSPF Instances** | `/routing ospf instance print detail` | `/routing ospf instance print` | **Parameter Incompatibility in v7:**<br/>`/routing ospf instance print detail` is unsupported in v7. v7 uses template-based interface configuration. |
| **BGP Peers / Connections**| `/routing bgp peer print detail` | `/routing bgp connection print detail` | **Namespace & Parameter Redesign in v7:**<br/>v6: `/routing bgp peer` with `remote-address`, `remote-as`.<br/>v7: `/routing bgp connection` with dotted notation `remote.address`, `remote.as`. |
| **BGP Runtime Sessions** | N/A (merged into peer) | `/routing bgp session print detail` | v7 separates connection declaration from active dynamic TCP peering sessions. |
| **Firewall Filter** | `/ip firewall filter print detail` | `/ip firewall filter print detail` | Core matchers identical (`chain`, `action`, `connection-state`, `in-interface`). |
| **Firewall NAT** | `/ip firewall nat print detail` | `/ip firewall nat print detail` | Core matchers identical (`srcnat`, `dstnat`, `masquerade`, `redirect`). |
| **Firewall Mangle** | `/ip firewall mangle print detail` | `/ip firewall mangle print detail` | Core matchers identical. v7 routing-mark references `/routing table`. |
| **ARP Table** | `/ip arp print detail` | `/ip arp print detail` | Identical syntax. v6 uses `D`, `C`; v7 uses `DA`, `DH`. |
| **DNS Cache & Config** | `/ip dns print` | `/ip dns print` | Identical syntax. v7 adds DoH (`doh-server`) configuration attributes. |

---

## 3. Parser & Normalizer Implementation Details

In `AIRA_ECOSYSTEM/core/network_intelligence/evidence.py` and `AIRA_ECOSYSTEM/agents/akane/reasoning_engine.py`, normalizers are engineered to handle version-specific formatting differences transparently:

### 3.1. Routing Table Flags Parser (`parse_routeros_routes`)
```python
# Handles both v6 spaced flags ("A S", "A D C") and v7 compound flags ("As", "DAc", "DAo")
flags_upper = flags.upper()
is_active = "A" in flags_upper or not flags_upper
is_dynamic = "D" in flags_upper
is_connect = "C" in flags_upper
is_static = "S" in flags_upper
```
- In v6, `A S` indicates Active Static; in v7, `As` indicates Active Static.
- In v6, `A D C` indicates Active Dynamic Connected; in v7, `DAc` indicates Dynamic Active Connected.
- The parser normalizes both into boolean attributes on `ParsedRoute` (`active`, `dynamic`, `connect`, `static`).

### 3.2. BGP Peer Normalizer (`_parse_bgp_peers`)
```python
# Dual regex matching for flat (v6) vs dotted (v7) parameter notation:
remote_ip_m = re.search(r"remote\.address=([0-9\.]+)", line_s) or re.search(r"remote-address=([0-9\.]+)", line_s)
remote_as_m = re.search(r"remote\.as=(\d+)", line_s) or re.search(r"remote-as=(\d+)", line_s)
prefix_count_m = re.search(r"prefix-count=(\d+)", line_s) or re.search(r"prefixes=(\d+)", line_s)
```
- v6 parameter `remote-address` maps seamlessly to v7 `remote.address`.
- v6 parameter `prefix-count` maps seamlessly to v7 `prefixes`.

---

## 4. Unsupported Commands in Read-Only Diagnostic Mode

The following commands are unconditionally prohibited on both RouterOS v6 and RouterOS v7 during all diagnostic, preflight, and investigation operations:

| Category | Forbidden Commands / Patterns | Reason for Prohibition |
| :--- | :--- | :--- |
| **Configuration Mutation** | `/... add`, `/... set`, `/... remove`, `/... enable`, `/... disable` | Modifies active running configuration; violates read-only non-mutation guarantee. |
| **Device Life-cycle** | `/system reboot`, `/system shutdown`, `/system reset-configuration` | Causes catastrophic device availability loss; terminates active monitoring sessions. |
| **Filesystem Redirection** | `file=evil.txt`, `append=data.rsc`, `stats-file=out.txt` | Writes to persistent flash memory; risk of disk exhaustion or payload planting. |
| **Command Substitution** | `[find ...]`, `[reboot]`, `[system resource get version]` | Executes nested arbitrary commands via CLI evaluation engine. |
| **Script Blocks** | `{ ... }`, `do={ ... }`, `:execute { ... }` | Executes multi-line scripting engine blocks. |
| **Colon Script Builtins** | `:execute`, `:put`, `:delay`, `:set`, `:global`, `:local` | Invokes scripting language primitives outside standard inspection commands. |
| **Unbounded Streaming** | `/interface monitor-traffic`, `/tool torch`, `interval=1`, `follow`, `continuous` | Floods SSH transport channel with continuous ANSI updates; freezes session threads. |
| **Sensitive Credential Dumps** | `/export show-sensitive`, `/user print detail` | Exposes plaintext passwords or SNMP community strings in audit trails. |
| **High-Count Active Probes** | `/ping count=100`, `/tool traceroute count=50` | Unbounded ICMP/UDP flooding; capped at `count=5` for ping and `count=3` for traceroute. |

---

## 5. Live Verification Status Matrix

| Major Version | Current Verification Level | Primary Lab Environment | Verification Readiness | Remaining Blockers |
| :--- | :--- | :--- | :--- | :--- |
| **RouterOS v7** | **Offline Hardened (Syntax & Fixtures)** | MikroTik CHR v7.14+ (KVM / Proxmox / VirtualBox) | **`READY_FOR_AUTHORIZED_CHR_TESTING`** | Live test execution is currently **`BLOCKED (LAB_OFFLINE)`** pending physical host activation of isolated lab VM. |
| **RouterOS v6** | **Live Probed & Offline Fixtures** | Physical MikroTik hAP ac lite (`192.168.0.1`, v6.49.18) | **`ROUTEROS_V6_VERIFIED_WITH_GAPS`** | Live read-only probing succeeded; full live verification requires dedicated `aira-audit` user and isolated lab identity. |

---

## 6. Readiness Assessment Conclusion

```
================================================================================
                    CHR INTEGRATION READINESS ASSESSMENT
================================================================================
 Overall Status: READY_FOR_AUTHORIZED_CHR_TESTING
 
 Evaluation:
 - RouterOS Command Hardening: 100% complete (63 adversarial tests passed).
 - Deployment Guide: docs/AIRA_CHR_LAB_DEPLOYMENT_GUIDE.md created.
 - Live Verification Plan: docs/AIRA_CHR_LIVE_VERIFICATION_PLAN.md created.
 - Compatibility Matrix: docs/AIRA_CHR_COMPATIBILITY_MATRIX.md updated.
 - Baseline Test Health: 958 backend passed, 247 frontend passed, build OK.
 - RouterOS v6: Verified with physical hAP ac lite live probe (v6.49.18).
 - RouterOS v7: Offline verified; live status remains BLOCKED (LAB_OFFLINE).
 
 Operational Constraint:
 - Live CHR v7 testing will only proceed once an authorized CHR VM is running and
   reachable at 10.10.10.10:22 with the aira-audit read-only user.
================================================================================
```
