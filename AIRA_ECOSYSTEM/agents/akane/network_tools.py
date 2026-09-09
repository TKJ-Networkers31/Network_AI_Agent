"""
agents/akane/network_tools.py — implementasi kemampuan AKANE.
Wrapper tipis di atas tools/ssh, tools/snmp, tools/mikrotik, tools/network,
tools/inventory (SUDAH dipindah ke AIRA_ECOSYSTEM/tools/*). Ini SATU-SATUNYA
tempat yang boleh import tools/* jaringan.
"""

from tools.network.diagnostics import ping as _ping, nslookup as _nslookup, traceroute as _traceroute
from tools.inventory import list_devices as _list_devices
from tools.mikrotik.routeros import (
    get_interfaces as _get_interfaces,
    get_ip_addresses as _get_ip_addresses,
    get_routes as _get_routes,
    get_firewall as _get_firewall,
    get_resources as _get_resources,
    get_identity as _get_identity,
    get_dns as _get_dns,
    get_dhcp_client as _get_dhcp_client,
    get_dhcp_server as _get_dhcp_server,
    get_nat as _get_nat,
    get_neighbors as _get_neighbors,
    get_arp as _get_arp,
)
from tools.snmp.monitor import (
    get_system_info as _snmp_get_system_info,
    get_interface_traffic as _snmp_get_interface_traffic,
)


def ping(target: str, count: int = 4) -> dict:
    return _ping(target, count)


def nslookup(target: str) -> dict:
    return _nslookup(target)


def traceroute(target: str) -> dict:
    return _traceroute(target)


def list_devices() -> dict:
    return _list_devices()


def get_interfaces(device_name: str) -> dict:
    return _get_interfaces(device_name)


def get_ip_addresses(device_name: str) -> dict:
    return _get_ip_addresses(device_name)


def get_routes(device_name: str) -> dict:
    return _get_routes(device_name)


def get_firewall(device_name: str) -> dict:
    return _get_firewall(device_name)


def get_resources(device_name: str) -> dict:
    return _get_resources(device_name)


def get_identity(device_name: str) -> dict:
    return _get_identity(device_name)


def get_dns(device_name: str) -> dict:
    return _get_dns(device_name)


def get_dhcp_client(device_name: str) -> dict:
    return _get_dhcp_client(device_name)


def get_dhcp_server(device_name: str) -> dict:
    return _get_dhcp_server(device_name)


def get_nat(device_name: str) -> dict:
    return _get_nat(device_name)


def get_neighbors(device_name: str) -> dict:
    return _get_neighbors(device_name)


def get_arp(device_name: str) -> dict:
    return _get_arp(device_name)


def snmp_get_system_info(device_name: str) -> dict:
    return _snmp_get_system_info(device_name)


def snmp_get_interface_traffic(device_name: str) -> dict:
    return _snmp_get_interface_traffic(device_name)
