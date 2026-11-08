"""
AIRA OS — Edge Gateway Read-Only Diagnostic Sandbox & Sanitizer (Networking VIII / WP 8.4.6).

Enforces the absolute non-negotiable invariant:
Live router configurations can NEVER be mutated through the Edge Gateway.
Arbitrary shell execution is completely forbidden and rejected at the gateway.
"""

from __future__ import annotations

import ipaddress
import logging
import platform
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aira.edge_gateway.collector")

# Strict allowlist of safe, read-only RouterOS API / CLI commands
ROUTEROS_ALLOWED_COMMANDS = {
    "/ip/address/print",
    "/ip/route/print",
    "/interface/print",
    "/interface/ethernet/print",
    "/ip/arp/print",
    "/system/resource/print",
    "/system/routerboard/print",
    "/routing/ospf/neighbor/print",
    "/routing/bgp/session/print",
}

# Forbidden mutating verbs
FORBIDDEN_MUTATING_VERBS = {
    "add", "set", "remove", "enable", "disable",
    "reboot", "reset", "export", "import", "comment",
    "edit", "move", "rename", "run", "upgrade",
}

# Dangerous shell injection characters
SHELL_INJECTION_PATTERN = re.compile(r"[;&|`$><\\!]")


class DiagnosticSanitizerError(Exception):
    """Raised when a command violates the read-only sandbox or security allowlist."""
    pass


class EdgeDiagnosticCollector:
    """Read-only local network diagnostic and telemetry collector."""

    @staticmethod
    def validate_target_ip(ip_str: str) -> str:
        """Validates that a string is a legitimate IPv4 or IPv6 address."""
        clean_ip = ip_str.strip()
        try:
            ipaddress.ip_address(clean_ip)
            return clean_ip
        except ValueError:
            raise DiagnosticSanitizerError(f"Security Rejection: Invalid IP address '{ip_str}'.")

    @classmethod
    def sanitize_routeros_command(cls, command: str) -> str:
        """
        Validates that a RouterOS command is strictly in the read-only allowlist.
        Rejects shell injection characters and mutating verbs.
        """
        cmd_clean = command.strip().lower()

        # Check shell injection delimiters
        if SHELL_INJECTION_PATTERN.search(cmd_clean):
            raise DiagnosticSanitizerError(
                f"Security Rejection: Command contains dangerous shell injection characters."
            )

        # Check mutating verbs
        tokens = cmd_clean.split()
        for tok in tokens:
            if tok in FORBIDDEN_MUTATING_VERBS:
                raise DiagnosticSanitizerError(
                    f"Security Rejection: Mutating verb '{tok}' is strictly forbidden on Edge Gateway."
                )

        # Check allowlist
        base_cmd = tokens[0] if tokens else ""
        if base_cmd not in ROUTEROS_ALLOWED_COMMANDS:
            raise DiagnosticSanitizerError(
                f"Security Rejection: Command '{base_cmd}' is not in the approved read-only allowlist."
            )

        return cmd_clean

    def run_icmp_ping(self, target_ip: str, count: int = 3, timeout_sec: float = 2.0) -> Dict[str, Any]:
        """
        Executes a bounded ICMP ping to verify local subnet device reachability.
        Uses parameter validation to prevent OS command injection.
        """
        valid_ip = self.validate_target_ip(target_ip)
        safe_count = max(1, min(5, count))
        safe_timeout = max(1.0, min(5.0, timeout_sec))

        is_windows = platform.system().lower() == "windows"
        if is_windows:
            timeout_ms = int(safe_timeout * 1000)
            args = ["ping", "-n", str(safe_count), "-w", str(timeout_ms), valid_ip]
        else:
            args = ["ping", "-c", str(safe_count), "-W", str(max(1, int(safe_timeout))), valid_ip]

        start_t = time.perf_counter()
        try:
            res = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=safe_timeout * safe_count + 2.0,
                check=False,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            if is_windows:
                is_reachable = res.returncode == 0 and "Reply from" in res.stdout
            else:
                out_lower = res.stdout.lower()
                is_reachable = res.returncode == 0 and ("bytes from" in out_lower or "0% packet loss" in out_lower or "1 packets received" in out_lower)

            return {
                "target_ip": valid_ip,
                "reachable": is_reachable,
                "duration_ms": round(duration_ms, 2),
                "packets_transmitted": safe_count,
                "raw_output": res.stdout[:500],
            }
        except Exception as e:
            return {
                "target_ip": valid_ip,
                "reachable": False,
                "error": str(e),
                "duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }

    def run_tcp_port_probe(self, target_ip: str, port: int, timeout_sec: float = 2.0) -> Dict[str, Any]:
        """Probes TCP port reachability (e.g. RouterOS API 8728, SSH 22)."""
        valid_ip = self.validate_target_ip(target_ip)
        if not (1 <= port <= 65535):
            raise DiagnosticSanitizerError(f"Invalid port: {port}. Must be 1-65535.")

        start_t = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(max(0.5, min(5.0, timeout_sec)))
        try:
            res = sock.connect_ex((valid_ip, port))
            is_open = res == 0
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return {
                "target_ip": valid_ip,
                "port": port,
                "is_open": is_open,
                "duration_ms": round(duration_ms, 2),
            }
        except Exception as e:
            return {
                "target_ip": valid_ip,
                "port": port,
                "is_open": False,
                "error": str(e),
            }
        finally:
            sock.close()
