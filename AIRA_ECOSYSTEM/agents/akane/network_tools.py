"""
agents/akane/network_tools.py — Implementasi kemampuan AKANE lewat Network MCP Server.

Semua operasi jaringan (diagnostik ICMP/DNS/Trace, print RouterOS, SNMP polling,
dan konfigurasi MikroTik) didelegasikan ke dedicated Network MCP Server
(mcp_servers/network/server.py) melalui MCP Client (core/mcp/client.py).

Keamanan:
- Target IP/Domain divalidasi oleh MCP server untuk mencegah command/flag injection.
- Secret (password/community) disamarkan otomatis sebelum sampai ke caller.
- Operasi pengubahan state (apply_config) mewajibkan persetujuan eksplisit.
"""

from typing import Optional

from core.mcp.client import get_network_mcp_client
from agents.akane.connection_manager import get_connection_manager


def ping(target: str, count: int = 4) -> dict:
    return get_network_mcp_client().call_tool("network_ping", {"target": target, "count": count})


def nslookup(target: str) -> dict:
    return get_network_mcp_client().call_tool("network_nslookup", {"target": target})


def traceroute(target: str) -> dict:
    return get_network_mcp_client().call_tool("network_traceroute", {"target": target})


def list_devices() -> dict:
    return get_network_mcp_client().call_tool("network_list_devices", {})


def _run_mikrotik_command(tool_name: str, device_name: str) -> dict:
    """Delegasikan print RouterOS ke MCP Server."""
    return get_network_mcp_client().call_tool(f"mikrotik_{tool_name}", {"device_name": device_name})


def get_interfaces(device_name: str) -> dict:
    return _run_mikrotik_command("get_interfaces", device_name)


def get_ip_addresses(device_name: str) -> dict:
    return _run_mikrotik_command("get_ip_addresses", device_name)


def get_routes(device_name: str) -> dict:
    return _run_mikrotik_command("get_routes", device_name)


def get_firewall(device_name: str) -> dict:
    return _run_mikrotik_command("get_firewall", device_name)


def get_resources(device_name: str) -> dict:
    return _run_mikrotik_command("get_resources", device_name)


def get_identity(device_name: str) -> dict:
    return _run_mikrotik_command("get_identity", device_name)


def get_dns(device_name: str) -> dict:
    return _run_mikrotik_command("get_dns", device_name)


def get_dhcp_client(device_name: str) -> dict:
    return _run_mikrotik_command("get_dhcp_client", device_name)


def get_dhcp_server(device_name: str) -> dict:
    return _run_mikrotik_command("get_dhcp_server", device_name)


def get_nat(device_name: str) -> dict:
    return _run_mikrotik_command("get_nat", device_name)


def get_neighbors(device_name: str) -> dict:
    return _run_mikrotik_command("get_neighbors", device_name)


def get_arp(device_name: str) -> dict:
    return _run_mikrotik_command("get_arp", device_name)


def snmp_get_system_info(device_name: str) -> dict:
    return get_network_mcp_client().call_tool("snmp_get_system_info", {"device_name": device_name})


def snmp_get_interface_traffic(device_name: str) -> dict:
    return get_network_mcp_client().call_tool("snmp_get_interface_traffic", {"device_name": device_name})


def connect_device(
    device_name: Optional[str] = None,
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    key_data: Optional[str] = None,
) -> dict:
    payload = {
        "device_name": device_name,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "key_data": key_data,
    }
    return get_network_mcp_client().call_tool("device_connect", {k: v for k, v in payload.items() if v is not None})


def execute_router_command(
    command: str,
    device_name: Optional[str] = None,
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    key_data: Optional[str] = None,
    timeout: float = 25.0,
) -> dict:
    """Mengeksekusi perintah CLI RouterOS apapun (read/write/exec) dan mengembalikan output untuk dianalisis."""
    payload = {
        "command": command,
        "device_name": device_name,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "key_data": key_data,
        "timeout": timeout,
    }
    return get_network_mcp_client().call_tool("mikrotik_execute_command", {k: v for k, v in payload.items() if v is not None})


