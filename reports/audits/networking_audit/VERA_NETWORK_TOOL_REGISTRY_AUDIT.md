# VERA NETWORK TOOL REGISTRY AUDIT
## Comprehensive Inspection of AI-Exposed Tools, MCP Servers, Akane/Rei Capabilities & Safety Guards

**Document Version:** 1.0.0  
**Audit Target:** VERA Tool Registries & AI Interfaces  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** AI Tool Architecture & Command Safety Audit  
**Status:** VALIDATED WITH KNOWN LEGACY STRINGS  

---

## 1. EXECUTIVE TOOL REGISTRY OVERVIEW

The VERA platform provides network operations capabilities to AI agents (such as Akane for operational execution and Rei for inventory and reasoning) through a layered tool hierarchy:

1. **Native RouterOS Tool Suite** ([tools/mikrotik/routeros.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tools/mikrotik/routeros.py)): Direct, hardened execution routines utilizing connection pooling.
2. **Network MCP Server** ([mcp_servers/network/server.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/mcp_servers/network/server.py)): 32 structured tools complying with the Model Context Protocol (MCP) standard.
3. **Akane Network Automation Toolkit** ([agents/akane/network_tools.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/agents/akane/network_tools.py)): High-level agent functions wrapping the Network MCP Client.
4. **Rei Inventory Toolkit** ([agents/rei/inventory_tools.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/agents/rei/inventory_tools.py)): Schema-validated device and credential management tools.

---

## 2. NATIVE ROUTEROS TOOL SUITE AUDIT

Located in [tools/mikrotik/routeros.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tools/mikrotik/routeros.py), this module implements `execute_mikrotik_tool(tool_name, device_name)` backed by the immutable command mapping table `COMMANDS`:

| Tool Name | Underlying CLI Command | Operation Mode | Safety Level |
| :--- | :--- | :---: | :---: |
| `get_interfaces` | `/interface print` | Read-Only | SAFE |
| `get_ip_addresses` | `/ip address print` | Read-Only | SAFE |
| `get_routes` | `/ip route print` | Read-Only | SAFE |
| `get_routes_v7` | `/routing route print` | Read-Only | SAFE |
| `get_ospf_routes` | `/routing ospf route print` | Read-Only | SAFE |
| `get_bgp_routes` | `/routing bgp route print` | Read-Only | SAFE |
| `get_firewall` | `/ip firewall filter print` | Read-Only | SAFE |
| `get_resources` | `/system resource print` | Read-Only | SAFE |
| `get_identity` | `/system identity print` | Read-Only | SAFE |
| `get_dns` | `/ip dns print` | Read-Only | SAFE |
| `get_dhcp_client` | `/ip dhcp-client print` | Read-Only | SAFE |
| `get_dhcp_server` | `/ip dhcp-server print` | Read-Only | SAFE |
| `get_nat` | `/ip firewall nat print` | Read-Only | SAFE |
| `get_neighbors` | `/ip neighbor print` | Read-Only | SAFE |
| `get_arp` | `/ip arp print` | Read-Only | SAFE |

### Security Assessment:
- **Zero Write Capability:** There is no execution pathway in `execute_mikrotik_tool` that accepts arbitrary command strings. If an unmapped tool name is supplied (e.g., `reboot`), it returns an explicit error: `Tool MikroTik '<name>' tidak tersedia.`
- **Live Hardware Test:** Executed `execute_mikrotik_tool('get_resources', 'MikroTik-hAP-ac-lite')` against live hardware. Successfully returned CPU, RAM, and uptime with `success: True`.

---

## 3. NETWORK MCP SERVER AUDIT (32 TOOLS)

The Network MCP Server defined in [mcp_servers/network/server.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/mcp_servers/network/server.py) exports 32 tools to external and internal MCP clients:

