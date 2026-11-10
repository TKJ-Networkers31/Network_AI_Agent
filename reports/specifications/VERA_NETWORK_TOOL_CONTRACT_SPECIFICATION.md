# VERA NETWORK TOOL CONTRACT SPECIFICATION
## Authoritative Tool Manifests, Typed Parameter Schemas & Execution Contracts

**Document Identity:** VERA-TOOL-SPEC-2026-V1  
**Classification:** Interface Specification & Safety Protocol  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. SPECIFICATION SCOPE

This document provides the formal contract specification for all 47 network automation tools exposed within the VERA Platform:
- **32 Model Context Protocol (MCP) Network Tools** (`mcp_servers/network/server.py`)
- **15 Native RouterOS Tools** (`tools/mikrotik/routeros.py`)

Every tool specifies its input schema, return contract, authorization level, execution safety guards, timeout policy, and associated VAE generative block mappings.

---

## 2. NATIVE ROUTEROS TOOLS (15 TOOLS)

Native RouterOS tools are executed via `tools.mikrotik.routeros:execute_mikrotik_tool(tool_name, device_name)` over authenticated, secure SSH transports.

### Execution Policy:
- **Safety Level:** READ-ONLY / SAFE.
- **Allowed Command Set:** Strict whitelist mapping only. Arbitrary command execution is impossible.
- **Timeout:** 10.0s standard; 25.0s banner timeout on low-power hardware.

| Tool Name | Exact CLI Command Executed | Input Parameters | Return Contract | VAE Block Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `get_identity` | `/system identity print` | `device_name: str` | `{"name": str, "output": str}` | `metric-grid` |
| `get_resources` | `/system resource print` | `device_name: str` | `{"uptime": str, "cpu_load": int, "free_memory": str, ...}` | `resource-gauge`, `metric-grid` |
| `get_interfaces` | `/interface print` | `device_name: str` | `{"interfaces": List[dict], "output": str}` | `interface-status` |
| `get_ip_addresses` | `/ip address print` | `device_name: str` | `{"addresses": List[dict], "output": str}` | `markdown`, `table` |
| `get_routes` | `/ip route print` | `device_name: str` | `{"routes": List[dict], "output": str}` | `route-table-view` |
| `get_routes_v7` | `/routing route print` | `device_name: str` | `{"routes": List[dict], "output": str}` | `route-table-view` |
| `get_ospf_routes` | `/routing ospf route print`| `device_name: str` | `{"routes": List[dict], "output": str}` | `route-table-view` |
| `get_bgp_routes` | `/routing bgp route print` | `device_name: str` | `{"routes": List[dict], "output": str}` | `route-table-view` |
| `get_firewall` | `/ip firewall filter print` | `device_name: str` | `{"rules": List[dict], "output": str}` | `markdown`, `table` |
| `get_nat` | `/ip firewall nat print` | `device_name: str` | `{"nat_rules": List[dict], "output": str}` | `markdown`, `table` |
| `get_dns` | `/ip dns print` | `device_name: str` | `{"servers": str, "cache": str}` | `markdown` |
| `get_dhcp_client` | `/ip dhcp-client print` | `device_name: str` | `{"leases": List[dict], "output": str}` | `markdown`, `table` |
| `get_dhcp_server` | `/ip dhcp-server print` | `device_name: str` | `{"servers": List[dict], "output": str}` | `markdown`, `table` |
| `get_neighbors` | `/ip neighbor print` | `device_name: str` | `{"neighbors": List[dict], "output": str}` | `graph`, `table` |
| `get_arp` | `/ip arp print` | `device_name: str` | `{"arp": List[dict], "output": str}` | `markdown`, `table` |

---

## 3. NETWORK MCP TOOLS (32 TOOLS)

Exported via `mcp_servers/network/server.py` using official Model Context Protocol (MCP 2.x) schemas.

### 3.1 Group A: Host Diagnostics & Inventory (Read-Only)
| Tool Identifier | Parameters | Validation / Safety Guard | Output Type |
| :--- | :--- | :--- | :--- |
| `network_ping` | `target: str, count: int (1-10)` | IPv4/IPv6/Domain target validation | `{"alive": bool, "avg_rtt_ms": float}` |
| `network_nslookup`| `target: str` | Domain/IP target validation | `{"answers": List[str], "canonical": str}` |
| `network_traceroute`| `target: str` | Target validation; bounded hops (20) | `{"reached": bool, "hops": List[dict]}` |
| `network_list_devices`| `include_disabled: bool` | Mask sensitive credentials | `{"devices": List[dict]}` |
| `snmp_get_system_info`| `host: str, community: str` | Read-only UDP probe | `{"sysDescr": str, "uptime": str}` |
| `snmp_get_interface_traffic`| `host: str, interface: str` | Read-only UDP probe | `{"rx_bps": int, "tx_bps": int}` |

