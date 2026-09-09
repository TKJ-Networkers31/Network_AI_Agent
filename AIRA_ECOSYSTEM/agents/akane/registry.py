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

# Skema function-calling (format tools=[...]) untuk semua tool AKANE,
# port dari agent/core/engine.py::build_tools() bagian network/mikrotik/snmp.
AKANE_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "ping",
        "description": "Melakukan ping ICMP dari komputer agent ke target jaringan (hostname atau IP).",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "description": "Hostname atau IP address tujuan."},
            "count": {"type": "integer", "description": "Jumlah paket ping.", "default": 4},
        }, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "nslookup",
        "description": "Melakukan DNS lookup terhadap hostname atau domain.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "traceroute",
        "description": "Melakukan traceroute menuju target.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "list_devices",
        "description": "Menampilkan semua perangkat jaringan yang terdaftar di inventory.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_interfaces",
        "description": "Mengambil interface dan status interface dari MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_ip_addresses",
        "description": "Mengambil IP address MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_routes",
        "description": "Mengambil routing table MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_resources",
        "description": "Mengambil resource (CPU, memory, uptime) MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_identity",
        "description": "Mengambil identity/nama sistem MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_firewall",
        "description": "Mengambil firewall filter rules MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_nat",
        "description": "Mengambil aturan NAT MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_dns",
        "description": "Mengambil konfigurasi DNS MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_dhcp_client",
        "description": "Mengambil konfigurasi DHCP client MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_dhcp_server",
        "description": "Mengambil konfigurasi DHCP server MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_neighbors",
        "description": "Mengambil hasil neighbor discovery (MNDP/CDP) MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_arp",
        "description": "Mengambil ARP table MikroTik.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "snmp_get_system_info",
        "description": "Mengambil info sistem via SNMP: CPU load, memory usage, uptime, nama sistem.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
    {"type": "function", "function": {
        "name": "snmp_get_interface_traffic",
        "description": "Mengambil traffic tiap interface via SNMP: status up/down, bytes in/out.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]},
    }},
]
