"""
mcp_servers/network/server.py — Dedicated Network Automation & Diagnostics MCP Server.

Implements official Model Context Protocol (MCP 2.x) tool interfaces for:
- Group A: Read-only Diagnostics (ICMP, DNS, Trace, RouterOS prints, SNMP stats, Inventory)
- Group B: Configuration Preparation & Validation (Script validation, diff, change planning)
- Group C: State-Changing Operations (Approved configuration application, connection management)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from mcp_servers.network.security import validate_network_target, mask_sensitive_data
from tools.network.diagnostics import ping as _diag_ping, nslookup as _diag_nslookup, traceroute as _diag_traceroute
from tools.inventory import list_devices as _inv_list_devices
from tools.mikrotik.routeros import COMMANDS as MIKROTIK_COMMANDS
from tools.snmp.monitor import (
    get_system_info as _snmp_system_info,
    get_interface_traffic as _snmp_interface_traffic,
)
from agents.akane.connection_manager import get_connection_manager

logger = logging.getLogger("aira.mcp.network")

# Disallowed dangerous substrings in proposed configuration commands
DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"/system\s+reset-configuration", re.IGNORECASE),
    re.compile(r"/system\s+reboot", re.IGNORECASE),
    re.compile(r"/file\s+remove", re.IGNORECASE),
    re.compile(r"/user\s+remove", re.IGNORECASE),
]


def _normalize_routeros_command(cmd: str) -> str:
    """Menormalisasi perbedaan sintaks umum RouterOS v6/v7 agar eksekusi write selalu sukses."""
    trimmed = cmd.strip()
    lower = trimmed.lower()
    # RouterOS v6 menambahkan dhcp-client dalam keadaan disabled=yes secara default kecuali disabled=no disertakan
    if lower.startswith("/ip dhcp-client add") and "disabled=" not in lower:
        trimmed += " disabled=no"
    # Jika LLM menggunakan passphrase= pada wireless security-profiles (sintaks v7/umum), konversi ke v6
    if "/interface wireless security-profiles" in lower and "passphrase=" in lower:
        import re as _re
        m = _re.search(r'passphrase=(?:"([^"]+)"|(\S+))', trimmed, _re.IGNORECASE)
        if m:
            pw = m.group(1) if m.group(1) is not None else m.group(2)
            trimmed = _re.sub(
                r'passphrase=(?:"[^"]+"|\S+)',
                f'mode=dynamic-keys authentication-types=wpa-psk,wpa2-psk wpa-pre-shared-key="{pw}" wpa2-pre-shared-key="{pw}"',
                trimmed,
                flags=_re.IGNORECASE,
            )
    return trimmed


def _exec_mikrotik_print(tool_key: str, device_name: str) -> dict:
    cmd = MIKROTIK_COMMANDS.get(tool_key)
    if not cmd:
        return {"success": False, "error": f"Tool '{tool_key}' not recognized."}

    manager = get_connection_manager()
    raw = manager.execute_for_device(device_name, cmd)
    return mask_sensitive_data({
        **raw,
        "tool": tool_key,
        "device": device_name,
        "category": "mikrotik",
    })


def create_network_mcp_server() -> MCPServer:
    """Builds and returns configured MCPServer instance for network automation."""
    server = MCPServer("aira-network-server", version="1.0.0")

    # ------------------------------------------------------------------
    # Group A: Read-Only Diagnostics (Local host & Device inspection)
    # ------------------------------------------------------------------

    @server.tool(name="network_ping", description="Ping an IPv4/IPv6 address or domain from the AIRA host.")
    def network_ping(target: str, count: int = 4) -> dict:
        try:
            valid_target = validate_network_target(target)
            return _diag_ping(valid_target, count=max(1, min(count, 10)))
        except Exception as exc:
            return {"success": False, "tool": "network_ping", "error": str(exc)}

    @server.tool(name="network_nslookup", description="Perform DNS forward/reverse resolution from the AIRA host.")
    def network_nslookup(target: str) -> dict:
        try:
            valid_target = validate_network_target(target)
            return _diag_nslookup(valid_target)
        except Exception as exc:
            return {"success": False, "tool": "network_nslookup", "error": str(exc)}

    @server.tool(name="network_traceroute", description="Trace the hop-by-hop route towards a target IP or domain.")
    def network_traceroute(target: str) -> dict:
        try:
            valid_target = validate_network_target(target)
            return _diag_traceroute(valid_target)
        except Exception as exc:
            return {"success": False, "tool": "network_traceroute", "error": str(exc)}

    @server.tool(name="network_list_devices", description="List all configured network devices in the AIRA inventory.")
    def network_list_devices(include_disabled: bool = False) -> dict:
        raw = _inv_list_devices(include_disabled=include_disabled)
        return mask_sensitive_data(raw)

    @server.tool(name="mikrotik_get_identity", description="Get MikroTik system identity hostname.")
    def mikrotik_get_identity(device_name: str) -> dict:
        return _exec_mikrotik_print("get_identity", device_name)

    @server.tool(name="mikrotik_get_resources", description="Get MikroTik CPU, RAM, uptime, and RouterOS version.")
    def mikrotik_get_resources(device_name: str) -> dict:
        return _exec_mikrotik_print("get_resources", device_name)

    @server.tool(name="mikrotik_get_interfaces", description="Get MikroTik network interface list and link status.")
    def mikrotik_get_interfaces(device_name: str) -> dict:
        return _exec_mikrotik_print("get_interfaces", device_name)

    @server.tool(name="mikrotik_get_ip_addresses", description="Get MikroTik IP address assignments.")
    def mikrotik_get_ip_addresses(device_name: str) -> dict:
        return _exec_mikrotik_print("get_ip_addresses", device_name)

    @server.tool(name="mikrotik_get_routes", description="Get MikroTik routing table (/ip route print).")
    def mikrotik_get_routes(device_name: str) -> dict:
        return _exec_mikrotik_print("get_routes", device_name)

    @server.tool(name="mikrotik_get_firewall", description="Get MikroTik firewall filter rules.")
    def mikrotik_get_firewall(device_name: str) -> dict:
        return _exec_mikrotik_print("get_firewall", device_name)

    @server.tool(name="mikrotik_get_dns", description="Get MikroTik DNS cache and server settings.")
    def mikrotik_get_dns(device_name: str) -> dict:
        return _exec_mikrotik_print("get_dns", device_name)

    @server.tool(name="mikrotik_get_dhcp_client", description="Get MikroTik DHCP client leases and status.")
    def mikrotik_get_dhcp_client(device_name: str) -> dict:
        return _exec_mikrotik_print("get_dhcp_client", device_name)

    @server.tool(name="mikrotik_get_dhcp_server", description="Get MikroTik DHCP server configurations.")
    def mikrotik_get_dhcp_server(device_name: str) -> dict:
        return _exec_mikrotik_print("get_dhcp_server", device_name)

    @server.tool(name="mikrotik_get_nat", description="Get MikroTik firewall NAT rules.")
    def mikrotik_get_nat(device_name: str) -> dict:
        return _exec_mikrotik_print("get_nat", device_name)

    @server.tool(name="mikrotik_get_neighbors", description="Get MikroTik CDP/MNDP neighbor discovery table.")
    def mikrotik_get_neighbors(device_name: str) -> dict:
        return _exec_mikrotik_print("get_neighbors", device_name)

    @server.tool(name="mikrotik_get_arp", description="Get MikroTik ARP table cache.")
    def mikrotik_get_arp(device_name: str) -> dict:
        return _exec_mikrotik_print("get_arp", device_name)

    @server.tool(name="snmp_get_system_info", description="Query device system info and CPU/RAM via SNMP.")
    def snmp_get_system_info(device_name: str) -> dict:
        return mask_sensitive_data(_snmp_system_info(device_name))

    @server.tool(name="snmp_get_interface_traffic", description="Query network interface octet counters via SNMP.")
    def snmp_get_interface_traffic(device_name: str) -> dict:
        return mask_sensitive_data(_snmp_interface_traffic(device_name))

    @server.tool(name="mikrotik_diagnose_route", description="Perform Longest Prefix Match (LPM) and route analysis for destination IP on router.")
    def mikrotik_diagnose_route(device_name: str, target_ip: str) -> dict:
        from agents.akane.reasoning_engine import parse_routeros_routes, evaluate_longest_prefix_match
        manager = get_connection_manager()
        routes_raw = manager.get_routes(device_name)
        if not routes_raw.get("success"):
            return mask_sensitive_data({"success": False, "error": routes_raw.get("error")})
        routes = parse_routeros_routes(routes_raw.get("raw_output", ""))
        lpm_result = evaluate_longest_prefix_match(routes, target_ip)
        return mask_sensitive_data({
            "success": True,
            "device_name": device_name,
            "target_ip": target_ip,
            "total_routes": len(routes),
            **lpm_result,
        })

    @server.tool(name="mikrotik_audit_firewall", description="Audit firewall filter rules, FastTrack placement, and NAT masquerade status.")
    def mikrotik_audit_firewall(device_name: str) -> dict:
        from agents.akane.reasoning_engine import parse_routeros_firewall, analyze_firewall_rules
        manager = get_connection_manager()
        fw_raw = manager.get_firewall_rules(device_name)
        nat_raw = manager.get_nat_rules(device_name)
        if not fw_raw.get("success"):
            return mask_sensitive_data({"success": False, "error": fw_raw.get("error")})
        rules = parse_routeros_firewall(fw_raw.get("raw_output", ""))
        audit = analyze_firewall_rules(rules, nat_raw=nat_raw.get("raw_output", ""))
        return mask_sensitive_data({
            "success": True,
            "device_name": device_name,
            **audit,
        })

    @server.tool(name="mikrotik_audit_vlan", description="Audit bridge VLAN filtering, PVID assignments, and VLAN isolation.")
    def mikrotik_audit_vlan(device_name: str) -> dict:
        from agents.akane.reasoning_engine import analyze_vlan_configuration
        manager = get_connection_manager()
        bridge_res = manager.execute_for_device(device_name, "/interface bridge print")
        vlan_res = manager.execute_for_device(device_name, "/interface bridge vlan print")
        port_res = manager.execute_for_device(device_name, "/interface bridge port print")
        audit = analyze_vlan_configuration(
            bridge_print_raw=bridge_res.get("output", ""),
            vlan_print_raw=vlan_res.get("output", ""),
            ports_print_raw=port_res.get("output", ""),
        )
        return mask_sensitive_data({
            "success": True,
            "device_name": device_name,
            **audit,
        })

    # ------------------------------------------------------------------
    # Group B: Configuration Preparation & Validation
    # ------------------------------------------------------------------

    @server.tool(name="mikrotik_validate_script", description="Validate syntax and safety of proposed RouterOS commands.")
    def mikrotik_validate_script(script_text: str) -> dict:
        lines = [line.strip() for line in (script_text or "").splitlines() if line.strip() and not line.strip().startswith("#")]
        if not lines:
            return {"valid": False, "error": "Script contains no executable commands."}

        issues = []
        for idx, line in enumerate(lines, 1):
            for pat in DANGEROUS_COMMAND_PATTERNS:
                if pat.search(line):
                    issues.append(f"Line {idx}: Potentially destructive command detected ('{line}')")

            # Check quotes balance
            if line.count('"') % 2 != 0:
                issues.append(f"Line {idx}: Unbalanced double quotes in command: '{line}'")

        return {
            "valid": len(issues) == 0,
            "command_count": len(lines),
            "commands": lines,
            "issues": issues,
            "safety": "safe" if len(issues) == 0 else "flagged",
        }

    @server.tool(name="mikrotik_plan_config_change", description="Generate a structured change plan before applying configuration.")
    def mikrotik_plan_config_change(device_name: str, commands: list[str]) -> dict:
        from agents.akane.config_engine import get_config_engine
        cfg_engine = get_config_engine()
        plan = cfg_engine.plan_change(device_name, commands)
        if not plan.get("success"):
            return {
                "success": False,
                "error": "Plan rejected: " + "; ".join(plan.get("flagged_issues", [])),
                "plan": plan,
            }
        preview = cfg_engine.preview_change(device_name, {"change_plan": plan})
        return mask_sensitive_data({
            "success": True,
            "device": device_name,
            "commands": plan.get("proposed_commands", []),
            "rollback_plan": plan.get("rollback_plan", []),
            "diff_preview": preview.get("diff_preview", ""),
            "change_summary": f"Plan to execute {plan.get('commands_count', 0)} commands on {device_name}.",
            "requires_approval": True,
        })

    # ------------------------------------------------------------------
    # Group C: State-Changing Operations (Explicit Approval Required)
    # ------------------------------------------------------------------

    @server.tool(name="mikrotik_apply_config", description="Apply approved RouterOS commands to a target device (requires approval).")
    def mikrotik_apply_config(device_name: str = "", commands: list[str] = None, approved: bool = False) -> dict:
        commands = commands or []
        from agents.akane.config_engine import get_config_engine
        cfg_engine = get_config_engine()

        if not approved:
            plan = cfg_engine.plan_change(device_name, commands)
            preview = cfg_engine.preview_change(device_name, {"change_plan": plan})
            return {
                "success": False,
                "requires_approval": True,
                "confirmation_required": True,
                "device": device_name,
                "commands": commands,
                "risk_level": plan.get("risk_level", "STANDARD"),
                "risk_flags": plan.get("risk_flags", []),
                "diff_preview": preview.get("diff_preview", ""),
                "rollback_plan": plan.get("rollback_plan", []),
                "message": f"Execution of state-changing commands on '{device_name}' requires explicit user approval. Call with approved=True after user confirmation.",
            }

        apply_res = cfg_engine.apply_change(device_name=device_name, commands=commands, approved=True)
        if not apply_res.get("success"):
            return mask_sensitive_data(apply_res)

        verify_res = cfg_engine.verify_change(device_name=device_name, applied_commands=commands)
        overall_status = "VERIFIED_SUCCESS" if verify_res.get("success") else "RECOVERY_REQUIRED"

        try:
            from core.topology_engine import get_topology_engine
            get_topology_engine().sync_from_router_async(device_name=device_name or None)
        except Exception:
            pass

        return mask_sensitive_data({
            "success": verify_res.get("success", False),
            "status": overall_status,
            "operation_id": apply_res.get("operation_id"),
            "device": device_name or "default",
            "applied_count": apply_res.get("applied_count", len(commands)),
            "details": apply_res.get("details", []),
            "verification": verify_res,
            "recovery_needed": not verify_res.get("success", False),
        })

    @server.tool(
        name="device_connect",
        description="Open a persistent SSH session to a device in inventory or ad-hoc via IP/hostname and credentials from chat.",
    )
    def device_connect(
        device_name: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
    ) -> dict:
        manager = get_connection_manager()
        dev = device_name or host
        if dev and ("." not in dev and ":" not in dev):
            target = manager._resolve_target(dev)
            if target.get("success"):
                res = manager.open_connection_for_device(dev)
                if res.get("success"):
                    try:
                        from core.topology_engine import get_topology_engine
                        get_topology_engine().sync_from_router_async(device_name=target.get("name"), host=target.get("host"))
                    except Exception:
                        pass
                return mask_sensitive_data({**res, "device": dev, "tool": "device_connect"})

        target_host = host or device_name
        if not target_host:
            return {"success": False, "tool": "device_connect", "error": "Target device_name or host must be specified."}

        res = manager.open_connection(
            host=target_host,
            username=username or "admin",
            password=password,
            key_data=key_data,
            port=port,
            device_name=device_name if device_name and device_name != target_host else None,
        )
        if res.get("success"):
            try:
                from core.topology_engine import get_topology_engine
                get_topology_engine().sync_from_router_async(device_name=device_name, host=target_host)
            except Exception:
                pass
        return mask_sensitive_data({**res, "device": device_name or target_host, "tool": "device_connect"})

    @server.tool(
        name="mikrotik_execute_command",
        description="Execute arbitrary read, write, or diagnostic CLI command on a MikroTik router and return raw output for AI analysis.",
    )
    def mikrotik_execute_command(
        command: str,
        device_name: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
        timeout: float = 25.0,
    ) -> dict:
        trimmed = (command or "").strip()
        if not trimmed:
            return {"success": False, "error": "Command string cannot be empty."}

        # Check dangerous system wipes
        for pat in DANGEROUS_COMMAND_PATTERNS:
            if pat.search(trimmed):
                return {
                    "success": False,
                    "error": f"Command rejected: dangerous operation detected ('{trimmed}').",
                    "flagged": True,
                }

        manager = get_connection_manager()
        lines = [ _normalize_routeros_command(l) for l in trimmed.splitlines() if l.strip() and not l.strip().startswith("#") ]

        if len(lines) <= 1:
            single_cmd = lines[0] if lines else trimmed
            raw = manager.execute_command(
                command=single_cmd,
                device_name=device_name,
                host=host,
                username=username,
                password=password,
                key_data=key_data,
                port=port,
                timeout=timeout,
            )
            if raw.get("success") and any(w in single_cmd.lower() for w in (" add", " set", " remove", " enable", " disable")):
                try:
                    from core.topology_engine import get_topology_engine
                    get_topology_engine().sync_from_router_async(device_name=device_name, host=host)
                except Exception:
                    pass
            return mask_sensitive_data({**raw, "tool": "mikrotik_execute_command"})

        # Multi-line batch execution
        combined_outputs = []
        last_res = {}
        for line_cmd in lines:
            last_res = manager.execute_command(
                command=line_cmd,
                device_name=device_name,
                host=host,
                username=username,
                password=password,
                key_data=key_data,
                port=port,
                timeout=timeout,
            )
            out_str = last_res.get("output", "")
            combined_outputs.append(f"$ {line_cmd}\n{out_str}".strip())
            if not last_res.get("success"):
                return mask_sensitive_data({
                    **last_res,
                    "output": "\n".join(combined_outputs),
                    "tool": "mikrotik_execute_command",
                })

        try:
            from core.topology_engine import get_topology_engine
            get_topology_engine().sync_from_router_async(device_name=device_name, host=host)
        except Exception:
            pass

        return mask_sensitive_data({
            "success": True,
            "command": trimmed,
            "output": "\n".join(combined_outputs),
            "tool": "mikrotik_execute_command",
        })

    @server.tool(
        name="mikrotik_generate_report",
        description="Audit MikroTik router health, interfaces, IP addresses, routing, firewall security, and logs into a structured diagnostic report.",
    )
    def mikrotik_generate_report(
        device_name: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
    ) -> dict:
        manager = get_connection_manager()
        target_label = device_name or host or "MikroTik"

        report_commands = {
            "identity": "/system identity print",
            "resources": "/system resource print",
            "interfaces": "/interface print brief",
            "ip_addresses": "/ip address print detail",
            "routes": "/ip route print",
            "firewall_filter": "/ip firewall filter print count-only",
            "nat_rules": "/ip firewall nat print",
            "recent_logs": '/log print where topics~"error|warning|critical"',
        }

        collected = {}
        errors = []

        for section, cmd in report_commands.items():
            res = manager.execute_command(
                command=cmd,
                device_name=device_name,
                host=host,
                username=username,
                password=password,
                key_data=key_data,
                port=port,
                timeout=15.0,
            )
            if res.get("success"):
                collected[section] = res.get("output", "").strip()
            else:
                err_msg = res.get("error") or "Unknown error"
                errors.append(f"{section}: {err_msg}")
                collected[section] = f"[Error: {err_msg}]"

        # Health heuristic analysis
        issues = []
        res_text = collected.get("resources", "")
        if "cpu-load: 100%" in res_text or "cpu-load: 9" in res_text:
            issues.append("High CPU load detected on router.")
        if "free-memory: 0" in res_text or "free-memory: [1-9]MiB" in res_text:
            issues.append("Low free memory detected.")

        log_text = collected.get("recent_logs", "")
        if log_text and "error" in log_text.lower():
            issues.append("Active error/warning entries found in RouterOS logs.")

        status = "CRITICAL" if len(issues) >= 2 else ("WARNING" if issues else "HEALTHY")

        return mask_sensitive_data({
            "success": True,
            "tool": "mikrotik_generate_report",
            "target": target_label,
            "overall_status": status,
            "detected_issues": issues,
            "section_errors": errors,
            "data": collected,
            "summary": f"Audit complete for {target_label}. Overall Status: {status} with {len(issues)} issue(s) flagged.",
        })

    @server.tool(name="device_disconnect", description="Close an active persistent SSH session to a device.")
    def device_disconnect(device_name: str) -> dict:
        manager = get_connection_manager()
        for s in manager.list_sessions():
            if str(s.get("device_name") or "").lower() == device_name.strip().lower():
                res = manager.close_connection(s["session_id"], reason="manual")
                return {**res, "tool": "device_disconnect", "device": device_name}
        return {"success": False, "tool": "device_disconnect", "error": f"No active session found for '{device_name}'."}


    # ------------------------------------------------------------------
    # Group D: Autonomous Topology & The Dude Troubleshooting
    # ------------------------------------------------------------------

    @server.tool(name="network_get_topology", description="Get full corporate network topology graph and device statuses (The Dude Native).")
    def network_get_topology() -> dict:
        from core.topology_engine import get_topology_engine
        engine = get_topology_engine()
        return mask_sensitive_data(engine.get_topology())

    @server.tool(name="network_troubleshoot_node", description="Perform Root Cause Analysis (RCA) and path tracing for a degraded/offline device.")
    def network_troubleshoot_node(node_id: str) -> dict:
        from core.topology_engine import get_topology_engine
        engine = get_topology_engine()
        return mask_sensitive_data(engine.troubleshoot_node(node_id))

    @server.tool(name="network_find_path", description="Trace topological and logical path between two network nodes with L2/L3 separation and bottleneck analysis.")
    def network_find_path(source: str, target: str, layer: Optional[str] = None) -> dict:
        from core.topology_engine import get_topology_engine
        engine = get_topology_engine()
        return mask_sensitive_data(engine.find_path(source=source, target=target, layer=layer))

    @server.tool(name="network_analyze_change_impact", description="Simulate failure or maintenance of a node/link, assessing blast radius, isolated devices, and rerouting.")
    def network_analyze_change_impact(target_node_id: str, change_type: str = "node_offline", affected_interface: Optional[str] = None) -> dict:
        from core.topology_engine import get_topology_engine
        engine = get_topology_engine()
        return mask_sensitive_data(engine.analyze_change_impact(target_node_id=target_node_id, change_type=change_type, affected_interface=affected_interface))

    return server



if __name__ == "__main__":
    import asyncio
    mcp_srv = create_network_mcp_server()
    asyncio.run(mcp_srv.run_stdio_async())
