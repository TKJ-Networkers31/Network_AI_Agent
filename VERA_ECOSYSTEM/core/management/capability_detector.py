"""
core/management/capability_detector.py — Capability & Reachability Detection for Multi-Path Device Management.

Determines available management protocols per device based on concrete evidence:
- Layer 3 IP reachability (SSH, RouterOS API)
- Layer 2 Adjacency & MAC reachability (MAC Telnet, MAC WinBox)
- RouterOS Version & RoMON support (Router Management Overlay Network)
"""
from __future__ import annotations

import logging
import re
import socket
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vera.management.detector")

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$|^([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$")
IPV4_REGEX = re.compile(r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")


def is_mac(val: Optional[str]) -> bool:
    if not val or not isinstance(val, str):
        return False
    return bool(MAC_REGEX.match(val.strip()))


def is_ip(val: Optional[str]) -> bool:
    if not val or not isinstance(val, str):
        return False
    return bool(IPV4_REGEX.match(val.strip()))


def check_tcp_port(host: str, port: int, timeout: float = 1.5) -> Tuple[bool, float, Optional[str]]:
    """Quick non-blocking TCP socket connect check."""
    import time
    if not is_ip(host):
        return False, 0.0, "Invalid IP address"

    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = (time.time() - start) * 1000.0
            return True, round(latency, 2), None
    except socket.timeout:
        return False, 0.0, f"Connection timed out ({timeout}s)"
    except ConnectionRefusedError:
        return False, 0.0, f"Port {port} connection refused"
    except Exception as exc:
        return False, 0.0, str(exc)


class CapabilityDetector:
    """Evaluates reachability and protocol compatibility across management paths."""

    @staticmethod
    def detect_ip_capabilities(host: str, ssh_port: int = 22, api_port: int = 8728) -> Dict[str, Any]:
        """Checks if SSH and RouterOS API are open and reachable over IP."""
        if not is_ip(host):
            return {
                "ip_valid": False,
                "ssh_reachable": False,
                "api_reachable": False,
                "reason": "Host bukan alamat IPv4 yang valid.",
            }

        ssh_ok, ssh_lat, ssh_err = check_tcp_port(host, ssh_port)
        api_ok, api_lat, api_err = check_tcp_port(host, api_port)

        return {
            "ip_valid": True,
            "ssh_reachable": ssh_ok,
            "ssh_latency_ms": ssh_lat,
            "ssh_error": ssh_err,
            "api_reachable": api_ok,
            "api_latency_ms": api_lat,
            "api_error": api_err,
        }

    @staticmethod
    def check_layer2_adjacency(
        target_mac: str,
        target_ip: Optional[str] = None,
        adjacent_interfaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Determines whether the target device is directly on a Layer 2 broadcast domain.
        MAC Telnet and MAC WinBox are non-routable Layer 2 protocols; they cannot cross L3 routers.
        """
        if not is_mac(target_mac):
            return {
                "is_adjacent": False,
                "reason": "MAC address target tidak valid atau tidak diketahui.",
            }

        # Check local ARP table / neighbor table
        clean_mac = target_mac.strip().lower()
        arp_found = False
        detected_iface = None

        try:
            with open("/proc/net/arp", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 6:
                        row_ip, hw_type, flags, hw_mac, mask, device = parts[:6]
                        if hw_mac.lower() == clean_mac:
                            arp_found = True
                            detected_iface = device
                            break
                        if target_ip and row_ip == target_ip:
                            arp_found = True
                            detected_iface = device
                            break
        except Exception as exc:
            logger.debug("Gagal membaca /proc/net/arp: %s", exc)

        if arp_found:
            return {
                "is_adjacent": True,
                "interface": detected_iface,
                "reason": f"Perangkat terdeteksi langsung di Layer 2 (interface {detected_iface}).",
            }

        # If user explicitly specified adjacent interface or device is on known bridge
        if adjacent_interfaces and len(adjacent_interfaces) > 0:
            return {
                "is_adjacent": True,
                "interface": adjacent_interfaces[0],
                "reason": f"Perangkat terhubung pada interface lokal Layer 2 {adjacent_interfaces[0]}.",
            }

        return {
            "is_adjacent": False,
            "reason": "Perangkat tidak terdeteksi di segmen Layer 2 lokal (tidak ada di ARP / broadcast domain).",
        }

    @staticmethod
    def evaluate_romon_compatibility(
        routeros_version: str,
        vendor: str = "MikroTik",
    ) -> Dict[str, Any]:
        """
        RoMON (Router Management Overlay Network) is a MikroTik proprietary protocol
        introduced in RouterOS v6.28. It is not supported on non-MikroTik devices or pre-v6.28 versions.
        """
        if vendor.lower() not in ("mikrotik", "routeros"):
            return {
                "supported": False,
                "reason": f"Vendor '{vendor}' tidak mendukung MikroTik RoMON.",
            }

        if not routeros_version:
            # Assume potential support for modern MikroTik devices until polled
            return {
                "supported": True,
                "version": "unknown",
                "reason": "Perangkat MikroTik, kapabilitas RoMON menunggu verifikasi versi RouterOS.",
            }

        # Parse version
        match = re.search(r"(\d+)\.(\d+)", routeros_version)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            if major > 6 or (major == 6 and minor >= 28):
                return {
                    "supported": True,
                    "version": routeros_version,
                    "reason": f"RouterOS v{routeros_version} kompatibel dengan RoMON (v6.28+ atau v7).",
                }
            else:
                return {
                    "supported": False,
                    "version": routeros_version,
                    "reason": f"RouterOS v{routeros_version} terlalu lawas untuk RoMON (memerlukan minimal v6.28).",
                }

        return {
            "supported": True,
            "version": routeros_version,
            "reason": "RouterOS terdeteksi, berpotensi mendukung RoMON.",
        }