### 3.2 Group B: RouterOS Telemetry & State Inspection (Read-Only)
| Tool Identifier | Parameters | Safety Guard | VAE Generative Mapping |
| :--- | :--- | :--- | :--- |
| `mikrotik_get_identity` | `device_name: str` | Read-only CLI print | `metric-grid` |
| `mikrotik_get_resources`| `device_name: str` | Read-only CLI print | `resource-gauge`, `metric-grid` |
| `mikrotik_get_interfaces`| `device_name: str` | Read-only CLI print | `interface-status` |
| `mikrotik_get_ip_addresses`| `device_name: str`| Read-only CLI print | `table` |
| `mikrotik_get_routes` | `device_name: str` | Read-only CLI print | `route-table-view` |
| `mikrotik_get_firewall` | `device_name: str` | Read-only CLI print | `table` |
| `mikrotik_get_nat` | `device_name: str` | Read-only CLI print | `table` |
| `mikrotik_get_dns` | `device_name: str` | Read-only CLI print | `markdown` |
| `mikrotik_get_dhcp_client`| `device_name: str` | Read-only CLI print | `table` |
| `mikrotik_get_dhcp_server`| `device_name: str` | Read-only CLI print | `table` |
| `mikrotik_get_neighbors`| `device_name: str` | Read-only CLI print | `graph` |
| `mikrotik_get_arp` | `device_name: str` | Read-only CLI print | `table` |

### 3.3 Group C: Network Topology, Intelligence & Simulation
| Tool Identifier | Parameters | Safety Guard | Output Contract |
| :--- | :--- | :--- | :--- |
| `network_get_topology` | `tenant_id: Optional[str]` | Read-only topology graph query | `{"nodes": list, "edges": list}` |
| `network_find_path` | `source: str, target: str` | Graph shortest path traversal | `{"path": list, "distance": int}` |
| `network_analyze_change_impact`| `target_node: str` | In-memory graph clone simulation | `{"isolated_nodes": list, "risk": str}` |
| `network_troubleshoot_node`| `node_id: str` | Read-only epistemic inference | `{"root_cause": str, "confidence": float}` |
| `mikrotik_diagnose_route`| `device_name: str, target_ip: str`| LPM RIB table lookup | `{"next_hop": str, "matched_route": str}` |
| `mikrotik_audit_firewall`| `device_name: str` | Read-only security audit | `{"open_risks": list, "score": int}` |
| `mikrotik_audit_vlan` | `device_name: str` | Read-only VLAN configuration audit | `{"vlan_mismatches": list}` |
| `mikrotik_generate_report`| `device_name: str` | Aggregate multi-point audit | `{"health_summary": dict, "recommendations": list}` |

### 3.4 Group D: Configuration Planning & Script Validation (Safe Dry-Run)
| Tool Identifier | Parameters | Safety Guard | Output Contract |
| :--- | :--- | :--- | :--- |
| `mikrotik_validate_script`| `script_body: str` | Static AST / regex syntax validation | `{"valid": bool, "warnings": list}` |
| `mikrotik_plan_config_change`| `device_name: str, commands: List[str]` | Dry-run change impact analysis | `{"planned_actions": list, "diff": str}` |
| `device_connect` | `device_name: str` | Non-mutating SSH handshake | `{"connected": bool, "session_id": str}` |
| `device_disconnect` | `device_name: str` | Session teardown | `{"closed": bool}` |

### 3.5 Group E: State-Changing Operations (Guarded / Confirmed Actions)
| Tool Identifier | Parameters | Mandatory Safety Guards | VAE Block Mapping |
| :--- | :--- | :--- | :--- |
| `mikrotik_apply_config` | `device_name: str, commands: List[str], approved: bool` | Requires explicit `approved=True` parameter; rejects dangerous commands (`reset-configuration`, `reboot`, `file remove`) | `action-card`, `config-diff` |
| `mikrotik_execute_command`| `device_name: str, command: str` | Blocked dangerous regex patterns; logged in audit trail | `action-card` |

---

## 4. SECURITY & PERMISSION ENFORCEMENT SUMMARY
1. **Zero Secret Leakage:** All passwords, private keys, and API tokens are redacted (`***REDACTED***`) in all logs, step events, and MCP tool results.
2. **Explicit User Approval:** Any mutating operation generates an `action-card` requiring two-factor or interactive user confirmation before execution.
3. **Disallowed Command Blacklist:** Dangerous RouterOS commands that would cause unrecoverable hardware bricking or catastrophic data loss are intercepted and aborted at the gateway level.
