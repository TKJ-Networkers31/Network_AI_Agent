# AIRA OS — Phase 8.6 RouterOS v6 vs. v7 Compatibility Results
## Detailed Evaluation of Syntactic, Semantic, and Architectural Differences

**Project:** AIRA OS — Network Intelligence & Diagnostic Platform  
**Workspace:** `D:\data\agent_ai`  
**Execution Timestamp:** 2026-10-30T12:50:00+07:00  
**Evaluated Versions:** RouterOS v6.49.18 (Physical Device) & RouterOS v7.14+ (Syntax & Fixtures)  

---

## 1. Executive Summary

MikroTik RouterOS v7 introduces major modifications across the routing stack, kernel architecture, and CLI output formatting. AIRA OS maintains separate command maps, normalizers, and configuration planning templates for RouterOS v6 and RouterOS v7.

This document compiles the empirical verification results for both versions, contrasting live-device telemetry from physical RouterOS v6.49.18 with offline fixtures and models for RouterOS v7.

---

## 2. Comprehensive Compatibility Evaluation

| Subsystem / Feature | RouterOS v6 (Observed Live) | RouterOS v7 (Verified Fixtures) | Compatibility Assessment |
| :--- | :--- | :--- | :--- |
| **System Identity** | `/system identity print` | `/system identity print` | **100% Compatible**. Live probe returned `name: MikroTik`. |
| **System Resources** | `/system resource print` | `/system resource print` | **100% Compatible**. Version parsing logic extracts major version `6` or `7`. |
| **IP Address Table** | Tabular and detail format supported. | Tabular format includes `Columns:` header. | **100% Compatible**. Parsers handle both multi-line detail and tabular headers. |
| **Routing Table Flags**| Spaced flags: `DC`, `ADC`, `A S`. | Compound flags: `DAc`, `As`, `DAo`. | **100% Compatible**. `parse_routeros_routes` maps both into normalized `ParsedRoute` objects. |
| **Policy Routing Rules** | `/ip route rule print detail` | `/routing rule print detail` | **Namespace Branching Active**: `COMMAND_MAP_V6` uses `/ip route rule`, while `COMMAND_MAP_V7` uses `/routing rule`. |
| **BGP Peering** | `/routing bgp peer print detail` (`remote-address=...`) | `/routing bgp connection print detail` (`remote.address=...`) | **Dual Regex Parsing**: `_parse_bgp_peers` handles both flat v6 syntax and dotted v7 syntax. |
| **OSPF Adjacency** | `/routing ospf neighbor print` | `/routing ospf neighbor print` | **100% Compatible**. Both output neighbor router-id, state, and address. |
| **OSPF Instance** | `/routing ospf instance print detail` | `/routing ospf instance print` | **Syntax Divergence**: v7 rejects `detail` on instance prints. Managed via version-specific command maps. |
| **Bridge VLAN Filtering** | `/interface bridge vlan print detail` | `/interface bridge vlan print detail` | **100% Compatible**. Both output tagged and untagged port lists. |
| **Firewall Filter & NAT** | Chains `input`, `forward`, `srcnat`, `dstnat`. | Identical chain architecture and action verbs. | **100% Compatible**. FastTrack and connection-state matchers identical. |

---

## 3. Version Resolution & Dispatch Mechanism

AIRA OS resolves device version through a 3-tier resolution hierarchy in [`CanonicalNetworkRegistry`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/canonical_network.py):
1. **Explicit Device Metadata**: Configured `os_version` or `ros_major_version` in inventory store.
2. **Preflight Live Probe**: Active query to `/system resource print` parsed via `parse_routeros_major_version()`.
3. **Conservative Default**: If unverified, falls back to RouterOS v7 baseline with status `IDENTITY_UNVERIFIED`.

---

## 4. Summary of Version Coverage Status

```
+-------------------------------------------------------------------------------+
| ROUTEROS VERSION COMPATIBILITY STATUS                                         |
+----------------------+--------------------+-----------------------------------+
| Target Platform      | Verification Level | Status Determination              |
+----------------------+--------------------+-----------------------------------+
| RouterOS v7          | Offline Hardened   | READY_FOR_AUTHORIZED_CHR_TESTING  |
|                      | (Syntax/Fixtures)  | (Live: BLOCKED - LAB_OFFLINE)     |
+----------------------+--------------------+-----------------------------------+
| RouterOS v6          | Live Probed (R1) & | ROUTEROS_V6_VERIFIED_WITH_GAPS    |
|                      | Offline Fixtures   | (Awaiting aira-audit provisioning)|
+----------------------+--------------------+-----------------------------------+
```
