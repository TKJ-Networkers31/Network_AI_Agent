"""
AIRA OS — Server-Side Request Forgery (SSRF) Protection & URL Validator.

Enforces OWASP Top 10 A10:2021 (Server-Side Request Forgery) protection.
Blocks requests to internal, loopback, link-local, cloud metadata, and multicast addresses.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("aira.security.ssrf")

# Cloud metadata addresses to strictly block
CLOUD_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.internal",
    "instance-data",
}

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # IPv4 Loopback
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud metadata
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("::/128"),            # IPv6 Unspecified
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-local
    ipaddress.ip_network("ff00::/8"),          # IPv6 Multicast
]

PRIVATE_RFC1918_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),     # CGNAT
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
]


def validate_safe_url(
    url: str,
    allow_private_devices: bool = False,
    registered_device_ips: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """
    Validates whether an external URL or host is safe to request.

    Args:
        url: The URL to validate (http:// or https://)
        allow_private_devices: If True, allows private RFC1918 IPs only if they match
                               registered_device_ips (for NOC device interactions).
        registered_device_ips: Set of allowed NOC inventory device IP strings.

    Returns:
        (is_safe, error_message): Tuple indicating whether target is safe to fetch.
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, f"Protokol '{parsed.scheme}' tidak diizinkan. Hanya HTTP dan HTTPS yang didukung."

    hostname = parsed.hostname
    if not hostname:
        return False, "Host tidak valid dalam URL."

    hostname_lower = hostname.lower()

    # Block metadata domains
    if hostname_lower in CLOUD_METADATA_HOSTS:
        logger.warning("SSRF blocked attempt to access cloud metadata: %s", hostname_lower)
        return False, "Akses ke metadata instance atau cloud provider ditolak oleh kebijakan keamanan."

    # Resolve hostname to IP address
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Tidak dapat menyelesaikan nama domain: '{hostname}'."

    resolved_ips = set()
    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            resolved_ips.add(ip_obj)
        except ValueError:
            continue

    if not resolved_ips:
        return False, f"Tidak ada alamat IP yang valid untuk '{hostname}'."

    for ip_obj in resolved_ips:
        # Check blocked networks (Loopback, Link-local, Metadata, Multicast)
        for net in BLOCKED_IP_NETWORKS:
            if ip_obj in net:
                logger.warning("SSRF blocked access to restricted IP %s for host %s", ip_obj, hostname)
                return False, f"Akses ke alamat IP terlarang ({ip_obj}) ditolak."

        # Check private networks
        is_private = any(ip_obj in priv_net for priv_net in PRIVATE_RFC1918_NETWORKS)
        if is_private:
            if allow_private_devices and registered_device_ips:
                if str(ip_obj) in registered_device_ips:
                    continue  # Explicitly registered NOC device IP allowed
            logger.warning("SSRF blocked access to private network IP %s for host %s", ip_obj, hostname)
            return False, f"Akses ke subnet jaringan privat ({ip_obj}) tidak diizinkan untuk resource eksternal."

    return True, ""
