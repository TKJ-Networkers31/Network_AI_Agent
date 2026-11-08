"""
core/network_intelligence/preflight.py — Controlled Lab Connection Preflight & Capability Audit.

Phase 6: Lab Preflight Diagnostic Engine.
Validates target reachability, authentication, identity, version, effective access rights,
output quality, and parser completeness with strict read-only backend controls.
Never exposes or logs credentials.
"""

from __future__ import annotations

import logging
import re
import socket
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from agents.akane.connection_manager import get_connection_manager
from core.canonical_network import get_canonical_registry, parse_routeros_major_version
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.models import (
    PreflightResult,
    PreflightStatus,
)
from core.network_intelligence.security import (
    validate_readonly_command,
)
from core.topology_models import sanitize_untrusted_text
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.network_intelligence.preflight")

# Baseline non-mutating commands tested during preflight
PREFLIGHT_DIAGNOSTIC_COMMANDS = [
    ("/system identity print", "identity", True),
    ("/system resource print", "resources", True),
    ("/interface print brief", "interfaces", True),
    ("/ip address print detail", "ip_addresses", True),
    ("/ip route print", "routes", True),
    ("/ip firewall filter print count-only", "firewall_filter", False),
    ("/ip firewall nat print count-only", "nat_rules", False),
]