def generate_router_report(
    device_name: Optional[str] = None,
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    key_data: Optional[str] = None,
) -> dict:
    """Mengaudit kesehatan, status interface, IP, routing, firewall, dan log router MikroTik ke dalam laporan terstruktur."""
    payload = {
        "device_name": device_name,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "key_data": key_data,
    }
    return get_network_mcp_client().call_tool("mikrotik_generate_report", {k: v for k, v in payload.items() if v is not None})


def disconnect_device(device_name: str) -> dict:
    return get_network_mcp_client().call_tool("device_disconnect", {"device_name": device_name})


def list_connections() -> dict:
    sessions = get_connection_manager().list_sessions()
    return {"success": True, "tool": "list_connections", "count": len(sessions), "connections": sessions}


def validate_script(script_text: str) -> dict:
    """Memeriksa sintaks dan keamanan skrip RouterOS sebelum eksekusi."""
    return get_network_mcp_client().call_tool("mikrotik_validate_script", {"script_text": script_text})


def plan_config_change(device_name: str, commands: list[str]) -> dict:
    """Menyusun rencana perubahan konfigurasi terstruktur sebelum diterapkan."""
    return get_network_mcp_client().call_tool("mikrotik_plan_config_change", {"device_name": device_name, "commands": commands})


def apply_config(device_name: str = "", commands: list[str] = None, approved: bool = False) -> dict:
    """Menerapkan daftar perintah konfigurasi RouterOS ke perangkat tujuan secara batch."""
    return get_network_mcp_client().call_tool("mikrotik_apply_config", {"device_name": device_name or "", "commands": commands or [], "approved": approved})


def get_network_topology() -> dict:
    """Mengambil peta topologi graf lengkap dan status kesehatan perangkat (The Dude Native)."""
    return get_network_mcp_client().call_tool("network_get_topology", {})


def troubleshoot_network_node(node_id: str) -> dict:
    """Menjalankan Root Cause Analysis (RCA) dan path tracing untuk node jaringan bermasalah."""
    return get_network_mcp_client().call_tool("network_troubleshoot_node", {"node_id": node_id})

def find_network_path(source: str, target: str, layer: Optional[str] = None) -> dict:
    """Menelusuri jalur topologi L2/L3 antara dua node jaringan beserta identifikasi bottleneck."""
    return get_network_mcp_client().call_tool("network_find_path", {"source": source, "target": target, "layer": layer})


def analyze_network_change_impact(target_node_id: str, change_type: str = "node_offline", affected_interface: Optional[str] = None) -> dict:
    """Menganalisis dampak gangguan/perubahan pada node/link terhadap isolasi jaringan dan rerouting."""
    return get_network_mcp_client().call_tool("network_analyze_change_impact", {
        "target_node_id": target_node_id,
        "change_type": change_type,
        "affected_interface": affected_interface,
    })

def diagnose_network_route(device_name: str, target_ip: str) -> dict:
    """Mengevaluasi routing table dan Longest Prefix Match (LPM) untuk IP tujuan tertentu."""
    return get_network_mcp_client().call_tool("mikrotik_diagnose_route", {"device_name": device_name, "target_ip": target_ip})


def audit_network_firewall(device_name: str) -> dict:
    """Mengaudit filter firewall, penempatan FastTrack, dan keberadaan NAT masquerade pada router."""
    return get_network_mcp_client().call_tool("mikrotik_audit_firewall", {"device_name": device_name})


def audit_network_vlan(device_name: str) -> dict:
    """Mengaudit konfigurasi bridge VLAN filtering dan penetapan PVID port."""
    return get_network_mcp_client().call_tool("mikrotik_audit_vlan", {"device_name": device_name})
