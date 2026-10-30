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
    "connect_device": nt.connect_device,
    "disconnect_device": nt.disconnect_device,
    "execute_router_command": nt.execute_router_command,
    "generate_router_report": nt.generate_router_report,
    "list_connections": nt.list_connections,
    "validate_script": nt.validate_script,
    "plan_config_change": nt.plan_config_change,
    "apply_config": nt.apply_config,
    "get_network_topology": nt.get_network_topology,
    "troubleshoot_network_node": nt.troubleshoot_network_node,
    "find_network_path": nt.find_network_path,
    "analyze_network_change_impact": nt.analyze_network_change_impact,
    "diagnose_network_route": nt.diagnose_network_route,
    "audit_network_firewall": nt.audit_network_firewall,
    "audit_network_vlan": nt.audit_network_vlan,
}

AKANE_DANGEROUS_TOOLS: set[str] = {"apply_config", "disconnect_device"}

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
    "connect_device": "mikrotik", 
    "disconnect_device": "mikrotik",
    "execute_router_command": "mikrotik",
    "generate_router_report": "mikrotik", 
    "list_connections": "mikrotik",
    "validate_script": "mikrotik",
    "plan_config_change": "mikrotik",
    "apply_config": "mikrotik",
    "get_network_topology": "network",
    "troubleshoot_network_node": "network",
    "find_network_path": "network",
    "analyze_network_change_impact": "network",
    "diagnose_network_route": "mikrotik",
    "audit_network_firewall": "mikrotik",
    "audit_network_vlan": "mikrotik",
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
    {"type": "function", "function": {
        "name": "connect_device",
        "description": "Membuka koneksi SSH persisten ke router MikroTik, baik menggunakan nama perangkat di inventory (mis. 'R1') maupun langsung menggunakan IP/host dan kredensial yang diberikan user di chat. Sesi dipertahankan aktif untuk perintah-perintah berikutnya.",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string", "description": "Nama perangkat di inventory atau hostname/IP target."},
            "host": {"type": "string", "description": "Alamat IP atau hostname router jika tidak tersimpan di inventory."},
            "username": {"type": "string", "description": "Username SSH (default: admin).", "default": "admin"},
            "password": {"type": "string", "description": "Password SSH (boleh kosong jika router tanpa password)."},
            "port": {"type": "integer", "description": "Port SSH router (default: 22).", "default": 22},
            "key_data": {"type": "string", "description": "Isi file SSH private key (PEM/OpenSSH format) jika login menggunakan public key authentication."},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "execute_router_command",
        "description": "Mengeksekusi perintah CLI RouterOS apapun (read/write/exec, konfigurasi, monitoring, script) ke router MikroTik secara persisten dan mengembalikan output teks utuh untuk dianalisis oleh AI. Dapat ditargetkan ke device_name inventory ATAU ke host/IP langsung dengan credential dari prompt.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Perintah CLI RouterOS lengkap yang ingin dieksekusi, misal '/ip address print', '/log print', '/tool traceroute 8.8.8.8 count=3'."},
            "device_name": {"type": "string", "description": "Nama perangkat di inventory (mis. 'R1') atau target."},
            "host": {"type": "string", "description": "Alamat IP/host router jika tidak ada di inventory."},
            "username": {"type": "string", "description": "Username SSH.", "default": "admin"},
            "password": {"type": "string", "description": "Password SSH router."},
            "port": {"type": "integer", "description": "Port SSH router.", "default": 22},
            "key_data": {"type": "string", "description": "SSH private key jika memakai autentikasi key."},
            "timeout": {"type": "number", "description": "Timeout eksekusi dalam detik.", "default": 25.0},
        }, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "generate_router_report",
        "description": "Mengaudit kondisi kesehatan lengkap router MikroTik (Resource CPU/RAM/Uptime, Interface link status, IP Address, Routing table, Firewall/NAT, serta log Error/Warning terbaru) dan menyusun laporan diagnostik yang terstruktur beserta penilaian status kesehatan (Healthy/Warning/Critical).",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string", "description": "Nama perangkat di inventory (mis. 'R1')."},
            "host": {"type": "string", "description": "Alamat IP/host router."},
            "username": {"type": "string", "description": "Username SSH.", "default": "admin"},
            "password": {"type": "string", "description": "Password SSH router."},
            "port": {"type": "integer", "description": "Port SSH router.", "default": 22},
            "key_data": {"type": "string", "description": "SSH private key jika memakai autentikasi key."},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "disconnect_device",
        "description": "Menutup koneksi SSH persisten ke satu perangkat.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"]}}},
    {"type": "function", "function": {
        "name": "list_connections",
        "description": "Melihat semua koneksi SSH yang sedang aktif (device, uptime, idle).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "validate_script",
        "description": "Memeriksa sintaks dan keamanan daftar perintah RouterOS sebelum direncanakan atau dieksekusi.",
        "parameters": {"type": "object", "properties": {"script_text": {"type": "string", "description": "Baris perintah RouterOS yang akan divalidasi."}}, "required": ["script_text"]}}},
    {"type": "function", "function": {
        "name": "plan_config_change",
        "description": "Menyusun change plan terstruktur untuk perangkat target (preflight check, validasi perintah, ringkasan dampak) sebelum diaplikasikan.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}, "commands": {"type": "array", "items": {"type": "string"}}}, "required": ["device_name", "commands"]}}},
    {"type": "function", "function": {
        "name": "apply_config",
        "description": "Menerapkan daftar perintah konfigurasi RouterOS (write/set/add/remove) secara batch dalam 1 panggilan tool ke perangkat MikroTik. Gunakan tool ini dengan approved=True saat user meminta mengkonfigurasi/memperbaiki router.",
        "parameters": {"type": "object", "properties": {"device_name": {"type": "string", "description": "Nama perangkat di inventory (mis. 'R1' atau 'ROUTER-1')."}, "commands": {"type": "array", "items": {"type": "string"}, "description": "Daftar berurutan perintah CLI RouterOS yang akan dieksekusi sekaligus."}, "approved": {"type": "boolean", "default": False}}, "required": ["commands"]}}},
    {"type": "function", "function": {
        "name": "get_network_topology",
        "description": "Mengambil seluruh data topologi jaringan perusahaan (The Dude Native): daftar router, switch, AP, server, serta link interkoneksi fisik dan status kesehatan live.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "troubleshoot_network_node",
        "description": "Melakukan Root Cause Analysis (RCA) dan path tracing untuk mendiagnosis mengapa suatu perangkat jaringan offline/lambat, mencari titik kegagalan di sepanjang jalur transmisi.",
        "parameters": {"type": "object", "properties": {
            "node_id": {"type": "string", "description": "ID node di topologi (misal 'node_ap_staff', 'node_sw_dist_2')."}
        }, "required": ["node_id"]}}},
    {"type": "function", "function": {
        "name": "find_network_path",
        "description": "Menelusuri jalur topologi L2/L3 antara dua node jaringan (source dan target), memetakan setiap hop, interface, bottleneck, dan estimasi latensi.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string", "description": "Nama, ID, atau IP perangkat awal."},
            "target": {"type": "string", "description": "Nama, ID, atau IP perangkat tujuan."},
            "layer": {"type": "string", "description": "Filter layer opsional: 'L2' (bridge/kabel fisik) atau 'L3' (routed).", "enum": ["L2", "L3"]}
        }, "required": ["source", "target"]}}},
    {"type": "function", "function": {
        "name": "analyze_network_change_impact",
        "description": "Mensimulasikan dampak jika suatu node atau interface mengalami gangguan/maintenance, memprediksi perangkat yang terisolasi dan blast radius.",
        "parameters": {"type": "object", "properties": {
            "target_node_id": {"type": "string", "description": "Nama, ID, atau IP node yang akan disimulasikan."},
            "change_type": {"type": "string", "description": "Tipe perubahan: 'node_offline', 'node_maintenance', 'interface_down'.", "default": "node_offline"},
            "affected_interface": {"type": "string", "description": "Nama interface jika change_type adalah interface_down."}
        }, "required": ["target_node_id"]}}},
    {"type": "function", "function": {
        "name": "diagnose_network_route",
        "description": "Mengevaluasi tabel rute dan Longest Prefix Match (LPM) untuk alamat IP tujuan pada router MikroTik.",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string", "description": "Nama perangkat MikroTik di inventory (misal 'R1')."},
            "target_ip": {"type": "string", "description": "Alamat IP tujuan yang ingin dievaluasi jalurnya."}
        }, "required": ["device_name", "target_ip"]}}},
    {"type": "function", "function": {
        "name": "audit_network_firewall",
        "description": "Mengaudit aturan firewall filter, efisiensi posisi FastTrack, dan kelengkapan NAT masquerade pada router MikroTik.",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string", "description": "Nama perangkat MikroTik di inventory (misal 'R1')."}
        }, "required": ["device_name"]}}},
    {"type": "function", "function": {
        "name": "audit_network_vlan",
        "description": "Mengaudit konfigurasi VLAN bridge, isolasi broadcast domain, dan PVID port pada router MikroTik.",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string", "description": "Nama perangkat MikroTik di inventory (misal 'R1')."}
        }, "required": ["device_name"]}}},
]