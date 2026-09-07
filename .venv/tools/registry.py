from tools.network.diagnostics import (
    ping,
    nslookup,
    traceroute,
)

from tools.inventory import list_devices

from tools.snmp.monitor import (
    get_system_info as snmp_get_system_info,
    get_interface_traffic as snmp_get_interface_traffic,
)

from tools.mikrotik.routeros import (
    get_interfaces,
    get_ip_addresses,
    get_routes,
    get_firewall,
    get_resources,
    get_identity,
    get_dns,
    get_dhcp_client,
    get_dhcp_server,
    get_nat,
    get_neighbors,
    get_arp,
)

from tools.web.search import (
    web_search,
    web_fetch,
)

TOOL_CATEGORY = {
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

    "web_search": "web",
    "web_fetch": "web",
}


# Semua tool saat ini adalah "print" (read-only) sehingga aman.
# Set ini disiapkan untuk masa depan: begitu kamu menambahkan tool
# yang bisa MENGUBAH konfigurasi (add/remove/set/disable/enable dsb),
# daftarkan nama tool-nya di sini agar engine.py meminta konfirmasi
# manual dari user sebelum tool tersebut dieksekusi.
DANGEROUS_TOOLS = set()


TOOL_MAP = {
    "ping": ping,
    "nslookup": nslookup,
    "traceroute": traceroute,

    "list_devices": list_devices,

    "get_interfaces": get_interfaces,
    "get_ip_addresses": get_ip_addresses,
    "get_routes": get_routes,
    "get_firewall": get_firewall,
    "get_resources": get_resources,
    "get_identity": get_identity,
    "get_dns": get_dns,
    "get_dhcp_client": get_dhcp_client,
    "get_dhcp_server": get_dhcp_server,
    "get_nat": get_nat,
    "get_neighbors": get_neighbors,
    "get_arp": get_arp,

    "snmp_get_system_info": snmp_get_system_info,
    "snmp_get_interface_traffic": snmp_get_interface_traffic,

    "web_search": web_search,
    "web_fetch": web_fetch,
}


def execute_tool(
    name,
    arguments
):

    if name not in TOOL_MAP:

        return {
            "success": False,
            "error": (
                f"Tool '{name}' tidak ditemukan."
            )
        }

    try:

        return TOOL_MAP[name](
            **arguments
        )

    except Exception as exc:

        return {
            "success": False,
            "tool": name,
            "error": str(exc)
        }