# Model Context Protocol (MCP) in AIRA OS

AIRA OS integrates network automation, diagnostics, and device management tools via the official **Model Context Protocol (MCP 2.x)** Python SDK.

## Architecture

```
                    ┌───────────────────────────┐
                    │      AIRA Brain / REI     │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │     core/mcp/client.py    │
                    │      (MCP Client Layer)   │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │ mcp_servers/network/      │
                    │      (Network MCP Server) │
                    ├───────────────────────────┤
                    │ Group A: Diagnostics      │
                    │ Group B: Config Prep      │
                    │ Group C: State Changes    │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │ Low-level Drivers         │
                    │ (SSH/APCE, SNMP, OS ICMP) │
                    └───────────────────────────┘
```

## Tool Inventory & Permissions

### Group A: Read-Only Diagnostics
These operations perform local or remote inspection without modifying device state:
- `network_ping`: ICMP echo check with anti-injection input validation.
- `network_nslookup`: Forward/reverse DNS resolution.
- `network_traceroute`: Hop-by-hop packet trace with timeout safeguards.
- `network_list_devices`: Reads configured inventory devices with secrets masked.
- `mikrotik_get_identity`: RouterOS system identity.
- `mikrotik_get_resources`: CPU, RAM, uptime, and RouterOS version.
- `mikrotik_get_interfaces`: Interface status and link states.
- `mikrotik_get_ip_addresses`: IP address assignments.
- `mikrotik_get_routes`: IP routing table (`/ip route print`).
- `mikrotik_get_firewall`: Firewall filter rules.
- `mikrotik_get_dns`: DNS settings and cache.
- `mikrotik_get_dhcp_client`: DHCP client leases.
- `mikrotik_get_dhcp_server`: DHCP server configurations.
- `mikrotik_get_nat`: NAT rules.
- `mikrotik_get_neighbors`: MNDP/CDP neighbor discovery.
- `mikrotik_get_arp`: ARP table cache.
- `snmp_get_system_info`: SNMP v2c CPU, RAM, and system description.
- `snmp_get_interface_traffic`: SNMP interface traffic octet counters.

### Group B: Configuration Preparation & Validation
Safe preflight and dry-run preparation tools:
- `mikrotik_validate_script`: Syntactic verification and heuristic detection of potentially destructive commands (e.g. `/system reset-configuration`).
- `mikrotik_plan_config_change`: Validates device presence, parses commands, and generates a structured change plan.

### Group C: State-Changing Operations (Approval Required)
High-impact operations that require explicit user approval (`approved=True`):
- `mikrotik_apply_config`: Executes validated commands via persistent shell; blocked by default unless explicitly confirmed.
- `device_connect`: Establishes persistent SSH channel.
- `device_disconnect`: Terminates active SSH channel.

## Security Architecture

1. **Target Validation (`mcp_servers/network/security.py`):**
   Validates network targets against RFC 1123 domain and IP formats; rejects flag injection (`-` prefixes), control characters, and shell separators.
2. **Secret Masking:**
   Recursively sanitizes passwords, private keys, API tokens, and SNMP community strings from all tool return payloads before delivering to LLM context.
3. **Approval Gating:**
   All Group C operations are registered in `DANGEROUS_TOOLS` and require explicit user approval.

## Running Tests

Run the dedicated MCP test suite:
```powershell
d:\data\agent_ai\.venv\Scripts\python.exe -m pytest AIRA_ECOSYSTEM/tests/test_mcp_integration.py -v
```