class LabPreflightChecker:
    """
    Executes non-invasive, read-only preflight diagnostic audit of a target lab device.
    Strictly adheres to:
    - Zero configuration mutation
    - Explicit status differentiation (7 PreflightStatus values)
    - Distinguishing TCP connect from SSH auth
    - Redacting all credentials and tokens
    """

    def __init__(self):
        self.cm = get_connection_manager()
        self.collector = EvidenceCollector()
        self.registry = get_canonical_registry()

    def run_preflight(
        self,
        target: str,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
        timeout: float = 4.0,
        correlation_id: Optional[str] = None,
    ) -> PreflightResult:
        """
        Runs comprehensive diagnostic preflight on target.
        """
        t0 = time.time()
        corr_id = correlation_id or f"preflight_{uuid.uuid4().hex[:10]}"

        # 1. Target & Credential Resolution
        if not target or not target.strip():
            return PreflightResult(
                target=target or "UNKNOWN",
                status=PreflightStatus.NOT_CONFIGURED.value,
                reachability=False,
                authenticated=False,
                correlation_id=corr_id,
                duration_ms=round((time.time() - t0) * 1000, 2),
                message="Target router tidak ditentukan atau string kosong.",
                limitations="Nama perangkat atau IP harus diberikan.",
            )

        resolved_host = target.strip()
        resolved_user = username
        resolved_pass = password
        resolved_port = port
        resolved_key = key_data
        dev_name: Optional[str] = None

        # Check inventory if direct credentials not provided
        if not resolved_pass and not resolved_key:
            target_info = self.cm._resolve_target(resolved_host)
            if target_info.get("success"):
                resolved_host = target_info.get("host", resolved_host)
                resolved_user = resolved_user or target_info.get("username", "admin")
                resolved_pass = target_info.get("password")
                resolved_key = target_info.get("key_data")
                resolved_port = target_info.get("port", resolved_port)
                dev_name = target_info.get("name")
            else:
                # Target not in inventory and no credentials supplied
                if not username and not password:
                    return PreflightResult(
                        target=target,
                        status=PreflightStatus.NOT_CONFIGURED.value,
                        reachability=False,
                        authenticated=False,
                        correlation_id=corr_id,
                        duration_ms=round((time.time() - t0) * 1000, 2),
                        message=f"Target '{target}' tidak ditemukan di inventory dan credential SSH tidak disertakan.",
                        limitations="Konfigurasikan credential perangkat di inventaris atau berikan parameter autentikasi.",
                    )

        resolved_user = resolved_user or "admin"

        # 2. Reachability & SSH Banner Probe
        reachability_ok, banner_or_err = self._probe_tcp_and_banner(resolved_host, resolved_port, timeout=timeout)
        if not reachability_ok:
            return PreflightResult(
                target=target,
                status=PreflightStatus.UNREACHABLE.value,
                reachability=False,
                authenticated=False,
                correlation_id=corr_id,
                duration_ms=round((time.time() - t0) * 1000, 2),
                message=f"Koneksi jaringan gagal ke {resolved_host}:{resolved_port}: {banner_or_err}",
                limitations="Perangkat mati, port SSH tertutup, atau terhalang firewall jaringan.",
            )

        # 3. Authentication & Ephemeral Session Verification
        auth_result = self.cm.test_target_credentials(
            host=resolved_host,
            username=resolved_user,
            password=resolved_pass,
            port=resolved_port,
            key_data=resolved_key,
            timeout=timeout,
        )

        if not auth_result.get("authenticated", False):
            err_type = auth_result.get("error_type")
            err_msg = auth_result.get("message") or "Autentikasi gagal"
            if err_type in ("timeout", "unreachable"):
                return PreflightResult(
                    target=target,
                    status=PreflightStatus.UNREACHABLE.value,
                    reachability=False,
                    authenticated=False,
                    correlation_id=corr_id,
                    duration_ms=round((time.time() - t0) * 1000, 2),
                    message=f"Timeout saat handshake SSH ke {resolved_host}: {err_msg}",
                    limitations="Transport SSH tidak merespons dalam batas waktu.",
                )
            return PreflightResult(
                target=target,
                status=PreflightStatus.AUTH_FAILED.value,
                reachability=True,
                authenticated=False,
                correlation_id=corr_id,
                duration_ms=round((time.time() - t0) * 1000, 2),
                message=f"Autentikasi SSH ditolak untuk user '{resolved_user}': {err_msg}",
                limitations="Username, password, atau SSH key tidak valid pada router target.",
            )

        # 4. Identity & RouterOS Version Verification
        identity_val = auth_result.get("identity")
        raw_identity_out = ""
        version_str: Optional[str] = None
        ros_major: Optional[int] = None

        # Execute identity and resource commands
        id_cmd_res = self.cm.execute_command(
            command="/system identity print",
            device_name=dev_name,
            host=resolved_host,
            username=resolved_user,
            password=resolved_pass,
            port=resolved_port,
            key_data=resolved_key,
            timeout=timeout,
        )

        if id_cmd_res.get("success"):
            raw_identity_out = id_cmd_res.get("output", "").strip()
            for line in raw_identity_out.splitlines():
                if "name:" in line.lower():
                    identity_val = line.split(":", 1)[1].strip()
                    break

        if not identity_val and not raw_identity_out:
            return PreflightResult(
                target=target,
                status=PreflightStatus.IDENTITY_UNVERIFIED.value,
                reachability=True,
                authenticated=True,
                identity=None,
                correlation_id=corr_id,
                duration_ms=round((time.time() - t0) * 1000, 2),
                message="Koneksi SSH berhasil tetapi pembacaan identitas router gagal atau kosong.",
                limitations="Perangkat tidak merespons command /system identity print secara valid.",
            )

        res_cmd_res = self.cm.execute_command(
            command="/system resource print",
            device_name=dev_name,
            host=resolved_host,
            username=resolved_user,
            password=resolved_pass,
            port=resolved_port,
            key_data=resolved_key,
            timeout=timeout,
        )
        if res_cmd_res.get("success"):
            raw_res_out = res_cmd_res.get("output", "")
            for line in raw_res_out.splitlines():
                if "version:" in line.lower():
                    v_raw = line.split(":", 1)[1].strip()
                    version_str = v_raw
                    ros_major = parse_routeros_major_version(v_raw)
                    break

        ros_major = ros_major or 7

        # 5. Diagnostic Commands & Capabilities Verification
        allowed_tested: List[str] = []
        rejected_cmds: List[Dict[str, str]] = []
        parsed_tables: List[str] = []
        cmd_latencies: List[float] = []
        truncated_count = 0
        prompt_mismatches = 0
        critical_failed = 0

        for cmd, obs_type, is_critical in PREFLIGHT_DIAGNOSTIC_COMMANDS:
            # Check security policy allowlist first
            is_valid, reason = validate_readonly_command(cmd)
            if not is_valid:
                rejected_cmds.append({"command": cmd, "reason": f"Blocked by security allowlist: {reason}"})
                if is_critical:
                    critical_failed += 1
                continue

            t_cmd = time.perf_counter()
            exec_res = self.cm.execute_command(
                command=cmd,
                device_name=dev_name,
                host=resolved_host,
                username=resolved_user,
                password=resolved_pass,
                port=resolved_port,
                key_data=resolved_key,
                timeout=timeout,
            )
            lat_ms = (time.perf_counter() - t_cmd) * 1000.0
            cmd_latencies.append(lat_ms)

            if not exec_res.get("success"):
                err_text = exec_res.get("error", "Execution failed")
                rejected_cmds.append({"command": cmd, "reason": err_text})
                if is_critical:
                    critical_failed += 1
                continue

            allowed_tested.append(cmd)
            raw_out = exec_res.get("output", "").strip()

            if "not enough permissions" in raw_out.lower() or "syntax error" in raw_out.lower():
                rejected_cmds.append({"command": cmd, "reason": f"RouterOS error: {raw_out[:100]}"})
                if is_critical:
                    critical_failed += 1
                continue

            if exec_res.get("warning") or not exec_res.get("prompt_matched", True):
                prompt_mismatches += 1

            if "[truncated]" in raw_out.lower():
                truncated_count += 1

            # Validate normalizer parsing
            try:
                norm = self.collector._normalize_observation(obs_type, raw_out, ros_major)
                if norm is not None:
                    parsed_tables.append(obs_type)
            except Exception as e:
                logger.warning("Normalizer check failed for %s: %s", obs_type, e)

        # 6. Determine Effective Permissions & Final Preflight Status
        effective_perms: List[str] = []
        if len(allowed_tested) > 0:
            effective_perms.append("read")

        # Determine overall status
        if critical_failed > 0:
            status = PreflightStatus.CONNECTED_READ_ONLY.value
            msg = f"Tersambung ke {identity_val}, namun {critical_failed} command diagnostik inti gagal dieksekusi."
            limits = "Hak akses user router dibatasi atau syntax command tidak didukung versi RouterOS ini."
        elif len(rejected_cmds) > 0 or len(parsed_tables) < len(PREFLIGHT_DIAGNOSTIC_COMMANDS) - 1:
            status = PreflightStatus.PARTIAL_CAPABILITY.value
            msg = f"Tersambung ke {identity_val} dengan kapabilitas diagnostik parsial ({len(parsed_tables)} tabel terparse valid)."
            limits = f"{len(rejected_cmds)} command opsional gagal atau ditolak hak akses."
        else:
            status = PreflightStatus.READY_FOR_DIAGNOSTICS.value
            msg = f"Perangkat {identity_val} (RouterOS v{ros_major}) siap untuk investigasi diagnostik penuh."
            limits = "Mode read-only aktif. Tidak ada command mutasi yang diizinkan."

        avg_lat = round(sum(cmd_latencies) / len(cmd_latencies), 2) if cmd_latencies else 0.0

        return PreflightResult(
            target=target,
            status=status,
            reachability=True,
            authenticated=True,
            identity=identity_val,
            routeros_version=version_str,
            ros_major_version=ros_major,
            effective_permissions=effective_perms,
            allowed_commands_tested=allowed_tested,
            rejected_commands=rejected_cmds,
            output_quality={
                "avg_latency_ms": avg_lat,
                "command_count": len(PREFLIGHT_DIAGNOSTIC_COMMANDS),
                "prompt_mismatches": prompt_mismatches,
                "truncated_count": truncated_count,
            },
            parser_completeness={
                "parsed_tables": parsed_tables,
                "table_count": len(parsed_tables),
                "missing_or_failed_tables": [
                    t for _, t, _ in PREFLIGHT_DIAGNOSTIC_COMMANDS if t not in parsed_tables
                ],
            },
            correlation_id=corr_id,
            duration_ms=round((time.time() - t0) * 1000, 2),
            message=msg,
            limitations=limits,
        )

    def _probe_tcp_and_banner(self, host: str, port: int, timeout: float = 3.0) -> Tuple[bool, str]:
        """
        Tests TCP handshake and verifies that an actual SSH daemon presents a banner.
        Does NOT rely solely on TCP connect_ex == 0.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((host, port))
            if res != 0:
                s.close()
                return False, f"TCP connect failed (code {res})"

            # Must read SSH banner to guarantee a real SSH service is listening
            banner_bytes = s.recv(1024)
            s.close()
            if not banner_bytes:
                return False, "Koneksi terbuka tetapi tidak ada SSH banner yang diterima (empty)"
            banner_str = banner_bytes.decode("ascii", errors="replace").strip()
            if not banner_str.startswith("SSH-"):
                return False, f"Layanan pada port {port} bukan SSH daemon (banner: '{banner_str[:30]}')"

            return True, banner_str
        except socket.timeout:
            return False, "Handshake soket atau pembacaan banner SSH mengalami timeout"
        except Exception as e:
            return False, str(e)