| Category | Tool Identifier | Functional Purpose | Safety Guard / Restrictions |
| :--- | :--- | :--- | :--- |
| **Session** | `device_connect` | Open persistent SSH session to device | Validated hostname/IP; SecretVault creds |
| **Session** | `device_disconnect` | Terminate active SSH session | Non-mutating session cleanup |
| **Execution** | `mikrotik_execute_command` | Execute arbitrary CLI command | Sanitized via `validate_command_safety` |
| **Execution** | `mikrotik_apply_config` | Batch apply configuration | Requires `approved=True` parameter |
| **Config Plan** | `mikrotik_plan_config_change`| Generate structured change plan | Non-mutating dry-run |
| **Syntax** | `mikrotik_validate_script` | Verify command syntax and safety | Pure AST / regex validation |
| **Audit** | `mikrotik_audit_firewall` | Audit firewall filters & NAT | Read-only inspection |
| **Audit** | `mikrotik_audit_vlan` | Audit bridge VLAN filtering & PVIDs | Read-only inspection |
| **Audit** | `mikrotik_diagnose_route` | Run LPM routing analysis | Control-plane RIB analysis |
| **Audit** | `mikrotik_generate_report` | Multi-point router health audit | Read-only aggregate inspection |
| **Telemetry** | `mikrotik_get_arp` | Retrieve ARP cache entries | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_dhcp_client`| Get DHCP client leases and status | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_dhcp_server`| Get DHCP server leases and pools | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_dns` | Query DNS server and static cache | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_firewall` | Inspect firewall filter rules | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_identity` | Query system identity name | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_interfaces`| Inspect interface operational status| Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_ip_addresses`| Inspect IP address assignments | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_nat` | Inspect NAT table entries | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_neighbors` | Retrieve CDP/MNDP neighbors | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_resources` | Retrieve CPU, RAM, and uptime | Read-only CLI parsing |
| **Telemetry** | `mikrotik_get_routes` | Retrieve routing table (/ip route) | Read-only CLI parsing |
| **Simulation** | `network_analyze_change_impact`| Simulate node/link failure blast radius| In-memory graph clone simulation |
| **Topology** | `network_find_path` | Trace topological path between nodes | Graph traversal over topology.db |
| **Topology** | `network_get_topology` | Get complete network topology graph| Read-only graph query |
| **Topology** | `network_troubleshoot_node`| Perform RCA on degraded node | Epistemic rule evaluation |
| **Inventory** | `network_list_devices` | List registered network devices | Read-only inventory store query |
| **Diagnostics**| `network_nslookup` | Perform DNS resolution from host | Target string validated |
| **Diagnostics**| `network_ping` | ICMP reachability probe | Bounded count and timeout |
| **Diagnostics**| `network_traceroute` | Hop-by-hop route trace | Bounded hop count and timeout |
| **SNMP** | `snmp_get_interface_traffic`| Query interface octet counters | Read-only SNMP GET |
| **SNMP** | `snmp_get_system_info` | Query system OIDs and CPU/RAM | Read-only SNMP GET |

---

## 4. CRITICAL FINDINGS IN TOOL REGISTRIES

### 4.1 Residual Legacy Branding in MCP Tool Docstrings (BUG-NET-05)
A forensic text search of [mcp_servers/network/server.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/mcp_servers/network/server.py) revealed residual legacy strings ("AIRA") inside user/LLM-visible tool descriptions:
- Tool `network_list_devices`: `"List all configured network devices in the AIRA inventory."`
- Tool `network_nslookup`: `"Perform DNS forward/reverse resolution from the AIRA host."`
- Tool `network_ping`: `"Ping an IPv4/IPv6 address or domain from the AIRA host."`

*Recommendation:* Update docstrings to reference "VERA" during the scheduled backlog cycle.

### 4.2 Parameter Safety Validation Guard
In [mcp_servers/network/security.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/mcp_servers/network/security.py), input targets are validated via:
```python
_VALID_TARGET_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$|"
    r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$|"
    r"^[a-zA-Z0-9._-]+$"
)
```
Forbidden characters (`;&|`$<>` etc.) are rejected immediately before transport execution, preventing command injection vulnerabilities into the SSH or shell sub-processes.
