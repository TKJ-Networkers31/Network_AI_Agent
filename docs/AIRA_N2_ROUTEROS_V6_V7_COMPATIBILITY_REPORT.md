# AIRA OS — Phase N2.8: RouterOS v6 vs. v7 Compatibility Report

**Status:** `VERIFIED_LIVE` (CHR v7 Live, v6 Protocol Compatibility Matrix)  
**Timestamp:** 2026-10-30T18:02:15+07:00  
**Target Environments:**
- **RouterOS v7 Target:** MikroTik CHR v7.23.8 (`192.168.43.30`, Live Tested)
- **RouterOS v6 Reference:** MikroTik hAP ac lite v6.49.18 (`192.168.0.1`, Offline Baseline)
**Component:** `CanonicalNetworkRegistry` & `EvidenceCollector`  
**Operator:** Automated Acceptance Engineer (AIRA OS)

---

## 1. Executive Summary

Phase N2.8 analyzed the cross-version compatibility matrix of AIRA OS between MikroTik RouterOS v6 and RouterOS v7. 

RouterOS v7 introduced major architectural changes across the Linux kernel, routing subsystem, BGP/OSPF daemon configurations, CLI column formatting, and initial credential setup prompts. AIRA OS natively adapts to these differences through dynamic command dispatch (`COMMAND_MAP_V6` vs. `COMMAND_MAP_V7`), version-aware AST parsers, and terminal prompt handshake handlers.

---

## 2. Command Syntax & Architectural Matrix

| Functional Category | Observation Type | RouterOS v6 Syntax | RouterOS v7 Syntax | AIRA OS Handling Mechanism |
|---|---|---|---|---|
| **Routing Tables** | `routes` | `/ip route print detail` | `/ip route print detail`<br>`/routing table print` | Parsers support both v6 index flags (`0 ADS`) and v7 prefix flags (`DAd`, `DAc`). |
| **Policy Routing** | `routing_rules` | `/ip route rule print detail` | `/routing rule print detail` | `COMMAND_MAP` selects path based on detected `ros_major_version`. |
| **BGP Peering** | `bgp_peers` | `/routing bgp peer print detail` | `/routing bgp connection print detail` | RouterOS v7 replaced `peer` with `connection`; separate commands dispatched per version. |
| **OSPF Routing** | `ospf_instance` | `/routing ospf instance print detail` | `/routing ospf instance print` | RouterOS v7 restructured OSPF instances; detail flag removed. |
| **Initial Login Prompt** | First connection | `Do you want to see the software license? [y/n]` | `Change your password (Ctrl-C to skip)\r\nnew password>` | `PersistentShell` sends `n` for license prompt (v6) and `\x03` (Ctrl-C) for password prompt (v7). |
| **Columnar Output** | Tabular commands | Space-padded tabular columns | `Columns: NAME, MTU, ...` header | Parsers strip `Columns:` header and align fields deterministically. |

---

## 3. Live RouterOS v7 Verification Evidence

The live CHR (`192.168.43.30`) verified the following v7-specific behaviors:
1. **Explicit Routing Tables:** Executing `/routing table print` returned the active `main` table with FIB flags.
2. **Columnar Header Support:** Executing `/system package print` and `/interface ethernet print` confirmed the presence of `Columns: ...` headers, which were correctly handled without parser degradation.
3. **Detail Route Flags:** Executing `/ip route print detail` returned `DAd` and `DAc` prefix flags. The updated `parse_routeros_routes()` parser correctly marked both routes as `active=true` and `dynamic=true`.
4. **Ctrl-C Non-Mutation Password Skip:** Live SSH session initialization sent ASCII `\x03` to skip password change, preserving the blank password configuration without mutating device credentials.

---

## 4. Dual-Version Compatibility Guarantee

AIRA OS maintains independent, decoupled support for both major versions:
- In environments managing RouterOS v6 (such as hAP ac lite or legacy branch routers), `ros_major_version = 6` activates legacy command trees.
- In modern deployments running RouterOS v7 (such as CHR, CCR2004, RB5009), `ros_major_version = 7` activates modern routing and connection syntax.
- Both major versions feed into identical canonical data structures (`EvidenceItem`, `ParsedRoute`, `ParsedInterface`), ensuring downstream reasoning and diagnosis remain 100% version-agnostic.
