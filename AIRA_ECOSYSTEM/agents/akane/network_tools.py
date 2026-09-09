"""
agents/akane/network_tools.py — implementasi kemampuan AKANE.

Ini murni WRAPPER tipis di atas tools/ssh, tools/snmp, tools/mikrotik,
tools/network, tools/inventory yang SUDAH ADA (logic paramiko/pysnmp TIDAK
perlu ditulis ulang, cuma di-import dan dipanggil dari sini).

Kenapa perlu lapisan wrapper padahal fungsinya cuma "panggil balik": supaya
`core/orchestrator.py` dan `api/` HANYA PERNAH import `agents.akane`,
TIDAK PERNAH `import tools.ssh` / `import tools.snmp` langsung - menjaga
aturan "Jangan mencampur SSH dengan UI" tetap valid secara struktural
(import-linter/aturan tim bisa cek ini otomatis kalau perlu nanti).

TODO migrasi: uncomment import di bawah setelah tools/ssh, tools/snmp,
tools/mikrotik, tools/network, tools/inventory dipindah ke
AIRA_ECOSYSTEM/tools/ (lihat MIGRATION_PLAN.md Tahap 3).
"""

# from tools.network.diagnostics import ping as _ping, nslookup as _nslookup, traceroute as _traceroute
# from tools.inventory import list_devices as _list_devices
# from tools.mikrotik.routeros import (
#     get_interfaces as _get_interfaces,
#     get_ip_addresses as _get_ip_addresses,
#     get_routes as _get_routes,
#     get_firewall as _get_firewall,
#     get_resources as _get_resources,
#     get_identity as _get_identity,
#     get_dns as _get_dns,
#     get_dhcp_client as _get_dhcp_client,
#     get_dhcp_server as _get_dhcp_server,
#     get_nat as _get_nat,
#     get_neighbors as _get_neighbors,
#     get_arp as _get_arp,
# )
# from tools.snmp.monitor import (
#     get_system_info as _snmp_get_system_info,
#     get_interface_traffic as _snmp_get_interface_traffic,
# )


def _not_wired(name: str) -> dict:
    return {
        "success": False,
        "tool": name,
        "error": (
            f"AKANE.{name} belum disambungkan ke tools/* - lihat "
            f"MIGRATION_PLAN.md Tahap 3, lalu uncomment import di file ini."
        ),
    }


def ping(target: str, count: int = 4) -> dict:
    return _not_wired("ping")  # TODO: return _ping(target, count)


def nslookup(target: str) -> dict:
    return _not_wired("nslookup")  # TODO: return _nslookup(target)


def traceroute(target: str) -> dict:
    return _not_wired("traceroute")  # TODO: return _traceroute(target)


def list_devices() -> dict:
    return _not_wired("list_devices")  # TODO: return _list_devices()


def get_interfaces(device_name: str) -> dict:
    return _not_wired("get_interfaces")


def get_ip_addresses(device_name: str) -> dict:
    return _not_wired("get_ip_addresses")


def get_routes(device_name: str) -> dict:
    return _not_wired("get_routes")


def get_firewall(device_name: str) -> dict:
    return _not_wired("get_firewall")


def get_resources(device_name: str) -> dict:
    return _not_wired("get_resources")


def get_identity(device_name: str) -> dict:
    return _not_wired("get_identity")


def get_dns(device_name: str) -> dict:
    return _not_wired("get_dns")


def get_dhcp_client(device_name: str) -> dict:
    return _not_wired("get_dhcp_client")


def get_dhcp_server(device_name: str) -> dict:
    return _not_wired("get_dhcp_server")


def get_nat(device_name: str) -> dict:
    return _not_wired("get_nat")


def get_neighbors(device_name: str) -> dict:
    return _not_wired("get_neighbors")


def get_arp(device_name: str) -> dict:
    return _not_wired("get_arp")


def snmp_get_system_info(device_name: str) -> dict:
    return _not_wired("snmp_get_system_info")


def snmp_get_interface_traffic(device_name: str) -> dict:
    return _not_wired("snmp_get_interface_traffic")
