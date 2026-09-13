"""
agents/akane/network_tools.py — implementasi kemampuan AKANE.

FIX (Phase 2.2 - AKANE Persistent Connection Engine):
Semua command yang menyentuh RouterOS lewat SSH (dulu ssh_execute() per
command, connect+exec+kembalikan) SEKARANG lewat
agents/akane/connection_manager.py::execute_for_device(), yang memakai
SATU shell channel persisten per device (invoke_shell), dibuka sekali
dan dipakai ulang untuk command berikutnya - tidak ada login berulang.

tools/ssh/client.py (ssh_execute, exec_command per call) TIDAK dihapus -
dipertahankan untuk kompatibilitas modul lain, tapi network_tools.py
TIDAK memanggilnya lagi untuk command-command mikrotik di bawah.

Tetap SATU-SATUNYA tempat yang boleh import tools/ssh, tools/snmp,
tools/mikrotik, tools/network, tools/inventory + connection_manager.
"""

from tools.network.diagnostics import ping as _ping, nslookup as _nslookup, traceroute as _traceroute
from tools.inventory import list_devices as _list_devices
from tools.mikrotik.routeros import COMMANDS as _MIKROTIK_COMMANDS
from tools.snmp.monitor import (
    get_system_info as _snmp_get_system_info,
    get_interface_traffic as _snmp_get_interface_traffic,
)

from agents.akane.connection_manager import get_connection_manager


def ping(target: str, count: int = 4) -> dict:
    return _ping(target, count)


def nslookup(target: str) -> dict:
    return _nslookup(target)


def traceroute(target: str) -> dict:
    return _traceroute(target)


def list_devices() -> dict:
    return _list_devices()


def _run_mikrotik_command(tool_name: str, device_name: str) -> dict:
    """
    Jalankan salah satu command RouterOS (lihat tools/mikrotik/routeros.py
    ::COMMANDS) lewat ConnectionManager - session SSH dibuka sekali per
    device dan dipakai ulang untuk semua command berikutnya.
    """

    command = _MIKROTIK_COMMANDS.get(tool_name)

    if not command:
        return {"success": False, "error": f"Tool MikroTik '{tool_name}' tidak tersedia."}

    manager = get_connection_manager()
    result = manager.execute_for_device(device_name, command)

    return {
        **result,
        "tool": tool_name,
        "category": "mikrotik",
        "device": device_name,
    }


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
    return _snmp_get_system_info(device_name)


def snmp_get_interface_traffic(device_name: str) -> dict:
    return _snmp_get_interface_traffic(device_name)