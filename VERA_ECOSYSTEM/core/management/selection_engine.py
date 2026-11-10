"""
core/management/selection_engine.py — Deterministic, Evidence-Based Management Path Selection Engine.

Evaluates:
1. IP management availability (SSH, RouterOS API)
2. Layer 2 adjacency & MAC reachability (MAC Telnet, MAC WinBox)
3. RoMON support and multi-hop reachability through authorized intermediaries
4. Manual administrative overrides

Produces an auditable selection rationale and explicit rejection reasons for every evaluated path.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.management.models import (
    DeviceManagementProfile,
    ManagementMethod,
    ManagementPath,
    PathStatus,
    RomonNeighbor,
)
from core.management.capability_detector import CapabilityDetector, is_ip, is_mac

logger = logging.getLogger("vera.management.selection")


class SelectionEngine:
    """Evaluates candidate management paths and selects the optimal path based on concrete evidence."""

    @classmethod
    def evaluate_paths(
        cls,
        device_id: str,
        device_name: str,
        host: Optional[str],
        mac: Optional[str] = None,
        vendor: str = "MikroTik",
        model: str = "",
        routeros_version: str = "",
        preferred_method: Optional[str] = None,
        manual_override: bool = False,
        romon_neighbors: Optional[List[RomonNeighbor]] = None,
        adjacent_interfaces: Optional[List[str]] = None,
        port: int = 22,
    ) -> DeviceManagementProfile:
        """Constructs a complete DeviceManagementProfile evaluating all 5 management paths."""
        paths: List[ManagementPath] = []
        is_mikrotik = vendor.lower() in ("mikrotik", "routeros")

        # -------------------------------------------------------------
        # 1. IP Capabilities (SSH & RouterOS API)
        # -------------------------------------------------------------
        ip_target = host if is_ip(host) else None
        ip_detection = CapabilityDetector.detect_ip_capabilities(host=ip_target or "") if ip_target else {
            "ip_valid": False, "ssh_reachable": False, "api_reachable": False, "reason": "Host bukan IP address."
        }

        # Path 1: SSH over IP
        ssh_status = PathStatus.AVAILABLE.value if ip_detection.get("ssh_reachable") else (
            PathStatus.UNAVAILABLE.value if ip_target else PathStatus.UNSUPPORTED.value
        )
        paths.append(ManagementPath(
            method=ManagementMethod.SSH_IP.value,
            target=ip_target or (host or "none"),
            port=port,
            status=ssh_status,
            latency_ms=ip_detection.get("ssh_latency_ms"),
            selection_reason="Koneksi langsung Layer 3 SSH aktif pada port 22." if ssh_status == PathStatus.AVAILABLE.value else "",
            rejection_reason="" if ssh_status == PathStatus.AVAILABLE.value else (
                ip_detection.get("ssh_error") or "Port SSH tidak merespons atau IP tidak terjangkau."
            ),
        ))

        # Path 2: RouterOS API over IP
        if is_mikrotik:
            api_status = PathStatus.AVAILABLE.value if ip_detection.get("api_reachable") else (
                PathStatus.UNAVAILABLE.value if ip_target else PathStatus.UNSUPPORTED.value
            )
            paths.append(ManagementPath(
                method=ManagementMethod.API_IP.value,
                target=ip_target or (host or "none"),
                port=8728,
                status=api_status,
                latency_ms=ip_detection.get("api_latency_ms"),
                selection_reason="RouterOS API aktif dan merespons pada port 8728." if api_status == PathStatus.AVAILABLE.value else "",
                rejection_reason="" if api_status == PathStatus.AVAILABLE.value else (
                    ip_detection.get("api_error") or "Port RouterOS API 8728 tidak terbuka atau diblokir firewall."
                ),
            ))

        # -------------------------------------------------------------
        # 2. Layer 2 Adjacency & MAC Management
        # -------------------------------------------------------------
        target_mac = mac if is_mac(mac) else (host if is_mac(host) else None)
        l2_check = CapabilityDetector.check_layer2_adjacency(
            target_mac=target_mac or "",
            target_ip=ip_target,
            adjacent_interfaces=adjacent_interfaces,
        )
        is_adjacent = l2_check.get("is_adjacent", False)
        adj_iface = l2_check.get("interface")

        if is_mikrotik:
            mac_telnet_status = PathStatus.AVAILABLE.value if (target_mac and is_adjacent) else (
                PathStatus.UNAVAILABLE.value if target_mac else PathStatus.UNSUPPORTED.value
            )
            paths.append(ManagementPath(
                method=ManagementMethod.MAC_TELNET.value,
                target=target_mac or "none",
                port=0,
                status=mac_telnet_status,
                details={"interface": adj_iface},
                selection_reason=f"Terdeteksi langsung di segmen Layer 2 pada interface {adj_iface}; MAC Telnet siap digunakan." if mac_telnet_status == PathStatus.AVAILABLE.value else "",
                rejection_reason="" if mac_telnet_status == PathStatus.AVAILABLE.value else (
                    "Perangkat tidak terdeteksi pada broadcast domain Layer 2 lokal (MAC Telnet tidak dapat melintasi router Layer 3)." if target_mac else "MAC address perangkat belum diketahui."
                ),
            ))

            mac_winbox_status = PathStatus.AVAILABLE.value if (target_mac and is_adjacent) else (
                PathStatus.UNAVAILABLE.value if target_mac else PathStatus.UNSUPPORTED.value
            )
            paths.append(ManagementPath(
                method=ManagementMethod.MAC_WINBOX.value,
                target=target_mac or "none",
                port=20561,
                status=mac_winbox_status,
                details={"interface": adj_iface},
                selection_reason=f"Layer 2 adjacent pada interface {adj_iface}; MAC WinBox port 20561 tersedia." if mac_winbox_status == PathStatus.AVAILABLE.value else "",
                rejection_reason="" if mac_winbox_status == PathStatus.AVAILABLE.value else (
                    "Bukan tetangga Layer 2 langsung. MAC WinBox hanya bekerja dalam satu segmen broadcast." if target_mac else "MAC address belum diketahui."
                ),
            ))

        # -------------------------------------------------------------
        # 3. RoMON (Router Management Overlay Network)
        # -------------------------------------------------------------
        romon_eval = CapabilityDetector.evaluate_romon_compatibility(routeros_version=routeros_version, vendor=vendor)
        romon_supported = romon_eval.get("supported", False)
        matched_neighbor: Optional[RomonNeighbor] = None

        if is_mikrotik and romon_supported and romon_neighbors:
            # Check if this device is present in discovered RoMON neighbors
            for n in romon_neighbors:
                if (target_mac and n.mac.lower() == target_mac.lower()) or (
                    device_name and n.identity.lower() == device_name.lower()
                ):
                    matched_neighbor = n
                    break

        if is_mikrotik:
            if not romon_supported:
                romon_status = PathStatus.UNSUPPORTED.value
                rejection = romon_eval.get("reason", "RoMON tidak didukung oleh versi RouterOS ini.")
                sel_reason = ""
            elif matched_neighbor:
                romon_status = PathStatus.AVAILABLE.value
                sel_reason = (
                    f"RoMON reachable melalui intermediary gateway '{matched_neighbor.via_device_name}' "
                    f"(hop count: {matched_neighbor.hop_count}, ID: {matched_neighbor.romon_id})."
                )
                rejection = ""
            else:
                romon_status = PathStatus.UNAVAILABLE.value
                rejection = (
                    "Perangkat belum terdeteksi di tabel RoMON tetangga gateway manapun. "
                    "Pastikan RoMON diaktifkan pada interface manajemen perangkat."
                )
                sel_reason = ""

            paths.append(ManagementPath(
                method=ManagementMethod.ROMON.value,
                target=matched_neighbor.romon_id if matched_neighbor else (target_mac or "none"),
                port=0,
                status=romon_status,
                intermediary_id=matched_neighbor.via_device_id if matched_neighbor else None,
                intermediary_name=matched_neighbor.via_device_name if matched_neighbor else None,
                hops=matched_neighbor.hop_count if matched_neighbor else 1,
                selection_reason=sel_reason,
                rejection_reason=rejection,
                details={"neighbor": matched_neighbor.to_dict() if matched_neighbor else None},
            ))

        # -------------------------------------------------------------
        # 4. Determine Active Path & Human-Readable Rationale
        # -------------------------------------------------------------
        active_path: Optional[ManagementPath] = None
        selection_rationale = ""

        # Check manual override first if requested
        if manual_override and preferred_method:
            target_p = next((p for p in paths if p.method == preferred_method), None)
            if target_p and target_p.status == PathStatus.AVAILABLE.value:
                active_path = target_p
                active_path.is_preferred = True
                active_path.is_active = True
                selection_rationale = f"Metode [{active_path.method}] dipilih secara manual oleh administrator (terverifikasi aktif)."
            elif target_p:
                # Path requested but not available
                selection_rationale = (
                    f"Peringatan: Metode manual [{preferred_method}] dipilih, namun status saat ini adalah "
                    f"{target_p.status} ({target_p.rejection_reason}). Menggunakan fallback otomatis."
                )

        # Automatic Evidence-Based Hierarchy
        if not active_path:
            # 1. SSH over direct IP (fastest, standard)
            ssh_p = next((p for p in paths if p.method == ManagementMethod.SSH_IP.value and p.status == PathStatus.AVAILABLE.value), None)
            # 2. RouterOS API over IP
            api_p = next((p for p in paths if p.method == ManagementMethod.API_IP.value and p.status == PathStatus.AVAILABLE.value), None)
            # 3. RoMON (multi-hop / overlay)
            romon_p = next((p for p in paths if p.method == ManagementMethod.ROMON.value and p.status == PathStatus.AVAILABLE.value), None)
            # 4. MAC Telnet (Layer 2 fallback if IP is down or unconfigured)
            mac_telnet_p = next((p for p in paths if p.method == ManagementMethod.MAC_TELNET.value and p.status == PathStatus.AVAILABLE.value), None)
            # 5. MAC Winbox
            mac_winbox_p = next((p for p in paths if p.method == ManagementMethod.MAC_WINBOX.value and p.status == PathStatus.AVAILABLE.value), None)

            if ssh_p:
                active_path = ssh_p
                selection_rationale = "Koneksi langsung Layer 3 SSH dipilih sebagai jalur utama (IP terjangkau & port 22 terbuka)."
            elif api_p:
                active_path = api_p
                selection_rationale = "RouterOS API dipilih karena port 8728 merespons aktif."
            elif romon_p:
                active_path = romon_p
                selection_rationale = (
                    f"RoMON Overlay dipilih secara otomatis karena IP langsung tidak terjangkau, "
                    f"namun perangkat ditemukan via gateway perantara '{romon_p.intermediary_name}' ({romon_p.hops} hop)."
                )
            elif mac_telnet_p:
                active_path = mac_telnet_p
                selection_rationale = (
                    f"MAC Telnet dipilih sebagai fallback darurat: IP langsung tidak terjangkau, "
                    f"namun perangkat terdeteksi langsung di Layer 2 (interface {adj_iface})."
                )
            elif mac_winbox_p:
                active_path = mac_winbox_p
                selection_rationale = "MAC WinBox dipilih sebagai fallback Layer 2."
            else:
                selection_rationale = (
                    "Tidak ada jalur manajemen yang aktif: Alamat IP tidak merespons, "
                    "perangkat tidak berada di segmen Layer 2 lokal, dan tidak terdeteksi di RoMON."
                )

        if active_path:
            active_path.is_active = True
            active_path.status = PathStatus.ACTIVE.value

        return DeviceManagementProfile(
            device_id=device_id,
            device_name=device_name,
            device_type="mikrotik" if is_mikrotik else "generic",
            vendor=vendor,
            model=model,
            routeros_version=routeros_version,
            ip=ip_target,
            mac=target_mac,
            paths=paths,
            active_path=active_path,
            manual_selection=manual_override,
            selection_rationale=selection_rationale,
            romon_enabled=bool(matched_neighbor) or (active_path and active_path.method == ManagementMethod.ROMON.value),
            romon_id=matched_neighbor.romon_id if matched_neighbor else None,
            layer2_adjacent=is_adjacent,
            adjacent_interface=adj_iface,
        )
