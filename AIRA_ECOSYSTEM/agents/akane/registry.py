"""
agents/akane/registry.py — pintu masuk resmi ke AKANE.

AKANE (Adaptive Knowledge & Autonomous Network Engine) menangani SSH, SNMP,
MikroTik, Cisco, Linux, network automation, configuration, monitoring.
AKANE TIDAK BERBICARA LANGSUNG KE USER - satu-satunya cara memanggilnya
adalah lewat AKANE_TOOLS di bawah, yang dikonsumsi oleh
core/orchestrator.py::AGENT_TOOL_MAP.

Ini adalah port dari bagian network di tools/registry.py lama (TOOL_MAP,
TOOL_CATEGORY, execute_tool) - HANYA yang berkaitan dengan network/mikrotik/
snmp/ssh, tanpa web_search/memory/vision (itu domain agent lain).

Kenapa dipisah dari network_tools.py: registry.py = "apa saja yang AKANE
bisa lakukan + validasi nama tool", network_tools.py = implementasi nyata
tiap kemampuan (wrap tools/ssh, tools/snmp, tools/mikrotik, tools/network).
"""

from agents.akane import network_tools as nt

# TODO: lengkapi mapping ini 1:1 dari bagian "mikrotik"/"network"/"snmp" di
# tools/registry.py::TOOL_MAP lama.
AKANE_TOOLS: dict = {
    "ping": nt.ping,
    "nslookup": nt.nslookup,
    "traceroute": nt.traceroute,
    "list_devices": nt.list_devices,
    "get_interfaces": nt.get_interfaces,
    "get_ip_addresses": nt.get_ip_addresses,
    "get_routes": nt.get_routes,
    "get_firewall": nt.get_firewall,
    "get_resources": nt.get_resources,
    "get_identity": nt.get_identity,
    "get_dns": nt.get_dns,
    "get_dhcp_client": nt.get_dhcp_client,
    "get_dhcp_server": nt.get_dhcp_server,
    "get_nat": nt.get_nat,
    "get_neighbors": nt.get_neighbors,
    "get_arp": nt.get_arp,
    "snmp_get_system_info": nt.snmp_get_system_info,
    "snmp_get_interface_traffic": nt.snmp_get_interface_traffic,
}

# Tool yang butuh konfirmasi manual sebelum eksekusi (mis. nanti ada
# "set_interface_disable", dsb). Port dari tools/registry.py::DANGEROUS_TOOLS.
AKANE_DANGEROUS_TOOLS: set[str] = set()

# Kategori untuk keperluan UI/logging (port dari TOOL_CATEGORY, subset network).
AKANE_TOOL_CATEGORY: dict[str, str] = {
    "ping": "network",
    "nslookup": "network",
    "traceroute": "network",
    "list_devices": "inventory",
    "get_interfaces": "mikrotik",
    "get_ip_addresses": "mikrotik",
    "get_routes": "mikrotik",
    "get_firewall": "mikrotik",
    "get_resources": "mikrotik",
    "get_identity": "mikrotik",
    "get_dns": "mikrotik",
    "get_dhcp_client": "mikrotik",
    "get_dhcp_server": "mikrotik",
    "get_nat": "mikrotik",
    "get_neighbors": "mikrotik",
    "get_arp": "mikrotik",
    "snmp_get_system_info": "snmp",
    "snmp_get_interface_traffic": "snmp",
}
