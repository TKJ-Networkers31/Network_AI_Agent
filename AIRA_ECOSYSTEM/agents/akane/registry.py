"""
agents/akane/registry.py — pintu masuk resmi ke AKANE.

AKANE (Adaptive Knowledge & Autonomous Network Engine) menangani SSH, SNMP,
MikroTik, Cisco, Linux, network automation, configuration, monitoring.
AKANE TIDAK BERBICARA LANGSUNG KE USER - satu-satunya cara memanggilnya
adalah lewat AKANE_TOOLS di bawah, yang dikonsumsi oleh
core/orchestrator.py::AGENT_TOOL_MAP.

FIX (Phase 0 Stabilization):
Deskripsi 'traceroute' dan 'get_routes' sebelumnya terlalu mirip (sama-sama
menyinggung kata "route"), sehingga LLM planner pernah salah memilih
get_routes(device_name='R1') untuk permintaan "tracert ke facebook.com" -
padahal traceroute ke host eksternal TIDAK ADA HUBUNGANNYA dengan routing
table internal sebuah device MikroTik. Deskripsi kedua tool ini sekarang
dipertegas saling silang supaya LLM tidak tertukar lagi.
"""

from agents.akane import network_tools as nt

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

AKANE_DANGEROUS_TOOLS: set[str] = set()

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

AKANE_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "ping",
        "description": "Melakukan ping ICMP dari komputer agent ke target jaringan (hostname atau IP), termasuk host publik seperti google.com, facebook.com, 8.8.8.8, dsb.",
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
        "description": (
            "Melakukan traceroute/tracert (jejak rute paket hop-by-hop) dari komputer agent "
            "menuju TARGET APA SAJA di internet atau LAN - boleh hostname publik "
            "(google.com, facebook.com, youtube.com, dsb) MAUPUN IP address. "
            "WAJIB pakai tool ini untuk setiap permintaan yang menyebut kata "
            "'traceroute', 'tracert', atau 'trace ke <host>'. "
            "JANGAN PERNAH memakai 'get_routes' untuk permintaan semacam ini - "
            "get_routes itu HAL YANG BERBEDA TOTAL: cuma untuk melihat routing "
            "table INTERNAL satu perangkat MikroTik yang sudah terdaftar di "
            "inventory (butuh device_name, misal 'R1'), bukan untuk trace ke "
            "host eksternal. "
            "CATATAN PENTING: traceroute ke internet bisa butuh waktu (sampai "
            "~45 detik) dan KADANG GAGAL karena ICMP diblokir firewall/ISP di "
            "tengah jalan - ini normal, BUKAN bug. Kalau traceroute gagal "
            "sekali untuk satu target, JANGAN mengulang panggilan traceroute "
            "ke target yang sama atau ke IP hasil resolusinya - cukup "
            "laporkan apa adanya ke user (sertakan output parsial kalau ada), "
            "dan tawarkan 'ping' sebagai cek konektivitas dasar sebagai "
            "gantinya."
        ),
        "parameters": {"type": "object", "properties": {"target": {"type": "string", "description": "Hostname publik atau IP tujuan trace, contoh: 'facebook.com', '8.8.8.8'."}}, "required": ["target"]},
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
        "description": (
            "Mengambil ROUTING TABLE INTERNAL dari SATU perangkat MikroTik "
            "yang sudah terdaftar di inventory (WAJIB isi device_name, mis. "
            "'R1' - kalau tidak tahu device apa saja yang ada, panggil "
            "'list_devices' dulu). Tool ini TIDAK ADA HUBUNGANNYA dengan "
            "traceroute/tracert ke host eksternal seperti google.com atau "
            "facebook.com - untuk kebutuhan itu WAJIB pakai tool 'traceroute', "
            "BUKAN tool ini."
        ),
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